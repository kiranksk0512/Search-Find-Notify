from __future__ import annotations

import asyncio
import html
import json
import random
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional, List

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

# -----------------------------------------------------------------------------
# Configure all Google filters you want to query.
# kind = "tag" uses the last-slot tag list signature.
# kind = "category" uses Google’s category enum signature (e.g., SOFTWARE_ENGINEERING).
# -----------------------------------------------------------------------------
SEARCH_FILTERS: List[Dict[str, str]] = [
    {"kind": "tag", "value": "ai-spotlight"},
    {"kind": "category", "value": "SOFTWARE_ENGINEERING"},
    {"kind": "category", "value": "TECHNICAL_SOLUTIONS"},
    {"kind": "category", "value": "NETWORK_ENGINEERING"},
    {"kind": "category", "value": "DEVELOPER_RELATIONS"},
    {"kind": "keyword",  "value": "Systems Integrator"},
    {"kind": "keyword",  "value": "Network Deployment Engineer"},
    {"kind": "keyword",  "value": "site reliability engineer"},
    {"kind": "keyword",  "value": "Technical Solutions Engineer"},
    {"kind": "keyword",  "value": "Application Engineer"},
    # You can add more categories if you want, e.g.:
    # {"kind": "category", "value": "SECURITY_ENGINEERING"},
    # {"kind": "category", "value": "DATA_ENGINEERING"},
]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)... Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)... Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64)... Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3)... Version/16.4 Safari/605.1.15",
]

ACCEPT_LANGUAGES = [
    "en-GB,en-US;q=0.9,en;q=0.8",
    "en-US,en;q=0.9",
    "en;q=0.9",
]


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _headers(ua: Optional[str] = None) -> Dict[str, str]:
    # Align with DevTools; x-same-domain and referer matter
    return {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": random.choice(ACCEPT_LANGUAGES),
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
        "origin": "https://www.google.com",
        "pragma": "no-cache",
        "referer": "https://www.google.com/about/careers/applications/jobs/results/",
        "x-same-domain": "1",
        "user-agent": ua or random.choice(USER_AGENTS),
    }


def _build_url(rpcids: str, f_sid: str, bl: str, at: Optional[str]) -> str:
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
    if at:
        params["at"] = at
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GOOGLE_URL}?{q}"


# ------------------------- Payload builders (exact shapes) --------------------
def _build_form_payload_for_tag(page: int, rpcid: str, tag: str) -> Dict[str, Any]:
    """
    Matches the 'ai-spotlight' DevTools signature:
      15-pos array, tag list at last slot (index 14), page at index 7.
      [None,None,None,None,"en",None,[["United States"]], page, None,None,None,None,None,None, [tag]]
    """
    args = [
        None, None, None, None,
        "en",
        None,
        [["United States"]],
        page,
        None, None, None, None, None, None,
        [tag],
    ]
    f_req = [[[rpcid, json.dumps([args]), None, "3"]]]
    return {"f.req": json.dumps(f_req)}


def _build_form_payload_for_category(page: int, rpcid: str, category_enum: str) -> Dict[str, Any]:
    """
    Matches your 'SOFTWARE_ENGINEERING' DevTools payload:
      14-pos array, category list at last slot (index 13), page at index 7.
      [None,None,None,None,"en",None,[["United States"]], page, None,None,None,None,None, [CATEGORY]]
    """
    args = [
        None, None, None, None,
        "en",
        None,
        [["United States"]],
        page,
        None, None, None, None, None,
        [category_enum],
    ]
    f_req = [[[rpcid, json.dumps([args]), None, "3"]]]
    return {"f.req": json.dumps(f_req)}

def _build_form_payload_for_keyword(page: int, rpcid: str, query_text: str) -> Dict[str, Any]:
    """
    Matches your 'Systems Integrator' DevTools payload (text search signature):
      8-pos array; query string at index 0, page at index 7.
      ["Systems Integrator", None, None, None, "en", None, [["United States"]], page]
    """
    args = [
        query_text,          # 0: free-text query
        None,                # 1
        None,                # 2
        None,                # 3
        "en",                # 4
        None,                # 5
        [["United States"]], # 6
        page,                # 7
    ]
    f_req = [[[rpcid, json.dumps([args]), None, "3"]]]
    return {"f.req": json.dumps(f_req)}


def _parse_batchexecute_for_jobs(response_text: str) -> List[list]:
    """
    Extract job rows from batchExecute leniently (accept any 'wrb.fr').
    """
    cleaned = (response_text or "").lstrip(")]}'\n")
    for line in cleaned.splitlines():
        try:
            parsed = json.loads(line)
            for entry in parsed:
                if not (isinstance(entry, list) and entry and entry[0] == "wrb.fr" and len(entry) >= 3):
                    continue
                payload_str = entry[2]
                try:
                    arr = json.loads(payload_str)
                except Exception:
                    continue
                # Common: [ [ [row...], ...], ... ]
                if isinstance(arr, list) and arr:
                    if isinstance(arr[0], list) and arr[0] and isinstance(arr[0][0], list):
                        return arr[0]
                    # Fallback: walk for first list-of-rows
                    found: List[list] = []
                    def walk(node):
                        if isinstance(node, list) and node and isinstance(node[0], list):
                            first = node[0]
                            if first and isinstance(first, list) and len(first) >= 2 and isinstance(first[0], str):
                                found.append(node)
                                return
                        if isinstance(node, list):
                            for c in node:
                                walk(c)
                    walk(arr)
                    if found:
                        return found[0]
        except Exception:
            continue
    return []


async def _scrape_once(label: str) -> ScrapeResult:
    company = get_company()
    run_ua = random.choice(USER_AGENTS)
    logger.info(f"[company={company}] 🚀 Google scrape ({label}) starting (ua={run_ua})…")

    # modest jitter
    await asyncio.sleep(random.uniform(0.0, 2.5))

    tokens = await extract_google_tokens_and_cookies()
    rpcids = tokens.get("rpcids")
    f_sid = tokens.get("f.sid")
    bl = tokens.get("bl")
    at = tokens.get("at")
    cookies_dict = tokens.get("cookies") or {}

    if not (rpcids and f_sid and bl):
        logger.error(f"[company={company}] ❌ Missing required Google tokens (rpcids/f.sid/bl).")
        return ScrapeResult(
            jobs=[],
            scrape_id=str(random.getrandbits(32))[:8],
            anomalous_zero=True,
            stats={"reason": "missing_tokens"},
            meta={"stage": "preflight"},
        )

    raw_cookie_header = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
    url = _build_url(rpcids, f_sid, bl, at)

    all_jobs: List[GoogleJob] = []
    per_filter_counts: Dict[str, int] = {}
    per_filter_pages: Dict[str, int] = {}
    empty_page_stops: Dict[str, int] = {}
    unique_seen = set()

    for filt in SEARCH_FILTERS:
        kind = filt["kind"]
        value = filt["value"]
        label_str = f"{kind}:{value}"

        logger.info(f"[company={company}] 🔍 Google query: {label_str}")
        page = 1
        consecutive_empty_pages = 0
        page_count_for_filter = 0
        added_for_filter = 0

        while True:
            headers = _headers(run_ua)
            if kind == "tag":
                payload = _build_form_payload_for_tag(page, rpcids, value)
            elif kind == "category":
                payload = _build_form_payload_for_category(page, rpcids, value)
            elif kind == "keyword":   # <-- NEW
                payload = _build_form_payload_for_keyword(page, rpcids, value)
            else:
                logger.warning(f"[company={company}] ⚠️ Unknown filter kind '{kind}', skipping")
                break

            response_text = await post_form(
                url=url,
                payload=payload,
                headers=headers,
                parse_json=False,        # batchExecute returns text lines
                cookies=raw_cookie_header,
            )
            page_count_for_filter += 1

            if response_text is None:
                logger.error(f"[company={company}] ❌ No response for '{label_str}' page {page}")
                break

            try:
                job_entries = _parse_batchexecute_for_jobs(response_text)
            except Exception as e:
                logger.exception(f"[company={company}] ❌ Parse error for '{label_str}' page {page}: {e}")
                break

            if not job_entries:
                consecutive_empty_pages += 1
                logger.warning(f"[company={company}] ⚠️ Empty job page for '{label_str}' page {page} (streak={consecutive_empty_pages})")
                if consecutive_empty_pages >= 3:
                    empty_page_stops[label_str] = consecutive_empty_pages
                    logger.warning(f"[company={company}] ⛔ Stopping '{label_str}' after 3 empty pages.")
                    break
                page += 1
                await asyncio.sleep(random.uniform(0.8, 2.2))
                continue

            consecutive_empty_pages = 0

            for row in job_entries:
                try:
                    job_id = row[0]
                    if job_id in unique_seen:
                        continue
                    unique_seen.add(job_id)
                    
                    job_title = html.unescape(row[1])
                    job_url = f"https://www.google.com/about/careers/applications/jobs/results/{job_id}"
                    date_posted = _now_iso_utc()
                    all_jobs.append(
                        GoogleJob(
                            job_id=job_id,
                            title=job_title,
                            url=job_url,
                            date_posted=date_posted,
                        )
                    )
                    added_for_filter += 1
                except Exception:
                    continue

            logger.info(f"[company={company}] ✅ '{label_str}' page {page}: +{len(job_entries)} jobs (cumulative {added_for_filter})")
            page += 1
            await asyncio.sleep(random.uniform(0.8, 2.2))

        per_filter_counts[label_str] = added_for_filter
        per_filter_pages[label_str] = page_count_for_filter

    total_jobs = len(all_jobs)
    logger.info(f"[company={company}] 🎉 Google union: {total_jobs} jobs across {len(SEARCH_FILTERS)} filters")

    anomalous_zero = (total_jobs == 0)

    return ScrapeResult(
        jobs=all_jobs,
        scrape_id=str(random.getrandbits(32))[:8],
        anomalous_zero=anomalous_zero,
        stats={
            "total_jobs": total_jobs,
            "per_filter_counts": per_filter_counts,
            "per_filter_pages": per_filter_pages,
            "empty_page_stops": empty_page_stops,
            "user_agent": run_ua,
        },
        meta={"mode": "batchExecute"},
    )


def should_persist_jobs(result: ScrapeResult, min_expected_count: int = 1) -> Tuple[bool, str]:
    """
    For spotlight + category slices, persist if non-zero.
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

    return True, "ok"


async def get_jobs(min_expected_count: int = 1) -> ScrapeResult:
    """
    Entry point. We keep min_expected_count low (these filters return small pages).
    """
    company = get_company()

    async def _run_once(label: str) -> ScrapeResult:
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
