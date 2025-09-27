from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from models.base_job import BaseJob

@dataclass
class OracleJob(BaseJob):
    # ---- Fields EXACTLY as set in _normalize_requisition ----
    # (No oracle_id here, because the normalizer doesn’t pass it.)

    # Simple scalars
    language: str = ""
    geography_id: Optional[int] = None
    workplace_type: str = ""                 # e.g., ""
    workplace_type_code: str = ""            # e.g., "ORA_ON_SITE"
    hot_job: bool = False                    # HotJobFlag
    trending_flag: bool = False                   # TrendingFlag
    be_first_to_apply_flag: bool = False                   # BeFirstToApplyFlag
    short_description: str = ""              # ShortDescriptionStr
    primary_location: Optional[str] = None   # PrimaryLocation
    posting_end_date: Optional[str] = None   # PostingEndDate

    # Collections
    secondary_locations: List[Dict[str, Any]] = field(default_factory=list)
    other_work_locations: List[Dict[str, Any]] = field(default_factory=list)
    work_location: List[Dict[str, Any]] = field(default_factory=list)
    requisition_flex_fields: List[Dict[str, Any]] = field(default_factory=list)

    # Business attributes
    business_unit: Optional[str] = None
    contract_type: Optional[str] = None
    department: Optional[str] = None
    external_qualifications: Optional[str] = None
    external_responsibilities: Optional[str] = None
    job_family: Optional[str] = None
    job_function: Optional[str] = None
    job_schedule: Optional[str] = None
    job_shift: Optional[str] = None
    job_type: Optional[str] = None
    legal_employer: Optional[str] = None
    manager_level: Optional[str] = None
    study_level: Optional[str] = None
    worker_type: Optional[str] = None

    COMPANY_KEY: str = "oracle"

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "language": self.language,
            "geography_id": self.geography_id,
            "workplace_type": self.workplace_type,
            "workplace_type_code": self.workplace_type_code,
            "hot_job": self.hot_job,
            "trending_flag": self.trending_flag,
            "be_first_to_apply_flag": self.be_first_to_apply_flag,
            "short_description": self.short_description,
            "primary_location": self.primary_location,
            "posting_end_date": self.posting_end_date,

            "secondary_locations": list(self.secondary_locations),
            "other_work_locations": list(self.other_work_locations),
            "work_location": list(self.work_location),
            "requisition_flex_fields": list(self.requisition_flex_fields),

            "business_unit": self.business_unit,
            "contract_type": self.contract_type,
            "department": self.department,
            "external_qualifications": self.external_qualifications,
            "external_responsibilities": self.external_responsibilities,
            "job_family": self.job_family,
            "job_function": self.job_function,
            "job_schedule": self.job_schedule,
            "job_shift": self.job_shift,
            "job_type": self.job_type,
            "legal_employer": self.legal_employer,
            "manager_level": self.manager_level,
            "study_level": self.study_level,
            "worker_type": self.worker_type,
        })
        return base

    # Inherit BaseJob.from_dict exactly as-is (only base fields are required to rehydrate)
    # def from_dict(...): pass

    def format_message(self) -> str:
            """Pretty print all fields for debugging or digests."""
            return (
                "🟠 Oracle Job\n"
                f"🔹 JobId: {self.job_id}\n"
                f"🔹 Title: {self.title}\n"
                f"🔗 URL: {self.url}\n"
                f"📍 Location: {self.location or self.primary_location or 'N/A'}\n"
                f"🗓 Posted: {self.date_posted or 'Unknown'} | Ends: {self.posting_end_date or 'N/A'}\n"
                f"🌐 Language: {self.language}\n"
                f"🌍 Geography ID: {self.geography_id}\n"
                f"🏢 WorkplaceType: {self.workplace_type} ({self.workplace_type_code})\n"
                f"🔥 HotJob: {self.hot_job} | 📈 TrendingFlag: {self.trending_flag} | 🥇 BeFirstToApplyFlag: {self.be_first_to_apply_flag}\n"
                f"📝 Short Description: {self.short_description}\n"
                f"🏢 BusinessUnit: {self.business_unit}\n"
                f"📑 ContractType: {self.contract_type}\n"
                f"🏬 Department: {self.department}\n"
                f"🎓 StudyLevel: {self.study_level}\n"
                f"👔 ManagerLevel: {self.manager_level}\n"
                f"👥 WorkerType: {self.worker_type}\n"
                f"⚖️ LegalEmployer: {self.legal_employer}\n"
                f"📂 JobFamily: {self.job_family}\n"
                f"⚙️ JobFunction: {self.job_function}\n"
                f"📅 JobSchedule: {self.job_schedule}\n"
                f"🌙 JobShift: {self.job_shift}\n"
                f"🛠 JobType: {self.job_type}\n"
                f"📜 ExternalQualifications: {self.external_qualifications}\n"
                f"🛠 ExternalResponsibilities: {self.external_responsibilities}\n"
                f"🏠 SecondaryLocations: {self.secondary_locations}\n"
                f"🏠 OtherWorkLocations: {self.other_work_locations}\n"
                f"🏠 WorkLocation: {self.work_location}\n"
                f"🔧 RequisitionFlexFields: {self.requisition_flex_fields}\n"
                "----------------------"
            )
