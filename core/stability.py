# core/stability.py
from __future__ import annotations

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime, timezone, timedelta

from core.storage_router import load_aux_json, save_aux_json

MISS_TAG = "miss_counts"


def load_miss_counts(_: str, company: str) -> Dict[str, Dict[str, Any]]:
    """Load per-company miss counters from aux storage."""
    return load_aux_json(company, MISS_TAG)


def save_miss_counts(_: str, company: str, counts: Dict[str, Dict[str, Any]]) -> None:
    """Persist per-company miss counters to aux storage."""
    save_aux_json(company, MISS_TAG, counts)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_str() -> str:
    # Use ISO format with timezone offset including colon (e.g. +00:00)
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso_guess(s: Optional[str]) -> Optional[datetime]:
    """Be tolerant of 'Z' and '+0000' forms."""
    if not s:
        return None
    try:
        s = s.replace("Z", "+00:00")
        # normalize trailing +0000 / -0000 -> +00:00 / -00:00
        if len(s) >= 5 and (s[-5] in "+-") and s[-2:].isdigit() and s[-5:-2].isdigit() and (len(s) < 6 or s[-3] != ":"):
            s = s[:-2] + ":" + s[-2:]
        return datetime.fromisoformat(s)
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
    """
    If there's a sudden count drop vs. previous snapshot, refetch and union results
    until we either reach the ratio_threshold of prev_count or exhaust retries.
    """
    curr_count = len(current_jobs)
    threshold = int(prev_count * ratio_threshold)

    if prev_count <= 0 or curr_count >= threshold:
        return current_jobs

    if logger:
        loss = 100.0 * (1 - curr_count / max(prev_count, 1))
        logger.warning(
            f"📉 Sudden drop detected {curr_count}/{prev_count} ({loss:.1f}%). "
            f"Refetching up to {max_refetches} time(s)."
        )

    base = {j.job_id: j for j in current_jobs}

    for attempt in range(1, max_refetches + 1):
        try:
            refetched = await scraper_func()
            for j in refetched:
                base[j.job_id] = j
            if logger:
                logger.info(f"🔁 Refetch {attempt}: union size now {len(base)}")
            if len(base) >= threshold:
                if logger:
                    logger.info("✅ Union meets ratio threshold; stopping refetch.")
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
    """
    Stability logic:
      - Increment miss counts for any job currently missing. (Includes jobs that started
        missing in earlier runs—so misses keep accruing.)
      - If miss >= threshold → confirmed_deleted
        else → quarantined_missing
      - If a job reappears with 0 < miss < threshold within grace → mark as reopened, clear history.
      - New jobs = current minus previous, minus reopened.
    Returns:
      (new_job_objs, deleted_job_objs, quarantined_missing, reopened)
    """
    miss_counts = load_miss_counts(base_data_path, company_name)  # {job_id: {"miss": int, "last_missing": str, "url": str|None}}

    confirmed_deleted: Dict[str, Any] = {}
    quarantined_missing: Dict[str, Any] = {}
    reopened: Dict[str, Any] = {}

    now_iso = utcnow_str()

    prev_ids = set(previous_jobs.keys())
    curr_ids = set(current_jobs_dict.keys())
    # Include already-missing IDs so their miss counters keep increasing across runs
    carry_missing_ids = set(miss_counts.keys())
    missing_this_run_ids = (prev_ids | carry_missing_ids) - curr_ids

    # 1) Increment 'miss' for everything currently missing. Store URL once (lean aux).
    for jid in missing_this_run_ids:
        entry = miss_counts.get(jid, {"miss": 0, "last_missing": None, "url": None})
        entry["miss"] = int(entry.get("miss", 0)) + 1
        entry["last_missing"] = now_iso

        # On first miss, try to capture a URL (for digest/logs when it finally deletes).
        if not entry.get("url"):
            job_obj = previous_jobs.get(jid)
            if job_obj is not None:
                if hasattr(job_obj, "url"):
                    entry["url"] = job_obj.url
                elif isinstance(job_obj, dict):
                    entry["url"] = job_obj.get("url", "")  # fallback
                else:
                    entry["url"] = ""  # last resort

        miss_counts[jid] = entry

        # Use minimal representation for reporting (job_id + url)
        job_for_maps = {"job_id": jid, "url": entry.get("url", "")}

        if entry["miss"] >= miss_threshold:
            confirmed_deleted[jid] = job_for_maps
        else:
            quarantined_missing[jid] = job_for_maps

    # 2) Present now → maybe reopened (if had prior misses), then clear history
    for jid, job in current_jobs_dict.items():
        if jid in miss_counts:
            miss_val = int(miss_counts[jid].get("miss", 0))
            last_missing_iso = miss_counts[jid].get("last_missing")
            if 0 < miss_val < miss_threshold:
                recent_reopen = False
                if last_missing_iso:
                    lm = parse_iso_guess(last_missing_iso)
                    if lm:
                        recent_reopen = (utcnow() - lm.astimezone(timezone.utc)) <= timedelta(days=reopen_grace_days)
                if recent_reopen:
                    reopened[jid] = job
                    if logger:
                        title = getattr(job, "title", "") or ""
                        url = getattr(job, "url", "") or ""
                        logger.info(
                            f"[Stability][{company_name}] Reopened before threshold: "
                            f"job_id={jid} | title={title} | url={url}"
                        )
            # Clear history in all 'present' cases
            miss_counts.pop(jid, None)

    # 3) Clean counters for confirmed deletions to prevent unbounded growth
    for jid in list(confirmed_deleted.keys()):
        miss_counts.pop(jid, None)

    save_miss_counts(base_data_path, company_name, miss_counts)

    # 4) New = present now but not previously, minus reopened
    curr_only = {jid: current_jobs_dict[jid] for jid in curr_ids - prev_ids}
    for jid in reopened.keys():
        curr_only.pop(jid, None)

    new_job_objs = curr_only
    deleted_job_objs = confirmed_deleted

    if logger:
        logger.info(
            "Stability → new=%d, deleted=%d, quarantined=%d, reopened=%d",
            len(new_job_objs), len(deleted_job_objs), len(quarantined_missing), len(reopened)
        )

    return new_job_objs, deleted_job_objs, quarantined_missing, reopened
