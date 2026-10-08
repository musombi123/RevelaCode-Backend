# backend/jumuiya/elimu/staff/schemas.py

from __future__ import annotations

import re
from typing import Any

from backend.jumuiya.elimu.permissions import (
    PERMISSIONS,
    ROLE_BURSAR,
    ROLE_REGISTRAR,
    ROLE_TEACHER,
    ROLE_PERMISSIONS,
)

from .models import (
    EMPLOYMENT_TYPES,
    STAFF_GENDERS,
    WORKING_DAYS,
)


# =========================================================
# ROLES
# =========================================================

ROLES = {
    ROLE_BURSAR,
    ROLE_REGISTRAR,
    ROLE_TEACHER,
}

ALL_ROLES = {
    "owner",
    ROLE_BURSAR,
    ROLE_REGISTRAR,
    ROLE_TEACHER,
}


# =========================================================
# STAFF STATUSES
# =========================================================

STAFF_STATUSES = {
    "active",
    "suspended",
    "removed",
}


# =========================================================
# ASSIGNMENT STATUSES
# =========================================================

ASSIGNMENT_STATUSES = {
    "active",
    "inactive",
}


# =========================================================
# LIMITS
# =========================================================

MAX_CLASS_IDS = 200
MAX_PERMISSIONS = 100

MAX_SUBJECTS = 100
MAX_LEARNING_AREA_IDS = 100
MAX_GRADE_LEVELS = 50

MAX_METADATA_KEYS = 50

MAX_EMAIL_LENGTH = 160
MAX_TOKEN_LENGTH = 500

MAX_NAME_LENGTH = 160
MAX_PHONE_LENGTH = 50
MAX_JOB_TITLE_LENGTH = 160
MAX_DEPARTMENT_LENGTH = 160
MAX_QUALIFICATION_LENGTH = 250
MAX_SPECIALIZATION_LENGTH = 250
MAX_LICENSE_LENGTH = 120
MAX_EMPLOYEE_NUMBER_LENGTH = 100

MAX_PREFERRED_PERIODS = 100
MAX_AVOID_PERIODS = 100
MAX_BLOCKED_SLOTS = 100
MAX_WEEKDAYS = 7

MAX_AVAILABILITY_RANGES_PER_DAY = 20

MAX_REPORT_TEXT = 500
MAX_NOTES_LENGTH = 2000

MAX_WORKLOAD_VALUE = 168


# =========================================================
# REGEX
# =========================================================

TIME_PATTERN = re.compile(
    r"^([01]\d|2[0-3]):([0-5]\d)$"
)


# =========================================================
# BASIC HELPERS
# =========================================================

def _object(
    data: Any,
) -> dict:
    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "JSON object is required."
        )

    return data


def _text(
    value: Any,
    *,
    name: str,
    max_len: int = 500,
) -> str:
    if value is None:
        return ""

    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            f"{name} must be text."
        )

    value = value.strip()

    if len(value) > max_len:
        raise ValueError(
            f"{name} must not exceed "
            f"{max_len} characters."
        )

    return value


def _required(
    data: dict,
    key: str,
    *,
    max_len: int = 500,
) -> str:
    value = _text(
        data.get(key),
        name=key,
        max_len=max_len,
    )

    if not value:
        raise ValueError(
            f"{key} is required."
        )

    return value


def _bool(
    value: Any,
    *,
    name: str,
    default: bool = False,
) -> bool:
    if value is None:
        return default

    if isinstance(
        value,
        bool,
    ):
        return value

    if isinstance(
        value,
        str,
    ):
        normalized = value.strip().lower()

        if normalized in {
            "true",
            "1",
            "yes",
            "y",
            "on",
        }:
            return True

        if normalized in {
            "false",
            "0",
            "no",
            "n",
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

    raise ValueError(
        f"{name} must be boolean."
    )


def _integer(
    value: Any,
    *,
    name: str,
    default: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    if value is None:
        return default

    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            f"{name} must be a whole number."
        )

    try:
        number = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            f"{name} must be a whole number."
        )

    if (
        minimum is not None
        and number < minimum
    ):
        raise ValueError(
            f"{name} must be at least "
            f"{minimum}."
        )

    if (
        maximum is not None
        and number > maximum
    ):
        raise ValueError(
            f"{name} must not exceed "
            f"{maximum}."
        )

    return number


def _dict(
    value: Any,
    *,
    name: str,
    max_keys: int,
) -> dict:
    if value is None:
        return {}

    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            f"{name} must be an object."
        )

    if len(value) > max_keys:
        raise ValueError(
            f"{name} cannot contain more than "
            f"{max_keys} fields."
        )

    return dict(
        value
    )


# =========================================================
# LIST HELPERS
# =========================================================

def _normalize_list(
    value: Any,
    *,
    key: str,
    maximum: int,
    item_max_len: int = 200,
    lowercase: bool = False,
) -> list[str]:
    if value is None:
        return []

    if isinstance(
        value,
        str,
    ):
        value = [
            value
        ]

    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            f"{key} must be a list."
        )

    if len(value) > maximum:
        raise ValueError(
            f"{key} cannot contain more than "
            f"{maximum} items."
        )

    output: list[str] = []

    for item in value:
        normalized = _text(
            item,
            name=key,
            max_len=item_max_len,
        )

        if lowercase:
            normalized = normalized.lower()

        if not normalized:
            continue

        if normalized not in output:
            output.append(
                normalized
            )

    return output


def _class_ids(
    value: Any,
) -> list[str]:
    return _normalize_list(
        value,
        key="assigned_class_ids",
        maximum=MAX_CLASS_IDS,
        item_max_len=120,
    )


def _subjects(
    value: Any,
) -> list[str]:
    return _normalize_list(
        value,
        key="subjects",
        maximum=MAX_SUBJECTS,
        item_max_len=160,
    )


def _learning_area_ids(
    value: Any,
) -> list[str]:
    return _normalize_list(
        value,
        key="learning_area_ids",
        maximum=MAX_LEARNING_AREA_IDS,
        item_max_len=160,
    )


def _grade_levels(
    value: Any,
) -> list[str]:
    return _normalize_list(
        value,
        key="grade_levels",
        maximum=MAX_GRADE_LEVELS,
        item_max_len=100,
        lowercase=True,
    )


def _metadata(
    value: Any,
) -> dict:
    return _dict(
        value,
        name="metadata",
        max_keys=MAX_METADATA_KEYS,
    )


# =========================================================
# EMAIL / ROLE / PERMISSIONS
# =========================================================

def _email(
    value: Any,
) -> str:
    value = _text(
        value,
        name="email",
        max_len=MAX_EMAIL_LENGTH,
    ).lower()

    if not value:
        return ""

    if (
        "@" not in value
        or value.startswith("@")
        or value.endswith("@")
        or " " in value
        or value.count("@") != 1
    ):
        raise ValueError(
            "email must be a valid email address."
        )

    local, domain = value.split(
        "@",
        1,
    )

    if not local or not domain:
        raise ValueError(
            "email must be a valid email address."
        )

    return value


def _role(
    value: Any,
) -> str:
    value = _text(
        value,
        name="role",
        max_len=60,
    ).lower()

    if value not in ALL_ROLES:
        raise ValueError(
            "Invalid Elimu role."
        )

    return value


def _staff_role(
    value: Any,
) -> str:
    role = _role(
        value
    )

    if role == "owner":
        raise ValueError(
            "Owner cannot be managed through staff management."
        )

    return role


def _permissions(
    value: Any,
    *,
    role: str,
    strict_role_check: bool = True,
) -> list[str]:
    permissions = _normalize_list(
        value,
        key="permissions",
        maximum=MAX_PERMISSIONS,
        item_max_len=120,
    )

    if not permissions:
        return []

    known = set(
        PERMISSIONS
    )

    invalid = [
        permission
        for permission in permissions
        if permission not in known
    ]

    if invalid:
        raise ValueError(
            "permissions contains unknown Elimu permissions."
        )

    if not strict_role_check:
        return permissions

    allowed_for_role = set(
        ROLE_PERMISSIONS.get(
            role,
            set(),
        )
    )

    outside_role = [
        permission
        for permission in permissions
        if permission not in allowed_for_role
    ]

    if outside_role:
        raise ValueError(
            "permissions contains permissions "
            "outside the selected role."
        )

    return permissions


# =========================================================
# TIME
# =========================================================

def _time(
    value: Any,
    *,
    name: str,
) -> str:
    normalized = _text(
        value,
        name=name,
        max_len=10,
    )

    if not normalized:
        return ""

    if not TIME_PATTERN.match(
        normalized
    ):
        raise ValueError(
            f"{name} must use HH:MM 24-hour format."
        )

    return normalized


def _optional_time(
    value: Any,
    *,
    name: str,
) -> str | None:
    normalized = _time(
        value,
        name=name,
    )

    return (
        normalized
        or None
    )


def _weekdays(
    value: Any,
    *,
    name: str,
) -> list[str]:
    values = _normalize_list(
        value,
        key=name,
        maximum=MAX_WEEKDAYS,
        item_max_len=20,
        lowercase=True,
    )

    valid = set(
        WORKING_DAYS
    )

    invalid = [
        day
        for day in values
        if day not in valid
    ]

    if invalid:
        raise ValueError(
            f"{name} contains an invalid weekday."
        )

    return values


# =========================================================
# AVAILABILITY
# =========================================================

def _availability(
    value: Any,
) -> dict:
    availability = _dict(
        value,
        name="availability",
        max_keys=MAX_WEEKDAYS,
    )

    result: dict[str, list[dict]] = {}

    valid_days = set(
        WORKING_DAYS
    )

    for raw_day, raw_ranges in availability.items():
        day = _text(
            raw_day,
            name="availability weekday",
            max_len=20,
        ).lower()

        if day not in valid_days:
            raise ValueError(
                f"Invalid availability weekday: {day}."
            )

        if raw_ranges is None:
            result[day] = []
            continue

        if not isinstance(
            raw_ranges,
            list,
        ):
            raise ValueError(
                f"Availability for {day} must be a list."
            )

        if len(raw_ranges) > MAX_AVAILABILITY_RANGES_PER_DAY:
            raise ValueError(
                f"Availability for {day} cannot contain "
                f"more than {MAX_AVAILABILITY_RANGES_PER_DAY} ranges."
            )

        ranges: list[dict] = []

        for item in raw_ranges:
            item = _object(
                item
            )

            start_time = _required(
                item,
                "start_time",
                max_len=10,
            )

            start_time = _time(
                start_time,
                name=f"{day}.start_time",
            )

            end_time = _required(
                item,
                "end_time",
                max_len=10,
            )

            end_time = _time(
                end_time,
                name=f"{day}.end_time",
            )

            if start_time >= end_time:
                raise ValueError(
                    f"{day} availability start_time "
                    "must be before end_time."
                )

            ranges.append(
                {
                    "start_time": start_time,
                    "end_time": end_time,
                    "label": (
                        _text(
                            item.get("label"),
                            name=f"{day}.label",
                            max_len=120,
                        )
                        or None
                    ),
                }
            )

        result[day] = ranges

    return result


# =========================================================
# IDENTITY PROFILE
# =========================================================

def identity_payload(
    value: Any,
    *,
    email_fallback: str | None = None,
) -> dict:
    data = _object(
        value or {}
    )

    email = _email(
        data.get(
            "email",
            email_fallback,
        )
    )

    return {
        "display_name": (
            _text(
                data.get("display_name"),
                name="display_name",
                max_len=MAX_NAME_LENGTH,
            )
            or None
        ),
        "first_name": (
            _text(
                data.get("first_name"),
                name="first_name",
                max_len=100,
            )
            or None
        ),
        "middle_name": (
            _text(
                data.get("middle_name"),
                name="middle_name",
                max_len=100,
            )
            or None
        ),
        "last_name": (
            _text(
                data.get("last_name"),
                name="last_name",
                max_len=100,
            )
            or None
        ),
        "preferred_name": (
            _text(
                data.get("preferred_name"),
                name="preferred_name",
                max_len=120,
            )
            or None
        ),
        "email": email,
        "phone": (
            _text(
                data.get("phone"),
                name="phone",
                max_len=MAX_PHONE_LENGTH,
            )
            or None
        ),
        "gender": _choice(
            data.get("gender"),
            STAFF_GENDERS,
            field_name="gender",
            allow_empty=True,
        ),
        "date_of_birth": (
            _text(
                data.get("date_of_birth"),
                name="date_of_birth",
                max_len=30,
            )
            or None
        ),
        "postal_address": (
            _text(
                data.get("postal_address"),
                name="postal_address",
                max_len=300,
            )
            or None
        ),
        "avatar_url": (
            _text(
                data.get("avatar_url"),
                name="avatar_url",
                max_len=1000,
            )
            or None
        ),
    }


# =========================================================
# EMPLOYMENT PROFILE
# =========================================================

def employment_payload(
    value: Any,
) -> dict:
    data = _object(
        value or {}
    )

    employment_type = _text(
        data.get(
            "employment_type",
            "permanent",
        ),
        name="employment_type",
        max_len=40,
    ).lower()

    if employment_type not in set(
        EMPLOYMENT_TYPES
    ):
        raise ValueError(
            "Invalid employment_type."
        )

    return {
        "employee_number": (
            _text(
                data.get("employee_number")
                or data.get("staff_number"),
                name="employee_number",
                max_len=MAX_EMPLOYEE_NUMBER_LENGTH,
            )
            or None
        ),
        "job_title": (
            _text(
                data.get("job_title"),
                name="job_title",
                max_len=MAX_JOB_TITLE_LENGTH,
            )
            or None
        ),
        "department": (
            _text(
                data.get("department"),
                name="department",
                max_len=MAX_DEPARTMENT_LENGTH,
            )
            or None
        ),
        "employment_type": employment_type,
        "hire_date": (
            _text(
                data.get("hire_date"),
                name="hire_date",
                max_len=30,
            )
            or None
        ),
        "end_date": (
            _text(
                data.get("end_date"),
                name="end_date",
                max_len=30,
            )
            or None
        ),
        "highest_qualification": (
            _text(
                data.get("highest_qualification"),
                name="highest_qualification",
                max_len=MAX_QUALIFICATION_LENGTH,
            )
            or None
        ),
        "specialization": (
            _text(
                data.get("specialization"),
                name="specialization",
                max_len=MAX_SPECIALIZATION_LENGTH,
            )
            or None
        ),
        "license_number": (
            _text(
                data.get("license_number"),
                name="license_number",
                max_len=MAX_LICENSE_LENGTH,
            )
            or None
        ),
        "supervisor_user_id": (
            _text(
                data.get("supervisor_user_id"),
                name="supervisor_user_id",
                max_len=120,
            )
            or None
        ),
        "notes": (
            _text(
                data.get("notes"),
                name="notes",
                max_len=MAX_NOTES_LENGTH,
            )
            or None
        ),
    }


# =========================================================
# WORKLOAD
# =========================================================

def workload_payload(
    value: Any,
) -> dict:
    data = _dict(
        value,
        name="workload",
        max_keys=10,
    )

    return {
        "max_periods_per_day": _integer(
            data.get(
                "max_periods_per_day"
            ),
            name="max_periods_per_day",
            default=8,
            minimum=1,
            maximum=24,
        ),
        "max_periods_per_week": _integer(
            data.get(
                "max_periods_per_week"
            ),
            name="max_periods_per_week",
            default=None,
            minimum=1,
            maximum=MAX_WORKLOAD_VALUE,
        ),
        "max_consecutive_periods": _integer(
            data.get(
                "max_consecutive_periods"
            ),
            name="max_consecutive_periods",
            default=None,
            minimum=1,
            maximum=24,
        ),
        "minimum_periods_per_week": _integer(
            data.get(
                "minimum_periods_per_week"
            ),
            name="minimum_periods_per_week",
            default=None,
            minimum=0,
            maximum=MAX_WORKLOAD_VALUE,
        ),
    }


# =========================================================
# TEACHING PROFILE
# =========================================================

def teaching_payload(
    value: Any,
    *,
    assigned_class_ids: Any = None,
) -> dict:
    data = _object(
        value or {}
    )

    if assigned_class_ids is not None:
        classes = _class_ids(
            assigned_class_ids
        )
    else:
        classes = _class_ids(
            data.get(
                "assigned_class_ids"
            )
        )

    return {
        "subjects": _subjects(
            data.get(
                "subjects",
                [],
            )
        ),
        "learning_area_ids": _learning_area_ids(
            data.get(
                "learning_area_ids",
                data.get(
                    "learning_areas",
                    [],
                ),
            )
        ),
        "assigned_class_ids": classes,
        "grade_levels": _grade_levels(
            data.get(
                "grade_levels",
                [],
            )
        ),
        "can_teach_multiple_classes": _bool(
            data.get(
                "can_teach_multiple_classes"
            ),
            name="can_teach_multiple_classes",
            default=True,
        ),
        "can_cover_substitution": _bool(
            data.get(
                "can_cover_substitution"
            ),
            name="can_cover_substitution",
            default=True,
        ),
        "can_supervise": _bool(
            data.get(
                "can_supervise"
            ),
            name="can_supervise",
            default=False,
        ),
        "mentor_teacher": _bool(
            data.get(
                "mentor_teacher"
            ),
            name="mentor_teacher",
            default=False,
        ),
        "workload": workload_payload(
            data.get(
                "workload"
            )
        ),
    }


# =========================================================
# TIMETABLE PROFILE
# =========================================================

def timetable_payload(
    value: Any,
) -> dict:
    data = _object(
        value or {}
    )

    preferred_days = _weekdays(
        data.get(
            "preferred_days",
            [],
        ),
        name="preferred_days",
    )

    unavailable_days = _weekdays(
        data.get(
            "unavailable_days",
            [],
        ),
        name="unavailable_days",
    )

    preferred_period_ids = _normalize_list(
        data.get(
            "preferred_period_ids",
            [],
        ),
        key="preferred_period_ids",
        maximum=MAX_PREFERRED_PERIODS,
        item_max_len=120,
    )

    avoid_period_ids = _normalize_list(
        data.get(
            "avoid_period_ids",
            [],
        ),
        key="avoid_period_ids",
        maximum=MAX_AVOID_PERIODS,
        item_max_len=120,
    )

    blocked_slots = _normalize_list(
        data.get(
            "blocked_slots",
            [],
        ),
        key="blocked_slots",
        maximum=MAX_BLOCKED_SLOTS,
        item_max_len=160,
        lowercase=True,
    )

    # A hard unavailable day overrides a preferred day.
    preferred_days = [
        day
        for day in preferred_days
        if day not in unavailable_days
    ]

    # A hard avoided period overrides a preferred period.
    preferred_period_ids = [
        period_id
        for period_id in preferred_period_ids
        if period_id not in avoid_period_ids
    ]

    return {
        "preferred_days": preferred_days,
        "unavailable_days": unavailable_days,
        "preferred_period_ids": preferred_period_ids,
        "avoid_period_ids": avoid_period_ids,
        "blocked_slots": blocked_slots,
        "availability": _availability(
            data.get(
                "availability"
            )
        ),
    }


# =========================================================
# REPORTING PROFILE
# =========================================================

def reporting_payload(
    value: Any,
) -> dict:
    data = _object(
        value or {}
    )

    return {
        "report_display_name": (
            _text(
                data.get("report_display_name"),
                name="report_display_name",
                max_len=MAX_NAME_LENGTH,
            )
            or None
        ),
        "signature_name": (
            _text(
                data.get("signature_name"),
                name="signature_name",
                max_len=MAX_NAME_LENGTH,
            )
            or None
        ),
        "can_add_teacher_remarks": _bool(
            data.get(
                "can_add_teacher_remarks"
            ),
            name="can_add_teacher_remarks",
            default=True,
        ),
        "can_publish_teacher_assessments": _bool(
            data.get(
                "can_publish_teacher_assessments"
            ),
            name="can_publish_teacher_assessments",
            default=False,
        ),
    }


# =========================================================
# FULL STAFF PROFILE
# =========================================================

def profile_payload(
    data: dict,
    *,
    email_fallback: str | None = None,
    assigned_class_ids: Any = None,
) -> dict:
    identity = identity_payload(
        data.get(
            "identity",
            {},
        ),
        email_fallback=email_fallback,
    )

    employment = employment_payload(
        data.get(
            "employment",
            {},
        )
    )

    teaching = teaching_payload(
        data.get(
            "teaching",
            {},
        ),
        assigned_class_ids=assigned_class_ids,
    )

    timetable = timetable_payload(
        data.get(
            "timetable",
            {},
        )
    )

    reporting = reporting_payload(
        data.get(
            "reporting",
            {},
        )
    )

    metadata = _metadata(
        data.get(
            "metadata"
        )
    )

    return {
        "identity": identity,
        "employment": employment,
        "teaching": teaching,
        "timetable": timetable,
        "reporting": reporting,
        "metadata": metadata,
    }


# =========================================================
# GENERIC CHOICE
# =========================================================

def _choice(
    value: Any,
    choices,
    *,
    field_name: str,
    allow_empty: bool = False,
):
    if value is None:
        return None if allow_empty else ""

    normalized = _text(
        value,
        name=field_name,
        max_len=100,
    ).lower()

    if not normalized:
        return None if allow_empty else ""

    if normalized not in set(
        choices
    ):
        raise ValueError(
            f"Invalid {field_name}."
        )

    return normalized


# =========================================================
# INVITE STAFF
# =========================================================

def invite_payload(
    data,
) -> dict:
    """
    Validate an Owner-created staff invitation.

    Backend determines:
      - school_id
      - invited_by
      - authenticated owner
      - final membership state

    Client does not control those fields.
    """

    _object(
        data
    )

    role = _staff_role(
        _required(
            data,
            "role",
            max_len=60,
        )
    )

    user_id = (
        _text(
            data.get("user_id"),
            name="user_id",
            max_len=120,
        )
        or None
    )

    email = (
        _email(
            data.get("email")
        )
        or None
    )

    if not user_id and not email:
        raise ValueError(
            "user_id or email is required."
        )

    assigned_class_ids = _class_ids(
        data.get(
            "assigned_class_ids",
            [],
        )
    )

    if (
        assigned_class_ids
        and role != ROLE_TEACHER
    ):
        raise ValueError(
            "assigned_class_ids may only be "
            "provided for teachers."
        )

    permissions = _permissions(
        data.get(
            "permissions",
            [],
        ),
        role=role,
    )

    profile = profile_payload(
        data,
        email_fallback=email,
        assigned_class_ids=assigned_class_ids,
    )

    expires_in_days = _integer(
        data.get(
            "expires_in_days",
            7,
        ),
        name="expires_in_days",
        minimum=1,
        maximum=30,
    )

    return {
        "user_id": user_id,
        "email": email,
        "role": role,

        "assigned_class_ids": (
            assigned_class_ids
        ),

        "permissions": permissions,

        "identity": profile[
            "identity"
        ],

        "employment": profile[
            "employment"
        ],

        "teaching": profile[
            "teaching"
        ],

        "timetable": profile[
            "timetable"
        ],

        "reporting": profile[
            "reporting"
        ],

        "metadata": profile[
            "metadata"
        ],

        "expires_in_days": expires_in_days,
    }


# =========================================================
# UPDATE STAFF MEMBERSHIP / PROFILE
# =========================================================

def update_payload(
    data,
) -> dict:
    """
    Validate mutable staff membership/profile fields.

    Protected fields such as:
      school_id
      user_id
      invited_by
      created_at

    are intentionally excluded.
    """

    _object(
        data
    )

    output = {}

    # -----------------------------------------------------
    # Role
    # -----------------------------------------------------

    new_role = None

    if "role" in data:
        new_role = _staff_role(
            data.get("role")
        )

        output[
            "role"
        ] = new_role

    # -----------------------------------------------------
    # Permissions
    # -----------------------------------------------------

    if "permissions" in data:

        permissions = data.get(
            "permissions"
        )

        if new_role is not None:

            output[
                "permissions"
            ] = _permissions(
                permissions,
                role=new_role,
            )

        else:
            # Existing role is authoritative and is
            # resolved again in services.py.
            output[
                "permissions"
            ] = _normalize_list(
                permissions,
                key="permissions",
                maximum=MAX_PERMISSIONS,
                item_max_len=120,
            )

            unknown = [
                permission
                for permission
                in output[
                    "permissions"
                ]
                if permission
                not in PERMISSIONS
            ]

            if unknown:
                raise ValueError(
                    "permissions contains "
                    "unknown Elimu permissions."
                )

    # -----------------------------------------------------
    # Assigned class scope
    # -----------------------------------------------------

    if "assigned_class_ids" in data:

        class_ids = _class_ids(
            data.get(
                "assigned_class_ids"
            )
        )

        output[
            "assigned_class_ids"
        ] = class_ids

    # -----------------------------------------------------
    # Status
    # -----------------------------------------------------

    if "status" in data:

        status = _text(
            data.get("status"),
            name="status",
            max_len=30,
        ).lower()

        if status not in STAFF_STATUSES:
            raise ValueError(
                "Invalid staff status."
            )

        output[
            "status"
        ] = status

    # -----------------------------------------------------
    # Profile sections
    # -----------------------------------------------------

    if "identity" in data:
        output[
            "identity"
        ] = identity_payload(
            data.get(
                "identity"
            )
        )

    if "employment" in data:
        output[
            "employment"
        ] = employment_payload(
            data.get(
                "employment"
            )
        )

    if "teaching" in data:

        teaching = teaching_payload(
            data.get(
                "teaching"
            ),
            assigned_class_ids=(
                output.get(
                    "assigned_class_ids"
                )
                if "assigned_class_ids"
                in output
                else None
            ),
        )

        output[
            "teaching"
        ] = teaching

        if (
            "assigned_class_ids"
            in output
        ):
            output[
                "teaching"
            ][
                "assigned_class_ids"
            ] = output[
                "assigned_class_ids"
            ]

    elif (
        "assigned_class_ids"
        in output
    ):
        output[
            "teaching"
        ] = teaching_payload(
            data.get(
                "teaching",
                {},
            ),
            assigned_class_ids=(
                output[
                    "assigned_class_ids"
                ]
            ),
        )

    if "timetable" in data:
        output[
            "timetable"
        ] = timetable_payload(
            data.get(
                "timetable"
            )
        )

    if "reporting" in data:
        output[
            "reporting"
        ] = reporting_payload(
            data.get(
                "reporting"
            )
        )

    if "metadata" in data:
        output[
            "metadata"
        ] = _metadata(
            data.get(
                "metadata"
            )
        )

    # -----------------------------------------------------
    # Top-level convenience fields
    # -----------------------------------------------------

    if "subjects" in data:

        subjects = _subjects(
            data.get(
                "subjects"
            )
        )

        output[
            "subjects"
        ] = subjects

        teaching = dict(
            output.get(
                "teaching",
                {},
            )
        )

        teaching[
            "subjects"
        ] = subjects

        output[
            "teaching"
        ] = teaching

    if "learning_area_ids" in data:

        learning_area_ids = _learning_area_ids(
            data.get(
                "learning_area_ids"
            )
        )

        output[
            "learning_area_ids"
        ] = learning_area_ids

        teaching = dict(
            output.get(
                "teaching",
                {},
            )
        )

        teaching[
            "learning_area_ids"
        ] = learning_area_ids

        output[
            "teaching"
        ] = teaching

    if not output:
        raise ValueError(
            "At least one field is required."
        )

    return output


# =========================================================
# ACCEPT INVITATION
# =========================================================

def accept_payload(
    data,
) -> dict:
    _object(
        data
    )

    token = _required(
        data,
        "token",
        max_len=MAX_TOKEN_LENGTH,
    )

    return {
        "token": token,
    }


# =========================================================
# TEACHER / CLASS ASSIGNMENT
# =========================================================

def assignment_payload(
    data,
) -> dict:
    _object(
        data
    )

    teacher_user_id = _required(
        data,
        "teacher_user_id",
        max_len=120,
    )

    class_id = _required(
        data,
        "class_id",
        max_len=120,
    )

    subjects = _subjects(
        data.get(
            "subjects",
            [],
        )
    )

    learning_area_ids = _learning_area_ids(
        data.get(
            "learning_area_ids",
            [],
        )
    )

    status = _text(
        data.get(
            "status",
            "active",
        ),
        name="status",
        max_len=30,
    ).lower()

    if status not in ASSIGNMENT_STATUSES:
        raise ValueError(
            "Invalid teacher assignment status."
        )

    return {
        "teacher_user_id": teacher_user_id,

        "class_id": class_id,

        "subjects": subjects,

        "learning_area_ids": (
            learning_area_ids
        ),

        "status": status,
    }