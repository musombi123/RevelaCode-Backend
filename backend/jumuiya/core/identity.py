# backend/jumuiya/core/identity.py

from __future__ import annotations


# =========================================================
# IDENTITY NORMALIZATION
# =========================================================

def normalize_user(raw_user: dict) -> dict:
    """
    Convert an existing RevelaCode authenticated user into
    the standard Jumuiya identity format.

    Jumuiya does NOT create a second user account.

    Existing RevelaCode authentication remains the source
    of truth.
    """

    if not isinstance(raw_user, dict):
        return {}

    # -----------------------------------------------------
    # USER ID
    # -----------------------------------------------------

    user_id = (
        raw_user.get("id")
        or raw_user.get("_id")
        or raw_user.get("user_id")
    )

    # -----------------------------------------------------
    # ROLES
    # -----------------------------------------------------

    roles = raw_user.get("roles")

    if isinstance(roles, str):
        roles = [roles]

    elif not isinstance(
        roles,
        (list, tuple, set),
    ):
        role = raw_user.get("role")

        roles = (
            [role]
            if role
            else ["user"]
        )

    roles = [
        str(role).strip()
        for role in roles
        if role
    ]

    if not roles:
        roles = ["user"]

    # Remove duplicates while preserving order.
    roles = list(
        dict.fromkeys(roles)
    )

    # -----------------------------------------------------
    # PRIMARY ROLE
    # -----------------------------------------------------

    primary_role = (
        raw_user.get("role")
        or roles[0]
        or "user"
    )

    # -----------------------------------------------------
    # NAME
    # -----------------------------------------------------

    full_name = (
        raw_user.get("full_name")
        or raw_user.get("name")
        or raw_user.get("display_name")
        or ""
    )

    # -----------------------------------------------------
    # CONTACT
    # -----------------------------------------------------

    contact = (
        raw_user.get("contact")
        or raw_user.get("phone")
        or raw_user.get("phone_number")
        or raw_user.get("mobile")
        or ""
    )

    # -----------------------------------------------------
    # EMAIL
    # -----------------------------------------------------

    email = (
        raw_user.get("email")
        or ""
    )

    # -----------------------------------------------------
    # VERIFICATION
    # -----------------------------------------------------

    verified = bool(
        raw_user.get(
            "verified",
            False,
        )
    )

    # -----------------------------------------------------
    # STANDARD JUMUIYA IDENTITY
    # -----------------------------------------------------

    return {
        "id": (
            str(user_id)
            if user_id is not None
            else None
        ),

        "full_name": str(
            full_name
        ).strip(),

        "contact": str(
            contact
        ).strip(),

        "email": str(
            email
        ).strip(),

        "role": str(
            primary_role
        ).strip(),

        "roles": roles,

        "verified": verified,
    }


# =========================================================
# IDENTITY VALIDATION
# =========================================================

def has_valid_identity(user: dict) -> bool:
    """
    Check whether a normalized Jumuiya identity contains
    a usable user ID.
    """

    if not isinstance(
        user,
        dict,
    ):
        return False

    return bool(
        user.get("id")
    )


# =========================================================
# ROLE HELPERS
# =========================================================

def user_has_role(
    user: dict,
    role: str,
) -> bool:
    """
    Check whether an identity has a particular role.
    """

    if not isinstance(
        user,
        dict,
    ):
        return False

    roles = user.get(
        "roles",
        [],
    )

    if isinstance(
        roles,
        str,
    ):
        roles = [roles]

    target = str(
        role
    ).strip()

    return target in {
        str(item).strip()
        for item in roles
        if item
    }


def user_has_any_role(
    user: dict,
    *roles: str,
) -> bool:
    """
    Check whether the user has at least one of the
    supplied roles.
    """

    return any(
        user_has_role(
            user,
            role,
        )
        for role in roles
    )


# =========================================================
# SAFE IDENTITY
# =========================================================

def public_identity(
    user: dict,
) -> dict:
    """
    Return only identity information safe to expose to
    frontend clients.

    Never expose internal authentication fields here.
    """

    normalized = normalize_user(
        user
    )

    return {
        "id": normalized.get(
            "id"
        ),
        "full_name": normalized.get(
            "full_name",
            "",
        ),
        "contact": normalized.get(
            "contact",
            "",
        ),
        "email": normalized.get(
            "email",
            "",
        ),
        "role": normalized.get(
            "role",
            "user",
        ),
        "roles": normalized.get(
            "roles",
            [],
        ),
        "verified": normalized.get(
            "verified",
            False,
        ),
    }