# backend/jumuiya/elimu/staff/routes.py

from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import (
    current_user_id,
    require_authenticated,
)
from backend.jumuiya.core.responses import (
    created,
    ok,
)

from . import schemas, services


# =========================================================
# BLUEPRINT
# =========================================================

staff_bp = Blueprint(
    "jumuiya_elimu_staff",
    __name__,
    url_prefix="/staff",
)


# =========================================================
# REQUEST HELPERS
# =========================================================

def body() -> dict:
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


def validate(
    validator,
    data,
):
    try:
        return validator(
            data
        )
    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "validation_error",
        )


def query_value(
    name: str,
    default: str | None = None,
) -> str | None:
    value = request.args.get(
        name
    )

    if value is None:
        return default

    value = value.strip()

    return (
        value
        if value
        else default
    )


# =========================================================
# STAFF DIRECTORY
# =========================================================

@staff_bp.get("")
@require_authenticated
def list_staff():
    """
    List active/present staff memberships for the
    authenticated user's Elimu school.
    """

    return ok(
        services.list_staff(
            current_user_id()
        )
    )


@staff_bp.get("/<user_id>")
@require_authenticated
def get_staff(
    user_id: str,
):
    """
    Get one staff member by RevelaCode user ID.

    School scope and permission checks are performed
    inside the service layer.
    """

    return ok(
        services.get_staff(
            current_user_id(),
            user_id,
        )
    )


# =========================================================
# STAFF INVITATIONS
# =========================================================

@staff_bp.post("/invite")
@require_authenticated
def invite():
    """
    Create either:
      - a direct school-user link, or
      - an email invitation.
    """

    payload = validate(
        schemas.invite_payload,
        body(),
    )

    return created(
        services.invite_staff(
            current_user_id(),
            payload,
        ),
        "Staff invitation created.",
    )


@staff_bp.post("/invitations/accept")
@require_authenticated
def accept():
    """
    Accept a staff invitation using the invitation token.
    """

    payload = validate(
        schemas.accept_payload,
        body(),
    )

    return ok(
        services.accept_invitation(
            current_user_id(),
            payload["token"],
        ),
        "School staff invitation accepted.",
    )


# =========================================================
# STAFF MANAGEMENT
# =========================================================

@staff_bp.put("/<user_id>")
@require_authenticated
def update(
    user_id: str,
):
    """
    Update role, permissions, class scope or staff status.

    The service layer determines whether the authenticated
    user has the required staff.update permission.
    """

    payload = validate(
        schemas.update_payload,
        body(),
    )

    return ok(
        services.update_staff(
            current_user_id(),
            user_id,
            payload,
        ),
        "Staff member updated.",
    )


@staff_bp.delete("/<user_id>")
@require_authenticated
def remove(
    user_id: str,
):
    """
    Soft-remove a staff membership.

    Teacher assignments are deactivated by the service layer.
    """

    return ok(
        services.remove_staff(
            current_user_id(),
            user_id,
        ),
        "Staff member removed.",
    )


# =========================================================
# TEACHER ASSIGNMENTS
# =========================================================

@staff_bp.get("/assignments/list")
@require_authenticated
def assignments():
    """
    List teacher/class assignments.

    Owners/Registrars can request a specific teacher.
    Teachers are restricted by the service layer to their
    own assignments.
    """

    teacher_user_id = query_value(
        "teacher_user_id"
    )

    return ok(
        services.list_assignments(
            current_user_id(),
            teacher_user_id,
        )
    )


@staff_bp.post("/assignments")
@require_authenticated
def assignment():
    """
    Assign a teacher to a school class and optionally
    define the subjects they teach.
    """

    payload = validate(
        schemas.assignment_payload,
        body(),
    )

    return created(
        services.assign_teacher(
            current_user_id(),
            payload,
        ),
        "Teacher assignment saved.",
    )