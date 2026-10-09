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

from backend.jumuiya.elimu import school_verification

# =========================================================
# ELIMU SUB-MODULE BLUEPRINTS
# =========================================================

from backend.jumuiya.elimu.reports.routes import reports_bp
from backend.jumuiya.elimu.staff.routes import staff_bp
from backend.jumuiya.elimu.timetable.routes import timetable_bp
from backend.jumuiya.elimu.automation.routes import automation_bp
from backend.jumuiya.elimu.sync.routes import sync_bp


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


def query_value(name, default=None):
    value = request.args.get(name)

    if value is None:
        return default

    value = value.strip()

    return value if value else default


# =========================================================
# SCHOOL ACCESS GUARD
# =========================================================


def require_school_account(fn):
    """
    Hard Elimu access boundary.

    Authenticated users without an active school account are
    blocked from school-management resources with the canonical
    `school_required` error.

    Android can use /access or /bootstrap for internal
    navigation to the school setup screen.
    """

    @wraps(fn)
    @require_authenticated
    def wrapped(*args, **kwargs):
        services.require_school(
            current_user_id()
        )

        return fn(*args, **kwargs)

    return wrapped


# =========================================================
# HEALTH
# =========================================================


@elimu_bp.get("/health")
def health():
    return ok({
        "hub": "elimu",
        "status": "online",
        "version": services.ELIMU_VERSION,
        "architecture": "school-first",
        "access_model": "active_school_account_required",
        "client_mode": "android_native",
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
            "calendar",
            "reports",
            "staff",
            "timetable",
            "automation",
            "sync",
            "curriculum_configuration",
            "exam_report_cards",
            "class_report_cards",
            "report_publication",
            "post_exam_programmes",
            "print_center",
            "print_ready_documents",
            "apk_bootstrap",
        ],
    })


# =========================================================
# ACCESS / APK BOOTSTRAP
# =========================================================


@elimu_bp.get("/access")
@require_authenticated
def access():
    return ok(
        services.access(
            current_user_id()
        )
    )


@elimu_bp.get("/bootstrap")
@require_authenticated
def bootstrap():
    """
    Single startup request for the Android/Web Elimu entry point.

    The client must not guess whether the user is a school account.

    The service is the source of truth and returns either:

        allowed=true
            -> open Elimu dashboard

        allowed=false
            -> navigate internally to elimu-school-setup
    """

    return ok(
        services.hub_bootstrap(
            current_user_id()
        )
    )


# =========================================================
# SCHOOL REGISTRATION
# =========================================================

@elimu_bp.get("/school")
@require_authenticated
def get_school():
    return ok(
        school_verification.get_my_application(
            current_user_id()
        )
    )


@elimu_bp.post("/school")
@require_authenticated
def save_school():
    payload = validate(
        schemas.school_application_payload,
        body(),
    )

    return created(
        school_verification.submit_application(
            current_user_id(),
            payload,
        ),
        "School application submitted for verification.",
    )


@elimu_bp.post("/school/demo")
@require_authenticated
def create_demo_school():
    # The server permits this only when both demo-mode environment
    # requirements are satisfied.
    payload = validate(
        schemas.school_payload,
        body(),
    )

    return created(
        school_verification.create_demo_school(
            current_user_id(),
            payload,
        ),
        "Development demo school created.",
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
            class_name=query_value("class_name"),
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
    payload = body()

    return ok(
        services.update_student(
            current_user_id(),
            student_id,
            payload,
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
            query_value("subject"),
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
            query_value("class_name"),
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
            student_id=query_value("student_id"),
            class_name=query_value("class_name"),
            start_date=query_value("start_date"),
            end_date=query_value("end_date"),
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
            student_id=query_value("student_id"),
            class_name=query_value("class_name"),
            subject=query_value("subject"),
            academic_year=query_value("academic_year"),
            term=query_value("term"),
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
            status=query_value("status"),
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
# SCHOOL EVENTS / CALENDAR
# =========================================================


@elimu_bp.get("/events")
@require_school_account
def get_events():
    return ok(
        services.events(
            current_user_id(),
            year=query_value("year"),
            event_type=query_value("event_type"),
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


@elimu_bp.get("/calendar")
@require_school_account
def get_calendar():
    return ok(
        services.calendar(
            current_user_id(),
            year=query_value("year"),
        )
    )


# =========================================================
# SUB-MODULE REGISTRATION
# =========================================================
#
# Elimu is the parent blueprint.
#
# Each major subsystem owns its own routes:
#
#   reports
#   staff
#   timetable
#   automation
#   sync
#
# This keeps the main Elimu routes.py from becoming the
# implementation owner for every subsystem.
#
# If the application registers elimu_bp under:
#
#   /api/jumuiya/elimu
#
# the resulting routes become:
#
#   /api/jumuiya/elimu/reports/...
#   /api/jumuiya/elimu/staff/...
#   /api/jumuiya/elimu/timetable/...
#   /api/jumuiya/elimu/automation/...
#   /api/jumuiya/elimu/sync/...
#
# =========================================================

elimu_bp.register_blueprint(reports_bp)

elimu_bp.register_blueprint(staff_bp)

elimu_bp.register_blueprint(timetable_bp)

elimu_bp.register_blueprint(automation_bp)

elimu_bp.register_blueprint(sync_bp)

elimu_bp.register_blueprint(verification_bp)