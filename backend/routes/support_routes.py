# backend/routes/support_routes.py
from flask import Blueprint, request, jsonify
from datetime import datetime
import re
from bson.objectid import ObjectId

from backend.db import get_db
from backend.utils.auth_keys import get_role
from backend.utils.current_role_auth import current_platform_actor, require_current_roles, PLATFORM_ADMIN_ROLES
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

    if role not in {"support", "support_admin"}:
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

    if role not in {"support", "support_admin"}:
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

    search_pattern = re.escape(search)
    query = {}

    if status:
        query["status"] = status

    if mine:
        query["assigned_to"] = role

    if search:
        query["$or"] = [
            {"subject": {"$regex": search_pattern, "$options": "i"}},
            {"user": {"$regex": search_pattern, "$options": "i"}}
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

    if role not in {"support", "support_admin"}:
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

    if role not in {"support", "support_admin"}:
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

    if len(query_text) > 200:
        return jsonify({
            "success": False,
            "message": "Search query must be 200 characters or fewer."
        }), 400

    query_pattern = re.escape(query_text)
    db = get_db()
    collection = db[COLLECTIONS["support_tickets"]]

    query = {
        "$or": [
            {"user": {"$regex": query_pattern, "$options": "i"}},
            {"email": {"$regex": query_pattern, "$options": "i"}},
            {"subject": {"$regex": query_pattern, "$options": "i"}},
            {"description": {"$regex": query_pattern, "$options": "i"}},
            {"status": {"$regex": query_pattern, "$options": "i"}}
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

    if role not in {"support", "support_admin"}:
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

    if role not in {"support", "support_admin"}:
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

    if role not in {"support", "support_admin"}:
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

    if role not in {"support", "support_admin"}:
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

# =========================================================
# SUPPORT ADMIN OPERATIONS
# =========================================================

SUPPORT_SUPERVISOR_ROLES = (*PLATFORM_ADMIN_ROLES, "support_admin")


def _support_audit(db, *, action, resource, metadata=None):
    actor = current_platform_actor()
    try:
        log_admin_action(
            db,
            action=action,
            resource=str(resource or ""),
            actor=str(actor.get("id") or actor.get("role") or "unknown"),
            metadata=metadata or {},
        )
    except Exception:
        from flask import current_app
        current_app.logger.exception("Support operation succeeded but audit recording failed")


@support_bp.route("/admin/overview", methods=["GET"])
@require_current_roles(*SUPPORT_SUPERVISOR_ROLES)
def support_admin_overview():
    db = get_db()
    tickets = db[COLLECTIONS["support_tickets"]]
    users = db["users"]
    total = tickets.count_documents({})
    open_count = tickets.count_documents({"status": "open"})
    pending_count = tickets.count_documents({"status": "pending"})
    resolved_count = tickets.count_documents({"status": "resolved"})
    unassigned = tickets.count_documents({
        "$or": [{"assigned_to": None}, {"assigned_to": {"$exists": False}}, {"assigned_to": ""}]
    })

    team_roles = {"support", "support_admin"}
    staff_count = users.count_documents({
        "$or": [
            {"role": {"$in": list(team_roles)}},
            {"roles": {"$in": list(team_roles)}},
        ],
        "status": {"$nin": ["banned", "deleted", "disabled", "suspended"]},
    })
    latest = []
    for ticket in tickets.find({}).sort("updated_at", -1).limit(15):
        latest.append({
            "id": str(ticket.get("_id") or ""),
            "subject": str(ticket.get("subject") or "Support request"),
            "user": str(ticket.get("user") or ""),
            "status": str(ticket.get("status") or "open"),
            "priority": str(ticket.get("priority") or "normal"),
            "assigned_to": ticket.get("assigned_to"),
            "assigned_to_name": ticket.get("assigned_to_name") or "",
            "created_at": str(ticket.get("created_at") or ""),
            "updated_at": str(ticket.get("updated_at") or ""),
        })

    return jsonify(success=True, stats={
        "total": total,
        "open": open_count,
        "pending": pending_count,
        "resolved": resolved_count,
        "unassigned": unassigned,
        "support_staff": staff_count,
        "resolution_rate": round(resolved_count / total * 100, 1) if total else 0,
    }, recent=latest), 200


@support_bp.route("/admin/team", methods=["GET"])
@require_current_roles(*SUPPORT_SUPERVISOR_ROLES)
def support_admin_team():
    db = get_db()
    users = db["users"]
    query = {
        "$or": [
            {"role": {"$in": ["support", "support_admin"]}},
            {"roles": {"$in": ["support", "support_admin"]}},
        ],
        "status": {"$nin": ["banned", "deleted", "disabled", "suspended", "inactive"]},
        "is_active": {"$ne": False},
    }
    team = []
    for user in users.find(query).sort("created_at", -1).limit(300):
        user_id = str(user.get("_id") or user.get("id") or user.get("user_id") or "")
        role = str(user.get("role") or "support")
        assigned = db[COLLECTIONS["support_tickets"]].count_documents({
            "$or": [
                {"assigned_to_user_id": user_id},
                {"assigned_to": user_id},
                {"assigned_to_contact": user.get("contact") or user.get("email")},
            ],
            "status": {"$ne": "resolved"},
        })
        team.append({
            "id": user_id,
            "full_name": user.get("full_name") or user.get("fullName") or user.get("name") or "",
            "contact": user.get("contact") or user.get("email") or "",
            "role": role,
            "status": str(user.get("status") or "active"),
            "verified": bool(user.get("verified", False)),
            "open_assigned_tickets": assigned,
        })
    return jsonify(success=True, team=team, count=len(team)), 200


@support_bp.route("/admin/activity", methods=["GET"])
@require_current_roles(*SUPPORT_SUPERVISOR_ROLES)
def support_admin_activity():
    db = get_db()
    limit = min(max(request.args.get("limit", default=50, type=int) or 50, 1), 100)
    query = {"action": {"$in": [
        "assign_ticket", "resolve_ticket", "support_ticket_assigned",
        "user_account_banned", "user_account_unbanned",
    ]}}
    rows = []
    for item in db[COLLECTIONS["admin_actions"]].find(query).sort("timestamp", -1).limit(limit):
        rows.append({
            "id": str(item.get("_id") or ""),
            "action": str(item.get("action") or ""),
            "resource": str(item.get("resource") or ""),
            "actor": str(item.get("actor") or ""),
            "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            "timestamp": str(item.get("timestamp") or item.get("created_at") or ""),
        })
    return jsonify(success=True, activity=rows, count=len(rows)), 200


@support_bp.route("/admin/tickets/<ticket_id>/assign", methods=["POST"])
@require_current_roles(*SUPPORT_SUPERVISOR_ROLES)
def support_admin_assign_ticket(ticket_id):
    if not ObjectId.is_valid(str(ticket_id or "")):
        return jsonify(success=False, message="A valid ticket ID is required."), 400
    data = request.get_json(silent=True) or {}
    support_user_id = str(data.get("support_user_id") or "").strip()
    if not support_user_id:
        return jsonify(success=False, message="Choose an active support agent."), 400

    db = get_db()
    user_query = {"_id": ObjectId(support_user_id)} if ObjectId.is_valid(support_user_id) else {
        "$or": [{"id": support_user_id}, {"user_id": support_user_id}]
    }
    staff = db["users"].find_one(user_query)
    if not staff:
        return jsonify(success=False, message="The chosen support account was not found."), 404
    roles = set(staff.get("roles") if isinstance(staff.get("roles"), list) else [])
    staff_role = str(staff.get("role") or "").strip().casefold()
    if staff_role != "support" and "support" not in {str(value).casefold() for value in roles}:
        return jsonify(success=False, message="Tickets may only be assigned to Support Agents, not a Support Administrator."), 422
    if str(staff.get("status") or "active").casefold() not in {"active", "verified"} or staff.get("is_active") is False:
        return jsonify(success=False, message="The selected support account is not active."), 409

    ticket_oid = ObjectId(ticket_id)
    tickets = db[COLLECTIONS["support_tickets"]]
    ticket = tickets.find_one({"_id": ticket_oid})
    if not ticket:
        return jsonify(success=False, message="Ticket not found."), 404
    if str(ticket.get("status") or "").casefold() == "resolved":
        return jsonify(success=False, message="Resolved tickets cannot be reassigned."), 409

    actor = current_platform_actor()
    staff_id = str(staff.get("_id") or staff.get("id") or staff.get("user_id") or support_user_id)
    staff_name = str(staff.get("full_name") or staff.get("fullName") or staff.get("name") or "")
    now = datetime.utcnow()
    tickets.update_one({"_id": ticket_oid}, {"$set": {
        "assigned_to": staff_id,
        "assigned_to_user_id": staff_id,
        "assigned_to_name": staff_name,
        "assigned_to_contact": str(staff.get("contact") or staff.get("email") or ""),
        "assigned_by": str(actor.get("id") or ""),
        "assigned_at": now,
        "updated_at": now,
    }})
    _support_audit(db, action="support_ticket_assigned", resource=ticket_id, metadata={
        "support_user_id": staff_id,
        "support_name": staff_name,
        "previous_assignment": ticket.get("assigned_to"),
    })
    updated = tickets.find_one({"_id": ticket_oid})
    return jsonify(success=True, message=f"Ticket assigned to {staff_name or 'the selected support agent'}.", ticket={
        "id": str(updated["_id"]),
        "subject": updated.get("subject") or "",
        "status": updated.get("status") or "open",
        "assigned_to": updated.get("assigned_to"),
        "assigned_to_user_id": updated.get("assigned_to_user_id"),
        "assigned_to_name": updated.get("assigned_to_name"),
        "updated_at": str(updated.get("updated_at") or ""),
    }), 200
