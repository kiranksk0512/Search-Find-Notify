import uuid
from typing import List, Dict, Any
from multidict import MultiDict
from core.fetcher import get_json_resilient
from core.logger import get_company_logger
from core.context import get_company
from core.scrape_types import ScrapeResult
from core.decision import retry_and_decide
from models.microsoftnew_job import MicrosoftNewJob

logger = get_company_logger()

BASE_URL = "https://apply.careers.microsoft.com/api/pcsx/search"

# EXACT profession filters from your cURL
PROFESSIONS = [
    "product management",
    "technology sales",
    "digital sales and solutions",
    "consulting services",
    "design & creative",
    "technical support",
    "analytics",
    "learning",
    "software engineering",
    "data center",
    "research, applied, & data sciences",
]
# Number of jobs per page as per Microsoft’s API
PAGE_SIZE = 10


def _build_params(offset: int) -> MultiDict:
    """
    Build query parameters EXACTLY matching Microsoft’s new API.
    Each filter_profession MUST appear multiple times.
    """
    params = MultiDict()
    params.add("domain", "microsoft.com")
    params.add("query", "")
    params.add("location", "United States")
    params.add("start", str(offset))
    params.add("sort_by", "timestamp")

    for p in PROFESSIONS:
        params.add("filter_profession", p)

    return params


async def _fetch_page(offset: int) -> List[MicrosoftNewJob]:
    """
    Fetch a single page and parse into MicrosoftNewJob objects.
    """

    params = _build_params(offset)

    data = await get_json_resilient(
        BASE_URL,
        params=params,
        headers={
            "accept": "application/json, text/plain, */*",
            "user-agent": "Mozilla/5.0"
        },
        logger=logger
    )

    if not data:
        return []

    # Real API structure: data -> positions
    positions = (
        data.get("data", {}).get("positions")
        if isinstance(data, dict)
        else None
    )

    if not positions:
        return []

    jobs: List[MicrosoftNewJob] = []

    for raw in positions:
        job_id = raw.get("id")
        if not job_id:
            continue

        title = raw.get("name", "Unknown")

        # Construct full URL
        url = "https://apply.careers.microsoft.com" + raw.get("positionUrl", "")

        # Take clean standardized location if available
        locs = raw.get("standardizedLocations", [])
        location = locs[0] if locs else "Unknown"

        jobs.append(
            MicrosoftNewJob(
                job_id=str(job_id),
                title=title,
                url=url,
                location=location,
                department=raw.get("department", "Unknown"),
                display_job_id=raw.get("displayJobId", "Unknown"),
                work_location=raw.get("workLocationOption", "Unknown"),
                posted=raw.get("postedTs", "Unknown"),
                created_date=raw.get("createdTs", "Unknown"),
                isHotJob=raw.get("isHot", 0),
            )
        )

    return jobs


async def _scrape_once(label: str) -> ScrapeResult:
    company = get_company()
    scrape_id = str(uuid.uuid4())[:8]
    logger.info(f"[company={company}] [{scrape_id}] ▶ Starting MicrosoftNew scrape ({label})")

    all_jobs: Dict[str, MicrosoftNewJob] = {}
    offset = 0

    consecutive_empty = 0
    MAX_PAGES = 2000   # deep crawling allowed

    for _ in range(MAX_PAGES):
        jobs = await _fetch_page(offset)

        if not jobs:
            consecutive_empty += 1
            logger.warning(
                f"[{company}] [{scrape_id}] Empty page at offset={offset} "
                f"(consecutive={consecutive_empty})"
            )

            if consecutive_empty >= 3:
                logger.warning(
                    f"[{company}] [{scrape_id}] 🛑 Stopping pagination after "
                    f"{consecutive_empty} empty pages."
                )
                break
        else:
            consecutive_empty = 0
            for j in jobs:
                all_jobs[j.job_id] = j

        offset += PAGE_SIZE

    job_list = list(all_jobs.values())
    anomalous = len(job_list) == 0

    return ScrapeResult(
        jobs=job_list,
        scrape_id=scrape_id,
        anomalous_zero=anomalous,
        stats={"count": len(job_list)},
        meta={"label": label},
    )


def _should_persist(result: ScrapeResult, min_expected_count: int = 30):
    if result is None:
        return False, "no_result"
    if result.anomalous_zero:
        return False, "anomalous_zero"

    count = len(result.jobs or [])
    if count == 0:
        return False, "zero_jobs"
    if count < min_expected_count:
        return False, f"too_few({count}<{min_expected_count})"

    return True, "ok"


async def get_jobs(min_expected_count: int = 50) -> ScrapeResult:
    company = get_company()

    first = await _scrape_once("first-pass")

    decided = await retry_and_decide(
        company=company,
        logger=logger,
        first_result=first,
        retry_fn=lambda: _scrape_once("retry"),
        min_expected_count=min_expected_count,
        should_persist_fn=_should_persist,
    )

    return decided
