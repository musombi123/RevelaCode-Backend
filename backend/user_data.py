# backend/user_profile/user_data.py
import os
import json
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify

# ---------------------------- MONGO SETUP ----------------------------
try:
    from backend.db import db  # MongoDB instance
    MONGO_AVAILABLE = True
    users_col = db.get_collection("users")
except Exception:
    MONGO_AVAILABLE = False
    users_col = None

# ---------------------------- FILE FALLBACK SETUP ----------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
file_lock = threading.Lock()

def atomic_write(filepath, data):
    import tempfile, shutil
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(filepath), delete=False, encoding="utf-8") as tf:
        json.dump(data, tf, indent=2)
        tempname = tf.name
    shutil.move(tempname, filepath)

def load_users_file():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_users_file(users: dict):
    with file_lock:
        atomic_write(USERS_FILE, users)

# ---------------------------- HELPER ----------------------------
def sanitize_mongo_doc(doc: dict) -> dict:
    """Convert Mongo ObjectId to string for JSON serialization."""
    if not doc:
        return doc
    doc_copy = doc.copy()
    if "_id" in doc_copy:
        doc_copy["_id"] = str(doc_copy["_id"])
    return doc_copy

# ---------------------------- BLUEPRINT ----------------------------
user_bp = Blueprint("user_bp", __name__)

# ---------------------------- ROUTES ----------------------------
@user_bp.route("/api/user/<contact>", methods=["GET"])
def get_user(contact):
    """Fetch user data, auto-create if missing."""
    user = None
    if MONGO_AVAILABLE:
        user = users_col.find_one({"contact": contact})
        user = sanitize_mongo_doc(user)

    users = load_users_file()
    if not user:
        user = users.get(contact)

    if not user:
        # auto-create defaults
        user = {
            "contact": contact,
            "history": [],
            "settings": {"theme": "light", "linked_accounts": []},
            "domains": [],
            "created_at": datetime.utcnow().isoformat()
        }
        # Save to Mongo
        if MONGO_AVAILABLE:
            try:
                users_col.insert_one(user)
            except Exception:
                pass

    # Always save/update file fallback
    users[contact] = sanitize_mongo_doc(user)
    save_users_file(users)

    return jsonify(user), 200

@user_bp.route("/api/user/<contact>", methods=["POST"])
def update_user(contact):
    """Update history/settings/domains. Auto-create if missing."""
    data = request.get_json(silent=True) or {}
    update = {}
    if "history" in data:
        update["history"] = data["history"]
    if "settings" in data:
        update["settings"] = data["settings"]
    if "domains" in data:
        update["domains"] = data["domains"]

    if MONGO_AVAILABLE and update:
        result = users_col.update_one({"contact": contact}, {"$set": update})
        if result.matched_count == 0:
            # create if missing
            new_data = {"contact": contact, **update, "created_at": datetime.utcnow().isoformat()}
            try:
                users_col.insert_one(new_data)
            except Exception:
                pass

    # Always update file fallback
    users = load_users_file()
    if contact not in users:
        users[contact] = {
            "contact": contact,
            "history": [],
            "settings": {"theme": "light", "linked_accounts": []},
            "domains": [],
            "created_at": datetime.utcnow().isoformat()
        }
    users[contact].update(update)
    users[contact] = sanitize_mongo_doc(users[contact])
    save_users_file(users)

    return jsonify({"success": True, "message": "User data updated"}), 200
