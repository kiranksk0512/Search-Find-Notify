from typing import Type, Dict
from models.base_job import BaseJob
from models.meta_job import MetaJob
from models.google_job import GoogleJob
from models.apple_job import AppleJob
from models.amazon_job import AmazonJob
from models.netflix_job import NetflixJob
from models.microsoft_job import MicrosoftJob
from models.goldman_job import GoldmanJob
from models.oracle_job import OracleJob
from models.mergedblackrock_job import MergedBlackRockJob
from models.adobe_job import AdobeJob
from models.databricks_job import DatabricksJob
from models.microsoftnew_job import MicrosoftNewJob
from models.salesforce_job import SalesforceJob
from models.nutanix_job import NutanixJob
from models.intuit_job import IntuitJob
from models.cisco_job import CiscoJob
from models.walmart_job import WalmartJob

REGISTRY: Dict[str, Type[BaseJob]] = {
    MetaJob.COMPANY_KEY: MetaJob,
    GoogleJob.COMPANY_KEY: GoogleJob,
    AppleJob.COMPANY_KEY: AppleJob,
    AmazonJob.COMPANY_KEY: AmazonJob,
    NetflixJob.COMPANY_KEY: NetflixJob,
    MicrosoftJob.COMPANY_KEY: MicrosoftJob,
    GoldmanJob.COMPANY_KEY: GoldmanJob,
    OracleJob.COMPANY_KEY: OracleJob,
    MergedBlackRockJob.COMPANY_KEY: MergedBlackRockJob,
    AdobeJob.COMPANY_KEY: AdobeJob,
    DatabricksJob.COMPANY_KEY: DatabricksJob,
    MicrosoftNewJob.COMPANY_KEY: MicrosoftNewJob,
    SalesforceJob.COMPANY_KEY: SalesforceJob,
    NutanixJob.COMPANY_KEY: NutanixJob,
    IntuitJob.COMPANY_KEY: IntuitJob,
    CiscoJob.COMPANY_KEY: CiscoJob,
    WalmartJob.COMPANY_KEY: WalmartJob,
}

def get_model_cls(company: str) -> Type[BaseJob]:
    try:
        return REGISTRY[company]
    except KeyError:
        raise ValueError(f"No model registered for company '{company}'")
