# backend/verify.py
import os
import json
import random
import smtplib
import threading
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

file_lock = threading.Lock()

# ================== HELPERS ==================
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_users(users):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with file_lock:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)

def generate_code():
    return str(random.randint(100000, 999999))

def is_valid_email(email: str) -> bool:
    return "@" in email and "." in email and len(email) >= 6

def parse_bool(value: str, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

# ================== EMAIL ==================
def send_email(contact: str, code: str) -> tuple[bool, str]:
    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()

    use_tls = parse_bool(os.environ.get("SMTP_USE_TLS"), default=True)
    use_ssl = parse_bool(os.environ.get("SMTP_USE_SSL"), default=False)

    if not all([host, user, password]):
        return False, "SMTP config missing (SMTP_HOST / SMTP_USER / SMTP_PASS)"

    if not is_valid_email(contact):
        return False, "Invalid email address"

    subject = "RevelaCode Verification Code"
    body = f"""RevelaCode Verification Code

Your verification code is: {code}

This code expires in 10 minutes.
If you didn’t request this, ignore this email.
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = contact

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=30) as server:
                server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                if use_tls:
                    server.starttls()
                    server.ehlo()
                server.login(user, password)
                server.send_message(msg)
        return True, ""
    except Exception as e:
        return False, f"Email error: {str(e)}"

# ================== ROUTES ==================
@verify_bp.route("/api/request-code", methods=["POST"])
def request_code():
    data = request.get_json(silent=True) or {}
    contact = (data.get("contact") or "").strip()

    if not contact:
        return jsonify({"success": False, "message": "❌ Contact (email) required"}), 400
    if not is_valid_email(contact):
        return jsonify({"success": False, "message": "❌ Invalid email format"}), 400

    users = load_users()
    if contact not in users:
        return jsonify({"success": False, "message": "❌ Account not found. Please register first."}), 404

    code = generate_code()
    expires = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

    users[contact]["verification_code"] = code
    users[contact]["code_expires"] = expires
    users[contact]["verified"] = False
    save_users(users)

    sent, err = send_email(contact, code)

    allow_debug = parse_bool(os.environ.get("ALLOW_DEBUG_CODE"), default=False)

    response = {
        "success": True if sent else False,
        "message": "✅ Verification code sent" if sent else "⚠ Code generated but email failed",
        "sent": sent
    }

    if allow_debug:
        response["debug_code"] = code

    if not sent and not allow_debug:
        response["error"] = err

    return jsonify(response), 200 if sent or allow_debug else 500

@verify_bp.route("/api/verify", methods=["POST"])
def verify_account():
    data = request.get_json(silent=True) or {}
    contact = (data.get("contact") or "").strip()
    code = (data.get("code") or "").strip()

    if not contact or not code:
        return jsonify({"success": False, "message": "❌ Contact and code required"}), 400
    if not is_valid_email(contact):
        return jsonify({"success": False, "message": "❌ Invalid email format"}), 400

    users = load_users()
    user = users.get(contact)
    if not user:
        return jsonify({"success": False, "message": "❌ Account not found"}), 404
    if user.get("verified"):
        return jsonify({"success": True, "message": "✅ Already verified"}), 200

    saved_code = str(user.get("verification_code") or "").strip()
    saved_expires = user.get("code_expires")
    if not saved_code or not saved_expires:
        return jsonify({"success": False, "message": "❌ No verification code found. Request a new code."}), 400
    if saved_code != code:
        return jsonify({"success": False, "message": "❌ Invalid code"}), 400

    try:
        if datetime.utcnow() > datetime.fromisoformat(saved_expires):
            return jsonify({"success": False, "message": "❌ Code expired"}), 400
    except Exception:
        return jsonify({"success": False, "message": "❌ Code expiry data corrupted. Request a new code."}), 400

    user["verified"] = True
    user.pop("verification_code", None)
    user.pop("code_expires", None)
    save_users(users)

    return jsonify({"success": True, "message": "✅ Account verified successfully"}), 200

@verify_bp.route("/api/verify-test", methods=["GET"])
def verify_test():
    return jsonify({"success": True, "status": "verify service live (email-only)"}), 200
