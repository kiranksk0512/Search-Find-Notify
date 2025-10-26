from __future__ import annotations

import asyncio
import html
import json
import random
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List
from zoneinfo import ZoneInfo

from core.logger import get_company_logger
from core.context import get_company
from core.fetcher import post_form
from core.scrape_types import ScrapeResult
from core.decision import retry_and_decide
from core.google_utils import extract_google_tokens_and_cookies
from models.google_job import GoogleJob

logger = get_company_logger()

GOOGLE_URL = "https://www.google.com/about/careers/applications/_/HiringCportalFrontendUi/data/batchexecute"
SOURCE_PATH = "/about/careers/applications/jobs/results/"

# SEARCH_TITLES = ["Software Engineer", "ai-spotlight"]
SEARCH_TITLES = ["ai-spotlight"]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)... Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)... Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64)... Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3)... Version/16.4 Safari/605.1.15"
]

ACCEPT_LANGUAGES = [
    "en-GB,en-US;q=0.9,en;q=0.8",
    "en-US,en;q=0.9",
    "en;q=0.9"
]


def _now_edt_str() -> str:
    return datetime.now(ZoneInfo("America/New_York")).strftime("%b %d, %Y %I:%M %p %Z")


def _headers(ua: Optional[str] = None) -> Dict[str, str]:
    return {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": random.choice(ACCEPT_LANGUAGES),
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
        "origin": "https://www.google.com",
        "pragma": "no-cache",
        "referer": "https://www.google.com/about/careers/applications/jobs/results/",
        "user-agent": ua or random.choice(USER_AGENTS),
    }


def _build_form_payload(page: int, rpcid: str, query_term: str) -> Dict[str, Any]:
    # First page sometimes needs a special device hint; we keep it minimal
    device_value = [1] if page == 1 else None

    job_query = [[f"\"{query_term}\"", None, None, device_value, "en", None, [["United States"]], page]]

    f_req = [[[rpcid, json.dumps(job_query), None, "3"]]]
    return {"f.req": json.dumps(f_req)}


def _build_url(rpcids: str, f_sid: str, bl: str) -> str:
    params = {
        "rpcids": rpcids,
        "source-path": SOURCE_PATH,
        "f.sid": f_sid,
        "bl": bl,
        "hl": "en",
        "soc-app": "1",
        "soc-platform": "1",
        "soc-device": "1",
        "rt": "c",
    }
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GOOGLE_URL}?{q}"


def _parse_batchexecute_for_jobs(response_text: str) -> List[list]:
    """
    Extract the job array payload embedded in batchExecute ('wrb.fr', 'r06xKb').
    Returns the list of job rows (each is a list).
    """
    cleaned = (response_text or "").lstrip(")]}'\n")
    for line in cleaned.splitlines():
        try:
            parsed = json.loads(line)
            for entry in parsed:
                if isinstance(entry, list) and len(entry) >= 3 and entry[0] == "wrb.fr" and entry[1] == "r06xKb":
                    job_string = entry[2]
                    arr = json.loads(job_string)
                    # Shape observed: [ [ [jobId, title, ...], ... ] , ...]
                    return arr[0] if isinstance(arr, list) and arr else []
        except Exception:
            continue
    return []


async def _scrape_once(label: str) -> ScrapeResult:
    """
    One full Google scrape across SEARCH_TITLES.
    Returns a ScrapeResult (object mode).
    """
    company = get_company()
    run_ua = random.choice(USER_AGENTS)
    logger.info(f"[company={company}] 🚀 Google scrape ({label}) starting (ua={run_ua})…")

    # Jitter to avoid synchronized bursts across scrapers
    await asyncio.sleep(random.uniform(0.0, 2.5))

    # Get dynamic tokens/cookies per run
    tokens = await extract_google_tokens_and_cookies()
    rpcids = tokens.get("rpcids")
    f_sid = tokens.get("f.sid")
    bl = tokens.get("bl")
    cookies_dict = tokens.get("cookies") or {}

    if not (rpcids and f_sid and bl):
        logger.error(f"[company={company}] ❌ Missing required Google tokens (rpcids/f.sid/bl).")
        # Return empty with anomalous_zero to trigger retry_and_decide path
        return ScrapeResult(
            jobs=[],
            scrape_id=str(random.getrandbits(32))[:8],
            anomalous_zero=True,
            stats={"reason": "missing_tokens"},
            meta={"stage": "preflight"},
        )

    raw_cookie_header = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
    url = _build_url(rpcids, f_sid, bl)

    all_jobs: List[GoogleJob] = []
    per_query_counts: Dict[str, int] = {}
    per_query_pages: Dict[str, int] = {}
    empty_page_stops: Dict[str, int] = {}

    for query in SEARCH_TITLES:
        logger.info(f"[company={company}] 🔍 Google query: {query}")
        page = 1
        consecutive_empty_pages = 0
        page_count_for_query = 0
        added_for_query = 0

        while True:
            headers = _headers(run_ua)
            payload = _build_form_payload(page, rpcids, query)

            response_text = await post_form(
                url=url,
                payload=payload,
                headers=headers,
                parse_json=False,
                cookies=raw_cookie_header,
            )
            page_count_for_query += 1

            if response_text is None:
                logger.error(f"[company={company}] ❌ No response for '{query}' page {page}")
                break

            try:
                job_entries = _parse_batchexecute_for_jobs(response_text)
            except Exception as e:
                logger.exception(f"[company={company}] ❌ Parse error for '{query}' page {page}: {e}")
                break

            if not job_entries:
                consecutive_empty_pages += 1
                logger.warning(f"[company={company}] ⚠️ Empty job page for '{query}' page {page} (streak={consecutive_empty_pages})")
                if consecutive_empty_pages >= 3:
                    empty_page_stops[query] = consecutive_empty_pages
                    logger.warning(f"[company={company}] ⛔ Stopping '{query}' after 3 empty pages.")
                    break
                page += 1
                await asyncio.sleep(random.uniform(0.8, 2.2))
                continue

            consecutive_empty_pages = 0

            for row in job_entries:
                try:
                    job_id = row[0]
                    job_title = html.unescape(row[1])
                    job_url = f"https://www.google.com/about/careers/applications/jobs/results/{job_id}"
                    # No posted timestamp in payload—use current EDT
                    date_posted = _now_edt_str()

                    all_jobs.append(
                        GoogleJob(
                            job_id=job_id,
                            title=job_title,
                            url=job_url,
                            date_posted=date_posted,
                        )
                    )
                    added_for_query += 1
                except Exception:
                    continue

            logger.info(f"[company={company}] ✅ '{query}' page {page}: +{len(job_entries)} jobs (cumulative {added_for_query})")
            page += 1
            await asyncio.sleep(random.uniform(0.8, 2.2))

        per_query_counts[query] = added_for_query
        per_query_pages[query] = page_count_for_query

    total_jobs = len(all_jobs)
    logger.info(f"[company={company}] 🎉 Google union: {total_jobs} jobs across {len(SEARCH_TITLES)} queries")

    anomalous_zero = (total_jobs == 0)

    return ScrapeResult(
        jobs=all_jobs,
        scrape_id=str(random.getrandbits(32))[:8],
        anomalous_zero=anomalous_zero,
        stats={
            "total_jobs": total_jobs,
            "per_query_counts": per_query_counts,
            "per_query_pages": per_query_pages,
            "empty_page_stops": empty_page_stops,
            "user_agent": run_ua,
        },
        meta={"mode": "batchExecute"},
    )


def should_persist_jobs(result: ScrapeResult, min_expected_count: int = 25) -> Tuple[bool, str]:
    """
    Google policy (object mode). Returns (should_persist, decision_reason).
    Threshold a bit lower than Meta because queries are targeted.
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


async def get_jobs(min_expected_count: int = 25) -> ScrapeResult:
    """
    Public entry: returns a ScrapeResult (object mode).
    """
    company = get_company()

    async def _run_once(label: str) -> ScrapeResult:
        # modest jitter to avoid synchronized bursts
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
