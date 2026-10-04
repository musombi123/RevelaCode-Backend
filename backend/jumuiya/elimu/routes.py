# backend/jumuiya/elimu/routes.py

from __future__ import annotations

from functools import wraps

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

from backend.jumuiya.elimu import (
    schemas,
    services,
)


# =========================================================
# BLUEPRINT
# =========================================================

elimu_bp = Blueprint(
    "jumuiya_elimu",
    __name__,
)


# =========================================================
# REQUEST HELPERS
# =========================================================

def body():
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
    fn,
    data,
):
    try:
        return fn(data)
    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "validation_error",
        )


# =========================================================
# SCHOOL ACCESS GUARD
# =========================================================

def require_school_account(fn):
    """
    Every real Elimu management endpoint passes through this
    guard.

    A user without an active school account receives:

        403
        school_required

    The APK can use that response to redirect internally to:

        elimu-school-setup
    """

    @wraps(fn)
    @require_authenticated
    def wrapped(*args, **kwargs):

        services.require_school(
            current_user_id()
        )

        return fn(
            *args,
            **kwargs
        )

    return wrapped


# =========================================================
# HEALTH
# =========================================================

@elimu_bp.get("/health")
def health():
    return ok({
        "hub": "elimu",
        "status": "online",
        "version": "3.0",
        "architecture": "school-first",
        "features": [
            "school_accounts",
            "students",
            "classes",
            "attendance",
            "assessments",
            "lessons",
            "assignments",
            "fees",
            "cbc",
            "annual_events",
            "reports",
            "print_ready_documents",
        ],
    })


# =========================================================
# ACCESS
# =========================================================

@elimu_bp.get("/access")
@require_authenticated
def access():
    return ok(
        services.access(
            current_user_id()
        )
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
def save_school():
    payload = validate(
        schemas.school_payload,
        body(),
    )

    return created(
        services.save_school(
            current_user_id(),
            payload,
        ),
        "School account saved.",
    )


# =========================================================
# PROFILE
# =========================================================

@elimu_bp.get("/profile")
@require_school_account
def get_profile():
    return ok(
        services.get_profile(
            current_user_id()
        )
    )


@elimu_bp.post("/profile")
@require_school_account
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
# DASHBOARD
# =========================================================

@elimu_bp.get("/dashboard")
@require_school_account
def get_dashboard():
    return ok(
        services.dashboard(
            current_user_id()
        )
    )


# =========================================================
# CLASSES
# =========================================================

@elimu_bp.get("/classes")
@require_school_account
def get_classes():
    return ok(
        services.list_classes(
            current_user_id()
        )
    )


@elimu_bp.post("/classes")
@require_school_account
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
# STUDENTS
# =========================================================

@elimu_bp.get("/students")
@require_school_account
def get_students():
    return ok(
        services.students(
            current_user_id(),
            class_name=request.args.get(
                "class_name"
            ),
        )
    )


@elimu_bp.post("/students")
@require_school_account
def add_student():
    payload = validate(
        schemas.student_payload,
        body(),
    )

    return created(
        services.create_student(
            current_user_id(),
            payload,
        ),
        "Student created.",
    )


@elimu_bp.get("/students/<student_id>")
@require_school_account
def get_student(student_id):
    return ok(
        services.get_student(
            current_user_id(),
            student_id,
        )
    )


@elimu_bp.put("/students/<student_id>")
@require_school_account
def edit_student(student_id):
    return ok(
        services.update_student(
            current_user_id(),
            student_id,
            body(),
        ),
        "Student updated.",
    )


# =========================================================
# LESSONS
# =========================================================

@elimu_bp.get("/lessons")
@require_school_account
def get_lessons():
    return ok(
        services.lessons(
            current_user_id(),
            request.args.get(
                "subject"
            ),
        )
    )


@elimu_bp.post("/lessons")
@require_school_account
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
@require_school_account
def get_assignments():
    return ok(
        services.assignments(
            current_user_id(),
            request.args.get(
                "class_name"
            ),
        )
    )


@elimu_bp.post("/assignments")
@require_school_account
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
# ATTENDANCE
# =========================================================

@elimu_bp.get("/attendance")
@require_school_account
def get_attendance():
    return ok(
        services.attendance(
            current_user_id(),
            student_id=request.args.get(
                "student_id"
            ),
            class_name=request.args.get(
                "class_name"
            ),
            start_date=request.args.get(
                "start_date"
            ),
            end_date=request.args.get(
                "end_date"
            ),
        )
    )


@elimu_bp.post("/attendance")
@require_school_account
def add_attendance():
    payload = validate(
        schemas.attendance_payload,
        body(),
    )

    return created(
        services.mark_attendance(
            current_user_id(),
            payload,
        ),
        "Attendance recorded.",
    )


# =========================================================
# ASSESSMENTS
# =========================================================

@elimu_bp.get("/assessments")
@require_school_account
def get_assessments():
    return ok(
        services.assessments(
            current_user_id(),
            student_id=request.args.get(
                "student_id"
            ),
            class_name=request.args.get(
                "class_name"
            ),
            subject=request.args.get(
                "subject"
            ),
            academic_year=request.args.get(
                "academic_year"
            ),
            term=request.args.get(
                "term"
            ),
        )
    )


@elimu_bp.post("/assessments")
@require_school_account
def add_assessment():
    payload = validate(
        schemas.assessment_payload,
        body(),
    )

    return created(
        services.create_assessment(
            current_user_id(),
            payload,
        ),
        "Assessment recorded.",
    )


# =========================================================
# FEES
# =========================================================

@elimu_bp.get("/fees")
@require_school_account
def get_fees():
    return ok(
        services.student_fees(
            current_user_id(),
            status=request.args.get(
                "status"
            ),
        )
    )


@elimu_bp.post("/fees")
@require_school_account
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
@require_school_account
def get_projects():
    return ok(
        services.student_projects(
            current_user_id()
        )
    )


@elimu_bp.post("/cbc/projects")
@require_school_account
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
# ANNUAL EVENTS
# =========================================================

@elimu_bp.get("/events")
@require_school_account
def get_events():
    return ok(
        services.events(
            current_user_id(),
            year=request.args.get(
                "year"
            ),
            event_type=request.args.get(
                "event_type"
            ),
        )
    )


@elimu_bp.post("/events")
@require_school_account
def add_event():
    payload = validate(
        schemas.event_payload,
        body(),
    )

    return created(
        services.create_event(
            current_user_id(),
            payload,
        ),
        "School event created.",
    )


@elimu_bp.put("/events/<event_id>")
@require_school_account
def edit_event(event_id):
    return ok(
        services.update_event(
            current_user_id(),
            event_id,
            body(),
        ),
        "School event updated.",
    )


@elimu_bp.delete("/events/<event_id>")
@require_school_account
def remove_event(event_id):
    return ok(
        services.delete_event(
            current_user_id(),
            event_id,
        ),
        "School event cancelled.",
    )


# =========================================================
# REPORT CENTER
# =========================================================

@elimu_bp.get("/reports/catalog")
@require_school_account
def reports_catalog():
    return ok(
        services.report_catalog(
            current_user_id()
        )
    )


@elimu_bp.get("/reports/school")
@require_school_account
def report_school():
    return ok(
        services.school_report(
            current_user_id()
        )
    )


@elimu_bp.get(
    "/reports/student/<student_id>"
)
@require_school_account
def report_student(student_id):
    return ok(
        services.student_report(
            current_user_id(),
            student_id,
            academic_year=request.args.get(
                "academic_year"
            ),
            term=request.args.get(
                "term"
            ),
        )
    )


@elimu_bp.get(
    "/reports/class/<path:class_name>"
)
@require_school_account
def report_class(class_name):
    return ok(
        services.class_report(
            current_user_id(),
            class_name,
            academic_year=request.args.get(
                "academic_year"
            ),
            term=request.args.get(
                "term"
            ),
        )
    )


@elimu_bp.get("/reports/attendance")
@require_school_account
def report_attendance():
    return ok(
        services.attendance_report(
            current_user_id(),
            start_date=request.args.get(
                "start_date"
            ),
            end_date=request.args.get(
                "end_date"
            ),
        )
    )


@elimu_bp.get("/reports/fees")
@require_school_account
def report_fees():
    return ok(
        services.fees_report(
            current_user_id(),
            status=request.args.get(
                "status"
            ),
        )
    )


@elimu_bp.get("/reports/events")
@require_school_account
def report_events():
    return ok(
        services.events_report(
            current_user_id(),
            year=request.args.get(
                "year"
            ),
        )
    )
