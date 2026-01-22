# backend/verify.py
import os, json, random, smtplib
from flask import Blueprint, request, jsonify
from email.mime.text import MIMEText
from twilio.rest import Client
from dotenv import load_dotenv
load_dotenv()

verify_bp = Blueprint("verify", __name__)

USERS_FILE = os.path.join("backend", "user_data", "users.json")

# --- load/save users ---
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

# --- send email ---
def send_email(to_email, code):
    SMTP_HOST = os.getenv("SMTP_HOST") or "smtp.gmail.com"
    SMTP_PORT = int(os.getenv("SMTP_PORT") or 587)
    SMTP_USER = os.getenv("SMTP_USER")  # your email
    SMTP_PASS = os.getenv("SMTP_PASS")  # your app password

    msg = MIMEText(f"Your verification code is: {code}")
    msg["Subject"] = "Your Verification Code"
    msg["From"] = SMTP_USER
    msg["To"] = to_email

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print("Email send error:", e)
        return False

# --- send SMS via Twilio ---
def send_sms(to_number, code):
    try:
        TWILIO_SID = os.getenv("TWILIO_SID")
        TWILIO_AUTH = os.getenv("TWILIO_AUTH")
        TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")  # your Twilio number

        client = Client(TWILIO_SID, TWILIO_AUTH)
        message = client.messages.create(
            body=f"Your verification code is: {code}",
            from_=TWILIO_NUMBER,
            to=to_number
        )
        return True
    except Exception as e:
        print("SMS send error:", e)
        return False

# --- Send verification code ---
@verify_bp.route("/api/send-code", methods=["POST"])
def send_code():
    data = request.get_json(force=True)
    contact = data.get("contact", "").strip()

    if not contact:
        return jsonify({"message": "Contact is required"}), 400

    users = load_users()
    if contact not in users:
        return jsonify({"message": "❌ Account not found"}), 404

    code = str(random.randint(100000, 999999))
    users[contact]["pending_code"] = code
    users[contact]["verified"] = False
    save_users(users)

    # --- Send code ---
    sent = False
    if "@" in contact:
        sent = send_email(contact, code)
    else:
        sent = send_sms(contact, code)

    if not sent:
        return jsonify({"message": "❌ Failed to send verification code"}), 500

    return jsonify({
        "message": f"✅ Verification code sent to {contact}",
        "debug_code": code  # for testing only
    }), 200

# --- Verify code ---
@verify_bp.route("/api/verify-code", methods=["POST"])
def verify_code():
    data = request.get_json(force=True)
    contact = data.get("contact", "").strip()
    code = data.get("code", "").strip()

    users = load_users()
    if contact not in users:
        return jsonify({"message": "❌ Account not found"}), 404

    if users[contact].get("pending_code") != code:
        return jsonify({"message": "❌ Invalid code"}), 400

    users[contact]["verified"] = True
    users[contact].pop("pending_code", None)
    save_users(users)

    return jsonify({"message": "✅ Account verified successfully"}), 200
