import random
import asyncio
from core.fetcher import post_json
from models.amazon_job import AmazonJob
from datetime import datetime
from zoneinfo import ZoneInfo
from core.logger import get_company_logger

API_URL = "https://www.amazon.jobs/api/jobs/search?is_als=true"

COOKIE_INFO = (
    "cookie_preferences=%7B%22advertising%22%3Afalse%2C%22analytics%22%3Afalse%2C%22version%22%3A2%7D;"
    " __Host-mons-sid=141-3830651-8920553; "
    "preferred_locale=en-US; "
    "__Host-mons-ubid=133-7864929-1942824; "
    "csm-sid=498-3926861-3708573; "
    "__Host-mons-st=o93WuIThtS0bYY4fxyP4fIxp+VSYGAzSBGuCnTwm63gI..."
)

CATEGORY_MAP = {
    "software-development": "Software Development",
    "systems-quality-security-engineering": "Systems, Quality, & Security Engineering",
    "solutions-architecture": "Solutions Architect",
    "data-science": "Data Science",
    "database-administration": "Database Administration"
}

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)... Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)... Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64)... Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3)... Version/16.4 Safari/605.1.15"
]

def get_headers(slug: str) -> dict:
    referer = f"https://www.amazon.jobs/content/en/job-categories/{slug}?country%5B%5D=US&employment-type%5B%5D=Full+time"
    return {
        "Accept": "application/json",
        "Accept-Language": random.choice(["en-GB,en-US;q=0.9,en;q=0.8", "en-US,en;q=0.9"]),
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://www.amazon.jobs",
        "Pragma": "no-cache",
        "Referer": referer,
        "User-Agent": random.choice(USER_AGENTS),
        "x-api-key": "PbxxNwIlTi4FP5oijKdtk3IrBF5CLd4R4oPHsKNh"
    }

def build_payload(category_name="Software Development", start=0, size=20):
    return {
        "accessLevel": "EXTERNAL",
        "contentFilterFacets": [{"name": "primarySearchLabel", "requestedFacetCount": 9999}],
        "excludeFacets": [
            {"name": "isConfidential", "values": [{"name": "1"}]},
            {"name": "businessCategory", "values": [{"name": "a-confidential-job"}]}
        ],
        "filterFacets": [{"name": "category", "requestedFacetCount": 9999, "values": [{"name": category_name}]}],
        "includeFacets": [],
        "jobTypeFacets": [{"name": "scheduleTypeId", "values": [{"name": "Full-Time"}]}],
        "locationFacets": [[
            {"name": "country", "requestedFacetCount": 9999, "values": [{"name": "US"}]},
            {"name": "normalizedStateName", "requestedFacetCount": 9999},
            {"name": "normalizedCityName", "requestedFacetCount": 9999}
        ]],
        "query": "",
        "size": size,
        "start": start,
        "treatment": "OM",
        "cookieInfo": COOKIE_INFO,
        "sort": {"sortOrder": "DESCENDING", "sortType": "CREATED_DATE"}
    }

def convert_timestamp_to_edt(ts_str):
    try:
        ts = int(ts_str)
        dt_utc = datetime.fromtimestamp(ts, tz=ZoneInfo("UTC"))
        dt_edt = dt_utc.astimezone(ZoneInfo("America/New_York"))
        return dt_edt.strftime("%b %d, %Y %I:%M %p %Z")
    except Exception:
        return "Unknown"

async def get_jobs():
    logger = get_company_logger()
    logger.info("Starting Amazon job scrape")
    categories = list(CATEGORY_MAP.keys())
    all_jobs = []

    # Add random jitter before starting
    await asyncio.sleep(random.uniform(0, 20))

    for slug in categories:
        category_name = CATEGORY_MAP[slug]
        logger.info(f"🔍 Starting scraper for {category_name} category in Amazon...")
        start = 0
        size = 10
        while True:
            headers = get_headers(slug)
            payload = build_payload(category_name, start, size)
            data = await post_json(API_URL, payload, headers)
            if not data:
                break

            hits = data.get("searchHits", [])
            if not hits:
                break

            for job in hits:
                fields = job.get("fields", {})
                job_id = fields.get("icimsJobId", ["Unknown"])[0]
                job_code = fields.get("jobCode", ["Unknown"])[0]
                title = fields.get("title", ["Unknown"])[0]
                team = fields.get("jobFamily", ["N/A"])[0]
                location = fields.get("location", ["Unknown"])[0]
                city = fields.get("city", ["N/A"])[0]
                company_name = fields.get("companyName", ["Amazon"])[0]
                job_role = fields.get("jobRole", ["N/A"])[0]
                employee_class = fields.get("employeeClass", ["N/A"])[0]
                url = f"https://www.amazon.jobs/en/jobs/{job_id}"
                businessCategory = fields.get("businessCategory", ["Unknown"])[0]
                category = fields.get("category", ["Unknown"])[0]
                centralRecruitmentTeam = fields.get("centralRecruitmentTeam", ["Unknown"])[0]
                hireTypeId = fields.get("hireTypeId", ["Unknown"])[0]
                roleFungibility = fields.get("roleFungibility", ["Unknown"])[0]
                sourceSystem = fields.get("sourceSystem", ["Unknown"])[0]

                raw_posted = fields.get("createdDate", [""])[0]
                raw_updated = fields.get("updatedDate", [""])[0]
                created_date = convert_timestamp_to_edt(raw_posted)
                updated_date = convert_timestamp_to_edt(raw_updated)

                job_obj = AmazonJob(
                    job_id=job_id,
                    job_code=job_code,
                    title=title,
                    url=url,
                    date_posted=created_date,
                    created_date=created_date,
                    location=location,
                    team=team,
                    city=city,
                    company=company_name,
                    role=job_role,
                    employee_class=employee_class,
                    updated_date=updated_date,
                    businessCategory=businessCategory,
                    category=category,
                    centralRecruitmentTeam=centralRecruitmentTeam,
                    hireTypeId=hireTypeId,
                    roleFungibility=roleFungibility,
                    sourceSystem=sourceSystem
                )
                all_jobs.append(job_obj)

            start += size
            logger.info(f"Till now retrieved {start} Jobs.")
            # Add random delay between pages
            await asyncio.sleep(random.uniform(1, 5))
        logger.info(f"🔍 Completed scraper for {category_name} category in Amazon...")
    logger.info(f"Scraped {len(all_jobs)} Amazon jobs.")
    return all_jobs
