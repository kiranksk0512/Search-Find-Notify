from dataclasses import dataclass
from typing import Dict, Any, Optional
from models.base_job import BaseJob


@dataclass
class DatabricksJob(BaseJob):
    COMPANY_KEY: str = "databricks"
    internal_job_id: Optional[str] = None
    updated_date: Optional[str] = None

    def format_message(self) -> str:
        internal_id_line = f"🆔 Internal: {self.internal_job_id}\n" if self.internal_job_id else ""
        updated_line = f"🗓 Updated: {self.updated_date}\n" if self.updated_date else ""
        return (
            f"📣 Databricks Job\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {self.location or 'Unknown'}\n"
            f"👨‍💻 Team: {self.team or 'Unknown'}\n"
            f"🔧 Sub-Team: {self.sub_teams or 'Unknown'}\n"
            f"🗓 Posted: {self.date_posted or 'Unknown'}\n"
            f"{updated_line}"
            f"{internal_id_line}"
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
            "internal_job_id": self.internal_job_id,
            "updated_date": self.updated_date,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DatabricksJob":
        return cls(
            job_id=d.get("job_id") or d.get("jobId") or d.get("id", ""),
            title=d.get("title", "Unknown"),
            url=d.get("url", ""),
            location=d.get("location"),
            team=d.get("team"),
            sub_teams=d.get("sub_teams"),
            date_posted=d.get("date_posted") or d.get("posted"),
            internal_job_id=d.get("internal_job_id"),
            updated_date=d.get("updated_date") or d.get("updated_at"),
        )
