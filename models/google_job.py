from dataclasses import dataclass
from typing import Dict, Any
from models.base_job import BaseJob


@dataclass
class GoogleJob(BaseJob):
    location: str = "USA"
    team: str = "Unknown"

    COMPANY_KEY: str = "google"

    def format_message(self) -> str:
        return (
            f"💻 Google Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {self.location}\n"
            f"👨‍💻 Team: {self.team}\n"
            f"🗓 Posted: {self.date_posted or 'Unknown'}\n"
            f"🔗 URL: {self.url}\n"
            "----------------------"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "team": self.team,
            "date_posted": self.date_posted,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GoogleJob":
        return cls(
            job_id=d.get("job_id") or d.get("jobId") or "",
            title=d.get("title", "Unknown"),
            url=d.get("url", ""),
            location=d.get("location", "USA"),
            team=d.get("team", "Unknown"),
            date_posted=d.get("date_posted") or d.get("posted"),
        )
