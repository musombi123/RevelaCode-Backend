from flask import Blueprint, request, jsonify
from datetime import datetime
from dotenv import load_dotenv

from backend.db import get_db
from backend.utils.decorators import require_role
from backend.utils.auth_keys import get_role
from backend.utils.audit_logger import log_admin_action
from backend.models.models import create_user, get_all_users

# ----------------------------
# Load environment variables
# ----------------------------
load_dotenv()

# ----------------------------
# Blueprint
# ----------------------------
admin_bp = Blueprint("admin", __name__)

# ----------------------------
# ADMIN LOGIN
# ----------------------------
@admin_bp.route("/admin/login", methods=["POST"])
def admin_login():
    role = get_role(request)

    if role != "admin":
        return jsonify({"message": "Unauthorized: Invalid API Key"}), 401

    return jsonify({
        "message": "Admin authenticated successfully",
        "role": role,
        "status": "ok"
    }), 200

# ----------------------------
# Dashboard
# ----------------------------
@admin_bp.route("/admin/dashboard", methods=["GET"])
@require_role("admin", notify=True, notify_text="Visited admin dashboard")
def admin_dashboard():
    return jsonify({"message": "Welcome, Admin! You have full access."}), 200

# ----------------------------
# User Management - CREATE USER (ADMIN CAN CREATE SUPPORT)
# ----------------------------
@admin_bp.route("/admin/manage-users", methods=["POST"])
@require_role("admin")
def manage_users():
    db = get_db()
    data = request.get_json(silent=True) or {}

    username = data.get("username")
    user_role = data.get("role")

    if not username or not user_role:
        return jsonify({"message": "Missing fields: username and role required"}), 400

    # Only allow valid roles: admin, support, user
    if user_role not in ["admin", "support", "user"]:
        return jsonify({"message": "Invalid role. Must be 'admin', 'support', or 'user'."}), 400

    # Create user in DB
    user = create_user(db, username, user_role)

    log_admin_action(
        db,
        action="create_user",
        resource=username,
        actor="admin",
        metadata={"role": user_role}
    )

    return jsonify({
        "message": f"User {username} with role {user_role} created successfully.",
        "user": {
            "username": user["username"],
            "role": user["role"]
        }
    }), 201

# ----------------------------
# User Management - LIST USERS
# ----------------------------
@admin_bp.route("/admin/list-users", methods=["GET"])
@require_role("admin")
def list_users():
    db = get_db()
    users_from_db = get_all_users(db)

    users = []
    for u in users_from_db:
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
@require_role("admin")
def update_scripture():
    db = get_db()
    data = request.get_json(silent=True) or {}

    scripture_id = data.get("id")
    content = data.get("content")

    if not scripture_id or not content:
        return jsonify({"message": "Missing id or content"}), 400

    result = db["scriptures"].update_one(
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
