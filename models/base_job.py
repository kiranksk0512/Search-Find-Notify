from dataclasses import dataclass
from typing import ClassVar, Dict, Any

@dataclass
class BaseJob:
    job_id: str
    title: str
    url: str
    date_posted: str | None = None
    location: str | None = None
    team: str | None = None
    sub_teams: str | None = None

    COMPANY_KEY: ClassVar[str] = "base"

    def format_message(self) -> str:
        """Default message (can be overridden per subclass)."""
        loc = self.location or "Unknown"
        team = self.team or "Unknown"
        posted = self.date_posted or "Unknown"
        return (
            f"{self.title}\n"
            f"URL: {self.url}\n"
            f"📍 Location: {loc}\n"
            f"👨‍💻 Team: {team}\n"
            f"🗓 Posted: {posted}\n"
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
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BaseJob":
        return cls(
            job_id=d.get("job_id") or d.get("jobId") or d.get("id", ""),
            title=d.get("title", "Unknown"),
            url=d.get("url", ""),
            location=d.get("location"),
            team=d.get("team"),
            sub_teams=d.get("sub_teams"),
            date_posted=d.get("date_posted") or d.get("posted"),
        )
