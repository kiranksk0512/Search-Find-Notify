from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo

from core.context import get_company
from core.fetcher import get_json_resilient
from core.logger import get_company_logger
from core.scrape_types import ScrapeResult
from core.decision import retry_and_decide
from models.databricks_job import DatabricksJob

logger = get_company_logger()

BASE_URL = "https://www.databricks.com"
PAGE_DATA_URL = f"{BASE_URL}/careers-assets/page-data/company/careers/open-positions/page-data.json"
GH_URL = "https://boards-api.greenhouse.io/v1/boards/databricks/jobs?content=true"

# Static header parts; dynamic UA/lang added per-run
HEADERS_BASE: Dict[str, str] = {
    "accept": "*/*",
    "referer": f"{BASE_URL}/company/careers/open-positions",
    "cache-control": "no-cache",
}

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
]

ACCEPT_LANGUAGES = [
    "en-GB,en-US;q=0.9,en;q=0.8",
    "en-US,en;q=0.9",
    "en;q=0.9",
]

# Department allowlist (case-insensitive match). Only jobs matching one of these
# department labels (from pageContext.metadata[].filterDept or job fields) are kept.
ALLOWED_DEPARTMENTS = {
    d.lower(): d for d in [
        "Engineering",
        "Field Engineering",
        "IT",
        "Mosaic AI",
        "Product",
        "Professional Services",
        "Security",
        "See More Jobs",
        "University Recruiting",
    ]
}

ALLOWED_LOCATIONS = {
     d.lower(): d for d in [
        "United States Of America",
        "United States",
        "America"
        "USA",
     ]
}

def _filter_greenhouse_jobs(gh_jobs: List[DatabricksJob]) -> List[DatabricksJob]:
    filtered: List[DatabricksJob] = []
    for j in gh_jobs:
        metadata = j.get("metadata") or []
        departments = j.get("departments") or []

        # NEW: If metadata missing, treat as null → fallback should be allowed
        is_any_filter_dept_null = True if not metadata else False

        is_job_added = False

        # 1. Primary: use metadata.filterDept
        for meta in metadata:
            filter_dept = meta.get("filterDept") or meta.get("FilterDept") or ""
            filter_dept_lower = filter_dept.lower()

            if not filter_dept_lower:
                is_any_filter_dept_null = True  # ANY null → fallback allowed

            for allowed_lower in ALLOWED_DEPARTMENTS.keys():
                if allowed_lower in filter_dept_lower or filter_dept_lower == allowed_lower:
                    filtered.append(j)
                    is_job_added = True
                    break
            if is_job_added:
                break

        if is_job_added:
            continue

        # 2. Fallback if ANY null filter or metadata missing
        if is_any_filter_dept_null and not is_job_added:
            for dept in departments:
                dept_name = dept.get("name") or ""
                dept_name_lower = dept_name.lower()
                for allowed_lower in ALLOWED_DEPARTMENTS.keys():
                    if allowed_lower in dept_name_lower or dept_name_lower == allowed_lower:
                        filtered.append(j)
                        is_job_added = True
                        break
                if is_job_added:
                    break

    return filtered


def _find_job_list(obj: Any) -> List[Dict[str, Any]]:
    # Try common Gatsby/GraphQL shapes first
    if isinstance(obj, dict):
        # result.data.*
        res = obj.get("result") or {}
        
        # result.pageContext.* (and lenient casing/keys for Databricks)
        page_ctx = res.get("pageContext") or res.get("pagecontext") or {}

        data = page_ctx.get("data") or page_ctx.get("Data") or {}

        allGreenhouseJobs = data.get("allGreenhouseJob") or {}
        gh_items = allGreenhouseJobs.get("nodes") or allGreenhouseJobs.get("Nodes")
        if isinstance(gh_items, list) and gh_items and isinstance(gh_items[0], dict) :
            return gh_items  # type: ignore
    return []


def _as_text(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    try:
        return ", ".join(v) if isinstance(v, (list, tuple)) else str(v)
    except Exception:
        return None


def _build_url(item: Dict[str, Any]) -> str:
    url = item.get("url") or item.get("applyUrl") or item.get("applyURL")
    if isinstance(url, str) and url:
        return url
    path = item.get("path") or item.get("permalink") or item.get("slug")
    if isinstance(path, str) and path:
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return BASE_URL + path
    return BASE_URL + "/company/careers/open-positions"


def _parse_greenhouse(data: Dict[str, Any]) -> List[DatabricksJob]:
    jobs: List[DatabricksJob] = []
    items = (data or {}).get("jobs") or []
    for it in items:
        try:
            jid = it.get("gh_Id") or it.get("id") or it.get("job_id") or it.get("internal_job_id")
            title = it.get("title") or "Unknown"
            url = it.get("absolute_url") or _build_url(it)
            # Greenhouse uses location: { name: "City, Country" }
            loc = (it.get("location") or {}).get("name")
            # Departments/offices are lists of dicts with name
            dept_names = [d.get("name") for d in (it.get("departments") or []) if isinstance(d, dict)]
            offc_names = [o.get("name") for o in (it.get("offices") or []) if isinstance(o, dict)]
            internal_job_id = it.get("internal_job_id")
            updated_at = it.get("updated_at") or it.get("created_at")

            # Per request: date_posted = current time in New York
            try:
                date_posted = datetime.now(ZoneInfo("America/New_York")).isoformat()
            except Exception:
                date_posted = updated_at or "Unknown"

            jobs.append(
                DatabricksJob(
                    job_id=str(jid),
                    title=str(title),
                    url=str(url),
                    location=_as_text(loc) or "Unknown",
                    team=_as_text(dept_names),
                    sub_teams=_as_text(offc_names),
                    date_posted=_as_text(date_posted),
                    internal_job_id=_as_text(internal_job_id),
                    updated_date=_as_text(updated_at),
                )
            )
        except Exception:
            continue
    return jobs

def should_persist_jobs(result: ScrapeResult, min_expected_count: int = 5) -> Tuple[bool, str]:
    company_local = get_company()
    if result is None:
        return False, "no_result"
    if result.anomalous_zero:
        logger.warning(f"[company={company_local}] [{result.scrape_id}] 🧯 anomalous_zero=True; skip persist/notify.")
        return False, "anomalous_zero"
    jobs_count = len(result.jobs or [])
    if jobs_count == 0:
        logger.warning(f"[company={company_local}] [{result.scrape_id}] 🧯 zero jobs; skip persist/notify.")
        return False, "zero_jobs"
    if jobs_count < min_expected_count:
        logger.warning(
            f"[company={company_local}] [{result.scrape_id}] 🧯 Too few jobs ({jobs_count}<{min_expected_count}); treating as partial outage; skip persist/notify."
        )
        return False, f"too_few({jobs_count}<{min_expected_count})"
    return True, "ok"

def collect_us_locations(node, target_id="United States"):
    """
    Recursively traverse allGreenhouseOffice tree and collect all location names under 'United States'
    """
    results = []

    def dfs(n, inside_us):
        # When this node is 'United States', start collecting its branches
        if n.get("name") == target_id:
            inside_us = True

        if inside_us:
            results.append(n["name"])

        for child in n.get("children", []):
            dfs(child, inside_us)

    dfs(node, False)
    return results


def find_us_locations(obj):
    """
    all_offices = response.result.pageContext.allGreenhouseOffice.nodes
    """

    if isinstance(obj, dict):
        # result.data.*
        res = obj.get("result") or {}
        
        # result.pageContext.* (and lenient casing/keys for Databricks)
        page_ctx = res.get("pageContext") or res.get("pagecontext") or {}

        data = page_ctx.get("data") or page_ctx.get("Data") or {}

        allGreenhouseOffice = data.get("allGreenhouseOffice") or {}
        all_offices = allGreenhouseOffice.get("nodes") or []
        for root in all_offices:
            if root["name"] == "USCA":
                # the United States node is inside USCA -> children
                for child in root["children"]:
                    if child["name"] == "United States":
                        return collect_us_locations(child)

    return []


def filter_us_jobs(all_jobs, us_locations):
    """
    all_jobs = your final jobs list (after API fetch)
    us_locations = list of all U.S. location names
    """
    us_jobs = []
    for job in all_jobs:
        offices = job.get("offices", [])
        for office in offices:
            if office["name"] in us_locations:
                us_jobs.append(job)
                break
    return us_jobs

async def _scrape_once(label: str) -> ScrapeResult:
    company = get_company()
    await asyncio.sleep(random.uniform(0.0, 2.0)) # Small jitter to avoid synchronized bursts
    scrape_id = f"{company}-{int(time.time())}-{random.randint(1000,9999)}"

    headers = {
        **HEADERS_BASE,
        "user-agent": random.choice(USER_AGENTS),
        "accept-language": random.choice(ACCEPT_LANGUAGES),
    }

    # The page-data endpoint generally returns the full dataset; query params
    # are used client-side to filter. We'll request without filters.
    data = await get_json_resilient(
        PAGE_DATA_URL,
        headers=headers,
        params=None,
        logger=logger,
    )

    jobs: List[DatabricksJob] = []
    raw_list: List[Dict[str, Any]] = []
    if data:
        us_locations = find_us_locations(data)
        raw_list = _find_job_list(data)
        if raw_list:
            logger.info(f"[company={company}] Found {len(raw_list)}  jobs before filtering i.e., in total.")
            dept_filtered_jobs = _filter_greenhouse_jobs(raw_list)
            logger.info(f"[company={company}] Found {len(dept_filtered_jobs)} jobs after filtering by department.")

            
            us_jobs = filter_us_jobs(dept_filtered_jobs, us_locations)
            logger.info(f"[company={company}] Found {len(us_jobs)} jobs after filtering by US locations.")

            if us_jobs:
                try:
                    jobs = _parse_greenhouse({"jobs": us_jobs})
                except Exception as e:
                    logger.exception(f"[company={company}] Exception while parsing inlined Greenhouse list: {e}")
                    jobs = []

    mode = "page-data"

    count = len(jobs)
    anomalous_zero = count == 0
    return ScrapeResult(
        jobs=jobs,
        scrape_id=scrape_id,
        anomalous_zero=anomalous_zero,
        stats={"count": count},
        meta={"source": mode, "label": label},
    )

async def get_jobs(min_expected_count: int = 5) -> ScrapeResult:

    company = get_company()

    first = await _scrape_once("first-pass")
    decided = await retry_and_decide(
        company=company,
        logger=logger,
        first_result=first,
        retry_fn=lambda: _scrape_once("retry-after-anomaly"),
        min_expected_count=min_expected_count,
        should_persist_fn=should_persist_jobs,
    )

    return decided
