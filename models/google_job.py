from models.base_job import BaseJob

class GoogleJob(BaseJob):
    def __init__(self, job_id, title, url, date_posted, team="Unknown", location="USA"):
        super().__init__(job_id, title, url, date_posted) 
        self.location = location
        self.team = team

    def format_message(self) -> str:
        return (
            f" Google Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {self.location}\n"
            f"👨‍💻 Team: {self.team}\n"
            f"🗓 Posted: {self.date_posted}\n"
            f"🔗 URL: {self.url}\n"
            "----------------------"
        )

    def to_dict(self) -> dict:
        return {
            "jobId" : self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "posted": self.date_posted,
            "team": self.team
        }