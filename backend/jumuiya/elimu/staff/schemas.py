# backend/jumuiya/elimu/staff/schemas.py

from __future__ import annotations

from backend.jumuiya.elimu.permissions import (
    PERMISSIONS,
    ROLE_BURSAR,
    ROLE_REGISTRAR,
    ROLE_TEACHER,
    ROLE_PERMISSIONS,
)


# =========================================================
# ROLES
# =========================================================

ROLES = {
    ROLE_BURSAR,
    ROLE_REGISTRAR,
    ROLE_TEACHER,
}

ALL_ROLES = {
    "owner",
    ROLE_BURSAR,
    ROLE_REGISTRAR,
    ROLE_TEACHER,
}


# =========================================================
# STAFF STATUSES
# =========================================================

STAFF_STATUSES = {
    "active",
    "suspended",
    "removed",
}


# =========================================================
# ASSIGNMENT STATUSES
# =========================================================

ASSIGNMENT_STATUSES = {
    "active",
    "inactive",
}


# =========================================================
# LIMITS
# =========================================================

MAX_CLASS_IDS = 200
MAX_PERMISSIONS = 100
MAX_SUBJECTS = 50
MAX_METADATA_KEYS = 30
MAX_EMAIL_LENGTH = 160
MAX_TOKEN_LENGTH = 500


# =========================================================
# HELPERS
# =========================================================

def _object(data):
    if not isinstance(data, dict):
        raise ValueError(
            "JSON object is required."
        )

    return data


def _text(
    value,
    *,
    max_len=500,
) -> str:
    if value is None:
        return ""

    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            "Value must be text."
        )

    value = value.strip()

    if len(value) > max_len:
        raise ValueError(
            f"Value must not exceed {max_len} characters."
        )

    return value


def _required(
    data,
    key,
    *,
    max_len=500,
) -> str:
    value = _text(
        data.get(key),
        max_len=max_len,
    )

    if not value:
        raise ValueError(
            f"{key} is required."
        )

    return value


def _normalize_list(
    value,
    *,
    key,
    maximum,
    item_max_len=200,
) -> list[str]:
    if value is None:
        return []

    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            f"{key} must be a list."
        )

    if len(value) > maximum:
        raise ValueError(
            f"{key} cannot contain more than {maximum} items."
        )

    output = []

    for item in value:
        normalized = _text(
            item,
            max_len=item_max_len,
        )

        if not normalized:
            continue

        if normalized not in output:
            output.append(normalized)

    return output


def _email(value) -> str:
    value = _text(
        value,
        max_len=MAX_EMAIL_LENGTH,
    ).lower()

    if not value:
        return ""

    # Lightweight request validation only.
    # Verification belongs to the invitation/account flow.
    if (
        "@" not in value
        or value.startswith("@")
        or value.endswith("@")
        or " " in value
        or value.count("@") != 1
    ):
        raise ValueError(
            "email must be a valid email address."
        )

    local, domain = value.split(
        "@",
        1,
    )

    if not local or not domain:
        raise ValueError(
            "email must be a valid email address."
        )

    return value


def _role(value) -> str:
    value = _text(
        value,
        max_len=60,
    ).lower()

    if value not in ALL_ROLES:
        raise ValueError(
            "Invalid Elimu role."
        )

    return value


def _staff_role(value) -> str:
    role = _role(
        value
    )

    if role == "owner":
        raise ValueError(
            "Owner cannot be managed through staff management."
        )

    return role


def _permissions(
    value,
    *,
    role: str,
) -> list[str]:
    permissions = _normalize_list(
        value,
        key="permissions",
        maximum=MAX_PERMISSIONS,
        item_max_len=120,
    )

    if not permissions:
        return []

    known = set(
        PERMISSIONS
    )

    invalid = [
        permission
        for permission in permissions
        if permission not in known
    ]

    if invalid:
        raise ValueError(
            "permissions contains unknown Elimu permissions."
        )

    # A role may only receive permissions that are valid
    # for that role. Services must still enforce authorization.
    allowed_for_role = set(
        ROLE_PERMISSIONS.get(
            role,
            set(),
        )
    )

    outside_role = [
        permission
        for permission in permissions
        if permission not in allowed_for_role
    ]

    if outside_role:
        raise ValueError(
            "permissions contains permissions outside the selected role."
        )

    return permissions


def _class_ids(
    value,
) -> list[str]:
    return _normalize_list(
        value,
        key="assigned_class_ids",
        maximum=MAX_CLASS_IDS,
        item_max_len=120,
    )


def _subjects(
    value,
) -> list[str]:
    return _normalize_list(
        value,
        key="subjects",
        maximum=MAX_SUBJECTS,
        item_max_len=120,
    )


def _metadata(
    value,
) -> dict:
    if value is None:
        return {}

    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            "metadata must be an object."
        )

    if len(value) > MAX_METADATA_KEYS:
        raise ValueError(
            "metadata contains too many fields."
        )

    return dict(
        value
    )


# =========================================================
# INVITE STAFF
# =========================================================

def invite_payload(data):
    """
    Validate an Owner-created staff invitation.

    The backend determines:
      - school_id
      - invited_by
      - authenticated owner
      - final membership state

    The client must not submit those fields.
    """

    _object(data)

    role = _staff_role(
        _required(
            data,
            "role",
            max_len=60,
        )
    )

    user_id = _text(
        data.get("user_id"),
        max_len=120,
    ) or None

    email = _email(
        data.get("email")
    ) or None

    if not user_id and not email:
        raise ValueError(
            "user_id or email is required."
        )

    assigned_class_ids = _class_ids(
        data.get(
            "assigned_class_ids",
            [],
        )
    )

    # Class assignments are meaningful for teachers.
    if (
        assigned_class_ids
        and role != ROLE_TEACHER
    ):
        raise ValueError(
            "assigned_class_ids may only be provided for teachers."
        )

    permissions = _permissions(
        data.get(
            "permissions",
            [],
        ),
        role=role,
    )

    metadata = _metadata(
        data.get(
            "metadata"
        )
    )

    expires_in_days = data.get(
        "expires_in_days",
        7,
    )

    if isinstance(
        expires_in_days,
        bool,
    ):
        raise ValueError(
            "expires_in_days must be a whole number."
        )

    try:
        expires_in_days = int(
            expires_in_days
        )
    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "expires_in_days must be a whole number."
        )

    if not 1 <= expires_in_days <= 30:
        raise ValueError(
            "expires_in_days must be between 1 and 30."
        )

    return {
        "user_id": user_id,
        "email": email,
        "role": role,
        "assigned_class_ids": assigned_class_ids,
        "permissions": permissions,
        "metadata": metadata,
        "expires_in_days": expires_in_days,
    }


# =========================================================
# UPDATE STAFF MEMBERSHIP
# =========================================================

def update_payload(data):
    """
    Validate mutable staff membership fields.

    Protected fields such as:
      school_id
      user_id
      invited_by
      created_at

    are intentionally excluded.
    """

    _object(data)

    output = {}

    if "role" in data:
        role = _staff_role(
            data.get("role")
        )

        output["role"] = role

        # If permissions are also supplied, validate them
        # against the new role.
        if "permissions" in data:
            output["permissions"] = _permissions(
                data.get(
                    "permissions"
                ),
                role=role,
            )

    elif "permissions" in data:
        raise ValueError(
            "role is required when changing permissions."
        )

    if "assigned_class_ids" in data:
        class_ids = _class_ids(
            data.get(
                "assigned_class_ids"
            )
        )

        output["assigned_class_ids"] = class_ids

    if "permissions" in data and "role" not in data:
        # Existing role will be resolved by the service,
        # therefore the service must revalidate the final
        # permissions against the stored role.
        output["permissions"] = _normalize_list(
            data.get(
                "permissions"
            ),
            key="permissions",
            maximum=MAX_PERMISSIONS,
            item_max_len=120,
        )

        unknown = [
            permission
            for permission in output["permissions"]
            if permission not in PERMISSIONS
        ]

        if unknown:
            raise ValueError(
                "permissions contains unknown Elimu permissions."
            )

    if "assigned_class_ids" in data:
        # The service will verify that these classes belong
        # to the same school and that the target user is a teacher.
        pass

    if "status" in data:
        status = _text(
            data.get("status"),
            max_len=30,
        ).lower()

        if status not in STAFF_STATUSES:
            raise ValueError(
                "Invalid staff status."
            )

        output["status"] = status

    if not output:
        raise ValueError(
            "At least one field is required."
        )

    return output


# =========================================================
# ACCEPT INVITATION
# =========================================================

def accept_payload(data):
    _object(data)

    token = _required(
        data,
        "token",
        max_len=MAX_TOKEN_LENGTH,
    )

    return {
        "token": token,
    }


# =========================================================
# TEACHER / CLASS ASSIGNMENT
# =========================================================

def assignment_payload(data):
    _object(data)

    teacher_user_id = _required(
        data,
        "teacher_user_id",
        max_len=120,
    )

    class_id = _required(
        data,
        "class_id",
        max_len=120,
    )

    subjects = _subjects(
        data.get(
            "subjects",
            [],
        )
    )

    status = _text(
        data.get(
            "status",
            "active",
        ),
        max_len=30,
    ).lower()

    if status not in ASSIGNMENT_STATUSES:
        raise ValueError(
            "Invalid teacher assignment status."
        )

    return {
        "teacher_user_id": teacher_user_id,
        "class_id": class_id,
        "subjects": subjects,
        "status": status,
    }