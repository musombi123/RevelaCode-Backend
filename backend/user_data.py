from flask import Blueprint, request, jsonify
import json, os, tempfile, shutil, logging

# Blueprint for user data routes
user_bp = Blueprint("user", __name__)

# Absolute path to user data directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "user_data")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def atomic_write(filepath, data):
    """Safely write JSON data atomically."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=os.path.dirname(filepath), delete=False) as tf:
        json.dump(data, tf, indent=2)
        tempname = tf.name
    shutil.move(tempname, filepath)
    logging.info(f"Data written atomically to {filepath}")

def load_user_data(contact):
    """Load user data (history & settings) by contact (email or phone)."""
    os.makedirs(DATA_DIR, exist_ok=True)

    history_file = os.path.join(DATA_DIR, f"{contact}_history.json")
    settings_file = os.path.join(DATA_DIR, f"{contact}_settings.json")

    try:
        with open(history_file) as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = []

    try:
        with open(settings_file) as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {"theme": "light", "linked_accounts": []}

    return {"history": history, "settings": settings}

def save_user_data(contact, history=None, settings=None):
    """Save user data (history & settings) by contact (email or phone)."""
    os.makedirs(DATA_DIR, exist_ok=True)

    if history is not None:
        atomic_write(os.path.join(DATA_DIR, f"{contact}_history.json"), history)
    if settings is not None:
        atomic_write(os.path.join(DATA_DIR, f"{contact}_settings.json"), settings)

# ------------------- API ROUTES -------------------

@user_bp.route("/api/user/<contact>", methods=["GET"])
def get_user(contact):
    """Fetch user data (history + settings)."""
    return jsonify(load_user_data(contact))

@user_bp.route("/api/user/<contact>", methods=["POST"])
def update_user(contact):
    """Update user history or settings."""
    data = request.get_json(silent=True) or {}
    history = data.get("history")
    settings = data.get("settings")

    save_user_data(contact, history=history, settings=settings)
    return jsonify({"status": "success", "message": f"User data updated for {contact}"})
