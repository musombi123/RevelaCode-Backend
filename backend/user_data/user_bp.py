# backend/user_data/user_bp.py
from flask import Blueprint, request, jsonify
import os
import json
import tempfile
import shutil
import logging

# ------------------ BLUEPRINT ------------------
user_bp = Blueprint("user", __name__)

# ------------------ PATHS ------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")

# ------------------ LOGGING ------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("user_bp")

# ------------------ HELPERS ------------------
def atomic_write(filepath, data):
    """Safely write JSON data atomically."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(filepath), delete=False, encoding="utf-8") as tf:
        json.dump(data, tf, indent=2)
        tempname = tf.name
    shutil.move(tempname, filepath)
    logger.info(f"Data written to {filepath}")

def load_users():
    """Load all users from users.json"""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_users(users):
    """Save all users to users.json"""
    atomic_write(USERS_FILE, users)

def load_user_data(contact):
    """Load a single user's data (history & settings)"""
    users = load_users()
    return users.get(contact, {"history": [], "settings": {"theme": "light", "linked_accounts": []}})

def save_user_data(contact, history=None, settings=None):
    """Save a single user's history/settings"""
    users = load_users()
    if contact not in users:
        users[contact] = {"contact": contact, "history": [], "settings": {"theme": "light", "linked_accounts": []}}
    if history is not None:
        users[contact]["history"] = history
    if settings is not None:
        users[contact]["settings"] = settings
    save_users(users)

# ------------------ ROUTES ------------------
@user_bp.route("/api/user/<contact>", methods=["GET"])
def get_user(contact):
    """Fetch user data (history + settings)."""
    return jsonify(load_user_data(contact)), 200

@user_bp.route("/api/user/<contact>", methods=["POST"])
def update_user(contact):
    """Update user history or settings."""
    data = request.get_json(silent=True) or {}
    history = data.get("history")
    settings = data.get("settings")
    save_user_data(contact, history=history, settings=settings)
    return jsonify({"status": "success", "message": f"User data updated for {contact}"}), 200
