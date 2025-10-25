# models/blackrock_job.py
from dataclasses import dataclass
from typing import Dict, Any
from models.base_job import BaseJob

@dataclass
class KiranBlackRockJob(BaseJob):
    location: str = "Unknown"
    team: str = "Unknown"
    category: str = "Unknown"

    COMPANY_KEY: str = "kiranblackrock"

    def format_message(self) -> str:
        return (
            "📣 BlackRock Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {self.location}\n"
            f"👨‍💻 Team: {self.team or self.category}\n"
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
            "category": self.category,
            "date_posted": self.date_posted,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KiranBlackRockJob":
        return cls(
            job_id=str(d.get("job_id") or d.get("id") or d.get("Id") or ""),
            title=d.get("title") or d.get("Title") or "Unknown",
            url=d.get("url") or d.get("JobUrl") or d.get("ApplyUrl") or "",
            location=d.get("location") or d.get("Location") or "Unknown",
            team=d.get("team") or d.get("MainTeam") or d.get("Department") or "Unknown",
            category=d.get("category") or d.get("Category") or "Unknown",
            date_posted=d.get("date_posted") or d.get("PostedDate") or d.get("Posted") or "Unknown",
        )


