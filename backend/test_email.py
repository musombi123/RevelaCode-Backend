import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("email_test")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM")

TEST_RECIPIENT = "mellanmakenji3@gmail.com"


def send_test_email():
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_FROM
        msg["To"] = TEST_RECIPIENT
        msg["Subject"] = "RevelaCode Email Test"

        body = (
            "Hello Mellan,\n\n"
            "This is a test email from RevelaCode backend.\n\n"
            "If you received this, Gmail SMTP works on Render.\n\n"
            "- RevelaCode AI"
        )

        msg.attach(MIMEText(body, "plain"))

        logger.info(f"Connecting to {SMTP_HOST}:{SMTP_PORT}")

        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.ehlo()
        server.starttls()
        server.ehlo()

        logger.info("Logging into SMTP server...")

        server.login(SMTP_USER, SMTP_PASS)

        logger.info(f"Sending email to {TEST_RECIPIENT}...")

        server.sendmail(SMTP_FROM, TEST_RECIPIENT, msg.as_string())

        server.quit()

        logger.info("✅ Email sent successfully!")

    except Exception as e:
        logger.exception(f"❌ Email test failed: {e}")


if __name__ == "__main__":
    send_test_email()