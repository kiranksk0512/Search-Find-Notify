from dataclasses import dataclass, field
from typing import Dict, Any, List
from models.base_job import BaseJob


@dataclass
class NetflixJob(BaseJob):
    location: str = "USA"
    ats_job_id: str = ""
    business_unit: str = ""
    department: str = ""
    display_job_id: str = ""
    is_private: bool = False
    created_date: str = ""
    updated_date: str = ""
    type: str = ""
    work_location_option: str = ""
    locations: List[str] = field(default_factory=list)

    COMPANY_KEY: str = "netflix"

    def format_message(self) -> str:
        locs = ", ".join(self.locations) if self.locations else "N/A"
        return (
            f"🎬 Netflix Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🆔 Display Job ID: {self.display_job_id}\n"
            f"🆔 ATS Job ID: {self.ats_job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {self.location}\n"
            f"📍 Locations: {locs}\n"
            f"🏢 Department: {self.department}\n"
            f"💼 Business Unit: {self.business_unit}\n"
            f"🗓 Created: {self.created_date}\n"
            f"🗓 Updated: {self.updated_date}\n"
            f"🔒 Is Private: {self.is_private}\n"
            f"⚙️ Type: {self.type} | Work option: {self.work_location_option}\n"
            f"🔗 URL: {self.url}\n"
            "----------------------"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "date_posted": self.date_posted,
            "ats_job_id": self.ats_job_id,
            "business_unit": self.business_unit,
            "department": self.department,
            "display_job_id": self.display_job_id,
            "is_private": self.is_private,
            "created_date": self.created_date,
            "updated_date": self.updated_date,
            "type": self.type,
            "work_location_option": self.work_location_option,
            "locations": list(self.locations) if self.locations else [],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NetflixJob":
        return cls(
            job_id=d.get("job_id") or d.get("jobId") or "",
            title=d.get("title", "Unknown"),
            url=d.get("url", ""),
            location=d.get("location", "USA"),
            date_posted=d.get("date_posted") or d.get("posted") or "",
            ats_job_id=d.get("ats_job_id", ""),
            business_unit=d.get("business_unit", ""),
            department=d.get("department", ""),
            display_job_id=d.get("display_job_id", ""),
            is_private=bool(d.get("is_private", False)),
            created_date=d.get("created_date") or d.get("t_create", ""),
            updated_date=d.get("updated_date") or d.get("t_update", ""),
            type=d.get("type", ""),
            work_location_option=d.get("work_location_option", ""),
            locations=list(d.get("locations", []) or []),
        )
