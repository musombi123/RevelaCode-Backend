from backend import data
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
full_name = data.get("full_name")
contact = data.get("contact")
user_role = data.get("role")

# ----------------------------
# Blueprint
# ----------------------------
admin_bp = Blueprint("admin", __name__)

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

    full_name = data.get("full_name")
    contact = data.get("contact")
    user_role = data.get("role")

    if not full_name or not contact or not user_role:
        return jsonify({
            "message": "Missing fields: full_name, contact and role required"
        }), 400

    # Only allow valid roles: admin, support, user
    if user_role not in ["support", "user"]:
        return jsonify({
            "message": "Invalid role. Must be 'support' or 'user'."
            }), 400

    # Create user in DB
    user = create_user(db, full_name, contact, user_role)

    log_admin_action(
        db,
        action="create_user",
        resource=contact,
        actor="admin",
        metadata={"role": user_role}
    )

    return jsonify({
        "message": f"User {contact} with role {user_role} created successfully.",
        "user": {
            "full_name": user["full_name"],
            "contact": user["contact"],
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
            "full_name": u.get("full_name"),
            "contact": u.get("contact"),
            "role": u.get("role", "user"),
            "verified": u.get("verified", False),
            "created_at": str(u.get("created_at"))
            })

    return jsonify({
        "users": users,
        "total": len(users)
    }), 200

@admin_bp.route("/admin/update-policy", methods=["POST"])
@require_role("admin")
def update_policy():
    db = get_db()
    data = request.get_json(silent=True) or {}

    policy_id = data.get("policy_id")
    content = data.get("content")

    if not policy_id or not content:
        return jsonify({
            "message": "policy_id and content required"
        }), 400

    db["policies"].update_one(
        {"_id": policy_id},
        {
            "$set": {
                "content": content,
                "updated_at": datetime.utcnow(),
                "updated_by": "admin"
            }
        },
        upsert=True
    )

    log_admin_action(
        db,
        action="update_policy",
        resource=policy_id,
        actor="admin"
    )

    return jsonify({
        "message": f"{policy_id} updated successfully"
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
