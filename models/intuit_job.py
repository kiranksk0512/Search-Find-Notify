from dataclasses import dataclass
from typing import Any, Dict

from models.base_job import BaseJob


@dataclass
class IntuitJob(BaseJob):
    category: str = "Unknown"
    job_type: str = ""
    requisition_id: str = ""

    COMPANY_KEY: str = "intuit"

    def format_message(self) -> str:
        job_type = self.job_type or "Unknown"
        return (
            "🚀 Intuit Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {self.location or 'Unknown'}\n"
            f"👥 Category: {self.category or 'Unknown'}\n"
            f"🛠 Job Type: {job_type}\n"
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
            "category": self.category,
            "job_type": self.job_type,
            "requisition_id": self.requisition_id,
            "date_posted": self.date_posted,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntuitJob":
        return cls(
            job_id=data.get("job_id") or data.get("jobId") or "",
            title=data.get("title", "Unknown"),
            url=data.get("url", ""),
            location=data.get("location", "Unknown"),
            category=data.get("category", "Unknown"),
            job_type=data.get("job_type", ""),
            requisition_id=data.get("requisition_id", ""),
            date_posted=data.get("date_posted") or data.get("posted") or "Unknown",
        )
