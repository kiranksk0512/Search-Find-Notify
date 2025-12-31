from dataclasses import dataclass
from typing import Any, Dict

from models.base_job import BaseJob


@dataclass
class WaymoJob(BaseJob):
    """Waymo job posting.

    Notes:
    - `team` is used for the job department.
    - `sub_teams` is used for employment type (e.g. Intern, Full-Time).
    """

    COMPANY_KEY: str = "waymo"

    def format_message(self) -> str:
        loc = self.location or "Unknown"
        dept = self.team or "Unknown"
        emp = self.sub_teams or "Unknown"
        posted = self.date_posted or "Unknown"
        return (
            "📣 Waymo Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {loc}\n"
            f"🏷 Department: {dept}\n"
            f"⏱ Employment: {emp}\n"
            f"🗓 Posted: {posted}\n"
            f"🔗 URL: {self.url}\n"
            "----------------------"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location or "Unknown",
            "team": self.team or "Unknown",
            "sub_teams": self.sub_teams or "Unknown",
            "date_posted": self.date_posted,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WaymoJob":
        return cls(
            job_id=d.get("job_id") or d.get("jobId") or d.get("id", ""),
            title=d.get("title", "Unknown"),
            url=d.get("url", ""),
            location=d.get("location") or "Unknown",
            team=d.get("team") or d.get("department") or "Unknown",
            sub_teams=d.get("sub_teams") or d.get("employment_type") or "Unknown",
            date_posted=d.get("date_posted") or d.get("posted"),
        )
