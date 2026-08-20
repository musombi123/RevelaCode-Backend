# backend/user_profile/auth_gate.py

from __future__ import annotations

import json
import os
import random
import threading

import jwt

from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from flask import Blueprint, jsonify, request
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

    if not contact:

        return jsonify(
            success=False,
            message="Contact required",
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

    return jsonify(
        success=True,

        # Keep this for your current development
        # verification flow. Remove it before exposing
        # this endpoint publicly.
        debug_code=code,
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

    if role == "admin":

        redirect = (
            "/admin/dashboard"
        )

        api_key = ADMIN_API_KEY

    elif role == "support":

        redirect = (
            "/support/dashboard"
        )

        api_key = SUPPORT_API_KEY

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

        api_key=api_key,

        access_token=token,

        token_type="Bearer",

        expires_in=(
            JWT_EXPIRES_HOURS * 60 * 60
        ),
    ), 200