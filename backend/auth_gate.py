# auth_gate.py
import json
import os
import hashlib
import random
import threading
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from .user_data import save_user_data
from .verify import send_code_to_contact

# ============================================
# File paths
# ============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
file_lock = threading.Lock()

# ============================================
# Blueprint setup
# ============================================
auth_bp = Blueprint("auth", __name__)

# ============================================
# Utility functions
# ============================================
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

# ============================================
# REGISTER + SEND VERIFICATION CODE
# ============================================
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

    # Save user before sending email
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

    # Send email only, fail registration if it doesn’t send
    try:
        send_code_to_contact(contact, code)
    except Exception as e:
        users.pop(contact, None)
        save_users(users)
        return jsonify({"success": False, "message": f"Failed to send verification email: {e}"}), 500

    # Initialize user data
    save_user_data(
        contact,
        history=[],
        settings={"theme": "light", "linked_accounts": []}
    )

    return jsonify({
        "success": True,
        "message": "Verification email sent successfully",
        "contact": contact
    }), 201

# ============================================
# RESEND VERIFICATION CODE
# ============================================
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

    try:
        send_code_to_contact(contact, code)
    except Exception as e:
        return jsonify({"success": False, "message": f"Failed to send verification email: {e}"}), 500

    return jsonify({"success": True, "message": "Verification email resent"}), 200

# ============================================
# VERIFY ACCOUNT
# ============================================
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
