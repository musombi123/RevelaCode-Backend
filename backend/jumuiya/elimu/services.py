# backend/jumuiya/elimu/services.py

from __future__ import annotations

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

    update["updated_at"] = now_utc()

    doc = collection(
        STUDENTS
    ).find_one_and_update(
        {
            "_id": _oid(
                student_id
            ),
            "school_id": str(
                school["_id"]
            ),
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

    payload = {
        **data,
        "school_id": str(
            school["_id"]
        ),
    }

    if data.get("student_id"):

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
            }
        )

        if not student:
            raise APIError(
                "Student does not belong to this school.",
                403,
                "student_access_denied",
            )

        payload["student_user_id"] = (
            payload.get(
                "student_user_id",
                "",
            )
        )

    document = fee_document(
        user_id,
        payload,
    )

    result = collection(
        FEES
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

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

    payload = {
        **data,
        "school_id": str(
            school["_id"]
        ),
    }

    if data.get(
        "student_id"
    ):

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
            }
        )

        if not student:
            raise APIError(
                "Student does not belong to this school.",
                403,
                "student_access_denied",
            )

    document = cbc_project_document(
        user_id,
        payload,
    )

    result = collection(
        CBC
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

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

    document = event_document(
        user_id,
        school["_id"],
        data,
    )

    result = collection(
        EVENTS
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

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

    query = {
        "school_id": str(
            school["_id"]
        ),
        "status": {
            "$ne": "cancelled"
        },
    }

    if year:
        query["start_date"] = {
            "$regex": f"^{str(year)}"
        }

    if event_type:
        query["event_type"] = str(
            event_type
        ).strip().lower()

    docs = (
        collection(EVENTS)
        .find(query)
        .sort(
            [
                ("start_date", 1),
                ("created_at", -1),
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

    update["updated_at"] = now_utc()

    doc = collection(
        EVENTS
    ).find_one_and_update(
        {
            "_id": _oid(
                event_id
            ),
            "school_id": str(
                school["_id"]
            ),
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
        "motto": school.get(
            "motto",
            "",
        ),
        "principal_name": school.get(
            "principal_name",
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

    if percentage >= 80:
        return "Outstanding"

    if percentage >= 70:
        return "Very Good"

    if percentage >= 60:
        return "Good"

    if percentage >= 50:
        return "Developing"

    return "Needs Support"


def _print_package(
    *,
    report_type,
    title,
    school,
    columns,
    rows,
    summary,
    metadata=None,
):
    return {
        "report_type": report_type,
        "title": title,
        "generated_at": now_utc().isoformat(),
        "paper": "A4",
        "orientation": "portrait",
        "school": _school_header(
            school
        ),
        "columns": columns,
        "rows": rows,
        "summary": summary,
        "metadata": metadata or {},
        "print": {
            "ready": True,
            "paper": "A4",
            "orientation": "portrait",
            "repeat_school_header": True,
        },
    }


# =========================================================
# REPORT CATALOG
# =========================================================

def report_catalog(
    user_id,
):
    _school_document(
        user_id
    )

    return {
        "reports": [
            {
                "key": "school",
                "label": "School Profile Report",
            },
            {
                "key": "student",
                "label": "Student Report Card",
            },
            {
                "key": "class",
                "label": "Class Performance Report",
            },
            {
                "key": "attendance",
                "label": "Attendance Report",
            },
            {
                "key": "fees",
                "label": "Fees Report",
            },
            {
                "key": "events",
                "label": "Annual Events Calendar",
            },
        ]
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

    school_id = str(
        school["_id"]
    )

    students_docs = list(
        collection(
            STUDENTS
        ).find(
            {
                "school_id": school_id,
                "class_name": str(
                    class_name
                ).strip(),
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
            query[
                "academic_year"
            ] = academic_year

        if term:
            query["term"] = term

        assessments_docs = list(
            collection(
                ASSESSMENTS
            ).find(query)
        )

        percentages = [
            float(
                item["percentage"]
            )
            for item in assessments_docs
            if item.get(
                "percentage"
            ) is not None
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
                    assessments_docs
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
            f"Class Performance Report - "
            f"{class_name}"
        ),
        school=school,
        columns=[
            "Admission No.",
            "Student",
            "Assessments",
            "Average %",
            "Performance",
        ],
        rows=rows,
        summary={
            "class_name": class_name,
            "student_count": len(
                students_docs
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

    total_amount = 0

    status_counts = {}

    rows = []

    for record in records:

        amount = float(
            record.get(
                "amount",
                0,
            )
            or 0
        )

        total_amount += amount

        current_status = record.get(
            "status",
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
                    "student_id",
                    record.get(
                        "student_user_id",
                        "",
                    ),
                ),
                record.get(
                    "description",
                    "",
                ),
                amount,
                record.get(
                    "currency",
                    "KES",
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
            "Description",
            "Amount",
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
            "total_amount": total_amount,
            "status_counts": status_counts,
        },
        metadata={
            "status": status,
        },
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

    query = {
        "school_id": str(
            school["_id"]
        ),
        "status": {
            "$ne": "cancelled"
        },
    }

    if year:
        query["start_date"] = {
            "$regex": f"^{str(year)}"
        }

    records = list(
        collection(
            EVENTS
        ).find(query).sort(
            "start_date",
            1,
        )
    )

    rows = [
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
            (
                "Annual"
                if item.get(
                    "is_annual"
                )
                else "One-time"
            ),
            item.get(
                "status",
                "",
            ),
        ]
        for item in records
    ]

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
            "Frequency",
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
            ),
        },
        metadata={
            "year": year,
        },
    )


# =========================================================
# DASHBOARD
# =========================================================

def dashboard(
    user_id,
):
    school = _school_document(
        user_id
    )

    school_id = str(
        school["_id"]
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

    return {
        "access": {
            "allowed": True,
            "school_id": school_id,
        },

        "school": _ser(
            school
        ),

        "profile": _ser(
            collection(
                PROFILES
            ).find_one(
                {
                    "user_id": str(
                        user_id
                    )
                }
            )
        ),

        "metrics": {
            "classes": classes_count,
            "students": students_count,
            "lessons": lessons_count,
            "assignments": assignments_count,
            "events": events_count,
            "pending_fees": pending_fees,
        },

        "recent": {
            "events": _many(
                recent_events
            ),
            "assignments": _many(
                recent_assignments
            ),
        },
    }
