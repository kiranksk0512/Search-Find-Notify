from dataclasses import dataclass
from typing import Dict, Any
from models.base_job import BaseJob


@dataclass
class AmazonJob(BaseJob):
    job_code: str = "N/A"
    location: str = "Unknown"
    team: str = "Unknown"
    city: str = "N/A"
    company: str = "Amazon"
    role: str = "N/A"
    employee_class: str = "N/A"
    created_date: str = "Unknown"
    updated_date: str = "Unknown"
    businessCategory: str = "N/A"
    category: str = "N/A"
    centralRecruitmentTeam: str = "N/A"
    hireTypeId: str = "N/A"
    roleFungibility: str = "N/A"
    sourceSystem: str = "N/A"

    COMPANY_KEY: str = "amazon"

    def format_message(self) -> str:
        return (
            f"🛒 Amazon Job Alert\n"
            f"🔹 Job ID: {self.job_id} (Code: {self.job_code})\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {self.location} ({self.city})\n"
            f"🏢 Company: {self.company}\n"
            f"👨‍💻 Team: {self.team} | Role: {self.role}\n"
            f"🧑‍💼 Class: {self.employee_class}\n"
            f"🗂 Category: {self.category} | Business: {self.businessCategory}\n"
            f"🌀 Recruiter Group: {self.centralRecruitmentTeam}\n"
            f"🔖 Hire Type: {self.hireTypeId} | Role Type: {self.roleFungibility}\n"
            f"🗓 Created: {self.created_date} | ♻️ Updated: {self.updated_date}\n"
            f"🔗 URL: {self.url}\n"
            f"📦 Source: {self.sourceSystem}\n"
            "----------------------"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_code": self.job_code,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "team": self.team,
            "city": self.city,
            "company": self.company,
            "role": self.role,
            "employee_class": self.employee_class,
            "created_date": self.created_date,
            "updated_date": self.updated_date,
            "businessCategory": self.businessCategory,
            "category": self.category,
            "centralRecruitmentTeam": self.centralRecruitmentTeam,
            "hireTypeId": self.hireTypeId,
            "roleFungibility": self.roleFungibility,
            "sourceSystem": self.sourceSystem,
            "date_posted": self.date_posted,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AmazonJob":
        return cls(
            job_id=d.get("job_id") or d.get("jobId") or "",
            job_code=d.get("job_code") or d.get("jobCode", "N/A"),
            title=d.get("title", "Unknown"),
            url=d.get("url", ""),
            location=d.get("location", "Unknown"),
            team=d.get("team", "Unknown"),
            city=d.get("city", "N/A"),
            company=d.get("company", "Amazon"),
            role=d.get("role", "N/A"),
            employee_class=d.get("employee_class", "N/A"),
            created_date=d.get("created_date") or d.get("created", "Unknown"),
            updated_date=d.get("updated_date") or d.get("updated", "Unknown"),
            businessCategory=d.get("businessCategory", "N/A"),
            category=d.get("category", "N/A"),
            centralRecruitmentTeam=d.get("centralRecruitmentTeam", "N/A"),
            hireTypeId=d.get("hireTypeId", "N/A"),
            roleFungibility=d.get("roleFungibility", "N/A"),
            sourceSystem=d.get("sourceSystem", "N/A"),
            date_posted=d.get("date_posted") or d.get("posted"),
        )
