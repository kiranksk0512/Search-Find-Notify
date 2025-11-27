from __future__ import annotations

import asyncio
import json
import os
import random
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from core.context import get_company
from core.decision import retry_and_decide
from core.logger import get_company_logger
from core.scrape_types import ScrapeResult
from models.cisco_job import CiscoJob

logger = get_company_logger()


def _read_env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return max(default, 1)
    try:
        value = int(raw)
        return max(value, 1)
    except ValueError:
        logger.warning(f"[cisco] Invalid integer for {key!r}={raw!r}; falling back to {default}")
        return max(default, 1)


WIDGETS_URL = "https://careers.cisco.com/widgets"
REFNUM_DEFAULT = "CISCISGLOBAL"
REFNUM = os.getenv("CISCO_REFNUM", REFNUM_DEFAULT)
PAGE_SIZE = _read_env_int("CISCO_PAGE_SIZE", 10)
MAX_PAGES = _read_env_int("CISCO_MAX_PAGES", 100)
MIN_EXPECTED_COUNT = _read_env_int("CISCO_MIN_EXPECTED", 30)
_country_raw = os.getenv("CISCO_COUNTRIES", "United States of America")
COUNTRY_FILTERS = [
    c.strip() for c in _country_raw.replace(",", "|").split("|") if c.strip()
]
KEYWORDS = os.getenv("CISCO_KEYWORDS", "")
SITE_TYPE = os.getenv("CISCO_SITE_TYPE", "external")
LANG_CODE = os.getenv("CISCO_LANG", "en_global")
DEVICE_TYPE = os.getenv("CISCO_DEVICE_TYPE", "desktop")

CISCO_COOKIE = os.getenv("CISCO_COOKIE", "").strip()
CISCO_CSRF_TOKEN = os.getenv("CISCO_CSRF_TOKEN", "").strip()

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
]

ACCEPT_LANGUAGES = [
    "en-GB,en-US;q=0.9,en;q=0.8",
    "en-US,en;q=0.9",
    "en;q=0.8",
]

REQUEST_DELAY_RANGE = (0.35, 0.7)


def _build_headers(user_agent: str) -> Dict[str, str]:
    headers = {
        "accept": "*/*",
        "accept-language": random.choice(ACCEPT_LANGUAGES),
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": "https://careers.cisco.com",
        "pragma": "no-cache",
        "referer": "https://careers.cisco.com/global/en/search-results",
        "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": user_agent,
        "priority": "u=1, i",
    }
    if CISCO_COOKIE:
        headers["cookie"] = CISCO_COOKIE
    if CISCO_CSRF_TOKEN:
        headers["x-csrf-token"] = CISCO_CSRF_TOKEN
    return headers


def _build_payload(offset: int, page_size: int) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "sortBy": "Most recent",
        "subsearch": "",
        "from": offset,
        "jobs": True,
        "counts": True,
        "all_fields": [
            "category",
            "country",
            "state",
            "city",
            "type",
            "RemoteType",
            "raasJobRequisitionType",
        ],
        "pageName": "search-results",
        "size": page_size,
        "clearAll": False,
        "jdsource": "facets",
        "isSliderEnable": False,
        "pageId": "page4",
        "siteType": SITE_TYPE,
        "keywords": KEYWORDS,
        "global": True,
        "selected_fields": {},
        "sort": {"order": "desc", "field": "postedDate"},
        "lang": LANG_CODE,
        "deviceType": DEVICE_TYPE,
        "country": "global",
        "refNum": REFNUM,
        "ddoKey": "refineSearch",
    }

    if COUNTRY_FILTERS:
        payload["selected_fields"]["country"] = COUNTRY_FILTERS

    # Remove empty selected_fields to match observed payloads
    if not payload["selected_fields"]:
        payload.pop("selected_fields", None)

    return payload


def _normalise_date(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        if "T" in raw:
            return raw.split("T", 1)[0]
        return raw
    except Exception:
        return raw


def _extract_locations(job: Dict[str, Any]) -> Tuple[str, ...]:
    collected: List[str] = []
    multi = job.get("multi_location") or []
    array = job.get("multi_location_array") or []

    def _add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            if value not in collected:
                collected.append(value)
        elif isinstance(value, dict):
            loc = value.get("location") or value.get("value")
            if isinstance(loc, str) and loc.strip() and loc not in collected:
                collected.append(loc)

    if isinstance(multi, list):
        for entry in multi:
            _add(entry)
    if isinstance(array, list):
        for entry in array:
            _add(entry)

    primary = job.get("cityStateCountry") or job.get("location")
    if isinstance(primary, str) and primary.strip() and primary not in collected:
        collected.insert(0, primary)

    return tuple(collected)


def _parse_jobs(payload: Dict[str, Any], scrape_id: str, page: int) -> Tuple[List[CiscoJob], int]:
    company = get_company()
    refine = payload.get("refineSearch")
    if not isinstance(refine, dict):
        logger.error(f"[company={company}] [{scrape_id}] ❌ Unexpected payload shape on page {page}: keys={list(payload.keys())}")
        return [], 0

    status = refine.get("status")
    if status and status != 200:
        logger.warning(f"[company={company}] [{scrape_id}] ⚠️ Non-200 status {status} on page {page}")

    total_hits = int(refine.get("totalHits") or refine.get("hits") or 0)
    data_section = refine.get("data") or {}
    jobs_raw = data_section.get("jobs") or []

    if not isinstance(jobs_raw, list):
        logger.warning(f"[company={company}] [{scrape_id}] ⚠️ jobs payload not a list on page {page}: type={type(jobs_raw)}")
        jobs_raw = []

    parsed: List[CiscoJob] = []
    for job in jobs_raw:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("jobId") or job.get("reqId") or job.get("jobSeqNo") or "").strip()
        if not job_id:
            continue

        title = job.get("title", "Unknown")
        url = job.get("applyUrl") or job.get("jobUrl") or job.get("jobDetailUrl")
        if not url:
            url = f"https://careers.cisco.com/jobs/ProjectDetail/{job_id}"

        loc_tuple = _extract_locations(job)
        primary_loc = loc_tuple[0] if loc_tuple else job.get("cityStateCountry") or job.get("location") or "Unknown"
        remote_type = job.get("RemoteType") or job.get("remoteType") or "Unknown"
        job_type = job.get("type") or job.get("jobType") or "Unknown"
        category = job.get("category")
        if not category:
            multi_cat = job.get("multi_category") or []
            if isinstance(multi_cat, list):
                category = ", ".join([c for c in multi_cat if isinstance(c, str) and c.strip()])
        if not category:
            category = "Unknown"

        department = job.get("department") or "Unknown"
        posted = _normalise_date(job.get("postedDate"))
        created = _normalise_date(job.get("dateCreated"))

        parsed.append(
            CiscoJob(
                job_id=job_id,
                title=title,
                url=url,
                location=primary_loc,
                remote_type=remote_type,
                job_type=job_type,
                category=category,
                department=department,
                all_locations=loc_tuple,
                date_posted=posted,
                date_created=created,
            )
        )

    logger.info(
        f"[company={company}] [{scrape_id}] 🧩 Parsed {len(parsed)} jobs on page {page} (total_hits={total_hits})"
    )
    return parsed, total_hits


async def _fetch_page(session: aiohttp.ClientSession, payload: Dict[str, Any], scrape_id: str, page: int) -> Optional[Dict[str, Any]]:
    company = get_company()
    t0 = time.time()
    try:
        async with session.post(WIDGETS_URL, json=payload) as resp:
            text = await resp.text()
            dt = int((time.time() - t0) * 1000)
            if resp.status != 200:
                logger.error(
                    f"[company={company}] [{scrape_id}] ❌ Page {page} fetch failed (status={resp.status} ms={dt})"
                )
                logger.debug(f"[company={company}] [{scrape_id}] Payload response: {text[:500]}")
                return None
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                logger.error(
                    f"[company={company}] [{scrape_id}] ❌ JSON decode failed on page {page}"
                )
                logger.debug(f"[company={company}] [{scrape_id}] Response text: {text[:500]}")
                return None
    except Exception as exc:
        dt = int((time.time() - t0) * 1000)
        logger.error(
            f"[company={company}] [{scrape_id}] ❌ Exception during page {page} fetch (ms={dt}): {exc}"
        )
        return None


def should_persist_jobs(result: ScrapeResult, min_expected_count: int = MIN_EXPECTED_COUNT) -> Tuple[bool, str]:
    company = get_company()
    if result is None:
        return False, "no_result"

    if result.anomalous_zero:
        logger.warning(f"[company={company}] [{result.scrape_id}] anomalous_zero=True")
        return False, "anomalous_zero"

    total = len(result.jobs or [])
    if total == 0:
        return False, "zero_jobs"

    if total < min_expected_count:
        return False, f"too_few({total}<{min_expected_count})"

    return True, "ok"


async def _scrape_once(label: str, *, min_expected_count: int) -> ScrapeResult:
    company = get_company()
    scrape_id = str(uuid.uuid4())[:8]
    ua = random.choice(USER_AGENTS)

    logger.info(
        f"[company={company}] [{scrape_id}] 🚀 Starting Cisco scrape ({label}) with UA={ua[:25]}…"
    )

    headers = _build_headers(ua)
    timeout = aiohttp.ClientTimeout(total=45)

    if not CISCO_COOKIE:
        logger.info(
            f"[company={company}] [{scrape_id}] ℹ️ Running without CISCO_COOKIE; relying on public widget access"
        )
    if not CISCO_CSRF_TOKEN:
        logger.info(
            f"[company={company}] [{scrape_id}] ℹ️ No CISCO_CSRF_TOKEN supplied; server must allow anonymous POSTs"
        )

    deduped: Dict[str, CiscoJob] = {}
    empty_streak = 0
    total_hits_reported: Optional[int] = None
    pages_attempted = 0

    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:

        for page in range(MAX_PAGES):
            offset = page * PAGE_SIZE
            payload = _build_payload(offset, PAGE_SIZE)
            page_data = await _fetch_page(session, payload, scrape_id, page)
            pages_attempted = page + 1

            if page_data is None:
                empty_streak += 1
                logger.warning(
                    f"[company={company}] [{scrape_id}] ⚠️ Empty response streak={empty_streak} on page {page}"
                )
                if empty_streak >= 3:
                    logger.warning(
                        f"[company={company}] [{scrape_id}] 🛑 Breaking after {empty_streak} consecutive empty responses"
                    )
                    break
                await asyncio.sleep(random.uniform(*REQUEST_DELAY_RANGE))
                continue

            page_jobs, total_hits = _parse_jobs(page_data, scrape_id, page)
            if total_hits and total_hits_reported is None:
                total_hits_reported = total_hits

            if not page_jobs:
                empty_streak += 1
                logger.info(
                    f"[company={company}] [{scrape_id}] 🈳 No jobs returned on page {page} (streak={empty_streak})"
                )
                if empty_streak >= 3 :
                    logger.info(
                        f"[company={company}] [{scrape_id}] 🛑 Stopping pagination (empty streak)"
                    )
                    break
                await asyncio.sleep(random.uniform(*REQUEST_DELAY_RANGE))
                continue

            empty_streak = 0
            for job in page_jobs:
                deduped[job.job_id] = job

            logger.info(
                f"[company={company}] [{scrape_id}] 📦 Page {page}: {len(page_jobs)} jobs (unique={len(deduped)})"
            )

            await asyncio.sleep(random.uniform(*REQUEST_DELAY_RANGE))

    final_jobs = list(deduped.values())
    anomalous_zero = len(final_jobs) == 0

    stats: Dict[str, Any] = {
        "pages": pages_attempted,
        "fetched": len(final_jobs),
        "page_size": PAGE_SIZE,
        "empty_streak_final": empty_streak,
    }
    if total_hits_reported is not None:
        stats["total_hits"] = total_hits_reported

    meta = {
        "source": "widgets_api",
        "country_filters": COUNTRY_FILTERS,
        "keywords": KEYWORDS,
        "site_type": SITE_TYPE,
    }

    result = ScrapeResult(
        jobs=final_jobs,
        scrape_id=scrape_id,
        anomalous_zero=anomalous_zero,
        stats=stats,
        meta=meta,
    )

    logger.info(
        f"[company={company}] [{scrape_id}] 🎉 Cisco total={len(final_jobs)} (anomalous_zero={anomalous_zero})"
    )
    return result


async def get_jobs(min_expected_count: int = MIN_EXPECTED_COUNT) -> ScrapeResult:
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
