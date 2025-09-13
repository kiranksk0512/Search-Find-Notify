from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from models.base_job import BaseJob


@dataclass
class MicrosoftJob(BaseJob):
    COMPANY_KEY: str = "microsoft"

    # Rich fields from properties{}
    profession: Optional[str] = None
    discipline: Optional[str] = None
    role_type: Optional[str] = None
    employment_type: Optional[str] = None
    job_type: Optional[str] = None
    worksite_flexibility: Optional[str] = None
    education_level: Optional[str] = None
    primary_location: Optional[str] = None
    locations: List[str] = field(default_factory=list)
    description_html: Optional[str] = None

    # Extras we’re adding
    last_updated: Optional[str] = None          # if the API ever provides it
    experience_track: Optional[str] = None      # "Experienced professionals" | "Students and graduates"

    def format_message(self) -> str:
        """Render all captured fields; omit missing ones."""
        lines = [
            "🪟 Microsoft Job Alert",
            f"🔹 JobId: {self.job_id}",
            f"🔹 Title: {self.title}",
            f"🗓 Posted: {self.date_posted or 'Unknown'}",
        ]
        if self.last_updated:        lines.append(f"🗓 Updated: {self.last_updated}")
        if self.url:                 lines.append(f"🔗 URL: {self.url}")
        if self.experience_track:    lines.append(f"🎯 Experience Track: {self.experience_track}")

        # Base/compat fields
        if self.location:            lines.append(f"📍 Location: {self.location}")

        # Rich fields
        if self.primary_location:    lines.append(f"📍 Primary Location: {self.primary_location}")
        if self.locations:           lines.append(f"📍 Locations: {', '.join(self.locations)}")
        if self.profession:          lines.append(f"🏷 Profession: {self.profession}")
        if self.discipline:          lines.append(f"🏷 Discipline: {self.discipline}")
        if self.role_type:           lines.append(f"👤 Role Type: {self.role_type}")
        if self.employment_type:     lines.append(f"🧾 Employment Type: {self.employment_type}")
        if self.job_type:            lines.append(f"🧩 Job Type: {self.job_type}")
        if self.worksite_flexibility:
                                     lines.append(f"🏢 Worksite Flexibility: {self.worksite_flexibility}")
        if self.education_level:     lines.append(f"🎓 Education Level: {self.education_level}")

        lines.append("----------------------")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Persist both base and Microsoft-specific fields to avoid losing data on rehydrate."""
        return {
            # BaseJob fields
            "job_id": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "team": self.team,
            "date_posted": self.date_posted,

            # Microsoft fields
            "profession": self.profession,
            "discipline": self.discipline,
            "role_type": self.role_type,
            "employment_type": self.employment_type,
            "job_type": self.job_type,
            "worksite_flexibility": self.worksite_flexibility,
            "education_level": self.education_level,
            "primary_location": self.primary_location,
            "locations": list(self.locations) if self.locations else [],
            "description_html": self.description_html,
            "last_updated": self.last_updated,
            "experience_track": self.experience_track,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MicrosoftJob":
        return cls(
            # Base fields (keep them populated!)
            job_id=d.get("job_id") or d.get("jobId") or d.get("id") or "",
            title=d.get("title", "Unknown"),
            url=d.get("url", ""),
            location=d.get("location"),
            team=d.get("team"),  # we’ll also set this in the scraper normalize for stability
            date_posted=d.get("date_posted") or d.get("posted") or d.get("date"),

            # Microsoft fields
            profession=d.get("profession"),
            discipline=d.get("discipline"),
            role_type=d.get("role_type"),
            employment_type=d.get("employment_type"),
            job_type=d.get("job_type"),
            worksite_flexibility=d.get("worksite_flexibility"),
            education_level=d.get("education_level"),
            primary_location=d.get("primary_location"),
            locations=list(d.get("locations", []) or []),
            description_html=d.get("description_html"),
            last_updated=d.get("last_updated"),
            experience_track=d.get("experience_track"),
        )
