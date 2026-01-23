from flask import Blueprint, request, jsonify
from backend.utils.auth_keys import get_role
from backend.utils.audit_logger import log_admin_action
from backend.models.models import create_user, get_all_users
from pymongo import MongoClient
from datetime import datetime

db = MongoClient("mongodb://localhost:27017/")["revelacode"]
admin_bp = Blueprint("admin", __name__)

COLLECTIONS = {
    "users": "users",
    "scriptures": "scriptures",
    "admin_actions": "admin_actions"
}

@admin_bp.route("/admin/dashboard")
def admin_dashboard():
    role = get_role(request)
    if role != "admin":
        return jsonify({"message": "Forbidden"}), 403
    return jsonify({"message": "Welcome, Admin! You have full access."})

@admin_bp.route("/admin/manage-users", methods=["POST"])
def manage_users():
    role = get_role(request)
    if role != "admin":
        return jsonify({"message": "Forbidden"}), 403

    data = request.json
    username = data.get("username")
    user_role = data.get("role")

    if not username or not user_role:
        return jsonify({"message": "Missing fields"}), 400

    # Use models.py function instead of raw insert
    user = create_user(db, username, user_role)

    # Log action
    actor = "admin1"  # replace with dynamic admin username
    log_admin_action(
        db,
        action="create_user",
        resource=username,
        actor=actor,
        metadata={"role": user_role}
    )

    return jsonify({"message": f"User {username} created successfully."})

@admin_bp.route("/admin/list-users", methods=["GET"])
def list_users():
    role = get_role(request)
    if role != "admin":
        return jsonify({"message": "Forbidden"}), 403

    users = get_all_users(db)  # fetch via models.py
    for u in users:
        u["_id"] = str(u["_id"])
    return jsonify(users)

@admin_bp.route("/admin/update-scripture", methods=["POST"])
def update_scripture():
    role = get_role(request)
    if role != "admin":
        return jsonify({"message": "Forbidden"}), 403

    data = request.json
    verse = data.get("verse")
    decoded = data.get("decodedMessage")

    if not verse or not decoded:
        return jsonify({"message": "Missing fields"}), 400

    db[COLLECTIONS["scriptures"]].update_one(
        {"verse": verse},
        {"$set": {"decoded": decoded, "updated_at": datetime.utcnow()}},
        upsert=True
    )

    # Log action
    actor = "admin1"
    log_admin_action(db, "update_scripture", verse, actor, {"decoded": decoded})

    return jsonify({"message": f"{verse} updated successfully."})
