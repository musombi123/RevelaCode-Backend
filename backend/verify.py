import os
import json
import random
import smtplib
from flask import Blueprint, request, jsonify
from email.mime.text import MIMEText
from dotenv import load_dotenv
from datetime import datetime, timedelta

# ------------------ LOAD ENV ------------------
load_dotenv()

# ------------------ BLUEPRINT ------------------
verify_bp = Blueprint("verify", __name__)

# ------------------ PATHS ------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "user_data", "users.json")
os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)

# ------------------ HELPER FUNCTIONS ------------------
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_users(users):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

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
    """Send verification code via email only"""
    return send_email(contact, code)

# ------------------ ROUTES ------------------
@verify_bp.route("/api/send-code", methods=["POST"])
def send_code():
    try:
        data = request.get_json(force=True)
        contact = (data.get("contact") or "").strip()

        if not contact:
            return jsonify({"message": "❌ Contact is required"}), 400

        users = load_users()
        if contact not in users:
            return jsonify({"message": "❌ Account not found"}), 404

        # Generate a fresh OTP every time
        code = str(random.randint(100000, 999999))
        users[contact]["pending_code"] = code
        users[contact]["code_expires"] = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        users[contact]["verified"] = False
        save_users(users)

        sent = send_code_to_contact(contact, code)
        if not sent:
            return jsonify({"message": "❌ Failed to send verification code"}), 500

        return jsonify({"message": f"📩 Verification code sent to {contact}"}), 200

    except Exception as e:
        return jsonify({"message": f"❌ {e}"}), 500

@verify_bp.route("/api/verify-code", methods=["POST"])
def verify_code():
    try:
        data = request.get_json(force=True)
        contact = (data.get("contact") or "").strip()
        code = (data.get("code") or "").strip()

        if not contact or not code:
            return jsonify({"message": "❌ Contact and code are required"}), 400

        users = load_users()
        if contact not in users:
            return jsonify({"message": "❌ Account not found"}), 404

        user = users[contact]

        if datetime.utcnow() > datetime.fromisoformat(user.get("code_expires", "1970-01-01T00:00:00")):
            return jsonify({"message": "❌ Code expired"}), 400

        if user.get("pending_code") != code:
            return jsonify({"message": "❌ Invalid code"}), 400

        user["verified"] = True
        user.pop("pending_code", None)
        user.pop("code_expires", None)
        save_users(users)

        return jsonify({"message": "✅ Account verified successfully"}), 200

    except Exception as e:
        return jsonify({"message": f"❌ {e}"}), 500

# ------------------ TEST ROUTE ------------------
@verify_bp.route("/api/test", methods=["GET"])
def test_verify():
    return jsonify({"message": "verify_bp is live!"}), 200
