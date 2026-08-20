# backend/jumuiya/core/permissions.py

from __future__ import annotations

from functools import wraps

from flask import g

from backend.jumuiya.core.errors import APIError


# =========================================================
# CURRENT USER
# =========================================================

def current_user():
    """
    Return the authenticated Jumuiya user.

    The integration/auth bridge is responsible for placing
    the authenticated user into:

        g.jumuiya_user
    """

    user = getattr(
        g,
        "jumuiya_user",
        None,
    )

    if not user:

        raise APIError(
            "Authentication is required.",
            401,
            "authentication_required",
        )

    if not isinstance(user, dict):

        raise APIError(
            "Invalid authenticated identity.",
            401,
            "invalid_identity",
        )

    return user


# =========================================================
# AUTHENTICATED DECORATOR
# =========================================================

def require_authenticated(fn):
    """
    Require a valid authenticated Jumuiya identity.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):

        current_user()

        return fn(
            *args,
            **kwargs,
        )

    return wrapper


# =========================================================
# USER ID
# =========================================================

def current_user_id():
    """
    Return the authenticated user's ID as a string.

    Supports the identity formats already used by
    RevelaCode's authentication system.
    """

    user = current_user()

    value = (
        user.get("id")
        or user.get("_id")
        or user.get("user_id")
    )

    if value is None:

        raise APIError(
            "Authenticated user has no usable ID.",
            401,
            "invalid_identity",
        )

    return str(value)


# =========================================================
# USER PHONE
# =========================================================

def current_user_phone():
    """
    Return the authenticated user's phone number.

    Useful for:
        - M-Pesa
        - notifications
        - marketplace communication
        - future OTP flows
    """

    user = current_user()

    value = (
        user.get("phone")
        or user.get("phone_number")
        or user.get("mobile")
    )

    if not value:
        return None

    return str(value)


# =========================================================
# USER EMAIL
# =========================================================

def current_user_email():
    """
    Return the authenticated user's email.
    """

    user = current_user()

    value = user.get("email")

    if not value:
        return None

    return str(value)


# =========================================================
# USER ROLES
# =========================================================

def current_user_roles():
    """
    Return the authenticated user's roles as a set.

    Supports both:

        {
            "role": "business_owner"
        }

    and:

        {
            "roles": [
                "business_owner",
                "seller"
            ]
        }
    """

    user = current_user()

    roles = user.get("roles")

    if roles is None:

        role = user.get("role")

        if role:
            roles = [role]

        else:
            roles = []

    elif isinstance(roles, str):

        roles = [roles]

    elif not isinstance(roles, (list, tuple, set)):

        roles = []

    return {
        str(role).strip()
        for role in roles
        if role
    }


# =========================================================
# HAS ROLE
# =========================================================

def has_role(role):
    """
    Check whether the current user has a specific role.
    """

    return str(role) in current_user_roles()


# =========================================================
# REQUIRE ROLES
# =========================================================

def require_roles(*allowed_roles):
    """
    Require the authenticated user to have at least one
    of the supplied roles.

    Example:

        @require_roles(
            "admin",
            "business_owner"
        )
    """

    allowed = {
        str(role).strip()
        for role in allowed_roles
        if role
    }

    if not allowed:

        raise ValueError(
            "require_roles() requires at least one role."
        )

    def decorator(fn):

        @wraps(fn)
        def wrapper(*args, **kwargs):

            roles = current_user_roles()

            if not roles.intersection(
                allowed
            ):

                raise APIError(
                    "You do not have permission to perform this action.",
                    403,
                    "forbidden",
                )

            return fn(
                *args,
                **kwargs,
            )

        return wrapper

    return decorator


# =========================================================
# REQUIRE ALL ROLES
# =========================================================

def require_all_roles(*required_roles):
    """
    Require the user to have ALL supplied roles.

    This is useful for highly privileged operations.
    """

    required = {
        str(role).strip()
        for role in required_roles
        if role
    }

    if not required:

        raise ValueError(
            "require_all_roles() requires at least one role."
        )

    def decorator(fn):

        @wraps(fn)
        def wrapper(*args, **kwargs):

            roles = current_user_roles()

            if not required.issubset(
                roles
            ):

                raise APIError(
                    "You do not have sufficient permissions.",
                    403,
                    "forbidden",
                )

            return fn(
                *args,
                **kwargs,
            )

        return wrapper

    return decorator