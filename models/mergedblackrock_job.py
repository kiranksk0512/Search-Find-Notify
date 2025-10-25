# models/mergedblackrock_job.py
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from models.base_job import BaseJob

@dataclass
class MergedBlackRockJob(BaseJob):
    """
    A wrapper job that your merged scraper returns. It carries canonical top-level
    fields (so the rest of the pipeline is unchanged) AND embeds the originals:
      - kiran_job: the object from the kiranblackrock scraper (if present)
      - blackrock_job: the object from the classic blackrock scraper (if present)
    We also store *_raw dicts so rehydrate works even if source classes aren't imported.
    """
    location: str = "Unknown"
    team: str = "Unknown"
    category: str = "Unknown"

    # Embedded originals (optionally typed as Any to avoid circular deps)
    kiran_job: Optional[Any] = None
    blackrock_job: Optional[Any] = None

    # IMPORTANT: set this to the company key you register in discover_scrapers()
    # If you register the merged scraper under "kiranblackrock", keep this the same.
    COMPANY_KEY: str = "mergedblackrock"

    def format_message(self) -> str:
        sources = []
        if self.kiran_job is not None:
            sources.append("kiran")
        if self.blackrock_job is not None:
            sources.append("classic")
        src_str = ", ".join(sources) if sources else "unknown"

        return (
            "📣 BlackRock (Merged) Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {self.location}\n"
            f"👨‍💻 Team: {self.team or self.category}\n"
            f"🗓 Posted: {self.date_posted or 'Unknown'}\n"
            f"🔗 URL: {self.url}\n"
            f"🔎 Sources: {src_str}\n"
            "----------------------"
        )

    def to_dict(self) -> Dict[str, Any]:
        def as_dict(obj: Any) -> Optional[Dict[str, Any]]:
            if obj is None:
                return None
            # If the source class has to_dict(), use it; otherwise best-effort copy
            if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
                try:
                    return obj.to_dict()
                except Exception:
                    pass
            # Fallback: pick common attributes if it looks like a dataclass-like object
            out = {}
            for attr in ("job_id", "title", "url", "location", "team", "category", "date_posted"):
                if hasattr(obj, attr):
                    out[attr] = getattr(obj, attr)
            return out or None

        return {
            "job_id": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "team": self.team,
            "category": self.category,
            "date_posted": self.date_posted,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MergedBlackRockJob":
        """
        Rehydrate the wrapper from stored JSON. We reattach raw dicts; we do not
        attempt to reconstruct typed source objects (not required by pipeline).
        """
        return cls(
            job_id=str(d.get("job_id") or ""),
            title=d.get("title") or "Unknown",
            url=d.get("url") or "",
            location=d.get("location") or "Unknown",
            team=d.get("team") or "Unknown",
            category=d.get("category") or d.get("team") or "Unknown",
            date_posted=d.get("date_posted") or "Unknown",
            kiran_job=None,
            blackrock_job=None
        )
