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

# ------------------ ROUTES ------------------
@auth_bp.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    full_name = (data.get("full_name") or "").strip()
    contact = (data.get("contact") or "").strip()
    password = (data.get("password") or "").strip()
    confirm_password = (data.get("confirm_password") or "").strip()

    if not full_name or not contact or not password or not confirm_password:
        return jsonify({"success": False, "message": "All fields required."}), 400
    if not is_valid_email(contact):
        return jsonify({"success": False, "message": "Invalid email."}), 400
    if password != confirm_password:
        return jsonify({"success": False, "message": "Passwords do not match."}), 400
    if len(password) < 6:
        return jsonify({"success": False, "message": "Password too short."}), 400

    users = load_users()
    if contact in users:
        return jsonify({"success": False, "message": "Account exists."}), 400

    # Only register the user here; verification handled by verify.py
    users[contact] = {
        "full_name": full_name,
        "contact": contact,
        "password": hash_password(password),
        "role": "normal",
        "verified": False,
        "verification_code": None,
        "guest_trials": 0
    }

    save_users(users)
    save_user_data(contact, history=[], settings={"theme": "light", "linked_accounts": []})

    return jsonify({
        "success": True,
        "message": "Account created. Verify your email using /api/request-code.",
        "contact": contact,
        "next_step": "/api/request-code"
    }), 201

@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    contact = (data.get("contact") or "").strip()
    password = (data.get("password") or "").strip()

    if not contact or not password:
        return jsonify({"success": False, "message": "Contact and password required"}), 400
    if not is_valid_email(contact):
        return jsonify({"success": False, "message": "Invalid email"}), 400

    users = load_users()
    user = users.get(contact)
    if not user or user.get("password") != hash_password(password):
        return jsonify({"success": False, "message": "Invalid credentials"}), 401
    if not user.get("verified"):
        # Delegate verification code request to verify.py
        return jsonify({"success": False, "message": "Account not verified.", "next_step": "/api/request-code"}), 403

    return jsonify({
        "success": True,
        "contact": contact,
        "full_name": user.get("full_name"),
        "role": user.get("role", "normal")
    }), 200

@auth_bp.route("/api/guest", methods=["GET"])
def api_guest():
    """Guest mode: 3 free trials, then force register/login"""
    users = load_users()
    guest = users.get("guest", {"guest_trials": 0})
    trials = guest.get("guest_trials", 0)

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
