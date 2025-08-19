import html
from datetime import datetime
from zoneinfo import ZoneInfo
from core.logger import get_company_logger
from core.fetcher import get_json
from models.netflix_job import NetflixJob

logger = get_company_logger("netflix")

BASE_URL = "https://explore.jobs.netflix.net/api/apply/v2/jobs"

HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Content-Type": "application/json",
    "Pragma": "no-cache",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Referer": (
        "https://explore.jobs.netflix.net/careers?"
        "location=United%20States&pid=790304512952&"
        "Teams=Data%20%26%20Insights&Teams=Engineering%20Operations&"
        "Teams=Product%20Design&Teams=Engineering&"
        "domain=netflix.com&sort_by=new"
    ),
}

async def get_jobs():
    page = 0
    all_jobs = []
    seen_ids = set()
    consecutive_empty_pages = 0

    while True:
        # Build params as list of tuples so multiple 'Teams' keys are kept
        params = [
            ('domain', 'netflix.com'),
            ('location', 'United States'),
            ('sort_by', 'new'),
            ('Teams', 'Data & Insights'),
            ('Teams', 'Engineering Operations'),
            ('Teams', 'Product Design'),
            ('Teams', 'Engineering'),
            ('num', 10),
            ('pid', '790304512952'),
            ('exclude_pid', '790304512952'),
            ('start', page * 10),
        ]

        logger.info(f"📦 Fetching page {page} with Teams: ['Engineering', 'Data & Insights', 'Product Design', 'Engineering Operations']")

        data = await get_json(BASE_URL, headers=HEADERS, params=params)
        if not data:
            logger.error(f"❌ Failed to fetch or parse data for page {page}")
            break

        job_list = data.get("positions", [])
        logger.info(f"✅ Page {page}: Retrieved {len(job_list)} jobs.")

        if not job_list:
            consecutive_empty_pages += 1
            if consecutive_empty_pages >= 3:
                logger.warning("⚠️ Stopping: 3 consecutive empty pages.")
                break
            page += 1
            continue

        consecutive_empty_pages = 0
        for job in job_list:
            job_id = str(job.get("id"))
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            job_title = html.unescape(job.get("name"))
            url = job.get("canonicalPositionUrl") or f"https://explore.jobs.netflix.net/careers/job/{job_id}"
            location = job.get("location", "United States")

            # Convert timestamps
            raw_t_create = job.get("t_create", 0)
            raw_t_update = job.get("t_update", 0)
            t_create_dt = datetime.fromtimestamp(raw_t_create, tz=ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S") if raw_t_create else ""
            t_update_dt = datetime.fromtimestamp(raw_t_update, tz=ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S") if raw_t_update else ""

            all_jobs.append(NetflixJob(
                job_id=job_id,
                title=job_title,
                url=url,
                location=location,
                date_posted=t_update_dt,
                ats_job_id=job.get("ats_job_id", ""),
                business_unit=job.get("business_unit", ""),
                department=job.get("department", ""),
                display_job_id=job.get("display_job_id", ""),
                is_private=job.get("isPrivate", False),
                created_date=t_create_dt,
                updated_date=t_update_dt,
                type=job.get("type", ""),
                work_location_option=job.get("work_location_option", ""),
                locations=job.get("locations", []),
            ))

        page += 1

    logger.info(f"🎉 Total Netflix jobs found: {len(all_jobs)}")
    return all_jobs
