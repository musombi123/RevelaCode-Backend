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
USERS_FILE = os.path.join(BASE_DIR, "users.json")

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
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def generate_code():
    return str(random.randint(100000, 999999))

# ================== EMAIL SENDER ==================
def send_email(contact: str, code: str) -> bool:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")

    if not all([host, user, password]):
        print("❌ SMTP config missing (SMTP_HOST/SMTP_USER/SMTP_PASS)")
        return False

    try:
        msg = MIMEText(
            f"""
RevelaCode Verification Code

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

        print(f"✅ Email sent to {contact}")
        return True

    except Exception as e:
        print("❌ Email send error:", e)
        return False

# ================== ROUTES ==================

# ---- SEND / RESEND CODE ----
@verify_bp.route("/api/request-code", methods=["POST"])
def request_code():
    try:
        data = request.get_json(force=True)
        contact = (data.get("contact") or "").strip()

        if not contact:
            return jsonify({"message": "❌ Contact (email) is required"}), 400

        # basic email check (simple)
        if "@" not in contact or "." not in contact:
            return jsonify({"message": "❌ Invalid email format"}), 400

        users = load_users()

        # IMPORTANT: must exist in users.json from register
        if contact not in users:
            return jsonify({"message": "❌ Account not found. Please register first."}), 404

        # Generate OTP
        code = generate_code()
        expires = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

        # Save OTP
        users[contact]["verification_code"] = code
        users[contact]["code_expires"] = expires
        users[contact]["verified"] = False

        save_users(users)

        # Send immediately
        sent = send_email(contact, code)

        return jsonify({
            "message": "✅ Verification code sent" if sent else "⚠ Code generated but email not sent (check SMTP)",
            "sent": sent,
            "debug_code": None if sent else code
        }), 200

    except Exception as e:
        return jsonify({"message": f"❌ {e}"}), 500


# ---- VERIFY CODE ----
@verify_bp.route("/api/verify", methods=["POST"])
def verify_account():
    try:
        data = request.get_json(force=True)
        contact = (data.get("contact") or "").strip()
        code = (data.get("code") or "").strip()

        if not contact or not code:
            return jsonify({"message": "❌ Contact and code are required"}), 400

        users = load_users()
        user = users.get(contact)

        if not user:
            return jsonify({"message": "❌ Account not found"}), 404

        if user.get("verified") is True:
            return jsonify({"message": "✅ Already verified"}), 200

        saved_code = user.get("verification_code")
        expires = user.get("code_expires")

        if not saved_code or not expires:
            return jsonify({"message": "❌ No verification code requested. Use /api/request-code"}), 400

        if saved_code != code:
            return jsonify({"message": "❌ Invalid code"}), 400

        if datetime.utcnow() > datetime.fromisoformat(expires):
            return jsonify({"message": "❌ Code expired. Request a new one."}), 400

        # Mark verified
        users[contact]["verified"] = True
        users[contact].pop("verification_code", None)
        users[contact].pop("code_expires", None)

        save_users(users)

        return jsonify({"message": "✅ Account verified successfully"}), 200

    except Exception as e:
        return jsonify({"message": f"❌ {e}"}), 500


# ---- TEST ROUTE ----
@verify_bp.route("/api/verify-test", methods=["GET"])
def verify_test():
    return jsonify({"status": "verify service live (email-only)"}), 200
