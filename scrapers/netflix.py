import asyncio
import html
import os
import random
from datetime import datetime
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo
from core.logger import get_company_logger
from core.fetcher import get_json
from core.context import get_company
from core.scrape_types import ScrapeResult
from core.decision import retry_and_decide
from models.netflix_job import NetflixJob

logger = get_company_logger("netflix")

BASE_URL = "https://explore.jobs.netflix.net/api/apply/v2/jobs"

# Query-search pid seen on Netflix search UI (differs from team browse pid)
SEARCH_PID = "790312512674"

# Include a few variants so we don't miss early-career roles.
EARLY_CAREER_QUERIES = [
    "new grad",
    "new grads",
    "new graduate",
    "early career",
    "early careers",
    "early grad",
    "early graduate",
]


def _parse_netflix_query_terms(env_value: str) -> List[str]:
    terms = []
    seen = set()
    for raw in (env_value or "").split(","):
        t = raw.strip()
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(t)
    return terms


# Optional override (comma-separated): NETFLIX_QUERY_TERMS="new grad, early career, intern"
_ENV_TERMS = _parse_netflix_query_terms(os.getenv("NETFLIX_QUERY_TERMS", ""))
if _ENV_TERMS:
    EARLY_CAREER_QUERIES = _ENV_TERMS

BASE_HEADERS = {
    "Accept": "*/*",
    # Avoid advertising zstd; some environments can't decode it reliably.
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Content-Type": "application/json",
    "Pragma": "no-cache",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
}

BROWSE_HEADERS = {
    **BASE_HEADERS,
    "Referer": (
        "https://explore.jobs.netflix.net/careers?"
        "location=United%20States&pid=790304512952&"
        "Teams=Data%20%26%20Insights&Teams=Engineering%20Operations&"
        "Teams=Product%20Design&Teams=Engineering&"
        "domain=netflix.com&sort_by=new"
    ),
}

SEARCH_HEADERS = {
    **BASE_HEADERS,
    "Referer": (
        "https://explore.jobs.netflix.net/careers/search?"
        "pid=790312512674&domain=netflix.com&sort_by=relevance"
    ),
}


def _normalize_unix_ts(ts: Any) -> int:
    """Netflix timestamps can vary; normalize seconds vs milliseconds."""
    try:
        v = int(ts)
    except Exception:
        return 0
    # Heuristic: > 1e12 is almost certainly ms
    if v > 1_000_000_000_000:
        v = int(v / 1000)
    return v


def _job_from_payload(job: Dict[str, Any]) -> Optional[NetflixJob]:
    job_id_raw = job.get("id")
    if job_id_raw is None or job_id_raw == "":
        return None
    job_id = str(job_id_raw)

    job_title = html.unescape(job.get("name") or "")
    if not job_title:
        job_title = "Unknown"

    url = job.get("canonicalPositionUrl") or f"https://explore.jobs.netflix.net/careers/job/{job_id}"
    location = job.get("location") or "United States"

    raw_t_create = _normalize_unix_ts(job.get("t_create", 0))
    raw_t_update = _normalize_unix_ts(job.get("t_update", 0))
    t_create_dt = (
        datetime.fromtimestamp(raw_t_create, tz=ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")
        if raw_t_create
        else ""
    )
    t_update_dt = (
        datetime.fromtimestamp(raw_t_update, tz=ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")
        if raw_t_update
        else ""
    )

    return NetflixJob(
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
    )


def should_persist_jobs(result: ScrapeResult, min_expected_count: int):
    company = get_company()

    if not result or not result.jobs:
        return False, "zero_jobs"

    cnt = len(result.jobs)
    if cnt < min_expected_count:
        return False, f"too_few({cnt}<{min_expected_count})"

    return True, "ok"


async def _scrape_once(label: str, min_expected_count: int = 20) -> ScrapeResult:
    company = get_company()
    scrape_id = label

    await asyncio.sleep(random.uniform(0, 2.0))

    all_jobs: List[NetflixJob] = []
    seen_ids = set()

    async def _page_through(*, params_builder, headers, phase: str):
        page = 0
        consecutive_empty_pages = 0

        while True:
            params = params_builder(page)
            logger.info(f"[company={company}] [{scrape_id}] ▶️  {phase} page={page}")

            data = await get_json(BASE_URL, headers=headers, params=params)
            if not data:
                logger.error(f"[company={company}] [{scrape_id}] ❌ {phase} failed to fetch/parse page={page}")
                break

            job_list = data.get("positions", []) or []
            logger.info(f"[company={company}] [{scrape_id}] ✅ {phase} page={page}: {len(job_list)} jobs")

            if not job_list:
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= 3:
                    logger.warning(
                        f"[company={company}] [{scrape_id}] ⚠️ {phase} stopping after {consecutive_empty_pages} empty pages"
                    )
                    break
                page += 1
                continue

            consecutive_empty_pages = 0
            for payload in job_list:
                j = _job_from_payload(payload)
                if not j:
                    continue
                if j.job_id in seen_ids:
                    continue
                seen_ids.add(j.job_id)
                all_jobs.append(j)

            page += 1
            await asyncio.sleep(random.uniform(0.7, 2.0))

    # 1) Existing team-based browsing (what you already had)
    def _browse_params(page: int):
        # list-of-tuples keeps multiple 'Teams' keys
        return [
            ("domain", "netflix.com"),
            ("location", "United States"),
            ("sort_by", "new"),
            ("Teams", "Data & Insights"),
            ("Teams", "Engineering Operations"),
            ("Teams", "Product Design"),
            ("Teams", "Engineering"),
            ("num", 10),
            ("pid", "790304512952"),
            ("exclude_pid", "790304512952"),
            ("start", page * 10),
        ]

    await _page_through(params_builder=_browse_params, headers=BROWSE_HEADERS, phase="browse")

    # 2) Query-based search (captures early-career/new-grad roles that don't match Teams filters)
    for q in EARLY_CAREER_QUERIES:
        await asyncio.sleep(random.uniform(0.2, 0.6))

        def _search_params(page: int, query: str = q):
            return [
                ("domain", "netflix.com"),
                ("profile", ""),
                ("query", query),
                ("pid", SEARCH_PID),
                ("sort_by", "relevance"),
                ("num", 10),
                ("start", page * 10),
            ]

        await _page_through(params_builder=_search_params, headers=SEARCH_HEADERS, phase=f"search(q={q})")

    logger.info(f"[company={company}] [{scrape_id}] ✅ Found total: {len(all_jobs)} jobs")

    return ScrapeResult(
        jobs=all_jobs,
        scrape_id=scrape_id,
        anomalous_zero=False,
        stats={"count": len(all_jobs)},
        meta={"label": label}
    )


async def get_jobs(min_expected_count: int = 2) -> ScrapeResult:
    company = get_company()

    first = await _scrape_once("first-pass", min_expected_count=min_expected_count)

    decided = await retry_and_decide(
        company=company,
        logger=logger,
        first_result=first,
        retry_fn=lambda: _scrape_once("retry", min_expected_count=min_expected_count),
        min_expected_count=min_expected_count,
        should_persist_fn=should_persist_jobs,
    )

    return decided
