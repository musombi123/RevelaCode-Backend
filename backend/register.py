# backend/registry.py
import os, json, hashlib
from flask import Blueprint, request, jsonify

registry_bp = Blueprint("registry", __name__)

USERS_FILE = os.path.join("backend", "user_data", "users.json")

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

@registry_bp.route("/api/register", methods=["POST"])
def register_user():
    try:
        data = request.get_json(force=True)
        full_name = data.get("full_name", "").strip()
        contact = data.get("contact", "").strip()
        password = data.get("password", "").strip()
        confirm_password = data.get("confirm_password", "").strip()

        if not full_name or not contact or not password:
            return jsonify({"message": "All fields are required"}), 400

        if password != confirm_password:
            return jsonify({"message": "Passwords do not match"}), 400

        users = load_users()
        if contact in users:
            return jsonify({"message": "⚠ Account already exists"}), 400

        users[contact] = {
            "full_name": full_name,
            "contact": contact,
            "password": hash_password(password),
            "role": "normal"
        }
        save_users(users)

        return jsonify({"message": "✅ Registration successful", "user": full_name}), 201
    except Exception as e:
        return jsonify({"message": str(e)}), 500
