# scrapers/apple.py
from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List
from zoneinfo import ZoneInfo

from core.fetcher import post_json
from core.logger import get_company_logger
from core.context import get_company
from core.scrape_types import ScrapeResult
from core.decision import retry_and_decide

from models.apple_job import AppleJob

logger = get_company_logger()
API_URL = "https://jobs.apple.com/api/v1/search"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15"
]

# === Exact filters copied from your DevTools request ===
APPLE_FILTER_LOCATIONS = ["postLocation-USA"]

APPLE_FILTER_TEAMS = [
    {"team": "teamsAndSubTeams-SFTWR", "subTeam": "subTeam-AF"},
    {"team": "teamsAndSubTeams-MLAI", "subTeam": "subTeam-MLI"},
    {"team": "teamsAndSubTeams-MLAI", "subTeam": "subTeam-DLRL"},
    {"team": "teamsAndSubTeams-MLAI", "subTeam": "subTeam-NLP"},
    {"team": "teamsAndSubTeams-MLAI", "subTeam": "subTeam-CV"},
    {"team": "teamsAndSubTeams-MLAI", "subTeam": "subTeam-AR"},
    {"team": "teamsAndSubTeams-HRDWR", "subTeam": "subTeam-SDE"},
    {"team": "teamsAndSubTeams-SFTWR", "subTeam": "subTeam-MCHLN"},
    {"team": "teamsAndSubTeams-SFTWR", "subTeam": "subTeam-COS"},
    {"team": "teamsAndSubTeams-SFTWR", "subTeam": "subTeam-SQAT"},
    {"team": "teamsAndSubTeams-SFTWR", "subTeam": "subTeam-CLD"},
    {"team": "teamsAndSubTeams-SFTWR", "subTeam": "subTeam-ISTECH"},
    {"team": "teamsAndSubTeams-SFTWR", "subTeam": "subTeam-DSR"},
    {"team": "teamsAndSubTeams-SFTWR", "subTeam": "subTeam-WSFT"},
    {"team": "teamsAndSubTeams-STDNT", "subTeam": "subTeam-INTRN"},
    {"team": "teamsAndSubTeams-STDNT", "subTeam": "subTeam-CORP"},
    {"team": "teamsAndSubTeams-STDNT", "subTeam": "subTeam-ASTR"},
    {"team": "teamsAndSubTeams-STDNT", "subTeam": "subTeam-ASLP"},
    {"team": "teamsAndSubTeams-STDNT", "subTeam": "subTeam-ARPS"},
    {"team": "teamsAndSubTeams-STDNT", "subTeam": "subTeam-ACCP"},
    {"team": "teamsAndSubTeams-STDNT", "subTeam": "subTeam-ACR"},
    {"team": "teamsAndSubTeams-HRDWR", "subTeam": "subTeam-MCHLN"},
    {"team": "teamsAndSubTeams-SFTWR", "subTeam": "subTeam-EPM"},
    {"team": "teamsAndSubTeams-SFTWR", "subTeam": "subTeam-SEC"},
]

def _ua() -> str:
    return random.choice(USER_AGENTS)

def build_headers(ua: Optional[str] = None) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Origin": "https://jobs.apple.com",
        "Referer": "https://jobs.apple.com/en-us/search",
        "User-Agent": ua or _ua()
    }

def build_payload(page: int) -> Dict[str, Any]:
    """
    Payload mirrors your DevTools request; page is 1-based.
    """
    return {
        "query": "",
        "filters": {"locations": APPLE_FILTER_LOCATIONS, "teams": APPLE_FILTER_TEAMS},
        "page": page,
        "locale": "en-us",
        "sort": "newest",  # you previously had ""; use "newest" per current UI API
        "format": {"longDate": "MMMM D, YYYY", "mediumDate": "MMM D, YYYY"},
    }

def convert_to_edt(utc_string: str) -> str:
    try:
        # Apple's postDateInGMT looks like "2025-10-25T18:14:36Z"
        dt_utc = datetime.fromisoformat(utc_string.replace("Z", "+00:00"))
        dt_edt = dt_utc.astimezone(ZoneInfo("America/New_York"))
        return dt_edt.strftime("%b %d, %Y %I:%M %p %Z")
    except Exception:
        return "Unknown"

def apple_job_url(job_id: str) -> str:
    # PIPE-* postings use only the numeric part
    if job_id and job_id.startswith("PIPE-"):
        return f"https://jobs.apple.com/en-us/details/{job_id.split('-', 1)[1]}"
    # all other IDs should use the full ID, including the dash
    return f"https://jobs.apple.com/en-us/details/{job_id}"

async def _scrape_once(label: str) -> ScrapeResult:
    """
    One full Apple scrape across paginated search.
    Returns a ScrapeResult (object mode).
    """
    company = get_company()
    run_ua = _ua()
    logger.info(f"[company={company}] 🚀 Apple scrape ({label}) starting (ua={run_ua})…")

    # Small jitter to de-sync with other scrapers
    await asyncio.sleep(random.uniform(0.0, 2.0))

    job_list: List[AppleJob] = []
    per_page_counts: Dict[int, int] = {}
    page = 1
    total_pages = 0

    while True:
        payload = build_payload(page)
        headers = build_headers(run_ua)

        data = await post_json(API_URL, payload, headers)
        total_pages += 1

        if not data:
            logger.warning(f"[company={company}] ⚠️ Empty/failed response at page={page}")
            break

        results = (data.get("res") or {}).get("searchResults") or []
        if not results:
            break

        page_count = 0
        for job in results:
            job_id = job.get("id") or "Unknown"
            title = job.get("postingTitle", "Unknown")
            team = (job.get("team") or {}).get("teamName", "N/A")
            # Apple's response can contain multiple locations – keep country name for now
            location = (job.get("locations") or [{}])[0].get("countryName", "Unknown")
            post_gmt = job.get("postDateInGMT", "Unknown")
            date_posted = convert_to_edt(post_gmt)
            url = apple_job_url(job_id)

            job_list.append(
                AppleJob(
                    job_id=job_id,
                    title=title,
                    url=url,
                    date_posted=date_posted,
                    team=team,
                    location=location,
                )
            )
            page_count += 1

        per_page_counts[page] = page_count
        logger.info(f"[company={company}] 📄 Page {page}: {page_count} jobs")
        page += 1

        # Polite pacing
        await asyncio.sleep(random.uniform(0.8, 2.2))

    total_jobs = len(job_list)
    logger.info(f"[company={company}] 🎉 Apple union: {total_jobs} jobs across {total_pages} pages")

    anomalous_zero = (total_jobs == 0)
    return ScrapeResult(
        jobs=job_list,
        scrape_id=str(random.getrandbits(32))[:8],
        anomalous_zero=anomalous_zero,
        stats={
            "total_jobs": total_jobs,
            "total_pages": total_pages,
            "per_page_counts": per_page_counts,
            "user_agent": run_ua,
        },
        meta={"mode": "paged"},
    )

def should_persist_jobs(result: ScrapeResult, min_expected_count: int = 50) -> Tuple[bool, str]:
    """
    Apple policy (object mode). Returns (should_persist, decision_reason).
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
        # Small jitter to avoid synchronized bursts
        await asyncio.sleep(random.uniform(0.0, 2.0))
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
