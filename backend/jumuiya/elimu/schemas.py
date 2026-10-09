# backend/jumuiya/elimu/schemas.py

from __future__ import annotations


# =========================================================
# ELIMU VALIDATION CONTRACT
# =========================================================
#
# This module is the request-validation boundary for the Elimu hub.
#
# Principles:
#   - Accept only known fields.
#   - Normalize text before it reaches services/models.
#   - Keep existing v3 payload names backward compatible.
#   - Support the v4 school, reporting, accounting and calendar
#     contracts used by Web and Android.
#   - Never trust client-supplied ownership fields such as
#     school_id, owner_user_id or created_by.
# =========================================================


# =========================================================
# HELPERS
# =========================================================

def _object(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")
    return data


def _text(
    data,
    key,
    required=False,
    max_len=500,
):
    value = data.get(key, "")

    if value is None:
        value = ""

    if not isinstance(value, str):
        raise ValueError(f"{key} must be text.")

    value = value.strip()

    if required and not value:
        raise ValueError(f"{key} is required.")

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
    value = data.get(key, default)

    if value is None:
        return default

    value = str(value).strip().lower()

    if value not in choices:
        raise ValueError(f"{key} is invalid.")

    return value


def _number(
    data,
    key,
    required=False,
    minimum=0,
    maximum=None,
):
    value = data.get(key)

    if value is None:
        if required:
            raise ValueError(f"{key} is required.")
        return None

    if isinstance(value, bool):
        raise ValueError(f"{key} must be a number.")

    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a number.")

    if value < minimum:
        raise ValueError(
            f"{key} must be at least {minimum}."
        )

    if maximum is not None and value > maximum:
        raise ValueError(
            f"{key} must not exceed {maximum}."
        )

    # Keep integers looking like integers in JSON contracts.
    if value.is_integer():
        return int(value)

    return value


def _integer(
    data,
    key,
    required=False,
    minimum=0,
    maximum=None,
):
    value = _number(
        data,
        key,
        required=required,
        minimum=minimum,
        maximum=maximum,
    )

    if value is None:
        return None

    if not float(value).is_integer():
        raise ValueError(f"{key} must be a whole number.")

    return int(value)


def _bool(
    data,
    key,
    default=False,
):
    value = data.get(key, default)

    if isinstance(value, bool):
        return value

    if value is None:
        return default

    if isinstance(value, str):
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

    if isinstance(value, (int, float)):
        return bool(value)

    raise ValueError(f"{key} must be boolean.")


def _list(
    data,
    key,
    max_items=20,
    item_max_len=200,
):
    value = data.get(key, [])

    if value is None:
        return []

    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list.")

    if len(value) > max_items:
        raise ValueError(
            f"{key} cannot contain more than {max_items} items."
        )

    output = []

    for item in value:
        if not isinstance(item, str):
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

        output.append(item)

    return list(dict.fromkeys(output))


def _dict(
    data,
    key,
    max_keys=30,
):
    value = data.get(key, {})

    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object.")

    if len(value) > max_keys:
        raise ValueError(
            f"{key} contains too many fields."
        )

    return value


def _email(
    data,
    key,
    max_len=160,
):
    value = _text(
        data,
        key,
        False,
        max_len,
    )

    if not value:
        return ""

    # Deliberately lightweight: this is a request sanity check,
    # not an email-verification mechanism.
    if (
        "@" not in value
        or value.startswith("@")
        or value.endswith("@")
        or " " in value
    ):
        raise ValueError(f"{key} must be a valid email.")

    return value


def _url(
    data,
    key,
    max_len=500,
):
    value = _text(
        data,
        key,
        False,
        max_len,
    )

    if not value:
        return ""

    if not (
        value.startswith("http://")
        or value.startswith("https://")
    ):
        raise ValueError(
            f"{key} must be a valid http(s) URL."
        )

    return value


# =========================================================
# NESTED SCHOOL SETTINGS
# =========================================================

def _report_branding(data):
    value = _dict(
        data,
        "report_branding",
        max_keys=20,
    )

    return {
        "logo_url": _url(
            value,
            "logo_url",
            500,
        ),
        "primary_color": _text(
            value,
            "primary_color",
            False,
            30,
        ),
        "secondary_color": _text(
            value,
            "secondary_color",
            False,
            30,
        ),
        "footer_text": _text(
            value,
            "footer_text",
            False,
            500,
        ),
        "watermark": _text(
            value,
            "watermark",
            False,
            200,
        ),
        "header_text": _text(
            value,
            "header_text",
            False,
            300,
        ),
        "show_motto": _bool(
            value,
            "show_motto",
            True,
        ),
        "show_contact": _bool(
            value,
            "show_contact",
            True,
        ),
    }


def _school_settings(data):
    value = _dict(
        data,
        "settings",
        max_keys=30,
    )

    return {
        "allow_parent_access": _bool(
            value,
            "allow_parent_access",
            False,
        ),
        "enable_notifications": _bool(
            value,
            "enable_notifications",
            True,
        ),
        "enable_print_center": _bool(
            value,
            "enable_print_center",
            True,
        ),
        "default_report_paper": {
            "a4": "A4",
            "a5": "A5",
            "letter": "Letter",
        }[
            _choice(
                value,
                "default_report_paper",
                {
                    "a4",
                    "a5",
                    "letter",
                },
                "a4",
            )
        ],
        "default_report_orientation": _choice(
            value,
            "default_report_orientation",
            {
                "portrait",
                "landscape",
            },
            "portrait",
        ),
        "show_signatures": _bool(
            value,
            "show_signatures",
            True,
        ),
        "include_generated_at": _bool(
            value,
            "include_generated_at",
            True,
        ),
    }


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
        "email": _email(
            data,
            "email",
        ),
        "website": _url(
            data,
            "website",
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
        "country": _text(
            data,
            "country",
            False,
            80,
        ) or "Kenya",
        "currency": _text(
            data,
            "currency",
            False,
            8,
        ).upper() or "KES",
        "timezone": _text(
            data,
            "timezone",
            False,
            80,
        ) or "Africa/Nairobi",
        "logo_url": _url(
            data,
            "logo_url",
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
        "report_branding": _report_branding(
            data,
        ),
        "settings": _school_settings(
            data,
        ),
    }

def school_application_payload(data):
    """
    Strict schema for a real-school registration application.

    This deliberately requires more information than the normal school
    profile schema. The server ignores client-provided verification states.
    """
    _object(data)

    payload = school_payload(data)

    registration_number = _text(
        data,
        "registration_number",
        True,
        100,
    )

    principal_name = _text(
        data,
        "principal_name",
        True,
        160,
    )

    phone = _text(
        data,
        "phone",
        True,
        40,
    )

    allowed_phone_characters = set(
        "+0123456789 ()-."
    )

    if any(
        character not in allowed_phone_characters
        for character in phone
    ):
        raise ValueError(
            "phone contains invalid characters."
        )

    phone_digits = "".join(
        character
        for character in phone
        if character.isdigit()
    )

    if len(phone_digits) < 7 or len(phone_digits) > 15:
        raise ValueError(
            "phone must contain between 7 and 15 digits."
        )

    email = _email(
        data,
        "email",
    )

    if not email:
        raise ValueError("email is required.")

    county = _text(
        data,
        "county",
        True,
        100,
    )

    town = _text(
        data,
        "town",
        True,
        100,
    )

    location = _text(
        data,
        "location",
        True,
        200,
    )

    evidence_url = _url(
        data,
        "registration_evidence_url",
        1000,
    )

    if not evidence_url:
        raise ValueError(
            "registration_evidence_url is required."
        )

    if not evidence_url.startswith("https://"):
        raise ValueError(
            "Registration evidence must use an HTTPS URL."
        )

    owner_declaration = _bool(
        data,
        "owner_declaration",
        False,
    )

    if owner_declaration is not True:
        raise ValueError(
            (
                "You must confirm that you are authorised to register "
                "this school and that the supplied details are accurate."
            )
        )

    payload.update({
        "registration_number": registration_number,
        "principal_name": principal_name,
        "phone": phone,
        "email": email,
        "county": county,
        "town": town,
        "location": location,
        "registration_evidence_url": evidence_url,
        "owner_declaration": True,
    })

    return payload


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
        "role": _text(
            data,
            "role",
            False,
            60,
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
        "email": _email(
            data,
            "email",
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
        "permissions": _list(
            data,
            "permissions",
            max_items=50,
            item_max_len=100,
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
        "code": _text(
            data,
            "code",
            False,
            50,
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
        "teacher_name": _text(
            data,
            "teacher_name",
            False,
            160,
        ),
        "capacity": _integer(
            data,
            "capacity",
            False,
            minimum=1,
            maximum=5000,
        ),
        "status": _choice(
            data,
            "status",
            {
                "active",
                "inactive",
                "archived",
            },
            "active",
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
        "student_code": _text(
            data,
            "student_code",
            False,
            80,
        ),
        "student_user_id": _text(
            data,
            "student_user_id",
            False,
            100,
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
        "stream": _text(
            data,
            "stream",
            False,
            50,
        ),
        "enrollment_date": _text(
            data,
            "enrollment_date",
            False,
            30,
        ),
        "leaving_date": _text(
            data,
            "leaving_date",
            False,
            30,
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
        "guardian_email": _email(
            data,
            "guardian_email",
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
        "status": _choice(
            data,
            "status",
            {
                "active",
                "inactive",
                "graduated",
                "transferred",
                "suspended",
            },
            "active",
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
        "published": _bool(
            data,
            "published",
            False,
        ),
        "status": _choice(
            data,
            "status",
            {
                "draft",
                "published",
                "archived",
            },
            "draft",
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
        "max_score": _number(
            data,
            "max_score",
            False,
            minimum=0.01,
            maximum=100000,
        ),
        "status": _choice(
            data,
            "status",
            {
                "active",
                "completed",
                "archived",
            },
            "active",
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
        "notes": _text(
            data,
            "notes",
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
        "assessment_date": _text(
            data,
            "assessment_date",
            False,
            30,
        ),
        "score": _number(
            data,
            "score",
            False,
            minimum=0,
            maximum=100000,
        ),
        "max_score": _number(
            data,
            "max_score",
            False,
            minimum=0.01,
            maximum=100000,
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
            minimum=0,
            maximum=1000000000,
        ),
        "amount_paid": _number(
            data,
            "amount_paid",
            False,
            minimum=0,
            maximum=1000000000,
        ) or 0,
        "currency": _text(
            data,
            "currency",
            False,
            8,
        ).upper() or "KES",
        "description": _text(
            data,
            "description",
            False,
            500,
        ),
        "fee_type": _text(
            data,
            "fee_type",
            False,
            80,
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
        "due_date": _text(
            data,
            "due_date",
            False,
            30,
        ),
        "payment_reference": _text(
            data,
            "payment_reference",
            False,
            120,
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
# CBC PROJECT
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
        "status": _choice(
            data,
            "status",
            {
                "active",
                "completed",
                "archived",
            },
            "active",
        ),
        "remarks": _text(
            data,
            "remarks",
            False,
            1000,
        ),
    }


# =========================================================
# EVENT RECURRENCE
# =========================================================

def _recurrence(data):
    value = _dict(
        data,
        "recurrence",
        max_keys=20,
    )

    recurrence_type = _choice(
        value,
        "type",
        {
            "none",
            "daily",
            "weekly",
            "monthly",
            "annual",
            "custom",
        },
        "none",
    )

    interval = _integer(
        value,
        "interval",
        False,
        minimum=1,
        maximum=366,
    )

    day_of_month = _integer(
        value,
        "day_of_month",
        False,
        minimum=1,
        maximum=31,
    )

    month = _integer(
        value,
        "month",
        False,
        minimum=1,
        maximum=12,
    )

    weekdays = _list(
        value,
        "weekdays",
        max_items=7,
        item_max_len=12,
    )

    until = _text(
        value,
        "until",
        False,
        50,
    )

    output = {
        "type": recurrence_type,
        "interval": interval or 1,
        "weekdays": weekdays,
        "day_of_month": day_of_month,
        "month": month,
        "until": until,
    }

    # Annual events should be represented consistently.
    if recurrence_type == "annual":
        output["interval"] = 1

    if recurrence_type == "monthly" and day_of_month is None:
        raise ValueError(
            "recurrence.day_of_month is required for monthly recurrence."
        )

    if recurrence_type == "annual":
        if month is not None and day_of_month is None:
            raise ValueError(
                "recurrence.day_of_month is required when recurrence.month is supplied."
            )

    return output


# =========================================================
# EVENTS
# =========================================================

def event_payload(data):
    _object(data)

    is_annual = _bool(
        data,
        "is_annual",
        False,
    )

    recurrence = _recurrence(
        data
    )

    # Backward compatibility:
    # is_annual=true without an explicit recurrence becomes annual.
    if is_annual and recurrence["type"] == "none":
        recurrence["type"] = "annual"

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
        "is_annual": is_annual,
        "recurrence": recurrence,
        "visibility": _choice(
            data,
            "visibility",
            {
                "school",
                "private",
                "community",
            },
            "school",
        ),
        "all_day": _bool(
            data,
            "all_day",
            False,
        ),
        "reminder_minutes": _integer(
            data,
            "reminder_minutes",
            False,
            minimum=0,
            maximum=10080,
        ) or 0,
        "calendar_year": _text(
            data,
            "calendar_year",
            False,
            30,
        ),
        "color": _text(
            data,
            "color",
            False,
            30,
        ),
    }
