import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER
from email.message import EmailMessage
from core.logger import get_company_logger


# def send_email_alert(company_name, new_jobs):
#     subject = f"🚨 {len(new_jobs)} New {company_name.title()} Jobs Found!"
#     body = "\n\n".join([
#         f"{job['title']}\n{job['location']}\n{job['url']}"
#         for job in new_jobs.values()
#     ])
#     body += f"\n\nChecked on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

#     msg = MIMEText(body)
#     msg['Subject'] = subject
#     msg['From'] = EMAIL_SENDER
#     msg['To'] = EMAIL_RECEIVER

#     try:
#         with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
#             server.login(EMAIL_SENDER, EMAIL_PASSWORD)
#             server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
#         print(f"📧 Email sent for {company_name}")
#     except Exception as e:
#         print(f"❌ Email failed: {e}")

def send_email_alert(subject, body):
    logger = get_company_logger()
    msg = EmailMessage()
    
    # ✅ Explicitly set content type and encoding
    msg.set_content(body, charset='utf-8')
    
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            logger.info("📧 Email sent successfully")
    except Exception as e:
        logger.error(f"❌ Email failed: {e}")