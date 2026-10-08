# backend/jumuiya/elimu/reports/routes.py

from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.permissions import current_user_id
from backend.jumuiya.core.responses import ok

from . import schemas
from . import services


# =========================================================
# BLUEPRINT
# =========================================================

reports_bp = Blueprint(
    "jumuiya_elimu_reports",
    __name__,
    url_prefix="/reports",
)


# =========================================================
# REQUEST HELPERS
# =========================================================

def _user_id() -> str:
    return current_user_id()


def _query_value(
    name: str,
) -> str | None:
    value = request.args.get(name)

    if value is None:
        return None

    value = value.strip()

    return value or None


def _json_body() -> dict:
    """
    Safely read a JSON request body.

    Schema validation remains responsible for checking
    required fields and payload structure.
    """
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return {}

    return payload


# =========================================================
# OVERVIEW
# =========================================================

@reports_bp.get("/overview")
def overview():
    return ok(
        services.overview(
            _user_id()
        )
    )


# =========================================================
# ATTENDANCE
# =========================================================

@reports_bp.get("/attendance")
def attendance():
    return ok(
        services.attendance(
            _user_id(),
            _query_value("start_date"),
            _query_value("end_date"),
        )
    )


# =========================================================
# FEES
# =========================================================

@reports_bp.get("/fees")
def fees():
    return ok(
        services.fees(
            _user_id(),
            _query_value("status"),
        )
    )


# =========================================================
# TIMETABLE
# =========================================================

@reports_bp.get("/timetable")
def timetable():
    return ok(
        services.timetable(
            _user_id()
        )
    )


# =========================================================
# DASHBOARD
# =========================================================

@reports_bp.get("/dashboard")
def dashboard():
    """
    Combined Elimu reporting payload for dashboard clients.
    """
    return ok(
        services.dashboard(
            _user_id()
        )
    )


# =========================================================
# SCHOOL CURRICULUM
# =========================================================
#
# A curriculum is the school's operational source of truth
# for which learning areas should appear on report cards.
#
# Example:
#   GET  /api/jumuiya/elimu/reports/curricula
#   POST /api/jumuiya/elimu/reports/curricula
#   GET  /api/jumuiya/elimu/reports/curricula/<id>
#
# =========================================================

@reports_bp.get("/curricula")
def curricula():
    return ok(
        services.curricula(
            _user_id(),
            education_level=_query_value("education_level"),
            grade=_query_value("grade"),
            academic_year=_query_value("academic_year"),
            term=_query_value("term"),
            status=_query_value("status"),
        )
    )


@reports_bp.post("/curricula")
def save_curriculum():
    payload = schemas.curriculum_payload(
        _json_body()
    )

    return ok(
        services.save_curriculum(
            _user_id(),
            payload,
        )
    )


@reports_bp.get("/curricula/<curriculum_id>")
def get_curriculum(curriculum_id: str):
    return ok(
        services.get_curriculum(
            _user_id(),
            curriculum_id,
        )
    )


# =========================================================
# EXAM REPORTS / REPORT CARDS
# =========================================================
#
# Individual learner:
#   POST /exam-reports/student
#
# Whole class:
#   POST /exam-reports/class
#
# Existing generated reports:
#   GET  /exam-reports
#   GET  /exam-reports/<report_id>
#
# Publish:
#   POST /exam-reports/<report_id>/publish
#
# =========================================================

@reports_bp.get("/exam-reports")
def exam_reports():
    """
    List generated student exam reports.

    Supported filters:
      student_id
      class_name
      academic_year
      term
      assessment_name
      status
    """
    return ok(
        services.exam_reports(
            _user_id(),
            student_id=_query_value("student_id"),
            class_name=_query_value("class_name"),
            academic_year=_query_value("academic_year"),
            term=_query_value("term"),
            assessment_name=_query_value("assessment_name"),
            status=_query_value("status"),
        )
    )


@reports_bp.post("/exam-reports/student")
def generate_student_exam_report():
    """
    Generate a complete report card for one learner.

    The service resolves the school's configured curriculum,
    loads the learner's assessment evidence, generates the
    CBC-first report, validates it, and persists it.
    """
    payload = schemas.exam_report_payload(
        _json_body()
    )

    return ok(
        services.generate_exam_report(
            _user_id(),
            payload,
        )
    )


@reports_bp.post("/exam-reports/class")
def generate_class_exam_reports():
    """
    Generate report cards for an entire class or an explicit
    set of student IDs.
    """
    payload = schemas.batch_exam_reports_payload(
        _json_body()
    )

    return ok(
        services.generate_class_reports(
            _user_id(),
            payload,
        )
    )


@reports_bp.get("/exam-reports/<report_id>")
def get_exam_report(report_id: str):
    return ok(
        services.get_exam_report(
            _user_id(),
            report_id,
        )
    )


@reports_bp.post("/exam-reports/<report_id>/publish")
def publish_exam_report(report_id: str):
    """
    Publish a generated report card so downstream clients
    such as the web dashboard, Android app, parent access,
    or printing layer can treat it as official.
    """
    return ok(
        services.publish_exam_report(
            _user_id(),
            report_id,
        )
    )


# =========================================================
# POST-EXAM SCHOOL PROGRAMMES
# =========================================================
#
# Generate:
#   POST /programmes
#
# List:
#   GET  /programmes
#
# Retrieve:
#   GET  /programmes/<programme_id>
#
# Publish:
#   POST /programmes/<programme_id>/publish
#
# =========================================================

@reports_bp.get("/programmes")
def programmes():
    """
    List generated school programmes.

    Supported filters:
      status
      academic_year
      term
    """
    return ok(
        services.programmes(
            _user_id(),
            status=_query_value("status"),
            academic_year=_query_value("academic_year"),
            term=_query_value("term"),
        )
    )


@reports_bp.post("/programmes")
def generate_programme():
    """
    Generate a post-exam school programme.

    The generator remains deterministic and server-side.
    AI can later suggest improvements, but it does not become
    the authority for the persisted programme.
    """
    payload = schemas.programme_payload(
        _json_body()
    )

    return ok(
        services.generate_programme(
            _user_id(),
            payload,
        )
    )


@reports_bp.get("/programmes/<programme_id>")
def get_programme(programme_id: str):
    return ok(
        services.get_programme(
            _user_id(),
            programme_id,
        )
    )


@reports_bp.post("/programmes/<programme_id>/publish")
def publish_programme(programme_id: str):
    """
    Publish a generated school programme.
    """
    return ok(
        services.publish_programme(
            _user_id(),
            programme_id,
        )
    )