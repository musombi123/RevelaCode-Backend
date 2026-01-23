# backend/verify.py
import os
import json
import random
import smtplib
from flask import Blueprint, request, jsonify
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from dotenv import load_dotenv

# ================== LOAD ENV ==================
load_dotenv()

# ================== BLUEPRINT ==================
verify_bp = Blueprint("verify", __name__)

# ================== PATHS ==================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "user_data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

# ================== HELPERS ==================
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

def generate_code():
    return str(random.randint(100000, 999999))

# ================== EMAIL ==================
def send_email(contact: str, code: str) -> bool:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")

    if not all([host, user, password]):
        print("❌ SMTP config missing")
        return False

    try:
        msg = MIMEText(
            f"""RevelaCode Verification Code

Your verification code is: {code}

This code expires in 10 minutes.
If you didn’t request this, ignore this email.
"""
        )
        msg["Subject"] = "RevelaCode Verification Code"
        msg["From"] = user
        msg["To"] = contact

        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)

        print(f"✅ Verification email sent to {contact}")
        return True

    except Exception as e:
        print("❌ Email error:", e)
        return False

# ================== ROUTES ==================

@verify_bp.route("/api/request-code", methods=["POST"])
def request_code():
    data = request.get_json(silent=True) or {}
    contact = (data.get("contact") or "").strip()

    if not contact:
        return jsonify({"message": "❌ Contact (email) required"}), 400

    users = load_users()

    if contact not in users:
        return jsonify({"message": "❌ Account not found. Please register first."}), 404

    code = generate_code()
    expires = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

    users[contact]["verification_code"] = code
    users[contact]["code_expires"] = expires
    users[contact]["verified"] = False

    save_users(users)

    sent = send_email(contact, code)

    return jsonify({
        "message": "✅ Verification code sent" if sent else "⚠ Code generated (SMTP failed)",
        "sent": sent,
        "debug_code": None if sent else code
    }), 200


@verify_bp.route("/api/verify", methods=["POST"])
def verify_account():
    data = request.get_json(silent=True) or {}
    contact = (data.get("contact") or "").strip()
    code = (data.get("code") or "").strip()

    if not contact or not code:
        return jsonify({"message": "❌ Contact and code required"}), 400

    users = load_users()
    user = users.get(contact)

    if not user:
        return jsonify({"message": "❌ Account not found"}), 404

    if user.get("verified"):
        return jsonify({"message": "✅ Already verified"}), 200

    if user.get("verification_code") != code:
        return jsonify({"message": "❌ Invalid code"}), 400

    if datetime.utcnow() > datetime.fromisoformat(user["code_expires"]):
        return jsonify({"message": "❌ Code expired"}), 400

    user["verified"] = True
    user.pop("verification_code", None)
    user.pop("code_expires", None)

    save_users(users)

    return jsonify({"message": "✅ Account verified successfully"}), 200


@verify_bp.route("/api/verify-test", methods=["GET"])
def verify_test():
    return jsonify({"status": "verify service live (email-only)"}), 200
