import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText

# Twilio
try:
    from twilio.rest import Client
except ImportError:
    Client = None

# Load environment variables
load_dotenv()

# -------------------- TEST EMAIL --------------------
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
TEST_EMAIL_TO = SMTP_USER  # send to yourself for testing

try:
    msg = MIMEText("Test email from RevelaCode")
    msg["Subject"] = "RevelaCode SMTP Test"
    msg["From"] = SMTP_USER
    msg["To"] = TEST_EMAIL_TO

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
    print("✅ Email sent successfully!")
except Exception as e:
    print("❌ Email failed:", e)

# -------------------- TEST TWILIO --------------------
TWILIO_SID = os.environ.get("TWILIO_SID")
TWILIO_AUTH = os.environ.get("TWILIO_AUTH")
TWILIO_NUMBER = os.environ.get("TWILIO_NUMBER")
TEST_PHONE_TO = "+254742466828"  # replace with your personal number (cannot be same as Twilio number!)

if Client and TWILIO_SID and TWILIO_AUTH and TWILIO_NUMBER:
    try:
        client = Client(TWILIO_SID, TWILIO_AUTH)
        message = client.messages.create(
            body="🔔 Test SMS from RevelaCode",
            from_=TWILIO_NUMBER,
            to=TEST_PHONE_TO
        )
        print("✅ SMS sent successfully! SID:", message.sid)
    except Exception as e:
        print("❌ Twilio SMS failed:", e)
else:
    print("❌ Twilio not configured properly or missing dependencies.")
