# backend/auth_gate.py
import json
import os
import hashlib
import threading
import random
from flask import Blueprint, request, jsonify
from dotenv import load_dotenv
from .user_data import save_user_data

# ------------------ LOAD ENV ------------------
load_dotenv()

# ------------------ PATHS ------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "user_data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
file_lock = threading.Lock()

# ------------------ BLUEPRINT ------------------
auth_bp = Blueprint("auth", __name__)

# ------------------ HELPERS ------------------
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

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def is_valid_email(email: str) -> bool:
    return "@" in email and "." in email and len(email) >= 6

def generate_code() -> str:
    return f"{random.randint(100000, 999999)}"

# ------------------ ROUTES ------------------

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
        "verification_code": None
    }

    save_users(users)

    # Initialize per-user files
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

# ------------------ REQUEST VERIFICATION CODE ------------------
@auth_bp.route("/api/request-code", methods=["POST"])
def api_request_code():
    data = request.get_json(silent=True) or {}
    contact = (data.get("contact") or "").strip()

    if not contact or not is_valid_email(contact):
        return jsonify({"success": False, "message": "Invalid contact"}), 400

    users = load_users()
    user = users.get(contact)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    code = generate_code()
    user["verification_code"] = code
    save_users(users)

    # Simulate email sending (or integrate SMTP)
    print(f"[DEV] Verification code for {contact}: {code}")

    return jsonify({
        "success": True,
        "message": f"Verification code sent to {contact} (check console in dev)."
    }), 200

# ------------------ VERIFY ------------------
@auth_bp.route("/api/verify", methods=["POST"])
def api_verify():
    data = request.get_json(silent=True) or {}
    contact = (data.get("contact") or "").strip()
    code = (data.get("code") or "").strip()

    if not contact or not code:
        return jsonify({"success": False, "message": "Contact and code required"}), 400

    users = load_users()
    user = users.get(contact)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    if user.get("verification_code") != code:
        return jsonify({"success": False, "message": "Invalid verification code"}), 400

    user["verified"] = True
    user["verification_code"] = None
    save_users(users)

    return jsonify({"success": True, "message": "Verified successfully"}), 200

# ------------------ LOGIN ------------------
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
    if not user or user.get("password") != hash_password(password):
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

# ------------------ GUEST ------------------
@auth_bp.route("/api/guest", methods=["GET"])
def api_guest():
    return jsonify({
        "success": True,
        "contact": "guest",
        "role": "guest",
        "message": "Guest mode: Limited access"
    }), 200
