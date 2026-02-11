# backend/routes/admin_routes.py
from flask import Blueprint, request, jsonify
from datetime import datetime
import os

from backend.db import get_db
from backend.utils.decorators import require_role
from backend.utils.auth_keys import get_role
from backend.utils.audit_logger import log_admin_action
from backend.models.models import create_user, get_all_users
from dotenv import load_dotenv

# ----------------------------
# Load environment variables
# ----------------------------
load_dotenv()

# ----------------------------
# Blueprint
# ----------------------------
admin_bp = Blueprint("admin", __name__)

COLLECTIONS = {
    "users": "users",
    "scriptures": "scriptures",
    "admin_actions": "admin_actions"
}

# ----------------------------
# Read API key from .env
# ----------------------------
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

def require_admin_key():
    api_key = request.headers.get("X-ADMIN-API-KEY")
    return api_key == ADMIN_API_KEY and ADMIN_API_KEY is not None

# ----------------------------
# Dashboard
# ----------------------------
@admin_bp.route("/admin/dashboard", methods=["GET"])
def admin_dashboard():
    if not require_admin_key():
        return jsonify({"message": "Unauthorized: Invalid or missing ADMIN_API_KEY"}), 401

    return jsonify({"message": "Welcome, Admin! You have full access."}), 200

# ----------------------------
# User Management - CREATE USER
# ----------------------------
@admin_bp.route("/admin/manage-users", methods=["POST"])
def manage_users():
    if not require_admin_key():
        return jsonify({"message": "Unauthorized: Invalid or missing ADMIN_API_KEY"}), 401

    db = get_db()
    data = request.get_json(silent=True) or {}

    username = data.get("username")
    user_role = data.get("role")

    if not username or not user_role:
        return jsonify({"message": "Missing fields: username and role required"}), 400

    new_user = {
        "username": username,
        "role": user_role,
        "created_at": datetime.utcnow()
    }

    db[COLLECTIONS["users"]].insert_one(new_user)

    log_admin_action(
        db,
        action="create_user",
        resource=username,
        actor="admin",
        metadata={"role": user_role}
    )

    return jsonify({
        "message": f"User {username} created successfully.",
        "user": {
            "username": username,
            "role": user_role
        }
    }), 201

# ----------------------------
# User Management - LIST USERS
# ----------------------------
@admin_bp.route("/admin/list-users", methods=["GET"])
def list_users():
    if not require_admin_key():
        return jsonify({"message": "Unauthorized: Invalid or missing ADMIN_API_KEY"}), 401

    db = get_db()

    users_cursor = db[COLLECTIONS["users"]].find()
    users = []

    for u in users_cursor:
        users.append({
            "username": u.get("username"),
            "role": u.get("role", "user"),
            "created_at": str(u.get("created_at"))
        })

    return jsonify({
        "users": users,
        "total": len(users)
    }), 200

# ----------------------------
# Scripture Management
# ----------------------------
@admin_bp.route("/admin/update-scripture", methods=["POST"])
def update_scripture():
    if not require_admin_key():
        return jsonify({"message": "Unauthorized: Invalid or missing ADMIN_API_KEY"}), 401

    db = get_db()
    data = request.get_json(silent=True) or {}

    scripture_id = data.get("id")
    content = data.get("content")

    if not scripture_id or not content:
        return jsonify({"message": "Missing id or content"}), 400

    result = db[COLLECTIONS["scriptures"]].update_one(
        {"_id": scripture_id},
        {"$set": {
            "content": content,
            "updated_at": datetime.utcnow()
        }}
    )

    log_admin_action(
        db,
        action="update_scripture",
        resource=scripture_id,
        actor="admin",
        metadata={"updated": result.modified_count > 0}
    )

    return jsonify({
        "message": "Scripture updated successfully.",
        "modified": result.modified_count
    }), 200
