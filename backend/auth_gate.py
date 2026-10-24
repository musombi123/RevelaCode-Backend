# backend/user_profile/auth_gate.py

from __future__ import annotations

import hmac
import json
import os
import random
import re
import threading

import jwt
from bson import ObjectId
from bson.errors import InvalidId

from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from flask import Blueprint, jsonify, request
from backend.email_service import send_verification_email
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()

ADMIN_API_KEY = os.getenv(
    "ADMIN_API_KEY",
    "",
)

SUPPORT_API_KEY = os.getenv(
    "SUPPORT_API_KEY",
    "",
)

JWT_SECRET = os.getenv(
    "JWT_SECRET"
)

JWT_ALGORITHM = "HS256"

# Match the role allowlist used by existing platform-administration routes.
PLATFORM_ADMIN_ROLES = frozenset({
    "admin",
    "platform_admin",
    "super_admin",
    "revelacode_admin",
})

JWT_EXPIRES_HOURS = int(
    os.getenv(
        "JWT_EXPIRES_HOURS",
        "24",
    )
)


# =========================================================
# VALIDATE JWT CONFIGURATION
# =========================================================

if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET is not configured."
    )


# =========================================================
# MONGO SETUP
# =========================================================

try:

    from backend.db import db

    MONGO_AVAILABLE = True

    users_col = db.get_collection(
        "users"
    )

except Exception:

    MONGO_AVAILABLE = False

    users_col = None


# =========================================================
# DATA FOLDER / FILE SETUP
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data",
)

os.makedirs(
    DATA_DIR,
    exist_ok=True,
)

USERS_FILE = os.path.join(
    DATA_DIR,
    "users.json",
)

file_lock = threading.Lock()


# =========================================================
# FILE HELPERS
# =========================================================

def atomic_write(
    filepath,
    data,
):
    import shutil
    import tempfile

    os.makedirs(
        os.path.dirname(filepath),
        exist_ok=True,
    )

    with tempfile.NamedTemporaryFile(
        "w",
        dir=os.path.dirname(filepath),
        delete=False,
        encoding="utf-8",
    ) as temp_file:

        json.dump(
            data,
            temp_file,
            indent=2,
        )

        temp_name = temp_file.name

    shutil.move(
        temp_name,
        filepath,
    )


def load_users_file():
    if not os.path.exists(
        USERS_FILE
    ):
        return {}

    try:

        with open(
            USERS_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(file)

    except (
        json.JSONDecodeError,
        OSError,
    ):

        return {}


def save_users_file(
    users: dict,
):
    with file_lock:

        atomic_write(
            USERS_FILE,
            users,
        )


def get_user_from_file(
    contact,
):
    users = load_users_file()

    return users.get(
        contact
    )


# =========================================================
# BLUEPRINT
# =========================================================

auth_bp = Blueprint(
    "auth_bp",
    __name__,
)

# Shared with RevelaAI's existing internal AI Gateway. Keep this
# credential server-side in both services; never expose it to clients.
REVELAAI_SERVICE_KEY = os.getenv(
    "REVELAAI_SERVICE_KEY",
    "",
).strip()


@auth_bp.route(
    "/api/auth/verify/<user_id>",
    methods=["GET"],
)
def verify_user_for_revelaai(user_id: str):
    """Verify that a RevelaCode user exists without exposing user data.

    This service-to-service endpoint intentionally returns only the
    requested ID and existence status. It never returns contact details,
    profile fields, or authentication data.
    """
    configured_key = REVELAAI_SERVICE_KEY
    presented_key = request.headers.get(
        "X-REVELAAI-SERVICE-KEY",
        "",
    ).strip()

    if not configured_key:
        return jsonify(
            success=False,
            code="service_verification_not_configured",
        ), 503

    if not presented_key or not hmac.compare_digest(
        presented_key,
        configured_key,
    ):
        return jsonify(
            success=False,
            code="service_verification_forbidden",
        ), 403

    normalized_id = str(user_id or "").strip()
    if not normalized_id or len(normalized_id) > 128:
        return jsonify(
            exists=False,
            userId=normalized_id,
        ), 404

    user = None
    if MONGO_AVAILABLE and users_col is not None:
        try:
            if ObjectId.is_valid(normalized_id):
                user = users_col.find_one(
                    {"_id": ObjectId(normalized_id)},
                    {"_id": 1, "id": 1, "user_id": 1},
                )
            else:
                user = users_col.find_one(
                    {"$or": [
                        {"id": normalized_id},
                        {"user_id": normalized_id},
                    ]},
                    {"_id": 1, "id": 1, "user_id": 1},
                )
        except Exception:
            # Do not fall back to a potentially stale local mirror when
            # Mongo is configured but temporarily unavailable.
            return jsonify(
                success=False,
                code="user_verification_unavailable",
            ), 503
    else:
        try:
            for record in load_users_file().values():
                if not isinstance(record, dict):
                    continue
                record_id = str(
                    record.get("_id")
                    or record.get("id")
                    or record.get("user_id")
                    or ""
                )
                if record_id == normalized_id:
                    user = record
                    break
        except Exception:
            return jsonify(
                success=False,
                code="user_verification_unavailable",
            ), 503

    if not user:
        return jsonify(
            exists=False,
            userId=normalized_id,
        ), 404

    actual_id = str(
        user.get("_id")
        or user.get("id")
        or user.get("user_id")
        or normalized_id
    )
    return jsonify(
        exists=(actual_id == normalized_id),
        userId=actual_id,
    ), 200


def _auth_profile_verified(value) -> bool:
    """Interpret database verification flags without truthy-string mistakes."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value or "").strip().casefold() in {"true", "1", "yes", "verified"}


@auth_bp.route(
    "/api/auth/me",
    methods=["GET"],
)
def authenticated_user_me():
    """Return the current user's canonical ID from the existing RevelaCode JWT."""
    authorization = request.headers.get("Authorization", "").strip()
    if not authorization.startswith("Bearer "):
        return jsonify(success=False, code="authentication_required"), 401

    token = authorization[7:].strip()
    if not token:
        return jsonify(success=False, code="authentication_required"), 401

    try:
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        return jsonify(success=False, code="token_expired"), 401
    except jwt.InvalidTokenError:
        return jsonify(success=False, code="invalid_token"), 401

    user_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
    if not user_id or len(user_id) > 128:
        return jsonify(success=False, code="invalid_user_identity"), 401

    profile_projection = {
        "_id": 1,
        "id": 1,
        "user_id": 1,
        "full_name": 1,
        "fullName": 1,
        "name": 1,
        "username": 1,
        "contact": 1,
        "email": 1,
        "phone": 1,
        "role": 1,
        "roles": 1,
        "verified": 1,
        "is_verified": 1,
        "status": 1,
        "created_at": 1,
        "joined_at": 1,
        "hub_usage": 1,
        "current_hubs": 1,
        "hubs": 1,
        "enabled_hubs": 1,
    }
    user = None
    try:
        if MONGO_AVAILABLE and users_col is not None:
            if ObjectId.is_valid(user_id):
                user = users_col.find_one(
                    {"_id": ObjectId(user_id)},
                    profile_projection,
                )
            if user is None:
                user = users_col.find_one(
                    {"$or": [{"id": user_id}, {"user_id": user_id}]},
                    profile_projection,
                )
        else:
            for record in load_users_file().values():
                if not isinstance(record, dict):
                    continue
                candidate = str(
                    record.get("_id") or record.get("id") or record.get("user_id") or ""
                )
                if candidate == user_id:
                    user = record
                    break
    except Exception:
        return jsonify(success=False, code="user_lookup_unavailable"), 503

    if not user:
        return jsonify(success=False, code="user_not_found"), 404

    account_ids = {
        str(value).strip()
        for value in (user.get("_id"), user.get("id"), user.get("user_id"))
        if value is not None and str(value).strip()
    }
    if user_id not in account_ids:
        return jsonify(success=False, code="user_identity_mismatch"), 403
    actual_id = str(user.get("_id") or user.get("id") or user.get("user_id") or user_id)

    account_status = str(user.get("status") or "active").strip().casefold()
    if user.get("is_active") is False or account_status in {"inactive", "disabled", "suspended", "blocked", "banned", "deleted", "revoked"}:
        return jsonify(success=False, authenticated=False, code="account_inactive", message="This account is not active."), 403

    raw_roles = user.get("roles")
    if isinstance(raw_roles, str):
        raw_roles = [raw_roles]
    if not isinstance(raw_roles, list):
        raw_roles = []
    canonical_roles = list(dict.fromkeys(
        [str(role).strip() for role in raw_roles if str(role).strip()]
        + ([str(user.get("role")).strip()] if user.get("role") else [])
    )) or ["user"]
    canonical_role = str(user.get("role") or canonical_roles[0]).strip() or "user"
    verified_value = user.get("verified")
    if verified_value is None:
        verified_value = user.get("is_verified", False)
    verified = _auth_profile_verified(verified_value)
    safe_user = {
        "id": actual_id,
        "user_id": actual_id,
        "full_name": user.get("full_name") or user.get("fullName") or user.get("name") or user.get("username") or "",
        "name": user.get("name") or user.get("full_name") or user.get("fullName") or user.get("username") or "",
        "username": user.get("username") or "",
        "contact": user.get("contact") or user.get("email") or user.get("phone") or "",
        "email": user.get("email") or "",
        "phone": user.get("phone") or "",
        "role": canonical_role,
        "roles": canonical_roles,
        "verified": verified,
        "account_status": user.get("status") or ("active" if verified else "unverified"),
        "created_at": user.get("created_at") or user.get("joined_at"),
        "hub_usage": user.get("hub_usage") or user.get("current_hubs") or user.get("hubs") or user.get("enabled_hubs") or [],
    }

    return jsonify(
        success=True,
        authenticated=True,
        userId=actual_id,
        id=actual_id,
        user=safe_user,
        role=canonical_role,
        roles=canonical_roles,
    ), 200



@auth_bp.route(
    "/api/auth/verify-admin",
    methods=["GET"],
)
def verify_admin_for_revelaai():
    """Verify the signed-in user's CURRENT database role for privileged AI routes.

    This endpoint does not trust browser role flags or role claims from a JWT.
    The JWT establishes identity; the current user record establishes role.
    """
    authorization = (request.headers.get("Authorization") or "").strip()
    if not authorization.startswith("Bearer "):
        return jsonify(success=False, authorized=False, code="authentication_required"), 401

    token = authorization[7:].strip()
    if not token:
        return jsonify(success=False, authorized=False, code="authentication_required"), 401

    try:
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        return jsonify(success=False, authorized=False, code="token_expired"), 401
    except jwt.InvalidTokenError:
        return jsonify(success=False, authorized=False, code="invalid_token"), 401

    user_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
    if not user_id or len(user_id) > 128:
        return jsonify(success=False, authorized=False, code="invalid_user_identity"), 401

    user = None
    try:
        if MONGO_AVAILABLE and users_col is not None:
            projection = {
                "_id": 1,
                "id": 1,
                "user_id": 1,
                "role": 1,
            }
            if ObjectId.is_valid(user_id):
                user = users_col.find_one({"_id": ObjectId(user_id)}, projection)
            if user is None:
                user = users_col.find_one(
                    {"$or": [{"id": user_id}, {"user_id": user_id}]},
                    projection,
                )
        else:
            for record in load_users_file().values():
                if not isinstance(record, dict):
                    continue
                candidate = str(
                    record.get("_id") or record.get("id") or record.get("user_id") or ""
                )
                if candidate == user_id:
                    user = record
                    break
    except Exception:
        return jsonify(success=False, authorized=False, code="role_lookup_unavailable"), 503

    if not user:
        return jsonify(success=False, authorized=False, code="user_not_found"), 404

    canonical_id = str(user.get("_id") or user.get("id") or user.get("user_id") or "")
    if not canonical_id or canonical_id != user_id:
        return jsonify(success=False, authorized=False, code="user_identity_mismatch"), 403

    # Match the singular role field used by the existing login/redirect flow.
    # Role changes take effect immediately; stale JWT role claims are ignored.
    role = str(user.get("role") or "user").strip().lower()
    if role not in PLATFORM_ADMIN_ROLES:
        return jsonify(
            success=False,
            authenticated=True,
            authorized=False,
            code="admin_required",
            userId=canonical_id,
            role=role,
        ), 403

    return jsonify(
        success=True,
        authenticated=True,
        authorized=True,
        userId=canonical_id,
        role=role,
    ), 200


# =========================================================
# TIME / VERIFICATION
# =========================================================

def now():
    """
    Return timezone-aware UTC datetime.
    """

    return datetime.now(
        timezone.utc
    )


def expires_in(
    minutes=10,
):
    return (
        now()
        + timedelta(
            minutes=minutes
        )
    )


def is_expired(
    value,
):
    """
    Safely check whether an ISO datetime has expired.
    """

    try:

        parsed = datetime.fromisoformat(
            value
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return now() > parsed

    except (
        TypeError,
        ValueError,
    ):

        return True


def generate_code():
    return str(
        random.randint(
            100000,
            999999,
        )
    )


# =========================================================
# MONGO SERIALIZATION
# =========================================================

def sanitize_mongo_doc(
    doc: dict,
) -> dict:

    if not doc:
        return doc

    doc_copy = doc.copy()

    if "_id" in doc_copy:

        doc_copy["_id"] = str(
            doc_copy["_id"]
        )

    return doc_copy


# =========================================================
# FILE USER STORAGE
# =========================================================

def save_user_to_file(
    user_data,
):
    users = load_users_file()

    users[
        user_data["contact"]
    ] = sanitize_mongo_doc(
        user_data
    )

    save_users_file(
        users
    )


# =========================================================
# JWT
# =========================================================

def create_access_token(
    user,
):
    """
    Create the access token used by the existing
    RevelaCode frontend and Jumuiya.

    The JWT contains identity information only.
    Authentication remains backed by the existing
    RevelaCode users collection.
    """

    user_id = (
        user.get("_id")
        or user.get("id")
        or user.get("user_id")
    )

    if user_id is None:
        raise RuntimeError(
            "Cannot create JWT: user has no ID."
        )

    issued_at = now()

    expires_at = (
        issued_at
        + timedelta(
            hours=JWT_EXPIRES_HOURS
        )
    )

    roles = user.get(
        "roles"
    )

    if isinstance(
        roles,
        str,
    ):
        roles = [roles]

    if not isinstance(
        roles,
        list,
    ):
        roles = [
            user.get(
                "role",
                "user",
            )
        ]

    roles = [
        str(role)
        for role in roles
        if role
    ]

    if not roles:
        roles = ["user"]

    payload = {
        "sub": str(user_id),
        "user_id": str(user_id),

        "contact": user.get(
            "contact",
            "",
        ),

        "full_name": user.get(
            "full_name",
            "",
        ),

        "role": user.get(
            "role",
            "user",
        ),

        "roles": roles,

        "verified": bool(
            user.get(
                "verified",
                False,
            )
        ),

        "iat": issued_at,

        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


# =========================================================
# REGISTRATION
# =========================================================

@auth_bp.route(
    "/api/register",
    methods=["POST"],
)
def register():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    full_name = data.get(
        "full_name"
    )

    contact = data.get(
        "contact"
    )

    password = data.get(
        "password"
    )

    confirm = data.get(
        "confirm_password"
    )

    if not all([
        full_name,
        contact,
        password,
        confirm,
    ]):

        return jsonify(
            success=False,
            message="All fields required",
        ), 400

    if password != confirm:

        return jsonify(
            success=False,
            message="Passwords do not match",
        ), 400

    # -----------------------------------------------------
    # EXISTING ACCOUNT CHECK
    # -----------------------------------------------------

    if (
        MONGO_AVAILABLE
        and users_col.find_one(
            {
                "contact": contact
            }
        )
    ):

        return jsonify(
            success=False,
            message="Account already exists",
        ), 400

    if get_user_from_file(
        contact
    ):

        return jsonify(
            success=False,
            message="Account already exists",
        ), 400

    # -----------------------------------------------------
    # USER DOCUMENT
    # -----------------------------------------------------

    user_data = {
        "full_name": full_name.strip(),

        "contact": contact.strip(),

        "password": generate_password_hash(
            password
        ),

        "role": "user",

        "roles": [
            "user"
        ],

        "verified": False,

        "created_at": now().isoformat(),

        "verification": {},

        "history": [],

        "settings": {
            "theme": "light",
            "linked_accounts": [],
        },

        "domains": [],
    }

    # -----------------------------------------------------
    # MONGO
    # -----------------------------------------------------

    if MONGO_AVAILABLE:

        result = users_col.insert_one(
            user_data
        )

        user_data["_id"] = (
            result.inserted_id
        )

    # -----------------------------------------------------
    # FILE FALLBACK / MIRROR
    # -----------------------------------------------------

    save_user_to_file(
        user_data
    )

    return jsonify(
        success=True,
        message="Account created",
    ), 201


# =========================================================
# SUPPORT: RESEND ACCOUNT VERIFICATION
# =========================================================

@auth_bp.route(
    "/api/support/resend-verification",
    methods=["POST"],
)
def support_resend_verification():
    """Send a fresh activation code when support assists an unverified user."""
    authorization = (request.headers.get("Authorization") or "").strip()
    if not authorization.startswith("Bearer "):
        return jsonify(success=False, code="authentication_required"), 401

    try:
        claims = jwt.decode(
            authorization[7:].strip(),
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
    except jwt.InvalidTokenError:
        return jsonify(success=False, code="invalid_token"), 401

    actor_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
    if not actor_id or len(actor_id) > 128:
        return jsonify(success=False, code="invalid_user_identity"), 401

    # Check the current stored role. Do not trust role claims supplied by the client/JWT.
    try:
        actor = None
        if MONGO_AVAILABLE and users_col is not None:
            projection = {"_id": 1, "id": 1, "user_id": 1, "role": 1, "roles": 1}
            if ObjectId.is_valid(actor_id):
                actor = users_col.find_one({"_id": ObjectId(actor_id)}, projection)
            if actor is None:
                actor = users_col.find_one(
                    {"$or": [{"id": actor_id}, {"user_id": actor_id}]},
                    projection,
                )
        else:
            for record in load_users_file().values():
                if not isinstance(record, dict):
                    continue
                if str(record.get("_id") or record.get("id") or record.get("user_id") or "") == actor_id:
                    actor = record
                    break
    except Exception:
        return jsonify(success=False, code="support_authorization_unavailable"), 503

    if not actor or str(actor.get("_id") or actor.get("id") or actor.get("user_id") or "") != actor_id:
        return jsonify(success=False, code="support_authorization_unavailable"), 403

    roles = actor.get("roles") if isinstance(actor.get("roles"), list) else []
    roles = {str(role).strip().casefold() for role in roles if role}
    role = str(actor.get("role") or "").strip().casefold()
    allowed_roles = {"support", "admin", "platform_admin", "super_admin", "revelacode_admin"}
    if role not in allowed_roles and not roles.intersection(allowed_roles):
        return jsonify(success=False, code="support_required"), 403

    data = request.get_json(silent=True) or {}
    contact = str(data.get("contact") or "").strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", contact):
        return jsonify(success=False, message="Enter the user's registered email address."), 422

    try:
        user = (
            users_col.find_one({"contact": contact})
            if MONGO_AVAILABLE and users_col is not None
            else get_user_from_file(contact)
        )
    except Exception:
        return jsonify(success=False, code="user_lookup_unavailable"), 503

    if not user:
        return jsonify(success=False, message="No account was found for that email address."), 404
    if _auth_profile_verified(user.get("verified", user.get("is_verified", False))):
        return jsonify(success=False, message="This account is already verified."), 409

    code = generate_code()
    verification_data = {"code": code, "expires": expires_in(10).isoformat()}
    try:
        if MONGO_AVAILABLE and users_col is not None:
            users_col.update_one({"contact": contact}, {"$set": {"verification": verification_data}})
            user = users_col.find_one({"contact": contact})
        else:
            user["verification"] = verification_data
        if user:
            save_user_to_file(user)

        send_verification_email(recipient=contact, code=code, purpose="support_activation")
    except Exception:
        if MONGO_AVAILABLE and users_col is not None:
            users_col.update_one({"contact": contact}, {"$unset": {"verification": ""}})
            user = users_col.find_one({"contact": contact})
        else:
            user.pop("verification", None)
        if user:
            save_user_to_file(user)
        return jsonify(
            success=False,
            message="Verification email could not be sent. Please check delivery configuration and try again.",
        ), 502

    return jsonify(
        success=True,
        message="A fresh 10-minute verification code was sent to the user's registered email address.",
    ), 200


# =========================================================
# REQUEST VERIFICATION CODE
# =========================================================

@auth_bp.route(
    "/api/request-code",
    methods=["POST"],
)
def request_code():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    contact = data.get(
        "contact"
    )

    contact = str(contact or "").strip()

    if not contact:
        return jsonify(
            success=False,
            message="Email address required",
        ), 400

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", contact):
        return jsonify(
            success=False,
            message="Enter a valid email address to receive your activation code.",
        ), 422

    user = (
        users_col.find_one(
            {
                "contact": contact
            }
        )
        if MONGO_AVAILABLE
        else get_user_from_file(
            contact
        )
    )

    if not user:

        return jsonify(
            success=False,
            message="Account not found",
        ), 404

    code = generate_code()

    verification_data = {
        "code": code,
        "expires": expires_in(
            10
        ).isoformat(),
    }

    if MONGO_AVAILABLE:

        users_col.update_one(
            {
                "contact": contact
            },
            {
                "$set": {
                    "verification": verification_data
                }
            },
        )

        user = users_col.find_one(
            {
                "contact": contact
            }
        )

    else:

        user["verification"] = (
            verification_data
        )

    save_user_to_file(
        user
    )

    try:
        send_verification_email(
            recipient=contact,
            code=code,
            purpose="activation",
        )
    except Exception:
        # Do not leave a usable code behind when delivery failed.
        if MONGO_AVAILABLE:
            users_col.update_one(
                {"contact": contact},
                {"$unset": {"verification": ""}},
            )
            user = users_col.find_one({"contact": contact})
        else:
            user.pop("verification", None)
        if user:
            save_user_to_file(user)
        return jsonify(
            success=False,
            message="We could not send the activation email. Please try again shortly.",
        ), 502

    return jsonify(
        success=True,
        message="Activation code sent to your email address. It expires in 10 minutes.",
    ), 200


# =========================================================
# VERIFY ACCOUNT
# =========================================================

@auth_bp.route(
    "/api/verify",
    methods=["POST"],
)
def verify():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    contact = data.get(
        "contact"
    )

    code = data.get(
        "code"
    )

    if not all([
        contact,
        code,
    ]):

        return jsonify(
            success=False,
            message="Contact and code required",
        ), 400

    user = (
        users_col.find_one(
            {
                "contact": contact
            }
        )
        if MONGO_AVAILABLE
        else get_user_from_file(
            contact
        )
    )

    if not user:

        return jsonify(
            success=False,
            message="Account not found",
        ), 404

    verification = user.get(
        "verification",
        {},
    )

    if verification.get(
        "code"
    ) != code:

        return jsonify(
            success=False,
            message="Invalid code",
        ), 400

    if is_expired(
        verification.get(
            "expires"
        )
    ):

        return jsonify(
            success=False,
            message="Code expired",
        ), 400

    # -----------------------------------------------------
    # MONGO
    # -----------------------------------------------------

    if MONGO_AVAILABLE:

        users_col.update_one(
            {
                "contact": contact
            },
            {
                "$set": {
                    "verified": True
                },

                "$unset": {
                    "verification": ""
                },
            },
        )

        user = users_col.find_one(
            {
                "contact": contact
            }
        )

    else:

        user["verified"] = True

        user.pop(
            "verification",
            None,
        )

    save_user_to_file(
        user
    )

    return jsonify(
        success=True,
        message="Account verified",
    ), 200


# =========================================================
# LOGIN
# =========================================================

@auth_bp.route(
    "/api/auth/login",
    methods=["POST"],
)
@auth_bp.route(
    "/api/login",
    methods=["POST"],
)
def login():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    contact = data.get(
        "contact"
    )

    password = data.get(
        "password"
    )

    if not all([
        contact,
        password,
    ]):

        return jsonify(
            success=False,
            message="Contact and password required",
        ), 400

    # -----------------------------------------------------
    # LOAD USER
    # -----------------------------------------------------

    user = (
        users_col.find_one(
            {
                "contact": contact
            }
        )
        if MONGO_AVAILABLE
        else get_user_from_file(
            contact
        )
    )

    if not user:

        return jsonify(
            success=False,
            message="Account not found",
        ), 404

    # -----------------------------------------------------
    # CURRENT ACCOUNT STATUS
    # -----------------------------------------------------

    account_status = str(user.get("status") or "active").strip().casefold()
    if user.get("is_active") is False or account_status in {
        "inactive", "disabled", "suspended", "blocked", "banned",
        "deleted", "revoked", "pending_invitation",
    }:
        return jsonify(
            success=False,
            code="account_inactive",
            message="This account is inactive or restricted. Contact RevelaCode Support.",
        ), 403

    # -----------------------------------------------------
    # VERIFICATION
    # -----------------------------------------------------

    if not user.get(
        "verified"
    ):

        return jsonify(
            success=False,
            message="Account not verified",
        ), 403

    # -----------------------------------------------------
    # PASSWORD
    # -----------------------------------------------------

    stored_password = user.get(
        "password"
    )

    if not stored_password:

        return jsonify(
            success=False,
            message="Account credentials are invalid",
        ), 401

    if not check_password_hash(
        stored_password,
        password,
    ):

        return jsonify(
            success=False,
            message="Invalid password",
        ), 401

    # -----------------------------------------------------
    # ROLE
    # -----------------------------------------------------

    role = user.get(
        "role",
        "user",
    )

    # -----------------------------------------------------
    # REDIRECT
    # -----------------------------------------------------

    redirect = "/dashboard"

    api_key = ""

    if str(role or "").strip().casefold() in PLATFORM_ADMIN_ROLES:

        redirect = "/admin/dashboard"
        # Platform admin browser APIs use the current-role JWT path. API keys
        # remain server-side for trusted server-to-server integrations only.

    elif str(role or "").strip().casefold() in {"support", "support_admin"}:

        redirect = "/support/dashboard"
        api_key = ""

    # -----------------------------------------------------
    # JWT
    # -----------------------------------------------------

    token = create_access_token(
        user
    )

    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    return jsonify(
        success=True,

        # Canonical identity is the same ID used in the signed JWT subject.
        userId=str(user.get("_id") or user.get("id") or user.get("user_id") or ""),
        id=str(user.get("_id") or user.get("id") or user.get("user_id") or ""),

        contact=user.get(
            "contact",
            "",
        ),

        full_name=user.get(
            "full_name",
            "",
        ),

        role=role,

        redirect=redirect,

        # Admin legacy views still use their scoped key. Support clients use JWTs.
        access_token=token,

        token_type="Bearer",

        expires_in=(
            JWT_EXPIRES_HOURS * 60 * 60
        ),
    ), 200