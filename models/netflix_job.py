from models.base_job import BaseJob

class NetflixJob(BaseJob):
    def __init__(self, job_id, title, url, date_posted, location="USA",
                 ats_job_id="", business_unit="", department="", display_job_id="",
                 is_private=False, created_date="", updated_date="", type="", work_location_option="",
                 locations=None):
        super().__init__(job_id, title, url, date_posted) 
        self.location = location
        self.ats_job_id = ats_job_id
        self.business_unit = business_unit
        self.department = department
        self.display_job_id = display_job_id
        self.is_private = is_private
        self.created_date = created_date
        self.updated_date = updated_date
        self.type = type
        self.work_location_option = work_location_option
        self.locations = locations or []  # ensure it's always a list

    def format_message(self) -> str:
        return (
            f"🎬 Netflix Job Alert\n"
            f"🔹 JobId: {self.job_id}\n"
            f"🆔 Display Job ID: {self.display_job_id}\n"
            f"🆔 ATS Job ID: {self.ats_job_id}\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {self.location}\n"
            f"📍 Locations: {', '.join(self.locations) if self.locations else 'N/A'}\n"
            f"🏢 Department: {self.department}\n"
            f"💼 Business Unit: {self.business_unit}\n"
            f"🗓 Created: {self.created_date}\n"
            f"🗓 Updated: {self.updated_date}\n"
            f"🗓 Is Private: {self.is_private}\n"
            f"⚙️ Type: {self.type} | Work option: {self.work_location_option}\n"
            f"🔗 URL: {self.url}\n"
            "----------------------"
        )

    def to_dict(self) -> dict:
        return {
            "jobId": self.job_id,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "posted": self.date_posted,
            "ats_job_id": self.ats_job_id,
            "business_unit": self.business_unit,
            "department": self.department,
            "display_job_id": self.display_job_id,
            "is_private": self.is_private,
            "t_create": self.created_date,
            "t_update": self.updated_date,
            "type": self.type,
            "work_location_option": self.work_location_option,
            "locations": self.locations
        }
