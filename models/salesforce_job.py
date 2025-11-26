from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, ClassVar
from models.base_job import BaseJob


@dataclass
class SalesforceJob(BaseJob):
    locations: List[str] = None
    team: str = "Unknown"

    COMPANY_KEY: ClassVar[str] = "salesforce"

    def format_message(self) -> str:
        loc_str = ", ".join(self.locations) if self.locations else "Unknown"
        return (
            f"📣 Salesforce Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Locations: {loc_str}\n"
            f"👨‍💻 Team: {self.team}\n"
            f"🔗 URL: {self.url}\n"
            "----------------------"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "url": self.url,
            "locations": self.locations or [],
            "team": self.team,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SalesforceJob":
        return cls(
            job_id=d.get("job_id") or "",
            title=d.get("title", "Unknown"),
            url=d.get("url", ""),
            locations=d.get("locations", []) or [],
            team=d.get("team", "Unknown"),
        )
