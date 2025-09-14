# core/stability.py
from __future__ import annotations
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime, timezone
from core.storage_router import load_aux_json, save_aux_json

MISS_TAG = "miss_counts"

def load_miss_counts(_: str, company: str) -> Dict[str, Dict[str, Any]]:
    return load_aux_json(company, MISS_TAG)

def save_miss_counts(_: str, company: str, counts: Dict[str, Dict[str, Any]]) -> None:
    save_aux_json(company, MISS_TAG, counts)

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def utcnow_str() -> str:
    return utcnow().strftime("%Y-%m-%dT%H:%M:%S%z")

def parse_iso_guess(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

async def confirm_big_drop(
    *,
    prev_count: int,
    current_jobs: List[Any],
    scraper_func,
    ratio_threshold: float,
    max_refetches: int,
    logger=None
) -> List[Any]:
    curr_count = len(current_jobs)
    if prev_count <= 0 or curr_count >= int(prev_count * ratio_threshold):
        return current_jobs
    if logger:
        logger.warning(f"📉 Sudden drop detected ({curr_count} vs prev {prev_count}); attempting refetch.")

    base = {j.job_id: j for j in current_jobs}
    for attempt in range(1, max_refetches + 1):
        try:
            refetched = await scraper_func()
            for j in refetched:
                base[j.job_id] = j
            if logger:
                logger.info(f"🔁 Refetch {attempt}: union size now {len(base)}")
            break
        except Exception as e:
            if logger:
                logger.warning(f"Refetch attempt {attempt} failed: {e}")
    return list(base.values())

def apply_stability(
    *,
    company_name: str,
    base_data_path: str,  # kept for signature compatibility
    current_jobs_dict: Dict[str, Any],
    previous_jobs: Dict[str, Any],
    miss_threshold: int,
    reopen_grace_days: int,
    logger=None
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    prev_only = {jid: previous_jobs[jid] for jid in previous_jobs.keys() - current_jobs_dict.keys()}
    curr_only = {jid: current_jobs_dict[jid] for jid in current_jobs_dict.keys() - previous_jobs.keys()}

    miss_counts = load_miss_counts(base_data_path, company_name)

    confirmed_deleted: Dict[str, Any] = {}
    quarantined_missing: Dict[str, Any] = {}
    reopened: Dict[str, Any] = {}
    now_iso = utcnow_str()

    # Missing this run → increment miss
    for jid, job in prev_only.items():
        entry = miss_counts.get(jid, {"miss": 0, "last_missing": None})
        entry["miss"] = int(entry.get("miss", 0)) + 1
        entry["last_missing"] = now_iso
        miss_counts[jid] = entry
        if entry["miss"] >= miss_threshold:
            confirmed_deleted[jid] = job
        else:
            quarantined_missing[jid] = job

    # Present now → maybe reopened (if miss < threshold), then clear history
    for jid, job in current_jobs_dict.items():
        if jid in miss_counts:
            miss_val = int(miss_counts[jid].get("miss", 0))
            last_missing_iso = miss_counts[jid].get("last_missing")
            if 0 < miss_val < miss_threshold:
                recent_reopen = False
                if last_missing_iso:
                    lm = parse_iso_guess(last_missing_iso)
                    if lm:
                        recent_reopen = (utcnow() - lm.astimezone(timezone.utc)).days <= reopen_grace_days
                if recent_reopen:
                    reopened[jid] = job
                    if logger:
                        title = getattr(job, "title", "") or ""
                        url = getattr(job, "url", "") or ""
                        logger.info(f"[Stability][{company_name}] Reopened before threshold: job_id={jid} | title={title} | url={url}")
            miss_counts.pop(jid, None)

    save_miss_counts(base_data_path, company_name, miss_counts)

    # New = curr_only minus reopened
    for jid in reopened.keys():
        curr_only.pop(jid, None)

    new_job_objs = curr_only
    deleted_job_objs = confirmed_deleted

    if logger:
        logger.info("Stability → new=%d, deleted=%d, quarantined=%d, reopened=%d",
                    len(new_job_objs), len(deleted_job_objs), len(quarantined_missing), len(reopened))

    return new_job_objs, deleted_job_objs, quarantined_missing, reopened
