# scrapers/adobe.py
import os
import json
import re
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, quote

from core.logger import get_company_logger
from core.fetcher import post_json  # <- your fetcher exposes this
from core.scrape_types import ScrapeResult
from models.adobe_job import AdobeJob

# ----------------------------- Constants -------------------------------------

COMPANY = "adobe"
logger = get_company_logger(COMPANY)

ADOBE_WIDGETS_URL = "https://careers.adobe.com/widgets"
CAREERS_BASE = "https://careers.adobe.com"
CAREERS_JOB_BASE = f"{CAREERS_BASE}/us/en/job/"

PAGE_SIZE = 10  # paginate until short page

# Filters captured from DevTools (selected_fields in payload)
FILTERS: Dict[str, List[str]] = {
    "country": ["United States of America"],
    "roleType": ["Individual Contributor"],  # -> jobLevel in payload
    "teams": ["Design", "Engineering and Product", "Information Technology", "Other", "Research"],
}

JSON_HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": CAREERS_BASE,
    "Referer": f"{CAREERS_BASE}/us/en/search-results",
    "User-Agent": "Mozilla/5.0 (JobScraper; +https://example.com)",
    # If Adobe ever requires CSRF, add it here:
    # "x-csrf-token": "...",
}

# ----------------------------- (Optional) Cache ------------------------------
# We keep the cache in case later you re-enable resolving canonicals.
CACHE_PATH = "data/adobe_url_cache.json"

def _load_cache() -> Dict[str, str]:
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_cache(cache: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

_URL_CACHE: Dict[str, str] = _load_cache()  # not used now but harmless

# ----------------------------- Utils -----------------------------------------

_slug_re = re.compile(r"[^a-z0-9]+", re.I)

def _slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = _slug_re.sub("-", s).strip("-")
    return quote(s)

def _iso_date(raw: str) -> str:
    # Adobe postedDate looks like "YYYY-MM-DDTHH:MM:SS.mmm+0000"
    return raw[:10] if raw else ""

def _build_payload(offset: int) -> Dict[str, Any]:
    # Mirrors the refineSearch widget payload from DevTools
    return {
        "lang": "en_us",
        "deviceType": "desktop",
        "country": "us",
        "pageName": "search-results",
        "all_fields": [
            "remote", "country", "state", "city", "experienceLevel",
            "category", "profession", "employmentType", "jobLevel"
        ],
        "clearAll": False,
        "counts": True,
        "ddoKey": "refineSearch",
        "from": offset,     # pagination offset
        "global": True,
        "isSliderEnable": False,
        "jdsource": "facets",
        "jobs": True,
        "keywords": "",
        "locationData": {},
        "pageId": "page15-ds",
        "selected_fields": {
            "category": FILTERS["teams"],
            "country": FILTERS["country"],
            "jobLevel": FILTERS["roleType"],
        },
        "siteType": "external",
        "size": PAGE_SIZE,
        "sortBy": "",
        "subsearch": "",
    }

# ----------------------------- Mapping ---------------------------------------

async def _map_item(item: Dict[str, Any]) -> AdobeJob:
    """
    Map an API item to AdobeJob.
    Prefer Adobe careers detail if API provides a path; otherwise use Workday applyUrl.
    """
    req_id = str(item.get("reqId", "")).strip()
    title = item.get("title", "") or ""
    apply_url = item.get("applyUrl", "") or ""
    location = item.get("location", "") or item.get("cityStateCountry", "") or ""
    team = item.get("category", "") or ""
    date_posted = _iso_date(item.get("postedDate", ""))

    # 1) If API exposes a detail path, use it immediately
    detail_path = item.get("jobDetailPath") or item.get("jobDetailUrl")
    url_detail = urljoin(CAREERS_BASE, detail_path) if detail_path else None

    # 2) (Resolver removed) — if no detail path, we won't try to resolve; fallback to applyUrl.

    # 3) Optional last resort: construct slug URL (keep but DO NOT rely on it)
    constructed = None
    if not url_detail and req_id and title:
        constructed = f"{CAREERS_JOB_BASE}{req_id}/{_slugify(title)}"

    # Final choice: detail path if present, else constructed if you want it, else applyUrl
    final_url = url_detail or constructed or apply_url

    return AdobeJob(
        job_id=req_id,      # must be the real Adobe reqId (e.g., "R162315")
        title=title,
        url=final_url,
        location=location,
        date_posted=date_posted,
        team=team,
    )

# ----------------------------- Fetching --------------------------------------

async def _fetch_json_page(offset: int) -> List[AdobeJob]:
    payload = _build_payload(offset)
    # core.fetcher.post_json signature: (url, data, headers=...)
    data = await post_json(ADOBE_WIDGETS_URL, payload, headers=JSON_HEADERS)

    # API shape: refineSearch -> data -> jobs
    results = (
        data.get("refineSearch", {})
            .get("data", {})
            .get("jobs", [])
        or []
    )

    jobs: List[AdobeJob] = []
    for item in results:
        jobs.append(await _map_item(item))
    return jobs

async def _run_once(label: str) -> ScrapeResult:
    collected: List[AdobeJob] = []
    offset = 0
    while True:
        page_jobs = await _fetch_json_page(offset)
        if not page_jobs:
            break
        collected.extend(page_jobs)
        if len(page_jobs) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    logger.info(f"Adobe: collected {len(collected)} jobs in {label}")
    return ScrapeResult(
        jobs=collected,
        scrape_id=label,
        anomalous_zero=(len(collected) == 0),
        should_persist=True,
        decision_reason="ok" if collected else "empty_result",
        stats={"default_count": len(collected)},
        meta={"filters": FILTERS},
    )

# ----------------------------- Entry -----------------------------------------

async def get_jobs() -> ScrapeResult:
    logger.info("🔍 Starting scraper for Adobe...")
    return await _run_once("first-pass")

###########################################-----------GETTING WORKDAY URLS-----------###########################################   

# # scrapers/adobe.py
# import re
# from typing import Dict, List, Optional, Tuple

# import aiohttp

# from core.context import current_company
# from core.logger import get_company_logger
# from core.fetcher import post_json
# from core.decision import retry_and_decide
# from core.scrape_types import ScrapeResult
# from core.storage_router import save_aux_json
# from models.adobe_job import AdobeJob

# # ---------- Endpoints & constants ----------
# ADOBE_WIDGETS_URL = "https://careers.adobe.com/widgets"
# LISTING_URL = "https://careers.adobe.com/us/en/search-results"
# PAGE_SIZE = 10  # from Adobe payload

# # Mirror your selected filters EXACTLY (as DevTools shows them)
# FILTERS: Dict[str, List[str]] = {
#     "country": ["United States of America"],                # -> selected_fields.country
#     "roleType": ["Individual Contributor"],                 # -> selected_fields.jobLevel
#     "teams": [                                              # -> selected_fields.category
#         "Design",
#         "Engineering and Product",
#         "Information Technology",
#         "Other",
#         "Research",
#     ],
# }

# # Minimal header set; add only if Adobe requires more
# BASE_HEADERS: Dict[str, str] = {
#     "accept": "application/json, text/plain, */*",
#     "user-agent": "Mozilla/5.0",
#     "referer": LISTING_URL,
#     "origin": "https://careers.adobe.com",
# }

# # Extract R-numbers (e.g., R149328)
# REQ_ID_RE = re.compile(r"\bR\d{3,7}\b", re.IGNORECASE)


# def _extract_job_id(*candidates: str) -> Optional[str]:
#     for c in candidates:
#         if not c:
#             continue
#         m = REQ_ID_RE.search(c)
#         if m:
#             return m.group(0).upper()
#     return None


# def _iso_date(s: str) -> str:
#     """Normalize 2025-05-01T00:00:00.000+0000 -> 2025-05-01."""
#     if not s:
#         return ""
#     m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
#     return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


# def _build_payload(offset: int) -> dict:
#     """
#     Mirrors the DevTools Request Payload you captured.
#     Only 'from' (offset) changes per page; PAGE_SIZE is fixed.
#     """
#     return {
#         "lang": "en_us",
#         "deviceType": "desktop",
#         "country": "us",
#         "pageName": "search-results",
#         "all_fields": [
#             "remote", "country", "state", "city",
#             "experienceLevel", "category", "profession",
#             "employmentType", "jobLevel"
#         ],
#         "clearAll": False,
#         "counts": True,
#         "ddoKey": "refineSearch",
#         "from": offset,               # pagination offset
#         "global": True,
#         "isSliderEnable": False,
#         "jdsource": "facets",
#         "jobs": True,
#         "keywords": "",
#         "locationData": {},
#         "pageId": "page15-ds",
#         "selected_fields": {
#             "category": FILTERS["teams"],
#             "country": FILTERS["country"],
#             "jobLevel": FILTERS["roleType"],
#         },
#         "siteType": "external",
#         "size": PAGE_SIZE,            # page size
#         "sortBy": "",
#         "subsearch": ""
#     }


# def _maybe_extract_csrf(html: str) -> Optional[str]:
#     """Best-effort CSRF extraction if Adobe embeds one."""
#     # <meta name="csrf-token" content="...">
#     m = re.search(r'name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', html, re.I)
#     if m:
#         return m.group(1)
#     # Or inline JSON like: "x-csrf-token":"..."
#     m = re.search(r'"x-csrf-token"\s*:\s*"([^"]+)"', html)
#     if m:
#         return m.group(1)
#     return None


# async def _prime_session_and_headers() -> Dict[str, str]:
#     """
#     Optional: GET the listing page to set cookies and maybe grab a CSRF token.
#     If it fails or token not found, just return BASE_HEADERS.
#     """
#     headers = dict(BASE_HEADERS)
#     try:
#         async with aiohttp.ClientSession(headers=headers) as sess:
#             async with sess.get(LISTING_URL, timeout=20) as resp:
#                 html = await resp.text()
#         token = _maybe_extract_csrf(html)
#         if token:
#             headers["x-csrf-token"] = token
#     except Exception:
#         # Silent fallback to BASE_HEADERS
#         pass
#     return headers


# async def _fetch_json_page(offset: int, headers: Dict[str, str]) -> List[AdobeJob]:
#     """
#     POST to /widgets with your exact payload; parse refineSearch.data.jobs.
#     """
#     payload = _build_payload(offset)
#     # NOTE: post_json(url, payload, headers) — positional payload (no 'json=' kwarg)
#     data = await post_json(ADOBE_WIDGETS_URL, payload, headers)

#     # Dump first page for debugging (request/response preview)
#     if offset == 0:
#         try:
#             save_aux_json(current_company.get(), "debug_page0", {
#                 "request": payload,
#                 "response_preview": (data or {})
#             })
#         except Exception:
#             pass

#     rs = (data or {}).get("refineSearch", {})
#     results = ((rs.get("data") or {}).get("jobs")) or []
#     jobs: List[AdobeJob] = []
#     for item in results:
#         job_id = _extract_job_id(
#             str(item.get("reqId", "")),
#             str(item.get("jobId", "")),
#             item.get("applyUrl", ""),
#         ) or str(item.get("reqId") or item.get("jobId") or "")

#         title = item.get("title", "")
#         url = item.get("applyUrl", "")
#         location = item.get("location", "") or item.get("cityStateCountry", "")
#         date_posted = _iso_date(item.get("postedDate", ""))
#         team = item.get("category", "")

#         jobs.append(AdobeJob(
#             job_id=job_id,
#             title=title,
#             url=url,
#             location=location,
#             date_posted=date_posted,
#             team=team,
#         ))
#     return jobs


# async def _run_once(label: str) -> ScrapeResult:
#     company = current_company.get()
#     logger = get_company_logger(company)

#     headers = await _prime_session_and_headers()

#     collected: List[AdobeJob] = []
#     offset = 0
#     while True:
#         page_jobs = await _fetch_json_page(offset, headers)
#         if not page_jobs:
#             break
#         collected.extend(page_jobs)
#         if len(page_jobs) < PAGE_SIZE:
#             break
#         offset += PAGE_SIZE

#     logger.info(f"Adobe: collected {len(collected)} jobs in {label}")
#     return ScrapeResult(
#         jobs=collected,
#         scrape_id=label,
#         anomalous_zero=(len(collected) == 0),
#         should_persist=True,                   # let framework handle big-drop & stability
#         decision_reason="ok" if collected else "empty_result",
#         stats={"default_count": len(collected)},
#         meta={"filters": FILTERS},
#     )


# def _adobe_should_persist(result: ScrapeResult, min_expected: int) -> Tuple[bool, str]:
#     """
#     retry_and_decide expects (should_persist, reason).
#     Always persist; if zero results, label the reason so the framework's stability can act.
#     """
#     count = int(result.stats.get("default_count", 0))
#     if count <= 0:
#         return (True, "empty_result")
#     return (True, "ok")


# async def get_jobs() -> ScrapeResult:
#     """
#     Framework entrypoint: run once, retry once on anomaly, then decide.
#     """
#     company = current_company.get()
#     logger = get_company_logger(company)

#     first = await _run_once("first-pass")
#     decided = await retry_and_decide(
#         company=company,
#         logger=logger,
#         first_result=first,
#         retry_fn=lambda: _run_once("retry-after-anomaly"),
#         min_expected_count=0,
#         should_persist_fn=_adobe_should_persist,
#     )
#     return decided
