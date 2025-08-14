# backend/auth_gate.py
import json
import os
import hashlib
from flask import Blueprint, request, jsonify
from user_data import load_user_data, save_user_data

USERS_FILE = "./backend/users.json"

auth_bp = Blueprint('auth', __name__)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_role(username):
    users = load_users()
    return users.get(username, {}).get("role", "guest")

# ==============================
# API ROUTES
# ==============================

@auth_bp.route("/api/register", methods=["POST"])
def api_register():
    data = request.json or {}
    username = data.get("username", "").strip()
    full_name = data.get("full_name", "").strip()
    contact = data.get("contact", "").strip()
    password = data.get("password", "").strip()
    confirm_password = data.get("confirm_password", "").strip()

    if not username or not full_name or not contact or not password:
        return jsonify({"success": False, "message": "All fields are required."}), 400

    if password != confirm_password:
        return jsonify({"success": False, "message": "Passwords do not match."}), 400

    users = load_users()
    if username in users:
        return jsonify({"success": False, "message": "Username already exists."}), 400

    users[username] = {
        "full_name": full_name,
        "contact": contact,
        "password": hash_password(password),
        "role": "normal"
    }
    save_users(users)

    save_user_data(username, history=[], settings={"theme": "light", "linked_accounts": []})

    return jsonify({"success": True, "username": username, "role": "normal"}), 201


@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password required."}), 400

    users = load_users()
    hashed = hash_password(password)

    if username in users and users[username]["password"] == hashed:
        return jsonify({
            "success": True,
            "username": username,
            "full_name": users[username]["full_name"],
            "role": get_user_role(username)
        }), 200

    return jsonify({"success": False, "message": "Invalid username or password."}), 401


@auth_bp.route("/api/guest", methods=["GET"])
def api_guest():
    return jsonify({
        "success": True,
        "username": "guest",
        "role": "guest",
        "message": "Guest mode: Limited access"
    }), 200
