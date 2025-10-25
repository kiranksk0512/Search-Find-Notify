# scrapers/mergedblackrock.py
import asyncio
import os
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlsplit, urlunsplit

from core.logger import get_company_logger
from zoneinfo import ZoneInfo
from datetime import datetime

from models.mergedblackrock_job import MergedBlackRockJob

# Import your two variants from util/
# Each module must export: async def get_jobs(min_expected_count: int = ...) -> dict OR list
from util.kiranblackrock import get_jobs as get_kiran_jobs
from util.blackrock import get_jobs as get_classic_jobs

logger = get_company_logger()

# ----------------------------- runtime toggles -----------------------------
USE_KIRAN = os.getenv("BLACKROCK_USE_KIRAN", "true").lower() not in ("0", "false", "no")
USE_CLASSIC = os.getenv("BLACKROCK_USE_CLASSIC", "true").lower() not in ("0", "false", "no")
PREFER_SOURCE = os.getenv("BLACKROCK_TIEBREAK", "kiran").lower()  # "kiran" or "classic"
# ---------------------------------------------------------------------------

def _normalize_url(u: str) -> str:
    if not u:
        return ""
    try:
        parts = urlsplit(u.strip())
        scheme = (parts.scheme or "").lower()
        netloc = (parts.netloc or "").lower()
        path = parts.path or ""
        query = parts.query or ""
        return urlunsplit((scheme, netloc, path, query, ""))
    except Exception:
        return u.strip()

def _list_to_url_map(jobs: List[object]) -> Dict[str, object]:
    out: Dict[str, object] = {}
    for j in jobs or []:
        url = getattr(j, "url", None)
        if url is None and isinstance(j, dict):
            url = j.get("url")
        key = _normalize_url(url or "")
        if not key:
            continue
        if key not in out:
            out[key] = j
    return out

def _wrap_union_entry(primary: Optional[object], secondary: Optional[object]) -> MergedBlackRockJob:
    """
    primary supplies canonical fields; secondary is kept for provenance only.
    """
    def val(obj, name, default="Unknown"):
        if obj is None:
            return default
        if hasattr(obj, name):
            return getattr(obj, name) or default
        if isinstance(obj, dict):
            return obj.get(name) or default
        return default

    # Pick canonical from primary; if somehow None, fall back to secondary.
    canon = primary or secondary

    url = val(canon, "url", "")
    job_id = val(canon, "job_id", "")
    title = val(canon, "title", "Unknown")
    location = val(canon, "location", "Unknown")
    team = val(canon, "team", "Unknown")
    category = val(canon, "category", team)
    date_posted = val(canon, "date_posted", "Unknown")

    # Attach originals in the correct slots
    def is_kiran(obj: Optional[object]) -> bool:
        return bool(obj) and obj.__class__.__name__.lower().startswith("kiran")

    kiran_obj = primary if is_kiran(primary) else (secondary if is_kiran(secondary) else None)
    classic_obj = primary if (primary and not is_kiran(primary)) else (secondary if (secondary and not is_kiran(secondary)) else None)

    return MergedBlackRockJob(
        job_id=job_id,
        title=title,
        url=url,
        location=location,
        team=team,
        category=category,
        date_posted=date_posted,
        kiran_job=kiran_obj,
        blackrock_job=classic_obj,
    )

def _dedupe_union_wrapped(a_jobs: List[object], b_jobs: List[object]) -> Tuple[List[MergedBlackRockJob], List[str], List[str], List[str]]:
    """
    a_jobs = Kiran; b_jobs = Classic
    When both have the same URL, put the preferred one as PRIMARY.
    """
    a_map = _list_to_url_map(a_jobs)  # Kiran
    b_map = _list_to_url_map(b_jobs)  # Classic

    a_keys = set(a_map.keys())
    b_keys = set(b_map.keys())

    only_a = sorted(a_keys - b_keys)
    only_b = sorted(b_keys - a_keys)
    both  = sorted(a_keys & b_keys)

    prefer_kiran = (PREFER_SOURCE != "classic")

    union_wrapped: List[MergedBlackRockJob] = []
    # A only
    for k in only_a:
        union_wrapped.append(_wrap_union_entry(a_map[k], None))
    # B only
    for k in only_b:
        union_wrapped.append(_wrap_union_entry(b_map[k], None))
    # Both: choose primary by preference (default: Kiran)
    for k in both:
        if prefer_kiran:
            union_wrapped.append(_wrap_union_entry(a_map[k], b_map[k]))  # Kiran first
        else:
            union_wrapped.append(_wrap_union_entry(b_map[k], a_map[k]))  # Classic first

    return union_wrapped, only_a, only_b, both

async def _run_source(name: str, fn, min_expected_count: int) -> List[object]:
    try:
        result = await fn(min_expected_count=min_expected_count)
    except TypeError:
        result = await fn()
    except Exception as e:
        logger.error(f"[mergedblackrock] source={name} exception: {e}")
        return []

    if isinstance(result, dict):
        jobs = result.get("jobs") or []
    else:
        jobs = result or []
    logger.info(f"[mergedblackrock] source={name} yielded={len(jobs)}")
    return jobs

async def get_jobs(min_expected_count: int = 20):
    logger.info(
        f"[mergedblackrock] ▶️ starting merged run "
        f"(USE_KIRAN={USE_KIRAN}, USE_CLASSIC={USE_CLASSIC}, min_expected_count={min_expected_count})"
    )

    tasks = []
    if USE_KIRAN:
        tasks.append(_run_source("kiranblackrock", get_kiran_jobs, min_expected_count))
    else:
        logger.info("[mergedblackrock] source=kiranblackrock DISABLED")
    if USE_CLASSIC:
        tasks.append(_run_source("blackrock", get_classic_jobs, min_expected_count))
    else:
        logger.info("[mergedblackrock] source=blackrock DISABLED")

    if not tasks:
        logger.warning("[mergedblackrock] both sources disabled; returning zero_jobs")
        return {
            "jobs": [],
            "should_persist": False,
            "decision_reason": "both_sources_disabled",
            "default_count": 0,
            "new_count": 0,
        }

    results = await asyncio.gather(*tasks, return_exceptions=False)
    if USE_KIRAN and USE_CLASSIC:
        a_jobs, b_jobs = results[0], results[1]
        a_name, b_name = "kiranblackrock", "blackrock"
    elif USE_KIRAN:
        a_jobs, b_jobs = results[0], []
        a_name, b_name = "kiranblackrock", "blackrock"
    else:
        a_jobs, b_jobs = [], results[0]
        a_name, b_name = "kiranblackrock", "blackrock"

    # Build wrapped union + diff sets by URL
    union_jobs, only_in_a, only_in_b, in_both = _dedupe_union_wrapped(a_jobs, b_jobs)

    # ---------- Analysis logs ----------
    if USE_KIRAN and USE_CLASSIC:
        if only_in_a:
            logger.info(f"[mergedblackrock] 🔎 URLs in {a_name} NOT in {b_name} (count={len(only_in_a)}):")
            for u in only_in_a:
                logger.info(f"[mergedblackrock]   {u}")
        if only_in_b:
            logger.info(f"[mergedblackrock] 🔎 URLs in {b_name} NOT in {a_name} (count={len(only_in_b)}):")
            for u in only_in_b:
                logger.info(f"[mergedblackrock]   {u}")
        if in_both:
            logger.info(f"[mergedblackrock] ✅ URLs present in BOTH (count={len(in_both)}):")
            for u in in_both:
                logger.info(f"[mergedblackrock]   {u}")
    else:
        logger.info("[mergedblackrock] analysis skipped: only one source enabled")

    # ---------- Decisioning ----------
    total = len(union_jobs)
    if total == 0:
        return {
            "jobs": [],
            "should_persist": False,
            "decision_reason": "zero_jobs",
            "default_count": 0,
            "new_count": 0,
        }

    if total < min_expected_count:
        return {
            "jobs": union_jobs,
            "should_persist": False,
            "decision_reason": f"too_few_union({total}<{min_expected_count})",
            "default_count": total,
            "new_count": 0,
        }

    logger.info(
        f"[mergedblackrock] ✅ union_size={total} "
        f"(kiran={len(a_jobs)}, classic={len(b_jobs)}); "
        f"timestamp={datetime.now(ZoneInfo('America/New_York')):%Y-%m-%d %H:%M:%S %Z}"
    )
    return {
        "jobs": union_jobs,
        "should_persist": True,
        "decision_reason": "ok",
        "default_count": total,
        "new_count": 0,
    }
