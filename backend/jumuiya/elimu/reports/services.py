# backend/jumuiya/elimu/reports/services.py

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from bson import ObjectId
from bson.decimal128 import Decimal128
from bson.errors import InvalidId
from pymongo import ReturnDocument

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.elimu.permissions import authorize

from .generator import (
    ReportGenerationError,
    generate_class_exam_reports,
    generate_post_exam_programme,
    generate_student_exam_report,
    validate_generated_report,
)
from .models import (
    EXAM_REPORTS,
    PROGRAMMES,
    SCHOOL_CURRICULA,
    exam_report_document,
    programme_document,
    curriculum_document,
    published_report_fields,
    published_programme_fields,
)


# =========================================================
# COLLECTION NAMES
# =========================================================

STUDENTS = "jumuiya_students"
CLASSES = "jumuiya_classes"
SCHOOL_MEMBERS = "jumuiya_elimu_school_members"
FEES = "jumuiya_fees"
ATTENDANCE = "jumuiya_attendance"
ASSESSMENTS = "jumuiya_assessments"
TIMETABLE_ENTRIES = "jumuiya_elimu_timetable_entries"


# =========================================================
# HELPERS
# =========================================================

def sid(
    member: Mapping[str, Any],
) -> str:
    """
    Return the authorized school ID.
    """
    school_id = member.get(
        "school_id"
    )

    if school_id is None:
        raise APIError(
            "Authorized user is not associated with a school.",
            403,
            "school_required",
        )

    return str(
        school_id
    )


def _school_id(
    member: Mapping[str, Any],
) -> str:
    return sid(member)


def _text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(
        value
    ).strip()


def _lower(
    value: Any,
) -> str:
    return _text(
        value
    ).lower()


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return default


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return default


def _safe_bool(
    value: Any,
    default: bool = False,
) -> bool:
    if isinstance(
        value,
        bool,
    ):
        return value

    if value is None:
        return default

    if isinstance(
        value,
        str,
    ):
        normalized = value.strip().lower()

        if normalized in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return True

        if normalized in {
            "0",
            "false",
            "no",
            "off",
        }:
            return False

    if isinstance(
        value,
        (int, float),
    ):
        return bool(
            value
        )

    return default


def _school_document(
    user_id: str,
) -> dict:
    """
    Reuse the Elimu school ownership boundary without importing
    the whole Elimu service module.
    """
    # authorize() already returns the authorized school/member context.
    member = authorize(
        user_id,
        "reports.view",
    )

    if not isinstance(
        member,
        Mapping,
    ):
        raise APIError(
            "Unable to resolve school access.",
            403,
            "school_access_denied",
        )

    school_id = member.get(
        "school_id"
    )

    if school_id is None:
        raise APIError(
            "A school account is required to access reports.",
            403,
            "school_required",
        )

    return {
        **dict(member),
        "school_id": str(
            school_id
        ),
    }


def _oid(
    value: Any,
) -> ObjectId:
    try:
        return ObjectId(
            str(
                value
            )
        )
    except (
        InvalidId,
        TypeError,
        ValueError,
    ) as exc:
        raise APIError(
            "Invalid resource ID.",
            400,
            "invalid_id",
        ) from exc


def _serialize(
    value: Any,
) -> Any:
    """
    Convert Mongo/Python values into JSON-safe values.
    """
    if isinstance(
        value,
        ObjectId,
    ):
        return str(
            value
        )

    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()

    if isinstance(
        value,
        Decimal,
    ):
        return float(
            value
        )

    if isinstance(
        value,
        Decimal128,
    ):
        return float(
            value.to_decimal()
        )

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key): _serialize(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        list,
    ):
        return [
            _serialize(item)
            for item in value
        ]

    return value


def _doc(
    value: Mapping[str, Any] | None,
) -> dict | None:
    if not value:
        return None

    return _serialize(
        dict(value)
    )


def _many(
    values: Iterable[Mapping[str, Any]],
) -> list[dict]:
    return [
        _serialize(
            dict(value)
        )
        for value in values
    ]


def _date_value(
    value: Any,
) -> Any:
    if value in (
        None,
        "",
    ):
        return None

    if isinstance(
        value,
        datetime,
    ):
        return value

    return str(
        value
    ).strip() or None


def _money(
    value: Any,
) -> Decimal:
    if value is None:
        return Decimal(
            "0"
        )

    if isinstance(
        value,
        Decimal,
    ):
        return value

    if isinstance(
        value,
        Decimal128,
    ):
        return value.to_decimal()

    if isinstance(
        value,
        bool,
    ):
        return Decimal(
            "0"
        )

    try:
        return Decimal(
            str(value)
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return Decimal(
            "0"
        )


def _money_float(
    value: Decimal,
) -> float:
    return float(
        value.quantize(
            Decimal(
                "0.01"
            )
        )
    )


def _distinct_count(
    collection_name: str,
    query: dict[str, Any],
    field: str,
) -> int:
    values = collection(
        collection_name
    ).distinct(
        field,
        query,
    )

    return len(
        {
            str(value)
            for value in values
            if value not in (
                None,
                "",
            )
        }
    )


# =========================================================
# OVERVIEW
# =========================================================

def overview(
    user_id: str,
) -> dict[str, Any]:
    """
    School reporting overview.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    school_query = {
        "school_id": school_id,
    }

    active_query = {
        **school_query,
        "status": {
            "$ne": "inactive",
        },
    }

    return {
        "school_id": school_id,

        "students": collection(
            STUDENTS
        ).count_documents(
            active_query
        ),

        "classes": collection(
            CLASSES
        ).count_documents(
            active_query
        ),

        "staff": collection(
            SCHOOL_MEMBERS
        ).count_documents(
            {
                **school_query,
                "status": "active",
            }
        ),

        "fees": collection(
            FEES
        ).count_documents(
            school_query
        ),

        "attendance": collection(
            ATTENDANCE
        ).count_documents(
            school_query
        ),

        "assessments": collection(
            ASSESSMENTS
        ).count_documents(
            school_query
        ),

        "exam_reports": collection(
            EXAM_REPORTS
        ).count_documents(
            school_query
        ),

        "curricula": collection(
            SCHOOL_CURRICULA
        ).count_documents(
            school_query
        ),

        "programmes": collection(
            PROGRAMMES
        ).count_documents(
            school_query
        ),
    }


# =========================================================
# ATTENDANCE REPORT
# =========================================================

def attendance(
    user_id: str,
    start_date: Any = None,
    end_date: Any = None,
) -> dict[str, Any]:
    """
    School attendance summary grouped by status.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    query: dict[str, Any] = {
        "school_id": school_id,
    }

    normalized_start = _date_value(
        start_date
    )

    normalized_end = _date_value(
        end_date
    )

    if (
        normalized_start is not None
        or normalized_end is not None
    ):
        date_query: dict[str, Any] = {}

        if normalized_start is not None:
            date_query[
                "$gte"
            ] = normalized_start

        if normalized_end is not None:
            date_query[
                "$lte"
            ] = normalized_end

        query[
            "date"
        ] = date_query

    rows = list(
        collection(
            ATTENDANCE
        ).find(
            query,
            {
                "_id": 0,
                "status": 1,
            },
        )
    )

    counts: dict[str, int] = {}

    for row in rows:
        status = (
            _lower(
                row.get(
                    "status",
                    "unknown",
                )
            )
            or "unknown"
        )

        counts[
            status
        ] = (
            counts.get(
                status,
                0,
            )
            + 1
        )

    return {
        "school_id": school_id,
        "total": len(
            rows
        ),
        "by_status": counts,
        "start_date": normalized_start,
        "end_date": normalized_end,
    }


# =========================================================
# FEES REPORT
# =========================================================

def fees(
    user_id: str,
    status: str | None = None,
) -> dict[str, Any]:
    """
    School fee totals.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    query: dict[str, Any] = {
        "school_id": school_id,
    }

    normalized_status = (
        _lower(
            status
        )
        if status is not None
        else None
    )

    if normalized_status:
        query[
            "status"
        ] = normalized_status

    rows = list(
        collection(
            FEES
        ).find(
            query,
            {
                "_id": 0,
                "amount": 1,
                "paid_amount": 1,
                "amount_paid": 1,
                "status": 1,
            },
        )
    )

    total = Decimal(
        "0"
    )

    paid = Decimal(
        "0"
    )

    for row in rows:
        total += _money(
            row.get(
                "amount",
                0,
            )
        )

        paid_value = row.get(
            "paid_amount"
        )

        if paid_value is None:
            paid_value = row.get(
                "amount_paid",
                0,
            )

        paid += _money(
            paid_value
        )

    outstanding = max(
        Decimal(
            "0"
        ),
        total - paid,
    )

    return {
        "school_id": school_id,
        "records": len(
            rows
        ),
        "amount": _money_float(
            total
        ),
        "paid": _money_float(
            paid
        ),
        "outstanding": _money_float(
            outstanding
        ),
        "status": normalized_status,
    }


# =========================================================
# TIMETABLE REPORT
# =========================================================

def timetable(
    user_id: str,
) -> dict[str, Any]:
    """
    Timetable coverage statistics.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    query = {
        "school_id": school_id,
    }

    entries_collection = collection(
        TIMETABLE_ENTRIES
    )

    return {
        "school_id": school_id,

        "entries": entries_collection.count_documents(
            query
        ),

        "teachers": _distinct_count(
            TIMETABLE_ENTRIES,
            query,
            "teacher_user_id",
        ),

        "classes": _distinct_count(
            TIMETABLE_ENTRIES,
            query,
            "class_id",
        ),

        "subjects": _distinct_count(
            TIMETABLE_ENTRIES,
            query,
            "subject",
        ),

        "rooms": _distinct_count(
            TIMETABLE_ENTRIES,
            query,
            "room_id",
        ),
    }


# =========================================================
# CURRICULUM
# =========================================================

def curricula(
    user_id: str,
    *,
    education_level: str | None = None,
    grade: str | None = None,
    academic_year: str | None = None,
    term: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """
    List school curriculum configurations.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    query: dict[str, Any] = {
        "school_id": school_id,
    }

    if education_level:
        query[
            "education_level"
        ] = _lower(
            education_level
        )

    if grade:
        query[
            "grade"
        ] = _text(
            grade
        )

    if academic_year:
        query[
            "academic_year"
        ] = _text(
            academic_year
        )

    if term:
        query[
            "term"
        ] = _text(
            term
        )

    if status:
        query[
            "status"
        ] = _lower(
            status
        )

    docs = (
        collection(
            SCHOOL_CURRICULA
        )
        .find(
            query
        )
        .sort(
            [
                (
                    "updated_at",
                    -1,
                ),
                (
                    "grade",
                    1,
                ),
            ]
        )
    )

    return _many(
        docs
    )


def get_curriculum(
    user_id: str,
    curriculum_id: str,
) -> dict:
    """
    Retrieve one school curriculum.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    doc = collection(
        SCHOOL_CURRICULA
    ).find_one(
        {
            "_id": _oid(
                curriculum_id
            ),
            "school_id": school_id,
        }
    )

    if not doc:
        raise APIError(
            "Curriculum configuration not found.",
            404,
            "curriculum_not_found",
        )

    return _doc(
        doc
    )


def save_curriculum(
    user_id: str,
    data: Mapping[str, Any],
) -> dict:
    """
    Create or update a curriculum configuration for the school.

    The school supplies the learning areas it offers. Ownership is
    always derived from the authenticated school.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    payload = dict(
        data
    )

    document = curriculum_document(
        user_id,
        school_id,
        payload,
    )

    identity_query = {
        "school_id": school_id,
        "education_level": document[
            "education_level"
        ],
        "grade": document[
            "grade"
        ],
        "academic_year": document.get(
            "academic_year",
            "",
        ),
        "term": document.get(
            "term",
            "",
        ),
    }

    existing = collection(
        SCHOOL_CURRICULA
    ).find_one(
        identity_query
    )

    if existing:
        document[
            "created_at"
        ] = existing.get(
            "created_at",
            document[
                "created_at"
            ],
        )

        document[
            "created_by"
        ] = existing.get(
            "created_by",
            document[
                "created_by"
            ],
        )

        result = collection(
            SCHOOL_CURRICULA
        ).find_one_and_update(
            {
                "_id": existing[
                    "_id"
                ],
                "school_id": school_id,
            },
            {
                "$set": {
                    **document,
                    "updated_at": datetime.now(
                        timezone.utc
                    ),
                }
            },
            return_document=ReturnDocument.AFTER,
        )

        log_action(
            user_id,
            "elimu.curriculum.updated",
            "curriculum",
            result[
                "_id"
            ],
        )

        return _doc(
            result
        )

    result = collection(
        SCHOOL_CURRICULA
    ).insert_one(
        document
    )

    document[
        "_id"
    ] = result.inserted_id

    log_action(
        user_id,
        "elimu.curriculum.created",
        "curriculum",
        result.inserted_id,
    )

    return _doc(
        document
    )


def _resolve_curriculum(
    school_id: str,
    student: Mapping[str, Any],
    data: Mapping[str, Any],
) -> dict:
    """
    Resolve the curriculum applicable to a learner.

    Priority:
        1. explicit curriculum_id when supplied internally
        2. exact grade/year/term match
        3. grade match
        4. latest active curriculum for school
    """

    curriculum_id = data.get(
        "curriculum_id"
    )

    if curriculum_id:
        doc = collection(
            SCHOOL_CURRICULA
        ).find_one(
            {
                "_id": _oid(
                    curriculum_id
                ),
                "school_id": school_id,
                "status": "active",
            }
        )

        if not doc:
            raise APIError(
                "The selected curriculum does not belong to this school "
                "or is not active.",
                404,
                "curriculum_not_found",
            )

        return doc

    student_class_id = (
        student.get(
            "class_id"
        )
    )

    class_doc = None

    if student_class_id:
        try:
            class_doc = collection(
                CLASSES
            ).find_one(
                {
                    "_id": _oid(
                        student_class_id
                    ),
                    "school_id": school_id,
                    "status": {
                        "$ne": "inactive",
                    },
                }
            )
        except APIError:
            class_doc = None

    requested_grade = _text(
        data.get(
            "grade"
        )
    )

    if not requested_grade and class_doc:
        requested_grade = _text(
            class_doc.get(
                "level"
            )
        )

    if not requested_grade:
        requested_grade = _text(
            student.get(
                "class_name"
            )
        )

    academic_year = _text(
        data.get(
            "academic_year"
        )
    )

    term = _text(
        data.get(
            "term"
        )
    )

    query = {
        "school_id": school_id,
        "status": "active",
    }

    if academic_year:
        query[
            "academic_year"
        ] = academic_year

    if term:
        query[
            "term"
        ] = term

    docs = list(
        collection(
            SCHOOL_CURRICULA
        )
        .find(
            query
        )
        .sort(
            [
                (
                    "updated_at",
                    -1,
                ),
                (
                    "created_at",
                    -1,
                ),
            ]
        )
    )

    if requested_grade:
        normalized_requested_grade = _lower(
            requested_grade
        )

        for doc in docs:
            if (
                _lower(
                    doc.get(
                        "grade"
                    )
                )
                == normalized_requested_grade
            ):
                return doc

    if len(
        docs
    ) == 1:
        return docs[0]

    if not docs:
        raise APIError(
            "No active curriculum is configured for this school. "
            "Configure the school's learning areas before generating "
            "learner reports.",
            422,
            "curriculum_required",
        )

    raise APIError(
        "Multiple curriculum configurations match this learner. "
        "Specify curriculum_id or grade.",
        422,
        "curriculum_ambiguous",
    )


# =========================================================
# STUDENT
# =========================================================

def _get_student_for_school(
    school_id: str,
    student_id: str,
) -> dict:
    student = collection(
        STUDENTS
    ).find_one(
        {
            "_id": _oid(
                student_id
            ),
            "school_id": school_id,
        }
    )

    if not student:
        raise APIError(
            "Student not found in this school.",
            404,
            "student_not_found",
        )

    return student


# =========================================================
# ATTENDANCE BY STUDENT
# =========================================================

def _attendance_for_students(
    school_id: str,
    student_ids: Iterable[str],
    *,
    start_date: Any = None,
    end_date: Any = None,
) -> dict[str, dict]:
    """
    Produce attendance summaries keyed by student ID.
    """
    normalized_ids = {
        str(
            student_id
        )
        for student_id in student_ids
        if student_id is not None
    }

    if not normalized_ids:
        return {}

    query: dict[str, Any] = {
        "school_id": school_id,
        "student_id": {
            "$in": list(
                normalized_ids
            )
        },
    }

    start = _date_value(
        start_date
    )

    end = _date_value(
        end_date
    )

    if (
        start is not None
        or end is not None
    ):
        date_query = {}

        if start is not None:
            date_query[
                "$gte"
            ] = start

        if end is not None:
            date_query[
                "$lte"
            ] = end

        query[
            "date"
        ] = date_query

    rows = list(
        collection(
            ATTENDANCE
        ).find(
            query,
            {
                "student_id": 1,
                "status": 1,
            },
        )
    )

    summaries: dict[str, dict] = {}

    for student_id in normalized_ids:
        summaries[
            student_id
        ] = {
            "total": 0,
            "present": 0,
            "absent": 0,
            "late": 0,
            "excused": 0,
            "attendance_rate": None,
        }

    for row in rows:
        student_id = str(
            row.get(
                "student_id"
            )
        )

        if student_id not in summaries:
            continue

        status = (
            _lower(
                row.get(
                    "status",
                    "unknown",
                )
            )
            or "unknown"
        )

        summary = summaries[
            student_id
        ]

        summary[
            "total"
        ] += 1

        if status in {
            "present",
            "absent",
            "late",
            "excused",
        }:
            summary[
                status
            ] += 1

    for summary in summaries.values():
        total = summary[
            "total"
        ]

        if total > 0:
            attended = (
                summary[
                    "present"
                ]
                + summary[
                    "late"
                ]
            )

            summary[
                "attendance_rate"
            ] = round(
                (
                    attended
                    / total
                )
                * 100,
                2,
            )

    return summaries


# =========================================================
# EXAM ASSESSMENTS
# =========================================================

def _student_assessments(
    school_id: str,
    student_id: str,
    *,
    academic_year: str | None = None,
    term: str | None = None,
    assessment_name: str | None = None,
    assessment_type: str | None = "exam",
) -> list[dict]:
    query: dict[str, Any] = {
        "school_id": school_id,
        "student_id": str(
            student_id
        ),
    }

    if academic_year:
        query[
            "academic_year"
        ] = _text(
            academic_year
        )

    if term:
        query[
            "term"
        ] = _text(
            term
        )

    if assessment_name:
        query[
            "assessment_name"
        ] = _text(
            assessment_name
        )

    if assessment_type:
        query[
            "assessment_type"
        ] = _lower(
            assessment_type
        )

    return list(
        collection(
            ASSESSMENTS
        )
        .find(
            query
        )
        .sort(
            [
                (
                    "assessment_date",
                    -1,
                ),
                (
                    "updated_at",
                    -1,
                ),
                (
                    "created_at",
                    -1,
                ),
            ]
        )
    )


def _class_students(
    school_id: str,
    class_name: str | None = None,
) -> list[dict]:
    query: dict[str, Any] = {
        "school_id": school_id,
        "status": "active",
    }

    if class_name:
        query[
            "class_name"
        ] = _text(
            class_name
        )

    return list(
        collection(
            STUDENTS
        )
        .find(
            query
        )
        .sort(
            [
                (
                    "class_name",
                    1,
                ),
                (
                    "full_name",
                    1,
                ),
            ]
        )
    )


# =========================================================
# SCHOOL BRANDING / REPORT SETTINGS
# =========================================================

def _report_branding(
    school: Mapping[str, Any],
) -> dict:
    branding = school.get(
        "report_branding",
        {},
    )

    if not isinstance(
        branding,
        Mapping,
    ):
        branding = {}

    return {
        **dict(
            branding
        ),
        "logo_url": _text(
            branding.get(
                "logo_url",
                school.get(
                    "logo_url",
                    "",
                ),
            )
        ),
        "school_name": _text(
            school.get(
                "name"
            )
        ),
        "motto": _text(
            school.get(
                "motto"
            )
        ),
        "phone": _text(
            school.get(
                "phone"
            )
        ),
        "email": _text(
            school.get(
                "email"
            )
        ),
        "website": _text(
            school.get(
                "website"
            )
        ),
        "postal_address": _text(
            school.get(
                "postal_address"
            )
        ),
    }


def _school_print_options(
    school: Mapping[str, Any],
) -> dict:
    settings = school.get(
        "settings",
        {},
    )

    if not isinstance(
        settings,
        Mapping,
    ):
        settings = {}

    return {
        "paper": (
            _text(
                settings.get(
                    "default_report_paper",
                    "A4",
                )
            )
            or "A4"
        ),

        "orientation": (
            _lower(
                settings.get(
                    "default_report_orientation",
                    "portrait",
                )
            )
            or "portrait"
        ),

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
# INDIVIDUAL EXAM REPORT
# =========================================================

def generate_exam_report(
    user_id: str,
    data: Mapping[str, Any],
) -> dict:
    """
    Generate and persist one CBC-aware learner report.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    student = _get_student_for_school(
        school_id,
        data[
            "student_id"
        ],
    )

    curriculum = _resolve_curriculum(
        school_id,
        student,
        data,
    )

    academic_year = _text(
        data.get(
            "academic_year"
        )
    )

    term = _text(
        data.get(
            "term"
        )
    )

    assessment_name = _text(
        data.get(
            "assessment_name"
        )
    )

    assessment_type = (
        _lower(
            data.get(
                "assessment_type",
                "exam",
            )
        )
        or "exam"
    )

    assessments = _student_assessments(
        school_id,
        str(
            student["_id"]
        ),
        academic_year=academic_year,
        term=term,
        assessment_name=assessment_name or None,
        assessment_type=assessment_type,
    )

    if not assessments:
        raise APIError(
            "No assessment evidence was found for this learner "
            "and report period.",
            422,
            "assessment_data_required",
        )

    attendance_map = _attendance_for_students(
        school_id,
        [
            str(
                student["_id"]
            )
        ],
    )

    include_attendance = _safe_bool(
        data.get(
            "include_attendance"
        ),
        True,
    )

    attendance_summary = (
        attendance_map.get(
            str(
                student["_id"]
            ),
            {},
        )
        if include_attendance
        else {}
    )

    ranking_enabled = _safe_bool(
        data.get(
            "ranking_enabled"
        ),
        False,
    )

    class_position = data.get(
        "class_position"
    )

    class_size = data.get(
        "class_size"
    )

    reports_for_ranking = None

    # -----------------------------------------------------
    # Optional class ranking
    # -----------------------------------------------------
    #
    # CBC reporting does not require traditional ranking.
    # When explicitly enabled, calculate it from the school's
    # entire class rather than trusting client-supplied position.
    # -----------------------------------------------------

    if ranking_enabled:
        class_name = (
            _text(
                data.get(
                    "class_name"
                )
            )
            or _text(
                student.get(
                    "class_name"
                )
            )
        )

        class_students = _class_students(
            school_id,
            class_name,
        )

        all_student_ids = [
            str(
                item["_id"]
            )
            for item in class_students
        ]

        class_attendance = _attendance_for_students(
            school_id,
            all_student_ids,
        )

        all_assessments = list(
            collection(
                ASSESSMENTS
            )
            .find(
                {
                    "school_id": school_id,
                    "student_id": {
                        "$in": all_student_ids
                    },
                    **(
                        {
                            "academic_year": academic_year
                        }
                        if academic_year
                        else {}
                    ),
                    **(
                        {
                            "term": term
                        }
                        if term
                        else {}
                    ),
                    **(
                        {
                            "assessment_name": assessment_name
                        }
                        if assessment_name
                        else {}
                    ),
                    "assessment_type": assessment_type,
                }
            )
            .sort(
                [
                    (
                        "assessment_date",
                        -1,
                    ),
                    (
                        "updated_at",
                        -1,
                    ),
                ]
            )
        )

        reports_for_ranking = generate_class_exam_reports(
            class_students,
            all_assessments,
            curriculum=curriculum,
            academic_year=academic_year or None,
            term=term or None,
            assessment_name=assessment_name or None,
            assessment_type=assessment_type,
            grading_scale=data.get(
                "grading_scale"
            ),
            performance_scale=data.get(
                "performance_scale"
            ),
            attendance_by_student=class_attendance,
            report_branding=_report_branding(
                member
            ),
            teacher_remarks=_text(
                data.get(
                    "teacher_remarks"
                )
            ),
            principal_remarks=_text(
                data.get(
                    "principal_remarks"
                )
            ),
            ranking_enabled=True,
        )

        selected_id = str(
            student["_id"]
        )

        selected_report = next(
            (
                report
                for report in reports_for_ranking
                if str(
                    report.get(
                        "student_id"
                    )
                )
                == selected_id
            ),
            None,
        )

        if selected_report:
            class_position = selected_report.get(
                "class_position"
            )

            class_size = selected_report.get(
                "class_size"
            )

            report = selected_report
        else:
            report = generate_student_exam_report(
                student,
                assessments,
                curriculum=curriculum,
                academic_year=academic_year or None,
                term=term or None,
                assessment_name=assessment_name or None,
                assessment_type=assessment_type,
                grading_scale=data.get(
                    "grading_scale"
                ),
                performance_scale=data.get(
                    "performance_scale"
                ),
                attendance=attendance_summary,
                teacher_remarks=_text(
                    data.get(
                        "teacher_remarks"
                    )
                ),
                principal_remarks=_text(
                    data.get(
                        "principal_remarks"
                    )
                ),
                learner_remarks=_text(
                    data.get(
                        "learner_remarks"
                    )
                ),
                class_position=class_position,
                class_size=class_size,
                ranking_enabled=True,
                report_branding=_report_branding(
                    member
                ),
                print_options=_school_print_options(
                    member
                ),
            )
    else:
        report = generate_student_exam_report(
            student,
            assessments,
            curriculum=curriculum,
            academic_year=academic_year or None,
            term=term or None,
            assessment_name=assessment_name or None,
            assessment_type=assessment_type,
            grading_scale=data.get(
                "grading_scale"
            ),
            performance_scale=data.get(
                "performance_scale"
            ),
            attendance=attendance_summary,
            teacher_remarks=_text(
                data.get(
                    "teacher_remarks"
                )
            ),
            principal_remarks=_text(
                data.get(
                    "principal_remarks"
                )
            ),
            learner_remarks=_text(
                data.get(
                    "learner_remarks"
                )
            ),
            class_position=class_position,
            class_size=class_size,
            ranking_enabled=False,
            report_branding=_report_branding(
                member
            ),
            print_options=_school_print_options(
                member
            ),
        )

    # -----------------------------------------------------
    # Enrich report with curriculum identity
    # -----------------------------------------------------

    report[
        "education_level"
    ] = curriculum.get(
        "education_level"
    )

    report[
        "grade"
    ] = curriculum.get(
        "grade"
    )

    report[
        "pathway"
    ] = curriculum.get(
        "pathway"
    )

    report[
        "track"
    ] = curriculum.get(
        "track"
    )

    report[
        "assessment_framework"
    ] = curriculum.get(
        "assessment_framework",
        "cbc",
    )

    report[
        "report_type"
    ] = data.get(
        "report_type",
        curriculum.get(
            "report_settings",
            {},
        ).get(
            "report_type",
            "individual_learner_report",
        ),
    )

    # -----------------------------------------------------
    # Add explicit improvement/next-step data
    # -----------------------------------------------------

    report[
        "strengths"
    ] = (
        list(
            data.get(
                "strengths",
                []
            )
            or []
        )
        or report.get(
            "strengths",
            []
        )
    )

    report[
        "areas_for_improvement"
    ] = list(
        data.get(
            "areas_for_improvement",
            []
        )
        or []
    )

    report[
        "next_steps"
    ] = list(
        data.get(
            "next_steps",
            []
        )
        or []
    )

    # -----------------------------------------------------
    # Validate before persistence
    # -----------------------------------------------------

    checked = validate_generated_report(
        report,
        curriculum,
    )

    if not checked.get(
        "valid"
    ):
        raise APIError(
            "Generated learner report failed validation.",
            422,
            "report_validation_failed",
        )

    document = exam_report_document(
        user_id,
        school_id,
        student,
        report,
    )

    # Stable report identity prevents accidental duplicates.
    identity = {
        "school_id": school_id,
        "student_id": str(
            student["_id"]
        ),
        "academic_year": _text(
            report.get(
                "academic_year"
            )
        ),
        "term": _text(
            report.get(
                "term"
            )
        ),
        "assessment_name": _text(
            report.get(
                "assessment_name"
            )
        ),
        "assessment_type": _lower(
            report.get(
                "assessment_type",
                "exam",
            )
        ),
    }

    existing = collection(
        EXAM_REPORTS
    ).find_one(
        identity
    )

    if existing:
        document[
            "created_at"
        ] = existing.get(
            "created_at",
            document[
                "created_at"
            ],
        )

        document[
            "status"
        ] = existing.get(
            "status",
            document[
                "status"
            ],
        )

        saved = collection(
            EXAM_REPORTS
        ).find_one_and_update(
            {
                "_id": existing[
                    "_id"
                ],
                "school_id": school_id,
            },
            {
                "$set": {
                    **document,
                    "updated_at": datetime.now(
                        timezone.utc
                    ),
                }
            },
            return_document=ReturnDocument.AFTER,
        )

        log_action(
            user_id,
            "elimu.exam_report.updated",
            "exam_report",
            saved[
                "_id"
            ],
        )

        return _doc(
            saved
        )

    result = collection(
        EXAM_REPORTS
    ).insert_one(
        document
    )

    document[
        "_id"
    ] = result.inserted_id

    log_action(
        user_id,
        "elimu.exam_report.generated",
        "exam_report",
        result.inserted_id,
        {
            "student_id": str(
                student["_id"]
            ),
            "assessment_name": report.get(
                "assessment_name"
            ),
        },
    )

    return _doc(
        document
    )


# =========================================================
# CLASS EXAM REPORTS
# =========================================================

def generate_class_reports(
    user_id: str,
    data: Mapping[str, Any],
) -> dict:
    """
    Generate and persist reports for an entire class.

    The school's curriculum controls the learning areas.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    class_name = _text(
        data.get(
            "class_name"
        )
    )

    student_ids = [
        str(
            value
        )
        for value in (
            data.get(
                "student_ids",
                []
            )
            or []
        )
        if value
    ]

    if class_name:
        students = _class_students(
            school_id,
            class_name,
        )
    elif student_ids:
        students = list(
            collection(
                STUDENTS
            ).find(
                {
                    "_id": {
                        "$in": [
                            _oid(
                                value
                            )
                            for value in student_ids
                        ]
                    },
                    "school_id": school_id,
                    "status": "active",
                }
            )
        )
    else:
        raise APIError(
            "Provide class_name or student_ids.",
            422,
            "validation_error",
        )

    if not students:
        raise APIError(
            "No active students were found for report generation.",
            404,
            "students_not_found",
        )

    # All students should belong to the same report curriculum.
    curriculum = _resolve_curriculum(
        school_id,
        students[0],
        data,
    )

    target_ids = [
        str(
            student["_id"]
        )
        for student in students
    ]

    assessment_query: dict[str, Any] = {
        "school_id": school_id,
        "student_id": {
            "$in": target_ids
        },
    }

    academic_year = _text(
        data.get(
            "academic_year"
        )
    )

    term = _text(
        data.get(
            "term"
        )
    )

    assessment_name = _text(
        data.get(
            "assessment_name"
        )
    )

    assessment_type = (
        _lower(
            data.get(
                "assessment_type",
                "exam",
            )
        )
        or "exam"
    )

    if academic_year:
        assessment_query[
            "academic_year"
        ] = academic_year

    if term:
        assessment_query[
            "term"
        ] = term

    if assessment_name:
        assessment_query[
            "assessment_name"
        ] = assessment_name

    assessment_query[
        "assessment_type"
    ] = assessment_type

    assessments = list(
        collection(
            ASSESSMENTS
        )
        .find(
            assessment_query
        )
        .sort(
            [
                (
                    "assessment_date",
                    -1,
                ),
                (
                    "updated_at",
                    -1,
                ),
                (
                    "created_at",
                    -1,
                ),
            ]
        )
    )

    attendance_map = {}

    if _safe_bool(
        data.get(
            "include_attendance"
        ),
        True,
    ):
        attendance_map = _attendance_for_students(
            school_id,
            target_ids,
        )

    ranking_enabled = _safe_bool(
        data.get(
            "ranking_enabled"
        ),
        False,
    )

    reports = generate_class_exam_reports(
        students,
        assessments,
        curriculum=curriculum,
        academic_year=academic_year or None,
        term=term or None,
        assessment_name=assessment_name or None,
        assessment_type=assessment_type,
        grading_scale=data.get(
            "grading_scale"
        ),
        performance_scale=data.get(
            "performance_scale"
        ),
        attendance_by_student=attendance_map,
        report_branding=_report_branding(
            member
        ),
        teacher_remarks=_text(
            data.get(
                "teacher_remarks"
            )
        ),
        principal_remarks=_text(
            data.get(
                "principal_remarks"
            )
        ),
        ranking_enabled=ranking_enabled,
    )

    saved = []

    students_by_id = {
        str(
            student["_id"]
        ): student
        for student in students
    }

    for report in reports:
        student_id = str(
            report.get(
                "student_id"
            )
        )

        student = students_by_id.get(
            student_id
        )

        if not student:
            continue

        report[
            "education_level"
        ] = curriculum.get(
            "education_level"
        )

        report[
            "grade"
        ] = curriculum.get(
            "grade"
        )

        report[
            "pathway"
        ] = curriculum.get(
            "pathway"
        )

        report[
            "track"
        ] = curriculum.get(
            "track"
        )

        report[
            "assessment_framework"
        ] = curriculum.get(
            "assessment_framework",
            "cbc",
        )

        checked = validate_generated_report(
            report,
            curriculum,
        )

        if not checked.get(
            "valid"
        ):
            raise APIError(
                f"Generated report for {student.get('full_name', student_id)} "
                "failed validation.",
                422,
                "report_validation_failed",
            )

        document = exam_report_document(
            user_id,
            school_id,
            student,
            report,
        )

        identity = {
            "school_id": school_id,
            "student_id": student_id,
            "academic_year": _text(
                report.get(
                    "academic_year"
                )
            ),
            "term": _text(
                report.get(
                    "term"
                )
            ),
            "assessment_name": _text(
                report.get(
                    "assessment_name"
                )
            ),
            "assessment_type": _lower(
                report.get(
                    "assessment_type",
                    "exam",
                )
            ),
        }

        existing = collection(
            EXAM_REPORTS
        ).find_one(
            identity
        )

        if existing:
            document[
                "created_at"
            ] = existing.get(
                "created_at",
                document[
                    "created_at"
                ],
            )

            document[
                "status"
            ] = existing.get(
                "status",
                document[
                    "status"
                ],
            )

            updated = collection(
                EXAM_REPORTS
            ).find_one_and_update(
                {
                    "_id": existing[
                        "_id"
                    ],
                    "school_id": school_id,
                },
                {
                    "$set": {
                        **document,
                        "updated_at": datetime.now(
                            timezone.utc
                        ),
                    }
                },
                return_document=ReturnDocument.AFTER,
            )

            saved.append(
                _doc(
                    updated
                )
            )

        else:
            result = collection(
                EXAM_REPORTS
            ).insert_one(
                document
            )

            document[
                "_id"
            ] = result.inserted_id

            saved.append(
                _doc(
                    document
                )
            )

    log_action(
        user_id,
        "elimu.exam_reports.generated",
        "exam_report_batch",
        None,
        {
            "count": len(
                saved
            ),
            "class_name": class_name,
            "academic_year": academic_year,
            "term": term,
            "assessment_name": assessment_name,
        },
    )

    return {
        "school_id": school_id,
        "count": len(
            saved
        ),
        "class_name": class_name or None,
        "academic_year": academic_year,
        "term": term,
        "assessment_name": assessment_name,
        "ranking_enabled": ranking_enabled,
        "reports": saved,
    }


# =========================================================
# EXAM REPORT LISTING
# =========================================================

def exam_reports(
    user_id: str,
    *,
    student_id: str | None = None,
    class_name: str | None = None,
    academic_year: str | None = None,
    term: str | None = None,
    assessment_name: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    Retrieve generated exam reports belonging to the school.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    limit = max(
        1,
        min(
            _safe_int(
                limit,
                100,
            ),
            500,
        ),
    )

    query: dict[str, Any] = {
        "school_id": school_id,
    }

    if student_id:
        query[
            "student_id"
        ] = str(
            student_id
        )

    if class_name:
        query[
            "class_name"
        ] = _text(
            class_name
        )

    if academic_year:
        query[
            "academic_year"
        ] = _text(
            academic_year
        )

    if term:
        query[
            "term"
        ] = _text(
            term
        )

    if assessment_name:
        query[
            "assessment_name"
        ] = _text(
            assessment_name
        )

    if status:
        query[
            "status"
        ] = _lower(
            status
        )

    docs = (
        collection(
            EXAM_REPORTS
        )
        .find(
            query
        )
        .sort(
            [
                (
                    "created_at",
                    -1,
                ),
                (
                    "student_name",
                    1,
                ),
            ]
        )
        .limit(
            limit
        )
    )

    return _many(
        docs
    )


def get_exam_report(
    user_id: str,
    report_id: str,
) -> dict:
    """
    Retrieve one generated learner report.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    doc = collection(
        EXAM_REPORTS
    ).find_one(
        {
            "_id": _oid(
                report_id
            ),
            "school_id": school_id,
        }
    )

    if not doc:
        raise APIError(
            "Exam report not found.",
            404,
            "exam_report_not_found",
        )

    return _doc(
        doc
    )


# =========================================================
# PUBLISH EXAM REPORT
# =========================================================

def publish_exam_report(
    user_id: str,
    report_id: str,
) -> dict:
    """
    Publish one generated learner report.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    existing = collection(
        EXAM_REPORTS
    ).find_one(
        {
            "_id": _oid(
                report_id
            ),
            "school_id": school_id,
        }
    )

    if not existing:
        raise APIError(
            "Exam report not found.",
            404,
            "exam_report_not_found",
        )

    if existing.get(
        "status"
    ) == "archived":
        raise APIError(
            "Archived exam reports cannot be published.",
            409,
            "report_archived",
        )

    update = published_report_fields(
        user_id
    )

    document = collection(
        EXAM_REPORTS
    ).find_one_and_update(
        {
            "_id": existing[
                "_id"
            ],
            "school_id": school_id,
        },
        {
            "$set": update
        },
        return_document=ReturnDocument.AFTER,
    )

    log_action(
        user_id,
        "elimu.exam_report.published",
        "exam_report",
        document[
            "_id"
        ],
    )

    return _doc(
        document
    )


# =========================================================
# POST-EXAM PROGRAMME
# =========================================================

def generate_programme(
    user_id: str,
    data: Mapping[str, Any],
) -> dict:
    """
    Generate and persist a post-examination school programme.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    try:
        generated = generate_post_exam_programme(
            start_date=_text(
                data.get(
                    "start_date"
                )
            ),
            end_date=_text(
                data.get(
                    "end_date"
                )
            ),
            activities=data.get(
                "activities",
                [],
            ),
            title=(
                _text(
                    data.get(
                        "title"
                    )
                )
                or "Post-Examination School Programme"
            ),
            academic_year=_text(
                data.get(
                    "academic_year"
                )
            ) or None,
            term=_text(
                data.get(
                    "term"
                )
            ) or None,
            daily_start_time=(
                _text(
                    data.get(
                        "daily_start_time"
                    )
                )
                or "08:00"
            ),
            daily_end_time=(
                _text(
                    data.get(
                        "daily_end_time"
                    )
                )
                or "16:00"
            ),
            avoid_weekends=_safe_bool(
                data.get(
                    "avoid_weekends"
                ),
                True,
            ),
            target_classes=data.get(
                "target_classes",
                [],
            ),
            target_students=data.get(
                "target_students",
                [],
            ),
        )

    except ReportGenerationError as exc:
        raise APIError(
            str(exc),
            422,
            "programme_generation_failed",
        ) from exc

    document = programme_document(
        user_id,
        school_id,
        generated,
    )

    result = collection(
        PROGRAMMES
    ).insert_one(
        document
    )

    document[
        "_id"
    ] = result.inserted_id

    log_action(
        user_id,
        "elimu.programme.generated",
        "programme",
        result.inserted_id,
        {
            "programme_type": generated.get(
                "programme_type"
            ),
            "academic_year": generated.get(
                "academic_year"
            ),
            "term": generated.get(
                "term"
            ),
        },
    )

    return _doc(
        document
    )


def programmes(
    user_id: str,
    *,
    academic_year: str | None = None,
    term: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    List generated school programmes.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    limit = max(
        1,
        min(
            _safe_int(
                limit,
                100,
            ),
            500,
        ),
    )

    query: dict[str, Any] = {
        "school_id": school_id,
    }

    if academic_year:
        query[
            "academic_year"
        ] = _text(
            academic_year
        )

    if term:
        query[
            "term"
        ] = _text(
            term
        )

    if status:
        query[
            "status"
        ] = _lower(
            status
        )

    docs = (
        collection(
            PROGRAMMES
        )
        .find(
            query
        )
        .sort(
            [
                (
                    "created_at",
                    -1,
                )
            ]
        )
        .limit(
            limit
        )
    )

    return _many(
        docs
    )


def get_programme(
    user_id: str,
    programme_id: str,
) -> dict:
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    doc = collection(
        PROGRAMMES
    ).find_one(
        {
            "_id": _oid(
                programme_id
            ),
            "school_id": school_id,
        }
    )

    if not doc:
        raise APIError(
            "Programme not found.",
            404,
            "programme_not_found",
        )

    return _doc(
        doc
    )


def publish_programme(
    user_id: str,
    programme_id: str,
) -> dict:
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    existing = collection(
        PROGRAMMES
    ).find_one(
        {
            "_id": _oid(
                programme_id
            ),
            "school_id": school_id,
        }
    )

    if not existing:
        raise APIError(
            "Programme not found.",
            404,
            "programme_not_found",
        )

    if existing.get(
        "status"
    ) == "archived":
        raise APIError(
            "Archived programmes cannot be published.",
            409,
            "programme_archived",
        )

    document = collection(
        PROGRAMMES
    ).find_one_and_update(
        {
            "_id": existing[
                "_id"
            ],
            "school_id": school_id,
        },
        {
            "$set": published_programme_fields(
                user_id
            )
        },
        return_document=ReturnDocument.AFTER,
    )

    log_action(
        user_id,
        "elimu.programme.published",
        "programme",
        document[
            "_id"
        ],
    )

    return _doc(
        document
    )


# =========================================================
# COMBINED REPORT DASHBOARD
# =========================================================

def dashboard(
    user_id: str,
) -> dict[str, Any]:
    """
    Combined reporting dashboard.

    This is still a reporting dashboard, but exam reports and
    curriculum configuration are now first-class parts of it.
    """
    member = _school_document(
        user_id
    )

    school_id = _school_id(
        member
    )

    school_query = {
        "school_id": school_id,
    }

    active_query = {
        **school_query,
        "status": {
            "$ne": "inactive",
        },
    }

    return {
        "school_id": school_id,

        "overview": {
            "students": collection(
                STUDENTS
            ).count_documents(
                active_query
            ),

            "classes": collection(
                CLASSES
            ).count_documents(
                active_query
            ),

            "staff": collection(
                SCHOOL_MEMBERS
            ).count_documents(
                {
                    **school_query,
                    "status": "active",
                }
            ),

            "fees": collection(
                FEES
            ).count_documents(
                school_query
            ),

            "attendance": collection(
                ATTENDANCE
            ).count_documents(
                school_query
            ),

            "assessments": collection(
                ASSESSMENTS
            ).count_documents(
                school_query
            ),

            "exam_reports": collection(
                EXAM_REPORTS
            ).count_documents(
                school_query
            ),
        },

        "timetable": timetable(
            user_id
        ),

        "curricula": {
            "count": collection(
                SCHOOL_CURRICULA
            ).count_documents(
                school_query
            ),
        },

        "programmes": {
            "count": collection(
                PROGRAMMES
            ).count_documents(
                school_query
            ),
        },
    }