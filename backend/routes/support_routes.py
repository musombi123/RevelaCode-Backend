from flask import Blueprint, request, jsonify
from backend.utils.auth_keys import get_role
from backend.utils.audit_logger import log_admin_action
from backend.models.models import get_all_users  # optional if you need user info
from pymongo import MongoClient
from datetime import datetime
from bson.objectid import ObjectId

db = MongoClient("mongodb://localhost:27017/")["revelacode"]
support_bp = Blueprint("support", __name__)

COLLECTIONS = {
    "support_tickets": "support_tickets",
    "admin_actions": "admin_actions"  # support logs can also go here
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
