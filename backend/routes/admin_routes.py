# backend/routes/admin_routes.py
from flask import Blueprint, request, jsonify
from datetime import datetime
import os

from backend.db import get_db
from backend.utils.decorators import require_role
from backend.utils.auth_keys import get_role
from backend.utils.audit_logger import log_admin_action
from backend.models.models import create_user, get_all_users

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
# Dashboard
# ----------------------------
@admin_bp.route("/admin/dashboard")
@require_role("admin", notify=True, notify_text="Visited admin dashboard")
def admin_dashboard():
    return jsonify({"message": "Welcome, Admin! You have full access."})

# ----------------------------
# User Management
# ----------------------------
@admin_bp.route("/admin/manage-users", methods=["POST"])
@require_role("admin")
def manage_users():
    db = get_db()
    data = request.get_json(silent=True) or {}

    username = data.get("username")
    user_role = data.get("role")

    if not username or not user_role:
        return jsonify({"message": "Missing fields"}), 400

    user = create_user(db, username, user_role)

    log_admin_action(
        db,
        action="create_user",
        resource=username,
        actor="admin",
        metadata={"role": user_role}
    )

    return jsonify({
        "message": f"User {username} created successfully."
    }), 201

@admin_bp.route("/admin/list-users", methods=["GET"])
@require_role("admin")
def list_users():
    db = get_db()
    users = get_all_users(db)

    sanitized = []
    for u in users:
        sanitized.append({
            "username": u.get("username"),
            "role": u.get("role", "user"),
            "created_at": str(u.get("created_at"))
        })

    return jsonify({
        "users": sanitized,
        "total": len(sanitized)
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
        "message": "Scripture updated successfully."
    }), 200
