from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from models.base_job import BaseJob

@dataclass
class AdobeJob(BaseJob):
    COMPANY_KEY: str = "adobe"

    # Adobe-specific fields
    category: Optional[str] = None
    date_created: Optional[str] = None
    department: Optional[str] = None
    hiring_manager: Optional[str] = None
    is_multi_category: Optional[bool] = None
    is_multi_location: Optional[bool] = None
    job_posting_end_date: Optional[str] = None
    job_seq_no: Optional[str] = None
    visibility_type: Optional[str] = None
    country: Optional[str] = None
    experience_level: Optional[str] = None
    ml_skills: List[str] = field(default_factory=list)

    def format_message(self) -> str:
        """Pretty print for emails or logs."""
        lines = [
            "🎨 Adobe Job Alert",
            f"🔹 Job ID: {self.job_id}",
            f"🔹 Title: {self.title}",
            f"🗓 Posted: {self.date_posted or 'Unknown'}",
        ]
        if self.url:
            lines.append(f"🔗 URL: {self.url}")
        if self.location:
            lines.append(f"📍 Location: {self.location}")
        if self.category:
            lines.append(f"🏷 Category: {self.category}")
        if self.hiring_manager:
            lines.append(f"👤 Hiring Manager: {self.hiring_manager}")
        if self.visibility_type:
            lines.append(f"🔒 Visibility: {self.visibility_type}")
        if self.job_posting_end_date:
            lines.append(f"🗓 Ends On: {self.job_posting_end_date}")

        # New section for ML skills
        if self.ml_skills:
            skills_display = ", ".join(self.ml_skills[:8])
            lines.append(f"🧠 Skills: {skills_display}")

        lines.append("----------------------")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "team": self.team,
            "date_posted": self.date_posted,
            "category": self.category,
            "date_created": self.date_created,
            "department": self.department,
            "hiring_manager": self.hiring_manager,
            "is_multi_category": self.is_multi_category,
            "is_multi_location": self.is_multi_location,
            "job_posting_end_date": self.job_posting_end_date,
            "job_seq_no": self.job_seq_no,
            "visibility_type": self.visibility_type,
            "country": self.country,
            "experience_level": self.experience_level,
            "ml_skills": self.ml_skills,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AdobeJob":
        return cls(
            job_id=d.get("job_id") or d.get("jobId") or "",
            title=d.get("title", ""),
            url=d.get("url", ""),
            location=d.get("location", ""),
            team=d.get("team"),
            date_posted=d.get("date_posted") or d.get("postedDate"),
            category=d.get("category"),
            date_created=d.get("date_created"),
            department=d.get("department"),
            hiring_manager=d.get("hiring_manager"),
            is_multi_category=d.get("is_multi_category"),
            is_multi_location=d.get("is_multi_location"),
            job_posting_end_date=d.get("job_posting_end_date"),
            job_seq_no=d.get("job_seq_no"),
            visibility_type=d.get("visibility_type"),
            country=d.get("country"),
            experience_level=d.get("experience_level"),
            ml_skills=list(d.get("ml_skills", []) or []),
        )
