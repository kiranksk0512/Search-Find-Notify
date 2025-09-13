from dataclasses import dataclass
from typing import Dict, Any
from models.base_job import BaseJob


@dataclass
class MetaJob(BaseJob):
    location: str = "Unknown"
    team: str = "Unknown"
    sub_teams: str = "Unknown"

    COMPANY_KEY: str = "meta"

    def format_message(self) -> str:
        return (
            f"📣 Meta Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {self.location}\n"
            f"👨‍💻 Team: {self.team}\n"
            f"🔧 Sub-Team: {self.sub_teams}\n"
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
            "sub_teams": self.sub_teams,
            "date_posted": self.date_posted,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MetaJob":
        return cls(
            job_id=d.get("job_id") or d.get("jobId") or "",
            title=d.get("title", "Unknown"),
            url=d.get("url", ""),
            location=d.get("location", "Unknown"),
            team=d.get("team", "Unknown"),
            sub_teams=d.get("sub_teams", "Unknown"),
            date_posted=d.get("date_posted") or d.get("posted") or "Unknown",
        )
