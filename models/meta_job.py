from models.base_job import BaseJob

class MetaJob(BaseJob):
    def __init__(self, job_id, title, url, date_posted="Unknown", team="Unknown", sub_teams="Unknown", location="Unknown"):
        super().__init__(job_id, title, url, date_posted)
        self.location = location
        self.team = team
        self.sub_teams = sub_teams

    def format_message(self) -> str:
        return (
            f"📣 Meta Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {self.location}\n"
            f"👨‍💻 Team: {self.team}\n"
            f"🔧 Sub-Team: {self.sub_teams}\n"
            f"🗓 Posted: {self.date_posted}\n"
            f"🔗 URL: {self.url}\n"
            "----------------------"
        )

    def to_dict(self) -> dict:
        return {
            "jobId": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "team": self.team,
            "sub_teams": self.sub_teams,
            "posted": self.date_posted
        }
