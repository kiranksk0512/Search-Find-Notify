from dataclasses import dataclass
from typing import Dict, Any
from models.base_job import BaseJob
from datetime import datetime
from zoneinfo import ZoneInfo

def convert_ts(ts):
    try:
        dt = datetime.fromtimestamp(int(ts), tz=ZoneInfo("America/New_York"))
        return dt.strftime("%b %d, %Y %I:%M %p %Z")
    except:
        return "Unknown"


@dataclass
class MicrosoftNewJob(BaseJob):
    location: str = "Unknown"
    department: str = "Unknown"
    display_job_id: str = "Unknown"
    work_location: str = "Unknown"
    posted: str = "Unknown"
    created_date: str = "Unknown"
    isHotJob: bool = 0

    COMPANY_KEY: str = "microsoftnew"

    def format_message(self) -> str:
        return (
            f"📣 New Microsoft Job Alert\n"
            f"🔹 {self.title}\n"
            f"🔹 JobId: {self.job_id} ({self.display_job_id})\n"
            f"📍 Location: {self.location}\n"
            f"🏢 Department: {self.department}\n"
            f"🗓 Posted: {convert_ts(self.posted)}\n"
            f"🗓 Created: {convert_ts(self.created_date)}\n"
            f"🔥 Hot Job: {'Yes' if self.isHotJob else 'No'}\n"
            f"🔗 URL: {self.url}\n"

            "----------------------"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "department": self.department,
            "display_job_id": self.display_job_id,
            "work_location": self.work_location,
            "posted": self.posted,
            "created_date": self.created_date,
            "isHotJob": self.isHotJob,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MicrosoftNewJob":
        return cls(
            job_id=d.get("job_id"),
            title=d.get("title", "Unknown"),
            url=d.get("url", ""),
            location=d.get("location", "Unknown"),
            department=d.get("department", "Unknown"),
            display_job_id=d.get("display_job_id", "Unknown"),
            work_location=d.get("work_location", "Unknown"),
            posted=d.get("posted", "Unknown"),
            created_date=d.get("created_date", "Unknown"),
            isHotJob=d.get("isHotJob", 0),
        )
