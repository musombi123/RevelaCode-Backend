# backend/routes/admin_routes.py
from flask import Blueprint, request, jsonify
from pathlib import Path
import importlib.util
import sys
from pymongo import MongoClient
from datetime import datetime
from backend.utils.decorators import require_role

# ----------------------------
# Dynamic imports
# ----------------------------
backend_path = Path(__file__).resolve().parent.parent  # /backend

# auth_keys
auth_keys_path = backend_path / "utils" / "auth_keys.py"
spec = importlib.util.spec_from_file_location("auth_keys", str(auth_keys_path))
auth_keys = importlib.util.module_from_spec(spec)
sys.modules["auth_keys"] = auth_keys
spec.loader.exec_module(auth_keys)
get_role = auth_keys.get_role

# audit_logger
audit_logger_path = backend_path / "utils" / "audit_logger.py"
spec = importlib.util.spec_from_file_location("audit_logger", str(audit_logger_path))
audit_logger = importlib.util.module_from_spec(spec)
sys.modules["audit_logger"] = audit_logger
spec.loader.exec_module(audit_logger)
log_admin_action = audit_logger.log_admin_action

# models
models_path = backend_path / "models" / "models.py"
spec = importlib.util.spec_from_file_location("models", str(models_path))
models = importlib.util.module_from_spec(spec)
sys.modules["models"] = models
spec.loader.exec_module(models)
create_user = models.create_user
get_all_users = models.get_all_users

# ----------------------------
# MongoDB setup
# ----------------------------
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["revelacode"]
# ----------------------------
# Blueprint
# ----------------------------
admin_bp = Blueprint("admin", __name__)

COLLECTIONS = {
    "users": "users",
    "scriptures": "scriptures",
    "admin_actions": "admin_actions"
}

# ✅ ONE (1) dashboard route — no duplicates
@admin_bp.route("/admin/dashboard")
@require_role("admin", notify=True, notify_text="Visited admin dashboard")
def admin_dashboard():
    return jsonify({"message": "Welcome, Admin! You have full access."})

@admin_bp.route("/admin/manage-users", methods=["POST"])
@require_role("admin")
def manage_users():
    data = request.json or {}
    username = data.get("username")
    user_role = data.get("role")

    if not username or not user_role:
        return jsonify({"message": "Missing fields"}), 400

    # Create user in Mongo
    user = create_user(db, username, user_role)

    # Log action
    actor = "admin1"  # replace with real admin identity later
    log_admin_action(
        db,
        action="create_user",
        resource=username,
        actor=actor,
        metadata={"role": user_role}
    )

    return jsonify({"message": f"User {username} created successfully."})

@admin_bp.route("/admin/list-users", methods=["GET"])
@require_role("admin")
def list_users():
    users = get_all_users(db)
    for u in users:
        u["_id"] = str(u["_id"])
    return jsonify(users)

@admin_bp.route("/admin/update-scripture", methods=["POST"])
@require_role("admin")
def update_scripture():
    data = request.json or {}

    scripture_id = data.get("id")
    content = data.get("content")

    if not scripture_id or not content:
        return jsonify({"message": "Missing id or content"}), 400

    # Example update (you can wire this to your real model later)
    db[COLLECTIONS["scriptures"]].update_one(
        {"_id": scripture_id},
        {"$set": {"content": content, "updated_at": datetime.utcnow()}}
    )

    log_admin_action(
        db,
        action="update_scripture",
        resource=scripture_id,
        actor="admin1",
        metadata={"updated": True}
    )

    return jsonify({"message": "Scripture updated successfully."})
