# backend/jumuiya/elimu/services.py

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError

from backend.jumuiya.elimu.models import (
    assessment_document,
    attendance_document,
    cbc_project_document,
    class_document,
    education_profile_document,
    event_document,
    fee_document,
    lesson_document,
    assignment_document,
    school_document,
    student_document,
)


# =========================================================
# COLLECTIONS
# =========================================================

SCHOOLS = "jumuiya_schools"
PROFILES = "jumuiya_education_profiles"
CLASSES = "jumuiya_classes"
STUDENTS = "jumuiya_students"
LESSONS = "jumuiya_lessons"
ASSIGNMENTS = "jumuiya_assignments"
FEES = "jumuiya_fees"
CBC = "jumuiya_cbc_projects"
ATTENDANCE = "jumuiya_attendance"
ASSESSMENTS = "jumuiya_assessments"
EVENTS = "jumuiya_school_events"


# =========================================================
# ELIMU CONTRACT / STATUS CONSTANTS
# =========================================================

ELIMU_VERSION = "4.0"
REPORT_SCHEMA_VERSION = "1.0"
DEFAULT_COUNTRY = "Kenya"
DEFAULT_CURRENCY = "KES"
DEFAULT_TIMEZONE = "Africa/Nairobi"

SCHOOL_STATUSES = {"active", "suspended", "archived"}
STUDENT_STATUSES = {
    "active",
    "inactive",
    "graduated",
    "transferred",
    "suspended",
}
EVENT_STATUSES = {"scheduled", "ongoing", "completed", "cancelled"}
ATTENDANCE_STATUSES = {"present", "late", "absent", "excused"}



# =========================================================
# TIME
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


# =========================================================
# SERIALIZATION
# =========================================================

def _ser_value(value):
    if isinstance(
        value,
        ObjectId,
    ):
        return str(value)

    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key): _ser_value(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        list,
    ):
        return [
            _ser_value(item)
            for item in value
        ]

    return value


def _ser(doc):
    if not doc:
        return None

    output = dict(doc)

    if "_id" in output:
        output["id"] = str(
            output.pop("_id")
        )

    return _ser_value(
        output
    )


def _many(docs):
    return [
        _ser(doc)
        for doc in docs
    ]


# =========================================================
# IDS
# =========================================================

def _oid(value):
    try:
        return ObjectId(
            str(value)
        )
    except (
        InvalidId,
        TypeError,
        ValueError,
    ):
        raise APIError(
            "Invalid resource ID.",
            400,
            "invalid_id",
        )


# =========================================================
# NORMALIZATION / SAFETY HELPERS
# =========================================================

def _text(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def _lower(value, default=""):
    value = _text(value, default)
    return value.lower() if value else default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _school_id(school):
    return str(school["_id"])


def _normalize_school_payload(data):
    """Create a safe, additive school update contract."""
    payload = dict(data or {})
    payload.pop("_id", None)
    payload.pop("owner_user_id", None)

    payload.setdefault("country", DEFAULT_COUNTRY)
    payload.setdefault("currency", DEFAULT_CURRENCY)
    payload.setdefault("timezone", DEFAULT_TIMEZONE)
    payload.setdefault("schema_version", ELIMU_VERSION)

    branding = payload.get("report_branding")
    if not isinstance(branding, dict):
        branding = {}

    payload["report_branding"] = {
        "logo_url": branding.get("logo_url", payload.get("logo_url", "")),
        "primary_color": branding.get("primary_color", ""),
        "secondary_color": branding.get("secondary_color", ""),
        "footer_text": branding.get("footer_text", ""),
        "watermark": branding.get("watermark", ""),
        **branding,
    }

    settings = payload.get("settings")
    if not isinstance(settings, dict):
        settings = {}

    payload["settings"] = {
        "allow_parent_access": settings.get("allow_parent_access", False),
        "enable_notifications": settings.get("enable_notifications", True),
        "enable_print_center": settings.get("enable_print_center", True),
        "default_report_paper": settings.get("default_report_paper", "A4"),
        "default_report_orientation": settings.get(
            "default_report_orientation",
            "portrait",
        ),
        **settings,
    }

    return payload


def _normalize_event_payload(data):
    """Normalize event metadata while remaining compatible with old records."""
    payload = dict(data or {})
    annual = _safe_bool(payload.get("is_annual"), False)

    recurrence = payload.get("recurrence")
    if not isinstance(recurrence, dict):
        recurrence = {
            "type": "annual" if annual else "none"
        }
    else:
        recurrence = {
            "type": _lower(
                recurrence.get(
                    "type",
                    "annual" if annual else "none",
                ),
                "annual" if annual else "none",
            ),
            **recurrence,
        }

    payload["is_annual"] = annual
    payload["recurrence"] = recurrence
    payload.setdefault("visibility", "school")
    payload.setdefault("all_day", False)
    payload.setdefault("reminder_minutes", 0)
    payload.setdefault(
        "calendar_year",
        _text(payload.get("academic_year")),
    )
    payload.setdefault("schema_version", ELIMU_VERSION)

    return payload






def _next_events(school_id, limit=5):
    today = now_utc().date().isoformat()

    docs = (
        collection(EVENTS)
        .find(
            {
                "school_id": str(school_id),
                "status": {"$ne": "cancelled"},
                "start_date": {"$gte": today},
            }
        )
        .sort("start_date", 1)
        .limit(limit)
    )

    return _many(docs)


# =========================================================
# SCHOOL ACCOUNT
# =========================================================

def my_school(
    user_id,
):
    return _ser(
        collection(
            SCHOOLS
        ).find_one(
            {
                "owner_user_id": str(
                    user_id
                ),
                "status": "active",
            }
        )
    )


def _school_document(
    user_id,
):
    school = collection(
        SCHOOLS
    ).find_one(
        {
            "owner_user_id": str(
                user_id
            ),
            "status": "active",
        }
    )

    if not school:
        raise APIError(
            "A school account is required to access the Elimu hub.",
            403,
            "school_required",
        )

    return school


def require_school(
    user_id,
):
    """
    Hard Elimu access boundary.

    The user must own an active school account.
    """

    school = _school_document(
        user_id
    )

    return _ser(
        school
    )


def access(
    user_id,
):
    school = collection(
        SCHOOLS
    ).find_one(
        {
            "owner_user_id": str(
                user_id
            ),
            "status": "active",
        }
    )

    if school:

        return {
            "allowed": True,
            "has_school": True,
            "school": _ser(
                school
            ),
            "redirect": None,
        }

    return {
        "allowed": False,
        "has_school": False,
        "school": None,
        "reason": "school_required",
        "redirect": {
            "screen": "elimu-school-setup",
            "mode": "create",
        },
    }


# =========================================================
# SCHOOL
# =========================================================

def save_school(
    user_id,
    data,
):
    uid = str(
        user_id
    )

    now = now_utc()
    data = _normalize_school_payload(data)

    existing = collection(
        SCHOOLS
    ).find_one(
        {
            "owner_user_id": uid
        }
    )

    if existing:

        document = collection(
            SCHOOLS
        ).find_one_and_update(
            {
                "_id": existing["_id"],
                "owner_user_id": uid,
            },
            {
                "$set": {
                    **data,
                    "owner_user_id": uid,
                    "updated_at": now,
                    "status": "active",
                }
            },
            return_document=ReturnDocument.AFTER,
        )

        log_action(
            uid,
            "elimu.school.updated",
            "school",
            document["_id"],
        )

        return _ser(
            document
        )

    document = school_document(
        uid,
        data,
    )

    result = collection(
        SCHOOLS
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    log_action(
        uid,
        "elimu.school.created",
        "school",
        result.inserted_id,
    )

    return _ser(
        document
    )


# =========================================================
# EDUCATION PROFILE
# =========================================================

def get_profile(
    user_id,
):
    _school_document(
        user_id
    )

    doc = collection(
        PROFILES
    ).find_one(
        {
            "user_id": str(
                user_id
            )
        }
    )

    return _ser(
        doc
    )


def save_profile(
    user_id,
    data,
):
    school = _school_document(
        user_id
    )

    uid = str(
        user_id
    )

    now = now_utc()

    update = {
        **data,
        "user_id": uid,
        "school_id": str(
            school["_id"]
        ),
        "updated_at": now,
        "status": "active",
    }

    doc = collection(
        PROFILES
    ).find_one_and_update(
        {
            "user_id": uid
        },
        {
            "$set": update,
            "$setOnInsert": {
                "created_at": now
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    log_action(
        uid,
        "elimu.profile.updated",
        "education_profile",
        doc["_id"],
    )

    return _ser(
        doc
    )


# =========================================================
# CLASSES
# =========================================================

def create_class(
    user_id,
    data,
):
    school = _school_document(
        user_id
    )

    document = class_document(
        school["_id"],
        data,
    )

    result = collection(
        CLASSES
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    log_action(
        user_id,
        "elimu.class.created",
        "class",
        result.inserted_id,
        {
            "school_id": str(
                school["_id"]
            )
        },
    )

    return _ser(
        document
    )


def list_classes(
    user_id,
):
    school = _school_document(
        user_id
    )

    docs = (
        collection(CLASSES)
        .find(
            {
                "school_id": str(
                    school["_id"]
                ),
                "status": "active",
            }
        )
        .sort(
            [
                ("level", 1),
                ("name", 1),
            ]
        )
    )

    return _many(
        docs
    )


# =========================================================
# STUDENTS
# =========================================================

def create_student(
    user_id,
    data,
):
    school = _school_document(
        user_id
    )

    admission_number = str(
        data["admission_number"]
    ).strip()

    duplicate = collection(
        STUDENTS
    ).find_one(
        {
            "school_id": str(
                school["_id"]
            ),
            "admission_number": admission_number,
        }
    )

    if duplicate:
        raise APIError(
            "A student with this admission number already exists.",
            409,
            "student_exists",
        )

    class_id = data.get(
        "class_id"
    )

    if class_id:

        class_doc = collection(
            CLASSES
        ).find_one(
            {
                "_id": _oid(
                    class_id
                ),
                "school_id": str(
                    school["_id"]
                ),
                "status": "active",
            }
        )

        if not class_doc:
            raise APIError(
                "Class does not belong to this school.",
                403,
                "class_access_denied",
            )

        data = {
            **data,
            "class_name": class_doc.get(
                "name",
                data.get(
                    "class_name",
                    "",
                ),
            ),
        }

    document = student_document(
        school["_id"],
        data,
    )

    result = collection(
        STUDENTS
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    log_action(
        user_id,
        "elimu.student.created",
        "student",
        result.inserted_id,
    )

    return _ser(
        document
    )


def students(
    user_id,
    class_name=None,
):
    school = _school_document(
        user_id
    )

    query = {
        "school_id": str(
            school["_id"]
        ),
        "status": "active",
    }

    if class_name:
        query["class_name"] = str(
            class_name
        ).strip()

    docs = (
        collection(STUDENTS)
        .find(query)
        .sort(
            [
                ("class_name", 1),
                ("full_name", 1),
            ]
        )
    )

    return _many(
        docs
    )


def get_student(
    user_id,
    student_id,
):
    school = _school_document(
        user_id
    )

    doc = collection(
        STUDENTS
    ).find_one(
        {
            "_id": _oid(
                student_id
            ),
            "school_id": str(
                school["_id"]
            ),
        }
    )

    if not doc:
        raise APIError(
            "Student not found.",
            404,
            "student_not_found",
        )

    return _ser(
        doc
    )


def update_student(
    user_id,
    student_id,
    data,
):
    school = _school_document(
        user_id
    )

    school_id = _school_id(school)
    student_oid = _oid(student_id)

    existing = collection(
        STUDENTS
    ).find_one(
        {
            "_id": student_oid,
            "school_id": school_id,
        }
    )

    if not existing:
        raise APIError(
            "Student not found.",
            404,
            "student_not_found",
        )

    allowed = {
        "admission_number",
        "full_name",
        "gender",
        "date_of_birth",
        "class_id",
        "class_name",
        "guardian_name",
        "guardian_phone",
        "guardian_email",
        "county",
        "town",
        "address",
        "status",
        "student_code",
        "stream",
        "enrollment_date",
        "leaving_date",
    }

    update = {
        key: value
        for key, value in data.items()
        if key in allowed
    }

    if not update:
        raise APIError(
            "No valid student fields were supplied.",
            422,
            "validation_error",
        )

    if "admission_number" in update:
        admission_number = _text(
            update["admission_number"]
        )

        if not admission_number:
            raise APIError(
                "Admission number cannot be empty.",
                422,
                "validation_error",
            )

        duplicate = collection(
            STUDENTS
        ).find_one(
            {
                "_id": {"$ne": student_oid},
                "school_id": school_id,
                "admission_number": admission_number,
            }
        )

        if duplicate:
            raise APIError(
                "A student with this admission number already exists.",
                409,
                "student_exists",
            )

        update["admission_number"] = admission_number

    if update.get("class_id"):
        target_class = collection(
            CLASSES
        ).find_one(
            {
                "_id": _oid(update["class_id"]),
                "school_id": school_id,
                "status": "active",
            }
        )

        if not target_class:
            raise APIError(
                "Class does not belong to this school.",
                403,
                "class_access_denied",
            )

        update["class_id"] = str(
            target_class["_id"]
        )
        update["class_name"] = target_class.get(
            "name",
            update.get(
                "class_name",
                existing.get(
                    "class_name",
                    "",
                ),
            ),
        )

    elif "class_name" in update:
        class_name = _text(
            update["class_name"]
        )

        if class_name:
            target_class = collection(
                CLASSES
            ).find_one(
                {
                    "school_id": school_id,
                    "name": class_name,
                    "status": "active",
                }
            )

            if not target_class:
                raise APIError(
                    "Class does not belong to this school.",
                    403,
                    "class_access_denied",
                )

            update["class_id"] = str(
                target_class["_id"]
            )
            update["class_name"] = target_class.get(
                "name",
                class_name,
            )

    if "status" in update:
        status = _lower(
            update["status"]
        )

        if status not in STUDENT_STATUSES:
            raise APIError(
                "Invalid student status.",
                422,
                "validation_error",
            )

        update["status"] = status

    update["updated_at"] = now_utc()

    doc = collection(
        STUDENTS
    ).find_one_and_update(
        {
            "_id": student_oid,
            "school_id": school_id,
        },
        {
            "$set": update
        },
        return_document=ReturnDocument.AFTER,
    )

    if not doc:
        raise APIError(
            "Student not found.",
            404,
            "student_not_found",
        )

    log_action(
        user_id,
        "elimu.student.updated",
        "student",
        doc["_id"],
    )

    return _ser(
        doc
    )



# =========================================================
# LESSONS
# =========================================================

def create_lesson(
    user_id,
    data,
):
    school = _school_document(
        user_id
    )

    document = lesson_document(
        user_id,
        school["_id"],
        data,
    )

    result = collection(
        LESSONS
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    log_action(
        user_id,
        "elimu.lesson.created",
        "lesson",
        result.inserted_id,
    )

    return _ser(
        document
    )


def lessons(
    user_id,
    subject=None,
):
    school = _school_document(
        user_id
    )

    query = {
        "school_id": str(
            school["_id"]
        )
    }

    if subject:
        query["subject"] = str(
            subject
        ).strip()

    docs = (
        collection(LESSONS)
        .find(query)
        .sort(
            "created_at",
            -1,
        )
    )

    return _many(
        docs
    )


# =========================================================
# ASSIGNMENTS
# =========================================================

def create_assignment(
    user_id,
    data,
):
    school = _school_document(
        user_id
    )

    document = assignment_document(
        user_id,
        school["_id"],
        data,
    )

    result = collection(
        ASSIGNMENTS
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    log_action(
        user_id,
        "elimu.assignment.created",
        "assignment",
        result.inserted_id,
    )

    return _ser(
        document
    )


def assignments(
    user_id,
    class_name=None,
):
    school = _school_document(
        user_id
    )

    query = {
        "school_id": str(
            school["_id"]
        )
    }

    if class_name:
        query["class_name"] = str(
            class_name
        ).strip()

    docs = (
        collection(ASSIGNMENTS)
        .find(query)
        .sort(
            "created_at",
            -1,
        )
    )

    return _many(
        docs
    )


# =========================================================
# ATTENDANCE
# =========================================================

def mark_attendance(
    user_id,
    data,
):
    school = _school_document(
        user_id
    )

    student = collection(
        STUDENTS
    ).find_one(
        {
            "_id": _oid(
                data["student_id"]
            ),
            "school_id": str(
                school["_id"]
            ),
            "status": "active",
        }
    )

    if not student:
        raise APIError(
            "Student not found in this school.",
            404,
            "student_not_found",
        )

    query = {
        "school_id": str(
            school["_id"]
        ),
        "student_id": str(
            student["_id"]
        ),
        "date": data["date"],
    }

    document = attendance_document(
        user_id,
        school["_id"],
        student,
        data,
    )

    result = collection(
        ATTENDANCE
    ).find_one_and_update(
        query,
        {
            "$set": document
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    log_action(
        user_id,
        "elimu.attendance.marked",
        "attendance",
        result["_id"],
        {
            "student_id": str(
                student["_id"]
            ),
            "date": data["date"],
        },
    )

    return _ser(
        result
    )


def attendance(
    user_id,
    *,
    student_id=None,
    class_name=None,
    start_date=None,
    end_date=None,
):
    school = _school_document(
        user_id
    )

    query = {
        "school_id": str(
            school["_id"]
        )
    }

    if student_id:
        query["student_id"] = str(
            student_id
        )

    if class_name:
        query["class_name"] = str(
            class_name
        ).strip()

    if start_date or end_date:

        date_query = {}

        if start_date:
            date_query["$gte"] = start_date

        if end_date:
            date_query["$lte"] = end_date

        query["date"] = date_query

    docs = (
        collection(ATTENDANCE)
        .find(query)
        .sort(
            [
                ("date", -1),
                ("student_name", 1),
            ]
        )
    )

    return _many(
        docs
    )


# =========================================================
# ASSESSMENTS
# =========================================================

def create_assessment(
    user_id,
    data,
):
    school = _school_document(
        user_id
    )

    student = collection(
        STUDENTS
    ).find_one(
        {
            "_id": _oid(
                data["student_id"]
            ),
            "school_id": str(
                school["_id"]
            ),
            "status": "active",
        }
    )

    if not student:
        raise APIError(
            "Student not found in this school.",
            404,
            "student_not_found",
        )

    document = assessment_document(
        user_id,
        school["_id"],
        student,
        data,
    )

    result = collection(
        ASSESSMENTS
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    log_action(
        user_id,
        "elimu.assessment.created",
        "assessment",
        result.inserted_id,
        {
            "student_id": str(
                student["_id"]
            ),
            "subject": data[
                "subject"
            ],
        },
    )

    return _ser(
        document
    )


def assessments(
    user_id,
    *,
    student_id=None,
    class_name=None,
    subject=None,
    academic_year=None,
    term=None,
):
    school = _school_document(
        user_id
    )

    query = {
        "school_id": str(
            school["_id"]
        )
    }

    if student_id:
        query["student_id"] = str(
            student_id
        )

    if class_name:
        query["class_name"] = str(
            class_name
        ).strip()

    if subject:
        query["subject"] = str(
            subject
        ).strip()

    if academic_year:
        query["academic_year"] = str(
            academic_year
        ).strip()

    if term:
        query["term"] = str(
            term
        ).strip()

    docs = (
        collection(ASSESSMENTS)
        .find(query)
        .sort(
            [
                ("created_at", -1),
                ("student_name", 1),
            ]
        )
    )

    return _many(
        docs
    )


# =========================================================
# FEES
# =========================================================

def create_fee(
    user_id,
    data,
):
    school = _school_document(
        user_id
    )
    school_id = _school_id(school)

    payload = {
        **data,
        "school_id": school_id,
    }

    if data.get("student_id"):
        student = collection(
            STUDENTS
        ).find_one(
            {
                "_id": _oid(
                    data["student_id"]
                ),
                "school_id": school_id,
            }
        )

        if not student:
            raise APIError(
                "Student does not belong to this school.",
                403,
                "student_access_denied",
            )

        payload["student_id"] = str(
            student["_id"]
        )
        payload["student_user_id"] = student.get(
            "student_user_id",
            "",
        )
        payload["student_name"] = student.get(
            "full_name",
            "",
        )
        payload["admission_number"] = student.get(
            "admission_number",
            "",
        )
        payload["class_name"] = student.get(
            "class_name",
            "",
        )

    amount = _safe_float(
        payload.get("amount"),
        0.0,
    )
    amount_paid = _safe_float(
        payload.get("amount_paid"),
        0.0,
    )
    amount_paid = max(
        0.0,
        min(
            amount_paid,
            amount,
        ),
    )

    payload["amount"] = amount
    payload["amount_paid"] = amount_paid
    payload["balance"] = round(
        max(
            amount - amount_paid,
            0.0,
        ),
        2,
    )

    if payload["balance"] == 0 and amount > 0:
        payload["status"] = "paid"
    elif amount_paid > 0:
        payload["status"] = "partial"
    else:
        payload.setdefault(
            "status",
            "pending",
        )

    document = fee_document(
        user_id,
        payload,
    )

    # Additive accounting fields keep old model deployments compatible.
    document["amount"] = amount
    document["amount_paid"] = amount_paid
    document["balance"] = round(
        max(
            amount - amount_paid,
            0.0,
        ),
        2,
    )
    document.setdefault(
        "currency",
        payload.get(
            "currency",
            DEFAULT_CURRENCY,
        ),
    )
    document.setdefault(
        "status",
        payload.get(
            "status",
            "pending",
        ),
    )

    result = collection(
        FEES
    ).insert_one(
        document
    )

    document["_id"] = result.inserted_id

    log_action(
        user_id,
        "elimu.fee.created",
        "fee",
        result.inserted_id,
    )

    return _ser(
        document
    )



def student_fees(
    user_id,
    status=None,
):
    school = _school_document(
        user_id
    )

    query = {
        "school_id": str(
            school["_id"]
        )
    }

    if status:
        query["status"] = str(
            status
        ).strip().lower()

    docs = (
        collection(FEES)
        .find(query)
        .sort(
            "created_at",
            -1,
        )
    )

    return _many(
        docs
    )


# =========================================================
# CBC PROJECTS
# =========================================================

def create_cbc_project(
    user_id,
    data,
):
    school = _school_document(
        user_id
    )
    school_id = _school_id(school)

    payload = {
        **data,
        "school_id": school_id,
        "teacher_user_id": str(user_id),
    }

    if data.get("student_id"):
        student = collection(
            STUDENTS
        ).find_one(
            {
                "_id": _oid(
                    data["student_id"]
                ),
                "school_id": school_id,
            }
        )

        if not student:
            raise APIError(
                "Student does not belong to this school.",
                403,
                "student_access_denied",
            )

        payload["student_id"] = str(
            student["_id"]
        )
        payload["student_user_id"] = student.get(
            "student_user_id",
            "",
        )
        payload["student_name"] = student.get(
            "full_name",
            "",
        )
        payload["admission_number"] = student.get(
            "admission_number",
            "",
        )
        payload["class_name"] = student.get(
            "class_name",
            "",
        )

    document = cbc_project_document(
        user_id,
        payload,
    )

    document.setdefault(
        "school_id",
        school_id,
    )
    document.setdefault(
        "teacher_user_id",
        str(user_id),
    )

    result = collection(
        CBC
    ).insert_one(
        document
    )

    document["_id"] = result.inserted_id

    log_action(
        user_id,
        "elimu.cbc.project.created",
        "cbc_project",
        result.inserted_id,
    )

    return _ser(
        document
    )



def student_projects(
    user_id,
):
    school = _school_document(
        user_id
    )

    docs = (
        collection(CBC)
        .find(
            {
                "school_id": str(
                    school["_id"]
                )
            }
        )
        .sort(
            "created_at",
            -1,
        )
    )

    return _many(
        docs
    )


# =========================================================
# EVENTS
# =========================================================

def create_event(
    user_id,
    data,
):
    school = _school_document(
        user_id
    )

    payload = _normalize_event_payload(
        data
    )
    payload["created_by"] = str(
        user_id
    )

    payload["calendar_year"] = (
        payload.get("calendar_year")
        or payload.get("academic_year")
        or (
            _text(
                payload.get("start_date")
            )[:4]
            if payload.get("start_date")
            else ""
        )
    )

    document = event_document(
        user_id,
        school["_id"],
        payload,
    )

    # Preserve upgraded metadata even while older model code is being rolled out.
    document.setdefault(
        "schema_version",
        ELIMU_VERSION,
    )
    document.setdefault(
        "recurrence",
        payload["recurrence"],
    )
    document.setdefault(
        "visibility",
        payload.get(
            "visibility",
            "school",
        ),
    )
    document.setdefault(
        "all_day",
        _safe_bool(
            payload.get(
                "all_day"
            ),
            False,
        ),
    )
    document.setdefault(
        "reminder_minutes",
        max(
            0,
            int(
                _safe_float(
                    payload.get(
                        "reminder_minutes"
                    ),
                    0,
                )
            ),
        ),
    )
    document.setdefault(
        "calendar_year",
        payload.get(
            "calendar_year",
            "",
        ),
    )
    document.setdefault(
        "created_by",
        str(user_id),
    )

    result = collection(
        EVENTS
    ).insert_one(
        document
    )

    document["_id"] = result.inserted_id

    log_action(
        user_id,
        "elimu.event.created",
        "school_event",
        result.inserted_id,
    )

    return _ser(
        document
    )


def events(
    user_id,
    *,
    year=None,
    event_type=None,
):
    school = _school_document(
        user_id
    )

    school_id = _school_id(
        school
    )

    query = {
        "school_id": school_id,
        "status": {
            "$ne": "cancelled"
        },
    }

    if year:
        year_value = _text(
            year
        )
        query["$or"] = [
            {
                "calendar_year": year_value
            },
            {
                "start_date": {
                    "$regex": f"^{year_value}"
                }
            },
        ]

    if event_type:
        query["event_type"] = _lower(
            event_type
        )

    docs = (
        collection(
            EVENTS
        )
        .find(
            query
        )
        .sort(
            [
                (
                    "start_date",
                    1,
                ),
                (
                    "created_at",
                    -1,
                ),
            ]
        )
    )

    return _many(
        docs
    )


def update_event(
    user_id,
    event_id,
    data,
):
    school = _school_document(
        user_id
    )

    school_id = _school_id(
        school
    )

    allowed = {
        "title",
        "event_type",
        "description",
        "start_date",
        "end_date",
        "location",
        "organizer",
        "academic_year",
        "term",
        "is_annual",
        "status",
        "recurrence",
        "visibility",
        "all_day",
        "reminder_minutes",
        "calendar_year",
    }

    update = {
        key: value
        for key, value in data.items()
        if key in allowed
    }

    if not update:
        raise APIError(
            "No valid event fields were supplied.",
            422,
            "validation_error",
        )

    if "status" in update:
        status = _lower(
            update["status"]
        )

        if status not in EVENT_STATUSES:
            raise APIError(
                "Invalid event status.",
                422,
                "validation_error",
            )

        update["status"] = status

    if (
        "is_annual" in update
        or "recurrence" in update
    ):
        annual = _safe_bool(
            update.get(
                "is_annual"
            ),
            False,
        )

        recurrence = update.get(
            "recurrence"
        )

        if not isinstance(
            recurrence,
            dict,
        ):
            recurrence = {
                "type": (
                    "annual"
                    if annual
                    else "none"
                )
            }

        recurrence = {
            "type": _lower(
                recurrence.get(
                    "type",
                    (
                        "annual"
                        if annual
                        else "none"
                    ),
                ),
                (
                    "annual"
                    if annual
                    else "none"
                ),
            ),
            **recurrence,
        }

        update["recurrence"] = recurrence
        update["is_annual"] = annual

    if (
        "calendar_year" not in update
        and update.get("academic_year")
    ):
        update["calendar_year"] = _text(
            update["academic_year"]
        )

    if "reminder_minutes" in update:
        update["reminder_minutes"] = max(
            0,
            int(
                _safe_float(
                    update["reminder_minutes"],
                    0,
                )
            ),
        )

    update["updated_at"] = now_utc()

    doc = collection(
        EVENTS
    ).find_one_and_update(
        {
            "_id": _oid(
                event_id
            ),
            "school_id": school_id,
        },
        {
            "$set": update
        },
        return_document=ReturnDocument.AFTER,
    )

    if not doc:
        raise APIError(
            "Event not found.",
            404,
            "event_not_found",
        )

    log_action(
        user_id,
        "elimu.event.updated",
        "school_event",
        doc["_id"],
    )

    return _ser(
        doc
    )



def delete_event(
    user_id,
    event_id,
):
    school = _school_document(
        user_id
    )

    result = collection(
        EVENTS
    ).update_one(
        {
            "_id": _oid(
                event_id
            ),
            "school_id": str(
                school["_id"]
            ),
        },
        {
            "$set": {
                "status": "cancelled",
                "updated_at": now_utc(),
            }
        },
    )

    if result.matched_count != 1:
        raise APIError(
            "Event not found.",
            404,
            "event_not_found",
        )

    log_action(
        user_id,
        "elimu.event.deleted",
        "school_event",
        event_id,
    )

    return {
        "deleted": True,
        "id": str(
            event_id
        ),
    }


# =========================================================
# REPORT HELPERS
# =========================================================

def _school_header(
    school,
):
    return {
        "name": school.get(
            "name",
            "",
        ),
        "code": school.get(
            "code",
            "",
        ),
        "registration_number": school.get(
            "registration_number",
            "",
        ),
        "school_type": school.get(
            "school_type",
            "",
        ),
        "motto": school.get(
            "motto",
            "",
        ),
        "mission": school.get(
            "mission",
            "",
        ),
        "vision": school.get(
            "vision",
            "",
        ),
        "principal_name": school.get(
            "principal_name",
            "",
        ),
        "administrator_name": school.get(
            "administrator_name",
            "",
        ),
        "phone": school.get(
            "phone",
            "",
        ),
        "email": school.get(
            "email",
            "",
        ),
        "website": school.get(
            "website",
            "",
        ),
        "postal_address": school.get(
            "postal_address",
            "",
        ),
        "location": school.get(
            "location",
            "",
        ),
        "county": school.get(
            "county",
            "",
        ),
        "town": school.get(
            "town",
            "",
        ),
        "country": school.get(
            "country",
            DEFAULT_COUNTRY,
        ),
        "logo_url": school.get(
            "logo_url",
            "",
        ),
    }


def _performance_band(
    percentage,
):
    if percentage is None:
        return "Not assessed"

    try:
        percentage = float(
            percentage
        )
    except (
        TypeError,
        ValueError,
    ):
        return "Not assessed"

    if percentage >= 80:
        return "Outstanding"

    if percentage >= 70:
        return "Very Good"

    if percentage >= 60:
        return "Good"

    if percentage >= 50:
        return "Developing"

    return "Needs Support"


def _report_branding(
    school,
):
    branding = school.get(
        "report_branding"
    )

    if not isinstance(
        branding,
        dict,
    ):
        branding = {}

    return {
        "logo_url": branding.get(
            "logo_url"
        ) or school.get(
            "logo_url",
            "",
        ),
        "primary_color": branding.get(
            "primary_color",
            "",
        ),
        "secondary_color": branding.get(
            "secondary_color",
            "",
        ),
        "footer_text": branding.get(
            "footer_text",
            "",
        ),
        "watermark": branding.get(
            "watermark",
            "",
        ),
    }


def _print_config(
    school,
    orientation="portrait",
):
    settings = school.get(
        "settings"
    )

    if not isinstance(
        settings,
        dict,
    ):
        settings = {}

    return {
        "ready": True,
        "renderer": "android_native",
        "paper": settings.get(
            "default_report_paper",
            "A4",
        ),
        "orientation": orientation,
        "repeat_school_header": True,
        "include_generated_at": True,
        "include_footer": True,
        "signature_lines": True,
        "save_as_pdf": True,
        "share": True,
        "print_preview": True,
    }


def _print_package(
    *,
    report_type,
    title,
    school,
    columns,
    rows,
    summary,
    metadata=None,
    orientation="portrait",
):
    settings = school.get(
        "settings"
    )

    if not isinstance(
        settings,
        dict,
    ):
        settings = {}

    metadata = dict(
        metadata or {}
    )

    metadata.setdefault(
        "academic_year",
        school.get(
            "academic_year",
            "",
        ),
    )
    metadata.setdefault(
        "term",
        school.get(
            "current_term",
            "",
        ),
    )
    metadata.setdefault(
        "schema_version",
        REPORT_SCHEMA_VERSION,
    )

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "hub": "elimu",
        "report_type": report_type,
        "title": title,
        "document_code": (
            f"ELIMU-"
            f"{str(report_type).upper()}"
        ),
        "generated_at": now_utc().isoformat(),
        "paper": settings.get(
            "default_report_paper",
            "A4",
        ),
        "orientation": orientation,
        "school": _school_header(
            school
        ),
        "branding": _report_branding(
            school
        ),
        "columns": columns,
        "rows": rows,
        "summary": summary,
        "metadata": metadata,
        "print": _print_config(
            school,
            orientation=orientation,
        ),
    }



# =========================================================
# REPORT CATALOG
# =========================================================

def report_catalog(
    user_id,
):
    school = _school_document(
        user_id
    )

    reports = [
        {
            "key": "school",
            "label": "School Profile Report",
            "description": (
                "Official school identity, leadership, "
                "contact and setup summary."
            ),
            "screen": "reports-school",
            "printable": True,
            "paper": "A4",
        },
        {
            "key": "student",
            "label": "Student Report Card",
            "description": (
                "Student academic performance, competency "
                "and attendance summary."
            ),
            "screen": "reports-student",
            "printable": True,
            "paper": "A4",
            "requires": ["student_id"],
        },
        {
            "key": "class",
            "label": "Class Performance Report",
            "description": (
                "Class-wide academic performance and learner "
                "summary."
            ),
            "screen": "reports-class",
            "printable": True,
            "paper": "A4",
            "requires": ["class_name"],
        },
        {
            "key": "attendance",
            "label": "Attendance Report",
            "description": (
                "Attendance records with present, late, absent "
                "and excused totals."
            ),
            "screen": "reports-attendance",
            "printable": True,
            "paper": "A4",
        },
        {
            "key": "fees",
            "label": "Fees Report",
            "description": (
                "Fee records with amount paid and outstanding "
                "balance information."
            ),
            "screen": "reports-fees",
            "printable": True,
            "paper": "A4",
            "orientation": "landscape",
        },
        {
            "key": "events",
            "label": "Annual Events Calendar",
            "description": (
                "Printable school calendar covering annual "
                "and one-time events."
            ),
            "screen": "reports-events",
            "printable": True,
            "paper": "A4",
        },
    ]

    return {
        "hub": "elimu",
        "school_id": _school_id(
            school
        ),
        "reports": reports,
        "print_center": _print_config(
            school
        ),
        "generated_at": now_utc().isoformat(),
    }



# =========================================================
# SCHOOL REPORT
# =========================================================

def school_report(
    user_id,
):
    school = _school_document(
        user_id
    )

    school_id = str(
        school["_id"]
    )

    class_count = collection(
        CLASSES
    ).count_documents(
        {
            "school_id": school_id,
            "status": "active",
        }
    )

    student_count = collection(
        STUDENTS
    ).count_documents(
        {
            "school_id": school_id,
            "status": "active",
        }
    )

    lesson_count = collection(
        LESSONS
    ).count_documents(
        {
            "school_id": school_id,
        }
    )

    event_count = collection(
        EVENTS
    ).count_documents(
        {
            "school_id": school_id,
            "status": {
                "$ne": "cancelled"
            },
        }
    )

    return _print_package(
        report_type="school",
        title="School Profile Report",
        school=school,
        columns=[
            "Field",
            "Value",
        ],
        rows=[
            [
                "School",
                school.get(
                    "name",
                    "",
                ),
            ],
            [
                "Code",
                school.get(
                    "code",
                    "",
                ),
            ],
            [
                "Registration Number",
                school.get(
                    "registration_number",
                    "",
                ),
            ],
            [
                "School Type",
                school.get(
                    "school_type",
                    "",
                ),
            ],
            [
                "County",
                school.get(
                    "county",
                    "",
                ),
            ],
            [
                "Town",
                school.get(
                    "town",
                    "",
                ),
            ],
            [
                "Principal",
                school.get(
                    "principal_name",
                    "",
                ),
            ],
            [
                "Academic Year",
                school.get(
                    "academic_year",
                    "",
                ),
            ],
            [
                "Current Term",
                school.get(
                    "current_term",
                    "",
                ),
            ],
        ],
        summary={
            "classes": class_count,
            "students": student_count,
            "lessons": lesson_count,
            "events": event_count,
        },
    )


# =========================================================
# STUDENT REPORT CARD
# =========================================================

def student_report(
    user_id,
    student_id,
    academic_year=None,
    term=None,
):
    school = _school_document(
        user_id
    )

    student = collection(
        STUDENTS
    ).find_one(
        {
            "_id": _oid(
                student_id
            ),
            "school_id": str(
                school["_id"]
            ),
        }
    )

    if not student:
        raise APIError(
            "Student not found.",
            404,
            "student_not_found",
        )

    query = {
        "school_id": str(
            school["_id"]
        ),
        "student_id": str(
            student["_id"]
        ),
    }

    if academic_year:
        query["academic_year"] = academic_year

    if term:
        query["term"] = term

    assessment_docs = list(
        collection(
            ASSESSMENTS
        )
        .find(query)
        .sort(
            [
                ("subject", 1),
                ("created_at", -1),
            ]
        )
    )

    # Latest assessment for each subject.
    subjects = {}

    for assessment in assessment_docs:

        subject = assessment.get(
            "subject",
            "Subject",
        )

        if subject in subjects:
            continue

        percentage = assessment.get(
            "percentage"
        )

        if percentage is None:

            score = assessment.get(
                "score"
            )

            maximum = assessment.get(
                "max_score",
                100,
            )

            try:
                percentage = round(
                    (
                        float(score)
                        / float(maximum)
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

        subjects[subject] = {
            "subject": subject,
            "assessment": assessment.get(
                "assessment_name",
                "",
            ),
            "score": assessment.get(
                "score"
            ),
            "max_score": assessment.get(
                "max_score"
            ),
            "percentage": percentage,
            "grade": assessment.get(
                "grade",
                "",
            ),
            "competency_level": assessment.get(
                "competency_level",
                "",
            ),
            "performance_band": _performance_band(
                percentage
            ),
            "remarks": assessment.get(
                "remarks",
                "",
            ),
        }

    subject_rows = list(
        subjects.values()
    )

    percentages = [
        item["percentage"]
        for item in subject_rows
        if item["percentage"] is not None
    ]

    average = (
        round(
            sum(percentages)
            / len(percentages),
            2,
        )
        if percentages
        else None
    )

    attendance_query = {
        "school_id": str(
            school["_id"]
        ),
        "student_id": str(
            student["_id"]
        ),
    }

    attendance_docs = list(
        collection(
            ATTENDANCE
        ).find(
            attendance_query
        )
    )

    present = sum(
        1
        for item in attendance_docs
        if item.get("status")
        == "present"
    )

    late = sum(
        1
        for item in attendance_docs
        if item.get("status")
        == "late"
    )

    absent = sum(
        1
        for item in attendance_docs
        if item.get("status")
        == "absent"
    )

    total_attendance = len(
        attendance_docs
    )

    attendance_rate = (
        round(
            (
                (present + late)
                / total_attendance
            )
            * 100,
            2,
        )
        if total_attendance
        else None
    )

    title = (
        f"Student Report Card - "
        f"{student.get('full_name', '')}"
    )

    return {
        **_print_package(
            report_type="student",
            title=title,
            school=school,
            columns=[
                "Subject",
                "Assessment",
                "Score",
                "Max",
                "%",
                "Grade",
                "Competency",
                "Remarks",
            ],
            rows=[
                [
                    item["subject"],
                    item["assessment"],
                    item["score"],
                    item["max_score"],
                    item["percentage"],
                    item["grade"],
                    item["competency_level"],
                    item["remarks"],
                ]
                for item in subject_rows
            ],
            summary={
                "student": _ser(
                    student
                ),
                "subjects": len(
                    subject_rows
                ),
                "average_percentage": average,
                "performance_band": _performance_band(
                    average
                ),
                "attendance": {
                    "total": total_attendance,
                    "present": present,
                    "late": late,
                    "absent": absent,
                    "attendance_rate": attendance_rate,
                },
            },
            metadata={
                "academic_year": academic_year,
                "term": term,
            },
        ),
        "student": _ser(
            student
        ),
    }


# =========================================================
# CLASS PERFORMANCE REPORT
# =========================================================

def class_report(
    user_id,
    class_name,
    academic_year=None,
    term=None,
):
    school = _school_document(
        user_id
    )

    school_id = _school_id(
        school
    )
    class_name = _text(
        class_name
    )

    students_docs = list(
        collection(
            STUDENTS
        )
        .find(
            {
                "school_id": school_id,
                "class_name": class_name,
                "status": "active",
            }
        )
        .sort(
            "full_name",
            1,
        )
    )

    rows = []

    for student in students_docs:
        query = {
            "school_id": school_id,
            "student_id": str(
                student["_id"]
            ),
        }

        if academic_year:
            query["academic_year"] = academic_year

        if term:
            query["term"] = term

        assessments_docs = list(
            collection(
                ASSESSMENTS
            )
            .find(query)
            .sort(
                [
                    ("subject", 1),
                    ("created_at", -1),
                ]
            )
        )

        latest_by_subject = {}

        for item in assessments_docs:
            subject = _text(
                item.get(
                    "subject"
                ),
                "Subject",
            )

            if subject not in latest_by_subject:
                latest_by_subject[subject] = item

        percentages = []

        for item in latest_by_subject.values():
            percentage = item.get(
                "percentage"
            )

            if percentage is None:
                score = item.get(
                    "score"
                )
                maximum = item.get(
                    "max_score",
                    100,
                )

                try:
                    percentage = (
                        float(score)
                        / float(maximum)
                    ) * 100
                except (
                    TypeError,
                    ValueError,
                    ZeroDivisionError,
                ):
                    percentage = None

            if percentage is not None:
                percentages.append(
                    round(
                        float(
                            percentage
                        ),
                        2,
                    )
                )

        average = (
            round(
                sum(percentages)
                / len(percentages),
                2,
            )
            if percentages
            else None
        )

        rows.append(
            [
                student.get(
                    "admission_number",
                    "",
                ),
                student.get(
                    "full_name",
                    "",
                ),
                len(
                    latest_by_subject
                ),
                average,
                _performance_band(
                    average
                ),
            ]
        )

    averages = [
        row[3]
        for row in rows
        if row[3] is not None
    ]

    class_average = (
        round(
            sum(averages)
            / len(averages),
            2,
        )
        if averages
        else None
    )

    return _print_package(
        report_type="class",
        title=(
            "Class Performance Report - "
            f"{class_name}"
        ),
        school=school,
        columns=[
            "Admission No.",
            "Student",
            "Subjects Assessed",
            "Average %",
            "Performance",
        ],
        rows=rows,
        summary={
            "class_name": class_name,
            "student_count": len(
                students_docs
            ),
            "students_assessed": sum(
                1
                for row in rows
                if row[3] is not None
            ),
            "class_average": class_average,
            "performance_band": _performance_band(
                class_average
            ),
        },
        metadata={
            "academic_year": academic_year,
            "term": term,
        },
    )



# =========================================================
# ATTENDANCE REPORT
# =========================================================

def attendance_report(
    user_id,
    start_date=None,
    end_date=None,
):
    records = attendance(
        user_id,
        start_date=start_date,
        end_date=end_date,
    )

    counts = {
        "present": 0,
        "late": 0,
        "absent": 0,
        "excused": 0,
    }

    rows = []

    for record in records:

        status = record.get(
            "status"
        )

        if status in counts:
            counts[status] += 1

        rows.append(
            [
                record.get(
                    "date",
                    "",
                ),
                record.get(
                    "admission_number",
                    "",
                ),
                record.get(
                    "student_name",
                    "",
                ),
                record.get(
                    "class_name",
                    "",
                ),
                status,
                record.get(
                    "reason",
                    "",
                ),
            ]
        )

    total = sum(
        counts.values()
    )

    attendance_rate = (
        round(
            (
                (
                    counts["present"]
                    + counts["late"]
                )
                / total
            )
            * 100,
            2,
        )
        if total
        else None
    )

    school = _school_document(
        user_id
    )

    return _print_package(
        report_type="attendance",
        title="Attendance Report",
        school=school,
        columns=[
            "Date",
            "Admission No.",
            "Student",
            "Class",
            "Status",
            "Reason",
        ],
        rows=rows,
        summary={
            **counts,
            "total": total,
            "attendance_rate": attendance_rate,
        },
        metadata={
            "start_date": start_date,
            "end_date": end_date,
        },
    )


# =========================================================
# FEES REPORT
# =========================================================

def fees_report(
    user_id,
    status=None,
):
    records = student_fees(
        user_id,
        status=status,
    )

    total_amount = 0.0
    total_paid = 0.0
    total_balance = 0.0
    status_counts = {}
    rows = []

    for record in records:
        amount = _safe_float(
            record.get(
                "amount"
            ),
            0.0,
        )

        amount_paid = _safe_float(
            record.get(
                "amount_paid"
            ),
            0.0,
        )

        balance = record.get(
            "balance"
        )

        if balance is None:
            balance = max(
                amount - amount_paid,
                0.0,
            )
        else:
            balance = max(
                _safe_float(
                    balance,
                    0.0,
                ),
                0.0,
            )

        total_amount += amount
        total_paid += amount_paid
        total_balance += balance

        current_status = _lower(
            record.get(
                "status"
            ),
            "pending",
        )

        status_counts[
            current_status
        ] = (
            status_counts.get(
                current_status,
                0,
            )
            + 1
        )

        rows.append(
            [
                record.get(
                    "student_name",
                    record.get(
                        "student_id",
                        record.get(
                            "student_user_id",
                            "",
                        ),
                    ),
                ),
                record.get(
                    "admission_number",
                    "",
                ),
                record.get(
                    "class_name",
                    "",
                ),
                record.get(
                    "description",
                    "",
                ),
                amount,
                amount_paid,
                balance,
                record.get(
                    "currency",
                    DEFAULT_CURRENCY,
                ),
                record.get(
                    "term",
                    "",
                ),
                record.get(
                    "academic_year",
                    "",
                ),
                current_status,
            ]
        )

    school = _school_document(
        user_id
    )

    return _print_package(
        report_type="fees",
        title="School Fees Report",
        school=school,
        columns=[
            "Student",
            "Admission No.",
            "Class",
            "Description",
            "Amount",
            "Paid",
            "Balance",
            "Currency",
            "Term",
            "Academic Year",
            "Status",
        ],
        rows=rows,
        summary={
            "records": len(
                records
            ),
            "total_amount": round(
                total_amount,
                2,
            ),
            "total_paid": round(
                total_paid,
                2,
            ),
            "total_balance": round(
                total_balance,
                2,
            ),
            "status_counts": status_counts,
        },
        metadata={
            "status": status,
        },
        orientation="landscape",
    )



# =========================================================
# EVENTS REPORT
# =========================================================

def events_report(
    user_id,
    year=None,
):
    school = _school_document(
        user_id
    )

    records = events(
        user_id,
        year=year,
    )

    rows = []

    for item in records:
        recurrence = item.get(
            "recurrence"
        )

        if isinstance(
            recurrence,
            dict,
        ):
            recurrence_type = recurrence.get(
                "type",
                "annual" if item.get("is_annual") else "none",
            )
        else:
            recurrence_type = (
                "annual"
                if item.get("is_annual")
                else "none"
            )

        rows.append(
            [
                item.get(
                    "start_date",
                    "",
                ),
                item.get(
                    "end_date",
                    "",
                ),
                item.get(
                    "title",
                    "",
                ),
                item.get(
                    "event_type",
                    "",
                ),
                item.get(
                    "location",
                    "",
                ),
                recurrence_type,
                item.get(
                    "status",
                    "",
                ),
            ]
        )

    return _print_package(
        report_type="events",
        title="School Annual Events Calendar",
        school=school,
        columns=[
            "Start",
            "End",
            "Event",
            "Type",
            "Location",
            "Recurrence",
            "Status",
        ],
        rows=rows,
        summary={
            "events": len(
                records
            ),
            "annual_events": sum(
                1
                for item in records
                if item.get(
                    "is_annual"
                )
                or (
                    isinstance(
                        item.get(
                            "recurrence"
                        ),
                        dict,
                    )
                    and item.get(
                        "recurrence",
                        {},
                    ).get(
                        "type"
                    ) == "annual"
                )
            ),
            "scheduled_events": sum(
                1
                for item in records
                if item.get(
                    "status"
                ) == "scheduled"
            ),
            "completed_events": sum(
                1
                for item in records
                if item.get(
                    "status"
                ) == "completed"
            ),
        },
        metadata={
            "year": year,
        },
    )



# =========================================================
# CALENDAR / PRINT CENTER / APK BOOTSTRAP
# =========================================================

def calendar(
    user_id,
    year=None,
):
    """Return a mobile-friendly annual school calendar contract."""
    school = _school_document(
        user_id
    )

    if year is None:
        configured_year = (
            school.get("calendar_year")
            or school.get("academic_year")
            or str(
                now_utc().year
            )
        )
        year = (
            _text(
                configured_year
            )[:4]
            or str(
                now_utc().year
            )
        )
    else:
        year = _text(
            year
        )

    records = events(
        user_id,
        year=year,
    )

    months = defaultdict(list)

    for event in records:
        start = _text(
            event.get(
                "start_date"
            )
        )
        month = (
            start[5:7]
            if len(start) >= 7
            else "00"
        )
        months[month].append(
            event
        )

    month_items = []

    for month_number in range(1, 13):
        month_key = f"{month_number:02d}"
        month_events = months.get(
            month_key,
            [],
        )

        month_items.append(
            {
                "month": month_number,
                "key": month_key,
                "events": month_events,
                "count": len(
                    month_events
                ),
            }
        )

    return {
        "hub": "elimu",
        "school": _school_header(
            school
        ),
        "year": year,
        "academic_year": school.get(
            "academic_year",
            "",
        ),
        "current_term": school.get(
            "current_term",
            "",
        ),
        "events": records,
        "months": month_items,
        "summary": {
            "total": len(
                records
            ),
            "annual": sum(
                1
                for event in records
                if event.get(
                    "is_annual"
                )
            ),
            "scheduled": sum(
                1
                for event in records
                if event.get(
                    "status"
                ) == "scheduled"
            ),
            "completed": sum(
                1
                for event in records
                if event.get(
                    "status"
                ) == "completed"
            ),
        },
        "print": _print_config(
            school
        ),
    }


def print_report(
    user_id,
    report_type,
    *,
    student_id=None,
    class_name=None,
    academic_year=None,
    term=None,
    start_date=None,
    end_date=None,
    status=None,
    year=None,
):
    """Single print-center dispatcher shared by web and Android clients."""
    key = _lower(
        report_type
    )

    dispatch = {
        "school": lambda: school_report(
            user_id
        ),
        "student": lambda: student_report(
            user_id,
            student_id,
            academic_year=academic_year,
            term=term,
        ),
        "class": lambda: class_report(
            user_id,
            class_name,
            academic_year=academic_year,
            term=term,
        ),
        "attendance": lambda: attendance_report(
            user_id,
            start_date=start_date,
            end_date=end_date,
        ),
        "fees": lambda: fees_report(
            user_id,
            status=status,
        ),
        "events": lambda: events_report(
            user_id,
            year=year,
        ),
        "annual_events": lambda: events_report(
            user_id,
            year=year,
        ),
    }

    if key not in dispatch:
        raise APIError(
            "Unsupported report type.",
            404,
            "report_not_found",
        )

    if key == "student" and not student_id:
        raise APIError(
            "student_id is required for a student report.",
            422,
            "validation_error",
        )

    if key == "class" and not class_name:
        raise APIError(
            "class_name is required for a class report.",
            422,
            "validation_error",
        )

    package = dispatch[
        key
    ]()

    return {
        **package,
        "print_center": {
            "available": True,
            "native_android": True,
            "save_as_pdf": True,
            "share": True,
        },
    }


def hub_bootstrap(
    user_id,
):
    """One-call startup contract for Android/Web Elimu navigation."""
    access_state = access(
        user_id
    )

    if not access_state[
        "allowed"
    ]:
        return {
            "hub": "elimu",
            "version": ELIMU_VERSION,
            "access": access_state,
            "redirect": access_state.get(
                "redirect"
            ),
            "school": None,
            "profile": None,
            "modules": [],
            "quick_actions": [],
            "metrics": {},
            "upcoming_events": [],
            "reports": [],
            "print_center": {
                "available": False,
                "reason": "school_required",
                "native_android": True,
            },
        }

    dashboard_data = dashboard(
        user_id
    )
    school = _school_document(
        user_id
    )

    modules = [
        {
            "key": "dashboard",
            "label": "School Dashboard",
            "screen": "elimu-dashboard",
            "enabled": True,
        },
        {
            "key": "students",
            "label": "Students",
            "screen": "elimu-students",
            "enabled": True,
        },
        {
            "key": "classes",
            "label": "Classes",
            "screen": "elimu-classes",
            "enabled": True,
        },
        {
            "key": "attendance",
            "label": "Attendance",
            "screen": "elimu-attendance",
            "enabled": True,
        },
        {
            "key": "assessments",
            "label": "Assessments",
            "screen": "elimu-assessments",
            "enabled": True,
        },
        {
            "key": "lessons",
            "label": "Lessons",
            "screen": "elimu-lessons",
            "enabled": True,
        },
        {
            "key": "assignments",
            "label": "Assignments",
            "screen": "elimu-assignments",
            "enabled": True,
        },
        {
            "key": "fees",
            "label": "Fees",
            "screen": "elimu-fees",
            "enabled": True,
        },
        {
            "key": "cbc",
            "label": "CBC Projects",
            "screen": "elimu-cbc",
            "enabled": True,
        },
        {
            "key": "calendar",
            "label": "Annual Calendar",
            "screen": "elimu-calendar",
            "enabled": True,
        },
        {
            "key": "reports",
            "label": "Report Center",
            "screen": "elimu-reports",
            "enabled": True,
        },
        {
            "key": "print",
            "label": "Print Center",
            "screen": "elimu-print-center",
            "enabled": True,
        },
    ]

    quick_actions = [
        {
            "key": "add_student",
            "label": "Add Student",
            "screen": "elimu-students-create",
            "icon": "user-plus",
        },
        {
            "key": "attendance",
            "label": "Mark Attendance",
            "screen": "elimu-attendance",
            "icon": "calendar-check",
        },
        {
            "key": "assessment",
            "label": "Record Assessment",
            "screen": "elimu-assessments-create",
            "icon": "graduation-cap",
        },
        {
            "key": "event",
            "label": "Add Event",
            "screen": "elimu-events-create",
            "icon": "calendar-plus",
        },
        {
            "key": "report",
            "label": "Print Report",
            "screen": "elimu-print-center",
            "icon": "printer",
        },
    ]

    return {
        "hub": "elimu",
        "version": ELIMU_VERSION,
        "access": {
            **dashboard_data.get(
                "access",
                {}
            ),
            "allowed": True,
            "has_school": True,
        },
        "redirect": None,
        "school": _ser(
            school
        ),
        "profile": dashboard_data.get(
            "profile"
        ),
        "modules": modules,
        "quick_actions": quick_actions,
        "metrics": dashboard_data.get(
            "metrics",
            {},
        ),
        "upcoming_events": dashboard_data.get(
            "upcoming_events",
            [],
        ),
        "recent": dashboard_data.get(
            "recent",
            {},
        ),
        "reports": report_catalog(
            user_id
        ).get(
            "reports",
            [],
        ),
        "print_center": dashboard_data.get(
            "print_center",
            _print_config(
                school
            ),
        ),
    }


# =========================================================
# DASHBOARD
# =========================================================

# =========================================================
# DASHBOARD
# =========================================================

def dashboard(
    user_id,
):
    school = _school_document(
        user_id
    )

    school_id = _school_id(
        school
    )

    classes_count = collection(
        CLASSES
    ).count_documents(
        {
            "school_id": school_id,
            "status": "active",
        }
    )

    students_count = collection(
        STUDENTS
    ).count_documents(
        {
            "school_id": school_id,
            "status": "active",
        }
    )

    lessons_count = collection(
        LESSONS
    ).count_documents(
        {
            "school_id": school_id,
        }
    )

    assignments_count = collection(
        ASSIGNMENTS
    ).count_documents(
        {
            "school_id": school_id,
        }
    )

    events_count = collection(
        EVENTS
    ).count_documents(
        {
            "school_id": school_id,
            "status": {
                "$ne": "cancelled"
            },
        }
    )

    pending_fees = collection(
        FEES
    ).count_documents(
        {
            "school_id": school_id,
            "status": {
                "$in": [
                    "pending",
                    "partial",
                    "overdue",
                ]
            },
        }
    )

    recent_events = list(
        collection(
            EVENTS
        )
        .find(
            {
                "school_id": school_id,
                "status": {
                    "$ne": "cancelled"
                },
            }
        )
        .sort(
            "start_date",
            1,
        )
        .limit(5)
    )

    recent_assignments = list(
        collection(
            ASSIGNMENTS
        )
        .find(
            {
                "school_id": school_id
            }
        )
        .sort(
            "created_at",
            -1,
        )
        .limit(6)
    )

    profile = collection(
        PROFILES
    ).find_one(
        {
            "user_id": str(
                user_id
            )
        }
    )

    upcoming_events = _next_events(
        school_id,
        limit=5,
    )

    return {
        "hub": "elimu",
        "version": ELIMU_VERSION,
        "access": {
            "allowed": True,
            "has_school": True,
            "school_id": school_id,
        },
        "school": _ser(
            school
        ),
        "profile": _ser(
            profile
        ),
        "modules": {
            "students": True,
            "classes": True,
            "attendance": True,
            "assessments": True,
            "lessons": True,
            "assignments": True,
            "fees": True,
            "cbc": True,
            "events": True,
            "reports": True,
            "print_center": True,
        },
        "metrics": {
            "classes": classes_count,
            "students": students_count,
            "lessons": lessons_count,
            "assignments": assignments_count,
            "events": events_count,
            "pending_fees": pending_fees,
        },
        "upcoming_events": upcoming_events,
        "recent": {
            "events": _many(
                recent_events
            ),
            "assignments": _many(
                recent_assignments
            ),
        },
        "quick_actions": [
            "add_student",
            "attendance",
            "assessment",
            "event",
            "report",
        ],
        "print_center": _print_config(
            school
        ),
    }
