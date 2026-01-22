# backend/auth_gate.py
import json
import os
import hashlib
import random
import threading
import smtplib
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from email.mime.text import MIMEText
from dotenv import load_dotenv
from .user_data import save_user_data

# ------------------ LOAD ENV ------------------
load_dotenv()

# ------------------ FILE PATHS ------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
COMMUNITY_POSTS_FILE = os.path.join(BASE_DIR, "community_posts.json")
file_lock = threading.Lock()

# ------------------ BLUEPRINT ------------------
auth_bp = Blueprint("auth", __name__)

# ------------------ HELPERS ------------------
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_users(users):
    with file_lock:
        with open(USERS_FILE, "w") as f:
            json.dump(users, f, indent=2)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_code():
    return str(random.randint(100000, 999999))

def send_email(contact: str, code: str) -> bool:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")

    if not host or not user or not password:
        print("SMTP not configured correctly.")
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
    """Currently email-only."""
    return send_email(contact, code)

# ------------------ ROUTES ------------------
@auth_bp.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    full_name = data.get("full_name", "").strip()
    contact = data.get("contact", "").strip()
    password = data.get("password", "").strip()
    confirm_password = data.get("confirm_password", "").strip()

    if not full_name or not contact or not password:
        return jsonify({"success": False, "message": "All fields are required."}), 400
    if password != confirm_password:
        return jsonify({"success": False, "message": "Passwords do not match."}), 400

    users = load_users()
    if contact in users:
        return jsonify({"success": False, "message": "Account already exists."}), 400

    code = generate_code()
    code_expires = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    users[contact] = {
        "full_name": full_name,
        "contact": contact,
        "password": hash_password(password),
        "role": "normal",
        "verified": False,
        "verification_code": code,
        "code_expires": code_expires
    }
    save_users(users)

    code_sent = send_code_to_contact(contact, code)

    save_user_data(
        contact,
        history=[],
        settings={"theme": "light", "linked_accounts": []}
    )

    return jsonify({
        "success": True,
        "message": "Verification code sent" if code_sent else "Verification code generated (debug mode)",
        "contact": contact,
        "debug_code": code if not code_sent else None
    }), 201

@auth_bp.route("/api/resend-code", methods=["POST"])
def resend_code():
    data = request.get_json(silent=True) or {}
    contact = data.get("contact", "").strip()
    users = load_users()
    user = users.get(contact)

    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404
    if user.get("verified"):
        return jsonify({"success": False, "message": "Already verified"}), 400

    code = generate_code()
    code_expires = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    user["verification_code"] = code
    user["code_expires"] = code_expires
    save_users(users)
    send_code_to_contact(contact, code)

    return jsonify({"success": True, "message": "Code resent"}), 200

@auth_bp.route("/api/verify", methods=["POST"])
def verify_account():
    data = request.get_json(silent=True) or {}
    contact = data.get("contact", "").strip()
    code = data.get("code", "").strip()
    users = load_users()
    user = users.get(contact)

    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404
    if user.get("verified"):
        return jsonify({"success": True, "message": "Already verified"}), 200
    if user.get("verification_code") != code:
        return jsonify({"success": False, "message": "Invalid code"}), 400
    if datetime.utcnow() > datetime.fromisoformat(user["code_expires"]):
        return jsonify({"success": False, "message": "Code expired"}), 400

    user["verified"] = True
    user.pop("verification_code", None)
    user.pop("code_expires", None)
    save_users(users)

    return jsonify({"success": True, "message": "Account verified"}), 200

@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    contact = data.get("contact", "").strip()
    password = data.get("password", "").strip()

    if not contact or not password:
        return jsonify({"success": False, "message": "Contact and password required."}), 400

    users = load_users()
    user = users.get(contact)
    if not user or user["password"] != hash_password(password):
        return jsonify({"success": False, "message": "Invalid credentials"}), 401
    if not user.get("verified"):
        return jsonify({"success": False, "message": "Account not verified"}), 403

    return jsonify({
        "success": True,
        "contact": contact,
        "full_name": user["full_name"],
        "role": user["role"]
    }), 200

@auth_bp.route("/api/guest", methods=["GET"])
def api_guest():
    return jsonify({
        "success": True,
        "contact": "guest",
        "role": "guest",
        "message": "Guest mode: Limited access"
    }), 200
