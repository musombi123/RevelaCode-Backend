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

    if not policy_id or not content:
        return jsonify({
            "message": "policy_id and content required"
        }), 400

    db["policies"].update_one(
        {"_id": policy_id},
        {
            "$set": {
                "content": content,
                "updated_at": datetime.utcnow(),
                "updated_by": "admin"
            }
        },
        upsert=True
    )

    log_admin_action(
        db,
        action="update_policy",
        resource=policy_id,
        actor="admin"
    )

    return jsonify({
        "message": f"{policy_id} updated successfully"
    }), 200

# ----------------------------
# Scripture Management
# ----------------------------
@admin_bp.route("/admin/update-scripture", methods=["POST"])
@require_current_roles(*PLATFORM_ADMIN_ROLES, "support_admin")
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
