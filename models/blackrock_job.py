from models.base_job import BaseJob


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

    def __init__(
        self,
        job_id: str,
        title: str,
        url: str,
        date_posted: str,
        team: str = "Unknown",
        location: str = "Unknown",
    ) -> None:
        # Initialise the base class with the core identifiers.  The base
        # class stores job_id, title, url and date_posted and defines
        # abstract methods that must be implemented here.
        super().__init__(job_id, title, url, date_posted)
        self.team = team
        self.location = location

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

    def to_dict(self) -> dict:
        """Return a simple serialisable representation of the job."""
        return {
            "jobId": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "team": self.team,
            "posted": self.date_posted,
        }