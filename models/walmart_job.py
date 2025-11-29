from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from models.base_job import BaseJob


@dataclass
class WalmartJob(BaseJob):
    job_posting_title: str = "Unknown"
    brand: str = "Unknown"
    areas: Tuple[str, ...] = ()
    categories: Tuple[str, ...] = ()
    employment_types: Tuple[str, ...] = ()
    population: str | None = None
    additional_locations: Tuple[str, ...] = ()
    skills: Tuple[str, ...] = ()

    COMPANY_KEY: str = "walmart"

    def format_message(self) -> str:
        loc = self.location or "Unknown"
        areas = ", ".join(self.areas) if self.areas else "Unknown"
        cats = ", ".join(self.categories) if self.categories else "Unknown"
        types = ", ".join(self.employment_types) if self.employment_types else "Unknown"
        addl = ", ".join(self.additional_locations) if self.additional_locations else "None"
        skills = ", ".join(self.skills) if self.skills else "None"
        return (
            "📣 Walmart Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"🔹 Posting: {self.job_posting_title}\n"
            f"🏢 Brand: {self.brand}\n"
            f"📍 Location: {loc}\n"
            f"🗺️ Areas: {areas}\n"
            f"🗂️ Categories: {cats}\n"
            f"🕒 Employment Type: {types}\n"
            f"👥 Population: {self.population or 'Unknown'}\n"
            f"📌 Additional Locations: {addl}\n"
            f"🧠 Skills: {skills}\n"
            f"🔗 URL: {self.url}\n"
            "----------------------"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "job_posting_title": self.job_posting_title,
            "brand": self.brand,
            "areas": list(self.areas),
            "categories": list(self.categories),
            "employment_types": list(self.employment_types),
            "population": self.population,
            "additional_locations": list(self.additional_locations),
            "skills": list(self.skills),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WalmartJob":
        def _tuple(key: str) -> Tuple[str, ...]:
            raw = data.get(key) or []
            if isinstance(raw, (list, tuple)):
                return tuple(str(v) for v in raw if isinstance(v, str))
            return ()

        return cls(
            job_id=data.get("job_id") or data.get("jobId") or "",
            title=data.get("title", "Unknown"),
            url=data.get("url", ""),
            location=data.get("location") or "Unknown",
            job_posting_title=data.get("job_posting_title") or data.get("jobPostingTitle", "Unknown"),
            brand=data.get("brand", "Unknown"),
            areas=_tuple("areas"),
            categories=_tuple("categories"),
            employment_types=_tuple("employment_types"),
            population=data.get("population"),
            additional_locations=_tuple("additional_locations"),
            skills=_tuple("skills"),
        )
