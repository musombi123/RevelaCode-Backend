# backend/auth_gate.py
import os
import json
import random
import hashlib
import smtplib
import threading
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from flask import Blueprint, request, jsonify
from dotenv import load_dotenv

from .user_data import save_user_data

# ================== LOAD ENV ==================
load_dotenv()

# ================== PATHS ==================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "user_data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

file_lock = threading.Lock()

# ================== BLUEPRINT ==================
auth_bp = Blueprint("auth", __name__)

# ================== HELPERS ==================
def parse_bool(value: str, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

def is_valid_email(email: str) -> bool:
    return "@" in email and "." in email and len(email) >= 6

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def generate_code() -> str:
    return str(random.randint(100000, 999999))

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

def now_utc():
    return datetime.utcnow()

def iso_in(minutes: int):
    return (now_utc() + timedelta(minutes=minutes)).isoformat()

def is_expired(iso_time: str) -> bool:
    try:
        return now_utc() > datetime.fromisoformat(iso_time)
    except Exception:
        return True

# ================== EMAIL ==================
def send_email(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()

    use_tls = parse_bool(os.environ.get("SMTP_USE_TLS"), default=True)
    use_ssl = parse_bool(os.environ.get("SMTP_USE_SSL"), default=False)

    smtp_from = os.environ.get("SMTP_FROM", user).strip()

    if not all([host, user, password]):
        return False, "SMTP config missing (SMTP_HOST / SMTP_USER / SMTP_PASS)"

    if not is_valid_email(to_email):
        return False, "Invalid email address"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_email

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

def send_verification_email(contact: str, code: str) -> tuple[bool, str]:
    subject = "RevelaCode Verification Code"
    body = f"""RevelaCode Verification Code

Your verification code is: {code}

This code expires in 10 minutes.
If you didn’t request this, ignore this email.
"""
    return send_email(contact, subject, body)

def send_reset_email(contact: str, code: str) -> tuple[bool, str]:
    subject = "RevelaCode Password Reset Code"
    body = f"""RevelaCode Password Reset

Your password reset code is: {code}

This code expires in 10 minutes.
If you didn’t request this, ignore this email.
"""
    return send_email(contact, subject, body)

# ================== CORE CODE SYSTEM ==================
def set_user_code(users: dict, contact: str, code_type: str, minutes=10) -> str:
    """
    code_type: "verify" or "reset" or "delete"
    """
    code = generate_code()
    expires = iso_in(minutes)

    if contact not in users:
        return ""

    if code_type == "verify":
        users[contact]["verification_code"] = code
        users[contact]["verification_expires"] = expires
        users[contact]["verified"] = False

    elif code_type == "reset":
        users[contact]["reset_code"] = code
        users[contact]["reset_expires"] = expires

    elif code_type == "delete":
        users[contact]["delete_code"] = code
        users[contact]["delete_expires"] = expires

    return code

def validate_user_code(user: dict, code_type: str, code: str) -> tuple[bool, str]:
    code = (code or "").strip()

    if code_type == "verify":
        saved_code = str(user.get("verification_code") or "").strip()
        expires = user.get("verification_expires")

    elif code_type == "reset":
        saved_code = str(user.get("reset_code") or "").strip()
        expires = user.get("reset_expires")

    elif code_type == "delete":
        saved_code = str(user.get("delete_code") or "").strip()
        expires = user.get("delete_expires")

    else:
        return False, "Invalid code type"

    if not saved_code or not expires:
        return False, "No code found. Request a new one."

    if saved_code != code:
        return False, "Invalid code"

    if is_expired(expires):
        return False, "Code expired"

    return True, "OK"

def clear_user_code(user: dict, code_type: str):
    if code_type == "verify":
        user.pop("verification_code", None)
        user.pop("verification_expires", None)

    elif code_type == "reset":
        user.pop("reset_code", None)
        user.pop("reset_expires", None)

    elif code_type == "delete":
        user.pop("delete_code", None)
        user.pop("delete_expires", None)

# ================== ROUTES ==================

@auth_bp.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}

    full_name = (data.get("full_name") or "").strip()
    contact = (data.get("contact") or "").strip()
    password = (data.get("password") or "").strip()
    confirm_password = (data.get("confirm_password") or "").strip()

    if not full_name or not contact or not password or not confirm_password:
        return jsonify({"success": False, "message": "All fields are required."}), 400

    if not is_valid_email(contact):
        return jsonify({"success": False, "message": "Invalid email format."}), 400

    if password != confirm_password:
        return jsonify({"success": False, "message": "Passwords do not match."}), 400

    if len(password) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters."}), 400

    users = load_users()

    if contact in users:
        return jsonify({"success": False, "message": "Account already exists."}), 400

    users[contact] = {
        "full_name": full_name,
        "contact": contact,
        "password": hash_password(password),
        "role": "normal",
        "verified": False,
        "created_at": now_utc().isoformat(),
        "guest_trials": 0
    }

    save_users(users)

    # init per-user files
    save_user_data(
        contact,
        history=[],
        settings={"theme": "light", "linked_accounts": []}
    )

    return jsonify({
        "success": True,
        "message": "Account created. Please verify your email.",
        "contact": contact,
        "next_step": "/api/request-code"
    }), 201


@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}

    contact = (data.get("contact") or "").strip()
    password = (data.get("password") or "").strip()

    if not contact or not password:
        return jsonify({"success": False, "message": "Contact and password required."}), 400

    if not is_valid_email(contact):
        return jsonify({"success": False, "message": "Invalid email format."}), 400

    users = load_users()
    user = users.get(contact)

    if not user:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    if user.get("password") != hash_password(password):
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    if not user.get("verified"):
        return jsonify({
            "success": False,
            "message": "Account not verified.",
            "next_step": "/api/request-code"
        }), 403

    return jsonify({
        "success": True,
        "contact": contact,
        "full_name": user.get("full_name"),
        "role": user.get("role", "normal")
    }), 200


@auth_bp.route("/api/guest", methods=["GET"])
def api_guest():
    users = load_users()
    guest = users.get("guest", {"guest_trials": 0})
    trials = int(guest.get("guest_trials", 0))

    if trials >= 3:
        return jsonify({
            "success": False,
            "message": "Guest trial limit reached. Please register or login."
        }), 403

    guest["guest_trials"] = trials + 1
    users["guest"] = guest
    save_users(users)

    return jsonify({
        "success": True,
        "contact": "guest",
        "role": "guest",
        "message": f"Guest mode: Limited access ({guest['guest_trials']}/3)"
    }), 200


# ================== VERIFICATION (EMAIL CODE) ==================

@auth_bp.route("/api/request-code", methods=["POST"])
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

    code = set_user_code(users, contact, code_type="verify", minutes=10)
    save_users(users)

    sent, err = send_verification_email(contact, code)

    allow_debug = parse_bool(os.environ.get("ALLOW_DEBUG_CODE"), default=False)

    response = {
        "success": True if sent else False,
        "message": "✅ Verification code sent" if sent else "⚠ Code generated but email failed",
        "sent": sent
    }

    if allow_debug:
        response["debug_code"] = code

    if not sent:
        response["error"] = err


    return jsonify(response), 200 if sent or allow_debug else 500


@auth_bp.route("/api/verify", methods=["POST"])
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

    ok, msg = validate_user_code(user, "verify", code)
    if not ok:
        return jsonify({"success": False, "message": f"❌ {msg}"}), 400

    user["verified"] = True
    clear_user_code(user, "verify")
    save_users(users)

    return jsonify({"success": True, "message": "✅ Account verified successfully"}), 200


# ================== PASSWORD RESET ==================

@auth_bp.route("/api/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True) or {}
    contact = (data.get("contact") or "").strip()

    if not contact:
        return jsonify({"success": False, "message": "❌ Contact (email) required"}), 400
    if not is_valid_email(contact):
        return jsonify({"success": False, "message": "❌ Invalid email format"}), 400

    users = load_users()
    if contact not in users:
        return jsonify({"success": False, "message": "❌ Account not found"}), 404

    code = set_user_code(users, contact, code_type="reset", minutes=10)
    save_users(users)

    sent, err = send_reset_email(contact, code)

    allow_debug = parse_bool(os.environ.get("ALLOW_DEBUG_CODE"), default=False)

    response = {
        "success": True if sent else False,
        "message": "✅ Reset code sent" if sent else "⚠ Reset code generated but email failed",
        "sent": sent
    }

    if allow_debug:
        response["debug_code"] = code

    if not sent and not allow_debug:
        response["error"] = err

    return jsonify(response), 200 if sent or allow_debug else 500


@auth_bp.route("/api/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}

    contact = (data.get("contact") or "").strip()
    code = (data.get("code") or "").strip()
    new_password = (data.get("new_password") or "").strip()
    confirm_password = (data.get("confirm_password") or "").strip()

    if not contact or not code or not new_password or not confirm_password:
        return jsonify({"success": False, "message": "❌ All fields required"}), 400
    if not is_valid_email(contact):
        return jsonify({"success": False, "message": "❌ Invalid email format"}), 400
    if len(new_password) < 6:
        return jsonify({"success": False, "message": "❌ Password must be at least 6 characters"}), 400
    if new_password != confirm_password:
        return jsonify({"success": False, "message": "❌ Passwords do not match"}), 400

    users = load_users()
    user = users.get(contact)
    if not user:
        return jsonify({"success": False, "message": "❌ Account not found"}), 404

    ok, msg = validate_user_code(user, "reset", code)
    if not ok:
        return jsonify({"success": False, "message": f"❌ {msg}"}), 400

    user["password"] = hash_password(new_password)
    clear_user_code(user, "reset")
    save_users(users)

    return jsonify({"success": True, "message": "✅ Password reset successful"}), 200


# ================== DELETE ACCOUNT ==================

@auth_bp.route("/api/delete-account", methods=["POST"])
def delete_account():
    """
    Secure delete:
    - requires contact + password
    - optional: confirm_code (if you want email-confirm delete later)
    """
    data = request.get_json(silent=True) or {}

    contact = (data.get("contact") or "").strip()
    password = (data.get("password") or "").strip()

    if not contact or not password:
        return jsonify({"success": False, "message": "❌ Contact and password required"}), 400
    if not is_valid_email(contact):
        return jsonify({"success": False, "message": "❌ Invalid email format"}), 400

    users = load_users()
    user = users.get(contact)

    if not user:
        return jsonify({"success": False, "message": "❌ Account not found"}), 404

    if user.get("password") != hash_password(password):
        return jsonify({"success": False, "message": "❌ Invalid password"}), 401

    # Delete user
    users.pop(contact, None)
    save_users(users)

    return jsonify({"success": True, "message": "✅ Account deleted successfully"}), 200


# ================== HEALTH CHECK ==================
@auth_bp.route("/api/auth-test", methods=["GET"])
def auth_test():
    return jsonify({"success": True, "status": "auth service live"}), 200
