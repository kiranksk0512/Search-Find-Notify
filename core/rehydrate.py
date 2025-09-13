from typing import Dict, Any
from core.model_registry import get_model_cls
from models.base_job import BaseJob

def rehydrate_jobs(company: str, data: Dict[str, Dict[str, Any]]) -> Dict[str, BaseJob]:
    """
    Convert {job_id: dict} loaded from storage into {job_id: ModelInstance}.
    """
    cls = get_model_cls(company)
    out: Dict[str, BaseJob] = {}
    for jid, payload in (data or {}).items():
        try:
            out[jid] = cls.from_dict(payload)
        except Exception:
            # Best-effort fallback; ensure we don't crash cleanup/diff
            out[jid] = cls(job_id=jid,
                           title=payload.get("title", "Unknown"),
                           url=payload.get("url", ""),
                           location=payload.get("location"),
                           team=payload.get("team"),
                           sub_teams=payload.get("sub_teams"),
                           date_posted=payload.get("date_posted"))
    return out
