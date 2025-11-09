import json
import os
import re
import asyncio
import random
from typing import List, Dict, Any
from urllib.parse import urljoin, quote

from core.context import get_company
from core.decision import retry_and_decide
from core.logger import get_company_logger
from core.fetcher import post_json  
from core.scrape_types import ScrapeResult
from models.adobe_job import AdobeJob

COMPANY = "adobe"
logger = get_company_logger(COMPANY)

ADOBE_WIDGETS_URL = "https://careers.adobe.com/widgets"
CAREERS_BASE = "https://careers.adobe.com"
CAREERS_JOB_BASE = f"{CAREERS_BASE}/us/en/job/"

PAGE_SIZE = 10
EMPTY_STREAK_LIMIT = 3
MAX_PAGES = 500

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
]

FILTERS: Dict[str, List[str]] = {
    "country": ["United States of America"],
    "roleType": ["Individual Contributor"],
    "teams": ["Design", "Engineering and Product", "Information Technology", "Other", "Research"],
}

JSON_HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": CAREERS_BASE,
    "Referer": f"{CAREERS_BASE}/us/en/search-results",
    "User-Agent": random.choice(USER_AGENTS),
}




_slug_re = re.compile(r"[^a-z0-9]+", re.I)

def _slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = _slug_re.sub("-", s).strip("-")
    return quote(s)

def _iso_date(raw: str) -> str:
    return raw[:10] if raw else ""

def _build_payload(offset: int) -> Dict[str, Any]:
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
        "from": offset,
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


async def _map_item(item: Dict[str, Any]) -> AdobeJob:
    req_id = str(item.get("reqId", "")).strip()
    title = item.get("title", "") or ""
    apply_url = item.get("applyUrl", "") or ""
    location = item.get("location", "") or item.get("cityStateCountry", "") or ""
    team = item.get("category", "") or ""
    date_posted = _iso_date(item.get("postedDate", ""))

    # Construct URLs
    detail_path = item.get("jobDetailPath") or item.get("jobDetailUrl")
    url_detail = urljoin(CAREERS_BASE, detail_path) if detail_path else None
    constructed = None
    if not url_detail and req_id and title:
        constructed = f"{CAREERS_JOB_BASE}{req_id}/{_slugify(title)}"
    final_url = url_detail or constructed or apply_url

    # New metadata fields
    category = item.get("category")
    date_created = item.get("dateCreated")
    department = item.get("department")
    hiring_manager = item.get("hiringManager")
    is_multi_category = item.get("isMultiCategory")
    is_multi_location = item.get("isMultiLocation")
    job_posting_end_date = item.get("jobPostingEndDate")
    job_seq_no = item.get("jobSeqNo")
    visibility_type = item.get("visibilityType")
    country = item.get("country")
    experience_level = item.get("experienceLevel")
    ml_skills = item.get("ml_skills") or []

    return AdobeJob(
        job_id=req_id,
        title=title,
        url=final_url,
        location=location,
        date_posted=date_posted,
        team=team,
        category=category,
        date_created=date_created,
        department=department,
        hiring_manager=hiring_manager,
        is_multi_category=is_multi_category,
        is_multi_location=is_multi_location,
        job_posting_end_date=job_posting_end_date,
        job_seq_no=job_seq_no,
        visibility_type=visibility_type,
        country=country,
        experience_level=experience_level,
        ml_skills=ml_skills,
    )


async def _fetch_json_page(offset: int) -> List[AdobeJob]:
    payload = _build_payload(offset)
    data = await post_json(ADOBE_WIDGETS_URL, payload, headers=JSON_HEADERS)
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

def should_persist_jobs(result: ScrapeResult, min_expected_count: int):
    if not result or not result.jobs:
        return False, "zero_jobs"
    total = len(result.jobs)
    if total < min_expected_count:
        return False, f"too_few({total}<{min_expected_count})"
    return True, "ok"


async def _run_once(label: str, min_expected_count: int = 10) -> ScrapeResult:
    collected: List[AdobeJob] = []
    offset = 0
    page = 0
    empty_streak = 0

    logger.info(f"▶️ Starting Adobe scrape ({label})")

    while page < MAX_PAGES:
        logger.info(f"[Adobe] Fetching page {page + 1} (offset={offset})")
        page_jobs = await _fetch_json_page(offset)

        if not page_jobs:
            empty_streak += 1
            logger.info(f"[Adobe] Empty page #{empty_streak}/{EMPTY_STREAK_LIMIT} (offset={offset})")
            if empty_streak >= EMPTY_STREAK_LIMIT:
                logger.info(f"[Adobe] Stopping after {EMPTY_STREAK_LIMIT} consecutive empty pages.")
                break
        else:
            empty_streak = 0
            collected.extend(page_jobs)
            logger.info(f"[Adobe] Page {page + 1}: +{len(page_jobs)} jobs, total={len(collected)}")

        offset += PAGE_SIZE
        page += 1
        await asyncio.sleep(random.uniform(1, 4))  

    logger.info(f"🎉 [Adobe] Collected total {len(collected)} jobs in {label}")
    unique_ids = len({j.job_id for j in collected})
    logger.info(f"[Adobe Debug] Total={len(collected)}, Unique IDs={unique_ids}, Duplicates={len(collected) - unique_ids}")
    return ScrapeResult(
        jobs=collected,
        scrape_id=label,
        anomalous_zero=(len(collected) == 0),
        should_persist=True,
        decision_reason="ok" if collected else "empty_result",
        stats={"default_count": len(collected)},
        meta={"filters": FILTERS},
    )


async def get_jobs(min_expected_count: int = 10) -> ScrapeResult:
    company = get_company()
    logger.info("🔍 Starting scraper for Adobe...")

    first = await _run_once("first-pass", min_expected_count=min_expected_count)

    decided = await retry_and_decide(
        company=company,
        logger=logger,
        first_result=first,
        retry_fn=lambda: _run_once("retry", min_expected_count),
        min_expected_count=min_expected_count,
        should_persist_fn=should_persist_jobs,
    )

    return decided
