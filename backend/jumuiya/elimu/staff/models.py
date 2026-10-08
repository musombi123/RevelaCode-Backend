# backend/jumuiya/elimu/staff/models.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Any, Iterable, Mapping

from backend.jumuiya.elimu.permissions import (
    PERMISSIONS,
    ROLE_BURSAR,
    ROLE_OWNER,
    ROLE_REGISTRAR,
    ROLE_TEACHER,
)


# =========================================================
# COLLECTIONS
# =========================================================

COLLECTION = "jumuiya_elimu_school_members"
INVITATIONS = "jumuiya_elimu_staff_invitations"


# =========================================================
# ROLES
# =========================================================

ROLES = (
    ROLE_OWNER,
    ROLE_BURSAR,
    ROLE_REGISTRAR,
    ROLE_TEACHER,
)


# =========================================================
# MEMBERSHIP STATUSES
# =========================================================
#
# Lifecycle:
#
#     pending
#        ↓
#     invited
#        ↓
#     accepted
#        ↓
#     active
#
# Optional terminal states:
#     suspended
#     removed
#
# =========================================================

STATUS_PENDING = "pending"
STATUS_INVITED = "invited"
STATUS_ACCEPTED = "accepted"
STATUS_ACTIVE = "active"
STATUS_SUSPENDED = "suspended"
STATUS_REMOVED = "removed"

STATUSES = (
    STATUS_PENDING,
    STATUS_INVITED,
    STATUS_ACCEPTED,
    STATUS_ACTIVE,
    STATUS_SUSPENDED,
    STATUS_REMOVED,
)


# =========================================================
# DEFAULTS
# =========================================================

DEFAULT_INVITATION_EXPIRY_DAYS = 7


# =========================================================
# TIME
# =========================================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# =========================================================
# NORMALIZATION
# =========================================================

def normalize_id(value: Any) -> str | None:
    """
    Normalize IDs to strings.

    MongoDB can contain ObjectId-backed IDs while API contracts
    generally work with strings. Keeping membership documents
    consistent makes cross-module authorization easier.
    """

    if value is None:
        return None

    value = str(value).strip()

    return value or None


def normalize_email(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip().lower()


def normalize_role(role: Any) -> str:
    value = str(
        role or ""
    ).strip().lower()

    if value not in ROLES:
        raise ValueError(
            "Invalid Elimu staff role."
        )

    return value


def normalize_status(status: Any) -> str:
    value = str(
        status or ""
    ).strip().lower()

    if value not in STATUSES:
        raise ValueError(
            "Invalid Elimu membership status."
        )

    return value


def normalize_permissions(
    permissions: Iterable[str] | None,
) -> list[str]:
    """
    Keep only known Elimu permissions and remove duplicates.
    """

    if permissions is None:
        return []

    allowed = set(PERMISSIONS)

    output = []

    for permission in permissions:
        value = str(
            permission or ""
        ).strip()

        if not value:
            continue

        if value not in allowed:
            continue

        if value not in output:
            output.append(value)

    return sorted(output)


def normalize_class_ids(
    class_ids: Iterable[Any] | None,
) -> list[str]:
    if class_ids is None:
        return []

    output = []

    for class_id in class_ids:
        normalized = normalize_id(
            class_id
        )

        if not normalized:
            continue

        if normalized not in output:
            output.append(normalized)

    return output


# =========================================================
# INVITATION TOKEN
# =========================================================

def invitation_token() -> str:
    """
    Generate a high-entropy invitation token.

    The raw token should only be delivered to the invited staff
    member. The database should store its hash.
    """

    return secrets.token_urlsafe(32)


def hash_invitation_token(
    token: str,
) -> str:
    if not isinstance(token, str):
        raise ValueError(
            "Invitation token must be text."
        )

    token = token.strip()

    if not token:
        raise ValueError(
            "Invitation token is required."
        )

    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


# =========================================================
# INVITATION EXPIRY
# =========================================================

def invitation_expiry(
    days: int = DEFAULT_INVITATION_EXPIRY_DAYS,
) -> datetime:
    if not isinstance(days, int):
        raise ValueError(
            "Invitation expiry must be a whole number of days."
        )

    if days < 1 or days > 30:
        raise ValueError(
            "Invitation expiry must be between 1 and 30 days."
        )

    return (
        now_utc()
        + timedelta(days=days)
    )


# =========================================================
# MEMBERSHIP DOCUMENT
# =========================================================

def membership_doc(
    school_id: Any,
    user_id: Any,
    role: str,
    invited_by: Any = None,
    status: str = STATUS_ACTIVE,
    permissions: Iterable[str] | None = None,
    assigned_class_ids: Iterable[Any] | None = None,
    accepted_at: datetime | None = None,
    activated_at: datetime | None = None,
    suspended_at: datetime | None = None,
    removed_at: datetime | None = None,
    **extra: Any,
) -> dict:
    """
    Build a school staff membership document.

    This builder deliberately does not trust client-supplied
    ownership fields. Higher-level services remain responsible
    for determining the school and authorized inviter.
    """

    school = normalize_id(
        school_id
    )

    user = normalize_id(
        user_id
    )

    inviter = normalize_id(
        invited_by
    )

    if not school:
        raise ValueError(
            "school_id is required."
        )

    if not user:
        raise ValueError(
            "user_id is required for a membership."
        )

    normalized_role = normalize_role(
        role
    )

    normalized_status = normalize_status(
        status
    )

    now = now_utc()

    document = {
        "school_id": school,
        "user_id": user,
        "role": normalized_role,
        "status": normalized_status,
        "permissions": normalize_permissions(
            permissions
        ),
        "assigned_class_ids": normalize_class_ids(
            assigned_class_ids
        ),
        "invited_by": inviter,
        "created_at": now,
        "updated_at": now,
    }

    # -----------------------------------------------------
    # Lifecycle timestamps
    # -----------------------------------------------------

    if accepted_at is not None:
        document["accepted_at"] = accepted_at

    if activated_at is not None:
        document["activated_at"] = activated_at

    if suspended_at is not None:
        document["suspended_at"] = suspended_at

    if removed_at is not None:
        document["removed_at"] = removed_at

    # -----------------------------------------------------
    # Safe extension fields
    # -----------------------------------------------------
    #
    # Prevent callers from overriding protected membership
    # identity/state fields through **extra.
    #
    # -----------------------------------------------------

    protected = {
        "school_id",
        "user_id",
        "role",
        "status",
        "permissions",
        "assigned_class_ids",
        "invited_by",
        "created_at",
        "updated_at",
        "accepted_at",
        "activated_at",
        "suspended_at",
        "removed_at",
    }

    for key, value in extra.items():
        if key in protected:
            raise ValueError(
                f"{key} cannot be overridden."
            )

        document[key] = value

    return document


# =========================================================
# INVITATION DOCUMENT
# =========================================================

def invitation_doc(
    school_id: Any,
    email: str,
    role: str,
    invited_by: Any,
    permissions: Iterable[str] | None = None,
    assigned_class_ids: Iterable[Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    expires_in_days: int = DEFAULT_INVITATION_EXPIRY_DAYS,
) -> tuple[dict, str]:
    """
    Build a staff invitation document.

    Returns:
        (document, raw_token)

    `raw_token` is intended for the invitation delivery layer.

    MongoDB stores only `token_hash`, never the raw invitation token.
    """

    school = normalize_id(
        school_id
    )

    inviter = normalize_id(
        invited_by
    )

    normalized_email = normalize_email(
        email
    )

    if not school:
        raise ValueError(
            "school_id is required."
        )

    if not normalized_email:
        raise ValueError(
            "email is required."
        )

    if not inviter:
        raise ValueError(
            "invited_by is required."
        )

    normalized_role = normalize_role(
        role
    )

    raw_token = invitation_token()

    now = now_utc()

    document = {
        "school_id": school,
        "email": normalized_email,
        "role": normalized_role,
        "status": STATUS_INVITED,

        # Security:
        # never persist the raw invitation token.
        "token_hash": hash_invitation_token(
            raw_token
        ),

        "permissions": normalize_permissions(
            permissions
        ),

        "assigned_class_ids": normalize_class_ids(
            assigned_class_ids
        ),

        "invited_by": inviter,

        "metadata": dict(
            metadata or {}
        ),

        "created_at": now,
        "updated_at": now,
        "expires_at": invitation_expiry(
            expires_in_days
        ),

        # Lifecycle timestamps.
        "accepted_at": None,
        "activated_at": None,
        "cancelled_at": None,
    }

    return document, raw_token


# =========================================================
# INVITATION VALIDATION
# =========================================================

def invitation_is_expired(
    document: Mapping[str, Any],
    current_time: datetime | None = None,
) -> bool:
    expires_at = document.get(
        "expires_at"
    )

    if not isinstance(
        expires_at,
        datetime,
    ):
        return True

    current = (
        current_time
        or now_utc()
    )

    return expires_at <= current


def invitation_is_usable(
    document: Mapping[str, Any],
    current_time: datetime | None = None,
) -> bool:
    if not isinstance(
        document,
        Mapping,
    ):
        return False

    status = str(
        document.get(
            "status",
            "",
        )
    ).strip().lower()

    if status != STATUS_INVITED:
        return False

    return not invitation_is_expired(
        document,
        current_time,
    )


# =========================================================
# TOKEN VERIFICATION
# =========================================================

def verify_invitation_token(
    raw_token: str,
    stored_hash: str,
) -> bool:
    if not raw_token or not stored_hash:
        return False

    calculated = hash_invitation_token(
        raw_token
    )

    return secrets.compare_digest(
        calculated,
        str(stored_hash),
    )