from __future__ import annotations
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timezone, timedelta
import json
import os

MISS_FILE_SUFFIX = "_miss_counts.json"

def utcnow_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

def _miss_path(base_dir: str, company: str) -> str:
    return os.path.join(base_dir, f"{company}{MISS_FILE_SUFFIX}")

def load_miss_counts(base_dir: str, company: str) -> Dict[str, Dict[str, Any]]:
    """
    Returns {job_id: {"miss": int, "last_missing": ISO8601}}
    """
    path = _miss_path(base_dir, company)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # normalize shape
            norm = {}
            for jid, v in data.items():
                if isinstance(v, dict):
                    norm[jid] = {"miss": int(v.get("miss", 0)), "last_missing": v.get("last_missing")}
                else:
                    norm[jid] = {"miss": int(v), "last_missing": None}
            return norm
    except Exception:
        return {}

def save_miss_counts(base_dir: str, company: str, counts: Dict[str, Dict[str, Any]]) -> None:
    path = _miss_path(base_dir, company)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(counts, f, ensure_ascii=False, indent=2)

def parse_iso_guess(s: Optional[str]) -> Optional[datetime]:
    if not s: return None
    try:
        s2 = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s2)
    except Exception:
        return None

def is_recent_posted(job, max_age_days: int) -> bool:
    try:
        iso = getattr(job, "date_posted", "") or ""
        dt = parse_iso_guess(iso)
        if not dt:
            return True
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days <= max_age_days
    except Exception:
        return True
