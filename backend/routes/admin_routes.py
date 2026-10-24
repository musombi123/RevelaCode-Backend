from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
import uuid

from bson import ObjectId
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

from backend.db import get_db
from backend.utils.current_role_auth import current_platform_actor, require_current_roles, PLATFORM_ADMIN_ROLES
from backend.utils.admin_invitation_email import send_admin_invitation_email
from backend.utils.audit_logger import log_admin_action
from backend.study.lesson_processor import LessonProcessor
from backend.study.study_service import StudyService

# ----------------------------
# Load environment variables
# ----------------------------
load_dotenv()

# ----------------------------
# Blueprint
# ----------------------------
admin_bp = Blueprint("admin", __name__)

# ----------------------------
# Dashboard
# ----------------------------
@admin_bp.route("/admin/dashboard", methods=["GET"])
@require_current_roles(*PLATFORM_ADMIN_ROLES)
def admin_dashboard():
    return jsonify({"message": "Welcome, Admin! You have full access."}), 200

# ----------------------------
# User management
# ----------------------------
@admin_bp.route("/admin/manage-users", methods=["POST"])
@require_current_roles(*PLATFORM_ADMIN_ROLES)
def manage_users():
    # Direct account creation is intentionally retired. Staff must accept a
    # single-use invitation and set their own password through /admin/invitations.
    return jsonify({
        "success": False,
        "code": "invitation_required",
        "message": "Use the secure support-team invitation flow to create staff accounts.",
    }), 410


@admin_bp.route("/admin/list-users", methods=["GET"])
@require_current_roles(*PLATFORM_ADMIN_ROLES)
def list_users():
    db = get_db()
    try:
        page = max(1, int(request.args.get("page", "1")))
        limit = min(100, max(1, int(request.args.get("limit", "50"))))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Page and limit must be integers."), 400

    search = str(request.args.get("search") or "").strip()[:100]
    role_filter = str(request.args.get("role") or "").strip().casefold()
    status_filter = str(request.args.get("status") or "").strip().casefold()
    query = {}
    if role_filter:
        query["role"] = role_filter
    if status_filter:
        query["status"] = status_filter
    if search:
        escaped = re.escape(search)
        query["$or"] = [
            {"full_name": {"$regex": escaped, "$options": "i"}},
            {"fullName": {"$regex": escaped, "$options": "i"}},
            {"name": {"$regex": escaped, "$options": "i"}},
            {"contact": {"$regex": escaped, "$options": "i"}},
            {"email": {"$regex": escaped, "$options": "i"}},
            {"username": {"$regex": escaped, "$options": "i"}},
        ]

    users_collection = db["users"]
    total = users_collection.count_documents(query)
    rows = users_collection.find(query).sort("created_at", -1).skip((page - 1) * limit).limit(limit)
    users = []
    for row in rows:
        user_id = str(row.get("_id") or row.get("id") or row.get("user_id") or "")
        if not user_id:
            continue
        users.append({
            "id": user_id,
            "full_name": row.get("full_name") or row.get("fullName") or row.get("name") or "",
            "contact": row.get("contact") or row.get("email") or row.get("phone") or "",
            "email": row.get("email") or row.get("contact") or "",
            "role": str(row.get("role") or "user"),
            "roles": row.get("roles") if isinstance(row.get("roles"), list) else [],
            "status": str(row.get("status") or "active"),
            "is_active": row.get("is_active", True),
            "verified": bool(row.get("verified", row.get("is_verified", False))),
            "created_at": row.get("created_at") or row.get("joined_at"),
            "last_login_at": row.get("last_login_at"),
        })

    return jsonify({
        "success": True,
        "users": users,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit,
        },
    }), 200


@admin_bp.route("/admin/update-policy", methods=["POST"])
@require_current_roles(*PLATFORM_ADMIN_ROLES, "support_admin")
def update_policy():
    db = get_db()
    data = request.get_json(silent=True) or {}

    policy_id = data.get("policy_id")
    content = data.get("content")
    if not isinstance(policy_id, str) or not policy_id.strip() or not isinstance(content, str) or not content.strip():
        return jsonify({"success": False, "message": "policy_id and non-empty content are required."}), 400
    if len(policy_id) > 120 or len(content) > 250000:
        return jsonify({"success": False, "message": "Policy ID or content exceeds the allowed size."}), 413

    actor = current_platform_actor()
    now = datetime.now(timezone.utc)
    db["policies"].update_one(
        {"_id": policy_id.strip()},
        {
            "$set": {
                "content": content.strip(),
                "updated_at": now,
                "updated_by": actor.get("id"),
            }
        },
        upsert=True
    )

    _log_admin_operation(
        db,
        action="update_policy",
        resource=policy_id.strip(),
        metadata={"updated_by": actor.get("id"), "revisioned_public_docs": "use /admin/legal/<type>"},
    )

    return jsonify({
        "message": f"{policy_id} updated successfully"
    }), 200

# ----------------------------
# Scripture Management
# ----------------------------
@admin_bp.route("/admin/update-scripture", methods=["POST"])
@require_current_roles(*PLATFORM_ADMIN_ROLES)
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
# =========================================================
# STUDY MATERIAL — TEXT / FILE UPLOAD
# =========================================================

@admin_bp.route(
    "/admin/study/upload",
    methods=["POST"],
)
@require_current_roles(*PLATFORM_ADMIN_ROLES, "support_admin")
def upload_study_material():

    # -----------------------------------------------------
    # FILE UPLOAD
    # -----------------------------------------------------

    if "file" in request.files:

        file = request.files.get(
            "file"
        )

        title = (
            request.form.get(
                "title"
            )
            or ""
        ).strip()

        category = (
            request.form.get(
                "category"
            )
            or ""
        ).strip()

        subcategory = (
            request.form.get(
                "subcategory"
            )
            or ""
        ).strip()

        year = (
            request.form.get(
                "year"
            )
            or ""
        ).strip()

        raw_tags = (
            request.form.get(
                "tags",
                "[]",
            )
        )

        try:
            import json

            tags = json.loads(
                raw_tags
            )

            if not isinstance(
                tags,
                list,
            ):
                tags = []

        except Exception:
            tags = []

        if not title:
            return jsonify({
                "success": False,
                "message": (
                    "Title is required."
                ),
            }), 400

        if not category:
            return jsonify({
                "success": False,
                "message": (
                    "Category is required."
                ),
            }), 400

        if not subcategory:
            return jsonify({
                "success": False,
                "message": (
                    "Subcategory is required."
                ),
            }), 400

        if not file.filename:
            return jsonify({
                "success": False,
                "message": (
                    "No file selected."
                ),
            }), 400

        result = (
            LessonProcessor
            .process_uploaded_file(
                file,
                title=title,
                category=category,
                subcategory=subcategory,
                year=year,
                tags=tags,
            )
        )

        status_code = (
            201
            if result.get("success")
            else 422
        )

        log_admin_action(
            get_db(),
            action="upload_study_document",
            resource=title,
            actor="admin",
            metadata={
                "category":
                    category,
                "subcategory":
                    subcategory,
                "filename":
                    file.filename,
            },
        )

        return jsonify(
            result
        ), status_code

    # -----------------------------------------------------
    # TEXT MATERIAL
    # -----------------------------------------------------

    data = request.get_json(
        silent=True
    ) or {}

    title = data.get(
        "title"
    )

    category = data.get(
        "category"
    )

    subcategory = data.get(
        "subcategory"
    )

    content = data.get(
        "content"
    )

    year = data.get(
        "year"
    )

    tags = data.get(
        "tags",
        [],
    )

    if not isinstance(
        tags,
        list,
    ):
        tags = []

    if not title:
        return jsonify({
            "success": False,
            "message": (
                "title is required."
            ),
        }), 400

    if not category:
        return jsonify({
            "success": False,
            "message": (
                "category is required."
            ),
        }), 400

    if not subcategory:
        return jsonify({
            "success": False,
            "message": (
                "subcategory is required."
            ),
        }), 400

    if not content or not str(
        content
    ).strip():
        return jsonify({
            "success": False,
            "message": (
                "content is required."
            ),
        }), 400

    result = (
        LessonProcessor
        .process_text_material(
            title=title,
            category=category,
            subcategory=subcategory,
            content=content,
            year=year,
            tags=tags,
        )
    )

    status_code = (
        201
        if result.get("success")
        else 409
        if result.get("material")
        else 422
    )

    log_admin_action(
        get_db(),
        action="upload_study_material",
        resource=title,
        actor="admin",
        metadata={
            "category":
                category,
            "subcategory":
                subcategory,
        },
    )

    return jsonify(
        result
    ), status_code

# ----------------------------
# Study Materials List
# ----------------------------

@admin_bp.route(
    "/admin/study/materials",
    methods=["GET"]
)
@require_current_roles(*PLATFORM_ADMIN_ROLES, "support_admin")
def admin_list_materials():

    category = request.args.get(
        "category"
    )

    materials = (
        StudyService
        .get_materials(
            category
        )
    )

    return jsonify({

        "materials":
        materials,

        "count":
        len(materials)

    }),200



# ----------------------------
# Study Material Statistics
# ----------------------------

@admin_bp.route(
    "/admin/study/stats",
    methods=["GET"]
)
@require_current_roles(*PLATFORM_ADMIN_ROLES, "support_admin")
def study_stats():

    materials = (
        StudyService
        .get_materials()
    )

    faith_count = len([

        m for m in materials

        if m.get(
            "category"
        )=="faith"
    ])

    education_count = len([

        m for m in materials

        if m.get(
            "category"
        )=="education"
    ])

    return jsonify({

        "total_materials":
        len(materials),

        "faith_materials":
        faith_count,

        "education_materials":
        education_count

    }),200


# =========================================================
# USER LIFECYCLE AND SUPPORT TEAM INVITATIONS
# =========================================================

_ADMIN_INVITATIONS_COLLECTION = "admin_invitations"
_SUPPORT_INVITATION_ROLES = {"support", "support_admin"}
_SUPERVISOR_ROLES = {"revelacode_admin", "super_admin"}


def _utc_now():
    return datetime.now(timezone.utc)


def _iso_utc(value):
    if not value:
        return None
    if isinstance(value, datetime):
        normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return normalized.isoformat()
    return str(value)


def _email_value(value):
    return str(value or "").strip().lower()


def _valid_email(value):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(value or "").strip()))


def _user_query_by_id(user_id):
    normalized = str(user_id or "").strip()
    if not normalized or len(normalized) > 128:
        return None
    if ObjectId.is_valid(normalized):
        return {"_id": ObjectId(normalized)}
    return {"$or": [{"id": normalized}, {"user_id": normalized}]}


def _safe_user(user):
    if not user:
        return None
    return {
        "id": str(user.get("_id") or user.get("id") or user.get("user_id") or ""),
        "full_name": user.get("full_name") or user.get("fullName") or user.get("name") or "",
        "contact": user.get("contact") or user.get("email") or user.get("phone") or "",
        "email": user.get("email") or user.get("contact") or "",
        "role": str(user.get("role") or "user"),
        "status": str(user.get("status") or "active"),
        "verified": bool(user.get("verified", user.get("is_verified", False))),
        "created_at": _iso_utc(user.get("created_at") or user.get("joined_at")),
    }


def _log_admin_operation(db, *, action, resource, metadata=None):
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
        # A failed secondary audit sink should not turn a successful durable
        # account-state mutation into an ambiguous response.
        from flask import current_app
        current_app.logger.exception("Admin operation succeeded but its audit event could not be written")


@admin_bp.route("/admin/users/<user_id>/status", methods=["PATCH"])
@require_current_roles(*PLATFORM_ADMIN_ROLES)
def update_user_status(user_id):
    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "").strip().lower()
    if action not in {"ban", "unban"}:
        return jsonify(success=False, message="Action must be 'ban' or 'unban'."), 400

    query = _user_query_by_id(user_id)
    if not query:
        return jsonify(success=False, message="A valid user ID is required."), 400

    db = get_db()
    users = db["users"]
    target = users.find_one(query)
    if not target:
        return jsonify(success=False, message="User account not found."), 404

    actor = current_platform_actor()
    target_id = str(target.get("_id") or target.get("id") or target.get("user_id") or "")
    if target_id == str(actor.get("id") or ""):
        return jsonify(success=False, message="You cannot ban or disable your own current administrator account."), 409

    target_roles = {
        str(value).strip().casefold()
        for value in (target.get("roles") if isinstance(target.get("roles"), list) else [])
        if value
    }
    target_role = str(target.get("role") or "user").strip().casefold()
    target_roles.add(target_role)
    actor_roles = set(actor.get("roles") or []) | {str(actor.get("role") or "").casefold()}
    is_top_level_actor = bool(actor_roles.intersection(_SUPERVISOR_ROLES))
    if target_roles.intersection(PLATFORM_ADMIN_ROLES) and not is_top_level_actor:
        return jsonify(success=False, message="Only the top-level RevelaCode administrator can change another platform administrator's account status."), 403

    now = _utc_now()
    if action == "ban":
        updates = {
            "status": "banned",
            "is_active": False,
            "banned_at": now,
            "banned_by": actor.get("id"),
            "updated_at": now.isoformat(),
        }
        audit_action = "user_account_banned"
    else:
        if str(target.get("status") or "").strip().casefold() == "deleted":
            return jsonify(success=False, message="Deleted accounts cannot be reactivated with the unban action."), 409
        updates = {
            "status": "active",
            "is_active": True,
            "unbanned_at": now,
            "unbanned_by": actor.get("id"),
            "updated_at": now.isoformat(),
        }
        audit_action = "user_account_unbanned"

    users.update_one(query, {"$set": updates})
    updated = users.find_one(query)
    _log_admin_operation(db, action=audit_action, resource=target_id, metadata={"role": target_role, "status": updates["status"]})
    return jsonify(success=True, message=("Account banned and sign-in disabled." if action == "ban" else "Account reactivated."), user=_safe_user(updated)), 200


@admin_bp.route("/admin/users/<user_id>", methods=["DELETE"])
@require_current_roles(*PLATFORM_ADMIN_ROLES)
def delete_user_account(user_id):
    """Soft-delete an account so sign-in stops while audit and business references remain."""
    query = _user_query_by_id(user_id)
    if not query:
        return jsonify(success=False, message="A valid user ID is required."), 400

    db = get_db()
    users = db["users"]
    target = users.find_one(query)
    if not target:
        return jsonify(success=False, message="User account not found."), 404

    actor = current_platform_actor()
    target_id = str(target.get("_id") or target.get("id") or target.get("user_id") or "")
    if target_id == str(actor.get("id") or ""):
        return jsonify(success=False, message="You cannot delete your own current administrator account."), 409

    target_roles = {
        str(value).strip().casefold()
        for value in (target.get("roles") if isinstance(target.get("roles"), list) else [])
        if value
    }
    target_role = str(target.get("role") or "user").strip().casefold()
    target_roles.add(target_role)
    actor_roles = set(actor.get("roles") or []) | {str(actor.get("role") or "").casefold()}
    if target_roles.intersection(PLATFORM_ADMIN_ROLES) and not actor_roles.intersection(_SUPERVISOR_ROLES):
        return jsonify(success=False, message="Only the top-level RevelaCode administrator can delete another platform administrator's account."), 403

    now = _utc_now()
    users.update_one(query, {"$set": {
        "status": "deleted",
        "is_active": False,
        "deleted_at": now,
        "deleted_by": actor.get("id"),
        "updated_at": now.isoformat(),
        # Invalidate password-based login even if a legacy login path is used.
        "password": generate_password_hash(secrets.token_urlsafe(48)),
    }})
    updated = users.find_one(query)
    _log_admin_operation(
        db,
        action="user_account_soft_deleted",
        resource=target_id,
        metadata={
            "role": target_role,
            "policy": "sign-in-disabled; audit and ecosystem references retained",
        },
    )
    return jsonify(
        success=True,
        message="Account deleted from active access. Audit and ecosystem records are retained for traceability.",
        user=_safe_user(updated),
    ), 200


@admin_bp.route("/admin/invitations", methods=["GET"])
@require_current_roles(*PLATFORM_ADMIN_ROLES)
def list_admin_invitations():
    db = get_db()
    try:
        limit = min(100, max(1, int(request.args.get("limit", "50"))))
    except (TypeError, ValueError):
        return jsonify(success=False, message="Limit must be an integer."), 400

    invitations = []
    for item in db[_ADMIN_INVITATIONS_COLLECTION].find({}).sort("created_at", -1).limit(limit):
        invitations.append({
            "id": str(item.get("_id") or ""),
            "full_name": item.get("full_name") or "",
            "contact": item.get("contact") or "",
            "role": item.get("role") or "",
            "status": item.get("status") or "unknown",
            "created_at": _iso_utc(item.get("created_at")),
            "expires_at": _iso_utc(item.get("expires_at")),
            "accepted_at": _iso_utc(item.get("accepted_at")),
            "invited_by": item.get("invited_by") or "",
        })
    return jsonify(success=True, invitations=invitations), 200


@admin_bp.route("/admin/invitations", methods=["POST"])
@require_current_roles(*PLATFORM_ADMIN_ROLES)
def create_admin_invitation():
    data = request.get_json(silent=True) or {}
    full_name = str(data.get("full_name") or "").strip()
    contact = _email_value(data.get("contact") or data.get("email"))
    role = str(data.get("role") or "").strip().casefold()

    if not full_name or len(full_name) > 120:
        return jsonify(success=False, message="Enter the invitee's full name (maximum 120 characters)."), 400
    if not _valid_email(contact):
        return jsonify(success=False, message="Enter a valid invitation email address."), 422
    if role not in _SUPPORT_INVITATION_ROLES:
        return jsonify(success=False, message="Choose Support Agent or Support Administrator."), 400

    db = get_db()
    existing_user = db["users"].find_one({"$or": [{"contact": contact}, {"email": contact}]})
    if existing_user:
        return jsonify(success=False, code="account_already_exists", message="An account already exists for this email. The invitation flow will not silently change an existing account's role."), 409

    now = _utc_now()
    expires_at = now + timedelta(days=7)
    raw_token = secrets.token_urlsafe(40)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    invitations = db[_ADMIN_INVITATIONS_COLLECTION]

    invitations.update_many(
        {"contact": contact, "status": "pending"},
        {"$set": {"status": "replaced", "updated_at": now}},
    )
    invitation = {
        "full_name": full_name,
        "contact": contact,
        "role": role,
        "token_hash": token_hash,
        "status": "pending",
        "invited_by": current_platform_actor().get("id"),
        "created_at": now,
        "expires_at": expires_at,
        "updated_at": now,
        "delivery_status": "pending",
    }
    inserted = invitations.insert_one(invitation)
    try:
        send_admin_invitation_email(
            recipient=contact,
            full_name=full_name,
            role=role,
            token=raw_token,
            expires_at=expires_at,
        )
    except Exception:
        invitations.update_one(
            {"_id": inserted.inserted_id, "status": "pending"},
            {"$set": {"status": "delivery_failed", "delivery_status": "failed", "updated_at": _utc_now()}},
        )
        _log_admin_operation(
            db,
            action="support_invitation_delivery_failed",
            resource=contact,
            metadata={"role": role},
        )
        return jsonify(success=False, code="invitation_email_failed", message="The invitation record was created but the email could not be delivered. Check RESEND_API_KEY and the configured sender before inviting again."), 502

    invitations.update_one(
        {"_id": inserted.inserted_id},
        {"$set": {"delivery_status": "accepted_by_provider", "updated_at": _utc_now()}},
    )
    _log_admin_operation(
        db,
        action="support_invitation_created",
        resource=contact,
        metadata={"role": role, "expires_at": expires_at.isoformat()},
    )
    return jsonify(
        success=True,
        message=f"Invitation sent to {contact}. It expires in 7 days.",
        invitation={
            "id": str(inserted.inserted_id),
            "full_name": full_name,
            "contact": contact,
            "role": role,
            "status": "pending",
            "expires_at": expires_at.isoformat(),
        },
    ), 201


@admin_bp.route("/admin/invitations/preview", methods=["GET"])
def preview_admin_invitation():
    raw_token = str(request.args.get("token") or "").strip()
    contact = _email_value(request.args.get("email"))
    if len(raw_token) < 32 or not _valid_email(contact):
        return jsonify(success=False, code="invalid_invitation", message="This invitation link is incomplete."), 400

    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    db = get_db()
    invitation = db[_ADMIN_INVITATIONS_COLLECTION].find_one({
        "token_hash": token_hash,
        "contact": contact,
        "status": "pending",
    })
    now = _utc_now()
    if not invitation:
        return jsonify(success=False, code="invitation_not_found", message="This invitation is invalid, expired, revoked, or already used."), 404
    expires_at = invitation.get("expires_at")
    if not isinstance(expires_at, datetime):
        return jsonify(success=False, code="invitation_invalid_expiry", message="The invitation expiry could not be verified."), 409
    if (expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at.astimezone(timezone.utc)) <= now:
        db[_ADMIN_INVITATIONS_COLLECTION].update_one({"_id": invitation["_id"], "status": "pending"}, {"$set": {"status": "expired", "updated_at": now}})
        return jsonify(success=False, code="invitation_expired", message="This invitation has expired. Ask the RevelaCode administrator to issue a new one."), 410

    return jsonify(
        success=True,
        invitation={
            "full_name": invitation.get("full_name") or "",
            "contact": contact,
            "role": invitation.get("role") or "",
            "expires_at": expires_at.isoformat(),
        },
    ), 200


@admin_bp.route("/admin/invitations/accept", methods=["POST"])
def accept_admin_invitation():
    data = request.get_json(silent=True) or {}
    raw_token = str(data.get("token") or "").strip()
    contact = _email_value(data.get("email"))
    password = str(data.get("password") or "")
    confirm_password = str(data.get("confirm_password") or "")

    if len(raw_token) < 32 or not _valid_email(contact):
        return jsonify(success=False, code="invalid_invitation", message="This invitation link is incomplete or invalid."), 400
    if len(password) < 12 or len(password) > 256:
        return jsonify(success=False, message="Set a password between 12 and 256 characters."), 422
    if password != confirm_password:
        return jsonify(success=False, message="The passwords do not match."), 422

    db = get_db()
    invitations = db[_ADMIN_INVITATIONS_COLLECTION]
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    invitation = invitations.find_one({
        "token_hash": token_hash,
        "contact": contact,
        "status": "pending",
    })
    if not invitation:
        return jsonify(success=False, code="invitation_not_found", message="This invitation is invalid, expired, revoked, or already used."), 404

    now = _utc_now()
    expires_at = invitation.get("expires_at")
    if not isinstance(expires_at, datetime) or (
        expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at.astimezone(timezone.utc)
    ) <= now:
        invitations.update_one({"_id": invitation["_id"], "status": "pending"}, {"$set": {"status": "expired", "updated_at": now}})
        return jsonify(success=False, code="invitation_expired", message="This invitation has expired. Ask the RevelaCode administrator to issue a new one."), 410

    role = str(invitation.get("role") or "").strip().casefold()
    if role not in _SUPPORT_INVITATION_ROLES:
        return jsonify(success=False, code="invalid_invitation_role", message="This invitation does not contain an approved support role."), 409

    users = db["users"]
    existing = users.find_one({"$or": [{"contact": contact}, {"email": contact}]})
    if existing:
        return jsonify(success=False, code="account_already_exists", message="An account already exists for this email. Contact the administrator to handle existing-account access."), 409

    claim = invitations.update_one(
        {"_id": invitation["_id"], "status": "pending", "expires_at": {"$gt": now}},
        {"$set": {"status": "accepting", "accepted_attempt_at": now, "updated_at": now}},
    )
    if claim.modified_count != 1:
        return jsonify(success=False, code="invitation_already_used", message="This invitation has already been used or changed."), 409

    user_data = {
        "id": str(uuid.uuid4()),
        "full_name": str(invitation.get("full_name") or "").strip(),
        "contact": contact,
        "email": contact,
        "password": generate_password_hash(password),
        "role": role,
        "roles": [role],
        "verified": True,
        "is_verified": True,
        "is_active": True,
        "status": "active",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "accepted_invitation_id": str(invitation["_id"]),
        "invited_by": invitation.get("invited_by"),
    }

    try:
        inserted_user = users.insert_one(user_data)
    except Exception:
        invitations.update_one(
            {"_id": invitation["_id"], "status": "accepting"},
            {"$set": {"status": "pending", "updated_at": _utc_now()}},
        )
        return jsonify(success=False, code="account_creation_failed", message="The account could not be created. The invitation can be retried."), 503

    invitations.update_one(
        {"_id": invitation["_id"], "status": "accepting"},
        {"$set": {
            "status": "accepted",
            "accepted_at": _utc_now(),
            "accepted_user_id": str(inserted_user.inserted_id),
            "updated_at": _utc_now(),
        }},
    )
    return jsonify(
        success=True,
        message="Your RevelaCode support account is active. Sign in with your invitation email and the password you just set.",
        role=role,
    ), 201


@admin_bp.route("/admin/invitations/<invitation_id>", methods=["DELETE"])
@require_current_roles(*PLATFORM_ADMIN_ROLES)
def revoke_admin_invitation(invitation_id):
    if not ObjectId.is_valid(str(invitation_id or "")):
        return jsonify(success=False, message="A valid invitation ID is required."), 400
    db = get_db()
    invitations = db[_ADMIN_INVITATIONS_COLLECTION]
    row = invitations.find_one({"_id": ObjectId(invitation_id)})
    if not row:
        return jsonify(success=False, message="Invitation not found."), 404
    if row.get("status") != "pending":
        return jsonify(success=False, message="Only a pending invitation can be revoked."), 409

    now = _utc_now()
    invitations.update_one(
        {"_id": row["_id"], "status": "pending"},
        {"$set": {"status": "revoked", "revoked_at": now, "revoked_by": current_platform_actor().get("id"), "updated_at": now}},
    )
    _log_admin_operation(db, action="support_invitation_revoked", resource=row.get("contact"), metadata={"role": row.get("role")})
    return jsonify(success=True, message="Invitation revoked."), 200


# =========================================================
# PUBLIC LEGAL DOCUMENTS AND ADMIN REVISION MANAGEMENT
# =========================================================

LEGAL_DOCUMENT_TYPES = {
    "privacy": "privacy",
    "privacy-policy": "privacy",
    "privacy_policy": "privacy",
    "terms": "terms",
    "terms-of-service": "terms",
    "terms_of_service": "terms",
    "cookies": "cookies",
    "cookie-policy": "cookies",
    "community-guidelines": "community_guidelines",
    "community_guidelines": "community_guidelines",
    "support-policy": "support_policy",
    "support_policy": "support_policy",
}


@admin_bp.route("/legal/<doc_type>", methods=["GET"])
def get_public_legal_document(doc_type):
    normalized = LEGAL_DOCUMENT_TYPES.get(str(doc_type or "").strip().lower())
    if not normalized:
        return jsonify(success=False, message="Unknown legal document type."), 404

    rows = get_db()["legaldocs"]
    document = rows.find_one({"type": normalized}, sort=[("created_at", -1)])
    if not document:
        return jsonify(success=False, message="This document has not been published yet.", type=normalized), 404
    return jsonify(
        success=True,
        type=normalized,
        version=str(document.get("version") or ""),
        content=str(document.get("content") or ""),
        updated_at=_iso_utc(document.get("updated_at") or document.get("created_at")),
        lastUpdated=_iso_utc(document.get("updated_at") or document.get("created_at")),
    ), 200


@admin_bp.route("/admin/legal/<doc_type>", methods=["PUT"])
@require_current_roles(*PLATFORM_ADMIN_ROLES, "support_admin")
def update_legal_document(doc_type):
    normalized = LEGAL_DOCUMENT_TYPES.get(str(doc_type or "").strip().lower())
    if not normalized:
        return jsonify(success=False, message="Unknown legal document type."), 400
    data = request.get_json(silent=True) or {}
    content = data.get("content")
    requested_version = str(data.get("version") or "").strip()[:40]
    if not isinstance(content, str) or not content.strip():
        return jsonify(success=False, message="Document content is required."), 400
    if len(content) > 250000:
        return jsonify(success=False, message="Document content exceeds the 250,000-character limit."), 413

    db = get_db()
    rows = db["legaldocs"]
    previous = rows.find_one({"type": normalized}, sort=[("created_at", -1)])
    if not requested_version:
        if previous:
            try:
                requested_version = f"{float(str(previous.get('version') or '1.0')) + 0.1:.1f}"
            except (TypeError, ValueError):
                requested_version = "1.1"
        else:
            requested_version = "1.0"

    now = _utc_now()
    actor = current_platform_actor()
    result = rows.insert_one({
        "type": normalized,
        "version": requested_version,
        "content": content.strip(),
        "created_at": now,
        "updated_at": now,
        "updated_by": actor.get("id"),
        "published": True,
    })
    _log_admin_operation(
        db,
        action="legal_document_published",
        resource=normalized,
        metadata={"version": requested_version, "revision_id": str(result.inserted_id)},
    )
    return jsonify(
        success=True,
        message=f"{normalized.replace('_', ' ').title()} was published as version {requested_version}.",
        type=normalized,
        version=requested_version,
    ), 201

