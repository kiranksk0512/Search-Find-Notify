from models.base_job import BaseJob

class AmazonJob(BaseJob):
    def __init__(
        self,
        job_id,
        job_code,
        title,
        url,
        date_posted,
        location,
        team,
        city="N/A",
        company="Amazon",
        role="N/A",
        employee_class="N/A",
        updated_date="Unknown",
        created_date="Unknown",
        businessCategory="N/A",
        category="N/A",
        centralRecruitmentTeam="N/A",
        hireTypeId="N/A",
        roleFungibility="N/A",
        sourceSystem="N/A"
    ):
        super().__init__(job_id, title, url, date_posted)
        self.job_code = job_code
        self.location = location
        self.team = team
        self.city = city
        self.company = company
        self.role = role
        self.employee_class = employee_class
        self.created_date = created_date
        self.updated_date = updated_date
        self.businessCategory = businessCategory
        self.category = category
        self.centralRecruitmentTeam = centralRecruitmentTeam
        self.hireTypeId = hireTypeId
        self.roleFungibility = roleFungibility
        self.sourceSystem = sourceSystem

    def format_message(self) -> str:
        return (
            f"🛒 Amazon Job Alert\n"
            f"🔹 Job ID: {self.job_id} (Code: {self.job_code})\n"
            f"🔹 Title: {self.title}\n"
            f"📍 Location: {self.location} ({self.city})\n"
            f"🏢 Company: {self.company}\n"
            f"👨‍💻 Team: {self.team} | Role: {self.role}\n"
            f"🧑‍💼 Class: {self.employee_class}\n"
            f"🗂 Category: {self.category} | Business: {self.businessCategory}\n"
            f"🌀 Recruiter Group: {self.centralRecruitmentTeam}\n"
            f"🔖 Hire Type: {self.hireTypeId} | Role Type: {self.roleFungibility}\n"
            f"🗓 Created: {self.created_date} | ♻️ Updated: {self.updated_date}\n"
            f"🔗 URL: {self.url}\n"
            f"📦 Source: {self.sourceSystem}\n"
            "----------------------"
        )

    def to_dict(self) -> dict:
        return {
            "jobId": self.job_id,
            "jobCode": self.job_code,
            "title": self.title,
            "url": self.url,
            "location": self.location,
            "city": self.city,
            "company": self.company,
            "team": self.team,
            "role": self.role,
            "employee_class": self.employee_class,
            "created": self.created_date,
            "updated": self.updated_date,
            "businessCategory": self.businessCategory,
            "category": self.category,
            "centralRecruitmentTeam": self.centralRecruitmentTeam,
            "hireTypeId": self.hireTypeId,
            "roleFungibility": self.roleFungibility,
            "sourceSystem": self.sourceSystem
        }
