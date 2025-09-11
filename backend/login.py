# backend/login.py
import os, json, hashlib
from flask import Blueprint, request, jsonify

login_bp = Blueprint("login", __name__)

USERS_FILE = os.path.join("backend", "user_data", "users.json")

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@login_bp.route("/api/login", methods=["POST"])
def login_user():
    try:
        data = request.get_json(force=True)
        contact = data.get("contact", "").strip()
        password = data.get("password", "").strip()

        if not contact or not password:
            return jsonify({"message": "Contact and password required"}), 400

        users = load_users()
        if contact not in users:
            return jsonify({"message": "❌ Invalid contact or password"}), 401

        hashed = hash_password(password)
        if users[contact]["password"] != hashed:
            return jsonify({"message": "❌ Invalid contact or password"}), 401

        return jsonify({
            "message": "✅ Login successful",
            "user": {
                "contact": contact,
                "full_name": users[contact]["full_name"],
                "role": users[contact]["role"]
            }
        }), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500
