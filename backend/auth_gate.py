import json
import os
import hashlib
import threading
from flask import Blueprint, request, jsonify
from .user_data import save_user_data

# ============================================
# File paths
# ============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
COMMUNITY_POSTS_FILE = os.path.join(BASE_DIR, "community_posts.json")

# Thread lock for safe file writes
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

def get_user_role(contact: str) -> str:
    users = load_users()
    return users.get(contact, {}).get("role", "guest")

def get_user_from_token(auth_header: str):
    """
    Extract user contact from a simple token.
    Expected header format:
       Authorization: Bearer <contact>
    NOTE: This is not secure — replace with JWT later.
    """
    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        contact = parts[1]
        users = load_users()
        if contact in users:
            return users[contact]
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
# API ROUTES
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
        return jsonify({"success": False, "message": "Account already exists with this contact."}), 400

    users[contact] = {
        "full_name": full_name,
        "contact": contact,
        "password": hash_password(password),
        "role": "normal"
    }
    save_users(users)

    # Initialize user-specific data file (if implemented)
    save_user_data(contact, history=[], settings={"theme": "light", "linked_accounts": []})

    return jsonify({"success": True, "contact": contact, "role": "normal"}), 201


@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}

    contact = data.get("contact", "").strip()
    password = data.get("password", "").strip()

    if not contact or not password:
        return jsonify({"success": False, "message": "Contact and password required."}), 400

    users = load_users()
    hashed = hash_password(password)

    if contact in users and users[contact]["password"] == hashed:
        return jsonify({
            "success": True,
            "contact": contact,
            "full_name": users[contact]["full_name"],
            "role": get_user_role(contact)
        }), 200

    return jsonify({"success": False, "message": "Invalid contact or password."}), 401


@auth_bp.route("/api/guest", methods=["GET"])
def api_guest():
    return jsonify({
        "success": True,
        "contact": "guest",
        "role": "guest",
        "message": "Guest mode: Limited access"
    }), 200
