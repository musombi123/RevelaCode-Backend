# backend/jumuiya/elimu/models.py

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# =========================================================
# ELIMU MODEL CONTRACT
# =========================================================
#
# MongoDB document factories for the Elimu school-management hub.
#
# Design goals:
#   - Preserve existing collection field names.
#   - Add professional v4 metadata without breaking v3 records.
#   - Keep ownership identifiers server-controlled.
#   - Store denormalized display fields where reports need fast reads.
#   - Support native Android reporting/printing contracts.
#   - Use safe defaults for older clients and partially populated data.
# =========================================================

ELIMU_SCHEMA_VERSION = "4.0"

DEFAULT_COUNTRY = "Kenya"
DEFAULT_CURRENCY = "KES"
DEFAULT_TIMEZONE = "Africa/Nairobi"


# =========================================================
# STATUS CONTRACTS
# =========================================================

SCHOOL_STATUS_ACTIVE = "active"

STUDENT_STATUSES = {
    "active",
    "inactive",
    "graduated",
    "transferred",
    "suspended",
}

CLASS_STATUSES = {
    "active",
    "inactive",
    "archived",
}

LESSON_STATUSES = {
    "draft",
    "published",
    "archived",
}

ASSIGNMENT_STATUSES = {
    "active",
    "completed",
    "archived",
}

ATTENDANCE_STATUSES = {
    "present",
    "absent",
    "late",
    "excused",
}

FEE_STATUSES = {
    "pending",
    "paid",
    "partial",
    "waived",
    "overdue",
}

CBC_STATUSES = {
    "active",
    "completed",
    "archived",
}

EVENT_STATUSES = {
    "scheduled",
    "ongoing",
    "completed",
    "cancelled",
}


# =========================================================
# TIME
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


# =========================================================
# HELPERS
# =========================================================

def _text(value: Any, default=""):
    if value is None:
        return default
    return str(value).strip()


def _list(value):
    if not isinstance(value, list):
        return []

    return list(value)


def _dict(value):
    if not isinstance(value, dict):
        return {}

    return dict(value)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_bool(value, default=False):
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    if isinstance(value, (int, float)):
        return bool(value)

    return default


def _status(value, allowed, default):
    value = _text(value, default).lower()

    if value not in allowed:
        return default

    return value


def _student_snapshot(student):
    """
    Server-derived student identity used by attendance, assessment,
    fee and CBC documents.
    """
    return {
        "student_id": (
            str(student["_id"])
            if student.get("_id") is not None
            else ""
        ),
        "student_user_id": _text(
            student.get("student_user_id")
        ),
        "student_name": _text(
            student.get("full_name")
        ),
        "admission_number": _text(
            student.get("admission_number")
        ),
        "class_name": _text(
            student.get("class_name")
        ),
    }


def _report_branding(data):
    branding = _dict(
        data.get("report_branding")
    )

    return {
        "logo_url": _text(
            branding.get(
                "logo_url",
                data.get("logo_url", ""),
            )
        ),
        "primary_color": _text(
            branding.get("primary_color")
        ),
        "secondary_color": _text(
            branding.get("secondary_color")
        ),
        "footer_text": _text(
            branding.get("footer_text")
        ),
        "watermark": _text(
            branding.get("watermark")
        ),
        "header_text": _text(
            branding.get("header_text")
        ),
        "show_motto": _safe_bool(
            branding.get("show_motto"),
            True,
        ),
        "show_contact": _safe_bool(
            branding.get("show_contact"),
            True,
        ),
    }


def _school_settings(data):
    settings = _dict(
        data.get("settings")
    )

    paper = _text(
        settings.get(
            "default_report_paper",
            "A4",
        )
    ).lower()

    if paper == "a4":
        paper = "A4"
    elif paper == "a5":
        paper = "A5"
    elif paper == "letter":
        paper = "Letter"
    else:
        paper = "A4"

    orientation = _text(
        settings.get(
            "default_report_orientation",
            "portrait",
        )
    ).lower()

    if orientation not in {
        "portrait",
        "landscape",
    }:
        orientation = "portrait"

    return {
        "allow_parent_access": _safe_bool(
            settings.get(
                "allow_parent_access"
            ),
            False,
        ),
        "enable_notifications": _safe_bool(
            settings.get(
                "enable_notifications"
            ),
            True,
        ),
        "enable_print_center": _safe_bool(
            settings.get(
                "enable_print_center"
            ),
            True,
        ),
        "default_report_paper": paper,
        "default_report_orientation": orientation,
        "show_signatures": _safe_bool(
            settings.get(
                "show_signatures"
            ),
            True,
        ),
        "include_generated_at": _safe_bool(
            settings.get(
                "include_generated_at"
            ),
            True,
        ),
    }


# =========================================================
# SCHOOL
# =========================================================

def school_document(
    user_id,
    data,
):
    now = now_utc()

    branding = _report_branding(data)
    settings = _school_settings(data)

    logo_url = _text(
        data.get(
            "logo_url",
            branding.get("logo_url", ""),
        )
    )

    if not branding.get("logo_url"):
        branding["logo_url"] = logo_url

    return {
        # -------------------------------------------------
        # DOCUMENT META
        # -------------------------------------------------

        "schema_version": ELIMU_SCHEMA_VERSION,

        # -------------------------------------------------
        # OWNERSHIP
        # -------------------------------------------------

        "owner_user_id": str(user_id),

        # -------------------------------------------------
        # SCHOOL IDENTITY
        # -------------------------------------------------

        "name": _text(
            data.get("name")
        ),

        "code": _text(
            data.get("code")
        ),

        "registration_number": _text(
            data.get("registration_number")
        ),

        "description": _text(
            data.get("description")
        ),

        "school_type": _text(
            data.get(
                "school_type",
                "primary",
            )
        ) or "primary",

        "motto": _text(
            data.get("motto")
        ),

        "mission": _text(
            data.get("mission")
        ),

        "vision": _text(
            data.get("vision")
        ),

        # -------------------------------------------------
        # LEADERSHIP
        # -------------------------------------------------

        "principal_name": _text(
            data.get("principal_name")
        ),

        "administrator_name": _text(
            data.get("administrator_name")
        ),

        # -------------------------------------------------
        # CONTACT
        # -------------------------------------------------

        "phone": _text(
            data.get("phone")
        ),

        "email": _text(
            data.get("email")
        ),

        "website": _text(
            data.get("website")
        ),

        "postal_address": _text(
            data.get("postal_address")
        ),

        # -------------------------------------------------
        # LOCATION
        # -------------------------------------------------

        "location": _text(
            data.get("location")
        ),

        "county": _text(
            data.get("county")
        ),

        "town": _text(
            data.get("town")
        ),

        "country": (
            _text(
                data.get(
                    "country",
                    DEFAULT_COUNTRY,
                )
            )
            or DEFAULT_COUNTRY
        ),

        "timezone": (
            _text(
                data.get(
                    "timezone",
                    DEFAULT_TIMEZONE,
                )
            )
            or DEFAULT_TIMEZONE
        ),

        # -------------------------------------------------
        # BRANDING
        # -------------------------------------------------

        "logo_url": logo_url,

        "report_branding": branding,

        # -------------------------------------------------
        # ACADEMIC SETTINGS
        # -------------------------------------------------

        "academic_year": _text(
            data.get("academic_year")
        ),

        "current_term": _text(
            data.get("current_term")
        ),

        "calendar_year": _text(
            data.get("calendar_year")
        ),

        # -------------------------------------------------
        # FINANCIAL / LOCALIZATION
        # -------------------------------------------------

        "currency": (
            _text(
                data.get(
                    "currency",
                    DEFAULT_CURRENCY,
                )
            ).upper()
            or DEFAULT_CURRENCY
        ),

        # -------------------------------------------------
        # SETTINGS
        # -------------------------------------------------

        "settings": settings,

        # -------------------------------------------------
        # STATUS
        # -------------------------------------------------

        "status": SCHOOL_STATUS_ACTIVE,

        # -------------------------------------------------
        # AUDIT
        # -------------------------------------------------

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# EDUCATION PROFILE
# =========================================================

def education_profile_document(
    user_id,
    data,
):
    now = now_utc()

    school_id = data.get(
        "school_id"
    )

    return {
        "schema_version": ELIMU_SCHEMA_VERSION,

        "user_id": str(user_id),

        "profile_type": (
            _text(
                data.get(
                    "profile_type",
                    "school_admin",
                )
            )
            or "school_admin"
        ),

        "role": (
            _text(
                data.get(
                    "role",
                    "school_admin",
                )
            )
            or "school_admin"
        ),

        "full_name": _text(
            data.get("full_name")
        ),

        "phone": _text(
            data.get("phone")
        ),

        "email": _text(
            data.get("email")
        ),

        "school_id": (
            str(school_id)
            if school_id
            else None
        ),

        "class_name": _text(
            data.get("class_name")
        ),

        "admission_number": _text(
            data.get("admission_number")
        ),

        "county": _text(
            data.get("county")
        ),

        "town": _text(
            data.get("town")
        ),

        "permissions": _list(
            data.get("permissions")
        ),

        "status": "active",

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# CLASS
# =========================================================

def class_document(
    school_id,
    data,
):
    now = now_utc()

    return {
        "schema_version": ELIMU_SCHEMA_VERSION,

        "school_id": str(
            school_id
        ),

        "name": _text(
            data.get("name")
        ),

        "code": _text(
            data.get("code")
        ),

        "level": _text(
            data.get("level")
        ),

        "stream": _text(
            data.get("stream")
        ),

        "academic_year": _text(
            data.get("academic_year")
        ),

        "teacher_id": (
            _text(
                data.get("teacher_id")
            )
            or None
        ),

        "teacher_name": _text(
            data.get("teacher_name")
        ),

        "capacity": (
            _safe_int(
                data.get("capacity")
            )
            if data.get("capacity") is not None
            else None
        ),

        "status": _status(
            data.get("status"),
            CLASS_STATUSES,
            "active",
        ),

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# STUDENT
# =========================================================

def student_document(
    school_id,
    data,
):
    now = now_utc()

    student_user_id = (
        _text(
            data.get("student_user_id")
        )
        or None
    )

    class_id = (
        _text(
            data.get("class_id")
        )
        or None
    )

    return {
        "schema_version": ELIMU_SCHEMA_VERSION,

        "school_id": str(
            school_id
        ),

        "student_user_id": student_user_id,

        "admission_number": _text(
            data.get(
                "admission_number"
            )
        ),

        "student_code": _text(
            data.get("student_code")
        ),

        "full_name": _text(
            data.get("full_name")
        ),

        "gender": _text(
            data.get("gender")
        ),

        "date_of_birth": _text(
            data.get("date_of_birth")
        ),

        "class_id": class_id,

        "class_name": _text(
            data.get("class_name")
        ),

        "stream": _text(
            data.get("stream")
        ),

        "enrollment_date": _text(
            data.get("enrollment_date")
        ),

        "leaving_date": _text(
            data.get("leaving_date")
        ),

        "guardian_name": _text(
            data.get("guardian_name")
        ),

        "guardian_phone": _text(
            data.get("guardian_phone")
        ),

        "guardian_email": _text(
            data.get("guardian_email")
        ),

        "county": _text(
            data.get("county")
        ),

        "town": _text(
            data.get("town")
        ),

        "address": _text(
            data.get("address")
        ),

        "status": _status(
            data.get("status"),
            STUDENT_STATUSES,
            "active",
        ),

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# LESSON
# =========================================================

def lesson_document(
    user_id,
    school_id,
    data,
):
    now = now_utc()

    published = _safe_bool(
        data.get("published"),
        False,
    )

    status = _status(
        data.get("status"),
        LESSON_STATUSES,
        "draft" if not published else "published",
    )

    if published:
        status = "published"

    return {
        "schema_version": ELIMU_SCHEMA_VERSION,

        "author_user_id": str(user_id),

        "school_id": str(
            school_id
        ),

        "subject": _text(
            data.get("subject")
        ),

        "title": _text(
            data.get("title")
        ),

        "description": _text(
            data.get("description")
        ),

        "class_name": _text(
            data.get("class_name")
        ),

        "academic_year": _text(
            data.get("academic_year")
        ),

        "term": _text(
            data.get("term")
        ),

        "content": _text(
            data.get("content")
        ),

        "materials": _list(
            data.get("materials")
        ),

        "published": published or status == "published",

        "status": status,

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# ASSIGNMENT
# =========================================================

def assignment_document(
    user_id,
    school_id,
    data,
):
    now = now_utc()

    return {
        "schema_version": ELIMU_SCHEMA_VERSION,

        "teacher_user_id": str(user_id),

        "school_id": str(
            school_id
        ),

        "class_name": _text(
            data.get("class_name")
        ),

        "subject": _text(
            data.get("subject")
        ),

        "title": _text(
            data.get("title")
        ),

        "description": _text(
            data.get("description")
        ),

        "due_date": _text(
            data.get("due_date")
        ) or None,

        "academic_year": _text(
            data.get("academic_year")
        ),

        "term": _text(
            data.get("term")
        ),

        "max_score": (
            _safe_float(
                data.get("max_score")
            )
            if data.get("max_score") is not None
            else None
        ),

        "status": _status(
            data.get("status"),
            ASSIGNMENT_STATUSES,
            "active",
        ),

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# ATTENDANCE
# =========================================================

def attendance_document(
    user_id,
    school_id,
    student,
    data,
):
    now = now_utc()
    snapshot = _student_snapshot(
        student
    )

    return {
        "schema_version": ELIMU_SCHEMA_VERSION,

        "school_id": str(
            school_id
        ),

        "student_id": snapshot[
            "student_id"
        ],

        "student_name": snapshot[
            "student_name"
        ],

        "admission_number": snapshot[
            "admission_number"
        ],

        "class_name": snapshot[
            "class_name"
        ],

        "date": _text(
            data.get("date")
        ),

        "status": _status(
            data.get("status"),
            ATTENDANCE_STATUSES,
            "present",
        ),

        "reason": _text(
            data.get("reason")
        ),

        "notes": _text(
            data.get("notes")
        ),

        "marked_by": str(user_id),

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# ASSESSMENT
# =========================================================

def assessment_document(
    user_id,
    school_id,
    student,
    data,
):
    now = now_utc()
    snapshot = _student_snapshot(
        student
    )

    score = data.get(
        "score"
    )

    max_score = data.get(
        "max_score",
        100,
    )

    percentage = None

    if (
        score is not None
        and max_score
    ):
        try:
            percentage = round(
                (
                    float(score)
                    / float(max_score)
                )
                * 100,
                2,
            )
        except (
            TypeError,
            ValueError,
            ZeroDivisionError,
        ):
            percentage = None

    return {
        "schema_version": ELIMU_SCHEMA_VERSION,

        "school_id": str(
            school_id
        ),

        "student_id": snapshot[
            "student_id"
        ],

        "student_name": snapshot[
            "student_name"
        ],

        "admission_number": snapshot[
            "admission_number"
        ],

        "class_name": snapshot[
            "class_name"
        ],

        "subject": _text(
            data.get("subject")
        ),

        "assessment_name": _text(
            data.get("assessment_name")
        ),

        "assessment_type": (
            _text(
                data.get(
                    "assessment_type",
                    "assessment",
                )
            )
            or "assessment"
        ),

        "academic_year": _text(
            data.get("academic_year")
        ),

        "term": _text(
            data.get("term")
        ),

        "assessment_date": _text(
            data.get("assessment_date")
        ),

        "score": score,

        "max_score": max_score,

        "percentage": percentage,

        "grade": _text(
            data.get("grade")
        ),

        "competency_level": _text(
            data.get("competency_level")
        ),

        "remarks": _text(
            data.get("remarks")
        ),

        "recorded_by": str(user_id),

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# FEE
# =========================================================

def fee_document(
    user_id,
    data,
):
    now = now_utc()

    school_id = data.get(
        "school_id"
    )

    amount = max(
        0.0,
        _safe_float(
            data.get("amount"),
            0.0,
        ),
    )

    amount_paid = max(
        0.0,
        min(
            _safe_float(
                data.get("amount_paid"),
                0.0,
            ),
            amount,
        ),
    )

    balance = round(
        max(
            amount - amount_paid,
            0.0,
        ),
        2,
    )

    status = _status(
        data.get("status"),
        FEE_STATUSES,
        "pending",
    )

    if amount > 0 and balance == 0:
        status = "paid"
    elif amount_paid > 0 and balance > 0:
        status = "partial"

    student_id = data.get(
        "student_id"
    )

    return {
        "schema_version": ELIMU_SCHEMA_VERSION,

        "student_user_id": (
            _text(
                data.get(
                    "student_user_id"
                )
            )
            or None
        ),

        "student_id": (
            str(student_id)
            if student_id
            else None
        ),

        "student_name": _text(
            data.get("student_name")
        ),

        "admission_number": _text(
            data.get("admission_number")
        ),

        "class_name": _text(
            data.get("class_name")
        ),

        "school_id": (
            str(school_id)
            if school_id
            else None
        ),

        "created_by": str(
            user_id
        ),

        "amount": amount,

        "amount_paid": amount_paid,

        "balance": balance,

        "currency": (
            _text(
                data.get(
                    "currency",
                    DEFAULT_CURRENCY,
                )
            ).upper()
            or DEFAULT_CURRENCY
        ),

        "description": _text(
            data.get("description")
        ),

        "fee_type": _text(
            data.get("fee_type")
        ),

        "term": _text(
            data.get("term")
        ),

        "academic_year": _text(
            data.get("academic_year")
        ),

        "due_date": _text(
            data.get("due_date")
        ) or None,

        "payment_reference": _text(
            data.get("payment_reference")
        ),

        "status": status,

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# CBC PROJECT
# =========================================================

def cbc_project_document(
    user_id,
    data,
):
    now = now_utc()

    school_id = data.get(
        "school_id"
    )

    student_id = data.get(
        "student_id"
    )

    student_user_id = (
        _text(
            data.get("student_user_id")
        )
        or None
    )

    return {
        "schema_version": ELIMU_SCHEMA_VERSION,

        "student_user_id": student_user_id,

        "student_id": (
            str(student_id)
            if student_id
            else None
        ),

        "student_name": _text(
            data.get("student_name")
        ),

        "admission_number": _text(
            data.get("admission_number")
        ),

        "class_name": _text(
            data.get("class_name")
        ),

        "teacher_user_id": str(
            user_id
        ),

        "school_id": (
            str(school_id)
            if school_id
            else None
        ),

        "title": _text(
            data.get("title")
        ),

        "description": _text(
            data.get("description")
        ),

        "category": _text(
            data.get("category")
        ),

        "skills": _list(
            data.get("skills")
        ),

        "materials": _list(
            data.get("materials")
        ),

        "status": _status(
            data.get("status"),
            CBC_STATUSES,
            "active",
        ),

        "remarks": _text(
            data.get("remarks")
        ),

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# SCHOOL EVENT
# =========================================================

def event_document(
    user_id,
    school_id,
    data,
):
    now = now_utc()

    is_annual = _safe_bool(
        data.get("is_annual"),
        False,
    )

    recurrence = _dict(
        data.get("recurrence")
    )

    if not recurrence:
        recurrence = {
            "type": (
                "annual"
                if is_annual
                else "none"
            ),
            "interval": 1,
            "weekdays": [],
            "day_of_month": None,
            "month": None,
            "until": "",
        }

    recurrence_type = _text(
        recurrence.get(
            "type",
            "annual" if is_annual else "none",
        )
    ).lower()

    if not recurrence_type:
        recurrence_type = (
            "annual"
            if is_annual
            else "none"
        )

    return {
        "schema_version": ELIMU_SCHEMA_VERSION,

        "school_id": str(
            school_id
        ),

        "created_by": str(
            user_id
        ),

        "title": _text(
            data.get("title")
        ),

        "event_type": (
            _text(
                data.get(
                    "event_type",
                    "school",
                )
            )
            or "school"
        ),

        "description": _text(
            data.get("description")
        ),

        "start_date": _text(
            data.get("start_date")
        ),

        "end_date": (
            _text(
                data.get("end_date")
            )
            or _text(
                data.get("start_date")
            )
        ),

        "location": _text(
            data.get("location")
        ),

        "organizer": _text(
            data.get("organizer")
        ),

        "academic_year": _text(
            data.get("academic_year")
        ),

        "term": _text(
            data.get("term")
        ),

        "is_annual": is_annual,

        "recurrence": {
            "type": recurrence_type,
            "interval": max(
                1,
                _safe_int(
                    recurrence.get(
                        "interval",
                        1,
                    ),
                    1,
                ),
            ),
            "weekdays": _list(
                recurrence.get(
                    "weekdays"
                )
            ),
            "day_of_month": (
                _safe_int(
                    recurrence.get(
                        "day_of_month"
                    )
                )
                if recurrence.get(
                    "day_of_month"
                )
                is not None
                else None
            ),
            "month": (
                _safe_int(
                    recurrence.get(
                        "month"
                    )
                )
                if recurrence.get(
                    "month"
                )
                is not None
                else None
            ),
            "until": _text(
                recurrence.get("until")
            ),
        },

        "visibility": (
            _text(
                data.get(
                    "visibility",
                    "school",
                )
            ).lower()
            or "school"
        ),

        "all_day": _safe_bool(
            data.get("all_day"),
            False,
        ),

        "reminder_minutes": max(
            0,
            _safe_int(
                data.get(
                    "reminder_minutes"
                ),
                0,
            ),
        ),

        "calendar_year": (
            _text(
                data.get("calendar_year")
            )
            or _text(
                data.get("academic_year")
            )
            or _text(
                data.get("start_date")
            )[:4]
        ),

        "color": _text(
            data.get("color")
        ),

        "status": _status(
            data.get("status"),
            EVENT_STATUSES,
            "scheduled",
        ),

        "created_at": now,

        "updated_at": now,
    }
