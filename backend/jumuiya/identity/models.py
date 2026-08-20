# backend/jumuiya/identity/models.py

from __future__ import annotations

from datetime import datetime, timezone


# =========================================================
# TIME
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


# =========================================================
# PROFILE DOCUMENT
# =========================================================

def profile_document(user):
    """
    Create the Jumuiya ecosystem profile for an existing
    RevelaCode authenticated user.

    IMPORTANT:
    This does NOT create a second user account.

    The RevelaCode `users` collection remains the source
    of truth for authentication and account identity.
    """

    if not isinstance(user, dict):
        raise ValueError(
            "User identity must be a dictionary."
        )

    user_id = (
        user.get("id")
        or user.get("_id")
        or user.get("user_id")
    )

    if user_id is None:
        raise ValueError(
            "User identity must contain a usable ID."
        )

    roles = user.get("roles")

    if isinstance(roles, str):
        roles = [roles]

    if not isinstance(
        roles,
        (list, tuple, set),
    ):
        role = user.get("role")
        roles = (
            [role]
            if role
            else ["user"]
        )

    roles = list(
        dict.fromkeys(
            str(role).strip()
            for role in roles
            if role
        )
    )

    if not roles:
        roles = ["user"]

    now = now_utc()

    return {
        "user_id": str(user_id),

        "full_name": str(
            user.get(
                "full_name",
                "",
            )
            or ""
        ).strip(),

        "contact": str(
            user.get(
                "contact",
                "",
            )
            or ""
        ).strip(),

        "roles": roles,

        # -------------------------------------------------
        # Jumuiya profile information
        # -------------------------------------------------

        "bio": "",

        "avatar_url": "",

        "county": "",

        "town": "",

        # -------------------------------------------------
        # Timestamps
        # -------------------------------------------------

        "created_at": now,

        "updated_at": now,
    }