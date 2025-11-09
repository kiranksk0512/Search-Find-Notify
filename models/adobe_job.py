# models/adobe_job.py
from dataclasses import dataclass
from typing import Any, Dict, ClassVar

from models.base_job import BaseJob


@dataclass
class AdobeJob(BaseJob):
    """
    Canonical model for Adobe postings.
    job_id MUST be Adobe's real requisition id (e.g., 'R160134').
    """
    job_id: str
    title: str
    url: str
    location: str = ""
    date_posted: str = ""  # ISO: YYYY-MM-DD (your scraper already trims it)
    team: str = ""

    # Registry key for this model; not part of instance state/snapshots
    COMPANY_KEY: ClassVar[str] = "adobe"

    # Render a single-line entry WITH the link (fixes the digest's New section).
    def format_message(self) -> str:
        bits = [self.title]
        if self.team:
            bits.append(f"({self.team})")
        if self.location:
            bits.append(f"- {self.location}")
        if self.date_posted:
            bits.append(f"[{self.date_posted}]")
        line = " ".join(bits)
        return f"{line} – {self.url}" if self.url else line

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AdobeJob":
        """
        Rehydrate from stored snapshots safely.
        """
        return cls(
            job_id=str(d.get("job_id", "")),
            title=d.get("title", "") or "",
            url=d.get("url", "") or "",
            location=d.get("location", "") or "",
            date_posted=d.get("date_posted", "") or "",
            team=d.get("team", "") or "",
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Snapshot-friendly shape. Keep keys stable across companies.
        """
        return {
            "job_id": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "date_posted": self.date_posted,
            "team": self.team,
        }
    
###########################################-----------GETTING WORKDAY URLS-----------###########################################  

# # models/adobe_job.py
# from dataclasses import dataclass
# from typing import Any, Dict

# from models.base_job import BaseJob


# @dataclass
# class AdobeJob(BaseJob):
#     """
#     Canonical model for Adobe postings.
#     job_id MUST be Adobe's real requisition id (e.g., 'R160134').
#     """
#     job_id: str
#     title: str
#     url: str
#     location: str = ""
#     date_posted: str = ""  # ISO: YYYY-MM-DD
#     team: str = ""

#     # Used by registry: REGISTRY["adobe"] = AdobeJob
#     COMPANY_KEY: str = "adobe"

#     # Render a single-line entry WITH the link (fixes your digest's New section).
#     def format_message(self) -> str:
#         bits = [self.title]
#         if self.team:
#             bits.append(f"({self.team})")
#         if self.location:
#             bits.append(f"- {self.location}")
#         if self.date_posted:
#             bits.append(f"[{self.date_posted}]")
#         line = " ".join(bits)
#         return f"{line} – {self.url}" if self.url else line

#     @classmethod
#     def from_dict(cls, d: Dict[str, Any]) -> "AdobeJob":
#         """
#         Ensure we can rehydrate from stored snapshots without surprises.
#         """
#         return cls(
#             job_id=str(d.get("job_id", "")),
#             title=d.get("title", "") or "",
#             url=d.get("url", "") or "",
#             location=d.get("location", "") or "",
#             date_posted=d.get("date_posted", "") or "",
#             team=d.get("team", "") or "",
#         )

#     def to_dict(self) -> Dict[str, Any]:
#         """
#         Snapshot-friendly shape. Keep keys stable across companies.
#         """
#         return {
#             "job_id": self.job_id,
#             "title": self.title,
#             "url": self.url,
#             "location": self.location,
#             "date_posted": self.date_posted,
#             "team": self.team,
#         }
