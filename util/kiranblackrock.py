# scrapers/kiranblackrock.py
import asyncio
from typing import Any, List, Optional, Dict, Tuple
from urllib.parse import urljoin
import json
import re

import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo

from core.logger import get_company_logger
from models.kiranblackrock_job import KiranBlackRockJob

logger = get_company_logger()

SITE_ROOT = "https://careers.blackrock.com"
RESULTS_URL = f"{SITE_ROOT}/search-jobs/results"

HEADERS = {
    "accept": "*/*",
    "x-requested-with": "XMLHttpRequest",
    "user-agent": "Mozilla/5.0",
}

BASE_QUERY: Dict[str, Any] = {
    "ActiveFacetID": "Engineering",
    "CurrentPage": 1,
    "RecordsPerPage": 10,            # pull more per call than the 10 in the curl
    "Distance": 50,
    "RadiusUnitType": 0,
    "Keywords": "",
    "Location": "United States",
    "Latitude": 39.76000,
    "Longitude": -98.50000,
    "ShowRadius": "False",
    "IsPagination": "False",
    "SortCriteria": 1,
    "SortDirection": 0,
    "SearchType": 1,
    "LocationType": 2,
    "LocationPath": 6252001,         # US path
    "OrganizationIds": 45831,        # BlackRock org
    "ResultsType": 0,
    # FacetFilters[] replicated from your capture:
    "FacetFilters[0].ID": 6252001,
    "FacetFilters[0].FacetType": 2,
    "FacetFilters[0].Count": 22,
    "FacetFilters[0].Display": "United States",
    "FacetFilters[0].IsApplied": "true",
    "FacetFilters[0].FieldName": "",
    "FacetFilters[1].ID": "Engineering",
    "FacetFilters[1].FacetType": 5,
    "FacetFilters[1].Count": 25,
    "FacetFilters[1].Display": "Engineering",
    "FacetFilters[1].IsApplied": "true",
    "FacetFilters[1].FieldName": "custom_fields.MainTeam",
    "FacetFilters[2].ID": "Product",
    "FacetFilters[2].FacetType": 5,
    "FacetFilters[2].Count": 13,
    "FacetFilters[2].Display": "Product",
    "FacetFilters[2].IsApplied": "true",
    "FacetFilters[2].FieldName": "custom_fields.MainTeam",
    "FacetFilters[3].ID": "Technology",
    "FacetFilters[3].FacetType": 5,
    "FacetFilters[3].Count": 9,
    "FacetFilters[3].Display": "Technology",
    "FacetFilters[3].IsApplied": "true",
    "FacetFilters[3].FieldName": "custom_fields.MainTeam",
    "SearchResultsModuleName": "Section 3 - Search Results",
    "SearchFiltersModuleName": "Section 3 - Search Filters",
}
def _normalize_params(d: Dict[str, Any]) -> Dict[str, str | int | float]:
    out: Dict[str, str | int | float] = {}
    for k, v in d.items():
        if isinstance(v, bool):
            out[k] = "true" if v else "false"
        elif isinstance(v, (str, int, float)):
            out[k] = v
        else:
            out[k] = str(v)
    return out

async def _fetch_page_text(page: int) -> Optional[Tuple[str, str]]:
    """Return (body, url) as text. Handles only GET of the 'results' partial."""
    params = _normalize_params({**BASE_QUERY, "CurrentPage": page})
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(RESULTS_URL, headers=HEADERS, params=params) as resp:
                body = await resp.text()
                if resp.status != 200:
                    logger.warning(f"[kiranblackrock] GET {resp.url} -> {resp.status}; body_snip={body[:200]}")
                    return None
                return body, str(resp.url)
    except Exception as e:
        logger.error(f"[kiranblackrock] exception fetching page={page}: {e}")
        return None

def _maybe_extract_html_from_json(body: str) -> Optional[str]:
    """
    Some deployments return JSON that contains the HTML for the results.
    We try to parse JSON and extract the largest HTML-looking string.
    """
    # Quick path: if it doesn't look like JSON, bail
    maybe_json = body.strip()
    if not (maybe_json.startswith("{") or maybe_json.startswith("[")):
        return None
    try:
        data = json.loads(maybe_json)
    except Exception:
        return None

    # Walk strings and pick the one containing our UL marker
    candidate_html = None
    marker = 'section3__search-results-ul'

    def walk(obj):
        nonlocal candidate_html
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
        elif isinstance(obj, str):
            if marker in obj and (candidate_html is None or len(obj) > len(candidate_html)):
                candidate_html = obj

    walk(data)
    return candidate_html

def _extract_total_pages_from_html(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    # Prefer explicit max on the page input if present
    input_max = soup.select_one("#pagination-current-bottom")
    if input_max and input_max.has_attr("max"):
        try:
            return max(1, int(input_max["max"]))
        except Exception:
            pass
    # Fallback: parse "/ N"
    total_span = soup.select_one(".pagination-total-pages")
    if total_span:
        txt = total_span.get_text(strip=True)
        m = re.search(r"/\s*(\d+)", txt)
        if m:
            try:
                return max(1, int(m.group(1)))
            except Exception:
                pass
    return 1

def _parse_jobs_from_html(html: str) -> List[KiranBlackRockJob]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[KiranBlackRockJob] = []

    for li in soup.select("ul.section3__search-results-ul > li.section3__search-results-li"):
        a = li.select_one("a.section3__search-results-a")
        # job_id primary + fallback (button)
        jid = (a.get("data-job-id").strip() if a and a.has_attr("data-job-id") else "") if a else ""
        if not jid:
            btn = li.select_one("button.js-save-job-btn[data-job-id]")
            if btn:
                jid = (btn.get("data-job-id") or "").strip()
        if not jid:
            continue

        href = a.get("href") if a else ""
        url = urljoin(SITE_ROOT, href or "")
        title_el = a.select_one("h2.section3__job-title") if a else None
        title = title_el.get_text(strip=True) if title_el else "Unknown"

        # merge primary + additional locations (dedup)
        locs: List[str] = []
        for block in li.select(".job-location"):
            info = block.select_one(".section3__job-info")
            if info:
                txt = info.get_text(strip=True)
                if txt and txt not in locs:
                    locs.append(txt)
        location = ", ".join(locs) if locs else "Unknown"

        team_info = li.select_one(".job-category .section3__job-info")
        team = team_info.get_text(strip=True) if team_info else "Unknown"

        posted = datetime.now(ZoneInfo("America/New_York")).strftime("%b %d, %Y %I:%M %p %Z")

        out.append(
            KiranBlackRockJob(
                job_id=jid,
                title=title,
                url=url,
                location=location,
                team=team,
                category=team,
                date_posted=posted,
            )
        )

    return out

async def get_jobs(min_expected_count: int = 2):
    page = 1
    all_jobs: List[KiranBlackRockJob] = []
    seen = set()
    total_pages = None

    while True:
        fetched = await _fetch_page_text(page)
        if not fetched:
            break

        body, req_url = fetched

        # On page 1, log a short diagnostic so we can see the shape
        if page == 1:
            preview = body[:300].replace("\n", "\\n")
            logger.info(f"[kiranblackrock] debug page1 url={req_url} body_snip={preview}")

        # If JSON-wrapped, extract the HTML; else use body as HTML
        html = _maybe_extract_html_from_json(body) or body

        if total_pages is None:
            total_pages = _extract_total_pages_from_html(html)

        parsed = _parse_jobs_from_html(html)
        new = [j for j in parsed if j.job_id not in seen]
        for j in new:
            seen.add(j.job_id)
        all_jobs.extend(new)

        logger.info(f"[kiranblackrock] page={page} added={len(new)} total={len(all_jobs)} (of ~{total_pages or '?'})")

        if (total_pages and page >= total_pages) or not parsed:
            break

        page += 1
        await asyncio.sleep(0.5)

    if len(all_jobs) == 0:
        return {"jobs": [], "should_persist": False, "decision_reason": "zero_jobs",
                "default_count": 0, "new_count": 0}

    if len(all_jobs) < min_expected_count:
        return {"jobs": all_jobs, "should_persist": False,
                "decision_reason": f"too_few({len(all_jobs)}<{min_expected_count})",
                "default_count": len(all_jobs), "new_count": 0}

    return {"jobs": all_jobs, "should_persist": True, "decision_reason": "ok",
            "default_count": len(all_jobs), "new_count": 0}
