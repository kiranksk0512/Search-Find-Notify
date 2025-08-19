import argparse
import asyncio
import time
from datetime import datetime
from core.storage import load_json, save_json
from core.utils import diff_jobs
from core.notifier import send_email_alert
from core.scraper_loader import discover_scrapers
from config import COMPANY_EMAIL_NOTIFICATIONS
from core.logger import get_company_logger
from core.context import current_company



def parse_args():
    parser = argparse.ArgumentParser(description="Job Scraper CLI")
    parser.add_argument("--company", type=str, default="all", help="Company to scrape (or 'all')")
    parser.add_argument("--force-version", action="store_true", help="Force versioned backup")
    parser.add_argument("--no-email", action="store_true", help="Disable email notifications")
    return parser.parse_args()

async def run_scraper(company_name, scraper_func, force_version=False, no_email=False):
    current_company.set(company_name)
    logger = get_company_logger(company_name)
    logger.info(f"🔍 Starting scraper for {company_name.title()}...")
    try:
        current_jobs = await scraper_func()
        previous_jobs = load_json(company_name)
        current_jobs_dict = {job.job_id: job for job in current_jobs}
        new_job_objs = diff_jobs(current_jobs_dict, previous_jobs)
        deleted_job_objs = diff_jobs(previous_jobs, current_jobs_dict)

        if new_job_objs:
            logger.info(f"🆕 {len(new_job_objs)} new jobs found for {company_name}")
            should_email = COMPANY_EMAIL_NOTIFICATIONS.get(company_name, True) and not no_email
            if should_email:
                email_body = "\n\n".join(job.format_message() for job in new_job_objs.values())
                send_email_alert(f"New {company_name.title()} Jobs!", email_body)
            else:
                logger.info("📭 New Jobs Email alert skipped.")
        else:
            logger.info(f"✅ No new jobs for {company_name}")

        if deleted_job_objs:
            logger.info(f"🆕 {len(deleted_job_objs)} deleted jobs found for {company_name}")
            should_email = COMPANY_EMAIL_NOTIFICATIONS.get(company_name, True) and not no_email
            if should_email:
                email_body = "\n\n".join(job.url for job in deleted_job_objs.values())
                send_email_alert(f"New {company_name.title()} Jobs!", email_body)
            else:
                logger.info("📭 Deleted Jobs Email alert skipped.")
        else:
            logger.info(f"✅ No deleted jobs for {company_name}")

        # Save scraped job data
        save_json(
            company_name,
            {job.job_id: job.to_dict() for job in current_jobs},
            force_version=force_version
        )
        
        logger.info(f"✅ Finished scraping {company_name}")
        return True

    except Exception as e:
        logger.exception(f"❌ Scraper for {company_name} failed with error: {e}")
        return False


async def main():
    args = parse_args()
    scraper_map = discover_scrapers()
    global_logger = get_company_logger("general")
    start_time = time.time()

    if args.company.lower() == "all":
        global_logger.info("🔁 Starting all scrapers...")
        tasks = []
        results = []

        for company, scraper_func in scraper_map.items():
            tasks.append(run_scraper(company, scraper_func, args.force_version, args.no_email))

        results = await asyncio.gather(*tasks, return_exceptions=False)
        succeeded = sum(1 for r in results if r is True)
        failed = len(results) - succeeded

        total_time = time.time() - start_time
        global_logger.info("📋 SUMMARY")
        global_logger.info(f"✅ Succeeded: {succeeded}")
        global_logger.info(f"❌ Failed: {failed}")
        global_logger.info(f"⏱ Total Runtime: {total_time:.2f} seconds")
    else:
        company = args.company.lower()
        scraper_func = scraper_map.get(company)
        if not scraper_func:
            global_logger.error(f"❌ No scraper found for company '{company}'")
            return
        await run_scraper(company, scraper_func, args.force_version, args.no_email)

if __name__ == "__main__":
    asyncio.run(main())
