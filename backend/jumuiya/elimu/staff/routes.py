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
    List all non-removed staff members in the
    authenticated user's Elimu school.
    """

    return ok(
        services.list_staff(
            current_user_id()
        )
    )


@staff_bp.get("/me")
@require_authenticated
def get_my_staff_profile():
    """
    Return the authenticated user's Elimu staff profile.

    This is especially useful for teacher dashboards because
    the frontend can load the same Staff contract used by
    Timetable, Assignments and Reports.
    """

    user_id = current_user_id()

    return ok(
        services.get_staff(
            user_id,
            user_id,
        )
    )


# =========================================================
# TEACHER DIRECTORY
# =========================================================

@staff_bp.get("/teachers")
@require_authenticated
def list_teachers():
    """
    List active teachers for assignment and timetable UIs.

    The service layer applies school scope and authorization.
    """

    return ok(
        services.list_teachers(
            current_user_id()
        )
    )


# =========================================================
# TEACHER ASSIGNMENTS
# =========================================================
#
# These routes are intentionally placed BEFORE:
#
#     /<user_id>
#
# so static endpoints such as /assignments/list and
# /assignments are never interpreted as a staff user ID.
#
# =========================================================

@staff_bp.get("/assignments/list")
@require_authenticated
def assignments():
    """
    List teacher/class assignments.

    Owners and Registrars can request a specific teacher.
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
    Assign a teacher to a school class.

    Optional:
        subjects
        learning_area_ids
        status
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


@staff_bp.delete("/assignments")
@require_authenticated
def deactivate_assignment():
    """
    Deactivate an existing teacher/class assignment.

    Expected body:

        {
            "teacher_user_id": "...",
            "class_id": "..."
        }

    Existing assignment history is preserved; only the active
    relationship is disabled.
    """

    payload = validate(
        schemas.assignment_payload,
        body(),
    )

    return ok(
        services.deactivate_teacher_assignment(
            current_user_id(),
            payload[
                "teacher_user_id"
            ],
            payload[
                "class_id"
            ],
        ),
        "Teacher assignment deactivated.",
    )


# =========================================================
# STAFF INVITATIONS
# =========================================================

@staff_bp.post("/invite")
@require_authenticated
def invite():
    """
    Create either:

      1. a direct school-user link, or
      2. an email invitation.

    The service determines the school and authorized inviter.
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
            payload[
                "token"
            ],
        ),
        "School staff invitation accepted.",
    )


# =========================================================
# STAFF MAINTENANCE
# =========================================================

@staff_bp.post("/maintenance/rebuild-teacher-scopes")
@require_authenticated
def rebuild_teacher_scopes():
    """
    Rebuild all teacher assigned_class_ids values from the
    authoritative teacher-assignment collection.

    Useful after migration, synchronization or legacy data
    repair.
    """

    return ok(
        services.rebuild_teacher_scopes(
            current_user_id()
        ),
        "Teacher class scopes rebuilt.",
    )


# =========================================================
# STAFF MEMBER
# =========================================================

@staff_bp.get("/<user_id>")
@require_authenticated
def get_staff(
    user_id: str,
):
    """
    Get one staff member by RevelaCode user ID.

    School scope and authorization are enforced by the
    service layer.
    """

    return ok(
        services.get_staff(
            current_user_id(),
            user_id,
        )
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
    Update:

      - role
      - permissions
      - staff status
      - assigned class scope
      - identity
      - employment
      - teaching profile
      - timetable profile
      - reporting profile
      - metadata

    Protected identity fields are enforced by the service.
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