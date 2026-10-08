# backend/jumuiya/elimu/staff/models.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
from typing import Any, Iterable, Mapping

from backend.jumuiya.elimu.permissions import (
    PERMISSIONS,
    ROLE_BURSAR,
    ROLE_OWNER,
    ROLE_REGISTRAR,
    ROLE_TEACHER,
)


# =========================================================
# COLLECTIONS
# =========================================================

COLLECTION = "jumuiya_elimu_school_members"
INVITATIONS = "jumuiya_elimu_staff_invitations"
TEACHER_ASSIGNMENTS = "jumuiya_elimu_teacher_assignments"


# =========================================================
# MODEL VERSION
# =========================================================

STAFF_MODEL_VERSION = "2.0"


# =========================================================
# ROLES
# =========================================================

ROLES = (
    ROLE_OWNER,
    ROLE_BURSAR,
    ROLE_REGISTRAR,
    ROLE_TEACHER,
)


# =========================================================
# MEMBERSHIP STATUSES
# =========================================================

STATUS_PENDING = "pending"
STATUS_INVITED = "invited"
STATUS_ACCEPTED = "accepted"
STATUS_ACTIVE = "active"
STATUS_SUSPENDED = "suspended"
STATUS_REMOVED = "removed"

STATUSES = (
    STATUS_PENDING,
    STATUS_INVITED,
    STATUS_ACCEPTED,
    STATUS_ACTIVE,
    STATUS_SUSPENDED,
    STATUS_REMOVED,
)


# =========================================================
# EMPLOYMENT / STAFF PROFILE CATALOGS
# =========================================================

EMPLOYMENT_TYPES = (
    "permanent",
    "contract",
    "part_time",
    "temporary",
    "intern",
    "volunteer",
    "other",
)

WORKING_DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

STAFF_GENDERS = (
    "male",
    "female",
    "other",
    "prefer_not_to_say",
)


# =========================================================
# DEFAULTS / LIMITS
# =========================================================

DEFAULT_INVITATION_EXPIRY_DAYS = 7

MAX_SUBJECTS = 100
MAX_LEARNING_AREAS = 100
MAX_CLASS_IDS = 200
MAX_METADATA_KEYS = 50
MAX_AVAILABILITY_RANGES_PER_DAY = 20
MAX_TIME_PREFERENCES = 100


# =========================================================
# TIME
# =========================================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# =========================================================
# BASIC NORMALIZATION
# =========================================================

def normalize_id(value: Any) -> str | None:
    """
    Normalize Mongo/API identifiers to stable strings.
    """

    if value is None:
        return None

    value = str(value).strip()

    return value or None


def normalize_email(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip().lower()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(
        str(value).strip().split()
    )


def normalize_optional_text(
    value: Any,
) -> str | None:
    value = normalize_text(
        value
    )

    return value or None


def normalize_bool(
    value: Any,
    default: bool = False,
) -> bool:
    """
    Safely normalize common boolean representations.

    Prevents:

        bool("false") == True
    """

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(
        value,
        (int, float),
    ):
        return bool(value)

    normalized = normalize_text(
        value
    ).lower()

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

    return default


def normalize_string_list(
    values: Iterable[Any] | None,
    *,
    maximum: int | None = None,
    lowercase: bool = False,
) -> list[str]:
    if values is None:
        return []

    if isinstance(
        values,
        str,
    ):
        values = [values]

    output: list[str] = []

    for value in values:
        normalized = normalize_text(
            value
        )

        if lowercase:
            normalized = normalized.lower()

        if not normalized:
            continue

        if normalized not in output:
            output.append(normalized)

        if (
            maximum is not None
            and len(output) > maximum
        ):
            raise ValueError(
                "List contains too many items."
            )

    return output


def normalize_class_ids(
    class_ids: Iterable[Any] | None,
) -> list[str]:
    if class_ids is None:
        return []

    if isinstance(
        class_ids,
        str,
    ):
        class_ids = [class_ids]

    output: list[str] = []

    for class_id in class_ids:
        normalized = normalize_id(
            class_id
        )

        if not normalized:
            continue

        if normalized not in output:
            output.append(normalized)

        if len(output) > MAX_CLASS_IDS:
            raise ValueError(
                f"assigned_class_ids cannot exceed "
                f"{MAX_CLASS_IDS} items."
            )

    return output


def normalize_role(
    role: Any,
) -> str:
    value = normalize_text(
        role
    ).lower()

    if value not in ROLES:
        raise ValueError(
            "Invalid Elimu staff role."
        )

    return value


def normalize_status(
    status: Any,
) -> str:
    value = normalize_text(
        status
    ).lower()

    if value not in STATUSES:
        raise ValueError(
            "Invalid Elimu membership status."
        )

    return value


def normalize_employment_type(
    value: Any,
) -> str:
    normalized = (
        normalize_text(
            value
        ).lower()
        or "permanent"
    )

    if normalized not in EMPLOYMENT_TYPES:
        raise ValueError(
            "Invalid employment type."
        )

    return normalized


def normalize_gender(
    value: Any,
) -> str | None:
    normalized = normalize_text(
        value
    ).lower()

    if not normalized:
        return None

    if normalized not in STAFF_GENDERS:
        raise ValueError(
            "Invalid staff gender."
        )

    return normalized


def normalize_permissions(
    permissions: Iterable[str] | None,
) -> list[str]:
    """
    Keep only canonical Elimu permissions and remove duplicates.

    Role enforcement remains the responsibility of permissions.py.
    This function only protects the document shape.
    """

    if permissions is None:
        return []

    allowed = set(
        PERMISSIONS
    )

    output: list[str] = []

    for permission in permissions:
        value = normalize_text(
            permission
        )

        if not value:
            continue

        if value not in allowed:
            continue

        if value not in output:
            output.append(value)

    return sorted(
        output
    )


def normalize_metadata(
    metadata: Mapping[str, Any] | None,
) -> dict:
    if metadata is None:
        return {}

    if not isinstance(
        metadata,
        Mapping,
    ):
        raise ValueError(
            "metadata must be an object."
        )

    if len(metadata) > MAX_METADATA_KEYS:
        raise ValueError(
            f"metadata cannot contain more than "
            f"{MAX_METADATA_KEYS} keys."
        )

    return {
        str(key): value
        for key, value in metadata.items()
        if str(key).strip()
    }


# =========================================================
# TIME / AVAILABILITY NORMALIZATION
# =========================================================

_TIME_RE = re.compile(
    r"^([01]\d|2[0-3]):([0-5]\d)$"
)


def normalize_time(
    value: Any,
) -> str | None:
    normalized = normalize_text(
        value
    )

    if not normalized:
        return None

    if not _TIME_RE.match(
        normalized
    ):
        raise ValueError(
            "Time must use HH:MM 24-hour format."
        )

    return normalized


def normalize_weekdays(
    values: Iterable[Any] | None,
) -> list[str]:
    days = normalize_string_list(
        values,
        lowercase=True,
    )

    for day in days:
        if day not in WORKING_DAYS:
            raise ValueError(
                f"Invalid weekday: {day}."
            )

    return days


def normalize_availability(
    availability: Mapping[str, Any] | None,
) -> dict[str, list[dict]]:
    """
    Canonical availability:

        {
            "monday": [
                {
                    "start_time": "07:30",
                    "end_time": "16:30"
                }
            ]
        }

    Empty availability means no explicit staff restriction.
    """

    if availability is None:
        return {}

    if not isinstance(
        availability,
        Mapping,
    ):
        raise ValueError(
            "availability must be an object."
        )

    result: dict[str, list[dict]] = {}

    for raw_day, raw_ranges in availability.items():
        day = normalize_text(
            raw_day
        ).lower()

        if day not in WORKING_DAYS:
            raise ValueError(
                f"Invalid availability weekday: {day}."
            )

        if raw_ranges is None:
            result[day] = []
            continue

        if (
            not isinstance(
                raw_ranges,
                Iterable,
            )
            or isinstance(
                raw_ranges,
                (str, bytes, Mapping),
            )
        ):
            raise ValueError(
                f"Availability for {day} must be an array."
            )

        ranges: list[dict] = []

        for item in raw_ranges:
            if not isinstance(
                item,
                Mapping,
            ):
                raise ValueError(
                    "Each availability range must be an object."
                )

            start_time = normalize_time(
                item.get("start_time")
            )

            end_time = normalize_time(
                item.get("end_time")
            )

            if not start_time or not end_time:
                raise ValueError(
                    "Availability ranges require "
                    "start_time and end_time."
                )

            if start_time >= end_time:
                raise ValueError(
                    f"Availability start_time must be "
                    f"before end_time for {day}."
                )

            ranges.append(
                {
                    "start_time": start_time,
                    "end_time": end_time,
                    "label": normalize_optional_text(
                        item.get("label")
                    ),
                }
            )

            if (
                len(ranges)
                > MAX_AVAILABILITY_RANGES_PER_DAY
            ):
                raise ValueError(
                    f"Availability cannot contain more than "
                    f"{MAX_AVAILABILITY_RANGES_PER_DAY} ranges per day."
                )

        result[day] = ranges

    return result


# =========================================================
# PROFILE NORMALIZATION
# =========================================================

def normalize_identity(
    identity: Mapping[str, Any] | None = None,
    *,
    email: Any = None,
) -> dict:
    source = dict(
        identity or {}
    )

    normalized_email = normalize_email(
        source.get(
            "email",
            email,
        )
    )

    first_name = normalize_optional_text(
        source.get("first_name")
    )

    middle_name = normalize_optional_text(
        source.get("middle_name")
    )

    last_name = normalize_optional_text(
        source.get("last_name")
    )

    preferred_name = normalize_optional_text(
        source.get("preferred_name")
    )

    display_name = normalize_optional_text(
        source.get("display_name")
    )

    if not display_name:
        display_name = (
            " ".join(
                part
                for part in (
                    first_name,
                    middle_name,
                    last_name,
                )
                if part
            )
            or preferred_name
        )

    return {
        "display_name": display_name or "",
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "preferred_name": preferred_name,
        "email": normalized_email,
        "phone": normalize_optional_text(
            source.get("phone")
        ),
        "gender": normalize_gender(
            source.get("gender")
        ),
        "date_of_birth": normalize_optional_text(
            source.get("date_of_birth")
        ),
        "postal_address": normalize_optional_text(
            source.get("postal_address")
        ),
        "avatar_url": normalize_optional_text(
            source.get("avatar_url")
        ),
    }


def normalize_employment(
    employment: Mapping[str, Any] | None = None,
) -> dict:
    source = dict(
        employment or {}
    )

    return {
        "employee_number": normalize_optional_text(
            source.get("employee_number")
            or source.get("staff_number")
        ),
        "job_title": normalize_optional_text(
            source.get("job_title")
        ),
        "department": normalize_optional_text(
            source.get("department")
        ),
        "employment_type": normalize_employment_type(
            source.get("employment_type")
        ),
        "hire_date": normalize_optional_text(
            source.get("hire_date")
        ),
        "end_date": normalize_optional_text(
            source.get("end_date")
        ),
        "highest_qualification": normalize_optional_text(
            source.get("highest_qualification")
        ),
        "specialization": normalize_optional_text(
            source.get("specialization")
        ),
        "license_number": normalize_optional_text(
            source.get("license_number")
        ),
        "supervisor_user_id": normalize_id(
            source.get("supervisor_user_id")
        ),
        "notes": normalize_optional_text(
            source.get("notes")
        ),
    }


def normalize_workload(
    workload: Mapping[str, Any] | None,
) -> dict:
    source = dict(
        workload or {}
    )

    def _number(
        key: str,
        default: int | None = None,
        minimum: int = 0,
        maximum: int = 168,
    ) -> int | None:
        value = source.get(
            key,
            default,
        )

        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                f"{key} must be a whole number."
            )

        try:
            value = int(value)
        except (
            TypeError,
            ValueError,
        ):
            raise ValueError(
                f"{key} must be a whole number."
            )

        if (
            value < minimum
            or value > maximum
        ):
            raise ValueError(
                f"{key} must be between "
                f"{minimum} and {maximum}."
            )

        return value

    return {
        "max_periods_per_day": _number(
            "max_periods_per_day",
            8,
            1,
            24,
        ),
        "max_periods_per_week": _number(
            "max_periods_per_week",
            None,
            1,
            168,
        ),
        "max_consecutive_periods": _number(
            "max_consecutive_periods",
            None,
            1,
            24,
        ),
        "minimum_periods_per_week": _number(
            "minimum_periods_per_week",
            None,
            0,
            168,
        ),
    }


def normalize_teaching_profile(
    teaching: Mapping[str, Any] | None = None,
    *,
    assigned_class_ids: Iterable[Any] | None = None,
) -> dict:
    source = dict(
        teaching or {}
    )

    classes = (
        normalize_class_ids(
            assigned_class_ids
        )
        if assigned_class_ids is not None
        else normalize_class_ids(
            source.get(
                "assigned_class_ids"
            )
        )
    )

    return {
        "subjects": normalize_string_list(
            source.get("subjects"),
            maximum=MAX_SUBJECTS,
        ),
        "learning_area_ids": normalize_string_list(
            source.get("learning_area_ids")
            or source.get("learning_areas"),
            maximum=MAX_LEARNING_AREAS,
        ),
        "assigned_class_ids": classes,
        "grade_levels": normalize_string_list(
            source.get("grade_levels"),
            maximum=50,
            lowercase=True,
        ),
        "can_teach_multiple_classes": normalize_bool(
            source.get(
                "can_teach_multiple_classes"
            ),
            True,
        ),
        "can_cover_substitution": normalize_bool(
            source.get(
                "can_cover_substitution"
            ),
            True,
        ),
        "can_supervise": normalize_bool(
            source.get(
                "can_supervise"
            ),
            False,
        ),
        "mentor_teacher": normalize_bool(
            source.get(
                "mentor_teacher"
            ),
            False,
        ),
        "workload": normalize_workload(
            source.get("workload")
        ),
    }


def normalize_timetable_profile(
    timetable: Mapping[str, Any] | None = None,
) -> dict:
    source = dict(
        timetable or {}
    )

    preferred_period_ids = normalize_string_list(
        source.get(
            "preferred_period_ids"
        ),
        maximum=MAX_TIME_PREFERENCES,
    )

    avoid_period_ids = normalize_string_list(
        source.get(
            "avoid_period_ids"
        ),
        maximum=MAX_TIME_PREFERENCES,
    )

    preferred_days = normalize_weekdays(
        source.get("preferred_days")
    )

    unavailable_days = normalize_weekdays(
        source.get("unavailable_days")
    )

    blocked_slots = normalize_string_list(
        source.get("blocked_slots"),
        maximum=MAX_TIME_PREFERENCES,
        lowercase=True,
    )

    return {
        "preferred_days": [
            day
            for day in preferred_days
            if day not in unavailable_days
        ],
        "unavailable_days": unavailable_days,
        "preferred_period_ids": [
            item
            for item in preferred_period_ids
            if item not in avoid_period_ids
        ],
        "avoid_period_ids": avoid_period_ids,
        "blocked_slots": blocked_slots,
        "availability": normalize_availability(
            source.get("availability")
        ),
    }


def normalize_reporting_profile(
    reporting: Mapping[str, Any] | None = None,
) -> dict:
    source = dict(
        reporting or {}
    )

    return {
        "report_display_name": normalize_optional_text(
            source.get(
                "report_display_name"
            )
        ),
        "signature_name": normalize_optional_text(
            source.get(
                "signature_name"
            )
        ),
        "can_add_teacher_remarks": normalize_bool(
            source.get(
                "can_add_teacher_remarks"
            ),
            True,
        ),
        "can_publish_teacher_assessments": normalize_bool(
            source.get(
                "can_publish_teacher_assessments"
            ),
            False,
        ),
    }


def staff_profile_doc(
    *,
    identity: Mapping[str, Any] | None = None,
    employment: Mapping[str, Any] | None = None,
    teaching: Mapping[str, Any] | None = None,
    timetable: Mapping[str, Any] | None = None,
    reporting: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    email: Any = None,
    assigned_class_ids: Iterable[Any] | None = None,
) -> dict:
    """
    Canonical staff profile used by Staff, Timetable,
    Reports and Sync.
    """

    return {
        "identity": normalize_identity(
            identity,
            email=email,
        ),
        "employment": normalize_employment(
            employment
        ),
        "teaching": normalize_teaching_profile(
            teaching,
            assigned_class_ids=assigned_class_ids,
        ),
        "timetable": normalize_timetable_profile(
            timetable
        ),
        "reporting": normalize_reporting_profile(
            reporting
        ),
        "metadata": normalize_metadata(
            metadata
        ),
    }


# =========================================================
# CANONICAL STAFF REFERENCES
# =========================================================

def staff_display_name(
    staff: Mapping[str, Any],
) -> str:
    if not isinstance(
        staff,
        Mapping,
    ):
        return ""

    identity = staff.get(
        "identity"
    )

    if isinstance(
        identity,
        Mapping,
    ):
        value = normalize_optional_text(
            identity.get(
                "display_name"
            )
        )

        if value:
            return value

    for key in (
        "display_name",
        "full_name",
        "name",
        "teacher_name",
    ):
        value = normalize_optional_text(
            staff.get(key)
        )

        if value:
            return value

    first_name = normalize_optional_text(
        staff.get("first_name")
    )

    last_name = normalize_optional_text(
        staff.get("last_name")
    )

    return " ".join(
        part
        for part in (
            first_name,
            last_name,
        )
        if part
    )


def staff_subjects(
    staff: Mapping[str, Any],
) -> list[str]:
    if not isinstance(
        staff,
        Mapping,
    ):
        return []

    teaching = staff.get(
        "teaching"
    )

    if isinstance(
        teaching,
        Mapping,
    ):
        subjects = normalize_string_list(
            teaching.get("subjects"),
            maximum=MAX_SUBJECTS,
        )

        if subjects:
            return subjects

    return normalize_string_list(
        staff.get("subjects"),
        maximum=MAX_SUBJECTS,
    )


def staff_learning_area_ids(
    staff: Mapping[str, Any],
) -> list[str]:
    if not isinstance(
        staff,
        Mapping,
    ):
        return []

    teaching = staff.get(
        "teaching"
    )

    if isinstance(
        teaching,
        Mapping,
    ):
        values = teaching.get(
            "learning_area_ids"
        )

        if values:
            return normalize_string_list(
                values,
                maximum=MAX_LEARNING_AREAS,
            )

    return normalize_string_list(
        staff.get(
            "learning_area_ids"
        ),
        maximum=MAX_LEARNING_AREAS,
    )


def staff_assigned_class_ids(
    staff: Mapping[str, Any],
) -> list[str]:
    if not isinstance(
        staff,
        Mapping,
    ):
        return []

    top_level = staff.get(
        "assigned_class_ids"
    )

    if top_level:
        return normalize_class_ids(
            top_level
        )

    teaching = staff.get(
        "teaching"
    )

    if isinstance(
        teaching,
        Mapping,
    ):
        return normalize_class_ids(
            teaching.get(
                "assigned_class_ids"
            )
        )

    return []


def teacher_reference(
    staff: Mapping[str, Any],
) -> dict:
    """
    Canonical Timetable/Reports teacher reference.

    teacher_user_id is the stable relational key.
    teacher_name is display/snapshot data only.
    """

    if not isinstance(
        staff,
        Mapping,
    ):
        raise ValueError(
            "staff must be an object."
        )

    user_id = normalize_id(
        staff.get("user_id")
    )

    school_id = normalize_id(
        staff.get("school_id")
    )

    role = normalize_text(
        staff.get("role")
    ).lower()

    if not user_id:
        raise ValueError(
            "Staff user_id is required "
            "for a teacher reference."
        )

    if role and role != ROLE_TEACHER:
        raise ValueError(
            "Teacher reference requires "
            "a teacher staff member."
        )

    employment = staff.get(
        "employment",
        {},
    )

    employee_number = (
        normalize_optional_text(
            employment.get(
                "employee_number"
            )
        )
        if isinstance(
            employment,
            Mapping,
        )
        else None
    )

    return {
        "staff_id": normalize_id(
            staff.get("staff_id")
        ) or user_id,
        "teacher_user_id": user_id,
        "teacher_name": staff_display_name(
            staff
        ),
        "school_id": school_id,
        "role": role or ROLE_TEACHER,
        "subjects": staff_subjects(
            staff
        ),
        "learning_area_ids": (
            staff_learning_area_ids(
                staff
            )
        ),
        "assigned_class_ids": (
            staff_assigned_class_ids(
                staff
            )
        ),
        "employee_number": employee_number,
    }


def staff_snapshot(
    staff: Mapping[str, Any],
    *,
    include_contact: bool = False,
) -> dict:
    """
    Safe staff snapshot for reports, audit records,
    exports and sync.
    """

    if not isinstance(
        staff,
        Mapping,
    ):
        raise ValueError(
            "staff must be an object."
        )

    role = normalize_text(
        staff.get("role")
    ).lower()

    identity = (
        staff.get(
            "identity",
            {},
        )
        if isinstance(
            staff.get(
                "identity",
                {},
            ),
            Mapping,
        )
        else {}
    )

    employment = (
        staff.get(
            "employment",
            {},
        )
        if isinstance(
            staff.get(
                "employment",
                {},
            ),
            Mapping,
        )
        else {}
    )

    if role == ROLE_TEACHER:
        reference = teacher_reference(
            staff
        )

    else:
        reference = {
            "staff_id": (
                normalize_id(
                    staff.get("staff_id")
                )
                or normalize_id(
                    staff.get("user_id")
                )
            ),
            "teacher_user_id": None,
            "teacher_name": "",
            "school_id": normalize_id(
                staff.get("school_id")
            ),
            "role": role,
            "subjects": staff_subjects(
                staff
            ),
            "learning_area_ids": (
                staff_learning_area_ids(
                    staff
                )
            ),
            "assigned_class_ids": (
                staff_assigned_class_ids(
                    staff
                )
            ),
            "employee_number": (
                normalize_optional_text(
                    employment.get(
                        "employee_number"
                    )
                )
            ),
        }

    snapshot = {
        "staff_id": reference[
            "staff_id"
        ],
        "user_id": normalize_id(
            staff.get("user_id")
        ),
        "school_id": reference[
            "school_id"
        ],
        "role": reference[
            "role"
        ],
        "status": normalize_text(
            staff.get("status")
        ).lower(),
        "display_name": (
            reference["teacher_name"]
            if reference["teacher_name"]
            else staff_display_name(
                staff
            )
        ),
        "employee_number": (
            reference[
                "employee_number"
            ]
        ),
        "job_title": normalize_optional_text(
            employment.get("job_title")
        ),
        "department": normalize_optional_text(
            employment.get("department")
        ),
        "subjects": reference[
            "subjects"
        ],
        "learning_area_ids": reference[
            "learning_area_ids"
        ],
        "assigned_class_ids": reference[
            "assigned_class_ids"
        ],
    }

    if include_contact:
        snapshot.update(
            {
                "email": normalize_email(
                    identity.get("email")
                ),
                "phone": normalize_optional_text(
                    identity.get("phone")
                ),
            }
        )

    return snapshot


def is_active_staff(
    staff: Mapping[str, Any] | None,
) -> bool:
    return (
        isinstance(
            staff,
            Mapping,
        )
        and normalize_text(
            staff.get("status")
        ).lower()
        == STATUS_ACTIVE
    )


def is_active_teacher(
    staff: Mapping[str, Any] | None,
) -> bool:
    return (
        is_active_staff(
            staff
        )
        and normalize_text(
            staff.get("role")
        ).lower()
        == ROLE_TEACHER
    )


# =========================================================
# INVITATION TOKEN
# =========================================================

def invitation_token() -> str:
    """
    Generate a high-entropy invitation token.

    The raw token is delivered only to the invitation
    delivery layer. The database stores its hash.
    """

    return secrets.token_urlsafe(
        32
    )


def hash_invitation_token(
    token: str,
) -> str:
    if not isinstance(
        token,
        str,
    ):
        raise ValueError(
            "Invitation token must be text."
        )

    token = token.strip()

    if not token:
        raise ValueError(
            "Invitation token is required."
        )

    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def verify_invitation_token(
    raw_token: str,
    stored_hash: str,
) -> bool:
    if not raw_token or not stored_hash:
        return False

    calculated = hash_invitation_token(
        raw_token
    )

    return secrets.compare_digest(
        calculated,
        str(stored_hash),
    )


# =========================================================
# INVITATION EXPIRY
# =========================================================

def invitation_expiry(
    days: int = DEFAULT_INVITATION_EXPIRY_DAYS,
) -> datetime:
    if (
        not isinstance(
            days,
            int,
        )
        or isinstance(
            days,
            bool,
        )
    ):
        raise ValueError(
            "Invitation expiry must be a whole number of days."
        )

    if days < 1 or days > 30:
        raise ValueError(
            "Invitation expiry must be between 1 and 30 days."
        )

    return (
        now_utc()
        + timedelta(
            days=days
        )
    )


def invitation_is_expired(
    document: Mapping[str, Any],
    current_time: datetime | None = None,
) -> bool:
    if not isinstance(
        document,
        Mapping,
    ):
        return True

    expires_at = document.get(
        "expires_at"
    )

    if not isinstance(
        expires_at,
        datetime,
    ):
        return True

    return (
        expires_at
        <= (
            current_time
            or now_utc()
        )
    )


def invitation_is_usable(
    document: Mapping[str, Any],
    current_time: datetime | None = None,
) -> bool:
    if not isinstance(
        document,
        Mapping,
    ):
        return False

    if normalize_text(
        document.get("status")
    ).lower() != STATUS_INVITED:
        return False

    if document.get(
        "cancelled_at"
    ):
        return False

    return not invitation_is_expired(
        document,
        current_time,
    )


# =========================================================
# MEMBERSHIP DOCUMENT
# =========================================================

def membership_doc(
    school_id: Any,
    user_id: Any,
    role: str,
    invited_by: Any = None,
    status: str = STATUS_ACTIVE,
    permissions: Iterable[str] | None = None,
    assigned_class_ids: Iterable[Any] | None = None,
    accepted_at: datetime | None = None,
    activated_at: datetime | None = None,
    suspended_at: datetime | None = None,
    removed_at: datetime | None = None,
    identity: Mapping[str, Any] | None = None,
    employment: Mapping[str, Any] | None = None,
    teaching: Mapping[str, Any] | None = None,
    timetable: Mapping[str, Any] | None = None,
    reporting: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    **extra: Any,
) -> dict:
    """
    Build the canonical Elimu staff membership.

    Existing callers can continue using the original membership
    arguments. New callers can populate identity, employment,
    teaching, timetable and reporting profiles.

    The stable relationship key for Timetable/Reports is user_id.
    """

    school = normalize_id(
        school_id
    )

    user = normalize_id(
        user_id
    )

    inviter = normalize_id(
        invited_by
    )

    if not school:
        raise ValueError(
            "school_id is required."
        )

    if not user:
        raise ValueError(
            "user_id is required for a membership."
        )

    normalized_role = normalize_role(
        role
    )

    normalized_status = normalize_status(
        status
    )

    now = now_utc()

    normalized_classes = normalize_class_ids(
        assigned_class_ids
    )

    profile = staff_profile_doc(
        identity=identity,
        employment=employment,
        teaching=teaching,
        timetable=timetable,
        reporting=reporting,
        metadata=metadata,
        email=(
            identity.get("email")
            if isinstance(
                identity,
                Mapping,
            )
            else None
        ),
        assigned_class_ids=normalized_classes,
    )

    display_name = profile[
        "identity"
    ][
        "display_name"
    ]

    document = {
        "model_version": STAFF_MODEL_VERSION,

        # Stable staff identity.
        "staff_id": user,
        "school_id": school,
        "user_id": user,

        # Authorization.
        "role": normalized_role,
        "status": normalized_status,
        "permissions": normalize_permissions(
            permissions
        ),

        # Server-side teacher class scope.
        "assigned_class_ids": normalized_classes,

        "invited_by": inviter,

        # Shared staff contract.
        "identity": profile[
            "identity"
        ],
        "employment": profile[
            "employment"
        ],
        "teaching": {
            **profile[
                "teaching"
            ],
            "assigned_class_ids": normalized_classes,
        },
        "timetable": profile[
            "timetable"
        ],
        "reporting": profile[
            "reporting"
        ],
        "metadata": profile[
            "metadata"
        ],

        # Compatibility/display aliases.
        "display_name": display_name,
        "subjects": profile[
            "teaching"
        ][
            "subjects"
        ],
        "learning_area_ids": profile[
            "teaching"
        ][
            "learning_area_ids"
        ],
        "teacher_name": (
            display_name
            if normalized_role
            == ROLE_TEACHER
            else None
        ),

        "created_at": now,
        "updated_at": now,
    }

    # -----------------------------------------------------
    # Lifecycle timestamps
    # -----------------------------------------------------

    if accepted_at is not None:
        document[
            "accepted_at"
        ] = accepted_at

    if activated_at is not None:
        document[
            "activated_at"
        ] = activated_at

    if suspended_at is not None:
        document[
            "suspended_at"
        ] = suspended_at

    if removed_at is not None:
        document[
            "removed_at"
        ] = removed_at

    # -----------------------------------------------------
    # Protected fields
    # -----------------------------------------------------

    protected = {
        "model_version",
        "staff_id",
        "school_id",
        "user_id",
        "role",
        "status",
        "permissions",
        "assigned_class_ids",
        "invited_by",
        "identity",
        "employment",
        "teaching",
        "timetable",
        "reporting",
        "metadata",
        "display_name",
        "subjects",
        "learning_area_ids",
        "teacher_name",
        "created_at",
        "updated_at",
        "accepted_at",
        "activated_at",
        "suspended_at",
        "removed_at",
    }

    for key, value in extra.items():
        if key in protected:
            raise ValueError(
                f"{key} cannot be overridden."
            )

        document[key] = value

    return document


# =========================================================
# INVITATION DOCUMENT
# =========================================================

def invitation_doc(
    school_id: Any,
    email: str,
    role: str,
    invited_by: Any,
    permissions: Iterable[str] | None = None,
    assigned_class_ids: Iterable[Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    expires_in_days: int = DEFAULT_INVITATION_EXPIRY_DAYS,
    identity: Mapping[str, Any] | None = None,
    employment: Mapping[str, Any] | None = None,
    teaching: Mapping[str, Any] | None = None,
    timetable: Mapping[str, Any] | None = None,
    reporting: Mapping[str, Any] | None = None,
) -> tuple[dict, str]:
    """
    Build a secure staff invitation.

    The raw token is returned only to the delivery layer.
    MongoDB stores only token_hash.
    """

    school = normalize_id(
        school_id
    )

    inviter = normalize_id(
        invited_by
    )

    normalized_email = normalize_email(
        email
    )

    if not school:
        raise ValueError(
            "school_id is required."
        )

    if not normalized_email:
        raise ValueError(
            "email is required."
        )

    if not inviter:
        raise ValueError(
            "invited_by is required."
        )

    normalized_role = normalize_role(
        role
    )

    normalized_classes = normalize_class_ids(
        assigned_class_ids
    )

    raw_token = invitation_token()

    now = now_utc()

    profile = staff_profile_doc(
        identity=identity,
        employment=employment,
        teaching=teaching,
        timetable=timetable,
        reporting=reporting,
        metadata=metadata,
        email=normalized_email,
        assigned_class_ids=normalized_classes,
    )

    document = {
        "model_version": STAFF_MODEL_VERSION,

        "school_id": school,
        "email": normalized_email,
        "role": normalized_role,
        "status": STATUS_INVITED,

        "token_hash": hash_invitation_token(
            raw_token
        ),

        "permissions": normalize_permissions(
            permissions
        ),

        "assigned_class_ids": normalized_classes,

        "invited_by": inviter,

        # Store intended profile for invitation acceptance.
        "profile": profile,

        # Existing API compatibility.
        "metadata": profile[
            "metadata"
        ],

        "created_at": now,
        "updated_at": now,

        "expires_at": invitation_expiry(
            expires_in_days
        ),

        "accepted_at": None,
        "activated_at": None,
        "cancelled_at": None,
    }

    return (
        document,
        raw_token,
    )