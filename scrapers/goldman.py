import asyncio
import random
import re
from typing import Any, Dict, List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from core.fetcher import post_json  # your existing resilient POST
from core.logger import get_company_logger
from models.goldman_job import GoldmanJob

logger = get_company_logger()

API_URL = "https://api-higher.gs.com/gateway/api/v1/graphql"
ROLES_BASE = "https://higher.gs.com/roles/"
CAREERS_BASE = "https://higher.gs.com/"

_num_prefix = re.compile(r"^\s*(\d+)")

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
]

# We can request both tracks; if you prefer to split, run two passes like Microsoft.
EXPERIENCES = ["EARLY_CAREER", "PROFESSIONAL"]

# Basic failsafes
PAGE_SIZE = 20
EMPTY_STREAK_LIMIT = 3
MAX_PAGES = 500


def _headers() -> Dict[str, str]:
    return {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": "https://higher.gs.com",
        "Referer": "https://higher.gs.com/",
        "User-Agent": random.choice(USER_AGENTS),
        # (Their DevTools also showed Datadog headers; not required for this public query)
    }


# Keep the GraphQL selection minimal-but-useful; add fields as needed
GQL_QUERY = """
query GetRoles($searchQueryInput: RoleSearchQueryInput!) {
  roleSearch(searchQueryInput: $searchQueryInput) {
    totalCount
    items {
      roleId
      corporateTitle
      jobTitle
      jobFunction
      locations {
        primary
        state
        country
        city
        __typename
      }
      status
      division
      skills
      jobType {
        code
        description
        __typename
      }
      
      externalSource { sourceId __typename }
      
      __typename
    }
    __typename
  }
}
""".strip()

# Your captured filters, lifted verbatim (you can move this to config if you want)
GS_FILTERS = [
    {
        "filterCategoryType": "EXPERIENCE_LEVEL",
        "filters": [
            {"filter": "Analyst", "subFilters": []},
            {"filter": "Associate", "subFilters": []},
        ],
    },
    {
        "filterCategoryType": "JOB_FUNCTION",
        "filters": [{"filter": "Software Engineering", "subFilters": []}],
    },
    {
        "filterCategoryType": "LOCATION",
        "filters": [
            {
                "filter": "United States",
                "subFilters": [
                    {"filter": "California", "subFilters": [
                        {"filter": "Los Angeles", "subFilters": []},
                        {"filter": "San Francisco", "subFilters": []}
                    ]},
                    {"filter": "Delaware", "subFilters": [{"filter": "Wilmington", "subFilters": []}]},
                    {"filter": "District of Columbia", "subFilters": [{"filter": "Washington", "subFilters": []}]},
                    {"filter": "Florida", "subFilters": [{"filter": "West Palm Beach", "subFilters": []}]},
                    {"filter": "Georgia", "subFilters": [{"filter": "Atlanta", "subFilters": []}]},
                    {"filter": "Illinois", "subFilters": [{"filter": "Chicago", "subFilters": []}]},
                    {"filter": "Massachusetts", "subFilters": [{"filter": "Boston", "subFilters": []}]},
                    {"filter": "New Jersey", "subFilters": [{"filter": "Jersey City", "subFilters": []}]},
                    {"filter": "New York", "subFilters": [
                        {"filter": "Albany", "subFilters": []},
                        {"filter": "New York", "subFilters": []}
                    ]},
                    {"filter": "Pennsylvania", "subFilters": [{"filter": "Philadelphia", "subFilters": []}]},
                    {"filter": "Texas", "subFilters": [
                        {"filter": "Dallas", "subFilters": []},
                        {"filter": "Houston", "subFilters": []},
                        {"filter": "Irving", "subFilters": []},
                        {"filter": "Richardson", "subFilters": []}
                    ]},
                    {"filter": "Utah", "subFilters": [
                        {"filter": "Draper", "subFilters": []},
                        {"filter": "Salt Lake City", "subFilters": []}
                    ]},
                ],
            }
        ],
    },
]



def _payload(page_number: int, experiences: List[str]) -> Dict[str, Any]:
    return {
        "operationName": "GetRoles",
        "query": GQL_QUERY,
        "variables": {
            "searchQueryInput": {
                "page": {"pageSize": PAGE_SIZE, "pageNumber": page_number},
                "sort": {"sortStrategy": "POSTED_DATE", "sortOrder": "DESC"},
                "filters": GS_FILTERS,
                "experiences": experiences,   # ["EARLY_CAREER","PROFESSIONAL"]
                "searchTerm": "",
            }
        },
    }

def _extract_numeric_from_role_id(role_id: str) -> Optional[str]:
    """
    roleId examples:
      - '153361_GS_MID_CAREER'  -> '153361'
      - 'b1918ab1-85f8-412c-8176-5630ff818805' -> None
    """
    if not role_id:
        return None
    m = _num_prefix.match(role_id)
    return m.group(1) if m else None

def _goldman_job_url(role_id: str, source_id: str) -> str:
    # Prefer the canonical /roles/<sourceId> when available
    if source_id:
        return f"{ROLES_BASE}{source_id}"
    # If no sourceId but roleId starts with digits, try that
    rid_num = _extract_numeric_from_role_id(role_id)
    if rid_num:
        return f"{ROLES_BASE}{rid_num}"
    
    # Last resort: send to the career wesbite
    return CAREERS_BASE

def _fmt_primary_location(locs: list[dict]) -> str:
    if not locs:
        return "N/A"
    prim = next((l for l in locs if l.get("primary")), None) or locs[0]
    return ", ".join([x for x in [prim.get("city"), prim.get("state"), prim.get("country")] if x])

def _normalize_item(it: dict) -> GoldmanJob:
    role_id = it.get("roleId") or ""
    ext_src = (it.get("externalSource") or {}).get("sourceId") or ""
    job_id = ext_src or role_id

    # populate current EST time as date_posted
    est_now = datetime.now(ZoneInfo("America/New_York")).strftime("%b %d, %Y %I:%M %p %Z")

    jt = it.get("jobType") or {}
    jt_code = jt.get("code", "") if jt else ""
    jt_desc = jt.get("description", "") if jt else ""

    locations = it.get("locations") or []
    location_str = _fmt_primary_location(locations)

    return GoldmanJob(
        job_id=job_id,
        title=it.get("jobTitle") or "Unknown",
        url=_goldman_job_url(role_id, ext_src),
        location=location_str,
        date_posted=est_now,
        role_id=role_id,
        external_source_id=ext_src,
        corporate_title=it.get("corporateTitle") or "",
        division=it.get("division") or "",
        job_function=it.get("jobFunction") or "",
        job_type_code=jt_code,
        job_type_desc=jt_desc,
        status=it.get("status") or "",
        locations=locations,
        skills=it.get("skills") or [],
    )


async def get_jobs() -> List[GoldmanJob]:
    jobs: List[GoldmanJob] = []
    seen: set[str] = set()

    await asyncio.sleep(random.uniform(0, 10))
    logger.info("Entered Goldman get_jobs()")

    page = 0
    empty_streak = 0
    last_sig: Optional[tuple] = None

    while page < MAX_PAGES:
        headers = _headers()
        payload = _payload(page, EXPERIENCES)

        data = await post_json(API_URL, payload, headers)
        if not data:
            empty_streak += 1
            logger.info(f"[Goldman] Empty/None payload on page {page}; streak {empty_streak}/{EMPTY_STREAK_LIMIT}")
            if empty_streak >= EMPTY_STREAK_LIMIT:
                break
            page += 1
            await asyncio.sleep(random.uniform(1, 3))
            continue

        # GraphQL shape: { "data": { "roleSearch": { "totalCount": N, "items": [...] } } }
        # ...inside the loop after fetching data...
        try:
            rs = data.get("data", {}).get("roleSearch", {}) if isinstance(data, dict) else {}
            items = rs.get("items") or []
            total_count = rs.get("totalCount")
        except Exception:
            items = []
            total_count = None

        ids = [
            (it.get("externalSource") or {}).get("sourceId") or (it.get("roleId") or "")
            for it in items
        ]
        sig = tuple(ids[:5] + ids[-5:]) if ids else tuple()

        new_count = 0
        for it in items:
            j = _normalize_item(it)
            key = j.job_id or j.role_id
            if key and key not in seen:
                seen.add(key)
                jobs.append(j)
                new_count += 1

        no_progress = (len(items) == 0) or (sig == last_sig) or (new_count == 0)
        if no_progress:
            empty_streak += 1
            logger.info(
                f"[Goldman] No progress on page {page} (raw={len(items)}, new={new_count}, repeat={sig == last_sig}); "
                f"streak {empty_streak}/{EMPTY_STREAK_LIMIT}"
            )
        else:
            empty_streak = 0

        last_sig = sig

        if empty_streak >= EMPTY_STREAK_LIMIT:
            logger.info(f"[Goldman] Stopping after {EMPTY_STREAK_LIMIT} consecutive no-progress pages.")
            break

        logger.info(f"[Goldman] Page {page}: +{new_count} new, total {len(jobs)} (server totalCount={total_count})")

        page += 1
        await asyncio.sleep(random.uniform(1, 3))


    logger.info(f"🎉 [Goldman] Found total: {len(jobs)} jobs")
    return jobs
