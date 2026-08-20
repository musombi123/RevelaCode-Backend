# backend/user_profile/accounts.py

from __future__ import annotations

import json
import os
import random
import threading

from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash

from .db import users_col


# =========================================================
# DATA FOLDER
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
# BLUEPRINT
# =========================================================

accounts_bp = Blueprint(
    "accounts",
    __name__,
)


# =========================================================
# TIME
# =========================================================

def now():
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
    if not value:
        return True

    try:

        if isinstance(
            value,
            str,
        ):
            value = datetime.fromisoformat(
                value
            )

        if value.tzinfo is None:
            value = value.replace(
                tzinfo=timezone.utc
            )

        return now() > value

    except (
        ValueError,
        TypeError,
    ):
        return True


# =========================================================
# CODE GENERATION
# =========================================================

def generate_code():
    return str(
        random.randint(
            100000,
            999999,
        )
    )


# =========================================================
# FILE STORAGE
# =========================================================

def sanitize_mongo_doc(
    doc: dict,
):
    if not doc:
        return doc

    output = dict(doc)

    if "_id" in output:
        output["_id"] = str(
            output["_id"]
        )

    return output


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
        ) as f:

            return json.load(f)

    except (
        json.JSONDecodeError,
        OSError,
    ):

        return {}


def save_users_file(
    users,
):

    with file_lock:

        temp_file = (
            USERS_FILE
            + ".tmp"
        )

        with open(
            temp_file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                users,
                f,
                indent=2,
            )

        os.replace(
            temp_file,
            USERS_FILE,
        )


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


def get_user_from_file(
    contact,
):

    users = load_users_file()

    return users.get(
        contact
    )


# =========================================================
# USER LOOKUP
# =========================================================

def find_user(
    contact,
):

    if users_col is not None:

        return users_col.find_one(
            {
                "contact": contact
            }
        )

    return get_user_from_file(
        contact
    )


# =========================================================
# REQUEST PASSWORD RESET
# =========================================================

@accounts_bp.route(
    "/api/request-reset",
    methods=["POST"],
)
def request_reset():

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

    user = find_user(
        contact
    )

    if not user:

        return jsonify(
            success=False,
            message="Account not found",
        ), 404

    code = generate_code()

    reset_data = {
        "code": code,
        "expires": expires_in(
            10
        ).isoformat(),
    }

    if users_col is not None:

        users_col.update_one(
            {
                "contact": contact
            },
            {
                "$set": {
                    "password_reset": reset_data
                }
            },
        )

    else:

        user["password_reset"] = (
            reset_data
        )

        save_user_to_file(
            user
        )

    # Keep this only for development.
    # Replace with your SMS/email delivery system
    # before production.
    return jsonify(
        success=True,
        debug_code=code,
    ), 200


# =========================================================
# VERIFY RESET CODE
# =========================================================

@accounts_bp.route(
    "/api/verify-reset",
    methods=["POST"],
)
def verify_reset():

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

    if not contact or not code:

        return jsonify(
            success=False,
            message="Contact and code required",
        ), 400

    user = find_user(
        contact
    )

    if not user:

        return jsonify(
            success=False,
            message="Account not found",
        ), 404

    reset = user.get(
        "password_reset",
        {}
    )

    if reset.get(
        "code"
    ) != code:

        return jsonify(
            success=False,
            message="Invalid code",
        ), 400

    if is_expired(
        reset.get(
            "expires"
        )
    ):

        return jsonify(
            success=False,
            message="Code expired",
        ), 400

    # -----------------------------------------------------
    # IMPORTANT
    # Store a short-lived authorization timestamp instead
    # of a permanent boolean.
    # -----------------------------------------------------

    reset_authorized_until = (
        now()
        + timedelta(
            minutes=15
        )
    ).isoformat()

    if users_col is not None:

        users_col.update_one(
            {
                "contact": contact
            },
            {
                "$set": {
                    "password_reset_authorized_until":
                        reset_authorized_until
                },

                "$unset": {
                    "password_reset": ""
                },
            },
        )

    else:

        user[
            "password_reset_authorized_until"
        ] = reset_authorized_until

        user.pop(
            "password_reset",
            None,
        )

        save_user_to_file(
            user
        )

    return jsonify(
        success=True,
        message="Code verified, proceed to reset",
    ), 200


# =========================================================
# RESET PASSWORD
# =========================================================

@accounts_bp.route(
    "/api/reset-password",
    methods=["POST"],
)
def reset_password():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    contact = data.get(
        "contact"
    )

    new_password = data.get(
        "new_password"
    )

    confirm = data.get(
        "confirm_password"
    )

    if not all([
        contact,
        new_password,
        confirm,
    ]):

        return jsonify(
            success=False,
            message="All fields required",
        ), 400

    if new_password != confirm:

        return jsonify(
            success=False,
            message="Passwords do not match",
        ), 400

    if len(new_password) < 8:

        return jsonify(
            success=False,
            message="Password must be at least 8 characters",
        ), 422

    user = find_user(
        contact
    )

    if not user:

        return jsonify(
            success=False,
            message="Account not found",
        ), 404

    authorized_until = user.get(
        "password_reset_authorized_until"
    )

    if not authorized_until:

        return jsonify(
            success=False,
            message="Reset not authorized",
        ), 403

    if is_expired(
        authorized_until
    ):

        if users_col is not None:

            users_col.update_one(
                {
                    "contact": contact
                },
                {
                    "$unset": {
                        "password_reset_authorized_until":
                            ""
                    }
                },
            )

        return jsonify(
            success=False,
            message="Password reset authorization expired",
        ), 403

    # =====================================================
    # IMPORTANT:
    # Use the SAME hashing mechanism as AuthGate.
    # =====================================================

    password_hash = (
        generate_password_hash(
            new_password
        )
    )

    if users_col is not None:

        users_col.update_one(
            {
                "contact": contact
            },
            {
                "$set": {
                    "password": password_hash
                },

                "$unset": {
                    "password_reset_authorized_until":
                        ""
                },
            },
        )

    else:

        user["password"] = (
            password_hash
        )

        user.pop(
            "password_reset_authorized_until",
            None,
        )

        save_user_to_file(
            user
        )

    return jsonify(
        success=True,
        message="Password reset successful",
    ), 200


# =========================================================
# REQUEST ACCOUNT DELETE
# =========================================================

@accounts_bp.route(
    "/api/request-delete",
    methods=["POST"],
)
def request_delete():

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

    user = find_user(
        contact
    )

    if not user:

        return jsonify(
            success=False,
            message="Account not found",
        ), 404

    code = generate_code()

    delete_data = {
        "code": code,
        "expires": expires_in(
            10
        ).isoformat(),
    }

    if users_col is not None:

        users_col.update_one(
            {
                "contact": contact
            },
            {
                "$set": {
                    "delete_verification":
                        delete_data
                }
            },
        )

    else:

        user[
            "delete_verification"
        ] = delete_data

        save_user_to_file(
            user
        )

    return jsonify(
        success=True,
        debug_code=code,
    ), 200


# =========================================================
# CONFIRM ACCOUNT DELETE
# =========================================================

@accounts_bp.route(
    "/api/confirm-delete",
    methods=["POST"],
)
def confirm_delete():

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

    if not contact or not code:

        return jsonify(
            success=False,
            message="Contact and code required",
        ), 400

    user = find_user(
        contact
    )

    if not user:

        return jsonify(
            success=False,
            message="Account not found",
        ), 404

    delete_verification = user.get(
        "delete_verification",
        {}
    )

    if delete_verification.get(
        "code"
    ) != code:

        return jsonify(
            success=False,
            message="Invalid code",
        ), 400

    if is_expired(
        delete_verification.get(
            "expires"
        )
    ):

        return jsonify(
            success=False,
            message="Code expired",
        ), 400

    if users_col is not None:

        users_col.delete_one(
            {
                "contact": contact
            }
        )

    else:

        users = load_users_file()

        users.pop(
            contact,
            None,
        )

        save_users_file(
            users
        )

    return jsonify(
        success=True,
        message="Account permanently deleted",
    ), 200
