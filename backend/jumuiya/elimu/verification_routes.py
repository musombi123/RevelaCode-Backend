
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


# Register this blueprint beneath the main Elimu blueprint.
#
# Parent prefix: /api/jumuiya/elimu
# This prefix:   /verification
#
# Resulting routes:
# GET  /api/jumuiya/elimu/verification/applications
# POST /api/jumuiya/elimu/verification/applications/<application_id>/review

verification_bp = Blueprint(
    "jumuiya_elimu_verification",
    __name__,
    url_prefix="/verification",
)

# Keep these synchronized with the canonical role names issued by
# RevelaCode's authentication and authorization layer.
PLATFORM_ADMIN_ROLES = (
    "admin",
    "platform_admin",
    "super_admin",
    "revelacode_admin",
)

DEFAULT_APPLICATION_LIMIT = 50
MAX_APPLICATION_LIMIT = 100
MAX_DECISION_LENGTH = 40
MAX_NOTES_LENGTH = 5000
MAX_CHECKS = 100


def _body() -> dict:
    """Read a JSON object or raise a consistent API validation error."""
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        raise APIError(
            "A valid JSON object request body is required.",
            400,
            "invalid_json",
        )

    return data


def _text_field(
    data: dict,
    field: str,
    *,
    required: bool = False,
    max_length: int | None = None,
    default: str = "",
) -> str:
    """Validate a text field without accepting numbers or other types."""
    value = data.get(field, default)

    if value is None:
        value = ""

    if not isinstance(value, str):
        raise APIError(
            f"{field} must be text.",
            422,
            "validation_error",
        )

    value = value.strip()

    if required and not value:
        raise APIError(
            f"{field} is required.",
            422,
            "validation_error",
        )

    if max_length is not None and len(value) > max_length:
        raise APIError(
            f"{field} must not exceed {max_length} characters.",
            422,
            "validation_error",
        )

    return value


def _checks_field(data: dict) -> dict:
    """Validate verification checks while leaving their domain schema to the service."""
    checks = data.get("checks", {})

    if not isinstance(checks, dict):
        raise APIError(
            "checks must be an object.",
            422,
            "validation_error",
        )

    if len(checks) > MAX_CHECKS:
        raise APIError(
            f"checks must not contain more than {MAX_CHECKS} entries.",
            422,
            "validation_error",
        )

    validated = {}

    for key, value in checks.items():
        if not isinstance(key, str) or not key.strip():
            raise APIError(
                "Each checks key must be a non-empty string.",
                422,
                "validation_error",
            )

        if len(key.strip()) > 100:
            raise APIError(
                "Each checks key must not exceed 100 characters.",
                422,
                "validation_error",
            )

        # Do not silently coerce values: the verification service
        # remains responsible for interpreting the check values.
        validated[key.strip()] = value

    return validated


@verification_bp.get("/applications")
@require_authenticated
@require_roles(*PLATFORM_ADMIN_ROLES)
def get_pending_applications():
    """
    List school verification applications for authorized platform admins.

    Query parameters:
        limit: integer from 1 to 100; defaults to 50.
    """
    raw_limit = request.args.get(
        "limit",
        str(DEFAULT_APPLICATION_LIMIT),
    )

    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        raise APIError(
            "limit must be a whole number.",
            422,
            "validation_error",
        )

    if not 1 <= limit <= MAX_APPLICATION_LIMIT:
        raise APIError(
            f"limit must be between 1 and {MAX_APPLICATION_LIMIT}.",
            422,
            "validation_error",
        )

    applications = school_verification.pending_applications(limit)

    return ok(applications)


@verification_bp.post("/applications/<application_id>/review")
@require_authenticated
@require_roles(*PLATFORM_ADMIN_ROLES)
def review_school_application(application_id: str):
    """
    Record a platform-admin decision on a school verification application.

    The domain service remains responsible for validating the application
    state and applying the decision consistently.
    """
    if not application_id or not application_id.strip():
        raise APIError(
            "application_id is required.",
            422,
            "validation_error",
        )

    data = _body()

    decision = _text_field(
        data,
        "decision",
        required=True,
        max_length=MAX_DECISION_LENGTH,
    )

    notes = _text_field(
        data,
        "notes",
        max_length=MAX_NOTES_LENGTH,
    )

    checks = _checks_field(data)

    reviewer_id = current_user_id()

    if reviewer_id is None:
        raise APIError(
            "Unable to identify the authenticated reviewer.",
            401,
            "authentication_required",
        )

    result = school_verification.review_application(
        reviewer_id,
        application_id.strip(),
        decision=decision,
        notes=notes,
        checks=checks,
    )

    return ok(
        result,
        "School verification decision recorded.",
    )