from __future__ import annotations

import asyncio
import random
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from core.context import get_company
from core.decision import retry_and_decide
from core.fetcher import get_json
from core.logger import get_company_logger
from core.scrape_types import ScrapeResult
from models.intuit_job import IntuitJob

logger = get_company_logger("intuit")

BASE_URL = "https://jobs.intuit.com/search-jobs/results"
JOB_BASE_URL = "https://jobs.intuit.com"
RECORDS_PER_PAGE = 15
MAX_PAGES = 60

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

ACCEPT_LANGUAGES = [
    "en-GB,en-US;q=0.9,en;q=0.8",
    "en-US,en;q=0.9",
    "en;q=0.9",
]

BASE_PARAMS: Dict[str, str] = {
    "ActiveFacetID": "6252001",
    "RadiusUnitType": "0",
    "RecordsPerPage": str(RECORDS_PER_PAGE),
    "Distance": "50",
    "Keywords": "",
    "Location": "",
    "ShowRadius": "False",
    "IsPagination": "False",
    "CustomFacetName": "",
    "FacetTerm": "",
    "FacetType": "0",
    "SearchResultsModuleName": "Search Results",
    "SearchFiltersModuleName": "Search Filters",
    "SortCriteria": "0",
    "SortDirection": "0",
    "SearchType": "5",
    "PostalCode": "",
    "ResultsType": "0",
    "FacetFilters[0].ID": "6252001",
    "FacetFilters[0].FacetType": "2",
    "FacetFilters[0].Display": "United States",
    "FacetFilters[0].IsApplied": "true",
}


def _build_headers(user_agent: str) -> Dict[str, str]:
    return {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": random.choice(ACCEPT_LANGUAGES),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://jobs.intuit.com/search-jobs",
        "User-Agent": user_agent,
        "X-Requested-With": "XMLHttpRequest",
    }


def _safe_int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_jobs(html: str) -> Tuple[List[IntuitJob], Dict[str, Optional[int]]]:
    soup = BeautifulSoup(html or "", "html.parser")

    section = soup.find("section", id="search-results")
    total_pages = _safe_int(section.get("data-total-pages")) if section else None
    total_results = _safe_int(section.get("data-total-job-results")) if section else None

    jobs: List[IntuitJob] = []
    seen_ids_for_page = set()

    for li in soup.select("ul.search-list > li"):
        anchor = li.find("a", class_="sr-item")
        if not anchor:
            continue

        job_id = anchor.get("data-job-id") or li.get("data-intuit-jobid")
        if not job_id or job_id in seen_ids_for_page:
            continue
        seen_ids_for_page.add(job_id)

        title_el = anchor.find("h2")
        title = title_el.get_text(strip=True) if title_el else "Unknown"

        location_el = anchor.find("span", class_="job-location")
        location = location_el.get_text(strip=True) if location_el else "Unknown"

        href = anchor.get("href", "")
        url = urljoin(JOB_BASE_URL, href)

        category = li.get("data-category", "Unknown")
        remote_raw = (li.get("data-remote") or "").strip()
        job_type = remote_raw if remote_raw and not remote_raw.isdigit() else ""

        requisition_id = ""
        if href:
            parts = [segment for segment in href.split("/") if segment]
            if parts:
                requisition_id = parts[-1]

        jobs.append(
            IntuitJob(
                job_id=job_id,
                title=title,
                url=url,
                location=location,
                category=category or "Unknown",
                job_type=job_type,
                requisition_id=requisition_id,
            )
        )

    return jobs, {"total_pages": total_pages, "total_results": total_results}


def should_persist_jobs(result: ScrapeResult, min_expected_count: int) -> Tuple[bool, str]:
    company = get_company()

    if not result or not result.jobs:
        logger.warning(f"[company={company}] 🧯 zero jobs; skip persist/notify.")
        return False, "zero_jobs"

    count = len(result.jobs)
    if count < min_expected_count:
        logger.warning(f"[company={company}] ⚠️ too few jobs ({count} < {min_expected_count}); skip persist/notify.")
        return False, f"too_few({count}<{min_expected_count})"

    return True, "ok"


async def _scrape_once(label: str, *, min_expected_count: int) -> ScrapeResult:
    company = get_company()
    run_ua = random.choice(USER_AGENTS)
    logger.info(f"[company={company}] [{label}] ▶️ Starting Intuit scrape (ua={run_ua})")

    await asyncio.sleep(random.uniform(0.0, 2.5))

    all_jobs: List[IntuitJob] = []
    seen_ids = set()
    total_pages_hint: Optional[int] = None

    page = 1
    consecutive_empty = 0

    while page <= MAX_PAGES:
        params = BASE_PARAMS.copy()
        params["CurrentPage"] = str(page)
        params["IsPagination"] = "True" if page > 1 else "False"
        params["RecordsPerPage"] = str(RECORDS_PER_PAGE)

        data = await get_json(BASE_URL, headers=_build_headers(run_ua), params=params)
        if not data:
            logger.error(f"[company={company}] [{label}] ❌ Failed to fetch page {page}")
            break

        html = data.get("results", "")
        page_jobs, meta = _parse_jobs(html)
        page_total_pages = meta.get("total_pages")

        if page_total_pages:
            total_pages_hint = page_total_pages

        new_jobs = [job for job in page_jobs if job.job_id not in seen_ids]
        for job in new_jobs:
            seen_ids.add(job.job_id)
        all_jobs.extend(new_jobs)

        logger.info(
            f"[company={company}] [{label}] ✅ Page {page}: fetched {len(page_jobs)} (new {len(new_jobs)})"
        )

        if not page_jobs:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                logger.info(f"[company={company}] [{label}] ⚠️ stopping after {consecutive_empty} empty pages")
                break
        else:
            consecutive_empty = 0

        page += 1
        await asyncio.sleep(random.uniform(0.6, 1.6))

    stats = {
        "count": len(all_jobs),
        "total_pages": total_pages_hint,
        "total_results": len(all_jobs),
        "records_per_page": RECORDS_PER_PAGE,
    }

    anomalous_zero = len(all_jobs) == 0

    return ScrapeResult(
        jobs=all_jobs,
        scrape_id=label,
        anomalous_zero=anomalous_zero,
        stats=stats,
        meta={"user_agent": run_ua},
    )


async def get_jobs(min_expected_count: int = 25) -> ScrapeResult:
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
