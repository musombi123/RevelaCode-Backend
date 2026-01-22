import json
import os
import hashlib
import random
import threading
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from .user_data.user_data import save_user_data
from .mailer import send_email_code

# ============================================
# File paths
# ============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
COMMUNITY_POSTS_FILE = os.path.join(BASE_DIR, "community_posts.json")

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

def get_user_role(contact: str) -> str:
    users = load_users()
    return users.get(contact, {}).get("role", "guest")

def get_user_from_token(auth_header: str):
    if not auth_header:
        return None
    parts = auth_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        users = load_users()
        return users.get(parts[1])
    return None

def load_posts():
    if os.path.exists(COMMUNITY_POSTS_FILE):
        with open(COMMUNITY_POSTS_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_posts(posts):
    with file_lock:
        with open(COMMUNITY_POSTS_FILE, "w") as f:
            json.dump(posts, f, indent=2)

# ============================================
# REGISTER + SEND VERIFICATION CODE
# ============================================

@auth_bp.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}

    full_name = data.get("full_name", "").strip()
    contact = data.get("contact", "").strip()  # email
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

    users[contact] = {
        "full_name": full_name,
        "contact": contact,
        "password": hash_password(password),
        "role": "normal",
        "verified": False,
        "verification_code": code,
        "code_expires": (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    }

    save_users(users)

    save_user_data(
        contact,
        history=[],
        settings={"theme": "light", "linked_accounts": []}
    )

    send_email_code(contact, code)

    return jsonify({
        "success": True,
        "message": "Verification code sent",
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
    user["verification_code"] = code
    user["code_expires"] = (datetime.utcnow() + timedelta(minutes=10)).isoformat()

    save_users(users)
    send_email_code(contact, code)

    return jsonify({"success": True, "message": "Code resent"}), 200

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

# ============================================
# LOGIN (BLOCK UNVERIFIED USERS)
# ============================================

@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}

    contact = data.get("contact", "").strip()
    password = data.get("password", "").strip()

    if not contact or not password:
        return jsonify({"success": False, "message": "Contact and password required."}), 400

    users = load_users()
    hashed = hash_password(password)

    user = users.get(contact)
    if not user or user["password"] != hashed:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

    if not user.get("verified"):
        return jsonify({"success": False, "message": "Account not verified"}), 403

    return jsonify({
        "success": True,
        "contact": contact,
        "full_name": user["full_name"],
        "role": user["role"]
    }), 200

# ============================================
# GUEST MODE
# ============================================

@auth_bp.route("/api/guest", methods=["GET"])
def api_guest():
    return jsonify({
        "success": True,
        "contact": "guest",
        "role": "guest",
        "message": "Guest mode: Limited access"
    }), 200
