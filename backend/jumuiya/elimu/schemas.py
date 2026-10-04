# backend/jumuiya/elimu/schemas.py

from __future__ import annotations


# =========================================================
# HELPERS
# =========================================================

def _object(data):
    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "JSON object required."
        )


def _text(
    data,
    key,
    required=False,
    max_len=500,
):
    value = data.get(
        key,
        "",
    )

    if value is None:
        value = ""

    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            f"{key} must be text."
        )

    value = value.strip()

    if (
        required
        and not value
    ):
        raise ValueError(
            f"{key} is required."
        )

    if len(value) > max_len:
        raise ValueError(
            f"{key} must not exceed {max_len} characters."
        )

    return value


def _choice(
    data,
    key,
    choices,
    default=None,
):
    value = data.get(
        key,
        default,
    )

    if value is None:
        return default

    value = str(
        value
    ).strip().lower()

    if value not in choices:
        raise ValueError(
            f"{key} is invalid."
        )

    return value


def _number(
    data,
    key,
    required=False,
    minimum=0,
):
    value = data.get(
        key
    )

    if value is None:

        if required:
            raise ValueError(
                f"{key} is required."
            )

        return None

    try:
        value = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            f"{key} must be a number."
        )

    if value < minimum:
        raise ValueError(
            f"{key} must be at least {minimum}."
        )

    return value


def _list(
    data,
    key,
    max_items=20,
    item_max_len=200,
):
    value = data.get(
        key,
        [],
    )

    if value is None:
        return []

    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            f"{key} must be a list."
        )

    if len(value) > max_items:
        raise ValueError(
            f"{key} cannot contain more than {max_items} items."
        )

    output = []

    for item in value:

        if not isinstance(
            item,
            str,
        ):
            raise ValueError(
                f"Each {key} item must be text."
            )

        item = item.strip()

        if not item:
            continue

        if len(item) > item_max_len:
            raise ValueError(
                f"{key} items are too long."
            )

        output.append(
            item
        )

    return list(
        dict.fromkeys(
            output
        )
    )


# =========================================================
# SCHOOL
# =========================================================

def school_payload(data):
    _object(data)

    return {
        "name": _text(
            data,
            "name",
            True,
            200,
        ),

        "code": _text(
            data,
            "code",
            False,
            80,
        ),

        "registration_number": _text(
            data,
            "registration_number",
            False,
            100,
        ),

        "description": _text(
            data,
            "description",
            False,
            2000,
        ),

        "school_type": _text(
            data,
            "school_type",
            False,
            60,
        ) or "primary",

        "motto": _text(
            data,
            "motto",
            False,
            300,
        ),

        "mission": _text(
            data,
            "mission",
            False,
            1500,
        ),

        "vision": _text(
            data,
            "vision",
            False,
            1500,
        ),

        "principal_name": _text(
            data,
            "principal_name",
            False,
            160,
        ),

        "administrator_name": _text(
            data,
            "administrator_name",
            False,
            160,
        ),

        "phone": _text(
            data,
            "phone",
            False,
            40,
        ),

        "email": _text(
            data,
            "email",
            False,
            160,
        ),

        "website": _text(
            data,
            "website",
            False,
            300,
        ),

        "postal_address": _text(
            data,
            "postal_address",
            False,
            300,
        ),

        "location": _text(
            data,
            "location",
            False,
            200,
        ),

        "county": _text(
            data,
            "county",
            False,
            100,
        ),

        "town": _text(
            data,
            "town",
            False,
            100,
        ),

        "logo_url": _text(
            data,
            "logo_url",
            False,
            500,
        ),

        "academic_year": _text(
            data,
            "academic_year",
            False,
            30,
        ),

        "current_term": _text(
            data,
            "current_term",
            False,
            50,
        ),

        "calendar_year": _text(
            data,
            "calendar_year",
            False,
            30,
        ),

        "report_branding": (
            data.get(
                "report_branding",
                {},
            )
            if isinstance(
                data.get(
                    "report_branding",
                    {},
                ),
                dict,
            )
            else {}
        ),

        "settings": (
            data.get(
                "settings",
                {},
            )
            if isinstance(
                data.get(
                    "settings",
                    {},
                ),
                dict,
            )
            else {}
        ),
    }


# =========================================================
# EDUCATION PROFILE
# =========================================================

def education_profile_payload(data):
    _object(data)

    return {
        "profile_type": _text(
            data,
            "profile_type",
            False,
            50,
        ) or "school_admin",

        "full_name": _text(
            data,
            "full_name",
            True,
            160,
        ),

        "phone": _text(
            data,
            "phone",
            False,
            40,
        ),

        "email": _text(
            data,
            "email",
            False,
            160,
        ),

        "class_name": _text(
            data,
            "class_name",
            False,
            100,
        ),

        "admission_number": _text(
            data,
            "admission_number",
            False,
            100,
        ),

        "county": _text(
            data,
            "county",
            False,
            100,
        ),

        "town": _text(
            data,
            "town",
            False,
            100,
        ),
    }


# =========================================================
# CLASS
# =========================================================

def class_payload(data):
    _object(data)

    return {
        "name": _text(
            data,
            "name",
            True,
            100,
        ),

        "level": _text(
            data,
            "level",
            False,
            100,
        ),

        "stream": _text(
            data,
            "stream",
            False,
            50,
        ),

        "academic_year": _text(
            data,
            "academic_year",
            False,
            30,
        ),

        "teacher_id": _text(
            data,
            "teacher_id",
            False,
            100,
        ),
    }


# =========================================================
# STUDENT
# =========================================================

def student_payload(data):
    _object(data)

    return {
        "admission_number": _text(
            data,
            "admission_number",
            True,
            80,
        ),

        "full_name": _text(
            data,
            "full_name",
            True,
            160,
        ),

        "gender": _text(
            data,
            "gender",
            False,
            30,
        ),

        "date_of_birth": _text(
            data,
            "date_of_birth",
            False,
            30,
        ),

        "class_id": _text(
            data,
            "class_id",
            False,
            100,
        ),

        "class_name": _text(
            data,
            "class_name",
            False,
            100,
        ),

        "guardian_name": _text(
            data,
            "guardian_name",
            False,
            160,
        ),

        "guardian_phone": _text(
            data,
            "guardian_phone",
            False,
            40,
        ),

        "guardian_email": _text(
            data,
            "guardian_email",
            False,
            160,
        ),

        "county": _text(
            data,
            "county",
            False,
            100,
        ),

        "town": _text(
            data,
            "town",
            False,
            100,
        ),

        "address": _text(
            data,
            "address",
            False,
            300,
        ),
    }


# =========================================================
# LESSON
# =========================================================

def lesson_payload(data):
    _object(data)

    return {
        "subject": _text(
            data,
            "subject",
            True,
            100,
        ),

        "title": _text(
            data,
            "title",
            True,
            200,
        ),

        "description": _text(
            data,
            "description",
            False,
            1500,
        ),

        "class_name": _text(
            data,
            "class_name",
            False,
            100,
        ),

        "content": _text(
            data,
            "content",
            False,
            30000,
        ),

        "materials": _list(
            data,
            "materials",
            30,
            300,
        ),
    }


# =========================================================
# ASSIGNMENT
# =========================================================

def assignment_payload(data):
    _object(data)

    return {
        "class_name": _text(
            data,
            "class_name",
            True,
            100,
        ),

        "subject": _text(
            data,
            "subject",
            True,
            100,
        ),

        "title": _text(
            data,
            "title",
            True,
            200,
        ),

        "description": _text(
            data,
            "description",
            False,
            3000,
        ),

        "due_date": _text(
            data,
            "due_date",
            False,
            50,
        ),
    }


# =========================================================
# ATTENDANCE
# =========================================================

def attendance_payload(data):
    _object(data)

    return {
        "student_id": _text(
            data,
            "student_id",
            True,
            100,
        ),

        "date": _text(
            data,
            "date",
            True,
            30,
        ),

        "status": _choice(
            data,
            "status",
            {
                "present",
                "absent",
                "late",
                "excused",
            },
            "present",
        ),

        "reason": _text(
            data,
            "reason",
            False,
            500,
        ),
    }


# =========================================================
# ASSESSMENT
# =========================================================

def assessment_payload(data):
    _object(data)

    return {
        "student_id": _text(
            data,
            "student_id",
            True,
            100,
        ),

        "subject": _text(
            data,
            "subject",
            True,
            100,
        ),

        "assessment_name": _text(
            data,
            "assessment_name",
            True,
            200,
        ),

        "assessment_type": _text(
            data,
            "assessment_type",
            False,
            60,
        ) or "assessment",

        "academic_year": _text(
            data,
            "academic_year",
            False,
            30,
        ),

        "term": _text(
            data,
            "term",
            False,
            50,
        ),

        "score": _number(
            data,
            "score",
            False,
            0,
        ),

        "max_score": _number(
            data,
            "max_score",
            False,
            1,
        ) or 100,

        "grade": _text(
            data,
            "grade",
            False,
            30,
        ),

        "competency_level": _text(
            data,
            "competency_level",
            False,
            100,
        ),

        "remarks": _text(
            data,
            "remarks",
            False,
            500,
        ),
    }


# =========================================================
# FEES
# =========================================================

def fee_payload(data):
    _object(data)

    return {
        "student_id": _text(
            data,
            "student_id",
            False,
            100,
        ),

        "student_user_id": _text(
            data,
            "student_user_id",
            False,
            100,
        ),

        "amount": _number(
            data,
            "amount",
            True,
        ),

        "currency": _text(
            data,
            "currency",
            False,
            8,
        ) or "KES",

        "description": _text(
            data,
            "description",
            False,
            500,
        ),

        "term": _text(
            data,
            "term",
            False,
            50,
        ),

        "academic_year": _text(
            data,
            "academic_year",
            False,
            30,
        ),

        "status": _choice(
            data,
            "status",
            {
                "pending",
                "paid",
                "partial",
                "waived",
                "overdue",
            },
            "pending",
        ),
    }


# =========================================================
# CBC
# =========================================================

def cbc_project_payload(data):
    _object(data)

    return {
        "student_user_id": _text(
            data,
            "student_user_id",
            False,
            100,
        ),

        "student_id": _text(
            data,
            "student_id",
            False,
            100,
        ),

        "title": _text(
            data,
            "title",
            True,
            200,
        ),

        "description": _text(
            data,
            "description",
            False,
            3000,
        ),

        "category": _text(
            data,
            "category",
            False,
            100,
        ),

        "skills": _list(
            data,
            "skills",
            30,
            100,
        ),

        "materials": _list(
            data,
            "materials",
            30,
            200,
        ),
    }


# =========================================================
# EVENTS
# =========================================================

def event_payload(data):
    _object(data)

    return {
        "title": _text(
            data,
            "title",
            True,
            200,
        ),

        "event_type": _text(
            data,
            "event_type",
            False,
            60,
        ) or "school",

        "description": _text(
            data,
            "description",
            False,
            2000,
        ),

        "start_date": _text(
            data,
            "start_date",
            True,
            50,
        ),

        "end_date": _text(
            data,
            "end_date",
            False,
            50,
        ),

        "location": _text(
            data,
            "location",
            False,
            200,
        ),

        "organizer": _text(
            data,
            "organizer",
            False,
            160,
        ),

        "academic_year": _text(
            data,
            "academic_year",
            False,
            30,
        ),

        "term": _text(
            data,
            "term",
            False,
            50,
        ),

        "is_annual": bool(
            data.get(
                "is_annual",
                False,
            )
        ),
    }
