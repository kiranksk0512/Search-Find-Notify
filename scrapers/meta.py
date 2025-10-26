from __future__ import annotations

import json
import time
import random
import asyncio
import urllib.parse
import uuid
import hashlib
import traceback
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from zoneinfo import ZoneInfo

from core.fetcher import post_form
from core.logger import get_company_logger
from core.meta_utils import extract_meta_tokens
from models.meta_job import MetaJob
from core.context import get_company

# Centralized result container + decision helper
from core.scrape_types import ScrapeResult
from core.decision import retry_and_decide

logger = get_company_logger()

GRAPHQL_URL = "https://www.metacareers.com/graphql"
DOC_ID = "29615178951461218"
FRIENDLY_NAME = "CareersJobSearchResultsDataQuery"

COOKIES = {
    'datr': 'BNaDaLVxvClP3ifeL2rvnxJH',
    'wd': '514x832'
}

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

# ----------------- small helpers -----------------

def _hash_short(s: str) -> str:
    try:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:10]
    except Exception:
        return "na"
    
def _mask(v, keep: int = 4) -> str:
    if v is None:
        return "null"
    s = str(v)
    return f"{s[:keep]}…{len(s)}"


def convert_to_edt(utc_timestamp: Optional[str]) -> str:
    try:
        if not utc_timestamp:
            return "Unknown"
        dt_utc = datetime.fromisoformat(utc_timestamp.replace("Z", "+00:00"))
        dt_edt = dt_utc.astimezone(ZoneInfo("America/New_York"))
        return dt_edt.strftime("%b %d, %Y %I:%M %p %Z")
    except Exception:
        return "Unknown"

# ----------------- payload & parsing -----------------


def get_payload(tokens: Dict[str, Any], *, sort_by_new: bool = False, after_cursor: Optional[str] = None, req_id: str = "1"):
    variables = {
        "search_input": {
            "q": None,
            "divisions": [],
            "offices": [],
            "roles": [],
            "leadership_levels": [],
            "saved_jobs": [],
            "saved_searches": [],
            "sub_teams": [],
            "teams": [],
            "is_leadership": False,
            "is_remote_only": False,
            "sort_by_new": bool(sort_by_new),
            "results_per_page": None
        }
    }
    if after_cursor:
        variables["search_input"]["after_cursor"] = after_cursor

    payload_dict = {
        'av': '0',
        '__user': '0',
        '__a': '1',
        '__req': req_id,
        '__hs': tokens.get("__hs", ""),
        'dpr': '2',
        '__ccg': 'EXCELLENT',
        '__rev': tokens.get("__rev", ""),
        '__hsi': tokens.get("__hsi", ""),
        '__dyn': '7xeUmwkHg7ebwKBAg5S1Dxu13wqovzEdEc8uxa1twYwJw5ux60Vo1upE4W0OE3nwaq1xwEw7Bx61vw4iwBgao1O82Iwb66oG0OU5a1qw8W1uwa-0raazoiwfe0Lo6-1FwcO0JE24wio1587u1rxC1RwkE',
        'lsd': tokens.get("lsd", ""),
        'jazoest': tokens.get("jazoest", ""),
        '__spin_r': tokens.get("__spin_r", ""),
        '__spin_b': tokens.get("__spin_b", ""),
        '__spin_t': str(int(time.time())),
        '__jssesw': '1',
        'fb_api_caller_class': 'RelayModern',
        'fb_api_req_friendly_name': FRIENDLY_NAME,
        'doc_id': DOC_ID,
        'variables': json.dumps(variables),
        'server_timestamps': 'true',
    }

    return urllib.parse.urlencode(payload_dict), variables


def parse_jobs(data: Dict[str, Any], *, scrape_id: str, mode: bool, page: int):
    company = get_company()
    if not isinstance(data, dict):
        logger.error(
            f"[company={company}] [{scrape_id}] ❌ Non-dict JSON on parse (mode={mode} page={page}) type={type(data)}"
        )
        return []

    errors = data.get("errors")
    if errors:
        logger.warning(f"[company={company}] [{scrape_id}] ⚠️ GraphQL errors present (mode={mode} page={page}): {errors}")

    root = data.get("data", {})
    node = root.get("job_search_with_featured_jobs", {})
    all_jobs = node.get("all_jobs", [])
    if not isinstance(all_jobs, list):
        logger.warning(
            f"[company={company}] [{scrape_id}] ⚠️ Unexpected all_jobs type: {type(all_jobs)} (mode={mode} page={page})"
        )
        all_jobs = []

    jobs = []
    for job in all_jobs:
        job_id = job.get("id")
        title = job.get("title", "Unknown")
        url = f"https://www.metacareers.com/jobs/{job_id}" if job_id else "Unknown"
        location = ", ".join(job.get("locations", [])) if "locations" in job else "Unknown"
        sub_teams = ", ".join(job.get("sub_teams", [])) if "sub_teams" in job else "Unknown"
        teams = ", ".join(job.get("teams", [])) if "teams" in job else "Unknown"
        posted = convert_to_edt(job.get("listed_on", ""))

        if not job_id:
            logger.debug(
                f"[company={company}] [{scrape_id}] ℹ️ Skipping job without id (mode={mode} page={page}) raw={job}"
            )
            continue

        jobs.append(MetaJob(
                job_id=job_id,
                title=title,
                url=url,
                location=location,
                team=teams,
                sub_teams=sub_teams,
                date_posted=posted,
            )
        )

    logger.info(f"[company={company}] [{scrape_id}] 🧩 Parsed jobs: {len(jobs)} (mode={mode} page={page})")
    return jobs

# ----------------- network page fetch -----------------


async def _fetch_page(
    tokens: Dict[str, Any],
    *,
    sort_by_new: bool,
    after_cursor: Optional[str],
    req_id: str,
    scrape_id: str,
    page: int,
    attempt: int,
    ua: str,
):
    company = get_company()
    HEADERS = {
        'accept': '*/*',
        'accept-language': random.choice(ACCEPT_LANGUAGES),
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://www.metacareers.com',
        'pragma': 'no-cache',
        'referer': 'https://www.metacareers.com/jobs',
        'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': ua,   # <-- use run-scoped UA,
        'x-asbd-id': '359341',
        'x-fb-friendly-name': FRIENDLY_NAME,
        'x-fb-lsd': tokens.get("lsd", ""),
    }

    payload, variables = get_payload(tokens, sort_by_new=sort_by_new, after_cursor=after_cursor, req_id=req_id)

    cursor_dbg = variables["search_input"].get("after_cursor")
    cursor_hash = _hash_short(cursor_dbg) if cursor_dbg else "none"

    t0 = time.time()
    try:
        json_data = await post_form(GRAPHQL_URL, payload, HEADERS)
        dt = (time.time() - t0) * 1000
        body_len = len(json.dumps(json_data)) if isinstance(json_data, dict) else 0

        logger.info(
            f"[company={company}] [{scrape_id}] ⬇️ Page fetch OK "
            f"(mode={sort_by_new} page={page} attempt={attempt} req_id={req_id} cursor={cursor_hash} "
            f"ms={dt:.0f} size={body_len})"
        )

        return json_data, HEADERS
    except Exception as e:
        dt = (time.time() - t0) * 1000
        logger.error(
            f"[company={company}] [{scrape_id}] ❌ Page fetch EXCEPTION "
            f"(mode={sort_by_new} page={page} attempt={attempt} req_id={req_id} cursor={cursor_hash} ms={dt:.0f}): {e}\n{traceback.format_exc()}"
        )
        return None, HEADERS


async def fetch_all_pages_for_mode(tokens: Dict[str, Any], *, sort_by_new: bool, scrape_id: str, ua: str):
    company = get_company()
    logger.info(f"[company={company}] [{scrape_id}] ▶️ Meta scrape mode sort_by_new={sort_by_new}")
    collected = []
    seen_ids = set()
    after_cursor = None
    page = 1
    max_retries = 1

    while True:
        req_id = str(page)

        # retry loop
        json_data = None
        headers_used = None
        for attempt in range(1, max_retries + 1):
            json_data, headers_used = await _fetch_page(
                tokens,
                sort_by_new=sort_by_new,
                after_cursor=after_cursor,
                req_id=req_id,
                scrape_id=scrape_id,
                page=page,
                attempt=attempt,
                ua=ua,
            )
            if json_data:
                break
            if attempt < max_retries:
                sleep_s = random.uniform(1.0, 2.0) * attempt
                logger.warning(
                    f"[company={company}] [{scrape_id}] 🔁 Retry (mode={sort_by_new} page={page}) in {sleep_s:.1f}s…"
                )
                await asyncio.sleep(sleep_s)

        if not json_data:
            logger.error(
                f"[company={company}] [{scrape_id}] ❌ Empty/failed GraphQL response after retries (mode={sort_by_new} page={page})."
            )
            break

        # sanity check for GraphQL shape
        if "data" not in json_data and "errors" not in json_data:
            logger.warning(
                f"[company={company}] [{scrape_id}] ⚠️ Unexpected JSON shape (no data/errors). Will stop paging. (mode={sort_by_new} page={page})"
            )
            break

        jobs = parse_jobs(json_data, scrape_id=scrape_id, mode=sort_by_new, page=page)

        # dedup within this mode
        new = [j for j in jobs if j.job_id not in seen_ids]
        for j in new:
            seen_ids.add(j.job_id)
        collected.extend(new)
        logger.info(
            f"[company={company}] [{scrape_id}] 📦 Page {page} added {len(new)} new (deduped {len(jobs) - len(new)}), total={len(collected)} (mode={sort_by_new})"
        )

        # page_info navigation
        page_info = (json_data.get("data", {}).get("job_search_with_featured_jobs", {}).get("page_info", {}))
        has_next = bool(page_info.get("has_next_page"))
        end_cursor = page_info.get("end_cursor")
        end_cursor_hash = _hash_short(end_cursor) if end_cursor else "none"

        logger.debug(
            f"[company={company}] [{scrape_id}] 🔎 page_info(has_next={has_next}, end_cursor={end_cursor_hash}) (mode={sort_by_new} page={page})"
        )

        if has_next and end_cursor:
            after_cursor = end_cursor
            page += 1
            await asyncio.sleep(random.uniform(1.0, 3.0))
        else:
            break

    logger.info(f"[company={company}] [{scrape_id}] ✅ mode sort_by_new={sort_by_new}: got {len(collected)} unique jobs")
    return collected

# ----------------- persist guard helper -----------------


def should_persist_jobs(result: ScrapeResult, min_expected_count: int = 50) -> Tuple[bool, str]:
    """
    Object-mode policy for Meta. Returns (should_persist, decision_reason).
    """
    company = get_company()

    if result is None:
        return False, "no_result"

    # anomaly guard
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


# ----------------- top-level: token refresh + decisioning -----------------


async def get_jobs(min_expected_count: int = 50):
    """
    Returns a dict compatible with existing callers:
      {
        "jobs": [MetaJob, ...],
        "scrape_id": str,
        "anomalous_zero": bool,
        "should_persist": bool,
        "decision_reason": str,
        "stats": {"default_count": int, "new_count": int},  # Meta-only extras
        "meta": {...}
      }
    """
    company = get_company()

    async def _scrape_once(label: str):
        ua = random.choice(USER_AGENTS)
        scrape_id = str(uuid.uuid4())[:8]
        logger.info(f"[company={company}] [{scrape_id}] 🚀 Starting Meta job scrape ({label}; union of both sort modes)…")

        tokens = extract_meta_tokens() or {}
        critical_missing = not (tokens.get("lsd") and tokens.get("__hsi") and tokens.get("__rev"))
        if critical_missing:
            logger.warning(
                f"[company={company}] [{scrape_id}] 🚨 Critical tokens missing; skipping this attempt to trigger retry."
            )
            return ScrapeResult(
                jobs=[],
                scrape_id=scrape_id,
                anomalous_zero=True,
                stats={"default_count": 0, "new_count": 0},
                meta={"note": "critical tokens missing"},
            )

        logger.info(
            f"[company={company}] [{scrape_id}] 🔑 tokens("
            f"__rev={_mask(tokens.get('__rev'))}, "
            f"__hsi={_mask(tokens.get('__hsi'))}, "
            f"lsd={_mask(tokens.get('lsd'))}, "
            f"jazoest={_mask(tokens.get('jazoest'))}, "
            f"__spin_r={_mask(tokens.get('__spin_r'))})"
        )

        await asyncio.sleep(random.uniform(0, 2.5))  # small jitter

        jobs_default, jobs_new = await asyncio.gather(
            fetch_all_pages_for_mode(tokens, sort_by_new=False, scrape_id=scrape_id, ua=ua),
            fetch_all_pages_for_mode(tokens, sort_by_new=True,  scrape_id=scrape_id, ua=ua),
        )

        by_id: Dict[str, MetaJob] = {}
        for j in jobs_default + jobs_new:
            if j.job_id not in by_id:
                by_id[j.job_id] = j

        all_jobs = list(by_id.values())
        logger.info(
            f"[company={company}] [{scrape_id}] 🎉 Meta union: {len(all_jobs)} unique jobs "
            f"(default={len(jobs_default)}, new={len(jobs_new)})"
        )

        anomalous_zero = (len(jobs_default) == 0 and len(jobs_new) == 0)
        if anomalous_zero:
            logger.warning(f"[company={company}] [{scrape_id}] 🚨 Anomalous ZERO across both modes – likely transient.")

        return ScrapeResult(
            jobs=all_jobs,
            scrape_id=scrape_id,
            anomalous_zero=anomalous_zero,
            stats={"default_count": len(jobs_default), "new_count": len(jobs_new)},
            meta={"mode": "union"},
        )

    # First pass
    first = await _scrape_once(label="first-pass")

    # Centralized anomaly guard + optional retry + final decision
    decided = await retry_and_decide(
        company=company,
        logger=logger,
        first_result=first,
        retry_fn=lambda: _scrape_once("retry-after-token-refresh"),
        min_expected_count=min_expected_count,
        should_persist_fn=should_persist_jobs,
    )

    return decided
