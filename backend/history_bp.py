# backend/history_bp.py

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request, g

from bson import ObjectId
from bson.errors import InvalidId
from flask_cors import cross_origin

from backend.db import db


# =========================================================
# BLUEPRINT
# =========================================================

history_bp = Blueprint(
    "history_bp",
    __name__,
)


# =========================================================
# DATABASE
# =========================================================

users_col = db.get_collection(
    "users"
)


# =========================================================
# CORS
# =========================================================

HISTORY_CORS_ORIGINS = [
    "https://revelacode-frontend.onrender.com",
    "https://www.revelacode-frontend.onrender.com",
    "https://localhost",
    "http://localhost",
]


# =========================================================
# TIME
# =========================================================

def utc_now():
    return datetime.utcnow().isoformat()


# =========================================================
# SANITIZATION
# =========================================================

def sanitize_history_entry(entry):
    """
    Safely normalize one history entry.

    Older history records may contain:
        - dictionaries
        - strings
        - Mongo ObjectIds
        - unexpected values

    The API must never crash while serializing history.
    """

    # -----------------------------------------------------
    # Dictionary entry
    # -----------------------------------------------------

    if isinstance(
        entry,
        dict,
    ):

        result = dict(
            entry
        )

        if "_id" in result:
            result["_id"] = str(
                result["_id"]
            )

        return result

    # -----------------------------------------------------
    # Legacy string
    # -----------------------------------------------------

    if isinstance(
        entry,
        str,
    ):

        return {
            "id": None,
            "timestamp": None,
            "type": "legacy",
            "input": entry,
            "output": "",
            "fileName": None,
            "extra": None,
        }

    # -----------------------------------------------------
    # Unsupported value
    # -----------------------------------------------------

    return {
        "id": None,
        "timestamp": None,
        "type": "legacy",
        "input": str(
            entry
        ),
        "output": "",
        "fileName": None,
        "extra": None,
    }


def sanitize_user_doc(
    doc: dict,
) -> dict:
    """
    Convert MongoDB values into safe JSON-compatible data.
    """

    if not doc:
        return doc

    doc_copy = dict(
        doc
    )

    # -----------------------------------------------------
    # USER OBJECT ID
    # -----------------------------------------------------

    if "_id" in doc_copy:

        doc_copy["_id"] = str(
            doc_copy["_id"]
        )

    # -----------------------------------------------------
    # HISTORY
    # -----------------------------------------------------

    history = doc_copy.get(
        "history",
        [],
    )

    if not isinstance(
        history,
        list,
    ):
        history = []

    doc_copy["history"] = [
        sanitize_history_entry(
            entry
        )
        for entry in history
    ]

    return doc_copy


# =========================================================
# AUTHENTICATION
# =========================================================

def get_authorized_contact():
    """
    The existing RevelaCode history contract uses:

        Authorization: <contact>

    IMPORTANT:
        This is intentionally NOT interpreted as:

        Authorization: Bearer <token>

    because the current frontend history client sends the
    authenticated user's contact directly.
    """

    contact = request.headers.get(
        "Authorization"
    )

    if contact is None:
        return ""

    return contact.strip()


# =========================================================
# FIND USER
# =========================================================

def find_user_by_contact(
    contact,
):
    if not contact:
        return None

    return users_col.find_one(
        {
            "contact": contact
        }
    )


def find_user_by_id(user_id):
    """Resolve a known authenticated user ID against the users collection."""
    if user_id is None:
        return None

    value = str(user_id).strip()
    if not value:
        return None

    try:
        object_id = ObjectId(value)
    except (InvalidId, TypeError, ValueError):
        object_id = None

    if object_id is not None:
        user = users_col.find_one({"_id": object_id})
        if user:
            return user

    user = users_col.find_one({"user_id": value})
    if user:
        return user

    return users_col.find_one({"id": value})


def history_update_filter(user, identity=None):
    """Build the update selector from the actual matched user document."""
    identity = identity if isinstance(identity, dict) else {}
    if isinstance(user, dict) and user.get("_id") is not None:
        return {"_id": user["_id"]}

    for key in ("user_id", "id", "contact", "email"):
        value = (user or {}).get(key) or identity.get(key)
        if value:
            return {key: value}

    raise ValueError("Cannot safely identify the history owner document.")


# =========================================================
# COMMON HANDLER
# =========================================================

def handle_history_request():
    """Handle history using the verified Jumuiya identity for Bearer JWTs.

    The old raw-contact authorization style remains supported only for
    legacy clients that do not send a Bearer token.
    """
    authorization = request.headers.get("Authorization", "").strip()
    identity = getattr(g, "jumuiya_user", None)

    if isinstance(identity, dict) and identity.get("id"):
        user = find_user_by_id(identity.get("id"))
        if not user:
            return jsonify({
                "success": False,
                "history": [],
                "message": "Authenticated user record was not found.",
            }), 404
        user_filter = history_update_filter(user, identity)
    else:
        # Never reinterpret a failed/expired Bearer JWT as a legacy contact.
        if authorization.lower().startswith("bearer "):
            return jsonify({
                "success": False,
                "history": [],
                "message": "Unauthorized",
            }), 401

        contact = authorization
        if not contact:
            return jsonify({
                "success": False,
                "history": [],
                "message": "Unauthorized",
            }), 401

        user = find_user_by_contact(contact)
        if not user:
            return jsonify({
                "success": False,
                "history": [],
                "message": "User not found",
            }), 404
        user_filter = history_update_filter(user, {"contact": contact})

    # Capture the selector before sanitizing `_id` for JSON serialization.
    user = sanitize_user_doc(user)
    current_history = user.get("history", [])
    if not isinstance(current_history, list):
        current_history = []

    if request.method == "GET":
        return jsonify({
            "success": True,
            "history": current_history,
        }), 200

    if request.method == "POST":
        entry = request.get_json(silent=True)
        if not isinstance(entry, dict) or not entry:
            return jsonify({
                "success": False,
                "history": current_history,
                "message": "No history entry provided",
            }), 400

        timestamp = (
            request.headers.get("X-Timestamp")
            or entry.get("timestamp")
            or utc_now()
        )
        new_entry = {**entry, "timestamp": timestamp}
        history_list = list(current_history)
        history_list.append(new_entry)

        users_col.update_one(
            user_filter,
            {"$set": {"history": history_list}},
        )
        return jsonify({
            "success": True,
            "history": history_list,
        }), 201

    if request.method == "DELETE":
        users_col.update_one(
            user_filter,
            {"$set": {"history": []}},
        )
        return jsonify({
            "success": True,
            "history": [],
        }), 200

    return jsonify({
        "success": False,
        "history": current_history,
        "message": "Method not allowed",
    }), 405



# =========================================================
# CANONICAL API ROUTE
# =========================================================
#
# Frontend contract:
#
#     GET /api/user/history
#
#     Authorization: <contact>
#
# This is now the primary history endpoint.
# =========================================================

@history_bp.route(
    "/api/user/history",
    methods=[
        "GET",
        "POST",
        "DELETE",
        "OPTIONS",
    ],
    endpoint="history_api",
)
@cross_origin(
    origins=HISTORY_CORS_ORIGINS,
    supports_credentials=True,
    methods=[
        "GET",
        "POST",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-ADMIN-KEY",
        "X-Timestamp",
    ],
)
def history_api():
    return handle_history_request()


# =========================================================
# LEGACY COMPATIBILITY ROUTE
# =========================================================
#
# Existing frontend code still uses:
#
#     POST   /history
#     DELETE /history
#
# Keep this route temporarily so we do not break existing
# history writes while making /api/user/history canonical.
# =========================================================

@history_bp.route(
    "/history",
    methods=[
        "GET",
        "POST",
        "DELETE",
        "OPTIONS",
    ],
    endpoint="history_legacy",
)
@cross_origin(
    origins=HISTORY_CORS_ORIGINS,
    supports_credentials=True,
    methods=[
        "GET",
        "POST",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-ADMIN-KEY",
        "X-Timestamp",
    ],
)
def history_legacy():
    return handle_history_request()
