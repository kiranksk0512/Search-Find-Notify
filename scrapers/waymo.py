from __future__ import annotations

import os
import re
import uuid
import random
import asyncio
import urllib.parse
from typing import Dict, List, Optional, Tuple

import aiohttp

from bs4 import BeautifulSoup

from core.logger import get_company_logger
from core.context import get_company
from core.scrape_types import ScrapeResult
from core.decision import retry_and_decide

from models.waymo_job import WaymoJob

try:
    import config as cfg
except Exception:  # pragma: no cover
    cfg = None

logger = get_company_logger()

BASE_URL = "https://careers.withwaymo.com"
SEARCH_URL = f"{BASE_URL}/jobs/search"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
]

DEFAULT_DEPARTMENT_UIDS = [
    "9edee38059d1b1ce766fe8312f3bc75e",  # AI Foundations
    "27559cce86bb746cf94bca8135c8f504",  # Design
    "2594747f04246632f591a5d6a2bdeaa5",  # Engineering Operations
    "8600dd97165768a9d0300ef597a01f3d",  # Product
    "451e57010e816b71a8312792faf5740f",  # Software Engineering
    "fdbec1fdc0be4cd648517ace2b6b0a45",  # Systems Engineering
]

# These are layout/version identifiers used by Waymo's careers site.
# If they rotate, set WAYMO_SEARCH_PARAMS_JSON in env to override.
DEFAULT_FIXED_PARAMS: Dict[str, str] = {
    "block_uid": "2ddfa6933a2443a69f97b24d1d165a22",
    "block_index": "0",
    "page_row_uid": "71208e73b81e8bf96151da4f51268c9a",
    "page_row_index": "1",
    "page_version_uid": "46864c8d67c81d288123cd150b3b6972",
}


def _parse_cookie_string(cookie_str: str) -> Optional[Dict[str, str]]:
    cookie_str = (cookie_str or "").strip()
    if not cookie_str:
        return None
    out: Dict[str, str] = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out or None


def _get_headers() -> Dict[str, str]:
    return {
        # Waymo expects Turbo Stream responses here; using a broader Accept
        # (including text/html) often yields 202 + empty body.
        "accept": "text/vnd.turbo-stream.html",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": f"{SEARCH_URL}?page=1",
        "user-agent": random.choice(USER_AGENTS),
    }


def _job_id_from_url(url: str) -> str:
    try:
        path = urllib.parse.urlparse(url).path
        if "/jobs/" in path:
            slug = path.split("/jobs/", 1)[1].strip("/").strip()
            return slug or url
        return url
    except Exception:
        return url


def _unwrap_turbo_stream_template(html: str) -> str:
    """Waymo returns Turbo Stream HTML with the real DOM inside <template>.

    Many HTML parsers treat <template> contents specially; unwrap to ensure we can CSS-select
    the job cards reliably.
    """
    soup = BeautifulSoup(html or "", "lxml")
    templates = soup.find_all("template")
    if not templates:
        return html or ""
    return "\n".join(t.decode_contents() for t in templates)


def _looks_blocked(text: str) -> bool:
    if not text:
        return True
    # Heuristics for WAF/blocked/captcha pages.
    needles = [
        "aws-waf-token",
        "Request blocked",
        "Access denied",
        "captcha",
        "CloudFront",
        "403 Forbidden",
    ]
    lower = text.lower()
    return any(n.lower() in lower for n in needles)


def _retryable_status(status: Optional[int]) -> bool:
    return status == 429 or (status is not None and 500 <= status < 600)


async def _get_text_with_status(
    url: str,
    *,
    headers: Dict[str, str],
    cookies: Optional[Dict[str, str]],
    base_timeout_s: int,
) -> Tuple[Optional[int], str, Dict[str, str]]:
    timeout = aiohttp.ClientTimeout(total=base_timeout_s)
    async with aiohttp.ClientSession(cookies=cookies, timeout=timeout) as session:
        async with session.get(url, headers=headers) as resp:
            txt = await resp.text()
            return resp.status, txt or "", {k.lower(): v for k, v in resp.headers.items()}


def _parse_jobs_from_turbo_stream(html: str) -> List[WaymoJob]:
    inner = _unwrap_turbo_stream_template(html)
    soup = BeautifulSoup(inner, "lxml")

    jobs: List[WaymoJob] = []
    for article in soup.select("article.job-search-results-card-col"):
        a = article.select_one("h3 a[href*='/jobs/']")
        if not a:
            continue

        title = a.get_text(" ", strip=True) or "Unknown"
        href = a.get("href", "")
        if not href:
            continue
        url = urllib.parse.urljoin(BASE_URL, href)
        job_id = _job_id_from_url(url)

        locations = [
            s.get_text(" ", strip=True)
            for s in article.select(".job-component-list-location span")
        ]
        locations = [l for l in locations if l]
        location = ", ".join(dict.fromkeys(locations)) if locations else "Unknown"

        dept = article.select_one(".job-component-list-department span")
        department = dept.get_text(" ", strip=True) if dept else "Unknown"

        emp = article.select_one(".job-component-list-employment_type span")
        employment_type = emp.get_text(" ", strip=True) if emp else "Unknown"

        jobs.append(
            WaymoJob(
                job_id=job_id,
                title=title,
                url=url,
                location=location,
                team=department,
                sub_teams=employment_type,
                date_posted=None,
            )
        )

    return jobs


def _extract_next_url(html: str) -> Optional[str]:
    inner = _unwrap_turbo_stream_template(html)
    soup = BeautifulSoup(inner, "lxml")
    a = soup.select_one("nav.pagination a[rel='next']")
    if not a:
        # Some pages use "Next" link at bottom.
        a = soup.find("a", attrs={"rel": "next"})
    if not a:
        return None
    href = a.get("href", "")
    if not href:
        return None
    return urllib.parse.urljoin(BASE_URL, href)


def should_persist_jobs(result: ScrapeResult, min_expected_count: int) -> Tuple[bool, str]:
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


async def _fetch_all_pages(*, start_url: str, cookies: Optional[Dict[str, str]], max_pages: int) -> Tuple[List[WaymoJob], int]:
    company = get_company()

    url = start_url
    pages = 0
    all_jobs: Dict[str, WaymoJob] = {}

    while url and pages < max_pages:
        pages += 1
        await asyncio.sleep(random.uniform(0.2, 1.2))  # jitter

        headers = _get_headers()
        status = None
        text = ""
        resp_headers: Dict[str, str] = {}

        # Retry loop (Waymo sometimes returns 429/5xx; WAF returns 202 + challenge)
        for attempt in range(1, 4):
            try:
                status, text, resp_headers = await _get_text_with_status(
                    url,
                    headers=headers,
                    cookies=cookies,
                    base_timeout_s=20,
                )
            except Exception as e:
                logger.warning(f"[company={company}] ⚠️ Waymo request exception (page={pages} attempt={attempt}): {e}")
                status, text, resp_headers = None, "", {}

            # WAF: 202 with explicit challenge header, usually empty body
            if status == 202 and resp_headers.get("x-amzn-waf-action", "").lower() == "challenge":
                logger.warning(
                    f"[company={company}] 🛡️ AWS WAF challenge (HTTP 202) from Waymo. "
                    "Set WAYMO_COOKIES (include aws-waf-token) to proceed."
                )
                # Keep what we've collected so far; just stop paging.
                url = None
                break

            if status == 200 and text and not _looks_blocked(text):
                break

            if _retryable_status(status) and attempt < 3:
                sleep_s = random.uniform(1.0, 2.5) * attempt
                logger.warning(
                    f"[company={company}] 🔁 Retryable status={status} (page={pages} attempt={attempt}); sleeping {sleep_s:.1f}s"
                )
                await asyncio.sleep(sleep_s)
                continue

            # Non-retryable / still empty
            snippet = (text[:200].replace("\n", " ") if text else "<empty>")
            logger.warning(
                f"[company={company}] ⚠️ Waymo page fetch failed (status={status} page={pages}) body={snippet}"
            )
            # If we already have some jobs, keep them and stop paging; otherwise fail empty.
            if all_jobs:
                url = None
                break
            return [], pages

        jobs = _parse_jobs_from_turbo_stream(text)
        logger.info(f"[company={company}] 🧩 Waymo parsed {len(jobs)} jobs (page={pages}).")

        for j in jobs:
            all_jobs[j.job_id] = j

        next_url = _extract_next_url(text)
        if not next_url:
            break
        url = next_url

    return list(all_jobs.values()), pages


def _build_start_url() -> str:
    """Construct initial search URL.

    Supports override via WAYMO_SEARCH_URL (full URL) for quick fixes when Waymo rotates params.
    """
    override = os.getenv("WAYMO_SEARCH_URL", "").strip() or (getattr(cfg, "WAYMO_SEARCH_URL", "") if cfg else "")
    if override:
        return override

    dept_env = os.getenv("WAYMO_DEPARTMENT_UIDS", "").strip() or (getattr(cfg, "WAYMO_DEPARTMENT_UIDS", "") if cfg else "")
    if dept_env:
        department_uids = [d.strip() for d in dept_env.split(",") if d.strip()]
    else:
        department_uids = DEFAULT_DEPARTMENT_UIDS

    country_env = os.getenv("WAYMO_COUNTRY_CODES", "US").strip() or (getattr(cfg, "WAYMO_COUNTRY_CODES", "US") if cfg else "US")
    country_codes = [c.strip() for c in country_env.split(",") if c.strip()] or ["US"]

    query = os.getenv("WAYMO_QUERY", "").strip() or (getattr(cfg, "WAYMO_QUERY", "") if cfg else "")

    params: List[Tuple[str, str]] = []
    params.extend(list(DEFAULT_FIXED_PARAMS.items()))
    params.append(("page", "1"))
    params.append(("location_uids", ""))
    params.append(("sort", ""))
    params.append(("search_departments", ""))

    for d in department_uids:
        params.append(("department_uids[]", d))

    params.append(("search_employment_types", ""))
    params.append(("search_country_codes", ""))

    for cc in country_codes:
        params.append(("country_codes[]", cc))

    params.append(("search_states", ""))
    params.append(("search_cities", ""))
    params.append(("search_dropdown_field_1_values", ""))
    params.append(("query", query))

    return f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"


async def get_jobs(min_expected_count: int = 40) -> ScrapeResult:
    """Scrape Waymo jobs from careers.withwaymo.com.

    This endpoint commonly returns Turbo Stream HTML. We parse job cards and paginate via rel=next.

    Env knobs:
      - WAYMO_COOKIES: cookie string copied from browser (optional, for WAF)
      - WAYMO_SEARCH_URL: full override URL (optional)
      - WAYMO_DEPARTMENT_UIDS: comma-separated uid list (optional)
      - WAYMO_COUNTRY_CODES: comma-separated country codes (default: US)
      - WAYMO_QUERY: search query string (default: empty)
      - WAYMO_MAX_PAGES: max pages to follow (default: 20)
      - WAYMO_MIN_EXPECTED_COUNT: overrides min_expected_count
    """
    company = get_company()

    min_expected = int(os.getenv("WAYMO_MIN_EXPECTED_COUNT", str(getattr(cfg, "WAYMO_MIN_EXPECTED_COUNT", min_expected_count) if cfg else min_expected_count)))
    max_pages = int(os.getenv("WAYMO_MAX_PAGES", str(getattr(cfg, "WAYMO_MAX_PAGES", 20) if cfg else 20)))

    cookie_src = os.getenv("WAYMO_COOKIES", "")
    if not cookie_src and cfg is not None:
        cookie_src = getattr(cfg, "WAYMO_COOKIES", "")
    cookies = _parse_cookie_string(cookie_src)

    async def _scrape_once(label: str) -> ScrapeResult:
        scrape_id = str(uuid.uuid4())[:8]
        start_url = _build_start_url()
        logger.info(f"[company={company}] [{scrape_id}] 🚀 Waymo scrape start ({label}) url={start_url.split('?')[0]}")

        jobs, pages = await _fetch_all_pages(start_url=start_url, cookies=cookies, max_pages=max_pages)
        anomalous_zero = (len(jobs) == 0)

        return ScrapeResult(
            jobs=jobs,
            scrape_id=scrape_id,
            anomalous_zero=anomalous_zero,
            stats={"pages": pages, "count": len(jobs)},
            meta={"source": "careers.withwaymo.com", "start_url": start_url},
        )

    first = await _scrape_once("first-pass")

    decided = await retry_and_decide(
        company=company,
        logger=logger,
        first_result=first,
        retry_fn=lambda: _scrape_once("retry"),
        min_expected_count=min_expected,
        should_persist_fn=should_persist_jobs,
    )

    return decided
