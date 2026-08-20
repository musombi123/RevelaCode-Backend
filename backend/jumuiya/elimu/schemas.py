from __future__ import annotations


def _text(data, key, required=False, max_len=500):
    value = data.get(key, "")

    if value is None:
        value = ""

    if not isinstance(value, str):
        raise ValueError(f"{key} must be text.")

    value = value.strip()

    if required and not value:
        raise ValueError(f"{key} is required.")

    if len(value) > max_len:
        raise ValueError(f"{key} is too long.")

    return value


def _number(data, key, required=False, minimum=0):
    value = data.get(key)

    if value is None and not required:
        return 0.0

    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a number.")

    if value < minimum:
        raise ValueError(
            f"{key} must be at least {minimum}."
        )

    return value


def education_profile_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    return {
        "profile_type": _text(data, "profile_type") or "student",
        "full_name": _text(data, "full_name", True, 160),
        "phone": _text(data, "phone", False, 40),
        "email": _text(data, "email", False, 160),
        "school_id": _text(data, "school_id", False, 100),
        "class_name": _text(data, "class_name", False, 100),
        "admission_number": _text(
            data,
            "admission_number",
            False,
            100,
        ),
        "county": _text(data, "county", False, 100),
        "town": _text(data, "town", False, 100),
    }


def school_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    return {
        "name": _text(data, "name", True, 200),
        "code": _text(data, "code", False, 80),
        "description": _text(data, "description", False, 1000),
        "phone": _text(data, "phone", False, 40),
        "email": _text(data, "email", False, 160),
        "location": _text(data, "location", False, 200),
        "county": _text(data, "county", False, 100),
        "school_type": _text(
            data,
            "school_type",
            False,
            50,
        ) or "primary",
    }


def class_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    return {
        "name": _text(data, "name", True, 100),
        "level": _text(data, "level", False, 100),
        "stream": _text(data, "stream", False, 50),
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


def lesson_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    materials = data.get("materials", [])

    if not isinstance(materials, list):
        raise ValueError("materials must be a list.")

    return {
        "school_id": _text(data, "school_id", False, 100),
        "subject": _text(data, "subject", True, 100),
        "title": _text(data, "title", True, 200),
        "description": _text(
            data,
            "description",
            False,
            1000,
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
            20000,
        ),
        "materials": materials,
    }


def assignment_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    return {
        "school_id": _text(data, "school_id", False, 100),
        "class_name": _text(data, "class_name", True, 100),
        "subject": _text(data, "subject", True, 100),
        "title": _text(data, "title", True, 200),
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


def fee_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    return {
        "student_user_id": _text(
            data,
            "student_user_id",
            True,
            100,
        ),
        "school_id": _text(
            data,
            "school_id",
            True,
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
        "status": _text(
            data,
            "status",
            False,
            30,
        ) or "pending",
    }


def cbc_project_payload(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")

    skills = data.get("skills", [])
    materials = data.get("materials", [])

    if not isinstance(skills, list):
        raise ValueError("skills must be a list.")

    if not isinstance(materials, list):
        raise ValueError("materials must be a list.")

    return {
        "student_user_id": _text(
            data,
            "student_user_id",
            True,
            100,
        ),
        "school_id": _text(
            data,
            "school_id",
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
        "skills": skills,
        "materials": materials,
    }