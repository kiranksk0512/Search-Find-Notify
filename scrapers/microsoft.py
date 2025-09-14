import asyncio
import random
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from zoneinfo import ZoneInfo

from core.fetcher import get_json_resilient
from core.logger import get_company_logger
from models.microsoft_job import MicrosoftJob



logger = get_company_logger()

API_BASE = "https://gcsservices.careers.microsoft.com/search/api/v1/search"

# Default filters from your capture; tweak if needed
DEFAULT_PARAMS = {
    "lc": "United States",                 # country
    "p": "Software Engineering",           # profession/discipline
    "l": "en_us",                          # locale
    "o": "Recent",                         # sort
}

# ---- New: tuning knobs / failsafes ----
PAGE_SIZE_DEFAULT = 20
EMPTY_STREAK_LIMIT = 3        # stop after 3 consecutive "no progress" pages
MAX_PAGES = 500               # hard guard against infinite pagination
# --------------------------------------

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
]

EXPERIENCE_TRACKS = [
    "Experienced professionals",
    "Students and graduates",
]

RUN_CORRELATION_ID = str(uuid.uuid4())
def _headers(sub_id: Optional[str] = None) -> Dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Cache-Control": "no-cache",
        "Origin": "https://jobs.careers.microsoft.com",
        "Pragma": "no-cache",
        "Referer": "https://jobs.careers.microsoft.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": random.choice(USER_AGENTS),
        # stable across the whole run:
        "x-correlationid": RUN_CORRELATION_ID,
        # per request/page:
        "x-subcorrelationid": sub_id or str(uuid.uuid4()),
    }

def _params(page: int, page_size: int = PAGE_SIZE_DEFAULT, exp: str = "Experienced professionals") -> Dict[str, Any]:
    p = dict(DEFAULT_PARAMS)
    p["pg"] = page
    p["pgSz"] = page_size
    p["exp"] = exp
    return p

def _to_est(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(ZoneInfo("America/New_York")).strftime("%b %d, %Y %I:%M %p %Z")
    except Exception:
        return "Unknown"

def _canonical_url(job_id: str) -> str:
    return f"https://jobs.careers.microsoft.com/us/en/job/{job_id}"

def _normalize(raw: Dict[str, Any], exp_track: Optional[str] = None) -> MicrosoftJob:
    props = raw.get("properties") or {}
    job_id = str(raw.get("jobId") or raw.get("id") or "")

    title = raw.get("title") or props.get("title") or "Unknown"

    primary_location = props.get("primaryLocation")
    locations = props.get("locations") or []
    location = primary_location or (locations[0] if locations else None) or "USA"

    profession = props.get("profession")
    discipline = props.get("discipline")
    role_type = props.get("roleType")
    employment_type = props.get("employmentType")
    job_type = props.get("jobType")
    worksite_flexibility = props.get("workSiteFlexibility")
    education_level = props.get("educationLevel")
    description_html = props.get("description")

    posted = _to_est(raw.get("postingDate") or raw.get("postedDate") or raw.get("datePosted"))
    last_updated = _to_est(raw.get("lastUpdated") or raw.get("lastModifiedDate"))  # optional; may be None

    return MicrosoftJob(
        job_id=job_id,
        title=title,
        url=_canonical_url(job_id) if job_id else "",
        # Base fields (keep populated)
        location=location,
        team=profession or discipline or "Unknown",    # <-- compatibility only
        date_posted=posted,

        # Microsoft rich fields
        profession=profession,
        discipline=discipline,
        role_type=role_type,
        employment_type=employment_type,
        job_type=job_type,
        worksite_flexibility=worksite_flexibility,
        education_level=education_level,
        primary_location=primary_location,
        locations=locations,
        last_updated=last_updated,
        experience_track=exp_track,
    )

def _extract_status(d: Dict[str, Any]) -> str:
    return (
        (d.get("operationResult") or {}).get("status")
        or d.get("status")
        or ""
    )

def _extract_error_code(d: Dict[str, Any]) -> Optional[str]:
    return (d.get("operationResult") or {}).get("errorCode") or d.get("errorCode")

def _extract_error_info(d: Dict[str, Any]) -> Optional[str]:
    return d.get("errorInfo")


def _extract_jobs(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Prefer operationResult.result.jobs → result.jobs → jobs
    opres = d.get("operationResult") or {}
    res1 = (opres.get("result") or {}).get("jobs")
    if isinstance(res1, list) and res1:
        return res1
    res2 = (d.get("result") or {}).get("jobs")
    if isinstance(res2, list) and res2:
        return res2
    res3 = d.get("jobs")
    return res3 if isinstance(res3, list) else []


def _extract_total(d: Dict[str, Any]) -> Optional[int]:
    opres = d.get("operationResult") or {}
    v = (opres.get("result") or {}).get("totalJobs")
    if v is None:
        v = (d.get("result") or {}).get("totalJobs")
    try:
        return int(v) if v is not None else None
    except Exception:
        return None


async def get_jobs() -> List[MicrosoftJob]:
    jobs: List[MicrosoftJob] = []
    seen_ids: set[str] = set()

    await asyncio.sleep(random.uniform(0, 20))
    logger.info("Entered Microsoft get_jobs()")

    for exp_track in EXPERIENCE_TRACKS:
        logger.info(f"[Microsoft] Scraping experience track: {exp_track}")
        page = 1
        empty_streak = 0
        last_sig: Optional[tuple] = None

        while page <= MAX_PAGES:
            headers = _headers()
            headers = _headers(sub_id=f"{RUN_CORRELATION_ID}:{exp_track}:pg{page}")
            params = _params(page, PAGE_SIZE_DEFAULT, exp_track)

            data = await get_json_resilient(
                        API_BASE,
                        headers=headers,
                        params=params,
                        logger=logger,
                    )

            if not data:
                empty_streak += 1
                logger.info(f"[Microsoft][{exp_track}] Empty payload (page {page}); streak {empty_streak}/{EMPTY_STREAK_LIMIT}")
                if empty_streak >= EMPTY_STREAK_LIMIT:
                    logger.info(f"[Microsoft][{exp_track}] Stopping after {EMPTY_STREAK_LIMIT} consecutive empty pages.")
                    break
                page += 1
                await asyncio.sleep(random.uniform(1, 4))
                continue

            status_val = _extract_status(data)
            status_ok = (status_val or "").lower() == "success"

            if not status_ok:
                err_code = _extract_error_code(data)
                err_info = _extract_error_info(data)
                msg = (f"Microsoft API non-success on page {page} [{exp_track}]: "
                    f"status={status_val!r}, errorCode={err_code!r}, errorInfo={err_info!r}, "
                    f"correlationId={RUN_CORRELATION_ID}")
                logger.error(msg)
                raise RuntimeError(msg)



            raw_jobs = _extract_jobs(data)

            tj = _extract_total(data)
            if tj is not None:
                logger.info(f"[Microsoft][{exp_track}] API reports totalJobs={tj}")

            ids = [str(r.get("jobId") or r.get("id") or "") for r in raw_jobs if r]
            sig = tuple(ids[:5] + ids[-5:]) if ids else tuple()

            new_count = 0
            for r in raw_jobs:
                j = _normalize(r, exp_track=exp_track)
                if j.job_id and j.job_id not in seen_ids:
                    seen_ids.add(j.job_id)
                    jobs.append(j)
                    new_count += 1

            no_progress = (len(raw_jobs) == 0) or (sig == last_sig) or (new_count == 0)
            if no_progress:
                empty_streak += 1
                logger.info(f"[Microsoft][{exp_track}] No progress on page {page} "
                            f"(raw={len(raw_jobs)}, new={new_count}, repeat={sig == last_sig}); "
                            f"streak {empty_streak}/{EMPTY_STREAK_LIMIT}")
            else:
                empty_streak = 0

            last_sig = sig
            logger.info(f"[Microsoft][{exp_track}] Page {page}: +{new_count} new, total {len(jobs)}")

            if empty_streak >= EMPTY_STREAK_LIMIT:
                logger.info(f"[Microsoft][{exp_track}] Stopping after {EMPTY_STREAK_LIMIT} consecutive no-progress pages.")
                break

            page += 1
            await asyncio.sleep(random.uniform(1, 4))

    logger.info(f"🎉 [Microsoft] Found total across all tracks: {len(jobs)} jobs")
    return jobs
