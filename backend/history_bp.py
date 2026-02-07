# backend/user_data/history_bp.py
import os
import json
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_cors import cross_origin

# ---------------- DATA SETUP ----------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
file_lock = threading.Lock()

# ---------------- FILE HELPERS ----------------
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

def get_user_from_file(contact):
    users = load_users_file()
    return users.get(contact)

def save_user_to_file(user_data):
    users = load_users_file()
    users[user_data["contact"]] = user_data
    save_users_file(users)

# ---------------- BLUEPRINT ----------------
history_bp = Blueprint("history_bp", __name__)

# ---------------- ROUTES ----------------
@history_bp.route("/history", methods=["GET", "POST", "DELETE", "OPTIONS"])
@cross_origin(
    origins=[
        "https://revelacode-frontend.onrender.com",
        "https://www.revelacode-frontend.onrender.com"
    ],
    supports_credentials=True,
    methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-ADMIN-KEY", "X-Timestamp"]
)
def history():
    contact = request.headers.get("Authorization")
    if not contact:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    user = get_user_from_file(contact)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    # ---------- GET ----------
    if request.method == "GET":
        return jsonify({"success": True, "history": user.get("history", [])}), 200

    # ---------- POST ----------
    if request.method == "POST":
        entry = request.get_json(silent=True) or {}
        if not entry:
            return jsonify({"success": False, "message": "No history entry provided"}), 400

        history_list = user.get("history", [])
        history_list.append({
            **entry,
            "timestamp": request.headers.get("X-Timestamp") or datetime.utcnow().isoformat()
        })
        user["history"] = history_list
        save_user_to_file(user)

        return jsonify({"success": True, "history": user["history"]}), 201

    # ---------- DELETE ----------
    if request.method == "DELETE":
        user["history"] = []
        save_user_to_file(user)
        return jsonify({"success": True, "history": []}), 200
