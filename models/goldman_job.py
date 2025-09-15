from dataclasses import dataclass, field
from typing import Dict, Any, List
from models.base_job import BaseJob


def _fmt_loc(l: Dict[str, Any]) -> str:
    parts = [l.get("city"), l.get("state"), l.get("country")]
    return ", ".join([p for p in parts if p])


@dataclass
class GoldmanJob(BaseJob):
    # keep both ids around for debugging
    role_id: str = ""
    external_source_id: str = ""           # e.g., "144771"
    corporate_title: str = ""
    division: str = ""
    job_function: str = ""
    job_type_code: str = ""
    job_type_desc: str = ""
    status: str = ""
    locations: List[Dict[str, Any]] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)

    COMPANY_KEY: str = "goldman"

    def format_message(self) -> str:
        locs = ", ".join(_fmt_loc(l) for l in self.locations) if self.locations else (self.location or "N/A")
        jt = f"{self.job_type_code or ''} {f'({self.job_type_desc})' if self.job_type_desc else ''}".strip() or "N/A"
        skills_str = ", ".join(self.skills) if self.skills else "N/A"
        return (
            "🏛️ Goldman Sachs Job Alert\n"
            f"🔹 JobId: {self.job_id}  (roleId={self.role_id or 'n/a'})\n"
            f"🔹 Title: {self.title}\n"
            f"🎖 Corporate Title: {self.corporate_title or 'N/A'}\n"
            f"🏢 Division: {self.division or 'N/A'}\n"
            f"🛠 Function: {self.job_function or 'N/A'}\n"
            f"🧾 Job Type: {jt}\n"
            f"🎯 Skills: {skills_str}\n"
            f"🗺 Locations: {locs}\n"
            f"⚑ Status: {self.status or 'N/A'}\n"
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
            "role_id": self.role_id,
            "external_source_id": self.external_source_id,
            "corporate_title": self.corporate_title,
            "division": self.division,
            "job_function": self.job_function,
            "job_type_code": self.job_type_code,
            "job_type_desc": self.job_type_desc,
            "status": self.status,
            "locations": self.locations,
            "skills": list(self.skills),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GoldmanJob":
        job_id = d.get("job_id") or d.get("external_source_id") or d.get("role_id") or ""
        return cls(
            job_id=job_id,
            title=d.get("title", "Unknown"),
            url=d.get("url", ""),
            location=d.get("location", ""),
            date_posted=d.get("date_posted", ""),
            role_id=d.get("role_id", ""),
            external_source_id=d.get("external_source_id", ""),
            corporate_title=d.get("corporate_title", ""),
            division=d.get("division", ""),
            job_function=d.get("job_function", ""),
            job_type_code=d.get("job_type_code", ""),
            job_type_desc=d.get("job_type_desc", ""),
            status=d.get("status", ""),
            locations=list(d.get("locations") or []),
            skills=list(d.get("skills") or []),
        )
