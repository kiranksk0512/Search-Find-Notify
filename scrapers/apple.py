import random
import asyncio
from core.fetcher import post_json
from models.apple_job import AppleJob
from datetime import datetime
from zoneinfo import ZoneInfo
from core.logger import get_company_logger

logger = get_company_logger()
API_URL = "https://jobs.apple.com/api/v1/search"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15"
]

def build_headers():
    return {
        "Content-Type": "application/json",
        "Origin": "https://jobs.apple.com",
        "Referer": "https://jobs.apple.com/en-us/search",
        "User-Agent": random.choice(USER_AGENTS)
    }

def build_payload(page):
    return {
        "query": "",
        "filters": {
            "locations": ["postLocation-USA"]
        },
        "page": page,
        "locale": "en-us",
        "sort": "newest",
        "format": {
            "longDate": "MMMM D, YYYY",
            "mediumDate": "MMM D, YYYY"
        }
    }

def convert_to_edt(utc_string):
    try:
        dt_utc = datetime.fromisoformat(utc_string.rstrip("Z"))
        dt_edt = dt_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/New_York"))
        return dt_edt.strftime("%b %d, %Y %I:%M %p %Z")
    except Exception:
        return "Unknown"
    
def apple_job_url(job_id: str) -> str:
    # PIPE-* postings use only the numeric part
    if job_id.startswith("PIPE-"):
        return f"https://jobs.apple.com/en-us/details/{job_id.split('-', 1)[1]}"
    # all other IDs should use the full ID, including the dash
    return f"https://jobs.apple.com/en-us/details/{job_id}"

async def get_jobs():
    job_list = []
    page = 1

    # Optional: add random jitter before starting, so different runs don't look identical
    await asyncio.sleep(random.uniform(0, 20))
    logger.info("Entered get_jobs()")

    while True:
        payload = build_payload(page)
        headers = build_headers()

        data = await post_json(API_URL, payload, headers)
        if not data:
            break

        results = data.get("res", {}).get("searchResults", [])
        if not results:
            break
        NoOfJobsInAPage = 0
        for job in results:
            job_id = job.get("id")
            title = job.get("postingTitle", "Unknown")
            team = job.get("team", {}).get("teamName", "N/A")
            location = job.get("locations", [{}])[0].get("countryName", "Unknown")
            post_gmt = job.get("postDateInGMT", "Unknown")
            date_posted = convert_to_edt(post_gmt)
            url = apple_job_url(job_id)

            job_obj = AppleJob(
                job_id=job_id,
                title=title,
                url=url,
                date_posted=date_posted,
                team=team,
                location=location
            )
            NoOfJobsInAPage += 1
            job_list.append(job_obj)
        logger.info(f"Found {NoOfJobsInAPage} jobs in Page : {page}")
        logger.info(f"Page :{page} completed")
        page += 1

        # Add random delay between pages
        await asyncio.sleep(random.uniform(1, 5))
        logger.info(f"Exiting get_jobs()")
    logger.info(f"🎉 Found : {len(job_list)} jobs")
    return job_list
