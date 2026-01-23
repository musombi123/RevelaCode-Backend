# backend/auth_gate.py
import json
import os
import hashlib
import threading
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
        with open(USERS_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_users(users):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with file_lock:
        with open(USERS_FILE, "w") as f:
            json.dump(users, f, indent=2)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

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

    if password != confirm_password:
        return jsonify({"success": False, "message": "Passwords do not match."}), 400

    if "@" not in contact or "." not in contact:
        return jsonify({"success": False, "message": "Invalid email format."}), 400

    users = load_users()

    if contact in users:
        return jsonify({"success": False, "message": "Account already exists."}), 400

    users[contact] = {
        "full_name": full_name,
        "contact": contact,
        "password": hash_password(password),
        "role": "normal",
        "verified": False
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


@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}

    contact = (data.get("contact") or "").strip()
    password = (data.get("password") or "").strip()

    if not contact or not password:
        return jsonify({"success": False, "message": "Contact and password required."}), 400

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
