from dataclasses import dataclass
from models.base_job import BaseJob

@dataclass
class AppleJob(BaseJob):
    COMPANY_KEY: str = "apple"

    def format_message(self) -> str:
        loc = self.location or "USA"
        team = self.team or "Unknown"
        posted = self.date_posted or "Unknown"
        return (
            f"🍎 Apple Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {loc}\n"
            f"👨‍💻 Team: {team}\n"
            f"🗓 Posted: {posted}\n"
            f"🔗 URL: {self.url}\n"
            "----------------------"
        )

    @classmethod
    def from_dict(cls, d: dict) -> "AppleJob":
        return cls(
            job_id=d.get("job_id") or d.get("jobId") or "",
            title=d.get("title", "Unknown"),
            url=d.get("url", ""),
            location=d.get("location", "USA"),
            team=d.get("team", "Unknown"),
            date_posted=d.get("date_posted") or d.get("posted"),
        )
