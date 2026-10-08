"""
Persistent models and normalization helpers for the Elimu timetable module.

Architecture
------------

The timetable module uses three layers:

    schemas.py
        validates external/API input

    services.py
        handles authorization, MongoDB, generation and persistence

    models.py
        normalizes canonical timetable documents

    generator.py
        creates deterministic timetable candidates

    validator.py
        remains the final server-side authority

RevelaAI may suggest or optimize timetable changes, but it never bypasses
the canonical model or server-side validation.

Canonical terminology
---------------------

The Elimu API uses:

    lessons_per_week
    double_lesson
    double_lessons_per_week

The generator compatibility layer may use:

    periods_per_week
    allow_double
    double_lessons_per_week
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


# =========================================================
# COLLECTIONS
# =========================================================

TIMETABLES = "jumuiya_elimu_timetables"
ENTRIES = "jumuiya_elimu_timetable_entries"


# =========================================================
# MODEL VERSION
# =========================================================

TIMETABLE_MODEL_VERSION = "3.0"


# =========================================================
# TIMETABLE STATUSES
# =========================================================

STATUS_DRAFT = "draft"
STATUS_GENERATING = "generating"
STATUS_READY = "ready"
STATUS_PUBLISHED = "published"
STATUS_ARCHIVED = "archived"
STATUS_FAILED = "failed"

TIMETABLE_STATUSES = (
    STATUS_DRAFT,
    STATUS_GENERATING,
    STATUS_READY,
    STATUS_PUBLISHED,
    STATUS_ARCHIVED,
    STATUS_FAILED,
)


# =========================================================
# PERIOD TYPES
# =========================================================

PERIOD_LESSON = "lesson"
PERIOD_BREAK = "break"
PERIOD_ASSEMBLY = "assembly"
PERIOD_LUNCH = "lunch"
PERIOD_ACTIVITY = "activity"
PERIOD_EXAM = "exam"
PERIOD_FREE = "free"

PERIOD_TYPES = (
    PERIOD_LESSON,
    PERIOD_BREAK,
    PERIOD_ASSEMBLY,
    PERIOD_LUNCH,
    PERIOD_ACTIVITY,
    PERIOD_EXAM,
    PERIOD_FREE,
)


# =========================================================
# TIME
# =========================================================

def now_utc() -> datetime:
    return datetime.now(
        timezone.utc
    )


# =========================================================
# BASIC NORMALIZATION
# =========================================================

def _text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(
        value
    ).strip()


def _id(
    value: Any,
) -> str | None:
    normalized = _text(
        value
    )

    return (
        normalized
        if normalized
        else None
    )


def _id_list(
    values: Iterable[Any] | None,
) -> list[str]:

    if values is None:
        return []

    if isinstance(
        values,
        str,
    ):
        values = [
            values
        ]

    result: list[str] = []

    for value in values:

        normalized = _id(
            value
        )

        if (
            normalized
            and normalized not in result
        ):
            result.append(
                normalized
            )

    return result


def _string_list(
    values: Iterable[Any] | None,
) -> list[str]:

    if values is None:
        return []

    if isinstance(
        values,
        str,
    ):
        values = [
            values
        ]

    result: list[str] = []

    for value in values:

        normalized = _text(
            value
        )

        if (
            normalized
            and normalized not in result
        ):
            result.append(
                normalized
            )

    return result


def _bool(
    value: Any,
    default: bool = False,
) -> bool:
    """
    Safely normalize booleans.

    Prevents:

        bool("false") == True
    """

    if value is None:
        return default

    if isinstance(
        value,
        bool,
    ):
        return value

    if isinstance(
        value,
        (int, float),
    ):
        return bool(
            value
        )

    normalized = (
        _text(
            value
        ).lower()
    )

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


def _whole_number(
    value: Any,
    *,
    field_name: str,
    minimum: int | None = None,
    maximum: int | None = None,
    default: int | None = None,
) -> int | None:

    if value is None:
        return default

    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            f"{field_name} must be a whole number."
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
            f"{field_name} must be a whole number."
        )

    if (
        minimum is not None
        and number < minimum
    ):
        raise ValueError(
            f"{field_name} must be at least {minimum}."
        )

    if (
        maximum is not None
        and number > maximum
    ):
        raise ValueError(
            f"{field_name} must be at most {maximum}."
        )

    return number


# =========================================================
# WEEKDAYS
# =========================================================

VALID_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def normalize_weekdays(
    weekdays: Iterable[Any] | None,
) -> list[str]:

    if weekdays is None:
        return []

    if isinstance(
        weekdays,
        str,
    ):
        weekdays = [
            weekdays
        ]

    result: list[str] = []

    for value in weekdays:

        day = (
            _text(
                value
            ).lower()
        )

        if not day:
            continue

        if day not in VALID_WEEKDAYS:

            raise ValueError(
                f"Invalid timetable weekday: {day}"
            )

        if day not in result:

            result.append(
                day
            )

    return result


# =========================================================
# PERIOD
# =========================================================

def normalize_period(
    period: Mapping[str, Any],
) -> dict:

    if not isinstance(
        period,
        Mapping,
    ):
        raise ValueError(
            "Each timetable period must be an object."
        )

    period_id = _id(
        period.get(
            "period_id"
        )
        or period.get(
            "id"
        )
    )

    if not period_id:

        raise ValueError(
            "period_id is required."
        )

    period_type = (
        _text(
            period.get(
                "type",
                period.get(
                    "kind",
                    PERIOD_LESSON,
                ),
            )
        ).lower()
        or PERIOD_LESSON
    )

    if period_type not in PERIOD_TYPES:

        raise ValueError(
            f"Invalid timetable period type: "
            f"{period_type}"
        )

    start_time = (
        _text(
            period.get(
                "start_time"
            )
        )
        or None
    )

    end_time = (
        _text(
            period.get(
                "end_time"
            )
        )
        or None
    )

    duration_minutes = period.get(
        "duration_minutes"
    )

    if duration_minutes is not None:

        duration_minutes = _whole_number(
            duration_minutes,
            field_name="duration_minutes",
            minimum=1,
            maximum=1440,
        )

    return {
        "period_id": period_id,

        "label": (
            _text(
                period.get(
                    "label"
                )
            )
            or _text(
                period.get(
                    "name"
                )
            )
            or period_id
        ),

        "type": period_type,

        "start_time": start_time,

        "end_time": end_time,

        "duration_minutes": duration_minutes,
    }


def normalize_periods(
    periods: Iterable[
        Mapping[str, Any]
    ] | None,
) -> list[dict]:

    if periods is None:
        return []

    result: list[dict] = []

    seen: set[str] = set()

    for period in periods:

        normalized = normalize_period(
            period
        )

        period_id = normalized[
            "period_id"
        ]

        comparison_id = (
            period_id.lower()
        )

        if comparison_id in seen:

            raise ValueError(
                f"Duplicate timetable period: "
                f"{period_id}"
            )

        seen.add(
            comparison_id
        )

        result.append(
            normalized
        )

    return result


# =========================================================
# PERIOD HELPERS
# =========================================================

def lesson_periods(
    periods: Iterable[
        Mapping[str, Any]
    ] | None,
) -> list[dict]:

    normalized = normalize_periods(
        periods
    )

    return [
        period
        for period in normalized
        if period[
            "type"
        ]
        == PERIOD_LESSON
    ]


def period_ids(
    periods: Iterable[
        Mapping[str, Any]
    ] | None,
) -> set[str]:

    return {
        period[
            "period_id"
        ]
        for period in normalize_periods(
            periods
        )
    }


# =========================================================
# SLOT IDENTIFIER
# =========================================================

def slot_key(
    day: Any,
    period_id: Any,
) -> str:

    normalized_day = (
        _text(
            day
        ).lower()
    )

    normalized_period = _text(
        period_id
    )

    return (
        f"{normalized_day}::"
        f"{normalized_period}"
    )


def normalize_blocked_slots(
    values: Iterable[Any] | None,
) -> list[str]:

    if values is None:
        return []

    if isinstance(
        values,
        str,
    ):
        values = [
            values
        ]

    result = []

    for value in values:

        raw = (
            _text(
                value
            ).lower()
        )

        if not raw:
            continue

        parts = raw.split(
            "::",
            1,
        )

        if len(parts) != 2:

            raise ValueError(
                "Blocked timetable slots must use "
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
                f"Invalid blocked-slot weekday: "
                f"{day}"
            )

        if not period_id:

            raise ValueError(
                "Blocked timetable slot requires "
                "a period_id."
            )

        canonical = slot_key(
            day,
            period_id,
        )

        if canonical not in result:

            result.append(
                canonical
            )

    return result


# =========================================================
# REQUIREMENT PRIORITY
# =========================================================

VALID_REQUIREMENT_PRIORITIES = (
    "low",
    "normal",
    "high",
    "critical",
)

PRIORITY_WEIGHTS = {
    "low": 10,
    "normal": 25,
    "high": 50,
    "critical": 100,
}


def normalize_priority(
    value: Any,
) -> str:

    # -----------------------------------------------------
    # Numeric compatibility
    # -----------------------------------------------------

    if isinstance(
        value,
        (int, float),
    ) and not isinstance(
        value,
        bool,
    ):

        number = int(
            value
        )

        if number >= 75:
            return "critical"

        if number >= 50:
            return "high"

        if number >= 25:
            return "normal"

        if number >= 0:
            return "low"

        raise ValueError(
            "Timetable priority cannot be negative."
        )

    priority = (
        _text(
            value
        ).lower()
        or "normal"
    )

    if priority in VALID_REQUIREMENT_PRIORITIES:

        return priority

    # Numeric string compatibility.
    try:

        numeric = int(
            priority
        )

        return normalize_priority(
            numeric
        )

    except ValueError:

        raise ValueError(
            "Invalid timetable requirement priority. "
            f"Expected one of: "
            f"{', '.join(VALID_REQUIREMENT_PRIORITIES)} "
            "or a number between 0 and 100."
        )


def priority_weight(
    value: Any,
) -> int:

    return PRIORITY_WEIGHTS[
        normalize_priority(
            value
        )
    ]


# =========================================================
# REQUIREMENT
# =========================================================

def normalize_requirement(
    requirement: Mapping[str, Any],
) -> dict:
    """
    Normalize one canonical timetable requirement.

    Canonical structure:

        {
            "class_id": "...",
            "teacher_user_id": "...",
            "subject": "Mathematics",

            "lessons_per_week": 5,

            "room_id": "...",

            "preferred_days": [...],
            "avoid_days": [...],

            "preferred_period_ids": [...],
            "avoid_period_ids": [...],

            "blocked_slots": [...],

            "double_lesson": True,
            "double_lessons_per_week": 1,

            "max_lessons_per_day": 2,
            "min_gap_periods": 1,
            "min_days_between": 1,

            "spread_across_days": True,
            "avoid_consecutive": True,

            "priority": "high"
        }

    Compatibility aliases accepted:

        periods_per_week
        allow_double
    """

    if not isinstance(
        requirement,
        Mapping,
    ):
        raise ValueError(
            "Each timetable requirement must be an object."
        )

    # -----------------------------------------------------
    # Identity
    # -----------------------------------------------------

    class_id = _id(
        requirement.get(
            "class_id"
        )
    )

    teacher_user_id = _id(
        requirement.get(
            "teacher_user_id"
        )
    )

    subject = _text(
        requirement.get(
            "subject"
        )
    )

    if not class_id:

        raise ValueError(
            "Timetable requirement class_id is required."
        )

    if not teacher_user_id:

        raise ValueError(
            "Timetable requirement "
            "teacher_user_id is required."
        )

    if not subject:

        raise ValueError(
            "Timetable requirement subject is required."
        )

    # -----------------------------------------------------
    # Weekly lessons
    #
    # Canonical:
    #     lessons_per_week
    #
    # Generator compatibility:
    #     periods_per_week
    # -----------------------------------------------------

    lessons_raw = requirement.get(
        "lessons_per_week"
    )

    if lessons_raw is None:

        lessons_raw = requirement.get(
            "periods_per_week"
        )

    lessons_per_week = _whole_number(
        lessons_raw,
        field_name="lessons_per_week",
        minimum=1,
        maximum=50,
        default=1,
    )

    # -----------------------------------------------------
    # Double lessons
    #
    # IMPORTANT:
    #
    # double_lesson=True only means doubles are allowed.
    # It does NOT automatically make all lessons doubles.
    # -----------------------------------------------------

    double_raw = requirement.get(
        "double_lesson"
    )

    if double_raw is None:

        double_raw = requirement.get(
            "allow_double"
        )

    double_lesson = _bool(
        double_raw,
        False,
    )

    double_count_raw = requirement.get(
        "double_lessons_per_week"
    )

    if double_count_raw is None:

        double_lessons_per_week = 0

    else:

        double_lessons_per_week = _whole_number(
            double_count_raw,
            field_name="double_lessons_per_week",
            minimum=0,
            maximum=25,
            default=0,
        )

    if not double_lesson:

        if double_lessons_per_week:

            raise ValueError(
                "double_lessons_per_week must be zero "
                "when double_lesson is false."
            )

        double_lessons_per_week = 0

    maximum_doubles = (
        lessons_per_week // 2
    )

    if (
        double_lessons_per_week
        > maximum_doubles
    ):

        raise ValueError(
            "double_lessons_per_week cannot exceed "
            "lessons_per_week // 2."
        )

    # -----------------------------------------------------
    # Room
    # -----------------------------------------------------

    room_id = _id(
        requirement.get(
            "room_id"
        )
    )

    # -----------------------------------------------------
    # Days
    # -----------------------------------------------------

    preferred_days = normalize_weekdays(
        requirement.get(
            "preferred_days",
            [],
        )
    )

    avoid_days = normalize_weekdays(
        requirement.get(
            "avoid_days",
            [],
        )
    )

    # Hard avoidance always wins.
    preferred_days = [
        day
        for day in preferred_days
        if day not in avoid_days
    ]

    # -----------------------------------------------------
    # Period preferences
    # -----------------------------------------------------

    preferred_period_ids = _id_list(
        requirement.get(
            "preferred_period_ids",
            [],
        )
    )

    avoid_period_ids = _id_list(
        requirement.get(
            "avoid_period_ids",
            [],
        )
    )

    preferred_period_ids = [
        period_id
        for period_id
        in preferred_period_ids
        if period_id
        not in avoid_period_ids
    ]

    # -----------------------------------------------------
    # Explicit blocked slots
    # -----------------------------------------------------

    blocked_slots = normalize_blocked_slots(
        requirement.get(
            "blocked_slots",
            [],
        )
    )

    # -----------------------------------------------------
    # Daily lesson limit for this subject
    # -----------------------------------------------------

    max_lessons_per_day = (
        _whole_number(
            requirement.get(
                "max_lessons_per_day"
            ),
            field_name="max_lessons_per_day",
            minimum=1,
            maximum=20,
            default=None,
        )
    )

    # -----------------------------------------------------
    # Spacing
    # -----------------------------------------------------

    min_gap_periods = _whole_number(
        requirement.get(
            "min_gap_periods"
        ),
        field_name="min_gap_periods",
        minimum=0,
        maximum=20,
        default=0,
    )

    min_days_between = _whole_number(
        requirement.get(
            "min_days_between"
        ),
        field_name="min_days_between",
        minimum=0,
        maximum=7,
        default=0,
    )

    # -----------------------------------------------------
    # Distribution
    # -----------------------------------------------------

    spread_across_days = _bool(
        requirement.get(
            "spread_across_days"
        ),
        True,
    )

    avoid_consecutive = _bool(
        requirement.get(
            "avoid_consecutive"
        ),
        False,
    )

    # -----------------------------------------------------
    # Priority
    # -----------------------------------------------------

    priority = normalize_priority(
        requirement.get(
            "priority",
            "normal",
        )
    )

    # -----------------------------------------------------
    # Display metadata
    # -----------------------------------------------------

    teacher_name = (
        _text(
            requirement.get(
                "teacher_name"
            )
        )
        or None
    )

    class_name = (
        _text(
            requirement.get(
                "class_name"
            )
        )
        or None
    )

    return {
        "class_id": class_id,

        "teacher_user_id": teacher_user_id,

        "subject": subject,

        "lessons_per_week": (
            lessons_per_week
        ),

        "room_id": room_id,

        "preferred_days": preferred_days,

        "avoid_days": avoid_days,

        "preferred_period_ids": (
            preferred_period_ids
        ),

        "avoid_period_ids": (
            avoid_period_ids
        ),

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

        "teacher_name": teacher_name,

        "class_name": class_name,
    }


def normalize_requirements(
    requirements: Iterable[
        Mapping[str, Any]
    ] | None,
) -> list[dict]:

    if requirements is None:
        return []

    if isinstance(
        requirements,
        Mapping,
    ):

        raise ValueError(
            "Timetable requirements must be an array."
        )

    result: list[dict] = []

    for requirement in requirements:

        result.append(
            normalize_requirement(
                requirement
            )
        )

    return result


# =========================================================
# SCHOOL-WIDE CONSTRAINTS
# =========================================================

def normalize_constraints(
    constraints: Mapping[str, Any] | None,
) -> dict:
    """
    Normalize school-wide timetable generation policies.

    Canonical public names are retained.

    The generator adapter in services.py translates them into
    generator-compatible rule names.
    """

    if constraints is None:
        constraints = {}

    if not isinstance(
        constraints,
        Mapping,
    ):

        raise ValueError(
            "Timetable constraints must be an object."
        )

    max_teacher_lessons_per_day = (
        _whole_number(
            constraints.get(
                "max_teacher_lessons_per_day"
            ),
            field_name="max_teacher_lessons_per_day",
            minimum=1,
            maximum=20,
            default=None,
        )
    )

    max_class_lessons_per_day = (
        _whole_number(
            constraints.get(
                "max_class_lessons_per_day"
            ),
            field_name="max_class_lessons_per_day",
            minimum=1,
            maximum=20,
            default=None,
        )
    )

    max_room_lessons_per_day = (
        _whole_number(
            constraints.get(
                "max_room_lessons_per_day"
            ),
            field_name="max_room_lessons_per_day",
            minimum=1,
            maximum=20,
            default=None,
        )
    )

    max_consecutive_periods = (
        _whole_number(
            constraints.get(
                "max_consecutive_periods"
            ),
            field_name="max_consecutive_periods",
            minimum=1,
            maximum=50,
            default=None,
        )
    )

    return {
        "max_teacher_lessons_per_day": (
            max_teacher_lessons_per_day
        ),

        "max_class_lessons_per_day": (
            max_class_lessons_per_day
        ),

        "max_room_lessons_per_day": (
            max_room_lessons_per_day
        ),

        "max_consecutive_periods": (
            max_consecutive_periods
        ),

        "avoid_same_subject_consecutive": _bool(
            constraints.get(
                "avoid_same_subject_consecutive"
            ),
            False,
        ),

        "balance_teacher_workload": _bool(
            constraints.get(
                "balance_teacher_workload"
            ),
            True,
        ),

        "spread_subjects_across_week": _bool(
            constraints.get(
                "spread_subjects_across_week"
            ),
            True,
        ),

        "allow_free_periods": _bool(
            constraints.get(
                "allow_free_periods"
            ),
            True,
        ),
    }


# =========================================================
# GENERATION METADATA
# =========================================================

VALID_GENERATION_METHODS = (
    "manual",
    "generated",
    "ai",
    "ai_assisted",
    "imported",
)


def normalize_generation(
    generation: Mapping[str, Any] | None,
) -> dict:

    if generation is None:

        return {
            "method": "manual",
            "engine": None,
            "version": None,
            "ai_assisted": False,
            "request_id": None,
            "nodes_explored": 0,
            "quality_score": None,
            "generated_by": None,
        }

    if not isinstance(
        generation,
        Mapping,
    ):

        raise ValueError(
            "generation must be an object."
        )

    method = (
        _text(
            generation.get(
                "method",
                "manual",
            )
        ).lower()
        or "manual"
    )

    if method not in VALID_GENERATION_METHODS:

        raise ValueError(
            f"Invalid timetable generation method: "
            f"{method}"
        )

    nodes_explored = _whole_number(
        generation.get(
            "nodes_explored"
        ),
        field_name="nodes_explored",
        minimum=0,
        maximum=10_000_000,
        default=0,
    )

    quality_score = generation.get(
        "quality_score"
    )

    if quality_score is not None:

        try:

            quality_score = float(
                quality_score
            )

        except (
            TypeError,
            ValueError,
        ):

            raise ValueError(
                "quality_score must be numeric."
            )

    generated_by = (
        _id(
            generation.get(
                "generated_by"
            )
        )
        or None
    )

    return {
        "method": method,

        "engine": (
            _text(
                generation.get(
                    "engine"
                )
            )
            or None
        ),

        "version": (
            _text(
                generation.get(
                    "version"
                )
            )
            or None
        ),

        "ai_assisted": _bool(
            generation.get(
                "ai_assisted",
                False,
            )
        ),

        "request_id": (
            _text(
                generation.get(
                    "request_id"
                )
            )
            or None
        ),

        "nodes_explored": (
            nodes_explored
        ),

        "quality_score": (
            quality_score
        ),

        "generated_by": generated_by,
    }


# =========================================================
# TIMETABLE DOCUMENT
# =========================================================

def timetable_doc(
    school_id: Any,
    weekdays: Iterable[Any],
    periods: Iterable[
        Mapping[str, Any]
    ],
    requirements: Iterable[
        Mapping[str, Any]
    ],
    created_by: Any,
    status: str = STATUS_DRAFT,
    name: str | None = None,
    *,
    academic_year: str | None = None,
    term: str | None = None,
    constraints: Mapping[str, Any] | None = None,
    generation: Mapping[str, Any] | None = None,
    version: int = 1,
    description: str | None = None,
) -> dict:
    """
    Create the master timetable document.

    Actual timetable lessons remain in ENTRIES.
    """

    school = _id(
        school_id
    )

    creator = _id(
        created_by
    )

    if not school:

        raise ValueError(
            "school_id is required."
        )

    if not creator:

        raise ValueError(
            "created_by is required."
        )

    normalized_status = (
        _text(
            status
        ).lower()
        or STATUS_DRAFT
    )

    if (
        normalized_status
        not in TIMETABLE_STATUSES
    ):

        raise ValueError(
            f"Invalid timetable status: "
            f"{normalized_status}"
        )

    normalized_version = _whole_number(
        version,
        field_name="version",
        minimum=1,
        maximum=1_000_000,
    )

    normalized_weekdays = normalize_weekdays(
        weekdays
    )

    if not normalized_weekdays:

        raise ValueError(
            "At least one timetable weekday is required."
        )

    normalized_periods = normalize_periods(
        periods
    )

    if not normalized_periods:

        raise ValueError(
            "At least one timetable period is required."
        )

    if not any(
        period["type"]
        == PERIOD_LESSON
        for period
        in normalized_periods
    ):

        raise ValueError(
            "At least one lesson period is required."
        )

    normalized_requirements = (
        normalize_requirements(
            requirements
        )
    )

    if not normalized_requirements:

        raise ValueError(
            "At least one timetable requirement is required."
        )

    # -----------------------------------------------------
    # Validate all referenced period IDs.
    # -----------------------------------------------------

    known_period_ids = {
        period[
            "period_id"
        ]
        for period
        in normalized_periods
    }

    for requirement in normalized_requirements:

        for period_id in (
            requirement[
                "preferred_period_ids"
            ]
            + requirement[
                "avoid_period_ids"
            ]
        ):

            if (
                period_id
                not in known_period_ids
            ):

                raise ValueError(
                    f"Unknown timetable period id "
                    f"'{period_id}' in requirement "
                    f"'{requirement['subject']}'."
                )

        for blocked_slot in requirement[
            "blocked_slots"
        ]:

            _day, blocked_period_id = (
                blocked_slot.split(
                    "::",
                    1,
                )
            )

            if (
                blocked_period_id
                not in known_period_ids
            ):

                raise ValueError(
                    f"Unknown timetable period id "
                    f"'{blocked_period_id}' "
                    "in blocked_slots."
                )

    normalized_constraints = (
        normalize_constraints(
            constraints
        )
    )

    normalized_generation = (
        normalize_generation(
            generation
        )
    )

    now = now_utc()

    return {
        "model_version": (
            TIMETABLE_MODEL_VERSION
        ),

        "school_id": school,

        "name": (
            _text(
                name
            )
            or "Academic Timetable"
        ),

        "description": (
            _text(
                description
            )
            or None
        ),

        "status": normalized_status,

        "version": normalized_version,

        "academic_year": (
            _text(
                academic_year
            )
            or None
        ),

        "term": (
            _text(
                term
            )
            or None
        ),

        "weekdays": normalized_weekdays,

        "periods": normalized_periods,

        "requirements": (
            normalized_requirements
        ),

        "constraints": (
            normalized_constraints
        ),

        "generation": (
            normalized_generation
        ),

        "created_by": creator,

        "created_at": now,

        "updated_at": now,

        "generated_at": None,

        "generation_started_at": None,

        "generation_error": None,

        "validation": None,

        "published_at": None,

        "published_by": None,
    }


# =========================================================
# TIMETABLE ENTRY
# =========================================================

def entry_doc(
    school_id: Any,
    timetable_id: Any,
    requirement: Mapping[str, Any],
    slot: Mapping[str, Any],
    *,
    generated_by: Any = None,
) -> dict:
    """
    Create one actual lesson entry.

    Entry documents contain only canonical persisted lesson information.

    Double lessons are represented as two consecutive lesson entries.
    Their relation remains derivable from the timetable requirement and
    selected adjacent periods.
    """

    school = _id(
        school_id
    )

    timetable = _id(
        timetable_id
    )

    if not school:

        raise ValueError(
            "school_id is required."
        )

    if not timetable:

        raise ValueError(
            "timetable_id is required."
        )

    normalized_requirement = (
        normalize_requirement(
            requirement
        )
    )

    if not isinstance(
        slot,
        Mapping,
    ):

        raise ValueError(
            "Timetable slot must be an object."
        )

    day = (
        _text(
            slot.get(
                "day"
            )
        ).lower()
    )

    if day not in VALID_WEEKDAYS:

        raise ValueError(
            "Invalid timetable entry day."
        )

    period_id = _id(
        slot.get(
            "period_id"
        )
    )

    if not period_id:

        raise ValueError(
            "period_id is required."
        )

    period_type = (
        _text(
            slot.get(
                "period_type",
                slot.get(
                    "type",
                    PERIOD_LESSON,
                ),
            )
        ).lower()
        or PERIOD_LESSON
    )

    if period_type not in PERIOD_TYPES:

        raise ValueError(
            f"Invalid timetable entry period type: "
            f"{period_type}"
        )

    if period_type != PERIOD_LESSON:

        raise ValueError(
            "Timetable lesson entries must use "
            "a lesson period."
        )

    now = now_utc()

    return {
        "model_version": (
            TIMETABLE_MODEL_VERSION
        ),

        "school_id": school,

        "timetable_id": timetable,

        "class_id": normalized_requirement[
            "class_id"
        ],

        "teacher_user_id": normalized_requirement[
            "teacher_user_id"
        ],

        "subject": normalized_requirement[
            "subject"
        ],

        "room_id": normalized_requirement.get(
            "room_id"
        ),

        "day": day,

        "period_id": period_id,

        "start_time": (
            _text(
                slot.get(
                    "start_time"
                )
            )
            or None
        ),

        "end_time": (
            _text(
                slot.get(
                    "end_time"
                )
            )
            or None
        ),

        "period_type": PERIOD_LESSON,

        "created_at": now,

        "updated_at": now,

        "generated_by": (
            _id(
                generated_by
            )
            if generated_by is not None
            else None
        ),
    }


# =========================================================
# PUBLICATION UPDATE HELPERS
# =========================================================

def published_fields(
    user_id: Any,
) -> dict:
    """
    Fields applied when a timetable becomes published.
    """

    user = _id(
        user_id
    )

    if not user:

        raise ValueError(
            "Publishing user is required."
        )

    timestamp = now_utc()

    return {
        "status": STATUS_PUBLISHED,

        "published_at": timestamp,

        "published_by": user,

        "updated_at": timestamp,
    }


# =========================================================
# ARCHIVE UPDATE HELPERS
# =========================================================

def archived_fields() -> dict:

    timestamp = now_utc()

    return {
        "status": STATUS_ARCHIVED,
        "updated_at": timestamp,
    }