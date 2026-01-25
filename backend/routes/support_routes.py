# backend/routes/support_routes.py
from flask import Blueprint, request, jsonify
from pathlib import Path
import importlib.util
import sys
from pymongo import MongoClient
from datetime import datetime
from bson.objectid import ObjectId

# ----------------------------
# Dynamic imports for utils & models
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
get_all_users = models.get_all_users

# ----------------------------
# MongoDB setup
# ----------------------------
db = MongoClient("mongodb://localhost:27017/")["revelacode"]

# ----------------------------
# Blueprint
# ----------------------------
support_bp = Blueprint("support", __name__)

COLLECTIONS = {
    "support_tickets": "support_tickets",
    "admin_actions": "admin_actions"
}

@support_bp.route("/support/dashboard")
def support_dashboard():
    role = get_role(request)
    if role != "support":
        return jsonify({"message": "Forbidden"}), 403
    return jsonify({"message": "Welcome, Support Team! You can manage tickets."})

@support_bp.route("/support/tickets", methods=["GET"])
def view_tickets():
    role = get_role(request)
    if role != "support":
        return jsonify({"message": "Forbidden"}), 403

    tickets = list(db[COLLECTIONS["support_tickets"]].find())
    for t in tickets:
        t["_id"] = str(t["_id"])
    return jsonify({"tickets": tickets})

@support_bp.route("/support/resolve-ticket", methods=["POST"])
def resolve_ticket():
    role = get_role(request)
    if role != "support":
        return jsonify({"message": "Forbidden"}), 403

    data = request.json
    ticket_id = data.get("ticket_id")
    resolution = data.get("resolution")

    if not ticket_id or not resolution:
        return jsonify({"message": "Missing fields"}), 400

    db[COLLECTIONS["support_tickets"]].update_one(
        {"_id": ObjectId(ticket_id)},
        {"$set": {"status": "resolved", "resolution": resolution, "resolved_at": datetime.utcnow()}}
    )

    actor = "support1"
    log_admin_action(
        db,
        action="resolve_ticket",
        resource=ticket_id,
        actor=actor,
        metadata={"resolution": resolution}
    )

    return jsonify({"message": f"Ticket {ticket_id} resolved."})
