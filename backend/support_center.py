"""Secure Support Team control plane for the existing RevelaCode Flask/Mongo app.

This module deliberately reuses the existing users collection, JWT identity,
Resend sender, support ticket store and Daraja checkout records. It does not
create a second identity or payment ledger.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from functools import wraps
from html.parser import HTMLParser
from urllib.parse import urlencode

import requests
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from flask import Blueprint, current_app, jsonify, request
from werkzeug.security import generate_password_hash

from backend.db import get_db
from backend.utils.current_role_auth import resolve_current_actor
from backend.utils.admin_invitation_email import send_admin_invitation_email
from backend.email_service import send_verification_email
from backend.support_config import SUPPORT_EMAIL

support_center_bp = Blueprint("support_center", __name__)
ADMIN_ROLES = {"super_admin"}
SUPPORT_ADMIN_ROLES = {"support_admin"}
SUPPORT_AGENT_ROLES = {"support_agent", "support"}  # "support" is the legacy agent role.
ALL_SUPPORT_ROLES = ADMIN_ROLES | SUPPORT_ADMIN_ROLES | SUPPORT_AGENT_ROLES
INVITES = "admin_invitations"
AUDIT = "support_audit_events"
TICKETS = "support_tickets"
PAYROLL = "support_payroll_records"
INBOUND = "support_inbound_messages"
RATE_LIMITS = "support_action_limits"
SEATS = "support_admin_seats"
UTC = timezone.utc


def now_utc():
    return datetime.now(UTC)


def _actor():
    actor, error, status = resolve_current_actor(request)
    if error:
        return None, (jsonify(error), status)
    roles = {str(x).strip().casefold() for x in (actor.get("roles") or [])}
    roles.add(str(actor.get("role") or "").strip().casefold())
    if str(actor.get("id") or "") == str(os.getenv("SUPER_ADMIN_USER_ID") or "").strip():
        roles.add("super_admin")
    actor = {**actor, "roles": sorted(roles)}
    return actor, None


def _require(*allowed):
    allowed_set = {str(x).casefold() for x in allowed}

    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            actor, failure = _actor()
            if failure:
                return failure
            if not allowed_set.intersection(actor["roles"]):
                return jsonify(success=False, code="forbidden", message="Your current support role cannot perform this action."), 403
            return fn(*args, actor=actor, **kwargs)
        return wrapped
    return decorate


def _id_query(value):
    value = str(value or "").strip()
    if not value or len(value) > 128:
        return None
    terms = [{"id": value}, {"user_id": value}]
    if ObjectId.is_valid(value):
        terms.insert(0, {"_id": ObjectId(value)})
    return {"$or": terms}


def _user_id(user):
    return str(user.get("_id") or user.get("id") or user.get("user_id") or "")


def _user_roles(user):
    raw = user.get("roles") if isinstance(user.get("roles"), list) else []
    return {str(x).strip().casefold() for x in raw if x} | {str(user.get("role") or "").strip().casefold()}


def _mask_email(value):
    value = str(value or "")
    if "@" not in value:
        return ""
    name, domain = value.split("@", 1)
    return (name[:1] + "***@" + domain) if name else "***@" + domain


def _mask_phone(value):
    digits = re.sub(r"\D", "", str(value or ""))
    return ("*" * max(0, len(digits) - 3) + digits[-3:]) if digits else ""


def _safe_member(user):
    return {
        "id": _user_id(user),
        "full_name": user.get("full_name") or user.get("fullName") or user.get("name") or "",
        "email": _mask_email(user.get("email") or user.get("contact")),
        "phone": _mask_phone(user.get("phone") or user.get("contact")),
        "role": user.get("role") or "user",
        "status": user.get("status") or "active",
        "verified": bool(user.get("verified", user.get("is_verified", False))),
        "created_at": user.get("created_at").isoformat() if hasattr(user.get("created_at"), "isoformat") else user.get("created_at"),
    }


def _audit(actor, action, target_type, target_id, before=None, after=None, reason=None):
    """Append-only, hash-linked audit event. No update/delete API is exposed."""
    db = get_db()
    events = db[AUDIT]
    previous = events.find_one({}, sort=[("sequence", -1)])
    sequence = int((previous or {}).get("sequence", 0)) + 1
    previous_hash = str((previous or {}).get("event_hash") or "GENESIS")
    document = {
        "sequence": sequence,
        "actor_id": actor.get("id"),
        "actor_role": actor.get("role"),
        "action": action,
        "target_type": target_type,
        "target_id": str(target_id or ""),
        "reason": str(reason or "")[:1000],
        "before": before or {},
        "after": after or {},
        "ip": request.headers.get("CF-Connecting-IP") or request.remote_addr,
        "user_agent": request.headers.get("User-Agent", "")[:300],
        "created_at": now_utc(),
        "previous_hash": previous_hash,
    }
    canonical = json.dumps(document, sort_keys=True, default=str, separators=(",", ":"))
    document["event_hash"] = hashlib.sha256((previous_hash + canonical).encode("utf-8")).hexdigest()
    events.insert_one(document)
    return document


def ensure_indexes():
    db = get_db()
    db[INVITES].create_index([("token_hash", 1)], unique=True, sparse=True)
    db[INVITES].create_index([("contact", 1), ("status", 1)])
    db[AUDIT].create_index([("sequence", 1)], unique=True)
    db[AUDIT].create_index([("created_at", -1)])
    db[TICKETS].create_index([("message_id", 1)], unique=True, partialFilterExpression={"message_id": {"$type": "string"}}, name="uq_support_ticket_message_id")
    db[TICKETS].create_index([("status", 1), ("updated_at", -1)])
    db[PAYROLL].create_index([("member_id", 1), ("period_start", 1), ("period_end", 1)])
    db[INBOUND].create_index([("message_id", 1)], unique=True, sparse=True)
    db[RATE_LIMITS].create_index([("expires_at", 1)], expireAfterSeconds=0)
    for seat in range(1, 4):
        db[SEATS].update_one(
            {"_id": seat},
            {"$setOnInsert": {"status": "available", "member_id": None, "invitation_id": None}},
            upsert=True,
        )


def _expire_pending_admin_invites():
    db = get_db()
    now = now_utc()
    expired = list(db[INVITES].find({"role": "support_admin", "status": "pending", "expires_at": {"$lte": now}}, {"_id": 1}))
    if expired:
        ids = [str(row["_id"]) for row in expired]
        db[INVITES].update_many({"_id": {"$in": [row["_id"] for row in expired]}, "status": "pending"}, {"$set": {"status": "expired", "updated_at": now}})
        db[SEATS].update_many({"invitation_id": {"$in": ids}, "status": "reserved"}, {"$set": {"status": "available", "member_id": None, "invitation_id": None}})


def _invite_seat(invitation_id):
    db = get_db()
    return db[SEATS].find_one_and_update(
        {"status": "available"},
        {"$set": {"status": "reserved", "invitation_id": str(invitation_id), "reserved_at": now_utc()}},
        sort=[("_id", 1)],
        return_document=True,
    )


def _release_seat(invitation_id):
    get_db()[SEATS].update_one(
        {"invitation_id": str(invitation_id), "status": "reserved"},
        {"$set": {"status": "available", "member_id": None, "invitation_id": None}},
    )


def _send_status_notice(email, subject, message):
    api_key = str(os.getenv("RESEND_API_KEY") or "").strip()
    sender = f"RevelaCode Support <{SUPPORT_EMAIL}>"
    if not api_key or not sender or not email:
        current_app.logger.warning("Support notification not sent: Resend configuration or recipient missing.")
        return False
    try:
        import resend
        resend.api_key = api_key
        resend.Emails.send({
            "from": sender,
            "to": [email],
            "reply_to": SUPPORT_EMAIL,
            "subject": subject,
            "text": message + "\n\nIf you believe this is an error, contact " + SUPPORT_EMAIL + ".",
        })
        return True
    except Exception:
        current_app.logger.exception("Support status notification failed.")
        return False


def _safe_invite(row):
    return {
        "id": str(row.get("_id") or ""),
        "name": row.get("full_name") or "",
        "email": _mask_email(row.get("contact")),
        "role": row.get("role") or "",
        "status": row.get("status") or "unknown",
        "created_at": row.get("created_at").isoformat() if hasattr(row.get("created_at"), "isoformat") else row.get("created_at"),
        "expires_at": row.get("expires_at").isoformat() if hasattr(row.get("expires_at"), "isoformat") else row.get("expires_at"),
        "invited_by": row.get("invited_by") or "",
        "delivery_status": row.get("delivery_status") or "",
    }


@support_center_bp.get("/overview")
@_require("super_admin", "support_admin")
def overview(actor):
    db = get_db()
    _expire_pending_admin_invites()
    active = db["users"].count_documents({
        "$or": [{"role": "support_admin"}, {"roles": "support_admin"}],
        "status": {"$nin": ["banned", "suspended", "deleted", "disabled"]},
        "is_active": {"$ne": False},
    })
    pending = db[INVITES].count_documents({"role": "support_admin", "status": "pending", "expires_at": {"$gt": now_utc()}})
    seats = list(db[SEATS].find({}).sort("_id", 1))
    members = []
    for row in db["users"].find({"$or": [{"role": {"$in": list(SUPPORT_ADMIN_ROLES | SUPPORT_AGENT_ROLES)}}, {"roles": {"$in": list(SUPPORT_ADMIN_ROLES | SUPPORT_AGENT_ROLES)}}]}).limit(300):
        members.append(_safe_member(row))
    invites = [_safe_invite(x) for x in db[INVITES].find({"status": {"$in": ["pending", "delivery_failed"]}}).sort("created_at", -1).limit(100)]
    return jsonify(
        success=True,
        seats={"limit": 3, "active": active, "pending": pending, "used": min(3, active + pending), "available": max(0, 3 - active - pending)},
        seat_records=[{"seat": x["_id"], "status": x.get("status"), "member_id": x.get("member_id")} for x in seats],
        members=members,
        invitations=invites,
    ), 200


@support_center_bp.post("/invitations")
@_require("super_admin", "support_admin")
def create_invitation(actor):
    data = request.get_json(silent=True) or {}
    name = str(data.get("full_name") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    role = str(data.get("role") or "").strip().lower()
    if not name or len(name) > 120 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify(success=False, message="A name and valid email address are required."), 422
    if role not in {"support_admin", "support_agent"}:
        return jsonify(success=False, message="Only Support Admin or Support Agent invitations are supported."), 422
    if role == "support_admin" and "super_admin" not in actor["roles"]:
        return jsonify(success=False, code="super_admin_required", message="Only the Super Admin can invite Support Admins."), 403
    if role == "support_agent" and not ({"super_admin", "support_admin"} & set(actor["roles"])):
        return jsonify(success=False, code="support_admin_required", message="A Support Admin must invite Support Agents."), 403

    db = get_db()
    existing = db["users"].find_one({"$or": [{"email": {"$regex": "^" + re.escape(email) + "$", "$options": "i"}}, {"contact": {"$regex": "^" + re.escape(email) + "$", "$options": "i"}}]})
    if existing:
        return jsonify(success=False, code="account_already_exists", message="This email already belongs to an account. Sign in to that account or use the account-linking flow; do not create a duplicate."), 409

    now = now_utc()
    expiry = now + timedelta(hours=48)
    token = secrets.token_urlsafe(40)
    invitation = {
        "full_name": name,
        "contact": email,
        "role": role,
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "status": "pending",
        "invited_by": actor["id"],
        "created_at": now,
        "expires_at": expiry,
        "updated_at": now,
        "delivery_status": "pending",
    }
    inserted = db[INVITES].insert_one(invitation)
    if role == "support_admin":
        reserved = _invite_seat(inserted.inserted_id)
        if not reserved:
            db[INVITES].update_one({"_id": inserted.inserted_id}, {"$set": {"status": "seat_limit_reached"}})
            return jsonify(success=False, code="support_admin_seat_limit", message="All three Support Admin seats are active or reserved."), 409
    try:
        send_admin_invitation_email(recipient=email, full_name=name, role=("support" if role == "support_agent" else role), token=token, expires_at=expiry)
    except Exception:
        db[INVITES].update_one({"_id": inserted.inserted_id}, {"$set": {"status": "delivery_failed", "delivery_status": "failed", "updated_at": now_utc()}})
        if role == "support_admin":
            _release_seat(inserted.inserted_id)
        _audit(actor, "support.invitation.delivery_failed", "invitation", inserted.inserted_id, after={"role": role})
        return jsonify(success=False, code="invitation_email_failed", message="The invitation was saved but Resend did not accept the email. Check the backend sender configuration."), 502
    db[INVITES].update_one({"_id": inserted.inserted_id}, {"$set": {"delivery_status": "accepted_by_provider", "updated_at": now_utc()}})
    _audit(actor, "support.invitation.created", "invitation", inserted.inserted_id, after={"role": role, "expires_at": expiry.isoformat()})
    return jsonify(success=True, invitation={"id": str(inserted.inserted_id), "role": role, "status": "pending", "expires_at": expiry.isoformat()}), 201


@support_center_bp.get("/invitations/preview")
def preview_invitation():
    token = str(request.args.get("token") or "").strip()
    email = str(request.args.get("email") or "").strip().lower()
    if len(token) < 32 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify(success=False, code="invalid_invitation", message="The invitation link is incomplete."), 400
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    invite = get_db()[INVITES].find_one({"token_hash": token_hash, "contact": email, "status": "pending"})
    if not invite:
        return jsonify(success=False, code="invitation_not_found", message="This invitation is invalid, expired, revoked or already used."), 404
    expiry = invite.get("expires_at")
    if not isinstance(expiry, datetime) or (expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry.astimezone(UTC)) <= now_utc():
        get_db()[INVITES].update_one({"_id": invite["_id"], "status": "pending"}, {"$set": {"status": "expired"}})
        _release_seat(invite["_id"])
        return jsonify(success=False, code="invitation_expired", message="This invitation has expired. Ask the inviter to issue a new one."), 410
    return jsonify(success=True, invitation={"full_name": invite.get("full_name") or "", "contact": email, "role": invite.get("role") or "", "expires_at": expiry.isoformat()}), 200


@support_center_bp.post("/invitations/accept")
def accept_invitation():
    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    confirm = str(data.get("confirm_password") or "")
    if len(token) < 32 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify(success=False, code="invalid_invitation", message="The invitation link is invalid."), 400
    if len(password) < 12 or len(password) > 256 or password != confirm:
        return jsonify(success=False, message="Use a matching password of at least 12 characters."), 422
    db = get_db()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    invite = db[INVITES].find_one({"token_hash": token_hash, "contact": email, "status": "pending"})
    if not invite:
        return jsonify(success=False, code="invitation_invalid_or_used", message="The invitation is invalid, expired, revoked or already used."), 404
    expires = invite.get("expires_at")
    if not isinstance(expires, datetime) or (expires.replace(tzinfo=UTC) if expires.tzinfo is None else expires.astimezone(UTC)) <= now_utc():
        db[INVITES].update_one({"_id": invite["_id"], "status": "pending"}, {"$set": {"status": "expired"}})
        _release_seat(invite["_id"])
        return jsonify(success=False, code="invitation_expired", message="This invitation has expired. Ask a Support Admin to issue a new one."), 410
    role = str(invite.get("role") or "")
    if role not in {"support_admin", "support_agent"}:
        return jsonify(success=False, code="invalid_invitation_role", message="This invitation role is not valid."), 409
    users = db["users"]
    if users.find_one({"$or": [{"email": email}, {"contact": email}]}):
        return jsonify(success=False, code="account_already_exists", message="An account already exists for this email. Sign in first and use the provider-linking process."), 409
    claim = db[INVITES].update_one({"_id": invite["_id"], "status": "pending", "expires_at": {"$gt": now_utc()}}, {"$set": {"status": "accepting", "accepted_attempt_at": now_utc()}})
    if claim.modified_count != 1:
        return jsonify(success=False, code="invitation_already_claimed", message="This invitation has already been used."), 409
    user_data = {
        "full_name": invite.get("full_name") or "",
        "fullName": invite.get("full_name") or "",
        "name": invite.get("full_name") or "",
        "contact": email,
        "email": email,
        "role": role,
        "roles": [role],
        "password": generate_password_hash(password),
        "verified": True,
        "is_verified": True,
        "status": "active",
        "is_active": True,
        "token_version": 0,
        "created_at": now_utc(),
        "invited_by": invite.get("invited_by"),
        "support_invited": True,
    }
    try:
        inserted = users.insert_one(user_data)
    except Exception:
        db[INVITES].update_one({"_id": invite["_id"], "status": "accepting"}, {"$set": {"status": "pending"}})
        return jsonify(success=False, code="account_creation_failed", message="The account could not be created. Try accepting the invitation again."), 503
    uid = str(inserted.inserted_id)
    db[INVITES].update_one({"_id": invite["_id"], "status": "accepting"}, {"$set": {"status": "accepted", "accepted_at": now_utc(), "accepted_user_id": uid}})
    if role == "support_admin":
        db[SEATS].update_one({"invitation_id": str(invite["_id"])}, {"$set": {"status": "active", "member_id": uid, "activated_at": now_utc()}})
    _audit({"id": uid, "role": role}, "support.invitation.accepted", "user", uid, after={"role": role})
    return jsonify(success=True, role=role, message="Your support account is ready. Sign in to continue."), 201


@support_center_bp.get("/invitations")
@_require("super_admin", "support_admin")
def list_invitations(actor):
    rows = get_db()[INVITES].find({"role": {"$in": ["support_admin", "support_agent", "support"]}}).sort("created_at", -1).limit(200)
    return jsonify(success=True, invitations=[_safe_invite(row) for row in rows]), 200


@support_center_bp.post("/invitations/<invitation_id>/resend")
@_require("super_admin", "support_admin")
def resend_invitation(invitation_id, actor):
    if not ObjectId.is_valid(invitation_id):
        return jsonify(success=False, message="Invalid invitation ID."), 400
    db = get_db()
    row = db[INVITES].find_one({"_id": ObjectId(invitation_id), "status": "pending"})
    if not row:
        return jsonify(success=False, message="Only a pending invitation can be resent."), 404
    role = row.get("role")
    if role == "support_admin" and "super_admin" not in actor["roles"]:
        return jsonify(success=False, message="Only the Super Admin can resend Support Admin invitations."), 403
    if role in {"support_agent", "support"} and not ({"super_admin", "support_admin"} & set(actor["roles"])):
        return jsonify(success=False, message="Support Admin access is required."), 403
    token = secrets.token_urlsafe(40)
    expiry = now_utc() + timedelta(hours=48)
    db[INVITES].update_one({"_id": row["_id"], "status": "pending"}, {"$set": {"token_hash": hashlib.sha256(token.encode()).hexdigest(), "expires_at": expiry, "updated_at": now_utc(), "delivery_status": "pending"}})
    try:
        send_admin_invitation_email(recipient=row["contact"], full_name=row.get("full_name") or "", role=("support" if role in {"support_agent", "support"} else role), token=token, expires_at=expiry)
    except Exception:
        db[INVITES].update_one({"_id": row["_id"]}, {"$set": {"delivery_status": "failed"}})
        _audit(actor, "support.invitation.resend_failed", "invitation", invitation_id, after={"role": role})
        return jsonify(success=False, message="Resend could not accept the renewed invitation email."), 502
    db[INVITES].update_one({"_id": row["_id"]}, {"$set": {"delivery_status": "accepted_by_provider"}})
    _audit(actor, "support.invitation.resent", "invitation", invitation_id, after={"expires_at": expiry.isoformat()})
    return jsonify(success=True, expires_at=expiry.isoformat()), 200


@support_center_bp.delete("/invitations/<invitation_id>")
@_require("super_admin", "support_admin")
def revoke_invitation(invitation_id, actor):
    if not ObjectId.is_valid(invitation_id):
        return jsonify(success=False, message="Invalid invitation ID."), 400
    db = get_db()
    row = db[INVITES].find_one({"_id": ObjectId(invitation_id), "status": "pending"})
    if not row:
        return jsonify(success=False, message="Only a pending invitation can be revoked."), 404
    if row.get("role") == "support_admin" and "super_admin" not in actor["roles"]:
        return jsonify(success=False, message="Only the Super Admin can revoke Support Admin invitations."), 403
    db[INVITES].update_one({"_id": row["_id"], "status": "pending"}, {"$set": {"status": "revoked", "revoked_at": now_utc(), "revoked_by": actor["id"]}})
    _release_seat(row["_id"])
    _audit(actor, "support.invitation.revoked", "invitation", invitation_id, before={"status": "pending"}, after={"status": "revoked"})
    return jsonify(success=True), 200


@support_center_bp.patch("/members/<member_id>/status")
@_require("super_admin", "support_admin")
def member_status(member_id, actor):
    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "").strip().lower()
    reason = str(data.get("reason") or "").strip()
    if action not in {"ban", "suspend", "restore", "remove"} or len(reason) < 8 or len(reason) > 1000:
        return jsonify(success=False, message="Choose ban, suspend, restore or remove and provide a reason of 8–1,000 characters."), 422
    query = _id_query(member_id)
    if not query:
        return jsonify(success=False, message="Invalid member ID."), 400
    db = get_db()
    users = db["users"]
    target = users.find_one(query)
    if not target:
        return jsonify(success=False, message="Support member not found."), 404
    target_roles = _user_roles(target)
    target_role = str(target.get("role") or "user").casefold()
    is_support_admin = "support_admin" in target_roles
    is_support_agent = bool(target_roles & SUPPORT_AGENT_ROLES)
    if not (is_support_admin or is_support_agent):
        return jsonify(success=False, message="This account is not a support-team member."), 409
    if str(_user_id(target)) == str(actor["id"]):
        return jsonify(success=False, message="You cannot change your own support access."), 409
    if is_support_admin and "super_admin" not in actor["roles"]:
        return jsonify(success=False, code="super_admin_required", message="Only the Super Admin can ban, suspend or remove a Support Admin."), 403
    if "support_admin" not in actor["roles"] and "super_admin" not in actor["roles"]:
        return jsonify(success=False, message="Support Admin access is required."), 403

    before = {"role": target_role, "status": target.get("status") or "active", "is_active": target.get("is_active", True)}
    now = now_utc()
    if action == "restore":
        if before["status"] not in {"banned", "suspended", "blocked", "disabled"}:
            return jsonify(success=False, message="Only a banned or suspended member can be restored."), 409
        updates = {"status": "active", "is_active": True, "restored_at": now, "restored_by": actor["id"]}
    elif action == "remove":
        updates = {"status": "deleted", "is_active": False, "archived": True, "deleted_at": now, "deleted_by": actor["id"], "removal_reason": reason}
    else:
        updates = {"status": "banned" if action == "ban" else "suspended", "is_active": False, f"{action}_at": now, f"{action}_by": actor["id"], f"{action}_reason": reason}
    users.update_one(query, {"$set": {**updates, "updated_at": now}, "$inc": {"token_version": 1}})
    uid = _user_id(target)
    for collection_name in ("jumuiya_user_sessions", "jumuiya_auth_sessions", "jumuiya_refresh_tokens", "user_sessions", "refresh_tokens"):
        try:
            db[collection_name].delete_many({"$or": [{"user_id": uid}, {"userId": uid}, {"account_id": uid}]})
        except Exception:
            current_app.logger.exception("Could not clear one session collection: %s", collection_name)
    if action == "remove":
        db[TICKETS].update_many({"assigned_to_user_id": uid, "status": {"$in": ["open", "pending"]}}, {"$unset": {"assigned_to_user_id": "", "assigned_to": "", "assigned_to_name": "", "assigned_to_contact": ""}, "$set": {"updated_at": now, "reassignment_reason": "Assignee archived"}})
    after = {"status": updates["status"], "is_active": updates["is_active"], "token_version_incremented": True}
    _audit(actor, f"support.member.{action}", "user", uid, before=before, after=after, reason=reason)
    action_label = {"ban": "banned", "suspend": "suspended", "restore": "restored", "remove": "removed"}[action]
    _send_status_notice(target.get("email") or target.get("contact"), "RevelaCode support account update", f"Your support-team account access has been {action_label}. Reason: {reason}")
    if is_support_admin and action in {"ban", "suspend", "remove"}:
        owner_id = str(os.getenv("SUPER_ADMIN_USER_ID") or "").strip()
        owner = db["users"].find_one(_id_query(owner_id)) if owner_id else None
        if owner:
            _send_status_notice(owner.get("email") or owner.get("contact"), "Support Admin account update", f"A Support Admin account was {action}d by a Super Admin. This is an informational notice.")
    if action in {"ban", "suspend", "remove"} and is_support_admin:
        db[SEATS].update_one({"member_id": uid}, {"$set": {"status": "available", "member_id": None, "invitation_id": None}})
    elif action == "restore" and is_support_admin:
        slot = db[SEATS].find_one_and_update({"status": "available"}, {"$set": {"status": "active", "member_id": uid, "invitation_id": None, "activated_at": now}}, sort=[("_id", 1)])
        if not slot:
            users.update_one(query, {"$set": {"status": "suspended", "is_active": False}})
            return jsonify(success=False, code="support_admin_seat_limit", message="No Support Admin seat is available. The account remains suspended."), 409
    return jsonify(success=True, message=f"Support member {action} completed.", member=_safe_member(users.find_one(query))), 200


@support_center_bp.patch("/members/<member_id>/role")
@_require("super_admin", "support_admin")
def member_role(member_id, actor):
    data = request.get_json(silent=True) or {}
    role = str(data.get("role") or "").strip().lower()
    reason = str(data.get("reason") or "").strip()
    if role not in {"support_agent", "support_admin"} or len(reason) < 8:
        return jsonify(success=False, message="Choose a support role and provide a reason."), 422
    query = _id_query(member_id)
    target = get_db()["users"].find_one(query or {})
    if not target:
        return jsonify(success=False, message="Member not found."), 404
    roles = _user_roles(target)
    if "super_admin" in roles:
        return jsonify(success=False, message="A support role cannot be assigned to the Super Admin."), 403
    if "support_admin" in roles and "super_admin" not in actor["roles"]:
        return jsonify(success=False, message="Only the Super Admin can change a Support Admin's role."), 403
    if role == "support_admin" and "super_admin" not in actor["roles"]:
        return jsonify(success=False, message="Only the Super Admin can assign Support Admin."), 403
    if role == "support_admin" and "support_admin" not in roles:
        ensure_indexes()
        seat = get_db()[SEATS].find_one_and_update({"status": "available"}, {"$set": {"status": "active", "member_id": _user_id(target), "invitation_id": None, "activated_at": now_utc()}}, sort=[("_id", 1)], return_document=True)
        if not seat:
            return jsonify(success=False, code="support_admin_seat_limit", message="All three Support Admin seats are active or reserved."), 409
    before = {"role": target.get("role")}
    get_db()["users"].update_one(query, {"$set": {"role": role, "roles": [role], "updated_at": now_utc()}})
    if role == "support_agent" and "support_admin" in roles:
        get_db()[SEATS].update_one({"member_id": _user_id(target)}, {"$set": {"status": "available", "member_id": None, "invitation_id": None}})
    _audit(actor, "support.member.role_changed", "user", member_id, before=before, after={"role": role}, reason=reason)
    return jsonify(success=True), 200


@support_center_bp.get("/verification/search")
@_require("support_agent", "support", "support_admin", "super_admin")
def search_verification(actor):
    lookup = str(request.args.get("lookup") or "").strip()
    if len(lookup) < 3 or len(lookup) > 254:
        return jsonify(success=False, message="Enter an email address or phone number."), 422
    escaped = re.escape(lookup)
    user = get_db()["users"].find_one({"$or": [{"email": {"$regex": "^" + escaped + "$", "$options": "i"}}, {"contact": {"$regex": "^" + escaped + "$", "$options": "i"}}, {"phone": lookup}]})
    if not user:
        _audit(actor, "support.verification.search_not_found", "user", "unknown", after={"lookup_type": "email" if "@" in lookup else "phone"})
        return jsonify(success=False, message="No matching account was found."), 404
    verified = bool(user.get("verified", user.get("is_verified", False)))
    recipient = str(user.get("email") or (user.get("contact") if "@" in str(user.get("contact") or "") else "") or "")
    result = {"user_id": _user_id(user), "verified": verified, "status": user.get("status") or "active", "email": _mask_email(recipient), "phone": _mask_phone(user.get("phone") or (user.get("contact") if "@" not in str(user.get("contact") or "") else "")), "email_available": bool(recipient), "sms_available": False}
    _audit(actor, "support.verification.search", "user", result["user_id"], after={"verified": verified})
    return jsonify(success=True, account=result), 200


@support_center_bp.post("/verification/resend")
@_require("support_agent", "support", "support_admin", "super_admin")
def resend_verification(actor):
    data = request.get_json(silent=True) or {}
    lookup = str(data.get("lookup") or "").strip()
    if len(lookup) < 3 or len(lookup) > 254:
        return jsonify(success=False, message="Enter an email address or phone number."), 422
    db = get_db()
    escaped = re.escape(lookup)
    user = db["users"].find_one({"$or": [{"email": {"$regex": "^" + escaped + "$", "$options": "i"}}, {"contact": {"$regex": "^" + escaped + "$", "$options": "i"}}, {"phone": lookup}]})
    if not user:
        _audit(actor, "support.verification.lookup_not_found", "user", "unknown", after={"lookup_type": "email" if "@" in lookup else "phone"})
        return jsonify(success=False, message="No matching account was found."), 404
    uid = _user_id(user)
    if bool(user.get("verified", user.get("is_verified", False))):
        return jsonify(success=True, verified=True, message="This account is already verified.", contact=_mask_email(user.get("email") or user.get("contact"))), 200
    recipient = str(user.get("email") or (user.get("contact") if "@" in str(user.get("contact") or "") else "") or "").strip().lower()
    if not recipient:
        _audit(actor, "support.verification.sms_unavailable", "user", uid, after={"channel": "sms", "status": "not_configured"})
        return jsonify(success=False, code="sms_provider_not_configured", message="This account has no email address available and SMS/OTP delivery is not configured."), 503
    limits = db[RATE_LIMITS]
    limit_now = now_utc()
    allowed = False
    # Three independent one-hour slots provide a rolling limit across workers.
    for slot in range(1, 4):
        slot_id = f"{uid}:verification_resend:{slot}"
        try:
            result = limits.update_one(
                {"_id": slot_id, "$or": [{"expires_at": {"$lte": limit_now}}, {"expires_at": {"$exists": False}}]},
                {"$set": {"user_id": uid, "action": "verification_resend", "created_at": limit_now, "expires_at": limit_now + timedelta(hours=1)}},
                upsert=True,
            )
            if result.modified_count == 1 or result.upserted_id:
                allowed = True
                break
        except DuplicateKeyError:
            continue
    if not allowed:
        _audit(actor, "support.verification.rate_limited", "user", uid, after={"limit": 3, "window": "rolling_60_minutes"})
        return jsonify(success=False, code="verification_resend_rate_limited", message="This account has reached the limit of three resend requests in one hour."), 429
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = now_utc() + timedelta(minutes=10)
    db["users"].update_one({"_id": user["_id"]}, {"$set": {"verification": {"code": code, "expires": expires.isoformat()}}})
    try:
        send_verification_email(recipient, code, purpose="support_activation")
    except Exception:
        _audit(actor, "support.verification.delivery_failed", "user", uid, after={"channel": "email"})
        return jsonify(success=False, message="The verification email could not be sent. Check the email provider configuration."), 502
    _audit(actor, "support.verification.resent", "user", uid, after={"channel": "email", "expires_in_seconds": 600})
    return jsonify(success=True, message="A new verification code was sent. The code is never displayed to support staff.", contact=_mask_email(recipient)), 200


@support_center_bp.get("/plans/pending")
@_require("support_agent", "support", "support_admin", "super_admin")
def pending_plans(actor):
    rows = get_db()["jumuiya_revenue_mpesa_checkouts"]
    cursor = rows.find({"status": {"$in": ["pending", "initiating", "awaiting_verification", "submission_unknown", "initiation_failed", "failed", "verified_activation_failed"]}}).sort("created_at", -1).limit(200)
    items = []
    for row in cursor:
        items.append({
            "id": str(row.get("_id") or ""),
            "user_id": str(row.get("user_id") or ""),
            "hub": row.get("hub"),
            "plan_code": row.get("plan_code"),
            "amount": row.get("amount"),
            "currency": row.get("currency") or "KES",
            "status": row.get("status"),
            "checkout_request_id": row.get("checkout_request_id") or "",
            "phone": _mask_phone(row.get("phone")),
            "receipt": row.get("receipt") or "",
            "created_at": row.get("created_at").isoformat() if hasattr(row.get("created_at"), "isoformat") else row.get("created_at"),
            "message": str(row.get("message") or "")[:300],
        })
    return jsonify(success=True, checkouts=items), 200


@support_center_bp.post("/plans/<checkout_id>/query")
@_require("support_agent", "support", "support_admin", "super_admin")
def query_plan(checkout_id, actor):
    rows = get_db()["jumuiya_revenue_mpesa_checkouts"]
    checkout = rows.find_one({"$or": [{"checkout_request_id": checkout_id}, {"_id": ObjectId(checkout_id) if ObjectId.is_valid(checkout_id) else None}]})
    if not checkout:
        return jsonify(success=False, message="Checkout not found."), 404
    if checkout.get("status") == "succeeded":
        return jsonify(success=True, verified=True, status="succeeded", message="Payment is already confirmed."), 200
    if not checkout.get("checkout_request_id"):
        return jsonify(success=False, code="checkout_not_submitted", message="There is no Safaricom CheckoutRequestID to query. This attempt cannot be STK-queried."), 409
    try:
        from backend.revenue.mpesa import _query_checkout, _apply_final_result, _public_checkout
        result = _query_checkout(checkout)
        verified = _apply_final_result(checkout, result)
        fresh = rows.find_one({"_id": checkout["_id"]}) or checkout
    except Exception:
        current_app.logger.exception("Support STK Query failed.")
        return jsonify(success=False, code="mpesa_query_failed", message="Safaricom status could not be checked. No plan status was changed by this request."), 503
    _audit(actor, "support.plan.stk_queried", "checkout", checkout_id, before={"status": checkout.get("status")}, after={"status": fresh.get("status"), "verified": bool(verified)})
    return jsonify(success=True, verified=bool(verified), checkout=_public_checkout(fresh)), 200


@support_center_bp.post("/plans/<checkout_id>/retry-link")
@_require("support_agent", "support", "support_admin", "super_admin")
def send_payment_retry_link(checkout_id, actor):
    data = request.get_json(silent=True) or {}
    ticket_id = str(data.get("ticket_id") or "").strip()
    reason = str(data.get("reason") or "").strip()
    if data.get("user_requested") is not True or len(reason) < 8 or not ObjectId.is_valid(ticket_id):
        return jsonify(success=False, message="A valid ticket, explicit user-request confirmation and reason are required."), 422
    rows = get_db()["jumuiya_revenue_mpesa_checkouts"]
    checkout = rows.find_one({"$or": [{"checkout_request_id": checkout_id}, {"_id": ObjectId(checkout_id) if ObjectId.is_valid(checkout_id) else None}]})
    ticket = get_db()[TICKETS].find_one({"_id": ObjectId(ticket_id)})
    if not checkout or not ticket:
        return jsonify(success=False, message="Checkout or support ticket not found."), 404
    if str(ticket.get("user_id") or "") != str(checkout.get("user_id") or ""):
        return jsonify(success=False, message="The ticket does not belong to the checkout account."), 403
    email = str(ticket.get("email") or "").strip().lower()
    if not email:
        user = get_db()["users"].find_one(_id_query(checkout.get("user_id")) or {})
        email = str((user or {}).get("email") or "").strip().lower()
    if "@" not in email:
        return jsonify(success=False, message="No verified email address is available for the customer."), 409
    token = secrets.token_urlsafe(40)
    token_row = {
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "user_id": str(checkout.get("user_id") or ""),
        "checkout_id": str(checkout.get("_id") or ""),
        "plan_code": checkout.get("plan_code"),
        "ticket_id": ticket_id,
        "requested_by": actor["id"],
        "reason": reason,
        "status": "pending",
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(minutes=30),
    }
    get_db()["support_checkout_retry_tokens"].insert_one(token_row)
    frontend = str(os.getenv("FRONTEND_URL") or os.getenv("REVELACODE_FRONTEND_URL") or "https://revelacode.co.ke").rstrip("/")
    retry_url = frontend + "/support/payment-retry?token=" + token
    sent = _send_status_notice(email, "Confirm your RevelaCode M-Pesa retry", f"You asked RevelaCode Support to retry your {checkout.get('plan_code')} plan payment. Open this secure, single-use confirmation link within 30 minutes: {retry_url}. You must sign in to your RevelaCode account and confirm the phone number before a new STK prompt is sent.")
    if not sent:
        get_db()["support_checkout_retry_tokens"].update_one({"token_hash": token_row["token_hash"]}, {"$set": {"status": "delivery_failed"}})
        return jsonify(success=False, message="The retry link could not be emailed. No new STK prompt was sent."), 502
    _audit(actor, "support.plan.retry_link_sent", "checkout", checkout_id, after={"ticket_id": ticket_id, "user_requested": True})
    return jsonify(success=True, message="A secure retry confirmation link was emailed. The customer must sign in and confirm before a new STK push is started."), 200


@support_center_bp.post("/plans/retry/validate")
def validate_payment_retry():
    actor, failure = _actor()
    if failure:
        return failure
    token = str((request.get_json(silent=True) or {}).get("token") or "").strip()
    if len(token) < 32:
        return jsonify(success=False, message="A valid retry link is required."), 400
    row = get_db()["support_checkout_retry_tokens"].find_one({"token_hash": hashlib.sha256(token.encode()).hexdigest(), "status": "pending", "expires_at": {"$gt": now_utc()}})
    if not row or str(row.get("user_id") or "") != str(actor.get("id") or ""):
        return jsonify(success=False, message="This retry link is invalid, expired or belongs to another account."), 403
    checkout = get_db()["jumuiya_revenue_mpesa_checkouts"].find_one({"_id": ObjectId(row["checkout_id"])}) if ObjectId.is_valid(str(row.get("checkout_id") or "")) else None
    if not checkout or checkout.get("status") not in {"initiation_failed", "failed", "cancelled"}:
        return jsonify(success=False, message="This checkout is not eligible for a fresh retry. Reconcile it with Support first."), 409
    return jsonify(success=True, plan={"plan_code": row.get("plan_code"), "hub": checkout.get("hub"), "amount": checkout.get("amount"), "currency": checkout.get("currency") or "KES", "ticket_id": row.get("ticket_id")}), 200


@support_center_bp.post("/plans/retry/complete")
def complete_payment_retry():
    actor, failure = _actor()
    if failure:
        return failure
    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip()
    checkout_request_id = str(data.get("checkout_request_id") or "").strip()
    if len(token) < 32 or not checkout_request_id:
        return jsonify(success=False, message="Retry token and new checkout reference are required."), 422
    db = get_db()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = db["support_checkout_retry_tokens"].find_one({"token_hash": token_hash, "status": "pending", "expires_at": {"$gt": now_utc()}})
    if not row or str(row.get("user_id") or "") != str(actor.get("id") or ""):
        return jsonify(success=False, message="Retry token is invalid or belongs to another account."), 403
    checkout = db["jumuiya_revenue_mpesa_checkouts"].find_one({"checkout_request_id": checkout_request_id, "user_id": str(actor.get("id") or ""), "plan_code": row.get("plan_code")})
    if not checkout:
        return jsonify(success=False, message="The new checkout does not match this retry request."), 409
    db["support_checkout_retry_tokens"].update_one({"_id": row["_id"], "status": "pending"}, {"$set": {"status": "used", "used_at": now_utc(), "new_checkout_request_id": checkout_request_id}})
    return jsonify(success=True), 200


@support_center_bp.post("/plans/<checkout_id>/manual-activation-request")
@_require("support_agent", "support", "support_admin", "super_admin")
def request_manual_activation(checkout_id, actor):
    data = request.get_json(silent=True) or {}
    receipt = str(data.get("receipt") or "").strip().upper()
    reason = str(data.get("reason") or "").strip()
    if not re.fullmatch(r"[A-Z0-9]{6,20}", receipt) or len(reason) < 10:
        return jsonify(success=False, message="A valid M-Pesa receipt and an explanation of at least 10 characters are required."), 422
    rows = get_db()["jumuiya_revenue_mpesa_checkouts"]
    checkout = rows.find_one({"$or": [{"checkout_request_id": checkout_id}, {"_id": ObjectId(checkout_id) if ObjectId.is_valid(checkout_id) else None}]})
    if not checkout:
        return jsonify(success=False, message="Checkout not found."), 404
    request_doc = {
        "checkout_id": str(checkout["_id"]),
        "checkout_request_id": checkout.get("checkout_request_id"),
        "user_id": str(checkout.get("user_id") or ""),
        "receipt": receipt,
        "reason": reason,
        "status": "pending_support_admin_approval",
        "requested_by": actor["id"],
        "created_at": now_utc(),
    }
    inserted = get_db()["support_plan_activation_requests"].insert_one(request_doc)
    _audit(actor, "support.plan.manual_activation_requested", "checkout", checkout_id, after={"request_id": str(inserted.inserted_id), "receipt_supplied": True})
    return jsonify(success=True, request_id=str(inserted.inserted_id), status=request_doc["status"], message="Request submitted. A Support Admin must review it; no subscription has been activated."), 201


@support_center_bp.get("/approvals")
@_require("support_admin", "super_admin")
def approvals(actor):
    rows = get_db()["support_plan_activation_requests"].find({"status": "pending_support_admin_approval"}).sort("created_at", -1).limit(100)
    return jsonify(success=True, approvals=[{
        "id": str(x["_id"]), "checkout_id": x.get("checkout_id"), "user_id": x.get("user_id"),
        "receipt": x.get("receipt"), "reason": x.get("reason"), "requested_by": x.get("requested_by"),
        "created_at": x.get("created_at").isoformat() if hasattr(x.get("created_at"), "isoformat") else x.get("created_at"),
    } for x in rows]), 200


@support_center_bp.post("/approvals/<request_id>/decision")
@_require("support_admin", "super_admin")
def decide_approval(request_id, actor):
    data = request.get_json(silent=True) or {}
    decision = str(data.get("decision") or "").strip().lower()
    reason = str(data.get("reason") or "").strip()
    if decision not in {"approve", "reject"} or len(reason) < 8:
        return jsonify(success=False, message="Choose approve or reject and provide a reason."), 422
    if not ObjectId.is_valid(request_id):
        return jsonify(success=False, message="Invalid approval ID."), 400
    db = get_db()
    item = db["support_plan_activation_requests"].find_one({"_id": ObjectId(request_id), "status": "pending_support_admin_approval"})
    if not item:
        return jsonify(success=False, message="Approval request not found or already handled."), 404
    checkout = db["jumuiya_revenue_mpesa_checkouts"].find_one({"_id": ObjectId(item["checkout_id"])})
    if decision == "approve":
        if not checkout or not checkout.get("checkout_request_id"):
            return jsonify(success=False, code="provider_reference_missing", message="A Support Admin cannot activate a plan without a provider checkout reference. Reconcile with Safaricom first."), 409
        try:
            from backend.revenue.mpesa import _query_checkout, _apply_final_result
            query_result = _query_checkout(checkout)
            _apply_final_result(checkout, query_result)
            fresh = db["jumuiya_revenue_mpesa_checkouts"].find_one({"_id": checkout["_id"]}) or checkout
        except Exception:
            return jsonify(success=False, code="provider_reconciliation_failed", message="Safaricom could not confirm this payment. The plan remains inactive."), 503
        if fresh.get("status") != "succeeded" or str(fresh.get("receipt") or "").upper() != str(item["receipt"]).upper():
            return jsonify(success=False, code="receipt_not_verified", message="Safaricom has not confirmed the submitted receipt for this checkout. No activation was made."), 409
        new_status = "approved_and_provider_verified"
    else:
        new_status = "rejected"
    db["support_plan_activation_requests"].update_one({"_id": item["_id"], "status": "pending_support_admin_approval"}, {"$set": {"status": new_status, "decision": decision, "decision_reason": reason, "decided_by": actor["id"], "decided_at": now_utc()}})
    _audit(actor, "support.plan.manual_activation_decision", "checkout", item.get("checkout_id"), before={"status": item.get("status")}, after={"status": new_status}, reason=reason)
    return jsonify(success=True, status=new_status, message="Decision recorded. Plan activation remains governed by the verified Daraja checkout result."), 200


@support_center_bp.get("/tickets")
@_require("support_agent", "support", "support_admin", "super_admin")
def list_tickets(actor):
    status = str(request.args.get("status") or "").strip()
    page = max(1, min(10000, int(request.args.get("page", "1"))))
    limit = max(1, min(100, int(request.args.get("limit", "25"))))
    query = {"status": status} if status else {}
    if "support_agent" in actor["roles"] or "support" in actor["roles"]:
        query["$or"] = [{"assigned_to_user_id": actor["id"]}, {"assigned_to": actor["id"]}, {"assigned_to": {"$in": [None, "", "support"]}}]
    rows = get_db()[TICKETS]
    total = rows.count_documents(query)
    items = []
    for row in rows.find(query).sort("updated_at", -1).skip((page - 1) * limit).limit(limit):
        items.append({"id": str(row["_id"]), "ticket_number": row.get("ticket_number") or str(row["_id"])[-8:].upper(), "subject": row.get("subject") or "", "status": "solved" if row.get("status") == "resolved" else (row.get("status") or "open"), "priority": row.get("priority") or "normal", "assignee_id": row.get("assigned_to_user_id"), "created_at": row.get("created_at").isoformat() if hasattr(row.get("created_at"), "isoformat") else row.get("created_at"), "updated_at": row.get("updated_at").isoformat() if hasattr(row.get("updated_at"), "isoformat") else row.get("updated_at")})
    return jsonify(success=True, tickets=items, pagination={"page": page, "limit": limit, "total": total}), 200


@support_center_bp.get("/tickets/<ticket_id>")
@_require("support_agent", "support", "support_admin", "super_admin")
def ticket_detail(ticket_id, actor):
    if not ObjectId.is_valid(ticket_id):
        return jsonify(success=False, message="Invalid ticket ID."), 400
    db = get_db()
    ticket = db[TICKETS].find_one({"_id": ObjectId(ticket_id)})
    if not ticket:
        return jsonify(success=False, message="Ticket not found."), 404
    if actor["role"] in SUPPORT_AGENT_ROLES and ticket.get("assigned_to_user_id") not in (None, actor["id"]) and ticket.get("assigned_to") not in (None, "", "support", actor["id"]):
        return jsonify(success=False, message="This ticket is assigned to another agent."), 403
    messages = []
    for row in db["support_ticket_messages"].find({"ticket_id": ticket_id}).sort("created_at", 1).limit(300):
        messages.append({"id": str(row.get("_id") or ""), "type": row.get("type"), "direction": row.get("direction"), "body_text": row.get("body_text"), "body_html": row.get("body_html"), "sender": _mask_email(row.get("sender")) if row.get("sender") else None, "created_at": row.get("created_at").isoformat() if hasattr(row.get("created_at"), "isoformat") else row.get("created_at")})
    return jsonify(success=True, ticket={"id": ticket_id, "ticket_number": ticket.get("ticket_number"), "subject": ticket.get("subject"), "status": "solved" if ticket.get("status") == "resolved" else ticket.get("status", "open"), "priority": ticket.get("priority", "normal"), "email": _mask_email(ticket.get("email")), "messages": messages}), 200


@support_center_bp.patch("/tickets/<ticket_id>/status")
@_require("support_agent", "support", "support_admin", "super_admin")
def update_ticket_status(ticket_id, actor):
    data = request.get_json(silent=True) or {}
    status = str(data.get("status") or "").strip().lower()
    if status not in {"open", "pending", "solved"} or not ObjectId.is_valid(ticket_id):
        return jsonify(success=False, message="Choose open, pending or solved and provide a valid ticket ID."), 422
    db = get_db()
    ticket = db[TICKETS].find_one({"_id": ObjectId(ticket_id)})
    if not ticket:
        return jsonify(success=False, message="Ticket not found."), 404
    if actor["role"] in SUPPORT_AGENT_ROLES and ticket.get("assigned_to_user_id") not in (None, actor["id"]) and ticket.get("assigned_to") not in (None, "", "support", actor["id"]):
        return jsonify(success=False, message="This ticket is assigned to another agent."), 403
    stored_status = "resolved" if status == "solved" else status
    updates = {"status": stored_status, "updated_at": now_utc()}
    if status == "solved":
        updates["resolved_at"] = now_utc()
    db[TICKETS].update_one({"_id": ticket["_id"]}, {"$set": updates})
    _audit(actor, "support.ticket.status_changed", "ticket", ticket_id, before={"status": ticket.get("status")}, after={"status": status})
    return jsonify(success=True, status=status), 200


@support_center_bp.patch("/tickets/<ticket_id>/assign")
@_require("support_admin", "super_admin")
def assign_ticket(ticket_id, actor):
    data = request.get_json(silent=True) or {}
    member_id = str(data.get("member_id") or "").strip()
    if not ObjectId.is_valid(ticket_id):
        return jsonify(success=False, message="Invalid ticket ID."), 400
    db = get_db()
    member = db["users"].find_one(_id_query(member_id) or {})
    if not member or not (_user_roles(member) & SUPPORT_AGENT_ROLES) or member.get("is_active") is False or str(member.get("status") or "active") != "active":
        return jsonify(success=False, message="Choose an active Support Agent."), 422
    ticket = db[TICKETS].find_one({"_id": ObjectId(ticket_id)})
    if not ticket:
        return jsonify(success=False, message="Ticket not found."), 404
    before = {"assigned_to_user_id": ticket.get("assigned_to_user_id") or ticket.get("assigned_to")}
    db[TICKETS].update_one({"_id": ticket["_id"]}, {"$set": {"assigned_to_user_id": member_id, "assigned_to": member_id, "assigned_to_name": member.get("full_name") or member.get("name") or "", "updated_at": now_utc()}})
    _audit(actor, "support.ticket.assigned", "ticket", ticket_id, before=before, after={"assigned_to_user_id": member_id})
    return jsonify(success=True, assigned_to_user_id=member_id), 200


@support_center_bp.post("/tickets/<ticket_id>/notes")
@_require("support_agent", "support", "support_admin", "super_admin")
def add_ticket_note(ticket_id, actor):
    text = str((request.get_json(silent=True) or {}).get("note") or "").strip()
    if len(text) < 1 or len(text) > 5000 or not ObjectId.is_valid(ticket_id):
        return jsonify(success=False, message="A note of 1–5,000 characters and valid ticket ID are required."), 422
    db = get_db()
    ticket = db[TICKETS].find_one({"_id": ObjectId(ticket_id)})
    if not ticket:
        return jsonify(success=False, message="Ticket not found."), 404
    if actor["role"] in SUPPORT_AGENT_ROLES and ticket.get("assigned_to_user_id") not in (None, actor["id"]):
        return jsonify(success=False, message="This ticket is assigned to another agent."), 403
    db["support_ticket_messages"].insert_one({"ticket_id": ticket_id, "type": "internal_note", "body_text": text, "author_id": actor["id"], "created_at": now_utc()})
    _audit(actor, "support.ticket.internal_note_added", "ticket", ticket_id, after={"note_length": len(text)})
    return jsonify(success=True), 201


@support_center_bp.post("/accessibility/issues")
@_require("support_agent", "support", "support_admin", "super_admin")
def link_accessibility_issue(actor):
    data = request.get_json(silent=True) or {}
    issue_type = str(data.get("issue_type") or "").strip().lower()
    ticket_id = str(data.get("ticket_id") or "").strip()
    details = str(data.get("details") or "").strip()
    allowed = {"cannot_login", "cannot_pay", "cannot_open_hub"}
    if issue_type not in allowed or not ObjectId.is_valid(ticket_id):
        return jsonify(success=False, message="Choose a supported accessibility issue and provide a valid ticket ID."), 422
    if len(details) > 2000:
        return jsonify(success=False, message="Issue details must be no longer than 2,000 characters."), 422
    db = get_db()
    ticket = db[TICKETS].find_one({"_id": ObjectId(ticket_id)})
    if not ticket:
        return jsonify(success=False, message="The ticket does not exist."), 404
    row = {"issue_type": issue_type, "ticket_id": ticket_id, "ticket_number": ticket.get("ticket_number"), "details": details, "reported_by": actor["id"], "created_at": now_utc()}
    inserted = db["support_accessibility_issues"].insert_one(row)
    db[TICKETS].update_one({"_id": ticket["_id"]}, {"$set": {"accessibility_issue": issue_type, "updated_at": now_utc()}})
    _audit(actor, "support.accessibility_issue.linked", "ticket", ticket_id, after={"issue_type": issue_type, "issue_id": str(inserted.inserted_id)})
    return jsonify(success=True, issue_id=str(inserted.inserted_id), ticket_id=ticket_id), 201


@support_center_bp.get("/accessibility/issues")
@_require("support_agent", "support", "support_admin", "super_admin")
def list_accessibility_issues(actor):
    rows = get_db()["support_accessibility_issues"].find({}).sort("created_at", -1).limit(100)
    return jsonify(success=True, issues=[{"id": str(x["_id"]), "issue_type": x.get("issue_type"), "ticket_id": x.get("ticket_id"), "ticket_number": x.get("ticket_number"), "details": x.get("details"), "created_at": x.get("created_at").isoformat() if hasattr(x.get("created_at"), "isoformat") else x.get("created_at")} for x in rows]), 200


@support_center_bp.get("/audit")
@_require("support_admin", "super_admin")
def list_audit(actor):
    try:
        limit = max(1, min(200, int(request.args.get("limit", "50"))))
    except ValueError:
        return jsonify(success=False, message="Limit must be a number."), 400
    rows = get_db()[AUDIT].find({}).sort("sequence", -1).limit(limit)
    return jsonify(success=True, events=[{
        "sequence": x.get("sequence"), "actor_id": x.get("actor_id"), "actor_role": x.get("actor_role"),
        "action": x.get("action"), "target_type": x.get("target_type"), "target_id": x.get("target_id"),
        "reason": x.get("reason"), "before": x.get("before"), "after": x.get("after"),
        "ip": x.get("ip"), "created_at": x.get("created_at").isoformat() if hasattr(x.get("created_at"), "isoformat") else x.get("created_at"),
        "previous_hash": x.get("previous_hash"), "event_hash": x.get("event_hash"),
    } for x in rows]), 200


@support_center_bp.post("/payroll")
@_require("support_admin")
def create_payroll(actor):
    data = request.get_json(silent=True) or {}
    member_id = str(data.get("member_id") or "").strip()
    try:
        rate = float(data.get("rate"))
        start = datetime.fromisoformat(str(data.get("period_start")).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(data.get("period_end")).replace("Z", "+00:00"))
        if rate < 0 or end <= start:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify(success=False, message="A non-negative rate and valid pay period are required."), 422
    member = get_db()["users"].find_one(_id_query(member_id) or {})
    if not member or not (_user_roles(member) & (SUPPORT_AGENT_ROLES | SUPPORT_ADMIN_ROLES)):
        return jsonify(success=False, message="A support-team member is required."), 404
    doc = {
        "member_id": member_id, "member_name": member.get("full_name") or member.get("name") or "",
        "rate": rate, "currency": "KES", "period_start": start, "period_end": end,
        "tasks_count": get_db()[TICKETS].count_documents({"status": "resolved", "resolved_at": {"$gte": start, "$lt": end}, "$or": [{"assigned_to_user_id": member_id}, {"assigned_to": member_id}]}), "bonus": float(data.get("bonus") or 0),
        "bonus_reason": str(data.get("bonus_reason") or "")[:500], "deduction": float(data.get("deduction") or 0),
        "deduction_reason": str(data.get("deduction_reason") or "")[:500], "status": "pending",
        "payment_method": str(data.get("payment_method") or "manual")[:40],
        "payment_reference": "", "created_by": actor["id"], "created_at": now_utc(),
    }
    if doc["bonus"] < 0 or doc["deduction"] < 0:
        return jsonify(success=False, message="Bonus and deduction must be zero or positive amounts."), 422
    inserted = get_db()[PAYROLL].insert_one(doc)
    _audit(actor, "support.payroll.created", "payroll", inserted.inserted_id, after={"member_id": member_id, "status": "pending", "rate": rate})
    return jsonify(success=True, id=str(inserted.inserted_id), status="pending"), 201


@support_center_bp.patch("/payroll/<record_id>")
@_require("support_admin")
def update_payroll(record_id, actor):
    data = request.get_json(silent=True) or {}
    if not ObjectId.is_valid(record_id):
        return jsonify(success=False, message="Invalid payroll record ID."), 400
    row = get_db()[PAYROLL].find_one({"_id": ObjectId(record_id)})
    if not row:
        return jsonify(success=False, message="Payroll record not found."), 404
    status = str(data.get("status") or row.get("status") or "pending")
    if status not in {"pending", "approved", "paid"}:
        return jsonify(success=False, message="Status must be pending, approved or paid."), 422
    reference = str(data.get("payment_reference") or row.get("payment_reference") or "").strip()
    if status == "paid" and not reference:
        return jsonify(success=False, message="A manual payout reference is required before marking a record paid."), 422
    changes = {"status": status, "updated_at": now_utc(), "updated_by": actor["id"]}
    if "payment_reference" in data:
        changes["payment_reference"] = reference[:120]
    if "rate" in data:
        changes["rate"] = max(0, float(data["rate"]))
    get_db()[PAYROLL].update_one({"_id": row["_id"]}, {"$set": changes})
    _audit(actor, "support.payroll.updated", "payroll", record_id, before={"status": row.get("status")}, after=changes)
    return jsonify(success=True, status=status), 200


@support_center_bp.get("/payroll")
@_require("support_admin", "super_admin")
def list_payroll(actor):
    rows = get_db()[PAYROLL].find({}).sort("period_start", -1).limit(500)
    return jsonify(success=True, records=[{
        "id": str(x["_id"]), "member_id": x.get("member_id"), "member_name": x.get("member_name"),
        "rate": x.get("rate"), "currency": x.get("currency"), "period_start": x.get("period_start").isoformat() if hasattr(x.get("period_start"), "isoformat") else x.get("period_start"),
        "period_end": x.get("period_end").isoformat() if hasattr(x.get("period_end"), "isoformat") else x.get("period_end"),
        "tasks_count": x.get("tasks_count"), "bonus": x.get("bonus"), "bonus_reason": x.get("bonus_reason"),
        "deduction": x.get("deduction"), "deduction_reason": x.get("deduction_reason"), "status": x.get("status"),
        "payment_method": x.get("payment_method"), "payment_reference": x.get("payment_reference"),
    } for x in rows]), 200


@support_center_bp.get("/payroll/export.csv")
@_require("support_admin", "super_admin")
def export_payroll_csv(actor):
    import csv
    import io
    month = str(request.args.get("month") or now_utc().strftime("%Y-%m"))
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        return jsonify(success=False, message="Month must use YYYY-MM format."), 422
    start = datetime.fromisoformat(month + "-01").replace(tzinfo=UTC)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Member", "Period start", "Period end", "Rate KES", "Tasks", "Bonus KES", "Bonus reason", "Deduction KES", "Deduction reason", "Status", "Payment method", "Payment reference"])
    for row in get_db()[PAYROLL].find({"period_start": {"$gte": start, "$lt": end}}).sort("period_start", 1):
        writer.writerow([row.get("member_name"), row.get("period_start"), row.get("period_end"), row.get("rate"), row.get("tasks_count"), row.get("bonus"), row.get("bonus_reason"), row.get("deduction"), row.get("deduction_reason"), row.get("status"), row.get("payment_method"), row.get("payment_reference")])
    response = current_app.response_class(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="revelacode-support-payroll-{month}.csv"'
    return response


@support_center_bp.get("/payroll/export.pdf")
@_require("support_admin", "super_admin")
def export_payroll_pdf(actor):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    month = str(request.args.get("month") or now_utc().strftime("%Y-%m"))
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        return jsonify(success=False, message="Month must use YYYY-MM format."), 422
    start = datetime.fromisoformat(month + "-01").replace(tzinfo=UTC)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), title=f"Support payroll {month}")
    styles = getSampleStyleSheet()
    story = [Paragraph(f"RevelaCode Support Payroll — {month}", styles["Title"]), Spacer(1, 12)]
    rows = [["Member", "Period", "Rate", "Tasks", "Bonus", "Deduction", "Status", "Reference"]]
    for row in get_db()[PAYROLL].find({"period_start": {"$gte": start, "$lt": end}}).sort("period_start", 1):
        period = f"{row.get('period_start', '')} to {row.get('period_end', '')}"
        rows.append([str(row.get("member_name") or "")[:32], period[:35], str(row.get("rate", "")), str(row.get("tasks_count", "")), str(row.get("bonus", 0)), str(row.get("deduction", 0)), str(row.get("status", "")), str(row.get("payment_reference") or "")[:24]])
    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0f172a")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#cbd5e1")), ("FONTSIZE", (0,0), (-1,-1), 8), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")])]))
    story.append(table)
    doc.build(story)
    response = current_app.response_class(buffer.getvalue(), mimetype="application/pdf")
    response.headers["Content-Disposition"] = f'attachment; filename="revelacode-support-payroll-{month}.pdf"'
    return response


@support_center_bp.get("/health")
@_require("support_agent", "support", "support_admin", "super_admin")
def system_health(actor):
    checks = {}
    try:
        get_db().command("ping")
        checks["database"] = {"status": "up"}
    except Exception:
        checks["database"] = {"status": "down"}
    checks["api"] = {"status": "up"}
    resend_key = str(os.getenv("RESEND_API_KEY") or "").strip()
    if resend_key:
        try:
            email_response = requests.get("https://api.resend.com/domains", headers={"Authorization": f"Bearer {resend_key}"}, timeout=8)
            checks["email"] = {"status": "connected" if email_response.status_code == 200 else "provider_error"}
        except requests.RequestException:
            checks["email"] = {"status": "unreachable"}
    else:
        checks["email"] = {"status": "not_configured"}
    checks["sms_otp"] = {"status": "not_configured", "provider": None}
    try:
        from backend.revenue.mpesa import _access_token
        _access_token()
        checks["daraja"] = {"status": "authenticated"}
    except Exception:
        checks["daraja"] = {"status": "authentication_failed"}
    checks["versions"] = {"web": os.getenv("WEB_APP_VERSION", "not_reported"), "android": os.getenv("ANDROID_APP_VERSION", "not_reported")}
    return jsonify(success=True, checks=checks), 200


class _SafeHTML(HTMLParser):
    ALLOWED = {"p", "br", "strong", "b", "em", "i", "ul", "ol", "li", "blockquote", "code", "pre", "a"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
    def handle_starttag(self, tag, attrs):
        if tag not in self.ALLOWED:
            return
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href.startswith(("https://", "http://")):
                self.output.append('<a href="' + html.escape(href, quote=True) + '" rel="nofollow noopener noreferrer">')
                return
        self.output.append("<" + tag + ">")
    def handle_endtag(self, tag):
        if tag in self.ALLOWED:
            self.output.append("</" + tag + ">")
    def handle_data(self, data):
        self.output.append(html.escape(data))
    def value(self):
        return "".join(self.output)


def _verify_resend_signature(raw, headers, secret):
    """Verify Resend/Svix webhook signature before accepting inbound email."""
    msg_id = headers.get("svix-id", "")
    timestamp = headers.get("svix-timestamp", "")
    signatures = headers.get("svix-signature", "")
    if not (msg_id and timestamp and signatures and secret.startswith("whsec_")):
        return False
    try:
        ts = int(timestamp)
        if abs(int(now_utc().timestamp()) - ts) > 300:
            return False
        key = base64.b64decode(secret.split("_", 1)[1])
        signed = msg_id.encode() + b"." + timestamp.encode() + b"." + raw
        expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
        return any(hmac.compare_digest(expected, item.split(",", 1)[1]) for item in signatures.split() if "," in item)
    except Exception:
        return False


@support_center_bp.post("/inbound/resend")
def inbound_resend():
    raw = request.get_data(cache=True)
    secret = str(os.getenv("RESEND_WEBHOOK_SECRET") or "").strip()
    if not _verify_resend_signature(raw, request.headers, secret):
        return jsonify(success=False, message="Invalid webhook signature."), 401
    event = request.get_json(silent=True) or {}
    if event.get("type") != "email.received":
        return jsonify(success=True, ignored=True), 200
    data = event.get("data") or {}
    message_id = str(data.get("message_id") or "").strip()
    email_id = str(data.get("email_id") or "").strip()
    if not message_id or not email_id:
        return jsonify(success=True, ignored=True), 200
    db = get_db()
    if db[INBOUND].find_one({"message_id": message_id}):
        return jsonify(success=True, duplicate=True), 200
    to_values = data.get("to") if isinstance(data.get("to"), list) else []
    if SUPPORT_EMAIL not in [str(x).lower() for x in to_values]:
        return jsonify(success=True, ignored=True), 200
    from_value = str(data.get("from") or "")
    sender_name, sender_email = parseaddr(from_value)
    if not sender_email or sender_email.lower() == SUPPORT_EMAIL:
        return jsonify(success=True, ignored=True), 200
    api_key = str(os.getenv("RESEND_API_KEY") or "").strip()
    try:
        fetched = requests.get(f"https://api.resend.com/emails/receiving/{email_id}", headers={"Authorization": f"Bearer {api_key}"}, timeout=12)
        fetched.raise_for_status()
        body = fetched.json()
    except Exception:
        current_app.logger.exception("Unable to retrieve inbound Resend message content.")
        return jsonify(success=False, message="Message content is not yet available; Resend will retry the webhook."), 503
    text_body = str(body.get("text") or "")[:50000]
    html_body = str(body.get("html") or "")
    sanitizer = _SafeHTML()
    sanitizer.feed(html_body[:100000])
    safe_html = sanitizer.value()
    inbound_headers = body.get("headers") if isinstance(body.get("headers"), dict) else {}
    in_reply_to = str(inbound_headers.get("in-reply-to") or inbound_headers.get("In-Reply-To") or "")
    reference_ids = re.findall(r"<[^>]+>", str(inbound_headers.get("references") or inbound_headers.get("References") or ""))
    thread_ids = [in_reply_to, *reference_ids]
    thread_ids = [value for value in thread_ids if value]
    existing = None
    if thread_ids:
        existing = db[TICKETS].find_one({"message_id": {"$in": thread_ids}})
        if not existing:
            prior_message = db["support_ticket_messages"].find_one({"message_id": {"$in": thread_ids}})
            if prior_message:
                existing = db[TICKETS].find_one({"_id": ObjectId(prior_message["ticket_id"])}) if ObjectId.is_valid(str(prior_message.get("ticket_id") or "")) else None
    now = now_utc()
    if existing:
        ticket_id = str(existing["_id"])
        db["support_ticket_messages"].insert_one({"ticket_id": ticket_id, "type": "email", "direction": "inbound", "message_id": message_id, "in_reply_to": in_reply_to, "sender": sender_email, "body_text": text_body, "body_html": safe_html, "created_at": now})
        db[TICKETS].update_one({"_id": existing["_id"]}, {"$set": {"status": "open", "updated_at": now}})
        ticket_number = existing.get("ticket_number") or str(existing["_id"])[-8:].upper()
    else:
        matched = db["users"].find_one({"$or": [{"email": sender_email.lower()}, {"contact": sender_email.lower()}]})
        ticket_number = "RC-" + now.strftime("%y%m") + "-" + secrets.token_hex(3).upper()
        attachments = []
        for attachment in (data.get("attachments") if isinstance(data.get("attachments"), list) else [])[:10]:
            filename = re.sub(r"[^A-Za-z0-9._-]", "_", str(attachment.get("filename") or "attachment"))[:120]
            content_type = str(attachment.get("content_type") or "application/octet-stream").lower()[:120]
            attachments.append({"filename": filename, "content_type": content_type, "status": "quarantined_pending_scan", "download_enabled": False})
        doc = {"ticket_number": ticket_number, "user_id": _user_id(matched) if matched else None, "user": (matched.get("full_name") or matched.get("name")) if matched else sender_name, "email": sender_email.lower(), "subject": str(data.get("subject") or "Support request")[:250], "description": text_body or "Email received. Open the email thread for details.", "body_html": safe_html, "message_id": message_id, "references": str(inbound_headers.get("references") or inbound_headers.get("References") or ""), "attachments": attachments, "status": "open", "priority": "normal", "assigned_to_user_id": None, "created_at": now, "updated_at": now, "source": "email"}
        inserted = db[TICKETS].insert_one(doc)
        ticket_id = str(inserted.inserted_id)
        db["support_ticket_messages"].insert_one({"ticket_id": ticket_id, "type": "email", "direction": "inbound", "message_id": message_id, "sender": sender_email, "body_text": text_body, "body_html": safe_html, "created_at": now})
    db[INBOUND].insert_one({"message_id": message_id, "email_id": email_id, "ticket_id": ticket_id, "received_at": now})
    # Acknowledge once, thread the acknowledgement to the inbound Message-ID,
    # and never answer messages originating from the support mailbox itself.
    if not existing and sender_email.lower() != SUPPORT_EMAIL:
        sender = f"RevelaCode Support <{SUPPORT_EMAIL}>"
        if api_key and sender:
            try:
                import resend
                resend.api_key = api_key
                resend.Emails.send({
                    "from": sender,
                    "to": [sender_email],
                    "reply_to": SUPPORT_EMAIL,
                    "subject": f"We received your RevelaCode request [{ticket_number}]",
                    "text": f"Thank you for contacting RevelaCode Support. Your ticket number is {ticket_number}. Our team will review your request and reply to this email.\n\nPlease keep the ticket number in the subject when replying.",
                    "headers": {"In-Reply-To": message_id, "References": message_id},
                })
                db[TICKETS].update_one({"_id": ObjectId(ticket_id)}, {"$set": {"acknowledgement_sent": True, "acknowledgement_sent_at": now_utc()}})
            except Exception:
                current_app.logger.exception("Support acknowledgement email failed.")
    return jsonify(success=True, ticket_number=ticket_number), 201


@support_center_bp.get("/mailbox")
@_require("support_agent", "support", "support_admin", "super_admin")
def mailbox(actor):
    rows = get_db()[TICKETS].find({"source": "email"}).sort("updated_at", -1).limit(200)
    return jsonify(success=True, tickets=[{"id": str(x["_id"]), "ticket_number": x.get("ticket_number"), "subject": x.get("subject"), "status": x.get("status"), "priority": x.get("priority"), "email": _mask_email(x.get("email")), "updated_at": x.get("updated_at").isoformat() if hasattr(x.get("updated_at"), "isoformat") else x.get("updated_at")} for x in rows]), 200


@support_center_bp.post("/tickets/<ticket_id>/reply")
@_require("support_agent", "support", "support_admin", "super_admin")
def reply_ticket(ticket_id, actor):
    data = request.get_json(silent=True) or {}
    message = str(data.get("message") or "").strip()
    if not ObjectId.is_valid(ticket_id) or not message or len(message) > 10000:
        return jsonify(success=False, message="A reply of 1–10,000 characters and valid ticket ID are required."), 422
    db = get_db()
    ticket = db[TICKETS].find_one({"_id": ObjectId(ticket_id)})
    if not ticket:
        return jsonify(success=False, message="Ticket not found."), 404
    if not ticket.get("email"):
        return jsonify(success=False, message="This ticket does not have a reply email address."), 409
    api_key = str(os.getenv("RESEND_API_KEY") or "").strip()
    sender = f"RevelaCode Support <{SUPPORT_EMAIL}>"
    if not api_key:
        return jsonify(success=False, message="Resend outbound email is not configured."), 503
    try:
        import resend
        resend.api_key = api_key
        headers = {}
        latest_message = db["support_ticket_messages"].find_one({"ticket_id": ticket_id, "message_id": {"$exists": True, "$ne": ""}}, sort=[("created_at", -1)])
        thread_reference = str((latest_message or {}).get("message_id") or ticket.get("message_id") or "")
        if thread_reference:
            headers["In-Reply-To"] = thread_reference
            headers["References"] = " ".join(filter(None, [str(ticket.get("references") or ""), thread_reference]))
        result = resend.Emails.send({"from": sender, "to": [ticket["email"]], "reply_to": SUPPORT_EMAIL, "subject": "Re: " + str(ticket.get("subject") or "RevelaCode Support"), "text": message, "headers": headers})
        provider_id = (result.get("id") if isinstance(result, dict) else getattr(result, "id", None)) or ""
        outbound_message_id = ""
        if provider_id:
            try:
                provider_email = requests.get(f"https://api.resend.com/emails/{provider_id}", headers={"Authorization": f"Bearer {api_key}"}, timeout=8)
                if provider_email.ok:
                    outbound_message_id = str((provider_email.json() or {}).get("message_id") or "")
            except requests.RequestException:
                current_app.logger.warning("Could not retrieve outbound support Message-ID from Resend.")
    except Exception:
        current_app.logger.exception("Support ticket reply failed.")
        return jsonify(success=False, message="The reply could not be accepted by Resend."), 502
    db["support_ticket_messages"].insert_one({"ticket_id": ticket_id, "type": "email", "direction": "outbound", "body_text": message, "message_id": outbound_message_id if "outbound_message_id" in locals() else "", "author_id": actor["id"], "provider_response": str(result)[:500], "created_at": now_utc()})
    db[TICKETS].update_one({"_id": ticket["_id"]}, {"$set": {"status": "pending", "updated_at": now_utc()}})
    _audit(actor, "support.ticket.reply_sent", "ticket", ticket_id, after={"message_length": len(message)})
    return jsonify(success=True, message="Reply accepted by the email provider."), 200
