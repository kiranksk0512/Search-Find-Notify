import argparse
import asyncio
import time
from datetime import datetime, timezone

# Storage (router: picks S3 or local based on env)
from core.storage_router import load_json, save_json

# Notifier (router: SES or local/no-op)
from core.notifier_router import send_email_alert

# Project utilities
from core.utils import diff_jobs
from core.scraper_loader import discover_scrapers
from core.logger import get_company_logger
from core.context import current_company

# Rehydrate previously saved JSON into model objects
from core.rehydrate import rehydrate_jobs

# Small type to return results without emailing per-company
from core.types import ScrapeSummary

# Per-company on/off switches (still honored in aggregated digest)
from config import COMPANY_EMAIL_NOTIFICATIONS


def parse_args():
    parser = argparse.ArgumentParser(description="Job Scraper CLI")
    parser.add_argument("--company", type=str, default="all", help="Company to scrape (or 'all')")
    parser.add_argument("--force-version", action="store_true", help="Force versioned backup")
    parser.add_argument("--no-email", action="store_true", help="Disable email notifications")
    return parser.parse_args()


async def run_scraper(company_name, scraper_func, force_version=False) -> ScrapeSummary:
    """
    Runs a single company's scraper.
    - Times the run
    - Logs runtime
    - Returns a ScrapeSummary with new/deleted jobs for aggregation
    """
    current_company.set(company_name)
    logger = get_company_logger(company_name)
    logger.info(f"🔍 Starting scraper for {company_name.title()}...")

    start_time = time.time()

    try:
        # 1) scrape current (model objects)
        current_jobs = await scraper_func()
        current_jobs_dict = {job.job_id: job for job in current_jobs}

        # 2) load baseline and rehydrate to model objects
        previous_jobs_raw = load_json(company_name)               # {job_id: dict}
        previous_jobs = rehydrate_jobs(company_name, previous_jobs_raw)  # {job_id: Model}

        logger.info(f"📦 Previous: {len(previous_jobs)} | Current: {len(current_jobs_dict)}")

        # 3) compute diffs
        new_job_objs = diff_jobs(current_jobs_dict, previous_jobs)
        deleted_job_objs = diff_jobs(previous_jobs, current_jobs_dict)

        logger.info(f"🧮 New: {len(new_job_objs)} | Deleted: {len(deleted_job_objs)}")

        # 4) save snapshot
        save_json(
            company_name,
            {jid: job.to_dict() for jid, job in current_jobs_dict.items()},
            force_version=force_version
        )

        runtime = time.time() - start_time
        logger.info(f"✅ Finished scraping {company_name} in {runtime:.2f} seconds")
        return ScrapeSummary(company=company_name, new=new_job_objs, deleted=deleted_job_objs, error=None)

    except Exception as e:
        runtime = time.time() - start_time
        logger.exception(f"❌ Scraper for {company_name} failed after {runtime:.2f} seconds: {e}")
        # return the error string so the digest can explain why this company has no jobs in the email
        return ScrapeSummary(company=company_name, new={}, deleted={}, error=str(e))

def _format_new_job(job) -> str:
    """Pretty block for a 'new' job; works for model or dict (fallback)."""
    if hasattr(job, "format_message"):
        return job.format_message()
    # Fallback if ever needed
    title = job.get("title", "Unknown")
    url = job.get("url", "")
    loc = job.get("location", "Unknown")
    posted = job.get("date_posted", "Unknown")
    return f"{title}\n{url}\nLocation: {loc}\nPosted: {posted}"


def _format_deleted_job(job) -> str:
    """For deleted jobs we typically just list URL."""
    if hasattr(job, "url"):
        return job.url or ""
    return job.get("url", "")


def _company_enabled(name: str) -> bool:
    """Honor per-company email toggles when building the digest."""
    return COMPANY_EMAIL_NOTIFICATIONS.get(name, True)


def build_digest(results, no_email: bool):
    if no_email:
        return None

    sections = []
    total_new = 0
    total_deleted = 0

    no_change_list = []      # companies enabled but no changes
    skipped_list = []        # companies disabled by config
    failed_list = []         # (company, error)

    # First pass: build sections for companies with changes and collect reasons for others
    for r in results:
        enabled = _company_enabled(r.company)

        if r.error:
            failed_list.append((r.company, r.error))
            continue

        n, d = len(r.new), len(r.deleted)

        if not enabled:
            # explain why it’s not in the digest
            if n or d:
                # even if there were changes, we’re skipping by policy
                skipped_list.append(f"{r.company} (changes suppressed by config)")
            else:
                skipped_list.append(f"{r.company} (suppressed by config)")
            continue

        if n == 0 and d == 0:
            no_change_list.append(r.company)
            continue

        # enabled and has changes -> render full section
        total_new += n
        total_deleted += d
        sections.append(f"==== {r.company.upper()} ====")

        if n:
            sections.append(f"🆕 New jobs: {n}")
            for job in r.new.values():
                sections.append(_format_new_job(job))
                sections.append("")

        if d:
            sections.append(f"🗑️ Deleted jobs: {d}")
            urls = [getattr(j, "url", "") if hasattr(j, "url") else j.get("url", "") for j in r.deleted.values()]
            urls = [u for u in urls if u]
            if urls:
                sections.extend(urls)
            sections.append("")

        sections.append("------------------------------")

    # Add “No changes” / “Skipped” / “Failed” summaries
    if no_change_list:
        sections.append("🟦 No changes:")
        sections.append(", ".join(sorted(no_change_list)))
        sections.append("------------------------------")

    if skipped_list:
        sections.append("⛔ Skipped by config:")
        for line in sorted(skipped_list):
            sections.append(f"- {line}")
        sections.append("------------------------------")

    if failed_list:
        sections.append("⚠️ Failed scrapers:")
        for company, err in failed_list:
            # keep error short
            msg = err.strip().split("\n", 1)[0]
            if len(msg) > 200:
                msg = msg[:200] + "…"
            sections.append(f"- {company}: {msg}")
        sections.append("------------------------------")

    if not sections:
        return None

    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"Job Digest ({ts}) — New: {total_new}, Deleted: {total_deleted}"
    body = "\n".join(sections).strip()
    if len(body) > 190_000:
        body = body[:190_000] + "\n\n…(truncated)"
    return subject, body


async def main():
    args = parse_args()
    scraper_map = discover_scrapers()
    global_logger = get_company_logger("general")
    start_time = time.time()

    # 1) choose which scrapers to run
    if args.company.lower() == "all":
        global_logger.info("🔁 Starting all scrapers...")
        tasks = [run_scraper(company, scraper_func, args.force_version)
                 for company, scraper_func in scraper_map.items()]
        results = await asyncio.gather(*tasks, return_exceptions=False)
    else:
        company = args.company.lower()
        scraper_func = scraper_map.get(company)
        if not scraper_func:
            global_logger.error(f"❌ No scraper found for company '{company}'")
            return
        results = [await run_scraper(company, scraper_func, args.force_version)]

    # 2) aggregated email (single SES send)
    digest = build_digest(results, args.no_email)
    if digest:
        subject, body = digest
        send_email_alert(subject, body)
        global_logger.info("📧 Sent aggregated digest.")
    else:
        global_logger.info("✅ No changes (or email disabled); no digest sent.")

    # 3) summary logs
    total_time = time.time() - start_time
    succeeded = sum(1 for r in results if r.new is not None and r.deleted is not None)
    failed = sum(1 for r in results if r.new is None and r.deleted is None)

    changed_companies = sum(1 for r in results if r.new or r.deleted)

    global_logger.info("📋 SUMMARY")
    global_logger.info(f"🏢 Ran scrapers: {len(results)} | 🔄 Changed: {changed_companies}")
    global_logger.info(f"✅ Succeeded: {succeeded}")
    global_logger.info(f"❌ Failed: {failed}")
    global_logger.info(f"⏱ Total Runtime: {total_time:.2f} seconds")

if __name__ == "__main__":
    asyncio.run(main())
