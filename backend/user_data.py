from flask import Blueprint, request, jsonify
import json, os, tempfile, shutil, logging

# Blueprint for user data routes
user_bp = Blueprint("user", __name__)

# Absolute path to backend directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
USERS_FILE = os.path.join(BASE_DIR, "data", "users.json")


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')


# ------------------- HELPERS -------------------

def atomic_write(filepath, data):
    """Safely write JSON data atomically."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(filepath), delete=False, encoding="utf-8") as tf:
        json.dump(data, tf, indent=2)
        tempname = tf.name
    shutil.move(tempname, filepath)
    logging.info(f"Data written atomically to {filepath}")


def load_users():
    """Load all users from users.json"""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_users(users: dict):
    """Save all users to users.json"""
    atomic_write(USERS_FILE, users)


def load_user_data(contact):
    """
    Load user data (history & settings) from users.json
    If user doesn't exist yet, return defaults.
    """
    users = load_users()
    user = users.get(contact, {})

    history = user.get("history", [])
    settings = user.get("settings", {"theme": "light", "linked_accounts": []})

    return {"history": history, "settings": settings}


def save_user_data(contact, history=None, settings=None):
    """
    Save user data (history & settings) INTO users.json
    This avoids needing backend/user_data/ folder.
    """
    users = load_users()

    if contact not in users:
        # Create minimal user shell if not registered yet
        users[contact] = {
            "contact": contact,
            "history": [],
            "settings": {"theme": "light", "linked_accounts": []}
        }

    if history is not None:
        users[contact]["history"] = history

    if settings is not None:
        users[contact]["settings"] = settings

    save_users(users)


# ------------------- API ROUTES -------------------

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
