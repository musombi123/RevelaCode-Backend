# backend/user_profile/user_data.py

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, g


# =========================================================
# MONGO SETUP
# =========================================================

try:
    from backend.db import db

    MONGO_AVAILABLE = True

    users_col = db.get_collection("users")

except Exception:

    MONGO_AVAILABLE = False
    users_col = None


# =========================================================
# FILE FALLBACK
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


def now_utc():
    return datetime.now(timezone.utc)


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


# =========================================================
# SERIALIZATION
# =========================================================

def sanitize_mongo_doc(
    doc: dict,
) -> dict:

    if not doc:
        return doc

    output = dict(doc)

    if "_id" in output:

        output["_id"] = str(
            output["_id"]
        )

    return output


# =========================================================
# BLUEPRINT
# =========================================================

user_bp = Blueprint(
    "user_bp",
    __name__,
)


# =========================================================
# AUTHENTICATED USER
# =========================================================

def authenticated_user():

    user = getattr(
        g,
        "jumuiya_user",
        None,
    )

    # Support the existing RevelaCode
    # auth context if one exists.
    if not user:

        user = getattr(
            g,
            "revelacode_user",
            None,
        )

    if not user:

        return None

    return user


def authenticated_contact():

    user = authenticated_user()

    if not user:
        return None

    return (
        user.get("contact")
        or user.get("phone")
        or user.get("phone_number")
    )


def authenticated_user_id():

    user = authenticated_user()

    if not user:
        return None

    value = (
        user.get("id")
        or user.get("_id")
        or user.get("user_id")
    )

    return (
        str(value)
        if value is not None
        else None
    )


# =========================================================
# SANITIZED USER DATA
# =========================================================

def public_user_data(
    user,
):
    """
    Return only the application-level user data.

    Never expose password, verification codes,
    or authentication secrets.
    """

    if not user:
        return None

    return {
        "id": (
            str(
                user.get("_id")
                or user.get("id")
                or user.get("user_id")
            )
            if (
                user.get("_id")
                or user.get("id")
                or user.get("user_id")
            )
            else None
        ),

        "contact": user.get(
            "contact",
            "",
        ),

        "history": user.get(
            "history",
            [],
        ),

        "settings": user.get(
            "settings",
            {
                "theme": "light",
                "linked_accounts": [],
            },
        ),

        "domains": user.get(
            "domains",
            [],
        ),

        "created_at": user.get(
            "created_at"
        ),
    }


# =========================================================
# GET USER BY CONTACT
# =========================================================

def get_user_record(
    contact,
):
    """
    Internal helper used to load the existing
    RevelaCode user record.
    """

    user = None

    if MONGO_AVAILABLE:

        user = users_col.find_one({
            "contact": contact
        })

    if not user:

        users = load_users_file()

        user = users.get(
            contact
        )

    return user


# =========================================================
# GET /api/user/me
# =========================================================

@user_bp.route(
    "/api/user/me",
    methods=["GET"],
)
def get_my_user():

    contact = authenticated_contact()

    if not contact:

        return jsonify(
            success=False,
            message="Authentication required",
        ), 401

    user = get_user_record(
        contact
    )

    if not user:

        return jsonify(
            success=False,
            message="User account not found",
        ), 404

    return jsonify(
        success=True,
        data=public_user_data(
            user
        ),
    ), 200


# =========================================================
# POST /api/user/me
# =========================================================

@user_bp.route(
    "/api/user/me",
    methods=["POST"],
)
def update_my_user():

    contact = authenticated_contact()

    if not contact:

        return jsonify(
            success=False,
            message="Authentication required",
        ), 401

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    if not isinstance(
        data,
        dict,
    ):

        return jsonify(
            success=False,
            message="JSON object required",
        ), 400

    update = {}

    # -----------------------------------------------------
    # HISTORY
    # -----------------------------------------------------

    if "history" in data:

        if not isinstance(
            data["history"],
            list,
        ):

            return jsonify(
                success=False,
                message="history must be a list",
            ), 422

        update["history"] = (
            data["history"]
        )

    # -----------------------------------------------------
    # SETTINGS
    # -----------------------------------------------------

    if "settings" in data:

        if not isinstance(
            data["settings"],
            dict,
        ):

            return jsonify(
                success=False,
                message="settings must be an object",
            ), 422

        update["settings"] = (
            data["settings"]
        )

    # -----------------------------------------------------
    # DOMAINS
    # -----------------------------------------------------

    if "domains" in data:

        if not isinstance(
            data["domains"],
            list,
        ):

            return jsonify(
                success=False,
                message="domains must be a list",
            ), 422

        update["domains"] = (
            data["domains"]
        )

    if not update:

        return jsonify(
            success=False,
            message="No valid user fields supplied",
        ), 422

    # -----------------------------------------------------
    # MONGO
    # -----------------------------------------------------

    if MONGO_AVAILABLE:

        result = users_col.update_one(
            {
                "contact": contact
            },
            {
                "$set": update
            },
        )

        if result.matched_count == 0:

            return jsonify(
                success=False,
                message="User account not found",
            ), 404

    # -----------------------------------------------------
    # FILE FALLBACK
    # -----------------------------------------------------

    users = load_users_file()

    if contact not in users:

        users[contact] = {
            "contact": contact,
            "history": [],
            "settings": {
                "theme": "light",
                "linked_accounts": [],
            },
            "domains": [],
            "created_at": now_utc().isoformat(),
        }

    users[contact].update(
        update
    )

    users[contact] = (
        sanitize_mongo_doc(
            users[contact]
        )
    )

    save_users_file(
        users
    )

    return jsonify(
        success=True,
        message="User data updated",
    ), 200


# =========================================================
# LEGACY GET ROUTE
# =========================================================

@user_bp.route(
    "/api/user/<contact>",
    methods=["GET"],
)
def legacy_get_user(contact):

    current_contact = (
        authenticated_contact()
    )

    if not current_contact:

        return jsonify(
            success=False,
            message="Authentication required",
        ), 401

    if contact != current_contact:

        return jsonify(
            success=False,
            message="You can only access your own user data",
        ), 403

    user = get_user_record(
        contact
    )

    if not user:

        return jsonify(
            success=False,
            message="User account not found",
        ), 404

    return jsonify(
        public_user_data(
            user
        )
    ), 200


# =========================================================
# LEGACY UPDATE ROUTE
# =========================================================

@user_bp.route(
    "/api/user/<contact>",
    methods=["POST"],
)
def legacy_update_user(contact):

    current_contact = (
        authenticated_contact()
    )

    if not current_contact:

        return jsonify(
            success=False,
            message="Authentication required",
        ), 401

    if contact != current_contact:

        return jsonify(
            success=False,
            message="You can only update your own user data",
        ), 403

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    if not isinstance(
        data,
        dict,
    ):

        return jsonify(
            success=False,
            message="JSON object required",
        ), 400

    update = {}

    if "history" in data:

        if not isinstance(
            data["history"],
            list,
        ):

            return jsonify(
                success=False,
                message="history must be a list",
            ), 422

        update["history"] = (
            data["history"]
        )

    if "settings" in data:

        if not isinstance(
            data["settings"],
            dict,
        ):

            return jsonify(
                success=False,
                message="settings must be an object",
            ), 422

        update["settings"] = (
            data["settings"]
        )

    if "domains" in data:

        if not isinstance(
            data["domains"],
            list,
        ):

            return jsonify(
                success=False,
                message="domains must be a list",
            ), 422

        update["domains"] = (
            data["domains"]
        )

    if not update:

        return jsonify(
            success=False,
            message="No valid user fields supplied",
        ), 422

    if MONGO_AVAILABLE:

        users_col.update_one(
            {
                "contact": contact
            },
            {
                "$set": update
            },
        )

    users = load_users_file()

    if contact not in users:

        users[contact] = {
            "contact": contact,
            "history": [],
            "settings": {
                "theme": "light",
                "linked_accounts": [],
            },
            "domains": [],
            "created_at": now_utc().isoformat(),
        }

    users[contact].update(
        update
    )

    users[contact] = (
        sanitize_mongo_doc(
            users[contact]
        )
    )

    save_users_file(
        users
    )

    return jsonify({
        "success": True,
        "message": "User data updated",
    }), 200