import argparse
import asyncio
import os
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

# Scraper result object
from core.scrape_types import ScrapeResult

# Per-company on/off switches (still honored in aggregated digest)
from config import COMPANY_EMAIL_NOTIFICATIONS

from config import (
    BASE_DATA_PATH,
    STABILITY_ENABLED,
    MISS_THRESHOLD,
    REOPEN_GRACE_DAYS,
    BIG_DROP_REFETCH_RATIO,
    MAX_REFETCHES,
)
from core.stability import confirm_big_drop, apply_stability


def parse_args():
    parser = argparse.ArgumentParser(description="Job Scraper CLI")
    parser.add_argument("--company", type=str, default="all", help="Company to scrape (or 'all')")
    parser.add_argument("--force-version", action="store_true", help="Force versioned backup")
    parser.add_argument("--no-email", action="store_true", help="Disable email notifications")
    return parser.parse_args()


async def run_scraper(company_name: str, scraper_func, force_version: bool = False) -> ScrapeSummary:
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
        # 1) scrape current (object contract)
        result: ScrapeResult = await scraper_func()

        current_jobs_list = result.jobs or []
        should_persist = bool(result.should_persist)
        decision_reason = result.decision_reason or "ok"
        stats = result.stats or {}
        default_count = stats.get("default_count")
        new_count = stats.get("new_count")

        logger.info(
            f"🧭 Decision from scraper: should_persist={should_persist} "
            f"reason={decision_reason} total={len(current_jobs_list)} "
            f"(default={default_count}, new={new_count})"
        )

        # Skip persist/notify if scraper signals anomalous retrieval
        if not should_persist:
            logger.warning(
                f"🧯 Skipping persist/notifications for {company_name} "
                f"(reason={decision_reason}; count={len(current_jobs_list)})"
            )
            runtime = time.time() - start_time
            logger.info(f"✅ Finished scraping {company_name} in {runtime:.2f} seconds (no-op persist/notify)")
            return ScrapeSummary(
                company=company_name,
                new={},
                deleted={},
                error=(
                    f"🧯 Skipping persist/notifications for {company_name} "
                    f"(reason={decision_reason}; count={len(current_jobs_list)})"
                ),
                reopened={}
            )

        # 2) load baseline and rehydrate
        previous_jobs_raw = load_json(company_name)                      # {job_id: dict}
        previous_jobs = rehydrate_jobs(company_name, previous_jobs_raw)  # {job_id: Model}

        # 2b) Big-drop confirmation (refetch + union) BEFORE diffing
        prev_count = len(previous_jobs)

        async def _refetch_jobs_only():
            r: ScrapeResult = await scraper_func()
            return r.jobs or []

        if prev_count > 0:
            current_jobs_list = await confirm_big_drop(
                prev_count=prev_count,
                current_jobs=current_jobs_list,
                scraper_func=_refetch_jobs_only,
                ratio_threshold=BIG_DROP_REFETCH_RATIO,
                max_refetches=MAX_REFETCHES,
                logger=logger,
            )

        current_jobs_dict = {job.job_id: job for job in current_jobs_list}
        logger.info(f"📦 Previous: {len(previous_jobs)} | Current (after confirmation): {len(current_jobs_dict)}")

        # 3) Stability path (company-scoped) vs. regular diff
        if STABILITY_ENABLED.get(company_name, True):
            new_job_objs, deleted_job_objs, quarantined_missing, reopened = apply_stability(
                company_name=company_name,
                base_data_path=BASE_DATA_PATH,
                current_jobs_dict=current_jobs_dict,
                previous_jobs=previous_jobs,
                miss_threshold=MISS_THRESHOLD,
                reopen_grace_days=REOPEN_GRACE_DAYS,
                logger=logger,
            )
            logger.info(f"🟨 Quarantined(missing<thr): {len(quarantined_missing)} | 🔁 Reopened: {len(reopened)}")
        else:
            new_job_objs = diff_jobs(current_jobs_dict, previous_jobs)
            deleted_job_objs = diff_jobs(previous_jobs, current_jobs_dict)
            quarantined_missing, reopened = {}, {}

        logger.info(f"🧮 New: {len(new_job_objs)} | Deleted: {len(deleted_job_objs)}")

        # 4) Save the *current snapshot* (keep store accurate)
        save_json(
            company_name,
            {jid: job.to_dict() for jid, job in current_jobs_dict.items()},
            force_version=force_version
        )

        runtime = time.time() - start_time
        logger.info(f"✅ Finished scraping {company_name} in {runtime:.2f} seconds")
        return ScrapeSummary(company=company_name, new=new_job_objs, deleted=deleted_job_objs, error=None, reopened=reopened)

    except Exception as e:
        runtime = time.time() - start_time
        logger.exception(f"❌ Scraper for {company_name} failed after {runtime:.2f} seconds: {e}")
        return ScrapeSummary(company=company_name, new={}, deleted={}, error=str(e), reopened={})


def _format_new_job(job) -> str:
    """Pretty block for a 'new' job; works for model or dict (fallback)."""
    if hasattr(job, "format_message"):
        return job.format_message()
    if isinstance(job, dict):
        title = job.get("title", "Unknown")
        url = job.get("url", "")
        loc = job.get("location", "Unknown")
        posted = job.get("date_posted", "Unknown")
        return f"{title}\n{url}\nLocation: {loc}\nPosted: {posted}"
    url = getattr(job, "url", "") or ""
    title = getattr(job, "title", "") or "Unknown"
    return f"{title}\n{url}"


def _format_deleted_job(job) -> str:
    """For deleted jobs we typically just list URL."""
    if hasattr(job, "url"):
        return job.url or ""
    if isinstance(job, dict):
        return job.get("url", "")
    return ""


def _company_enabled(name: str) -> bool:
    """Honor per-company email toggles when building the digest."""
    return COMPANY_EMAIL_NOTIFICATIONS.get(name, True)


def build_digest(results, no_email: bool):
    if no_email:
        return None

    sections = []
    total_new = 0
    total_deleted = 0
    total_reopened = 0  # includes stability reopen events

    no_change_list = []
    skipped_list = []
    failed_list = []

    for r in results:
        enabled = _company_enabled(r.company)

        if r.error:
            failed_list.append((r.company, r.error))
            continue

        n, d = len(r.new), len(r.deleted)
        r_opened_dict = getattr(r, "reopened", {}) or {}
        r_open = len(r_opened_dict)

        if not enabled:
            if n or d or r_open:
                skipped_list.append(f"{r.company} (changes suppressed by config)")
            else:
                skipped_list.append(f"{r.company} (suppressed by config)")
            continue

        if n == 0 and d == 0 and r_open == 0:
            no_change_list.append(r.company)
            continue

        total_new += n
        total_deleted += d
        total_reopened += r_open
        sections.append(f"==== {r.company.upper()} ====")

        if n:
            sections.append(f"🆕 New jobs: {n}")
            for job in r.new.values():
                sections.append(_format_new_job(job))
                sections.append("")

        if r_open:
            # sections.append(f"🔁 Reopened before delete threshold (not new): {r_open}")
            seen_urls = set()
            for j in r_opened_dict.values():
                url = getattr(j, "url", "") if hasattr(j, "url") else (j.get("url", "") if isinstance(j, dict) else "")
                title = getattr(j, "title", "") if hasattr(j, "title") else (j.get("title", "") if isinstance(j, dict) else "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    prefix = f"{title} – " if title else ""
                    # sections.append(f"{prefix}{url}")
            # sections.append("")

        if d:
            sections.append(f"🗑️ Deleted jobs: {d}")
            urls = []
            for j in r.deleted.values():
                if hasattr(j, "url"):
                    urls.append(j.url or "")
                elif isinstance(j, dict):
                    urls.append(j.get("url", ""))
            urls = [u for u in urls if u]
            if urls:
                sections.extend(urls)
            sections.append("")

        sections.append("------------------------------")

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
            msg = err.strip().split("\n", 1)[0]
            if len(msg) > 200:
                msg = msg[:200] + "…"
            sections.append(f"- {company}: {msg}")
        sections.append("------------------------------")

    if not sections:
        return None

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"JobTrotter is here, ({ts}) — New: {total_new}, Deleted: {total_deleted}, Reopened: {total_reopened}"
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
    skipped_companies = []

    skip_env = os.getenv("SFN_SKIP_COMPANIES", "")
    skip_companies = {
        company.strip().lower()
        for company in skip_env.split(",")
        if company.strip()
    }

    if args.company.lower() == "all":
        global_logger.info("🔁 Starting all scrapers...")
        tasks = []
        for company, scraper_func in scraper_map.items():
            if company in skip_companies:
                global_logger.info(
                    f"⏭️ Skipping {company} because it's listed in SFN_SKIP_COMPANIES"
                )
                skipped_companies.append(company)
                continue
            tasks.append(run_scraper(company, scraper_func, args.force_version))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=False)
        else:
            results = []
    else:
        company = args.company.lower()
        scraper_func = scraper_map.get(company)
        if not scraper_func:
            global_logger.error(f"❌ No scraper found for company '{company}'")
            return
        if company in skip_companies:
            global_logger.info(
                f"⏭️ {company} run disabled because it's listed in SFN_SKIP_COMPANIES"
            )
            skipped_companies.append(company)
            results = []
        else:
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
    succeeded = sum(1 for r in results if not r.error)
    failed = sum(1 for r in results if r.error)

    # Count runs that had any type of change, including reopened
    changed_companies = sum(1 for r in results if r.new or r.deleted or (getattr(r, "reopened", {}) or {}))

    global_logger.info("📋 SUMMARY")
    if skipped_companies:
        global_logger.info(
            f"⏭️ Skipped (env): {', '.join(sorted(skipped_companies))}"
        )
    global_logger.info(f"🏢 Ran scrapers: {len(results)} | 🔄 Changed: {changed_companies}")
    global_logger.info(f"✅ Succeeded: {succeeded}")
    global_logger.info(f"❌ Failed: {failed}")
    global_logger.info(f"⏱ Total Runtime: {total_time:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(main())
