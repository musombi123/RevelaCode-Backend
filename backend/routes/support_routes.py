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
@support_bp.route("/dashboard", methods=["GET"])
def support_dashboard():
    role = get_role(request)

    if role != "support":
        return jsonify({
            "success": False,
            "message": "Forbidden"
        }), 403

    db = get_db()

    tickets = db[COLLECTIONS["support_tickets"]]

    stats = {
        "total": tickets.count_documents({}),
        "open": tickets.count_documents({"status": "open"}),
        "pending": tickets.count_documents({"status": "pending"}),
        "resolved": tickets.count_documents({"status": "resolved"}),
        "assigned_to_me": tickets.count_documents({"assigned_to": role}),
        "unassigned": tickets.count_documents({
            "$or": [
                {"assigned_to": None},
                {"assigned_to": {"$exists": False}}
            ]
        })
    }

    recent = []

    cursor = (
        tickets
        .find()
        .sort("created_at", -1)
        .limit(5)
    )

    for ticket in cursor:
        recent.append({
            "id": str(ticket["_id"]),
            "user": ticket.get("user"),
            "subject": ticket.get("subject"),
            "status": ticket.get("status", "open"),
            "assigned_to": ticket.get("assigned_to"),
            "created_at": str(ticket.get("created_at"))
        })

    return jsonify({
        "success": True,
        "message": "Support dashboard loaded.",
        "stats": stats,
        "recent": recent
    }), 200

# ----------------------------
# View Tickets
# ----------------------------
@support_bp.route("/tickets", methods=["GET"])
def view_tickets():
    role = get_role(request)

    if role != "support":
        return jsonify({
            "success": False,
            "message": "Forbidden"
        }), 403

    db = get_db()
    collection = db[COLLECTIONS["support_tickets"]]

    # Query parameters
    page = max(int(request.args.get("page", 1)), 1)
    limit = max(min(int(request.args.get("limit", 20)), 100), 1)

    status = request.args.get("status")
    search = request.args.get("search", "").strip()
    mine = request.args.get("mine", "false").lower() == "true"

    query = {}

    if status:
        query["status"] = status

    if mine:
        query["assigned_to"] = role

    if search:
        query["$or"] = [
            {"subject": {"$regex": search, "$options": "i"}},
            {"user": {"$regex": search, "$options": "i"}}
        ]

    total = collection.count_documents(query)

    cursor = (
        collection
        .find(query)
        .sort("created_at", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )

    tickets = []

    for ticket in cursor:
        tickets.append({
            "id": str(ticket["_id"]),
            "user": ticket.get("user"),
            "subject": ticket.get("subject"),
            "status": ticket.get("status", "open"),
            "assigned_to": ticket.get("assigned_to"),
            "created_at": str(ticket.get("created_at")),
            "resolved_at": (
                str(ticket.get("resolved_at"))
                if ticket.get("resolved_at")
                else None
            )
        })

    return jsonify({
        "success": True,
        "tickets": tickets,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }), 200

# ----------------------------
# Resolve Ticket
# ----------------------------
@support_bp.route("/resolve", methods=["POST"])
def resolve_ticket():
    role = get_role(request)

    if role != "support":
        return jsonify({
            "success": False,
            "message": "Forbidden"
        }), 403

    data = request.get_json(silent=True) or {}

    ticket_id = data.get("ticket_id")
    resolution = data.get("resolution", "").strip()

    if not ticket_id:
        return jsonify({
            "success": False,
            "message": "ticket_id is required"
        }), 400

    if not resolution:
        return jsonify({
            "success": False,
            "message": "resolution is required"
        }), 400

    try:
        oid = ObjectId(ticket_id)
    except Exception:
        return jsonify({
            "success": False,
            "message": "Invalid ticket ID"
        }), 400

    db = get_db()
    collection = db[COLLECTIONS["support_tickets"]]

    ticket = collection.find_one({"_id": oid})

    if not ticket:
        return jsonify({
            "success": False,
            "message": "Ticket not found"
        }), 404

    if ticket.get("status") == "resolved":
        return jsonify({
            "success": False,
            "message": "Ticket has already been resolved."
        }), 409

    assigned_to = ticket.get("assigned_to")

    if assigned_to not in [None, role]:
        return jsonify({
            "success": False,
            "message": "This ticket is assigned to another support agent."
        }), 403

    collection.update_one(
        {"_id": oid},
        {
            "$set": {
                "status": "resolved",
                "resolution": resolution,
                "resolved_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "assigned_to": role
            }
        }
    )

    log_admin_action(
        db,
        action="resolve_ticket",
        resource=ticket_id,
        actor=role,
        metadata={
            "status": "resolved"
        }
    )

    updated = collection.find_one({"_id": oid})

    return jsonify({
        "success": True,
        "message": "Ticket resolved successfully.",
        "ticket": {
            "id": str(updated["_id"]),
            "user": updated.get("user"),
            "subject": updated.get("subject"),
            "status": updated.get("status"),
            "assigned_to": updated.get("assigned_to"),
            "resolved_at": str(updated.get("resolved_at")),
            "updated_at": str(updated.get("updated_at"))
        }
    }), 200

# ----------------------------
# Search Tickets
# ----------------------------
@support_bp.route("/search", methods=["GET"])
def search_tickets():
    role = get_role(request)

    if role != "support":
        return jsonify({
            "success": False,
            "message": "Forbidden"
        }), 403

    query_text = request.args.get("q", "").strip()

    if not query_text:
        return jsonify({
            "success": False,
            "message": "Missing search query."
        }), 400

    db = get_db()
    collection = db[COLLECTIONS["support_tickets"]]

    query = {
        "$or": [
            {"user": {"$regex": query_text, "$options": "i"}},
            {"email": {"$regex": query_text, "$options": "i"}},
            {"subject": {"$regex": query_text, "$options": "i"}},
            {"description": {"$regex": query_text, "$options": "i"}},
            {"status": {"$regex": query_text, "$options": "i"}}
        ]
    }

    results = []

    for ticket in collection.find(query).sort("created_at", -1):
        results.append({
            "id": str(ticket["_id"]),
            "user": ticket.get("user"),
            "email": ticket.get("email"),
            "subject": ticket.get("subject"),
            "status": ticket.get("status"),
            "assigned_to": ticket.get("assigned_to"),
            "created_at": str(ticket.get("created_at"))
        })

    return jsonify({
        "success": True,
        "count": len(results),
        "tickets": results
    }), 200
# ----------------------------
# Support History
# ----------------------------
@support_bp.route("/history", methods=["GET"])
def support_history():
    role = get_role(request)

    if role != "support":
        return jsonify({
            "success": False,
            "message": "Forbidden"
        }), 403

    db = get_db()
    collection = db[COLLECTIONS["admin_actions"]]

    page = max(int(request.args.get("page", 1)), 1)
    limit = max(min(int(request.args.get("limit", 20)), 100), 1)

    query = {
        "action": {
            "$in": [
                "assign_ticket",
                "resolve_ticket"
            ]
        }
    }

    total = collection.count_documents(query)

    cursor = (
        collection
        .find(query)
        .sort("timestamp", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )

    history = []

    for log in cursor:
        history.append({
            "id": str(log["_id"]),
            "action": log.get("action"),
            "resource": log.get("resource"),
            "actor": log.get("actor"),
            "metadata": log.get("metadata", {}),
            "timestamp": str(log.get("timestamp"))
        })

    return jsonify({
        "success": True,
        "history": history,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }), 200
# ----------------------------
# Support Analytics
# ----------------------------
@support_bp.route("/analytics", methods=["GET"])
def support_analytics():
    role = get_role(request)

    if role != "support":
        return jsonify({
            "success": False,
            "message": "Forbidden"
        }), 403

    db = get_db()
    collection = db[COLLECTIONS["support_tickets"]]

    total = collection.count_documents({})

    open_count = collection.count_documents({
        "status": "open"
    })

    pending_count = collection.count_documents({
        "status": "pending"
    })

    resolved_count = collection.count_documents({
        "status": "resolved"
    })

    assigned_count = collection.count_documents({
        "assigned_to": role
    })

    unassigned_count = collection.count_documents({
        "$or": [
            {"assigned_to": None},
            {"assigned_to": {"$exists": False}}
        ]
    })

    recent_activity = []

    cursor = (
        collection
        .find()
        .sort("updated_at", -1)
        .limit(10)
    )

    for ticket in cursor:
        recent_activity.append({
            "id": str(ticket["_id"]),
            "subject": ticket.get("subject"),
            "status": ticket.get("status"),
            "assigned_to": ticket.get("assigned_to"),
            "updated_at": str(ticket.get("updated_at"))
            if ticket.get("updated_at")
            else None
        })

    return jsonify({
        "success": True,
        "analytics": {
            "total_tickets": total,
            "open_tickets": open_count,
            "pending_tickets": pending_count,
            "resolved_tickets": resolved_count,
            "assigned_to_me": assigned_count,
            "unassigned_tickets": unassigned_count,
            "resolution_rate": round(
                (resolved_count / total * 100), 1
            ) if total else 0
        },
        "recent_activity": recent_activity
    }), 200
# ----------------------------
# Get Single Ticket
# ----------------------------
@support_bp.route("/ticket/<ticket_id>", methods=["GET"])
def get_ticket(ticket_id):
    role = get_role(request)

    if role != "support":
        return jsonify({
            "success": False,
            "message": "Forbidden"
        }), 403

    try:
        oid = ObjectId(ticket_id)
    except Exception:
        return jsonify({
            "success": False,
            "message": "Invalid ticket ID"
        }), 400

    db = get_db()

    ticket = db[COLLECTIONS["support_tickets"]].find_one({
        "_id": oid
    })

    if not ticket:
        return jsonify({
            "success": False,
            "message": "Ticket not found"
        }), 404

    return jsonify({
        "success": True,
        "ticket": {
            "id": str(ticket["_id"]),
            "user": ticket.get("user"),
            "email": ticket.get("email"),
            "subject": ticket.get("subject"),
            "description": ticket.get("description"),
            "status": ticket.get("status", "open"),
            "priority": ticket.get("priority", "normal"),
            "assigned_to": ticket.get("assigned_to"),
            "resolution": ticket.get("resolution"),
            "created_at": str(ticket.get("created_at")),
            "updated_at": str(ticket.get("updated_at"))
            if ticket.get("updated_at")
            else None,
            "resolved_at": str(ticket.get("resolved_at"))
            if ticket.get("resolved_at")
            else None
        }
    }), 200

# ----------------------------
# Assign Ticket
# ----------------------------
@support_bp.route("/assign", methods=["POST"])
def assign_ticket():
    role = get_role(request)

    if role != "support":
        return jsonify({
            "success": False,
            "message": "Forbidden"
        }), 403

    data = request.get_json(silent=True) or {}

    ticket_id = data.get("ticket_id")

    if not ticket_id:
        return jsonify({
            "success": False,
            "message": "ticket_id is required"
        }), 400

    try:
        oid = ObjectId(ticket_id)
    except Exception:
        return jsonify({
            "success": False,
            "message": "Invalid ticket ID"
        }), 400

    db = get_db()
    collection = db[COLLECTIONS["support_tickets"]]

    ticket = collection.find_one({"_id": oid})

    if not ticket:
        return jsonify({
            "success": False,
            "message": "Ticket not found"
        }), 404

    if ticket.get("status") == "resolved":
        return jsonify({
            "success": False,
            "message": "Resolved tickets cannot be assigned."
        }), 400

    if ticket.get("assigned_to") == role:
        return jsonify({
            "success": False,
            "message": "Ticket is already assigned to you."
        }), 409

    collection.update_one(
        {"_id": oid},
        {
            "$set": {
                "assigned_to": role,
                "updated_at": datetime.utcnow()
            }
        }
    )

    log_admin_action(
        db,
        action="assign_ticket",
        resource=ticket_id,
        actor=role,
        metadata={
            "assigned_to": role
        }
    )

    updated = collection.find_one({"_id": oid})

    return jsonify({
        "success": True,
        "message": "Ticket assigned successfully.",
        "ticket": {
            "id": str(updated["_id"]),
            "user": updated.get("user"),
            "subject": updated.get("subject"),
            "status": updated.get("status"),
            "assigned_to": updated.get("assigned_to"),
            "updated_at": str(updated.get("updated_at"))
        }
    }), 200