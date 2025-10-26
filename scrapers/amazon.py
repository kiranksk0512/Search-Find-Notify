from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from zoneinfo import ZoneInfo

from core.fetcher import post_json
from core.logger import get_company_logger
from core.context import get_company
from core.scrape_types import ScrapeResult
from core.decision import retry_and_decide
from models.amazon_job import AmazonJob

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

logger = get_company_logger()


def _ua() -> str:
    return random.choice(USER_AGENTS)


def get_headers(slug: str, ua: Optional[str] = None) -> dict:
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
        "User-Agent": ua or _ua(),
        "x-api-key": "PbxxNwIlTi4FP5oijKdtk3IrBF5CLd4R4oPHsKNh",
    }


def build_payload(category_name: str, start: int = 0, size: int = 20) -> dict:
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

def convert_timestamp_to_edt(ts_str: str) -> str:
    try:
        ts = int(ts_str)
        dt_utc = datetime.fromtimestamp(ts, tz=ZoneInfo("UTC"))
        dt_edt = dt_utc.astimezone(ZoneInfo("America/New_York"))
        return dt_edt.strftime("%b %d, %Y %I:%M %p %Z")
    except Exception:
        return "Unknown"


async def _scrape_once(label: str) -> ScrapeResult:
    """
    One full Amazon scrape across configured categories.
    Returns a ScrapeResult (object mode).
    """
    company = get_company()
    run_ua = _ua()
    logger.info(f"[company={company}] 🚀 Amazon scrape ({label}) starting (ua={run_ua})…")

    # Small jitter to de-sync from other jobs
    await asyncio.sleep(random.uniform(0.0, 2.5))

    categories = list(CATEGORY_MAP.items())  # [(slug, name), ...]
    all_jobs: list[AmazonJob] = []
    per_cat_counts: Dict[str, int] = {}
    total_pages = 0

    for slug, category_name in categories:
        logger.info(f"[company={company}] ▶️ Amazon category: {category_name}")
        start = 0
        size = 20
        cat_count = 0

        while True:
            headers = get_headers(slug, ua=run_ua)
            payload = build_payload(category_name, start=start, size=size)
            data = await post_json(API_URL, payload, headers)
            total_pages += 1

            if not data:
                logger.warning(f"[company={company}] ⚠️ Empty/failed response for category={category_name} start={start}")
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

                created_raw = fields.get("createdDate", [""])[0]
                updated_raw = fields.get("updatedDate", [""])[0]
                created_date = convert_timestamp_to_edt(created_raw)
                updated_date = convert_timestamp_to_edt(updated_raw)

                all_jobs.append(
                    AmazonJob(
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
                        sourceSystem=sourceSystem,
                    )
                )
                cat_count += 1

            start += size
            logger.info(f"[company={company}] 📦 Category={category_name} retrieved {cat_count} so far; next start={start}")
            await asyncio.sleep(random.uniform(0.8, 2.4))  # polite pacing

        per_cat_counts[category_name] = cat_count
        logger.info(f"[company={company}] ✅ Category done: {category_name} count={cat_count}")

    total_jobs = len(all_jobs)
    logger.info(f"[company={company}] 🎉 Amazon union: {total_jobs} jobs across {len(categories)} categories, pages={total_pages}")

    # If *everything* returned empty, mark anomalous_zero to trigger retry path
    anomalous_zero = (total_jobs == 0)

    return ScrapeResult(
        jobs=all_jobs,
        scrape_id=str(random.getrandbits(32))[:8],
        anomalous_zero=anomalous_zero,
        stats={
            "total_jobs": total_jobs,
            "total_pages": total_pages,
            "per_category": per_cat_counts,
            "user_agent": run_ua,
        },
        meta={"mode": "categories"},
    )


def should_persist_jobs(result: ScrapeResult, min_expected_count: int = 50) -> Tuple[bool, str]:
    """
    Amazon policy (object mode). Returns (should_persist, decision_reason).
    """
    company = get_company()

    if result is None:
        return False, "no_result"

    if result.anomalous_zero:
        logger.warning(f"[company={company}] [{result.scrape_id}] 🧯 anomalous_zero=True; skip persist/notify.")
        return False, "anomalous_zero"

    jobs_count = len(result.jobs or [])
    if jobs_count == 0:
        logger.warning(f"[company={company}] [{result.scrape_id}] 🧯 zero jobs; skip persist/notify.")
        return False, "zero_jobs"

    if jobs_count < min_expected_count:
        logger.warning(
            f"[company={company}] [{result.scrape_id}] 🧯 Too few jobs ({jobs_count}<{min_expected_count}); "
            "treating as partial outage; skip persist/notify."
        )
        return False, f"too_few({jobs_count}<{min_expected_count})"

    return True, "ok"


async def get_jobs(min_expected_count: int = 50) -> ScrapeResult:
    """
    Public entry: returns a ScrapeResult (object mode).
    """
    company = get_company()

    async def _run_once(label: str) -> ScrapeResult:
        # optional longer jitter at top to spread load if many scrapers run together
        await asyncio.sleep(random.uniform(0.0, 2.5))
        return await _scrape_once(label)

    first = await _run_once("first-pass")

    decided = await retry_and_decide(
        company=company,
        logger=logger,
        first_result=first,
        retry_fn=lambda: _run_once("retry-after-anomaly"),
        min_expected_count=min_expected_count,
        should_persist_fn=should_persist_jobs,
    )

    return decided
