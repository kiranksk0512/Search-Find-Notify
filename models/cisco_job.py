from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Tuple

from models.base_job import BaseJob


@dataclass
class CiscoJob(BaseJob):
    location: str = "Unknown"
    remote_type: str = "Unknown"
    job_type: str = "Unknown"
    category: str = "Unknown"
    department: str = "Unknown"
    all_locations: Tuple[str, ...] = ()
    date_created: str | None = None

    COMPANY_KEY: str = "cisco"

    def format_message(self) -> str:
        multi_loc = ", ".join(self.all_locations) if self.all_locations else self.location or "Unknown"
        remote = self.remote_type or "Unknown"
        job_type = self.job_type or "Unknown"
        cat = self.category or "Unknown"
        dept = self.department or "Unknown"
        posted = self.date_posted or "Unknown"
        created = self.date_created or "Unknown"
        return (
            f"📣 Cisco Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location(s): {multi_loc}\n"
            f"🧭 Remote Type: {remote}\n"
            f"🗂️ Category: {cat}\n"
            f"🏢 Department: {dept}\n"
            f"🕒 Type: {job_type}\n"
            f"🗓 Posted: {posted}\n"
            f"🗃 Created: {created}\n"
            f"🔗 URL: {self.url}\n"
            "----------------------"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "remote_type": self.remote_type,
            "job_type": self.job_type,
            "category": self.category,
            "department": self.department,
            "all_locations": list(self.all_locations),
            "date_posted": self.date_posted,
            "date_created": self.date_created,
            "type": self.job_type,
            "postedDate": self.date_posted,
            "dateCreated": self.date_created,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CiscoJob":
        raw_locations = data.get("all_locations") or []
        loc_tuple: Tuple[str, ...] = tuple(_ensure_str(v) for v in raw_locations if isinstance(v, str) and v.strip())
        primary_location = data.get("location") or (loc_tuple[0] if loc_tuple else "Unknown")
        return cls(
            job_id=data.get("job_id") or data.get("jobId") or "",
            title=data.get("title", "Unknown"),
            url=data.get("url", ""),
            location=primary_location,
            remote_type=data.get("remote_type") or data.get("remoteType") or "Unknown",
            job_type=data.get("job_type") or data.get("type") or "Unknown",
            category=data.get("category") or "Unknown",
            department=data.get("department") or "Unknown",
            all_locations=loc_tuple,
            date_posted=data.get("date_posted") or data.get("postedDate"),
            date_created=data.get("date_created") or data.get("dateCreated"),
        )


def _ensure_str(value: Any) -> str:
    try:
        return str(value)
    except Exception:
        return ""
