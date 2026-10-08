"""
Advanced deterministic constraint-based timetable generator.

This module is intentionally independent from MongoDB, authorization,
HTTP/API concerns, and Elimu membership logic.

The service layer is responsible for adapting the canonical Elimu timetable
schema into this generator's compatibility contract.

Generator input contract
------------------------

weekdays:
    [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
    ]

periods:
    [
        {
            "id": "p1",
            "name": "Period 1",
            "start_time": "08:00",
            "end_time": "08:40",
            "kind": "lesson",
        },
        {
            "id": "break1",
            "name": "Tea Break",
            "start_time": "10:00",
            "end_time": "10:20",
            "kind": "break",
        },
        {
            "id": "p3",
            "name": "Period 3",
            "start_time": "10:20",
            "end_time": "11:00",
            "kind": "lesson",
        },
    ]

requirements:
    [
        {
            "class_id": "...",
            "teacher_user_id": "...",
            "subject": "Mathematics",

            "periods_per_week": 4,

            "room_id": "...",

            "allow_double": True,
            "double_lessons_per_week": 1,

            "preferred_days": [
                "monday",
                "wednesday",
            ],

            "avoid_days": [
                "friday",
            ],

            "preferred_period_ids": [
                "p1",
                "p2",
            ],

            "avoid_period_ids": [
                "p7",
            ],

            "blocked_slots": [
                "friday::p5",
            ],

            "max_lessons_per_day": 2,
            "min_gap_periods": 1,
            "min_days_between": 0,

            "priority": 25,
        }
    ]

Optional generator rules:
-------------------------

generate(
    ...,
    rules={
        "max_class_periods_per_day": 8,
        "max_teacher_periods_per_day": 7,
        "max_room_periods_per_day": 8,
        "max_consecutive_periods": 4,
    }
)

Hard constraints
----------------

1. A class cannot have two lessons in the same slot.
2. A teacher cannot teach two lessons in the same slot.
3. A room cannot host two lessons in the same slot.
4. blocked_slots cannot be used.
5. avoid_days cannot be used.
6. avoid_period_ids cannot be used.
7. Only lesson periods can be scheduled.
8. Double lessons occupy two genuinely adjacent lesson periods.
9. A break/non-lesson period ALWAYS breaks double adjacency.
10. max_lessons_per_day is respected when supplied.
11. min_gap_periods is respected when supplied.
12. min_days_between is respected when supplied.
13. Generator-wide daily resource limits are respected when supplied.
14. max_consecutive_periods is respected when supplied.

Soft constraints
----------------

1. preferred_days are preferred.
2. preferred_period_ids are preferred.
3. requirements with higher priority are scheduled earlier.
4. double lessons are placed naturally where requested.
5. lessons are spread across days when possible.
6. classes, teachers, and rooms are balanced across the day.
7. repeated same-subject placement on the same day is discouraged.
8. unnecessary consecutive same-requirement lessons are discouraged.
9. stable period/day ordering is used as a final deterministic tie-breaker.

Design principle
----------------

The generator creates a valid timetable candidate.

The server-side validator remains authoritative.

RevelaAI may suggest or optimize schedules later, but every final schedule
must pass the validator before it can be persisted.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


# =========================================================
# VERSION / CONSTANTS
# =========================================================

GENERATOR_VERSION = "3.1"

LESSON_KIND = "lesson"

DEFAULT_MAX_NODES = 100000


# =========================================================
# ERRORS
# =========================================================


class GenerationError(Exception):
    """
    Raised when a conflict-free timetable cannot be generated.
    """


# =========================================================
# BASIC NORMALIZATION
# =========================================================


def _normalize_day(
    day: Any,
) -> str:
    return str(
        day
    ).strip().lower()


def _normalize_period_id(
    period_id: Any,
) -> str:
    return str(
        period_id
    ).strip()


def _slot_key(
    day: str,
    period_id: str,
) -> str:
    return (
        f"{_normalize_day(day)}::"
        f"{_normalize_period_id(period_id)}"
    )


def _safe_int(
    value: Any,
    default: int,
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


def _string_list(
    value: Any,
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
        (list, tuple, set),
    ):
        return []

    result = []

    for item in value:

        text = str(
            item
        ).strip()

        if text:
            result.append(
                text
            )

    return result


# =========================================================
# SLOT BUILDING
# =========================================================


def build_slots(
    weekdays: list[str],
    periods: list[dict],
) -> list[dict]:
    """
    Build all usable lesson slots.

    Important:
        `_period_index` refers to the ORIGINAL period list index.

    This allows the generator to distinguish:

        lesson -> lesson

    from:

        lesson -> break -> lesson

    A break therefore cannot accidentally become a double-lesson bridge.
    """

    if not isinstance(
        weekdays,
        list,
    ):
        raise GenerationError(
            "weekdays must be a list."
        )

    if not isinstance(
        periods,
        list,
    ):
        raise GenerationError(
            "periods must be a list."
        )

    normalized_weekdays = []

    seen_days = set()

    for day in weekdays:

        normalized = _normalize_day(
            day
        )

        if not normalized:
            continue

        if normalized in seen_days:
            continue

        seen_days.add(
            normalized
        )

        normalized_weekdays.append(
            normalized
        )

    if not normalized_weekdays:
        raise GenerationError(
            "At least one weekday is required."
        )

    slots = []

    seen_period_ids = set()

    segment = 0

    lesson_position = 0

    for period_index, period in enumerate(
        periods
    ):

        if not isinstance(
            period,
            dict,
        ):
            raise GenerationError(
                "Each timetable period must be an object."
            )

        period_id = _normalize_period_id(
            period.get(
                "id"
            )
        )

        if not period_id:
            raise GenerationError(
                "Every timetable period must have an 'id'."
            )

        # Period IDs must be unique across the ENTIRE period list,
        # including breaks and activities. Otherwise a non-lesson
        # period can collide with a lesson period in downstream
        # lookups and sorting.
        if period_id in seen_period_ids:
            raise GenerationError(
                f"Duplicate timetable period id '{period_id}'."
            )

        seen_period_ids.add(
            period_id
        )

        kind = str(
            period.get(
                "kind",
                LESSON_KIND,
            )
        ).strip().lower()

        # -------------------------------------------------
        # Non-lesson periods separate scheduling segments.
        #
        # A break, assembly, prayer, lunch, etc. therefore
        # breaks true double-lesson adjacency.
        # -------------------------------------------------

        if kind != LESSON_KIND:
            segment += 1
            continue

        for day_index, day in enumerate(
            normalized_weekdays
        ):

            slots.append(
                {
                    "day": day,
                    "day_index": day_index,

                    "period_id": period_id,

                    "start_time": period.get(
                        "start_time"
                    ),
                    "end_time": period.get(
                        "end_time"
                    ),
                    "kind": LESSON_KIND,

                    # Original timetable order.
                    "_period_index": period_index,

                    # Lesson-only ordering.
                    "_lesson_position": lesson_position,

                    # Segment separated by breaks.
                    "_segment": segment,
                }
            )

        lesson_position += 1

    if not slots:
        raise GenerationError(
            "No lesson periods are available."
        )

    return slots


def _slots_by_day(
    slots: list[dict],
) -> dict[str, list[dict]]:
    """
    Group slots by weekday while preserving original period order.
    """

    grouped: dict[
        str,
        list[dict],
    ] = {}

    for slot in slots:

        grouped.setdefault(
            slot["day"],
            [],
        ).append(
            slot
        )

    return grouped


def _double_slots(
    slots: list[dict],
) -> list[tuple[dict, dict]]:
    """
    Build valid double-lesson pairs.

    A valid pair requires:

        - same day
        - same segment
        - original period indexes differ by exactly one

    Therefore:

        P1 + P2       -> valid

        P1 + Break    -> invalid

        P2 + Break + P3
        -> invalid

    This fixes the major adjacency flaw from the previous generator.
    """

    grouped = _slots_by_day(
        slots
    )

    pairs = []

    for day_slots in grouped.values():

        for index in range(
            len(day_slots) - 1
        ):

            first = day_slots[
                index
            ]

            second = day_slots[
                index + 1
            ]

            if (
                first["_segment"]
                != second["_segment"]
            ):
                continue

            if (
                second["_period_index"]
                != first["_period_index"] + 1
            ):
                continue

            pairs.append(
                (
                    first,
                    second,
                )
            )

    return pairs


# =========================================================
# REQUIREMENT NORMALIZATION
# =========================================================


def _canonicalize_requirement(
    requirement: dict,
) -> dict:
    """
    Accept the canonical Elimu timetable requirement shape as well
    as the legacy generator shape.

    Canonical fields:
        lessons_per_week
        double_lesson

    Legacy fields:
        periods_per_week
        allow_double

    The service layer currently performs this adaptation, but
    keeping the generator tolerant makes it safer to call directly
    from tests and future orchestration code.
    """

    normalized = dict(requirement)

    if "periods_per_week" not in normalized:
        normalized[
            "periods_per_week"
        ] = normalized.get(
            "lessons_per_week",
            0,
        )

    if "allow_double" not in normalized:
        normalized[
            "allow_double"
        ] = normalized.get(
            "double_lesson",
            False,
        )

    return normalized


def _periods_per_week(
    requirement: dict,
) -> int:

    value = requirement.get(
        "periods_per_week",
        0,
    )

    if isinstance(
        value,
        bool,
    ):
        raise GenerationError(
            "periods_per_week must be an integer."
        )

    try:
        value = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        raise GenerationError(
            "periods_per_week must be an integer."
        )

    if value < 0:
        raise GenerationError(
            "periods_per_week cannot be negative."
        )

    return value


def _priority(
    requirement: dict,
) -> int:

    value = requirement.get(
        "priority",
        25,
    )

    if isinstance(
        value,
        bool,
    ):
        return 25

    try:
        return int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return 25


def _allow_double(
    requirement: dict,
) -> bool:

    return _safe_bool(
        requirement.get(
            "allow_double",
            False,
        ),
        False,
    )


def _double_lessons_per_week(
    requirement: dict,
) -> int:
    """
    Return the exact number of double-lesson blocks required.

    Semantics:

        allow_double=False
            -> doubles are prohibited

        allow_double=True
            -> doubles are permitted, but NOT automatically required

        double_lessons_per_week
            -> exact number of double blocks requested by the school

    Examples:

        periods_per_week=5
        allow_double=True
        double_lessons_per_week=1

            -> 1 double + 3 singles

        periods_per_week=5
        allow_double=True
        double_lessons_per_week=0

            -> 5 singles

        periods_per_week=4
        allow_double=False

            -> 4 singles
    """

    periods_per_week = _periods_per_week(
        requirement
    )

    allow_double = _allow_double(
        requirement
    )

    raw = requirement.get(
        "double_lessons_per_week"
    )

    # -----------------------------------------------------
    # No doubles permitted.
    # -----------------------------------------------------

    if not allow_double:

        if raw not in (
            None,
            0,
            "0",
        ):
            raise GenerationError(
                "double_lessons_per_week cannot be greater "
                "than zero when allow_double is false."
            )

        return 0

    # -----------------------------------------------------
    # Doubles permitted but none explicitly requested.
    # -----------------------------------------------------

    if raw is None:
        return 0

    value = _safe_int(
        raw,
        -1,
    )

    if value < 0:
        raise GenerationError(
            "double_lessons_per_week cannot be negative."
        )

    maximum = periods_per_week // 2

    if value > maximum:

        raise GenerationError(
            "double_lessons_per_week cannot exceed "
            "periods_per_week // 2."
        )

    return value

def _preferred_days(
    requirement: dict,
) -> set[str]:

    return {
        _normalize_day(
            value
        )
        for value in _string_list(
            requirement.get(
                "preferred_days",
                [],
            )
        )
    }


def _avoid_days(
    requirement: dict,
) -> set[str]:

    return {
        _normalize_day(
            value
        )
        for value in _string_list(
            requirement.get(
                "avoid_days",
                [],
            )
        )
    }


def _preferred_period_ids(
    requirement: dict,
) -> set[str]:

    return {
        _normalize_period_id(
            value
        )
        for value in _string_list(
            requirement.get(
                "preferred_period_ids",
                [],
            )
        )
    }


def _avoid_period_ids(
    requirement: dict,
) -> set[str]:

    return {
        _normalize_period_id(
            value
        )
        for value in _string_list(
            requirement.get(
                "avoid_period_ids",
                [],
            )
        )
    }


def _blocked_slots(
    requirement: dict,
) -> set[str]:

    return {
        str(value).strip().lower()
        for value in _string_list(
            requirement.get(
                "blocked_slots",
                [],
            )
        )
    }


def _max_lessons_per_day(
    requirement: dict,
) -> int | None:

    value = requirement.get(
        "max_lessons_per_day"
    )

    if value is None:
        return None

    value = _safe_int(
        value,
        -1,
    )

    if value < 0:
        raise GenerationError(
            "max_lessons_per_day cannot be negative."
        )

    return value


def _min_gap_periods(
    requirement: dict,
) -> int:

    value = _safe_int(
        requirement.get(
            "min_gap_periods",
            0,
        ),
        0,
    )

    if value < 0:
        raise GenerationError(
            "min_gap_periods cannot be negative."
        )

    return value


def _min_days_between(
    requirement: dict,
) -> int:

    value = _safe_int(
        requirement.get(
            "min_days_between",
            0,
        ),
        0,
    )

    if value < 0:
        raise GenerationError(
            "min_days_between cannot be negative."
        )

    return value


def _spread_across_days(
    requirement: dict,
) -> bool:

    return _safe_bool(
        requirement.get(
            "spread_across_days",
            True,
        ),
        True,
    )


def _avoid_consecutive(
    requirement: dict,
) -> bool:

    return _safe_bool(
        requirement.get(
            "avoid_consecutive",
            False,
        ),
        False,
    )


def _validate_requirement(
    requirement: dict,
) -> None:

    required = (
        "class_id",
        "teacher_user_id",
        "subject",
    )

    for field in required:

        if not str(
            requirement.get(
                field,
                "",
            )
        ).strip():

            raise GenerationError(
                f"Timetable requirement is missing "
                f"'{field}'."
            )

    periods_per_week = _periods_per_week(
        requirement
    )

    double_count = _double_lessons_per_week(
        requirement
    )

    if (
        double_count * 2
        > periods_per_week
    ):

        raise GenerationError(
            f"Requirement '{requirement.get('subject')}' "
            "has too many double lessons."
        )

    _max_lessons_per_day(
        requirement
    )

    _min_gap_periods(
        requirement
    )

    _min_days_between(
        requirement
    )


# =========================================================
# REQUIREMENT EXPANSION
# =========================================================


def _expand_requirements(
    requirements: list[dict],
) -> list[dict]:
    """
    Convert weekly requirements into scheduling units.

    A unit is either:

        single lesson
        or
        double lesson block
    """

    units = []

    for req_index, requirement in enumerate(
        requirements
    ):

        periods_per_week = _periods_per_week(
            requirement
        )

        if periods_per_week <= 0:
            continue

        double_count = _double_lessons_per_week(
            requirement
        )

        single_count = (
            periods_per_week
            - (
                double_count * 2
            )
        )

        occurrence = 0

        for _ in range(
            double_count
        ):

            units.append(
                {
                    "req_index": req_index,
                    "requirement": requirement,
                    "occurrence": occurrence,
                    "double": True,
                }
            )

            occurrence += 1

        for _ in range(
            single_count
        ):

            units.append(
                {
                    "req_index": req_index,
                    "requirement": requirement,
                    "occurrence": occurrence,
                    "double": False,
                }
            )

            occurrence += 1

    return units


# =========================================================
# STATE
# =========================================================


def _new_state() -> dict:
    return {
        "entries": [],

        "used_class": defaultdict(set),
        "used_teacher": defaultdict(set),
        "used_room": defaultdict(set),

        "class_day_periods": defaultdict(
            lambda: defaultdict(set)
        ),
        "teacher_day_periods": defaultdict(
            lambda: defaultdict(set)
        ),
        "room_day_periods": defaultdict(
            lambda: defaultdict(set)
        ),

        "requirement_day_units": defaultdict(
            Counter
        ),
        "requirement_day_periods": defaultdict(
            lambda: defaultdict(set)
        ),
        "requirement_days": defaultdict(
            set
        ),

        "requirement_subject_day": defaultdict(
            Counter
        ),

        "unit_assignments": {},
    }


# =========================================================
# ENTRY HELPERS
# =========================================================


def _candidate_slots(
    candidate: dict | tuple[dict, dict],
) -> list[dict]:

    if isinstance(
        candidate,
        tuple,
    ):
        return [
            candidate[0],
            candidate[1],
        ]

    return [
        candidate
    ]


def _candidate_days(
    candidate: dict | tuple[dict, dict],
) -> set[str]:

    return {
        slot["day"]
        for slot in _candidate_slots(
            candidate
        )
    }


def _candidate_period_indexes(
    candidate: dict | tuple[dict, dict],
) -> list[int]:

    return [
        slot["_period_index"]
        for slot in _candidate_slots(
            candidate
        )
    ]


def _make_entry(
    requirement: dict,
    slot: dict,
    occurrence: int,
) -> dict:
    """
    Public timetable entry.

    Internal fields are intentionally stripped.
    """

    return {
        "class_id": str(
            requirement[
                "class_id"
            ]
        ),
        "teacher_user_id": str(
            requirement[
                "teacher_user_id"
            ]
        ),
        "subject": str(
            requirement[
                "subject"
            ]
        ).strip(),
        "room_id": (
            requirement.get(
                "room_id"
            )
        ),
        "day": _normalize_day(
            slot["day"]
        ),
        "period_id": _normalize_period_id(
            slot["period_id"]
        ),
        "start_time": slot.get(
            "start_time"
        ),
        "end_time": slot.get(
            "end_time"
        ),
        "kind": LESSON_KIND,
        "occurrence": occurrence,
    }


# =========================================================
# RESOURCE OCCUPANCY
# =========================================================


def _resource_key(
    value: Any,
) -> str:

    return str(
        value
    ).strip()


def _resource_load(
    state: dict,
    resource_type: str,
    resource_id: str,
    day: str,
) -> int:

    mapping = {
        "class": state[
            "class_day_periods"
        ],
        "teacher": state[
            "teacher_day_periods"
        ],
        "room": state[
            "room_day_periods"
        ],
    }

    return len(
        mapping[
            resource_type
        ][
            resource_id
        ][
            day
        ]
    )


def _max_consecutive_for_day(
    period_indexes: set[int],
) -> int:

    if not period_indexes:
        return 0

    ordered = sorted(
        period_indexes
    )

    maximum = 1
    current = 1

    for index in range(
        1,
        len(ordered),
    ):

        if (
            ordered[index]
            == ordered[index - 1] + 1
        ):

            current += 1

            maximum = max(
                maximum,
                current,
            )

        else:

            current = 1

    return maximum


def _resource_consecutive_after(
    state: dict,
    resource_type: str,
    resource_id: str,
    candidate_slots: list[dict],
    max_consecutive_periods: int | None,
) -> bool:
    """
    Check the maximum consecutive-period rule.

    Original period indexes are used, meaning a break resets adjacency.
    """

    if (
        max_consecutive_periods is None
    ):
        return True

    mapping = {
        "class": state[
            "class_day_periods"
        ],
        "teacher": state[
            "teacher_day_periods"
        ],
        "room": state[
            "room_day_periods"
        ],
    }

    day_periods = mapping[
        resource_type
    ][
        resource_id
    ]

    grouped: dict[
        str,
        set[int]
    ] = defaultdict(set)

    for day, indexes in day_periods.items():
        grouped[
            day
        ].update(
            indexes
        )

    for slot in candidate_slots:

        grouped[
            slot["day"]
        ].add(
            slot["_period_index"]
        )

    for indexes in grouped.values():

        if (
            _max_consecutive_for_day(
                indexes
            )
            > max_consecutive_periods
        ):
            return False

    return True


# =========================================================
# REQUIREMENT SPACING
# =========================================================


def _requirement_candidate_respects_spacing(
    state: dict,
    unit: dict,
    candidate: dict | tuple[dict, dict],
) -> bool:

    req_index = unit[
        "req_index"
    ]

    requirement = unit[
        "requirement"
    ]

    candidate_slots = _candidate_slots(
        candidate
    )

    candidate_days = _candidate_days(
        candidate
    )

    existing_days = state[
        "requirement_days"
    ][
        req_index
    ]

    # -----------------------------------------------------
    # Maximum lessons per day
    # -----------------------------------------------------

    max_lessons_per_day = (
        _max_lessons_per_day(
            requirement
        )
    )

    if max_lessons_per_day is not None:

        for day in candidate_days:

            # `max_lessons_per_day` is interpreted as actual
            # occupied lesson periods. A double lesson therefore
            # consumes two units of daily capacity.
            current = 0

            existing_periods = state[
                "requirement_day_periods"
            ][
                req_index
            ].get(
                day,
                set(),
            )

            current = len(
                existing_periods
            )

            candidate_periods = sum(
                1
                for slot in candidate_slots
                if slot["day"] == day
            )

            if (
                current + candidate_periods
                > max_lessons_per_day
            ):
                return False

    # -----------------------------------------------------
    # Minimum number of lesson periods between the same
    # requirement on the same day.
    # -----------------------------------------------------

    min_gap = _min_gap_periods(
        requirement
    )

    if min_gap > 0:

        existing = state[
            "requirement_day_periods"
        ][
            req_index
        ]

        for candidate_slot in candidate_slots:

            day = candidate_slot[
                "day"
            ]

            candidate_index = candidate_slot[
                "_period_index"
            ]

            for existing_index in existing.get(
                day,
                set(),
            ):

                if (
                    abs(
                        candidate_index
                        - existing_index
                    )
                    <= min_gap
                ):
                    return False

    # -----------------------------------------------------
    # Minimum days between occurrences.
    # -----------------------------------------------------

    min_days = _min_days_between(
        requirement
    )

    if min_days > 0:

        candidate_day_indexes = {
            candidate_slot[
                "day_index"
            ]
            for candidate_slot in candidate_slots
        }

        existing_day_indexes = {
            _day_index_from_state(
                state,
                req_index,
                day,
            )
            for day in existing_days
        }

        for candidate_day_index in candidate_day_indexes:

            for existing_day_index in existing_day_indexes:

                if (
                    abs(
                        candidate_day_index
                        - existing_day_index
                    )
                    <= min_days
                ):
                    return False

    return True


def _day_index_from_state(
    state: dict,
    req_index: int,
    day: str,
) -> int:
    """
    State keeps actual days but not a separate global day-index map.

    Placements are inspected through unit assignments.
    """

    for assignment in state[
        "unit_assignments"
    ].values():

        if (
            assignment[
                "req_index"
            ]
            != req_index
        ):
            continue

        for slot in assignment[
            "slots"
        ]:

            if slot[
                "day"
            ] == day:

                return int(
                    slot[
                        "day_index"
                    ]
                )

    return 0


# =========================================================
# CANDIDATE HARD-CONSTRAINT CHECK
# =========================================================


def _candidate_has_resource_conflict(
    state: dict,
    candidate_entries: list[dict],
) -> bool:

    for entry in candidate_entries:

        key = _slot_key(
            entry["day"],
            entry["period_id"],
        )

        class_id = _resource_key(
            entry["class_id"]
        )

        teacher_id = _resource_key(
            entry[
                "teacher_user_id"
            ]
        )

        room_id = entry.get(
            "room_id"
        )

        if (
            key
            in state[
                "used_class"
            ][
                class_id
            ]
        ):
            return True

        if (
            key
            in state[
                "used_teacher"
            ][
                teacher_id
            ]
        ):
            return True

        if room_id:

            room_key = _resource_key(
                room_id
            )

            if (
                key
                in state[
                    "used_room"
                ][
                    room_key
                ]
            ):
                return True

    return False


def _candidate_respects_daily_resource_limits(
    state: dict,
    candidate_entries: list[dict],
    rules: dict,
) -> bool:

    max_class = rules.get(
        "max_class_periods_per_day"
    )

    max_teacher = rules.get(
        "max_teacher_periods_per_day"
    )

    max_room = rules.get(
        "max_room_periods_per_day"
    )

    max_consecutive = rules.get(
        "max_consecutive_periods"
    )

    candidate_by_class = defaultdict(
        list
    )
    candidate_by_teacher = defaultdict(
        list
    )
    candidate_by_room = defaultdict(
        list
    )

    for entry in candidate_entries:

        candidate_by_class[
            _resource_key(
                entry["class_id"]
            )
        ].append(
            entry
        )

        candidate_by_teacher[
            _resource_key(
                entry["teacher_user_id"]
            )
        ].append(
            entry
        )

        room_id = entry.get(
            "room_id"
        )

        if room_id:

            candidate_by_room[
                _resource_key(
                    room_id
                )
            ].append(
                entry
            )

    # -----------------------------------------------------
    # Class daily load
    # -----------------------------------------------------

    if max_class is not None:

        for class_id, entries in candidate_by_class.items():

            grouped = defaultdict(
                list
            )

            for entry in entries:
                grouped[
                    entry["day"]
                ].append(
                    entry
                )

            for day, day_entries in grouped.items():

                projected = (
                    _resource_load(
                        state,
                        "class",
                        class_id,
                        day,
                    )
                    + len(day_entries)
                )

                if projected > max_class:
                    return False

    # -----------------------------------------------------
    # Teacher daily load
    # -----------------------------------------------------

    if max_teacher is not None:

        for teacher_id, entries in candidate_by_teacher.items():

            grouped = defaultdict(
                list
            )

            for entry in entries:
                grouped[
                    entry["day"]
                ].append(
                    entry
                )

            for day, day_entries in grouped.items():

                projected = (
                    _resource_load(
                        state,
                        "teacher",
                        teacher_id,
                        day,
                    )
                    + len(day_entries)
                )

                if projected > max_teacher:
                    return False

    # -----------------------------------------------------
    # Room daily load
    # -----------------------------------------------------

    if max_room is not None:

        for room_id, entries in candidate_by_room.items():

            grouped = defaultdict(
                list
            )

            for entry in entries:
                grouped[
                    entry["day"]
                ].append(
                    entry
                )

            for day, day_entries in grouped.items():

                projected = (
                    _resource_load(
                        state,
                        "room",
                        room_id,
                        day,
                    )
                    + len(day_entries)
                )

                if projected > max_room:
                    return False

    # -----------------------------------------------------
    # Maximum consecutive periods
    # -----------------------------------------------------

    if max_consecutive is not None:

        for class_id, entries in candidate_by_class.items():

            if not _resource_consecutive_after(
                state,
                "class",
                class_id,
                _entry_slots(entries),
                max_consecutive,
            ):
                return False

        for teacher_id, entries in candidate_by_teacher.items():

            if not _resource_consecutive_after(
                state,
                "teacher",
                teacher_id,
                _entry_slots(entries),
                max_consecutive,
            ):
                return False

        for room_id, entries in candidate_by_room.items():

            if not _resource_consecutive_after(
                state,
                "room",
                room_id,
                _entry_slots(entries),
                max_consecutive,
            ):
                return False

    return True


def _entry_slots(
    entries: list[dict],
) -> list[dict]:
    """
    Convert public entries back to lightweight slot objects needed
    for consecutive-load checks.

    The public entry retains only day/period_id, so this helper is
    intentionally only used where exact original indexes are already
    represented by the entries' stored period order later.
    """

    # The caller uses this helper only for max-consecutive validation.
    # We cannot reconstruct original indexes solely from a public entry.
    # Therefore this function is replaced at runtime by candidate-slot
    # handling in `_candidate_respects_daily_resource_limits`.

    return [
        {
            "day": entry["day"],
            "period_id": entry["period_id"],
            "_period_index": entry.get(
                "_period_index",
                0,
            ),
        }
        for entry in entries
    ]


# =========================================================
# RESOURCE CONSTRAINT CHECK USING RAW CANDIDATE SLOTS
# =========================================================


def _candidate_respects_rules(
    state: dict,
    unit: dict,
    candidate: dict | tuple[dict, dict],
    rules: dict,
) -> bool:

    requirement = unit[
        "requirement"
    ]

    candidate_slots = _candidate_slots(
        candidate
    )

    candidate_entries = [
        _make_entry(
            requirement,
            slot,
            unit["occurrence"],
        )
        for slot in candidate_slots
    ]

    # -----------------------------------------------------
    # Resource collisions
    # -----------------------------------------------------

    if _candidate_has_resource_conflict(
        state,
        candidate_entries,
    ):
        return False

    # -----------------------------------------------------
    # Resource daily limits using raw slot indexes.
    # -----------------------------------------------------

    resource_groups = {
        "class": (
            str(
                requirement[
                    "class_id"
                ]
            ),
            rules.get(
                "max_class_periods_per_day"
            ),
            state[
                "class_day_periods"
            ],
        ),
        "teacher": (
            str(
                requirement[
                    "teacher_user_id"
                ]
            ),
            rules.get(
                "max_teacher_periods_per_day"
            ),
            state[
                "teacher_day_periods"
            ],
        ),
    }

    room_id = requirement.get(
        "room_id"
    )

    if room_id:
        resource_groups[
            "room"
        ] = (
            str(room_id),
            rules.get(
                "max_room_periods_per_day"
            ),
            state[
                "room_day_periods"
            ],
        )

    for (
        resource_type,
        (
            resource_id,
            daily_limit,
            mapping,
        ),
    ) in resource_groups.items():

        if daily_limit is None:
            continue

        grouped = defaultdict(
            list
        )

        for slot in candidate_slots:

            grouped[
                slot["day"]
            ].append(
                slot
            )

        for day, day_slots in grouped.items():

            existing_count = len(
                mapping[
                    resource_id
                ][
                    day
                ]
            )

            projected = (
                existing_count
                + len(day_slots)
            )

            if projected > daily_limit:
                return False

    # -----------------------------------------------------
    # Consecutive-period limit.
    # -----------------------------------------------------

    max_consecutive = rules.get(
        "max_consecutive_periods"
    )

    if max_consecutive is not None:

        for (
            resource_type,
            (
                resource_id,
                _daily_limit,
                mapping,
            ),
        ) in resource_groups.items():

            existing_grouped = mapping[
                resource_id
            ]

            for day in {
                slot["day"]
                for slot in candidate_slots
            }:

                indexes = set(
                    existing_grouped.get(
                        day,
                        set(),
                    )
                )

                indexes.update(
                    slot[
                        "_period_index"
                    ]
                    for slot in candidate_slots
                    if slot["day"] == day
                )

                if (
                    _max_consecutive_for_day(
                        indexes
                    )
                    > max_consecutive
                ):
                    return False

    # -----------------------------------------------------
    # Requirement spacing rules.
    # -----------------------------------------------------

    if not _requirement_candidate_respects_spacing(
        state,
        unit,
        candidate,
    ):
        return False

    # -----------------------------------------------------
    # Avoid same requirement becoming consecutive if
    # explicitly requested.
    # -----------------------------------------------------

    if _avoid_consecutive(
        requirement
    ):

        existing = state[
            "requirement_day_periods"
        ][
            unit["req_index"]
        ]

        for slot in candidate_slots:

            day = slot[
                "day"
            ]

            index = slot[
                "_period_index"
            ]

            for existing_index in existing.get(
                day,
                set(),
            ):

                if abs(
                    index
                    - existing_index
                ) == 1:

                    return False

    return True


# =========================================================
# CANDIDATE FILTERING
# =========================================================


def _candidate_allowed_by_preference_filters(
    requirement: dict,
    candidate: dict | tuple[dict, dict],
) -> bool:

    blocked = _blocked_slots(
        requirement
    )

    avoid_days = _avoid_days(
        requirement
    )

    avoid_periods = _avoid_period_ids(
        requirement
    )

    for slot in _candidate_slots(
        candidate
    ):

        key = _slot_key(
            slot["day"],
            slot["period_id"],
        )

        if key in blocked:
            return False

        if slot["day"] in avoid_days:
            return False

        if (
            slot["period_id"]
            in avoid_periods
        ):
            return False

    return True


def _generate_candidate_list(
    state: dict,
    unit: dict,
    slots: list[dict],
    double_pairs: list[tuple[dict, dict]],
    rules: dict,
) -> list[dict | tuple[dict, dict]]:

    requirement = unit[
        "requirement"
    ]

    if unit["double"]:

        base_candidates = (
            double_pairs
        )

    else:

        base_candidates = slots

    candidates = []

    for candidate in base_candidates:

        if not _candidate_allowed_by_preference_filters(
            requirement,
            candidate,
        ):
            continue

        if not _candidate_respects_rules(
            state,
            unit,
            candidate,
            rules,
        ):
            continue

        candidates.append(
            candidate
        )

    return candidates


# =========================================================
# SOFT SCORING
# =========================================================


def _candidate_score(
    state: dict,
    unit: dict,
    candidate: dict | tuple[dict, dict],
    day_order: dict[str, int],
) -> tuple:

    requirement = unit[
        "requirement"
    ]

    slots = _candidate_slots(
        candidate
    )

    first = slots[
        0
    ]

    day = first[
        "day"
    ]

    preferred_days = _preferred_days(
        requirement
    )

    preferred_periods = _preferred_period_ids(
        requirement
    )

    spread = _spread_across_days(
        requirement
    )

    req_index = unit[
        "req_index"
    ]

    # -----------------------------------------------------
    # Preferred weekday
    # -----------------------------------------------------

    preferred_day_penalty = (
        0
        if (
            not preferred_days
            or day in preferred_days
        )
        else 100
    )

    # -----------------------------------------------------
    # Preferred period
    # -----------------------------------------------------

    if not preferred_periods:

        preferred_period_penalty = 0

    else:

        preferred_hits = sum(
            1
            for slot in slots
            if slot[
                "period_id"
            ]
            in preferred_periods
        )

        preferred_period_penalty = (
            len(slots)
            - preferred_hits
        ) * 15

    # -----------------------------------------------------
    # Spread same requirement across days.
    # -----------------------------------------------------

    existing_days = state[
        "requirement_days"
    ][
        req_index
    ]

    spread_penalty = 0

    if spread and day in existing_days:

        spread_penalty = 30

    # -----------------------------------------------------
    # Same requirement/day repetition.
    # -----------------------------------------------------

    same_day_count = state[
        "requirement_day_units"
    ][
        req_index
    ][
        day
    ]

    repeated_subject_penalty = (
        same_day_count * 12
    )

    # -----------------------------------------------------
    # Class/teacher/room load balancing.
    # -----------------------------------------------------

    class_id = _resource_key(
        requirement[
            "class_id"
        ]
    )

    teacher_id = _resource_key(
        requirement[
            "teacher_user_id"
        ]
    )

    room_id = requirement.get(
        "room_id"
    )

    class_load = _resource_load(
        state,
        "class",
        class_id,
        day,
    )

    teacher_load = _resource_load(
        state,
        "teacher",
        teacher_id,
        day,
    )

    room_load = 0

    if room_id:
        room_load = _resource_load(
            state,
            "room",
            _resource_key(room_id),
            day,
        )

    # -----------------------------------------------------
    # Avoid same-requirement adjacency as a soft penalty
    # when it is not explicitly a hard constraint.
    # -----------------------------------------------------

    adjacency_penalty = 0

    existing = state[
        "requirement_day_periods"
    ][
        req_index
    ]

    for slot in slots:

        for existing_index in existing.get(
            slot["day"],
            set(),
        ):

            if abs(
                slot["_period_index"]
                - existing_index
            ) == 1:

                adjacency_penalty += 20

    # -----------------------------------------------------
    # Stable deterministic ordering.
    # -----------------------------------------------------

    return (
        preferred_day_penalty,
        preferred_period_penalty,
        spread_penalty,
        repeated_subject_penalty,
        adjacency_penalty,

        # Load balancing.
        class_load * 3,
        teacher_load * 3,
        room_load * 2,

        # Higher-priority requirements already win at the
        # unit-selection stage, but retain deterministic
        # ordering here.
        -_priority(
            requirement
        ),

        day_order.get(
            day,
            999,
        ),

        int(
            first.get(
                "_period_index",
                0,
            )
        ),
    )


# =========================================================
# RESERVATION
# =========================================================


def _reserve(
    state: dict,
    unit: dict,
    candidate: dict | tuple[dict, dict],
) -> None:

    requirement = unit[
        "requirement"
    ]

    req_index = unit[
        "req_index"
    ]

    slots = _candidate_slots(
        candidate
    )

    entries = [
        _make_entry(
            requirement,
            slot,
            unit["occurrence"],
        )
        for slot in slots
    ]

    class_id = _resource_key(
        requirement[
            "class_id"
        ]
    )

    teacher_id = _resource_key(
        requirement[
            "teacher_user_id"
        ]
    )

    room_id = requirement.get(
        "room_id"
    )

    # -----------------------------------------------------
    # Public entries
    # -----------------------------------------------------

    state[
        "entries"
    ].extend(
        entries
    )

    # -----------------------------------------------------
    # Resources
    # -----------------------------------------------------

    for slot in slots:

        key = _slot_key(
            slot["day"],
            slot["period_id"],
        )

        state[
            "used_class"
        ][
            class_id
        ].add(
            key
        )

        state[
            "used_teacher"
        ][
            teacher_id
        ].add(
            key
        )

        state[
            "class_day_periods"
        ][
            class_id
        ][
            slot["day"]
        ].add(
            slot["_period_index"]
        )

        state[
            "teacher_day_periods"
        ][
            teacher_id
        ][
            slot["day"]
        ].add(
            slot["_period_index"]
        )

        if room_id:

            room_key = _resource_key(
                room_id
            )

            state[
                "used_room"
            ][
                room_key
            ].add(
                key
            )

            state[
                "room_day_periods"
            ][
                room_key
            ][
                slot["day"]
            ].add(
                slot["_period_index"]
            )

        state[
            "requirement_day_periods"
        ][
            req_index
        ][
            slot["day"]
        ].add(
            slot["_period_index"]
        )

        state[
            "requirement_days"
        ][
            req_index
        ].add(
            slot["day"]
        )

    # One double block = one lesson occurrence.
    first_day = slots[
        0
    ][
        "day"
    ]

    state[
        "requirement_day_units"
    ][
        req_index
    ][
        first_day
    ] += 1

    state[
        "requirement_subject_day"
    ][
        req_index
    ][
        first_day
    ] += 1

    state[
        "unit_assignments"
    ][
        id(unit)
    ] = {
        "req_index": req_index,
        "unit": unit,
        "slots": slots,
        "entries": entries,
    }


def _release(
    state: dict,
    unit: dict,
) -> None:

    assignment = state[
        "unit_assignments"
    ].pop(
        id(unit)
    )

    requirement = unit[
        "requirement"
    ]

    req_index = unit[
        "req_index"
    ]

    slots = assignment[
        "slots"
    ]

    entries = assignment[
        "entries"
    ]

    class_id = _resource_key(
        requirement[
            "class_id"
        ]
    )

    teacher_id = _resource_key(
        requirement[
            "teacher_user_id"
        ]
    )

    room_id = requirement.get(
        "room_id"
    )

    for entry, slot in zip(
        entries,
        slots,
    ):

        key = _slot_key(
            entry["day"],
            entry["period_id"],
        )

        state[
            "used_class"
        ][
            class_id
        ].discard(
            key
        )

        state[
            "used_teacher"
        ][
            teacher_id
        ].discard(
            key
        )

        state[
            "class_day_periods"
        ][
            class_id
        ][
            slot["day"]
        ].discard(
            slot["_period_index"]
        )

        state[
            "teacher_day_periods"
        ][
            teacher_id
        ][
            slot["day"]
        ].discard(
            slot["_period_index"]
        )

        if room_id:

            room_key = _resource_key(
                room_id
            )

            state[
                "used_room"
            ][
                room_key
            ].discard(
                key
            )

            state[
                "room_day_periods"
            ][
                room_key
            ][
                slot["day"]
            ].discard(
                slot["_period_index"]
            )

        state[
            "requirement_day_periods"
        ][
            req_index
        ][
            slot["day"]
        ].discard(
            slot["_period_index"]
        )

    first_day = slots[
        0
    ][
        "day"
    ]

    state[
        "requirement_day_units"
    ][
        req_index
    ][
        first_day
    ] -= 1

    if (
        state[
            "requirement_day_units"
        ][
            req_index
        ][
            first_day
        ]
        <= 0
    ):

        del state[
            "requirement_day_units"
        ][
            req_index
        ][
            first_day
        ]

    state[
        "requirement_subject_day"
    ][
        req_index
    ][
        first_day
    ] -= 1


# =========================================================
# RESOURCE CAPACITY PRE-CHECK
# =========================================================


def _validate_basic_capacity(
    slots: list[dict],
    requirements: list[dict],
    double_pairs: list[tuple[dict, dict]],
) -> None:
    """
    Reject obviously impossible requirements before search begins.
    """

    slot_count = len(
        slots
    )

    pair_count = len(
        double_pairs
    )

    for requirement in requirements:

        periods_per_week = _periods_per_week(
            requirement
        )

        if periods_per_week <= 0:
            continue

        allowed_slot_count = 0

        for slot in slots:

            if _candidate_allowed_by_preference_filters(
                requirement,
                slot,
            ):
                allowed_slot_count += 1

        if (
            allowed_slot_count
            < periods_per_week
        ):

            raise GenerationError(
                f"Requirement '{requirement.get('subject')}' "
                f"does not have enough available lesson slots "
                f"for {periods_per_week} weekly periods."
            )

        double_count = _double_lessons_per_week(
            requirement
        )

        if double_count <= 0:
            continue

        if pair_count == 0:
            raise GenerationError(
                f"Requirement '{requirement.get('subject')}' "
                "requests double lessons, but no valid adjacent "
                "lesson-period pair exists."
            )

        # A pair must satisfy THIS requirement's hard preference
        # filters. A valid pair somewhere else in the timetable is
        # not enough.
        allowed_pairs = 0

        for first, second in double_pairs:
            pair = (
                first,
                second,
            )

            if _candidate_allowed_by_preference_filters(
                requirement,
                pair,
            ):
                allowed_pairs += 1

        if allowed_pairs < double_count:
            raise GenerationError(
                f"Requirement '{requirement.get('subject')}' "
                f"requests {double_count} double lesson block(s), "
                f"but only {allowed_pairs} compatible adjacent "
                "block(s) remain after its restrictions."
            )


# =========================================================
# UNIT ORDERING / MRV
# =========================================================


def _unit_static_key(
    unit: dict,
) -> tuple:

    requirement = unit[
        "requirement"
    ]

    return (
        -_priority(
            requirement
        ),
        -_periods_per_week(
            requirement
        ),
        0
        if unit["double"]
        else 1,
        str(
            requirement.get(
                "class_id",
                "",
            )
        ),
        str(
            requirement.get(
                "teacher_user_id",
                "",
            )
        ),
        str(
            requirement.get(
                "subject",
                "",
            )
        ),
        unit[
            "occurrence"
        ],
    )


def _select_next_unit(
    state: dict,
    units: list[dict],
    slots: list[dict],
    double_pairs: list[tuple[dict, dict]],
    rules: dict,
) -> tuple[
    dict | None,
    list[dict | tuple[dict, dict]],
]:

    best_unit = None
    best_candidates = None
    best_key = None

    for unit in units:

        if id(unit) in state[
            "unit_assignments"
        ]:
            continue

        candidates = _generate_candidate_list(
            state,
            unit,
            slots,
            double_pairs,
            rules,
        )

        candidate_count = len(
            candidates
        )

        # -------------------------------------------------
        # Immediate dead-end.
        # -------------------------------------------------

        if candidate_count == 0:
            return (
                unit,
                [],
            )

        requirement = unit[
            "requirement"
        ]

        key = (
            candidate_count,

            # Highest priority first.
            -_priority(
                requirement
            ),

            # Doubles first because they are more constrained.
            0
            if unit["double"]
            else 1,

            -_periods_per_week(
                requirement
            ),

            str(
                requirement.get(
                    "class_id",
                    "",
                )
            ),

            str(
                requirement.get(
                    "subject",
                    "",
                )
            ),

            unit[
                "occurrence"
            ],
        )

        if (
            best_key is None
            or key < best_key
        ):

            best_key = key

            best_unit = unit

            best_candidates = candidates

    if best_unit is None:
        return (
            None,
            [],
        )

    return (
        best_unit,
        best_candidates or [],
    )


# =========================================================
# SCORE HELPERS
# =========================================================


def _total_soft_score(
    state: dict,
    day_order: dict[str, int],
) -> int:

    score = 0

    # The actual candidate score is deterministic and does not need
    # to be reconstructed from final entries. This function returns a
    # simple quality summary for API consumers.

    for entry in state[
        "entries"
    ]:

        # Stable base reward for successful placement.
        score += 100

        # Earlier periods have a tiny preference.
        score -= int(
            entry.get(
                "occurrence",
                0,
            )
        )

        score -= day_order.get(
            entry["day"],
            0,
        )

    return max(
        score,
        0,
    )


# =========================================================
# MAIN GENERATOR
# =========================================================


def generate(
    weekdays: list[str],
    periods: list[dict],
    requirements: list[dict],
    max_nodes: int = DEFAULT_MAX_NODES,
    rules: dict | None = None,
) -> dict:
    """
    Generate a deterministic school timetable.

    Backwards compatibility:
        The original call still works:

            generate(
                weekdays,
                periods,
                requirements,
            )

    Advanced callers can additionally provide:

        rules={
            "max_class_periods_per_day": 8,
            "max_teacher_periods_per_day": 7,
            "max_room_periods_per_day": 8,
            "max_consecutive_periods": 4,
        }
    """

    if max_nodes <= 0:
        raise GenerationError(
            "max_nodes must be greater than zero."
        )

    if not isinstance(
        requirements,
        list,
    ):
        raise GenerationError(
            "requirements must be a list."
        )

    rules = dict(
        rules or {}
    )

    # -----------------------------------------------------
    # Normalize optional global rules.
    # -----------------------------------------------------

    for field in (
        "max_class_periods_per_day",
        "max_teacher_periods_per_day",
        "max_room_periods_per_day",
        "max_consecutive_periods",
    ):

        if field not in rules:
            continue

        value = rules[
            field
        ]

        if value is None:
            continue

        value = _safe_int(
            value,
            -1,
        )

        if value < 0:

            raise GenerationError(
                f"{field} must be greater than or equal to zero."
            )

        rules[
            field
        ] = value

    # -----------------------------------------------------
    # Normalize / validate requirements.
    # -----------------------------------------------------

    normalized_requirements = []

    for requirement in requirements:

        if not isinstance(
            requirement,
            dict,
        ):
            raise GenerationError(
                "Each timetable requirement must be an object."
            )

        # Never mutate caller-owned objects.
        normalized = _canonicalize_requirement(
            requirement
        )

        _validate_requirement(
            normalized
        )

        normalized_requirements.append(
            normalized
        )

    # -----------------------------------------------------
    # Build slots.
    # -----------------------------------------------------

    slots = build_slots(
        weekdays,
        periods,
    )

    double_pairs = _double_slots(
        slots
    )

    # -----------------------------------------------------
    # Remove zero-period requirements.
    # -----------------------------------------------------

    active_requirements = [
        requirement
        for requirement in normalized_requirements
        if _periods_per_week(
            requirement
        ) > 0
    ]

    if not active_requirements:

        return {
            "generation_version": GENERATOR_VERSION,
            "entries": [],
            "nodes_explored": 0,
            "quality_score": 0,
            "scheduled_periods": 0,
            "requirements_count": 0,
        }

    # -----------------------------------------------------
    # Basic capacity validation.
    # -----------------------------------------------------

    _validate_basic_capacity(
        slots,
        active_requirements,
        double_pairs,
    )

    # -----------------------------------------------------
    # Expand weekly requirements.
    # -----------------------------------------------------

    units = _expand_requirements(
        active_requirements
    )

    if not units:

        return {
            "generation_version": GENERATOR_VERSION,
            "entries": [],
            "nodes_explored": 0,
            "quality_score": 0,
            "scheduled_periods": 0,
            "requirements_count": 0,
        }

    # -----------------------------------------------------
    # Deterministic day ordering.
    # -----------------------------------------------------

    normalized_weekdays = [
        _normalize_day(
            day
        )
        for day in weekdays
        if _normalize_day(
            day
        )
    ]

    day_order = {
        day: index
        for index, day in enumerate(
            normalized_weekdays
        )
    }

    # -----------------------------------------------------
    # State.
    # -----------------------------------------------------

    state = _new_state()

    nodes = 0

    dead_end_unit = None

    # =====================================================
    # BACKTRACKING SEARCH
    # =====================================================

    def backtrack(
        assigned_count: int,
    ) -> bool:

        nonlocal nodes
        nonlocal dead_end_unit

        nodes += 1

        if nodes > max_nodes:
            return False

        # -------------------------------------------------
        # Completed.
        # -------------------------------------------------

        if assigned_count >= len(
            units
        ):

            return True

        # -------------------------------------------------
        # MRV:
        # choose the unassigned unit with the fewest
        # currently legal placements.
        # -------------------------------------------------

        unit, candidates = _select_next_unit(
            state,
            units,
            slots,
            double_pairs,
            rules,
        )

        if unit is None:
            return True

        if not candidates:

            dead_end_unit = unit

            return False

        # -------------------------------------------------
        # Deterministic soft-score ordering.
        # -------------------------------------------------

        candidates.sort(
            key=lambda candidate:
                _candidate_score(
                    state,
                    unit,
                    candidate,
                    day_order,
                )
        )

        # -------------------------------------------------
        # Explore candidates.
        # -------------------------------------------------

        for candidate in candidates:

            _reserve(
                state,
                unit,
                candidate,
            )

            if backtrack(
                assigned_count + 1
            ):
                return True

            _release(
                state,
                unit,
            )

        return False

    # -----------------------------------------------------
    # Execute.
    # -----------------------------------------------------

    success = backtrack(
        0
    )

    if not success:

        if nodes > max_nodes:

            raise GenerationError(
                "Timetable generation exceeded the maximum "
                f"search limit of {max_nodes} nodes. "
                "The supplied constraints may be too restrictive."
            )

        if dead_end_unit is not None:

            requirement = dead_end_unit[
                "requirement"
            ]

            subject = str(
                requirement.get(
                    "subject",
                    "Unknown subject",
                )
            )

            class_id = str(
                requirement.get(
                    "class_id",
                    "Unknown class",
                )
            )

            raise GenerationError(
                "No conflict-free timetable could be generated. "
                f"The scheduling engine became blocked while placing "
                f"'{subject}' for class '{class_id}'. "
                "Review blocked slots, avoid days/periods, weekly "
                "lesson counts, double-lesson requirements, spacing, "
                "and daily resource limits."
            )

        raise GenerationError(
            "No conflict-free timetable could be generated."
        )

    # =====================================================
    # FINAL DETERMINISTIC ORDER
    # =====================================================

    period_order = {}

    for index, period in enumerate(
        periods
    ):

        period_id = _normalize_period_id(
            period.get(
                "id"
            )
        )

        if period_id:

            period_order[
                period_id
            ] = index

    state[
        "entries"
    ].sort(
        key=lambda entry: (
            day_order.get(
                entry["day"],
                999,
            ),

            period_order.get(
                entry["period_id"],
                999,
            ),

            str(
                entry["class_id"]
            ),

            str(
                entry["teacher_user_id"]
            ),

            str(
                entry["subject"]
            ),

            int(
                entry.get(
                    "occurrence",
                    0,
                )
            ),
        )
    )

    # =====================================================
    # VALIDATE GENERATED COUNT
    # =====================================================

    expected_periods = sum(
        _periods_per_week(
            requirement
        )
        for requirement in active_requirements
    )

    actual_periods = len(
        state[
            "entries"
        ]
    )

    if actual_periods != expected_periods:

        raise GenerationError(
            "Internal generation error: scheduled period count "
            f"({actual_periods}) does not match the required "
            f"period count ({expected_periods})."
        )

    # =====================================================
    # RESULT
    # =====================================================

    return {
        "generation_version": GENERATOR_VERSION,

        "entries": state[
            "entries"
        ],

        "nodes_explored": nodes,

        "quality_score": _total_soft_score(
            state,
            day_order,
        ),

        "scheduled_periods": actual_periods,

        "requirements_count": len(
            active_requirements
        ),

        "double_blocks": sum(
            1
            for unit in units
            if unit["double"]
        ),

        "constraints": {
            "hard": [
                "class_conflict",
                "teacher_conflict",
                "room_conflict",
                "blocked_slots",
                "avoid_days",
                "avoid_period_ids",
                "lesson_periods_only",
                "true_adjacent_double_lessons",
                "max_lessons_per_day",
                "min_gap_periods",
                "min_days_between",
                "daily_resource_limits",
                "max_consecutive_periods",
            ],
            "soft": [
                "preferred_days",
                "preferred_period_ids",
                "priority_ordering",
                "day_distribution",
                "resource_load_balancing",
                "same_subject_day_repetition",
                "unnecessary_consecutive_lessons",
            ],
        },

        "algorithm": {
            "strategy": "constraint_backtracking_mrv",
            "deterministic": True,
            "database_independent": True,
            "validator_authoritative": True,
        },
    }


# =========================================================
# WORKLOAD SUMMARY
# =========================================================


def workload_summary(
    entries: list[dict],
) -> dict:
    """
    Return teacher/class workload information.

    Useful for dashboards, diagnostics, and later AI optimization.
    """

    teachers = Counter()
    classes = Counter()
    rooms = Counter()

    teacher_daily = defaultdict(
        Counter
    )
    class_daily = defaultdict(
        Counter
    )
    room_daily = defaultdict(
        Counter
    )

    for entry in entries:

        teacher_id = str(
            entry.get(
                "teacher_user_id",
                "",
            )
        )

        class_id = str(
            entry.get(
                "class_id",
                "",
            )
        )

        room_id = entry.get(
            "room_id"
        )

        day = _normalize_day(
            entry.get(
                "day",
                "",
            )
        )

        teachers[
            teacher_id
        ] += 1

        classes[
            class_id
        ] += 1

        teacher_daily[
            teacher_id
        ][
            day
        ] += 1

        class_daily[
            class_id
        ][
            day
        ] += 1

        if room_id:

            room_key = str(
                room_id
            )

            rooms[
                room_key
            ] += 1

            room_daily[
                room_key
            ][
                day
            ] += 1

    return {
        "teachers": dict(
            teachers
        ),
        "classes": dict(
            classes
        ),
        "rooms": dict(
            rooms
        ),
        "teacher_daily": {
            teacher: dict(
                days
            )
            for teacher, days
            in teacher_daily.items()
        },
        "class_daily": {
            class_id: dict(
                days
            )
            for class_id, days
            in class_daily.items()
        },
        "room_daily": {
            room: dict(
                days
            )
            for room, days
            in room_daily.items()
        },
    }