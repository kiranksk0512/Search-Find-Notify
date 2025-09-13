import os
import boto3
from core.logger import get_company_logger

# Values come from Lambda environment variables or config.py
try:
    from config import SES_SENDER, SES_RECIPIENTS
except ImportError:
    SES_SENDER = os.environ.get("SES_SENDER")
    SES_RECIPIENTS = os.environ.get("SES_RECIPIENTS", "").split(",")

ses = boto3.client("ses")
logger = get_company_logger()

def send_email_alert(subject: str, body: str):
    """
    Send an email via AWS SES.
    - SES_SENDER: verified email or domain in SES
    - SES_RECIPIENTS: comma-separated list of emails (must be verified if in SES sandbox)
    """
    if not SES_SENDER or not SES_RECIPIENTS:
        logger.error("❌ SES_SENDER or SES_RECIPIENTS not configured")
        return

    try:
        response = ses.send_email(
            Source=SES_SENDER,
            Destination={"ToAddresses": SES_RECIPIENTS},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
        message_id = response.get("MessageId")
        logger.info(f"📧 SES email sent successfully (MessageId={message_id})")
    except Exception as e:
        logger.error(f"❌ SES email failed: {e}")
