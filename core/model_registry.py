from typing import Type, Dict
from models.base_job import BaseJob
from models.meta_job import MetaJob
from models.google_job import GoogleJob
from models.apple_job import AppleJob
from models.amazon_job import AmazonJob
from models.netflix_job import NetflixJob

REGISTRY: Dict[str, Type[BaseJob]] = {
    MetaJob.COMPANY_KEY: MetaJob,
    GoogleJob.COMPANY_KEY: GoogleJob,
    AppleJob.COMPANY_KEY: AppleJob,
    AmazonJob.COMPANY_KEY: AmazonJob,
    NetflixJob.COMPANY_KEY: NetflixJob,
}

def get_model_cls(company: str) -> Type[BaseJob]:
    try:
        return REGISTRY[company]
    except KeyError:
        raise ValueError(f"No model registered for company '{company}'")
