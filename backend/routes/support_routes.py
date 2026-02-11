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
@support_bp.route("/support/dashboard")
def support_dashboard():
    role = get_role(request)
    if role != "support":
        return jsonify({"message": "Forbidden"}), 403

    return jsonify({
        "message": "Welcome, Support Team! You can manage tickets."
    }), 200

# ----------------------------
# View Tickets
# ----------------------------
@support_bp.route("/support/tickets", methods=["GET"])
def view_tickets():
    role = get_role(request)
    if role != "support":
        return jsonify({"message": "Forbidden"}), 403

    db = get_db()
    tickets = list(db[COLLECTIONS["support_tickets"]].find())

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

# ----------------------------
# Resolve Ticket
# ----------------------------
@support_bp.route("/support/resolve-ticket", methods=["POST"])
def resolve_ticket():
    role = get_role(request)
    if role != "support":
        return jsonify({"message": "Forbidden"}), 403

    db = get_db()
    data = request.get_json(silent=True) or {}

    ticket_id = data.get("ticket_id")
    resolution = data.get("resolution")

    if not ticket_id or not resolution:
        return jsonify({"message": "Missing fields"}), 400

    result = db[COLLECTIONS["support_tickets"]].update_one(
        {"_id": ObjectId(ticket_id)},
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
        actor="support",
        metadata={"resolved": result.modified_count > 0}
    )

    return jsonify({
        "message": f"Ticket {ticket_id} resolved."
    }), 200

# ----------------------------
# Support Login
# ----------------------------
@support_bp.route("/support/login", methods=["POST"])
def support_login():
    role = get_role(request)

    if role != "support":
        return jsonify({"message": "Unauthorized: Invalid API Key"}), 401

    return jsonify({
        "message": "Support authenticated successfully",
        "role": role,
        "status": "ok"
    }), 200

# ---------- BLUEPRINT REGISTRATION HELPER ----------
def register_bp(import_path: str, bp_name: str, url_prefix: str = None):
    try:
        module = __import__(import_path, fromlist=[bp_name])
        bp = getattr(module, bp_name)
        app.register_blueprint(bp, url_prefix=url_prefix)
        logger.info(f"{bp_name} registered ({import_path}) with prefix {url_prefix}")
    except Exception as e:
        logger.warning(f"{bp_name} not available from {import_path}: {e}")
