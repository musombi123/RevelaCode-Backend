# backend/jumuiya/elimu/verification_routes.py

from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import (
    current_user_id,
    require_authenticated,
    require_roles,
)
from backend.jumuiya.core.responses import ok
from backend.jumuiya.elimu import school_verification


verification_bp = Blueprint(
    "jumuiya_elimu_verification",
    __name__,
    url_prefix="/verification",
)


# Update these role names if RevelaCode's trusted platform-admin
# identities use different canonical role names.
PLATFORM_ADMIN_ROLES = (
    "admin",
    "platform_admin",
    "super_admin",
    "revelacode_admin",
)


def _body():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        raise APIError(
            "JSON request body is required.",
            400,
            "invalid_json",
        )

    return data


@verification_bp.get("/applications")
@require_authenticated
@require_roles(*PLATFORM_ADMIN_ROLES)
def get_pending_applications():
    raw_limit = request.args.get("limit", "50")

    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        raise APIError(
            "limit must be a whole number.",
            422,
            "validation_error",
        )

    return ok(
        school_verification.pending_applications(limit)
    )


@verification_bp.post("/applications/<application_id>/review")
@require_authenticated
@require_roles(*PLATFORM_ADMIN_ROLES)
def review_school_application(application_id):
    data = _body()

    decision = data.get("decision", "")
    notes = data.get("notes", "")
    checks = data.get("checks", {})

    if not isinstance(decision, str):
        raise APIError(
            "decision must be text.",
            422,
            "validation_error",
        )

    if not isinstance(notes, str):
        raise APIError(
            "notes must be text.",
            422,
            "validation_error",
        )

    if not isinstance(checks, dict):
        raise APIError(
            "checks must be an object.",
            422,
            "validation_error",
        )

    result = school_verification.review_application(
        current_user_id(),
        application_id,
        decision=decision,
        notes=notes,
        checks=checks,
    )

    return ok(
        result,
        "School verification decision recorded.",
    )