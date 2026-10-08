"""
Timetable request schemas for Elimu.

This module defines the public/API contract for school timetable creation,
generation, manual adjustment, publication, and regeneration.

Architecture
------------

School configuration
        +
School timetable requirements
        +
Optional AI-generated instructions
        ↓
      schemas.py
        ↓
    services.py
        ↓
 timetable/generator.py
        ↓
 generated timetable
        ↓
 server-side validation
        ↓
 persistence

Important
---------

The schema uses the canonical Elimu vocabulary:

    lessons_per_week
    double_lesson

The generator may use its compatibility vocabulary:

    periods_per_week
    allow_double

The service layer is responsible for adapting between the two.

AI is therefore allowed to generate or modify structured timetable
requirements, but it does not bypass validation or persistence rules.
"""

from __future__ import annotations

from typing import Any


# =========================================================
# LIMITS
# =========================================================

MAX_WEEKDAYS = 7
MAX_PERIODS = 50
MAX_REQUIREMENTS = 2000

MAX_METADATA_KEYS = 30

MAX_PREFERRED_DAYS = 7
MAX_AVOID_DAYS = 7

MAX_PREFERRED_PERIODS = 50
MAX_AVOID_PERIODS = 50

MAX_BLOCKED_SLOTS = 200

MAX_WEEKLY_LESSONS = 50
MAX_DAILY_LESSONS = 20
MAX_GAP_PERIODS = 20
MAX_GAP_DAYS = 7
MAX_DOUBLE_LESSONS = 25

MIN_PRIORITY = 0
MAX_PRIORITY = 100


# =========================================================
# ENUMS
# =========================================================

VALID_WEEKDAYS = {
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}


VALID_PERIOD_TYPES = {
    "lesson",
    "break",
    "assembly",
    "lunch",
    "activity",
    "exam",
    "free",
}


VALID_PRIORITIES = {
    "low",
    "normal",
    "high",
    "critical",
}


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
            f"{name} must not exceed {max_len} characters."
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

        normalized = (
            value.strip().lower()
        )

        if normalized in {
            "true",
            "1",
            "yes",
            "on",
        }:
            return True

        if normalized in {
            "false",
            "0",
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

    raise ValueError(
        f"{name} must be boolean."
    )


def _positive_int(
    value: Any,
    *,
    name: str,
    minimum: int = 1,
    maximum: int = 1000,
) -> int:

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

    if number < minimum:
        raise ValueError(
            f"{name} must be at least {minimum}."
        )

    if number > maximum:
        raise ValueError(
            f"{name} must not exceed {maximum}."
        )

    return number


def _nonnegative_int(
    value: Any,
    *,
    name: str,
    maximum: int = 1000,
    default: int = 0,
) -> int:

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

    if number < 0:
        raise ValueError(
            f"{name} cannot be negative."
        )

    if number > maximum:
        raise ValueError(
            f"{name} must not exceed {maximum}."
        )

    return number


# =========================================================
# STRING LISTS
# =========================================================

def _string_list(
    value: Any,
    *,
    name: str,
    maximum: int,
    item_max_len: int = 200,
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
            f"{name} must be a list."
        )

    if len(value) > maximum:
        raise ValueError(
            f"{name} cannot contain more than "
            f"{maximum} items."
        )

    result = []

    for item in value:

        normalized = _text(
            item,
            name=name,
            max_len=item_max_len,
        )

        if not normalized:
            continue

        if normalized not in result:
            result.append(
                normalized
            )

    return result


# =========================================================
# WEEKDAYS
# =========================================================

def _weekdays(
    value: Any,
    *,
    name: str = "weekdays",
) -> list[str]:

    days = _string_list(
        value,
        name=name,
        maximum=MAX_WEEKDAYS,
        item_max_len=20,
    )

    result = []

    for day in days:

        normalized = day.lower()

        if normalized not in VALID_WEEKDAYS:
            raise ValueError(
                f"Invalid weekday: {day}."
            )

        if normalized not in result:

            result.append(
                normalized
            )

    return result


# =========================================================
# PERIOD
# =========================================================

def _period(
    value: Any,
) -> dict:

    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            "Each timetable period must be an object."
        )

    # -----------------------------------------------------
    # Canonical field
    # -----------------------------------------------------

    period_id = (
        _text(
            value.get(
                "period_id"
            ),
            name="period_id",
            max_len=80,
        )
        or _text(
            value.get(
                "id"
            ),
            name="period_id",
            max_len=80,
        )
    )

    if not period_id:

        raise ValueError(
            "period_id is required."
        )

    # -----------------------------------------------------
    # Display label
    # -----------------------------------------------------

    label = (
        _text(
            value.get(
                "label"
            ),
            name="label",
            max_len=120,
        )
        or _text(
            value.get(
                "name"
            ),
            name="label",
            max_len=120,
        )
        or period_id
    )

    # -----------------------------------------------------
    # Period type
    # -----------------------------------------------------

    period_type = (
        _text(
            value.get(
                "type",
                value.get(
                    "kind",
                    "lesson",
                ),
            ),
            name="type",
            max_len=30,
        ).lower()
        or "lesson"
    )

    if period_type not in VALID_PERIOD_TYPES:

        raise ValueError(
            "Invalid timetable period type."
        )

    # -----------------------------------------------------
    # Times
    # -----------------------------------------------------

    start_time = (
        _text(
            value.get(
                "start_time"
            ),
            name="start_time",
            max_len=20,
        )
        or None
    )

    end_time = (
        _text(
            value.get(
                "end_time"
            ),
            name="end_time",
            max_len=20,
        )
        or None
    )

    # -----------------------------------------------------
    # Duration
    # -----------------------------------------------------

    duration_minutes = value.get(
        "duration_minutes"
    )

    if duration_minutes is not None:

        duration_minutes = _positive_int(
            duration_minutes,
            name="duration_minutes",
            minimum=1,
            maximum=600,
        )

    return {
        "period_id": period_id,
        "label": label,
        "type": period_type,
        "start_time": start_time,
        "end_time": end_time,
        "duration_minutes": duration_minutes,
    }


def _periods(
    value: Any,
) -> list[dict]:

    if value is None:
        return []

    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            "periods must be a list."
        )

    if len(value) > MAX_PERIODS:

        raise ValueError(
            f"periods cannot contain more than "
            f"{MAX_PERIODS} items."
        )

    result = []

    seen_ids = set()

    for item in value:

        period = _period(
            item
        )

        period_id = period[
            "period_id"
        ]

        comparison_id = (
            period_id.lower()
        )

        if comparison_id in seen_ids:

            raise ValueError(
                f"Duplicate timetable period: "
                f"{period_id}."
            )

        seen_ids.add(
            comparison_id
        )

        result.append(
            period
        )

    return result


# =========================================================
# BLOCKED SLOT
# =========================================================

def _blocked_slots(
    value: Any,
) -> list[str]:

    values = _string_list(
        value,
        name="blocked_slots",
        maximum=MAX_BLOCKED_SLOTS,
        item_max_len=120,
    )

    result = []

    for raw in values:

        normalized = raw.strip().lower()

        parts = normalized.split(
            "::",
            1,
        )

        if len(parts) != 2:

            raise ValueError(
                "Each blocked slot must use the format "
                "'day::period_id'."
            )

        day = parts[
            0
        ].strip()

        period_id = parts[
            1
        ].strip()

        if day not in VALID_WEEKDAYS:

            raise ValueError(
                f"Invalid blocked-slot weekday: {day}."
            )

        if not period_id:

            raise ValueError(
                "Blocked slot period_id is required."
            )

        canonical = (
            f"{day}::{period_id}"
        )

        if canonical not in result:

            result.append(
                canonical
            )

    return result


# =========================================================
# DOUBLE LESSONS
# =========================================================

def _double_lessons(
    value: Any,
    *,
    lessons_per_week: int,
    double_lesson: bool,
) -> int:
    """
    Resolve the exact number of weekly double blocks.

    Canonical semantics:

        double_lesson=False
            -> no doubles

        double_lesson=True + omitted count
            -> zero doubles by default

        double_lesson=True + count
            -> exactly that many double blocks

    This prevents the old behavior where simply enabling doubles
    could unexpectedly turn every compatible lesson into a double.
    """

    raw = value

    if not double_lesson:

        if raw is not None:

            count = _nonnegative_int(
                raw,
                name="double_lessons_per_week",
                maximum=MAX_DOUBLE_LESSONS,
                default=0,
            )

            if count != 0:

                raise ValueError(
                    "double_lessons_per_week must be zero "
                    "when double_lesson is false."
                )

        return 0

    if raw is None:

        return 0

    count = _nonnegative_int(
        raw,
        name="double_lessons_per_week",
        maximum=MAX_DOUBLE_LESSONS,
        default=0,
    )

    maximum = (
        lessons_per_week // 2
    )

    if count > maximum:

        raise ValueError(
            "double_lessons_per_week cannot exceed "
            "lessons_per_week // 2."
        )

    return count


# =========================================================
# PRIORITY
# =========================================================

def _priority(
    value: Any,
) -> tuple[int, str]:
    """
    Return:

        numeric_priority
        priority_label
    """

    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            "priority must be a number or priority label."
        )

    # -----------------------------------------------------
    # Numeric input
    # -----------------------------------------------------

    if isinstance(
        value,
        (int, float),
    ):

        numeric = int(
            value
        )

        if not (
            MIN_PRIORITY
            <= numeric
            <= MAX_PRIORITY
        ):

            raise ValueError(
                "priority must be between "
                f"{MIN_PRIORITY} and {MAX_PRIORITY}."
            )

    # -----------------------------------------------------
    # Numeric text
    # -----------------------------------------------------

    elif isinstance(
        value,
        str,
    ):

        raw = value.strip()

        try:

            numeric = int(
                raw
            )

            if not (
                MIN_PRIORITY
                <= numeric
                <= MAX_PRIORITY
            ):

                raise ValueError(
                    "priority must be between "
                    f"{MIN_PRIORITY} and {MAX_PRIORITY}."
                )

        except ValueError:

            label = raw.lower()

            if label not in VALID_PRIORITIES:

                raise ValueError(
                    "Invalid priority."
                )

            numeric = {
                "low": 10,
                "normal": 25,
                "high": 60,
                "critical": 90,
            }[
                label
            ]

    else:

        raise ValueError(
            "priority must be a number or priority label."
        )

    label = (
        "critical"
        if numeric >= 75
        else "high"
        if numeric >= 50
        else "normal"
        if numeric >= 25
        else "low"
    )

    return (
        numeric,
        label,
    )


# =========================================================
# REQUIREMENT
# =========================================================

def _requirement(
    value: Any,
    *,
    period_ids: set[str] | None = None,
) -> dict:

    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            "Each timetable requirement must be an object."
        )

    # -----------------------------------------------------
    # Identity
    # -----------------------------------------------------

    class_id = _required(
        value,
        "class_id",
        max_len=120,
    )

    teacher_user_id = _required(
        value,
        "teacher_user_id",
        max_len=120,
    )

    subject = _required(
        value,
        "subject",
        max_len=120,
    )

    # -----------------------------------------------------
    # Canonical lessons/week
    #
    # Backward compatibility:
    # `periods_per_week` is accepted as an input alias.
    # -----------------------------------------------------

    lessons_raw = value.get(
        "lessons_per_week"
    )

    if lessons_raw is None:

        lessons_raw = value.get(
            "periods_per_week"
        )

    if lessons_raw is None:

        raise ValueError(
            "lessons_per_week is required."
        )

    lessons_per_week = _positive_int(
        lessons_raw,
        name="lessons_per_week",
        minimum=1,
        maximum=MAX_WEEKLY_LESSONS,
    )

    # -----------------------------------------------------
    # Room
    # -----------------------------------------------------

    room_id = (
        _text(
            value.get(
                "room_id"
            ),
            name="room_id",
            max_len=120,
        )
        or None
    )

    # -----------------------------------------------------
    # Days
    # -----------------------------------------------------

    preferred_days = _weekdays(
        value.get(
            "preferred_days",
            [],
        ),
        name="preferred_days",
    )

    avoid_days = _weekdays(
        value.get(
            "avoid_days",
            [],
        ),
        name="avoid_days",
    )

    # -----------------------------------------------------
    # Period preferences
    # -----------------------------------------------------

    preferred_period_ids = _string_list(
        value.get(
            "preferred_period_ids",
            [],
        ),
        name="preferred_period_ids",
        maximum=MAX_PREFERRED_PERIODS,
        item_max_len=80,
    )

    avoid_period_ids = _string_list(
        value.get(
            "avoid_period_ids",
            [],
        ),
        name="avoid_period_ids",
        maximum=MAX_AVOID_PERIODS,
        item_max_len=80,
    )

    # -----------------------------------------------------
    # Blocked slots
    # -----------------------------------------------------

    blocked_slots = _blocked_slots(
        value.get(
            "blocked_slots",
            [],
        )
    )

    # -----------------------------------------------------
    # Double lessons
    #
    # Canonical field:
    #     double_lesson
    #
    # Compatibility alias:
    #     allow_double
    # -----------------------------------------------------

    double_value = value.get(
        "double_lesson"
    )

    if double_value is None:

        double_value = value.get(
            "allow_double"
        )

    double_lesson = _bool(
        double_value,
        name="double_lesson",
        default=False,
    )

    double_lessons_per_week = _double_lessons(
        value.get(
            "double_lessons_per_week"
        ),
        lessons_per_week=lessons_per_week,
        double_lesson=double_lesson,
    )

    # -----------------------------------------------------
    # Daily subject limit
    # -----------------------------------------------------

    max_lessons_per_day = None

    if (
        value.get(
            "max_lessons_per_day"
        )
        is not None
    ):

        max_lessons_per_day = _positive_int(
            value[
                "max_lessons_per_day"
            ],
            name="max_lessons_per_day",
            minimum=1,
            maximum=MAX_DAILY_LESSONS,
        )

    # -----------------------------------------------------
    # Period spacing
    # -----------------------------------------------------

    min_gap_periods = _nonnegative_int(
        value.get(
            "min_gap_periods"
        ),
        name="min_gap_periods",
        maximum=MAX_GAP_PERIODS,
        default=0,
    )

    # -----------------------------------------------------
    # Day spacing
    # -----------------------------------------------------

    min_days_between = _nonnegative_int(
        value.get(
            "min_days_between"
        ),
        name="min_days_between",
        maximum=MAX_GAP_DAYS,
        default=0,
    )

    # -----------------------------------------------------
    # Distribution preferences
    # -----------------------------------------------------

    spread_across_days = _bool(
        value.get(
            "spread_across_days"
        ),
        name="spread_across_days",
        default=True,
    )

    avoid_consecutive = _bool(
        value.get(
            "avoid_consecutive"
        ),
        name="avoid_consecutive",
        default=False,
    )

    # -----------------------------------------------------
    # Priority
    # -----------------------------------------------------

    priority_value = value.get(
        "priority",
        "normal",
    )

    priority, priority_label = _priority(
        priority_value
    )

    # -----------------------------------------------------
    # Display metadata
    # -----------------------------------------------------

    teacher_name = (
        _text(
            value.get(
                "teacher_name"
            ),
            name="teacher_name",
            max_len=160,
        )
        or None
    )

    class_name = (
        _text(
            value.get(
                "class_name"
            ),
            name="class_name",
            max_len=160,
        )
        or None
    )

    # -----------------------------------------------------
    # Cross-check referenced period IDs
    # -----------------------------------------------------

    if period_ids:

        for period_id in (
            preferred_period_ids
            + avoid_period_ids
        ):

            if period_id not in period_ids:

                raise ValueError(
                    f"Unknown timetable period id: "
                    f"{period_id}."
                )

    # -----------------------------------------------------
    # Cross-check blocked slots
    # -----------------------------------------------------

    if period_ids:

        for blocked in blocked_slots:

            _day, blocked_period_id = blocked.split(
                "::",
                1,
            )

            if blocked_period_id not in period_ids:

                raise ValueError(
                    f"Unknown blocked-slot period id: "
                    f"{blocked_period_id}."
                )

    # -----------------------------------------------------
    # Avoid impossible day preference combinations
    # -----------------------------------------------------

    overlap_days = (
        set(preferred_days)
        & set(avoid_days)
    )

    if overlap_days:

        raise ValueError(
            "A day cannot be both preferred and avoided: "
            + ", ".join(
                sorted(
                    overlap_days
                )
            )
        )

    # -----------------------------------------------------
    # Canonical output
    # -----------------------------------------------------

    return {
        "class_id": class_id,
        "teacher_user_id": teacher_user_id,
        "subject": subject,

        "lessons_per_week": lessons_per_week,

        "room_id": room_id,

        "preferred_days": preferred_days,
        "avoid_days": avoid_days,

        "preferred_period_ids": preferred_period_ids,
        "avoid_period_ids": avoid_period_ids,

        "blocked_slots": blocked_slots,

        "double_lesson": double_lesson,
        "double_lessons_per_week": (
            double_lessons_per_week
        ),

        "max_lessons_per_day": (
            max_lessons_per_day
        ),

        "min_gap_periods": (
            min_gap_periods
        ),

        "min_days_between": (
            min_days_between
        ),

        "spread_across_days": (
            spread_across_days
        ),

        "avoid_consecutive": (
            avoid_consecutive
        ),

        "priority": priority,
        "priority_label": priority_label,

        "teacher_name": teacher_name,
        "class_name": class_name,
    }


def _requirements(
    value: Any,
    *,
    period_ids: set[str] | None = None,
) -> list[dict]:

    if value is None:
        return []

    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            "requirements must be a list."
        )

    if len(value) > MAX_REQUIREMENTS:

        raise ValueError(
            "requirements cannot contain more than "
            f"{MAX_REQUIREMENTS} items."
        )

    return [
        _requirement(
            item,
            period_ids=period_ids,
        )
        for item in value
    ]


# =========================================================
# GENERATION CONSTRAINTS
# =========================================================

def _constraints(
    value: Any,
) -> dict:

    if value is None:
        return {}

    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            "constraints must be an object."
        )

    output = {}

    # -----------------------------------------------------
    # Teacher daily maximum
    # -----------------------------------------------------

    teacher_limit = value.get(
        "max_teacher_lessons_per_day"
    )

    if teacher_limit is not None:

        output[
            "max_teacher_lessons_per_day"
        ] = _positive_int(
            teacher_limit,
            name="max_teacher_lessons_per_day",
            minimum=1,
            maximum=MAX_DAILY_LESSONS,
        )

    # -----------------------------------------------------
    # Class daily maximum
    # -----------------------------------------------------

    class_limit = value.get(
        "max_class_lessons_per_day"
    )

    if class_limit is not None:

        output[
            "max_class_lessons_per_day"
        ] = _positive_int(
            class_limit,
            name="max_class_lessons_per_day",
            minimum=1,
            maximum=MAX_DAILY_LESSONS,
        )

    # -----------------------------------------------------
    # Room daily maximum
    # -----------------------------------------------------

    room_limit = value.get(
        "max_room_lessons_per_day"
    )

    if room_limit is not None:

        output[
            "max_room_lessons_per_day"
        ] = _positive_int(
            room_limit,
            name="max_room_lessons_per_day",
            minimum=1,
            maximum=MAX_DAILY_LESSONS,
        )

    # -----------------------------------------------------
    # Maximum consecutive periods
    # -----------------------------------------------------

    consecutive_limit = value.get(
        "max_consecutive_periods"
    )

    if consecutive_limit is not None:

        output[
            "max_consecutive_periods"
        ] = _positive_int(
            consecutive_limit,
            name="max_consecutive_periods",
            minimum=1,
            maximum=MAX_PERIODS,
        )

    # -----------------------------------------------------
    # Soft optimization flags
    # -----------------------------------------------------

    output[
        "avoid_same_subject_consecutive"
    ] = _bool(
        value.get(
            "avoid_same_subject_consecutive"
        ),
        name="avoid_same_subject_consecutive",
        default=False,
    )

    output[
        "balance_teacher_workload"
    ] = _bool(
        value.get(
            "balance_teacher_workload"
        ),
        name="balance_teacher_workload",
        default=True,
    )

    output[
        "spread_subjects_across_week"
    ] = _bool(
        value.get(
            "spread_subjects_across_week"
        ),
        name="spread_subjects_across_week",
        default=True,
    )

    output[
        "allow_free_periods"
    ] = _bool(
        value.get(
            "allow_free_periods"
        ),
        name="allow_free_periods",
        default=True,
    )

    return output


# =========================================================
# METADATA
# =========================================================

def _metadata(
    value: Any,
) -> dict:

    if value is None:
        return {}

    if not isinstance(
        value,
        dict,
    ):
        raise ValueError(
            "metadata must be an object."
        )

    if len(value) > MAX_METADATA_KEYS:

        raise ValueError(
            "metadata contains too many fields."
        )

    return dict(
        value
    )


# =========================================================
# CREATE TIMETABLE
# =========================================================

def create_payload(
    data: Any,
) -> dict:
    """
    Validate a complete timetable generation request.

    The school supplies its own timetable structure and requirements.

    Server-only fields such as:
        school_id
        created_by
        generated_at

    are intentionally not accepted here.
    """

    _object(
        data
    )

    # -----------------------------------------------------
    # Basic identity
    # -----------------------------------------------------

    name = (
        _text(
            data.get(
                "name"
            ),
            name="name",
            max_len=200,
        )
        or "Academic Timetable"
    )

    academic_year = (
        _text(
            data.get(
                "academic_year"
            ),
            name="academic_year",
            max_len=30,
        )
        or None
    )

    term = (
        _text(
            data.get(
                "term"
            ),
            name="term",
            max_len=50,
        )
        or None
    )

    # -----------------------------------------------------
    # Timetable structure
    # -----------------------------------------------------

    weekdays = _weekdays(
        data.get(
            "weekdays",
            [],
        )
    )

    periods = _periods(
        data.get(
            "periods",
            [],
        )
    )

    if not weekdays:

        raise ValueError(
            "At least one weekday is required."
        )

    if not periods:

        raise ValueError(
            "At least one timetable period is required."
        )

    lesson_periods = [
        period
        for period in periods
        if period["type"] == "lesson"
    ]

    if not lesson_periods:

        raise ValueError(
            "At least one lesson period is required."
        )

    period_ids = {
        period[
            "period_id"
        ]
        for period in periods
    }

    # -----------------------------------------------------
    # Requirements
    # -----------------------------------------------------

    requirements = _requirements(
        data.get(
            "requirements",
            [],
        ),
        period_ids=period_ids,
    )

    if not requirements:

        raise ValueError(
            "At least one timetable requirement "
            "is required."
        )

    # -----------------------------------------------------
    # Global rules
    # -----------------------------------------------------

    constraints = _constraints(
        data.get(
            "constraints"
        )
    )

    # -----------------------------------------------------
    # Metadata
    # -----------------------------------------------------

    metadata = _metadata(
        data.get(
            "metadata"
        )
    )

    return {
        "name": name,
        "academic_year": academic_year,
        "term": term,

        "weekdays": weekdays,

        "periods": periods,

        "requirements": requirements,

        "constraints": constraints,

        "metadata": metadata,
    }


# =========================================================
# PATCH TIMETABLE ENTRY
# =========================================================

def patch_entry_payload(
    data: Any,
) -> dict:
    """
    Validate a manual timetable entry adjustment.

    The service layer remains responsible for:
      - timetable ownership
      - class ownership
      - teacher assignment
      - room assignment
      - slot availability
      - hard conflict validation
      - publication restrictions
    """

    _object(
        data
    )

    # -----------------------------------------------------
    # Day
    # -----------------------------------------------------

    day = _text(
        data.get(
            "day"
        ),
        name="day",
        max_len=20,
    ).lower()

    if not day:

        raise ValueError(
            "day is required."
        )

    if day not in VALID_WEEKDAYS:

        raise ValueError(
            "Invalid timetable day."
        )

    # -----------------------------------------------------
    # Period
    # -----------------------------------------------------

    period_id = _required(
        data,
        "period_id",
        max_len=80,
    )

    # -----------------------------------------------------
    # Optional room
    # -----------------------------------------------------

    room_id = (
        _text(
            data.get(
                "room_id"
            ),
            name="room_id",
            max_len=120,
        )
        or None
    )

    # -----------------------------------------------------
    # Optional adjustment metadata
    # -----------------------------------------------------

    reason = (
        _text(
            data.get(
                "reason"
            ),
            name="reason",
            max_len=500,
        )
        or None
    )

    return {
        "day": day,
        "period_id": period_id,
        "room_id": room_id,
        "reason": reason,
    }


# =========================================================
# PUBLISH TIMETABLE
# =========================================================

def publish_payload(
    data: Any,
) -> dict:
    """
    Validate publication confirmation.

    Authorization and publication state transitions belong
    to the service layer.
    """

    _object(
        data
    )

    confirmation = _bool(
        data.get(
            "confirmation"
        ),
        name="confirmation",
        default=False,
    )

    if not confirmation:

        raise ValueError(
            "confirmation must be true before publishing."
        )

    return {
        "confirmation": True,
    }


# =========================================================
# REGENERATE / AI ADJUSTMENT
# =========================================================

def regenerate_payload(
    data: Any,
) -> dict:
    """
    Validate a timetable regeneration / adjustment request.

    This is intentionally safe for RevelaAI integration.

    RevelaAI may request:

        - regenerate the timetable
        - apply school constraints
        - preserve a published timetable
        - optimize using preferences

    It must still flow through services -> generator ->
    server-side validator.
    """

    _object(
        data
    )

    # -----------------------------------------------------
    # AI control
    # -----------------------------------------------------

    use_ai = _bool(
        data.get(
            "use_ai"
        ),
        name="use_ai",
        default=True,
    )

    # -----------------------------------------------------
    # Publication protection
    # -----------------------------------------------------

    preserve_published = _bool(
        data.get(
            "preserve_published"
        ),
        name="preserve_published",
        default=True,
    )

    # -----------------------------------------------------
    # Optional school constraint overrides
    # -----------------------------------------------------

    constraints = _constraints(
        data.get(
            "constraints"
        )
    )

    # -----------------------------------------------------
    # Optional metadata
    # -----------------------------------------------------

    metadata = _metadata(
        data.get(
            "metadata"
        )
    )

    return {
        "use_ai": use_ai,

        "preserve_published": (
            preserve_published
        ),

        "constraints": constraints,

        "metadata": metadata,
    }


# =========================================================
# AI TIMETABLE INSTRUCTION
# =========================================================

def ai_instruction_payload(
    data: Any,
) -> dict:
    """
    Validate a natural-language timetable instruction intended
    for RevelaAI.

    Example:

        {
            "instruction":
                "Move Mathematics for Form 2 away from Monday P1."
        }

    RevelaAI should translate this instruction into structured
    timetable constraints before it reaches the generator.
    """

    _object(
        data
    )

    instruction = _required(
        data,
        "instruction",
        max_len=2000,
    )

    return {
        "instruction": instruction,
    }