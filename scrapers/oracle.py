# oracle.py

import asyncio
import random
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, quote  # 🔹 for full URL logging

from core.fetcher import get_json          # resilient async GET (you already have this)
from core.logger import get_company_logger
from models.oracle_job import OracleJob    # your existing dataclass/pydantic model

try:
    from util.oracle_categories_helper import resolve_category_ids  # sync helper you tested
except Exception:
    resolve_category_ids = None  # keep scraper functional if helper isn't available

logger = get_company_logger()

API_URL = "https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"

# Chrome/Safari rotations to keep things looking real
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
]

# Paging
PAGE_SIZE_FILTERED = 14        # When any facet filters are active (CATEGORIES / FLEX / LOCATIONS)
PAGE_SIZE_SITE_ONLY = 100      # 🔹 Larger page size for site-only
EMPTY_STREAK_LIMIT = 3
MAX_PAGES = 600

# Facet constants
FACETS_ALL = "LOCATIONS;WORK_LOCATIONS;WORKPLACE_TYPES;TITLES;CATEGORIES;ORGANIZATIONS;POSTING_DATES;FLEX_FIELDS"
US_LOCATION_ID = "300000000149325"  # USA (site's "United States" location facet)
YEARS_FLEX_RAW = '"AttributeChar6|See Job Description;0 to 2+ years"'

CATEGORY_NAMES = [
    "Product Development",
    "Information Technology",
    "Consulting",
]

# Expand list from DevTools
EXPAND = ",".join([
    "requisitionList.workLocation",
    "requisitionList.otherWorkLocations",
    "requisitionList.secondaryLocations",
    "flexFieldsFacet.values",
    "requisitionList.requisitionFlexFields",
])


def _headers() -> Dict[str, str]:
    return {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://careers.oracle.com",
        "Referer": "https://careers.oracle.com/",
        "User-Agent": random.choice(USER_AGENTS),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def _finder_filtered(*,
                     last_selected: str,
                     include_location: bool,
                     include_years: bool,
                     category_ids: Optional[List[str]],
                     limit: int,
                     offset: int) -> str:
    """
    Build a 'findReqs;...' string with limit/offset INSIDE the finder (finder-paging),
    which is required when using CATEGORIES/FLEX_FIELDS etc.
    """
    parts = [
        f"findReqs;siteNumber=CX_45001",
        f"facetsList={FACETS_ALL}",
        f"lastSelectedFacet={last_selected}",
    ]
    if include_location:
        parts.append(f"selectedLocationsFacet={US_LOCATION_ID}")
    if category_ids:
        parts.append("selectedCategoriesFacet=" + ";".join(category_ids))  # ;-separated
    if include_years:
        parts.append(f"selectedFlexFieldsFacets={YEARS_FLEX_RAW}")
    parts.append("sortBy=POSTING_DATES_DESC")
    parts.append(f"limit={limit}")
    parts.append(f"offset={offset}")
    return ",".join(parts)


def _params_filtered(last_selected: str,
                     page_index: int,
                     page_size: int,
                     *,
                     use_location: bool,
                     use_years: bool,
                     category_ids: Optional[List[str]]) -> Dict[str, Any]:
    finder = _finder_filtered(
        last_selected=last_selected,
        include_location=use_location,
        include_years=use_years,
        category_ids=category_ids,
        limit=page_size,
        offset=page_index * page_size,
    )
    return {"onlyData": "true", "expand": EXPAND, "finder": finder}


def _params_site_only(page_index: int, page_size: int) -> Dict[str, Any]:
    # Site-only can safely use a larger page size
    finder = ",".join([
        "findReqs;siteNumber=CX_45001",
        f"facetsList={FACETS_ALL}",
        "lastSelectedFacet=LOCATIONS",
        "sortBy=POSTING_DATES_DESC",
        f"limit={page_size}",
        f"offset={page_index * page_size}",
    ])
    return {"onlyData": "true", "expand": EXPAND, "finder": finder}


def _oracle_job_url(req_id: str) -> str:
    return f"https://careers.oracle.com/en/sites/jobsearch/job/{req_id}/" if req_id else "https://careers.oracle.com/"


def _to_est(date_str: Optional[str]) -> str:
    if not date_str:
        return datetime.now(ZoneInfo("America/New_York")).strftime("%b %d, %Y %I:%M %p %Z")
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(ZoneInfo("America/New_York")).strftime("%b %d, %Y %I:%M %p %Z")
    except Exception:
        return datetime.now(ZoneInfo("America/New_York")).strftime("%b %d, %Y %I:%M %p %Z")


def _normalize_requisition(req: Dict[str, Any]) -> OracleJob:
    job_id = str(req.get("Id") or "")
    title = req.get("Title") or "Unknown"
    location = req.get("PrimaryLocation") or req.get("PrimaryLocationCountry") or "USA"
    posted_date = _to_est(req.get("PostedDate"))

    return OracleJob(
        job_id=job_id,
        title=title,
        url=_oracle_job_url(job_id),
        location=location,
        date_posted=posted_date,

        # rich extras from ORC
        language=req.get("Language") or "",
        geography_id=req.get("GeographyId"),
        workplace_type=req.get("WorkplaceType") or "",
        workplace_type_code=req.get("WorkplaceTypeCode") or "",
        hot_job=bool(req.get("HotJobFlag", False)),
        trending_flag=bool(req.get("TrendingFlag", False)),
        be_first_to_apply_flag=bool(req.get("BeFirstToApplyFlag", False)),
        short_description=req.get("ShortDescriptionStr") or "",
        primary_location=req.get("PrimaryLocation"),
        secondary_locations=req.get("secondaryLocations") or [],
        other_work_locations=req.get("otherWorkLocations") or [],
        work_location=req.get("workLocation") or [],
        requisition_flex_fields=req.get("requisitionFlexFields") or [],

        business_unit=req.get("BusinessUnit"),
        contract_type=req.get("ContractType"),
        department=req.get("Department"),
        external_qualifications=req.get("ExternalQualificationsStr"),
        external_responsibilities=req.get("ExternalResponsibilitiesStr"),
        job_family=req.get("JobFamily"),
        job_function=req.get("JobFunction"),
        job_schedule=req.get("JobSchedule"),
        job_shift=req.get("JobShift"),
        job_type=req.get("JobType"),
        legal_employer=req.get("LegalEmployer"),
        manager_level=req.get("ManagerLevel"),
        posting_end_date=req.get("PostingEndDate"),
        study_level=req.get("StudyLevel"),
        worker_type=req.get("WorkerType"),
    )


def _extract_reqs(payload: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Optional[int]]:
    items = payload.get("items") or []
    first = items[0] if items and isinstance(items[0], dict) else {}
    return (first.get("requisitionList") or []), first.get("TotalJobsCount")


# 🔹 Helper to log the fully prepared, encoded URL (once per mode)
def _full_url(params: Dict[str, Any]) -> str:
    # Proper percent-encoding for commas/semicolons etc.
    return f"{API_URL}?{urlencode(params, doseq=True, quote_via=quote)}"


async def _page_through(mode_name: str,
                        build_params,
                        page_size: int,
                        *,
                        max_pages: int = MAX_PAGES) -> List[OracleJob]:
    """
    Paginate using the given param builder (which already embeds finder-paging or site-only).
    Stops after EMPTY_STREAK_LIMIT no-progress pages.
    """
    jobs: List[OracleJob] = []
    seen: set[str] = set()
    empty_streak = 0
    last_sig: Optional[tuple] = None
    server_total: Optional[int] = None

    page = 0
    while page < max_pages:
        params = build_params(page)

        # 🔹 Log the fully prepared URL on first page of each mode
        if page == 0:
            logger.info(f"[Oracle] URL ({mode_name}): {_full_url(params)}")

        logger.debug(f"[Oracle] ({mode_name}) GET {API_URL} params={params}")
        data = await get_json(API_URL, headers=_headers(), params=params)

        if not data or not isinstance(data, dict):
            empty_streak += 1
            logger.info(f"[{mode_name}] empty payload page={page}; streak {empty_streak}/{EMPTY_STREAK_LIMIT}")
            if empty_streak >= EMPTY_STREAK_LIMIT:
                logger.info(f"[{mode_name}] stopping after {EMPTY_STREAK_LIMIT} empty pages.")
                break
            page += 1
            await asyncio.sleep(random.uniform(0.8, 1.6))
            continue

        reqs, total = _extract_reqs(data)
        if server_total is None and total is not None:
            server_total = total

        ids = [str(r.get("Id") or "") for r in reqs]
        sig = tuple(ids[:5] + ids[-5:]) if ids else tuple()

        new_count = 0
        for r in reqs:
            j = _normalize_requisition(r)
            if j.job_id and j.job_id not in seen:
                seen.add(j.job_id)
                jobs.append(j)
                new_count += 1

        repeat = (sig == last_sig)

        # 🔹 Stricter no-progress: only repeat windows with no new items, or truly empty result
        no_progress = (len(reqs) == 0) or (repeat and new_count == 0)

        logger.info(f"[{mode_name}] page={page} got={len(reqs)} new={new_count} "
                    f"collected={len(jobs)} server_total={server_total}")

        if len(jobs) < 5 and new_count >= 1:
            # log a couple of titles early for sanity
            for r in reqs[:5]:
                rid = r.get("Id")
                t = r.get("Title")
                if rid and t:
                    logger.debug(f" - {rid} : {t}")

        if no_progress:
            empty_streak += 1
        else:
            empty_streak = 0
            last_sig = sig

        if empty_streak >= EMPTY_STREAK_LIMIT:
            logger.info(f"[{mode_name}] stopping after {EMPTY_STREAK_LIMIT} no-progress pages.")
            break

        page += 1
        await asyncio.sleep(random.uniform(0.8, 1.6))

    if server_total is not None and len(jobs) != server_total:
        logger.debug(f"[{mode_name}] note: collected={len(jobs)} server_total={server_total}")

    return jobs


async def get_jobs() -> List[OracleJob]:
    """
    Strategy:
      1) CAT + LOC + YEARS     (finder-paging, lastSelected=CATEGORIES)
      2) LOC + YEARS           (finder-paging, lastSelected=AttributeChar6)
      3) YEARS only            (finder-paging, lastSelected=AttributeChar6)
      4) SITE_ONLY             (site-only with larger page)
    """
    await asyncio.sleep(random.uniform(0, 4.0))
    logger.info("Entered Oracle get_jobs()")

    # --- dynamically resolve category IDs (once) ---
    resolved_category_ids: List[str] = []

    if CATEGORY_NAMES and resolve_category_ids:
        try:
            ids = resolve_category_ids(CATEGORY_NAMES)  # returns List[int]
            resolved_category_ids = [str(i) for i in ids if i]
            if resolved_category_ids:
                logger.info(f"[Oracle] Resolved {len(resolved_category_ids)} category IDs "
                            f"from names {CATEGORY_NAMES}: {resolved_category_ids}")
            else:
                logger.warning("[Oracle] Category resolution returned 0 IDs; will skip categories.")
        except Exception as e:
            logger.warning(f"[Oracle] Category ID resolution failed ({e}); will skip categories.")
    elif CATEGORY_NAMES:
        logger.warning("[Oracle] Helper not available; set CATEGORY_NAMES=[] or add the helper module.")

    # --- 1) CAT + LOC + YEARS ---
    if resolved_category_ids:
        def _p1(page: int) -> Dict[str, Any]:
            return _params_filtered(
                last_selected="CATEGORIES",
                page_index=page,
                page_size=PAGE_SIZE_FILTERED,
                use_location=True,
                use_years=True,
                category_ids=resolved_category_ids,
            )

        jobs = await _page_through("CAT+LOC+YEARS (finder-paging, lastSelected=CATEGORIES)", _p1, PAGE_SIZE_FILTERED)
        if jobs:
            logger.info(f"🎉 Oracle: returning {len(jobs)} jobs from CAT+LOC+YEARS.")
            return jobs
        logger.warning("[Oracle] CAT+LOC+YEARS returned nothing; falling back to LOC+YEARS...")

    # --- 2) LOC + YEARS ---
    def _p2(page: int) -> Dict[str, Any]:
        return _params_filtered(
            last_selected="AttributeChar6",
            page_index=page,
            page_size=PAGE_SIZE_FILTERED,
            use_location=True,
            use_years=True,
            category_ids=None,
        )

    jobs = await _page_through("LOC+YEARS (finder-paging, lastSelected=AttributeChar6)", _p2, PAGE_SIZE_FILTERED)
    if jobs:
        logger.info(f"🎉 Oracle: returning {len(jobs)} jobs from LOC+YEARS.")
        return jobs
    logger.warning("[Oracle] LOC+YEARS returned nothing; falling back to YEARS only...")

    # --- 3) YEARS only ---
    def _p3(page: int) -> Dict[str, Any]:
        return _params_filtered(
            last_selected="AttributeChar6",
            page_index=page,
            page_size=PAGE_SIZE_FILTERED,
            use_location=False,
            use_years=True,
            category_ids=None,
        )

    jobs = await _page_through("YEARS only (finder-paging, lastSelected=AttributeChar6)", _p3, PAGE_SIZE_FILTERED)
    if jobs:
        logger.info(f"🎉 Oracle: returning {len(jobs)} jobs from YEARS only.")
        return jobs
    logger.warning("[Oracle] YEARS only returned nothing; falling back to SITE_ONLY...")

    # --- 4) SITE_ONLY ---
    def _p4(page: int) -> Dict[str, Any]:
        return _params_site_only(page, PAGE_SIZE_SITE_ONLY)

    jobs = await _page_through("SITE_ONLY (broad)", _p4, PAGE_SIZE_SITE_ONLY)
    logger.info(f"🎉 Oracle: returning {len(jobs)} jobs from SITE_ONLY.")
    return jobs
