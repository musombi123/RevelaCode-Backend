import os, json, random, smtplib
from flask import Blueprint, request, jsonify
from email.mime.text import MIMEText

verify_bp = Blueprint("verify", __name__)

USERS_FILE = os.path.join("user_data", "users.json")

# ------------------ OPTIONAL IMPORTS ------------------
twilio_available = True
try:
    from twilio.rest import Client
except ImportError:
    twilio_available = False

# ------------------ HELPER FUNCTIONS ------------------
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def send_sms(contact: str, code: str) -> bool:
    """Send OTP via Twilio SMS"""
    if not twilio_available:
        return False

    sid = os.environ.get("TWILIO_SID")
    auth = os.environ.get("TWILIO_AUTH")
    number = os.environ.get("TWILIO_NUMBER")

    if not sid or not auth or not number:
        return False

    try:
        client = Client(sid, auth)
        client.messages.create(
            body=f"RevelaCode verification code: {code}",
            from_=number,
            to=contact
        )
        return True
    except Exception as e:
        print("Twilio error:", e)
        return False

def send_email(contact: str, code: str) -> bool:
    """Send OTP via SMTP email"""
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")

    if not host or not user or not password:
        return False

    try:
        msg = MIMEText(f"Your RevelaCode verification code: {code}")
        msg["Subject"] = "RevelaCode Verification Code"
        msg["From"] = user
        msg["To"] = contact

        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True
    except Exception as e:
        print("SMTP error:", e)
        return False

def send_code_to_contact(contact: str, code: str) -> bool:
    """Send code to phone if starts with +, else assume email"""
    if contact.startswith("+"):
        return send_sms(contact, code)
    return send_email(contact, code)

# ------------------ ROUTES ------------------
@verify_bp.route("/api/send-code", methods=["POST"])
def send_code():
    try:
        data = request.get_json(force=True)
        contact = data.get("contact", "").strip()

        if not contact:
            return jsonify({"message": "❌ Contact is required"}), 400

        users = load_users()
        if contact not in users:
            return jsonify({"message": "❌ Account not found"}), 404

        code = str(random.randint(100000, 999999))
        users[contact]["pending_code"] = code
        users[contact]["verified"] = False
        save_users(users)

        sent = send_code_to_contact(contact, code)

        return jsonify({
            "message": "✅ Verification code sent" if sent else "✅ Verification code generated (debug mode)",
            "sent": sent,
            "debug_code": code if not sent else None
        }), 200

    except Exception as e:
        return jsonify({"message": f"❌ {e}"}), 500

@verify_bp.route("/api/verify-code", methods=["POST"])
def verify_code():
    try:
        data = request.get_json(force=True)
        contact = data.get("contact", "").strip()
        code = data.get("code", "").strip()

        if not contact or not code:
            return jsonify({"message": "❌ Contact and code are required"}), 400

        users = load_users()
        if contact not in users:
            return jsonify({"message": "❌ Account not found"}), 404

        if users[contact].get("pending_code") != code:
            return jsonify({"message": "❌ Invalid code"}), 400

        users[contact]["verified"] = True
        users[contact].pop("pending_code", None)
        save_users(users)

        return jsonify({"message": "✅ Account verified successfully"}), 200

    except Exception as e:
        return jsonify({"message": f"❌ {e}"}), 500
