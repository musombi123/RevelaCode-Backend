from flask import Blueprint, request

from backend.jumuiya.core.permissions import (
    require_authenticated,
    current_user_id,
)

from backend.jumuiya.core.responses import ok, created
from backend.jumuiya.core.errors import APIError

from backend.jumuiya.elimu import schemas, services


elimu_bp = Blueprint(
    "jumuiya_elimu",
    __name__,
)


def body():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        raise APIError(
            "JSON request body is required.",
            400,
            "invalid_json",
        )

    return data


def validate(fn, data):
    try:
        return fn(data)
    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "validation_error",
        )


# =========================================================
# HEALTH
# =========================================================

@elimu_bp.get("/health")
def health():
    return ok({
        "hub": "elimu",
        "status": "online",
    })


# =========================================================
# PROFILE
# =========================================================

@elimu_bp.get("/profile")
@require_authenticated
def get_profile():
    return ok(
        services.get_profile(
            current_user_id()
        )
    )


@elimu_bp.post("/profile")
@require_authenticated
def save_profile():
    payload = validate(
        schemas.education_profile_payload,
        body(),
    )

    return ok(
        services.save_profile(
            current_user_id(),
            payload,
        ),
        "Education profile saved.",
    )


# =========================================================
# SCHOOL
# =========================================================

@elimu_bp.get("/school")
@require_authenticated
def get_school():
    return ok(
        services.my_school(
            current_user_id()
        )
    )


@elimu_bp.post("/school")
@require_authenticated
def create_school():
    payload = validate(
        schemas.school_payload,
        body(),
    )

    return created(
        services.create_school(
            current_user_id(),
            payload,
        ),
        "School created.",
    )


# =========================================================
# CLASSES
# =========================================================

@elimu_bp.get("/classes")
@require_authenticated
def get_classes():
    return ok(
        services.list_classes(
            current_user_id()
        )
    )


@elimu_bp.post("/classes")
@require_authenticated
def add_class():
    payload = validate(
        schemas.class_payload,
        body(),
    )

    return created(
        services.create_class(
            current_user_id(),
            payload,
        ),
        "Class created.",
    )


# =========================================================
# LESSONS
# =========================================================

@elimu_bp.get("/lessons")
@require_authenticated
def get_lessons():
    return ok(
        services.lessons(
            current_user_id(),
            request.args.get("subject"),
        )
    )


@elimu_bp.post("/lessons")
@require_authenticated
def add_lesson():
    payload = validate(
        schemas.lesson_payload,
        body(),
    )

    return created(
        services.create_lesson(
            current_user_id(),
            payload,
        ),
        "Lesson created.",
    )


# =========================================================
# ASSIGNMENTS
# =========================================================

@elimu_bp.get("/assignments")
@require_authenticated
def get_assignments():
    return ok(
        services.assignments(
            current_user_id(),
            request.args.get("class_name"),
        )
    )


@elimu_bp.post("/assignments")
@require_authenticated
def add_assignment():
    payload = validate(
        schemas.assignment_payload,
        body(),
    )

    return created(
        services.create_assignment(
            current_user_id(),
            payload,
        ),
        "Assignment created.",
    )


# =========================================================
# FEES
# =========================================================

@elimu_bp.get("/fees")
@require_authenticated
def get_fees():
    return ok(
        services.student_fees(
            current_user_id()
        )
    )


@elimu_bp.post("/fees")
@require_authenticated
def add_fee():
    payload = validate(
        schemas.fee_payload,
        body(),
    )

    return created(
        services.create_fee(
            current_user_id(),
            payload,
        ),
        "Fee record created.",
    )


# =========================================================
# CBC
# =========================================================

@elimu_bp.get("/cbc/projects")
@require_authenticated
def get_projects():
    return ok(
        services.student_projects(
            current_user_id()
        )
    )


@elimu_bp.post("/cbc/projects")
@require_authenticated
def add_project():
    payload = validate(
        schemas.cbc_project_payload,
        body(),
    )

    return created(
        services.create_cbc_project(
            current_user_id(),
            payload,
        ),
        "CBC project created.",
    )


# =========================================================
# DASHBOARD
# =========================================================

@elimu_bp.get("/dashboard")
@require_authenticated
def get_dashboard():
    return ok(
        services.dashboard(
            current_user_id()
        )
    )