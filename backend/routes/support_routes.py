# backend/routes/support_routes.py
from flask import Blueprint, request, jsonify
from datetime import datetime
from bson.objectid import ObjectId

from backend.db import get_db
from backend.utils.auth_keys import get_role
from backend.utils.audit_logger import log_admin_action

# ----------------------------
# Blueprint
# ----------------------------
support_bp = Blueprint("support", __name__)

COLLECTIONS = {
    "support_tickets": "support_tickets",
    "admin_actions": "admin_actions"
}

# ----------------------------
# Dashboard
# ----------------------------
@support_bp.route("/dashboard")
def support_dashboard():
    role = get_role(request)
    if role != "support":
        return jsonify({"message": "Forbidden"}), 403

    db = get_db()

    total_open = db[COLLECTIONS["support_tickets"]].count_documents({"status": "open"})
    my_tickets = db[COLLECTIONS["support_tickets"]].count_documents({"assigned_to": role})

    return jsonify({
        "message": "Support Dashboard",
        "stats": {
            "open_tickets": total_open,
            "my_tickets": my_tickets
        }
    }), 200

# ----------------------------
# View Tickets
# ----------------------------
@support_bp.route("/tickets", methods=["GET"])
def view_tickets():
    role = get_role(request)
    if role != "support":
        return jsonify({"message": "Forbidden"}), 403

    db = get_db()
    tickets = list(db[COLLECTIONS["support_tickets"]].find().limit(50))

    sanitized = []
    for t in tickets:
        sanitized.append({
            "id": str(t["_id"]),
            "user": t.get("user"),
            "subject": t.get("subject"),
            "status": t.get("status", "open"),
            "created_at": str(t.get("created_at")),
            "resolved_at": str(t.get("resolved_at")) if t.get("resolved_at") else None
        })

    return jsonify({
        "tickets": sanitized,
        "total": len(sanitized)
    }), 200
#-------------------
#ti
#-------------------
@support_bp.route("/assign-ticket", methods=["POST"])
def assign_ticket():
    role = get_role(request)
    if role != "support":
        return jsonify({"message": "Forbidden"}), 403

    db = get_db()
    data = request.get_json(silent=True) or {}

    ticket_id = data.get("ticket_id")

    if not ticket_id:
        return jsonify({"message": "Missing ticket_id"}), 400

    try:
        oid = ObjectId(ticket_id)
    except Exception:
        return jsonify({"message": "Invalid ticket_id"}), 400

    db[COLLECTIONS["support_tickets"]].update_one(
        {"_id": oid},
        {"$set": {"assigned_to": role}}
    )

    return jsonify({
        "message": f"Ticket assigned to {role}"
    }), 200

# ----------------------------
# Resolve Ticket
# ----------------------------
@support_bp.route("/resolve-ticket", methods=["POST"])
def resolve_ticket():
    role = get_role(request)
    if role != "support":
        return jsonify({"message": "Forbidden"}), 403

    db = get_db()
    data = request.get_json(silent=True) or {}

    ticket_id = data.get("ticket_id")
    resolution = data.get("resolution")

    if not ticket_id or not resolution or not resolution.strip():
        return jsonify({"message": "Missing fields"}), 400

    try:
        oid = ObjectId(ticket_id)
    except Exception:
        return jsonify({"message": "Invalid ticket_id"}), 400

    ticket = db[COLLECTIONS["support_tickets"]].find_one({"_id": oid})

    if not ticket:
        return jsonify({"message": "Ticket not found"}), 404

    # 🚨 OWNERSHIP CHECK (NEW CORE FEATURE)
    if ticket.get("assigned_to") not in [None, role]:
        return jsonify({"message": "Not assigned to you"}), 403

    result = db[COLLECTIONS["support_tickets"]].update_one(
        {"_id": oid},
        {
            "$set": {
                "status": "resolved",
                "resolution": resolution,
                "resolved_at": datetime.utcnow()
            }
        }
    )

    log_admin_action(
        db,
        action="resolve_ticket",
        resource=ticket_id,
        actor=role,
        metadata={"resolved": result.modified_count > 0}
    )

    return jsonify({
        "message": f"Ticket {ticket_id} resolved."
    }), 200
