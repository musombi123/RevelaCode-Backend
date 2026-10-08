# backend/jumuiya/elimu/timetable/validator.py

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


# =========================================================
# CONSTANTS
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


# =========================================================
# NORMALIZATION HELPERS
# =========================================================

def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    if isinstance(
        value,
        bool,
    ):
        return default

    try:
        return int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return default


def _text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(
        value
    ).strip()


def _normalise_day(
    value: Any,
) -> str:
    return _text(
        value
    ).lower()


def _normalise_period_id(
    value: Any,
) -> str:
    return _text(
        value
    )


def _normalise_subject(
    value: Any,
) -> str:
    return _text(
        value
    ).lower()


def _normalise_resource(
    value: Any,
) -> str:
    return _text(
        value
    )


def _slot_key(
    day: Any,
    period_id: Any,
) -> str:
    return (
        f"{_normalise_day(day)}::"
        f"{_normalise_period_id(period_id)}"
    )


def _normalise_slots(
    values: Any,
) -> set[str]:
    if values is None:
        return set()

    if isinstance(
        values,
        str,
    ):
        values = [
            values
        ]

    if not isinstance(
        values,
        Iterable,
    ):
        return set()

    output = set()

    for value in values:
        text = _text(
            value
        ).lower()

        if text:
            output.add(
                text
            )

    return output


def _normalise_day_set(
    values: Any,
) -> set[str]:
    if values is None:
        return set()

    if isinstance(
        values,
        str,
    ):
        values = [
            values
        ]

    if not isinstance(
        values,
        Iterable,
    ):
        return set()

    return {
        _normalise_day(value)
        for value in values
        if _normalise_day(value)
    }


def _normalise_period_set(
    values: Any,
) -> set[str]:
    if values is None:
        return set()

    if isinstance(
        values,
        str,
    ):
        values = [
            values
        ]

    if not isinstance(
        values,
        Iterable,
    ):
        return set()

    return {
        _normalise_period_id(value)
        for value in values
        if _normalise_period_id(value)
    }


# =========================================================
# FIELD COMPATIBILITY
# =========================================================

def _requirement_periods(
    requirement: Mapping[str, Any],
) -> int:
    """
    Canonical field:
        lessons_per_week

    Legacy compatibility field:
        periods_per_week
    """

    if "lessons_per_week" in requirement:
        return _safe_int(
            requirement.get(
                "lessons_per_week"
            ),
            default=-1,
        )

    return _safe_int(
        requirement.get(
            "periods_per_week",
            0,
        ),
        default=-1,
    )


def _requirement_allows_double(
    requirement: Mapping[str, Any],
) -> bool:
    """
    Canonical field:
        double_lesson

    Legacy compatibility field:
        allow_double
    """

    if "double_lesson" in requirement:
        return bool(
            requirement.get(
                "double_lesson",
                False,
            )
        )

    return bool(
        requirement.get(
            "allow_double",
            False,
        )
    )


def _requirement_double_count(
    requirement: Mapping[str, Any],
) -> Optional[int]:
    """
    Optional exact double count.

    This is supported when supplied by an advanced/legacy
    requirement, but is not required by the canonical schema.
    """

    if (
        "double_lessons_per_week"
        not in requirement
    ):
        return None

    value = _safe_int(
        requirement.get(
            "double_lessons_per_week"
        ),
        default=-1,
    )

    return value


def _requirement_blocked_slots(
    requirement: Mapping[str, Any],
) -> set[str]:
    """
    Supports:
      - blocked_slots directly
      - canonical avoid_days
      - canonical avoid_period_ids

    `services.py` may already flatten the canonical fields into
    blocked_slots, but the validator can safely understand both.
    """

    blocked = _normalise_slots(
        requirement.get(
            "blocked_slots",
            [],
        )
    )

    avoid_days = _normalise_day_set(
        requirement.get(
            "avoid_days",
            [],
        )
    )

    avoid_periods = _normalise_period_set(
        requirement.get(
            "avoid_period_ids",
            [],
        )
    )

    # We cannot construct every possible slot without knowing the
    # timetable periods, so direct blocked_slots remain authoritative.
    #
    # When entries are checked below, avoid_days and
    # avoid_period_ids are independently enforced.
    return blocked


def _requirement_key(
    requirement: Mapping[str, Any],
) -> tuple[str, str, str]:
    return (
        _normalise_resource(
            requirement.get(
                "class_id"
            )
        ),
        _normalise_resource(
            requirement.get(
                "teacher_user_id"
            )
        ),
        _normalise_subject(
            requirement.get(
                "subject"
            )
        ),
    )


def _entry_key(
    entry: Mapping[str, Any],
) -> tuple:
    return (
        _normalise_day(
            entry.get(
                "day"
            )
        ),
        _normalise_period_id(
            entry.get(
                "period_id"
            )
        ),
        _normalise_resource(
            entry.get(
                "class_id"
            )
        ),
        _normalise_resource(
            entry.get(
                "teacher_user_id"
            )
        ),
        _normalise_subject(
            entry.get(
                "subject"
            )
        ),
        _normalise_resource(
            entry.get(
                "room_id"
            )
        ),
    )


def _entry_matches_requirement(
    entry: Mapping[str, Any],
    requirement: Mapping[str, Any],
) -> bool:
    return (
        _normalise_resource(
            entry.get(
                "class_id"
            )
        )
        == _normalise_resource(
            requirement.get(
                "class_id"
            )
        )
        and
        _normalise_resource(
            entry.get(
                "teacher_user_id"
            )
        )
        == _normalise_resource(
            requirement.get(
                "teacher_user_id"
            )
        )
        and
        _normalise_subject(
            entry.get(
                "subject"
            )
        )
        == _normalise_subject(
            requirement.get(
                "subject"
            )
        )
    )


# =========================================================
# STRUCTURAL VALIDATION
# =========================================================

def _validate_entry_shape(
    entries: Sequence[Dict[str, Any]],
    errors: List[Dict[str, Any]],
) -> None:
    required_fields = (
        "day",
        "period_id",
        "class_id",
        "teacher_user_id",
        "subject",
    )

    for index, entry in enumerate(
        entries
    ):
        if not isinstance(
            entry,
            dict,
        ):
            errors.append(
                {
                    "type": "invalid_entry",
                    "index": index,
                    "entry": entry,
                }
            )
            continue

        missing = [
            field
            for field in required_fields
            if not _text(
                entry.get(
                    field
                )
            )
        ]

        if missing:
            errors.append(
                {
                    "type": "missing_entry_fields",
                    "index": index,
                    "missing": missing,
                    "entry": entry,
                }
            )

            continue

        day = _normalise_day(
            entry.get(
                "day"
            )
        )

        if day not in VALID_WEEKDAYS:
            errors.append(
                {
                    "type": "invalid_entry_day",
                    "index": index,
                    "day": day,
                }
            )


def _validate_duplicates(
    entries: Sequence[Dict[str, Any]],
    errors: List[Dict[str, Any]],
) -> None:
    """
    Exact duplicate entry detection.

    Resource conflicts are checked separately.
    """

    seen = Counter(
        _entry_key(entry)
        for entry in entries
        if isinstance(
            entry,
            dict,
        )
    )

    for key, count in seen.items():
        if count > 1:
            errors.append(
                {
                    "type": "duplicate_entry",
                    "entry_key": key,
                    "count": count,
                }
            )


# =========================================================
# RESOURCE CONFLICTS
# =========================================================

def _validate_slot_conflicts(
    entries: Sequence[Dict[str, Any]],
    errors: List[Dict[str, Any]],
) -> None:
    """
    One time slot cannot contain:

      - the same teacher twice
      - the same class twice
      - the same room twice
    """

    buckets: Dict[
        tuple[str, str],
        List[Dict[str, Any]],
    ] = defaultdict(list)

    for entry in entries:
        if not isinstance(
            entry,
            dict,
        ):
            continue

        buckets[
            (
                _normalise_day(
                    entry.get(
                        "day"
                    )
                ),
                _normalise_period_id(
                    entry.get(
                        "period_id"
                    )
                ),
            )
        ].append(
            entry
        )

    for slot, items in buckets.items():

        teacher_counts = Counter(
            _normalise_resource(
                item.get(
                    "teacher_user_id"
                )
            )
            for item in items
            if _normalise_resource(
                item.get(
                    "teacher_user_id"
                )
            )
        )

        class_counts = Counter(
            _normalise_resource(
                item.get(
                    "class_id"
                )
            )
            for item in items
            if _normalise_resource(
                item.get(
                    "class_id"
                )
            )
        )

        room_counts = Counter(
            _normalise_resource(
                item.get(
                    "room_id"
                )
            )
            for item in items
            if _normalise_resource(
                item.get(
                    "room_id"
                )
            )
        )

        for teacher_id, count in teacher_counts.items():
            if count > 1:
                errors.append(
                    {
                        "type": "teacher_conflict",
                        "slot": slot,
                        "teacher_user_id": teacher_id,
                        "count": count,
                    }
                )

        for class_id, count in class_counts.items():
            if count > 1:
                errors.append(
                    {
                        "type": "class_conflict",
                        "slot": slot,
                        "class_id": class_id,
                        "count": count,
                    }
                )

        for room_id, count in room_counts.items():
            if count > 1:
                errors.append(
                    {
                        "type": "room_conflict",
                        "slot": slot,
                        "room_id": room_id,
                        "count": count,
                    }
                )


# =========================================================
# TEACHER AVAILABILITY
# =========================================================

def _validate_teacher_unavailability(
    entries: Sequence[Dict[str, Any]],
    teacher_unavailable: Optional[Dict[Any, Any]],
    errors: List[Dict[str, Any]],
) -> None:
    unavailable = (
        teacher_unavailable
        or {}
    )

    if not isinstance(
        unavailable,
        dict,
    ):
        return

    normalized_unavailable = {}

    for teacher_id, blocked in unavailable.items():

        normalized_unavailable[
            _normalise_resource(
                teacher_id
            )
        ] = _normalise_slots(
            blocked
        )

    for entry in entries:

        if not isinstance(
            entry,
            dict,
        ):
            continue

        teacher_id = _normalise_resource(
            entry.get(
                "teacher_user_id"
            )
        )

        blocked = normalized_unavailable.get(
            teacher_id,
            set(),
        )

        slot = _slot_key(
            entry.get(
                "day"
            ),
            entry.get(
                "period_id"
            ),
        )

        if slot in blocked:
            errors.append(
                {
                    "type": "teacher_unavailable",
                    "entry": entry,
                    "teacher_user_id": teacher_id,
                    "slot": slot,
                }
            )


# =========================================================
# REQUIREMENT STRUCTURE
# =========================================================

def _validate_requirement_values(
    requirements: Sequence[Dict[str, Any]],
    errors: List[Dict[str, Any]],
) -> None:

    seen_keys = set()

    for requirement in requirements:

        if not isinstance(
            requirement,
            dict,
        ):
            errors.append(
                {
                    "type": "invalid_requirement",
                    "requirement": requirement,
                }
            )
            continue

        key = _requirement_key(
            requirement
        )

        if not all(key):
            errors.append(
                {
                    "type": "invalid_requirement_identity",
                    "key": key,
                    "requirement": requirement,
                }
            )
            continue

        if key in seen_keys:
            errors.append(
                {
                    "type": "duplicate_requirement",
                    "key": key,
                }
            )

        seen_keys.add(
            key
        )

        periods_per_week = _requirement_periods(
            requirement
        )

        if periods_per_week < 0:
            errors.append(
                {
                    "type": "invalid_periods_per_week",
                    "key": key,
                    "periods_per_week": periods_per_week,
                }
            )

        # -------------------------------------------------
        # Double lesson validation.
        #
        # IMPORTANT:
        # An odd number such as 5 is valid.
        #
        # Example:
        #     1 double = 2 periods
        #     3 singles = 3 periods
        #     total = 5
        # -------------------------------------------------

        allows_double = _requirement_allows_double(
            requirement
        )

        double_count = _requirement_double_count(
            requirement
        )

        if double_count is not None:

            if double_count < 0:
                errors.append(
                    {
                        "type": "invalid_double_lesson_count",
                        "key": key,
                        "double_lessons_per_week": double_count,
                    }
                )

            if not allows_double and double_count > 0:
                errors.append(
                    {
                        "type": "double_lessons_not_allowed",
                        "key": key,
                    }
                )

            if (
                double_count >= 0
                and periods_per_week >= 0
                and double_count * 2
                > periods_per_week
            ):
                errors.append(
                    {
                        "type": "double_lessons_exceed_weekly_periods",
                        "key": key,
                        "periods_per_week": periods_per_week,
                        "double_lessons_per_week": double_count,
                    }
                )

        # -------------------------------------------------
        # Canonical double_lesson=False means the generator
        # must not create a double block, but it does not
        # invalidate an odd/even weekly count.
        # -------------------------------------------------

        if not allows_double:
            continue


# =========================================================
# REQUIREMENT PERIOD COUNTS
# =========================================================

def _validate_requirement_periods(
    entries: Sequence[Dict[str, Any]],
    requirements: Sequence[Dict[str, Any]],
    errors: List[Dict[str, Any]],
) -> None:

    actual = Counter(
        (
            _normalise_resource(
                entry.get(
                    "class_id"
                )
            ),
            _normalise_resource(
                entry.get(
                    "teacher_user_id"
                )
            ),
            _normalise_subject(
                entry.get(
                    "subject"
                )
            ),
        )
        for entry in entries
        if isinstance(
            entry,
            dict,
        )
    )

    required_keys = set()

    for requirement in requirements:

        if not isinstance(
            requirement,
            dict,
        ):
            continue

        key = _requirement_key(
            requirement
        )

        required_keys.add(
            key
        )

        expected = _requirement_periods(
            requirement
        )

        if expected < 0:
            continue

        actual_count = actual[
            key
        ]

        if actual_count != expected:
            errors.append(
                {
                    "type": "required_periods_mismatch",
                    "key": key,
                    "expected": expected,
                    "actual": actual_count,
                }
            )

    # -----------------------------------------------------
    # Generated entries must not exist without a declared
    # requirement.
    # -----------------------------------------------------

    for key, actual_count in actual.items():

        if key not in required_keys:
            errors.append(
                {
                    "type": "entry_without_requirement",
                    "key": key,
                    "actual": actual_count,
                }
            )


# =========================================================
# REQUIREMENT RESTRICTIONS
# =========================================================

def _validate_requirement_restrictions(
    entries: Sequence[Dict[str, Any]],
    requirements: Sequence[Dict[str, Any]],
    errors: List[Dict[str, Any]],
) -> None:

    for requirement in requirements:

        if not isinstance(
            requirement,
            dict,
        ):
            continue

        matching_entries = [
            entry
            for entry in entries
            if isinstance(
                entry,
                dict,
            )
            and _entry_matches_requirement(
                entry,
                requirement,
            )
        ]

        if not matching_entries:
            continue

        blocked_slots = _requirement_blocked_slots(
            requirement
        )

        avoid_days = _normalise_day_set(
            requirement.get(
                "avoid_days",
                [],
            )
        )

        avoid_periods = _normalise_period_set(
            requirement.get(
                "avoid_period_ids",
                [],
            )
        )

        for entry in matching_entries:

            day = _normalise_day(
                entry.get(
                    "day"
                )
            )

            period_id = _normalise_period_id(
                entry.get(
                    "period_id"
                )
            )

            slot = _slot_key(
                day,
                period_id,
            )

            if slot in blocked_slots:
                errors.append(
                    {
                        "type": "requirement_blocked_slot",
                        "slot": slot,
                        "entry": entry,
                        "key": _requirement_key(
                            requirement
                        ),
                    }
                )

            if day in avoid_days:
                errors.append(
                    {
                        "type": "requirement_avoid_day_violation",
                        "day": day,
                        "entry": entry,
                        "key": _requirement_key(
                            requirement
                        ),
                    }
                )

            if period_id in avoid_periods:
                errors.append(
                    {
                        "type": "requirement_avoid_period_violation",
                        "period_id": period_id,
                        "entry": entry,
                        "key": _requirement_key(
                            requirement
                        ),
                    }
                )


# =========================================================
# PREFERRED DAYS
# =========================================================

def _validate_preferred_days(
    entries: Sequence[Dict[str, Any]],
    requirements: Sequence[Dict[str, Any]],
    warnings: List[Dict[str, Any]],
) -> None:
    """
    Preferred days are soft constraints.

    They produce warnings and never invalidate an otherwise
    conflict-free timetable.
    """

    for requirement in requirements:

        if not isinstance(
            requirement,
            dict,
        ):
            continue

        preferred_days = _normalise_day_set(
            requirement.get(
                "preferred_days",
                [],
            )
        )

        if not preferred_days:
            continue

        matching_entries = [
            entry
            for entry in entries
            if isinstance(
                entry,
                dict,
            )
            and _entry_matches_requirement(
                entry,
                requirement,
            )
        ]

        for entry in matching_entries:

            actual_day = _normalise_day(
                entry.get(
                    "day"
                )
            )

            if (
                actual_day
                and actual_day
                not in preferred_days
            ):
                warnings.append(
                    {
                        "type": "preferred_day_violation",
                        "entry": entry,
                        "preferred_days": sorted(
                            preferred_days
                        ),
                        "actual_day": actual_day,
                        "key": _requirement_key(
                            requirement
                        ),
                    }
                )


# =========================================================
# PREFERRED PERIODS
# =========================================================

def _validate_preferred_periods(
    entries: Sequence[Dict[str, Any]],
    requirements: Sequence[Dict[str, Any]],
    warnings: List[Dict[str, Any]],
) -> None:
    """
    preferred_period_ids are soft constraints.
    """

    for requirement in requirements:

        preferred_periods = _normalise_period_set(
            requirement.get(
                "preferred_period_ids",
                [],
            )
        )

        if not preferred_periods:
            continue

        matching_entries = [
            entry
            for entry in entries
            if isinstance(
                entry,
                dict,
            )
            and _entry_matches_requirement(
                entry,
                requirement,
            )
        ]

        for entry in matching_entries:

            period_id = _normalise_period_id(
                entry.get(
                    "period_id"
                )
            )

            if period_id not in preferred_periods:
                warnings.append(
                    {
                        "type": "preferred_period_violation",
                        "entry": entry,
                        "preferred_period_ids": sorted(
                            preferred_periods
                        ),
                        "actual_period_id": period_id,
                        "key": _requirement_key(
                            requirement
                        ),
                    }
                )


# =========================================================
# KNOWN TIMETABLE SLOTS
# =========================================================

def _validate_known_slots(
    entries: Sequence[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    *,
    weekdays: Optional[Sequence[Any]] = None,
    periods: Optional[Sequence[Dict[str, Any]]] = None,
) -> None:
    """
    Strong timetable-level validation.

    When weekday/period definitions are supplied:
      - day must exist
      - period_id must exist
      - period must be a lesson period
    """

    known_days = {
        _normalise_day(day)
        for day in (
            weekdays
            or []
        )
        if _normalise_day(day)
    }

    period_map = {}

    for period in (
        periods
        or []
    ):
        if not isinstance(
            period,
            dict,
        ):
            continue

        period_id = (
            period.get(
                "period_id"
            )
            or period.get(
                "id"
            )
        )

        period_id = _normalise_period_id(
            period_id
        )

        if not period_id:
            continue

        if period_id in period_map:
            errors.append(
                {
                    "type": "duplicate_period_definition",
                    "period_id": period_id,
                }
            )
            continue

        period_map[
            period_id
        ] = period

    for entry in entries:

        if not isinstance(
            entry,
            dict,
        ):
            continue

        day = _normalise_day(
            entry.get(
                "day"
            )
        )

        period_id = _normalise_period_id(
            entry.get(
                "period_id"
            )
        )

        if known_days and day not in known_days:
            errors.append(
                {
                    "type": "unknown_timetable_day",
                    "entry": entry,
                    "day": day,
                }
            )

        if period_map:

            period = period_map.get(
                period_id
            )

            if period is None:
                errors.append(
                    {
                        "type": "unknown_timetable_period",
                        "entry": entry,
                        "period_id": period_id,
                    }
                )

                continue

            period_type = _text(
                period.get(
                    "type"
                )
                or period.get(
                    "kind"
                )
                or "lesson"
            ).lower()

            if period_type != "lesson":
                errors.append(
                    {
                        "type": "non_lesson_period",
                        "entry": entry,
                        "period_id": period_id,
                        "period_type": period_type,
                    }
                )


# =========================================================
# OPTIONAL DAILY LIMITS
# =========================================================

def _validate_daily_limits(
    entries: Sequence[Dict[str, Any]],
    errors: List[Dict[str, Any]],
    *,
    max_class_periods_per_day: Optional[int] = None,
    max_teacher_periods_per_day: Optional[int] = None,
    max_room_periods_per_day: Optional[int] = None,
) -> None:

    class_daily = Counter()
    teacher_daily = Counter()
    room_daily = Counter()

    for entry in entries:

        day = _normalise_day(
            entry.get(
                "day"
            )
        )

        class_id = _normalise_resource(
            entry.get(
                "class_id"
            )
        )

        teacher_id = _normalise_resource(
            entry.get(
                "teacher_user_id"
            )
        )

        room_id = _normalise_resource(
            entry.get(
                "room_id"
            )
        )

        if class_id:
            class_daily[
                (
                    class_id,
                    day,
                )
            ] += 1

        if teacher_id:
            teacher_daily[
                (
                    teacher_id,
                    day,
                )
            ] += 1

        if room_id:
            room_daily[
                (
                    room_id,
                    day,
                )
            ] += 1

    if max_class_periods_per_day is not None:

        for (
            class_id,
            day,
        ), count in class_daily.items():

            if count > max_class_periods_per_day:
                errors.append(
                    {
                        "type": "class_daily_limit_exceeded",
                        "class_id": class_id,
                        "day": day,
                        "count": count,
                        "maximum": max_class_periods_per_day,
                    }
                )

    if max_teacher_periods_per_day is not None:

        for (
            teacher_id,
            day,
        ), count in teacher_daily.items():

            if count > max_teacher_periods_per_day:
                errors.append(
                    {
                        "type": "teacher_daily_limit_exceeded",
                        "teacher_user_id": teacher_id,
                        "day": day,
                        "count": count,
                        "maximum": max_teacher_periods_per_day,
                    }
                )

    if max_room_periods_per_day is not None:

        for (
            room_id,
            day,
        ), count in room_daily.items():

            if count > max_room_periods_per_day:
                errors.append(
                    {
                        "type": "room_daily_limit_exceeded",
                        "room_id": room_id,
                        "day": day,
                        "count": count,
                        "maximum": max_room_periods_per_day,
                    }
                )


# =========================================================
# MAIN VALIDATOR
# =========================================================

def validate(
    entries: Optional[
        Sequence[Dict[str, Any]]
    ],
    requirements: Optional[
        Sequence[Dict[str, Any]]
    ] = None,
    teacher_unavailable: Optional[
        Dict[Any, Any]
    ] = None,
    *,
    weekdays: Optional[
        Sequence[Any]
    ] = None,
    periods: Optional[
        Sequence[Dict[str, Any]]
    ] = None,
    max_class_periods_per_day: Optional[
        int
    ] = None,
    max_teacher_periods_per_day: Optional[
        int
    ] = None,
    max_room_periods_per_day: Optional[
        int
    ] = None,
) -> Dict[str, Any]:
    """
    Authoritative Elimu timetable validator.

    Backward-compatible call:

        validate(
            entries,
            requirements,
            teacher_unavailable,
        )

    Strong timetable-aware call:

        validate(
            entries,
            requirements,
            teacher_unavailable,
            weekdays=weekdays,
            periods=periods,
        )

    Hard constraints:
        - required entry fields
        - valid weekdays
        - duplicate entries
        - teacher conflicts
        - class conflicts
        - room conflicts
        - teacher unavailable slots
        - required weekly lesson counts
        - entry must correspond to a requirement
        - blocked slots
        - avoided days
        - avoided periods
        - valid timetable days/periods when definitions supplied
        - lesson periods only
        - optional daily resource limits

    Soft constraints:
        - preferred days
        - preferred periods
    """

    errors: List[
        Dict[str, Any]
    ] = []

    warnings: List[
        Dict[str, Any]
    ] = []

    safe_entries = [
        entry
        for entry in (
            entries
            or []
        )
        if isinstance(
            entry,
            dict,
        )
    ]

    safe_requirements = [
        requirement
        for requirement in (
            requirements
            or []
        )
        if isinstance(
            requirement,
            dict,
        )
    ]

    # -----------------------------------------------------
    # Structure
    # -----------------------------------------------------

    _validate_entry_shape(
        entries or [],
        errors,
    )

    _validate_duplicates(
        safe_entries,
        errors,
    )

    # -----------------------------------------------------
    # Resource collisions
    # -----------------------------------------------------

    _validate_slot_conflicts(
        safe_entries,
        errors,
    )

    # -----------------------------------------------------
    # Teacher availability
    # -----------------------------------------------------

    _validate_teacher_unavailability(
        safe_entries,
        teacher_unavailable,
        errors,
    )

    # -----------------------------------------------------
    # Requirements
    # -----------------------------------------------------

    if safe_requirements:

        _validate_requirement_values(
            safe_requirements,
            errors,
        )

        _validate_requirement_periods(
            safe_entries,
            safe_requirements,
            errors,
        )

        _validate_requirement_restrictions(
            safe_entries,
            safe_requirements,
            errors,
        )

        _validate_preferred_days(
            safe_entries,
            safe_requirements,
            warnings,
        )

        _validate_preferred_periods(
            safe_entries,
            safe_requirements,
            warnings,
        )

    # -----------------------------------------------------
    # Known timetable structure
    # -----------------------------------------------------

    if (
        weekdays is not None
        or periods is not None
    ):
        _validate_known_slots(
            safe_entries,
            errors,
            weekdays=weekdays,
            periods=periods,
        )

    # -----------------------------------------------------
    # Optional daily resource limits
    # -----------------------------------------------------

    _validate_daily_limits(
        safe_entries,
        errors,
        max_class_periods_per_day=(
            max_class_periods_per_day
        ),
        max_teacher_periods_per_day=(
            max_teacher_periods_per_day
        ),
        max_room_periods_per_day=(
            max_room_periods_per_day
        ),
    )

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "error_count": len(
            errors
        ),
        "warning_count": len(
            warnings
        ),
        "summary": {
            "entries": len(
                safe_entries
            ),
            "requirements": len(
                safe_requirements
            ),
            "has_errors": bool(
                errors
            ),
            "has_warnings": bool(
                warnings
            ),
        },
    }