# backend/reset_password.py
import os, json, hashlib
from flask import Blueprint, request, jsonify

reset_bp = Blueprint("reset_password", __name__)

USERS_FILE = os.path.join("user_data", "users.json")

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@reset_bp.route("/api/reset-password", methods=["POST"])
def reset_password():
    try:
        data = request.get_json(force=True)
        contact = data.get("contact", "").strip()
        old_password = data.get("old_password", "").strip()
        new_password = data.get("new_password", "").strip()
        confirm_password = data.get("confirm_password", "").strip()

        if not contact or not old_password or not new_password:
            return jsonify({"message": "All fields are required"}), 400

        if new_password != confirm_password:
            return jsonify({"message": "Passwords do not match"}), 400

        users = load_users()
        if contact not in users:
            return jsonify({"message": "❌ Account not found"}), 404

        if users[contact]["password"] != hash_password(old_password):
            return jsonify({"message": "❌ Old password is incorrect"}), 401

        users[contact]["password"] = hash_password(new_password)
        save_users(users)

        return jsonify({"message": "✅ Password reset successful"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
