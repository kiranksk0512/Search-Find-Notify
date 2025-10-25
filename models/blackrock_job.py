from models.base_job import BaseJob
from typing import Dict, Any
from dataclasses import dataclass, field

@dataclass
class BlackrockJob(BaseJob):
    """
    Representation of a single BlackRock career posting.

    Each job advertises an open role on BlackRock's careers site.  The
    attributes captured mirror those used across existing job models in
    this repository (for example, GoogleJob and AmazonJob), allowing
    consistent handling downstream by the notification and storage
    layers.  Additional fields may be added as necessary, but the core
    fields here cover the essentials (identifier, title, URL, posted
    date, team and location).
    """

    COMPANY_KEY: str = "blackrock"

    def format_message(self) -> str:
        """Return a formatted string suitable for email notifications."""
        return (
            f" BlackRock Job Alert\n"
            f" Job ID: {self.job_id}\n"
            f" Title: {self.title}\n"
            f" Location: {self.location}\n"
            f" Team: {self.team}\n"
            f" Posted: {self.date_posted}\n"
            f" URL: {self.url}\n"
            "----------------------"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a simple serialisable representation of the job."""
        return {
            "jobId": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "team": self.team,
            "posted": self.date_posted,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "blackrock":
        return cls(
            job_id=d.get("job_id") or d.get("jobId") or "",
            title=d.get("title", "Unknown"),
            url=d.get("url", ""),
            location=d.get("location", "USA"),
            team=d.get("team", "Unknown"),
            date_posted=d.get("date_posted") or d.get("posted"),
        )