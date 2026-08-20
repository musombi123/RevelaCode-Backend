# backend/jumuiya/identity/routes.py

from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import (
    require_authenticated,
    current_user,
    current_user_id,
)
from backend.jumuiya.core.responses import ok

from backend.jumuiya.identity import services


# =========================================================
# BLUEPRINT
# =========================================================

identity_bp = Blueprint(
    "jumuiya_identity",
    __name__,
)


# =========================================================
# HELPERS
# =========================================================

def json_body():
    """
    Require a valid JSON object for profile updates.
    """

    data = request.get_json(
        silent=True
    )

    if not isinstance(
        data,
        dict,
    ):
        raise APIError(
            "JSON request body is required.",
            400,
            "invalid_json",
        )

    return data


# =========================================================
# CURRENT USER
# =========================================================

@identity_bp.get("/me")
@require_authenticated
def me():
    """
    Return the authenticated RevelaCode account together
    with its Jumuiya ecosystem profile.
    """

    user = current_user()

    return ok({
        "account": user,
        "profile": services.profile(user),
    })


# =========================================================
# UPDATE PROFILE
# =========================================================

@identity_bp.put("/profile")
@require_authenticated
def update_profile():
    """
    Update the authenticated user's Jumuiya profile.
    """

    user_id = current_user_id()

    data = json_body()

    profile = services.update_profile(
        user_id,
        data,
    )

    return ok(
        profile,
        "Profile updated.",
    )