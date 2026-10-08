"""
School-aware timetable optimizer for Elimu.

Responsibilities
----------------
This module does NOT generate the initial timetable.

It improves an existing timetable by:
    1. validating the current schedule,
    2. building a structured school context for RevelaAI,
    3. validating any AI proposal with the server-side validator,
    4. preserving the exact lesson composition,
    5. reconciling only movable timetable fields from the AI proposal,
    6. scoring the proposal against school preferences,
    7. accepting only a strictly better valid schedule.

Authority
---------
RevelaAI is advisory. The server-side validator remains authoritative.
This module never writes to MongoDB; the service layer persists accepted
results after its own authorization/business-rule checks.

Accepted context shapes
-----------------------
The ``constraints`` argument may be either:

    {
        "requirements": [...],
        "weekdays": [...],
        "periods": [...],
        "constraints": {...},
    }

or the timetable's school-wide constraint dictionary directly.

For compatibility, canonical Elimu fields and generator compatibility fields
are both accepted where practical.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .validator import validate


# =========================================================
# TYPES
# =========================================================

Entry = Dict[str, Any]
Requirements = Sequence[Dict[str, Any]]
AICallable = Callable[[Dict[str, Any]], Any]


# =========================================================
# CONSTANTS
# =========================================================

HARD_PENALTY = 100000
VERY_HIGH_PENALTY = 10000
HIGH_PENALTY = 1000
OPTIMIZER_VERSION = "4.0"

DEFAULT_DAY_ORDER = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

IMMUTABLE_ENTRY_FIELDS = (
    "school_id",
    "timetable_id",
    "class_id",
    "teacher_user_id",
    "subject",
)

MOVABLE_ENTRY_FIELDS = (
    "day",
    "period_id",
    "room_id",
)

PERIOD_ID_KEYS = ("period_id", "id")


# =========================================================
# BASIC HELPERS
# =========================================================


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on", "y"}:
        return True
    if normalized in {"false", "0", "no", "off", "n"}:
        return False
    return default


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalise_day(value: Any) -> str:
    return _text(value).lower()


def _normalise_period_id(value: Any) -> str:
    return _text(value)


def _normalise_subject(value: Any) -> str:
    return _text(value).lower()


def _clone_entries(entries: Iterable[Entry]) -> List[Entry]:
    return [deepcopy(entry) for entry in entries if isinstance(entry, dict)]


def _canonical_day_value(value: Any) -> str:
    return _normalise_day(value)


# =========================================================
# CONTEXT NORMALIZATION
# =========================================================


def _normalise_constraints(constraints: Any) -> Dict[str, Any]:
    """Normalize the optimizer context without destroying school metadata."""
    if isinstance(constraints, dict):
        return deepcopy(constraints)

    if isinstance(constraints, (list, tuple)):
        return {"requirements": deepcopy(list(constraints))}

    return {}


def _context(
    constraints: Any,
    *,
    requirements: Optional[Requirements] = None,
    weekdays: Optional[Sequence[Any]] = None,
    periods: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build one canonical in-memory context for scoring and validation."""
    normalized = _normalise_constraints(constraints)

    # A full timetable context can keep school-wide settings nested under
    # ``constraints``. Preserve them while also exposing top-level fields.
    nested = normalized.get("constraints")
    if isinstance(nested, dict):
        school = deepcopy(nested)
    else:
        school = {
            key: deepcopy(value)
            for key, value in normalized.items()
            if key not in {"requirements", "weekdays", "periods", "metadata"}
        }

    if requirements is not None:
        normalized["requirements"] = _clone_entries(requirements)
    elif not isinstance(normalized.get("requirements"), (list, tuple)):
        normalized["requirements"] = []

    if weekdays is not None:
        normalized["weekdays"] = deepcopy(list(weekdays))
    elif not isinstance(normalized.get("weekdays"), (list, tuple)):
        normalized["weekdays"] = []

    if periods is not None:
        normalized["periods"] = deepcopy(list(periods))
    elif not isinstance(normalized.get("periods"), (list, tuple)):
        normalized["periods"] = []

    normalized["constraints"] = school
    return normalized


def _requirements_from_context(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    requirements = context.get("requirements")
    if not isinstance(requirements, (list, tuple)):
        requirements = context.get("constraints", {}).get("requirements", [])

    if not isinstance(requirements, (list, tuple)):
        return []

    return [item for item in requirements if isinstance(item, dict)]


def _school_constraints(context: Dict[str, Any]) -> Dict[str, Any]:
    nested = context.get("constraints")
    if isinstance(nested, dict):
        return nested

    return {
        key: value
        for key, value in context.items()
        if key not in {"requirements", "weekdays", "periods", "metadata"}
    }


# =========================================================
# PERIOD CATALOGUE
# =========================================================


def _period_definitions(context: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for period in context.get("periods", []) or []:
        if not isinstance(period, dict):
            continue
        period_id = next(
            (_normalise_period_id(period.get(key)) for key in PERIOD_ID_KEYS if period.get(key) is not None),
            "",
        )
        if period_id:
            result[period_id] = deepcopy(period)
    return result


def _period_map(context: Dict[str, Any]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for index, period in enumerate(context.get("periods", []) or []):
        if not isinstance(period, dict):
            continue
        period_id = next(
            (_normalise_period_id(period.get(key)) for key in PERIOD_ID_KEYS if period.get(key) is not None),
            "",
        )
        if period_id and period_id not in mapping:
            mapping[period_id] = index
    return mapping


def _lesson_period_map(context: Dict[str, Any]) -> Dict[str, int]:
    """Return period indexes using lesson periods only when the type is known."""
    mapping: Dict[str, int] = {}
    lesson_index = 0

    for period in context.get("periods", []) or []:
        if not isinstance(period, dict):
            continue

        period_id = next(
            (_normalise_period_id(period.get(key)) for key in PERIOD_ID_KEYS if period.get(key) is not None),
            "",
        )
        kind = _text(period.get("type") or period.get("kind")).lower()

        # Unknown period types are retained for backwards compatibility.
        if kind and kind not in {"lesson", "teaching", "class"}:
            continue

        if period_id and period_id not in mapping:
            mapping[period_id] = lesson_index
            lesson_index += 1

    return mapping


def _period_index(entry: Entry, context: Dict[str, Any]) -> int:
    period_id = _normalise_period_id(entry.get("period_id"))
    mapping = _period_map(context)
    if period_id in mapping:
        return mapping[period_id]

    digits = "".join(char for char in period_id if char.isdigit())
    if digits:
        return _safe_int(digits, 10**6)

    return 10**6


def _day_index(value: Any, context: Dict[str, Any]) -> int:
    day = _normalise_day(value)
    configured = [
        _normalise_day(item.get("name") if isinstance(item, dict) else item)
        for item in (context.get("weekdays") or [])
    ]
    configured = [item for item in configured if item]

    if day in configured:
        return configured.index(day)
    return DEFAULT_DAY_ORDER.get(day, 10**6)


def _entry_sort_key(entry: Entry, context: Dict[str, Any]) -> Tuple[int, int, str, str, str]:
    return (
        _day_index(entry.get("day"), context),
        _period_index(entry, context),
        _text(entry.get("class_id")),
        _text(entry.get("teacher_user_id")),
        _normalise_subject(entry.get("subject")),
    )


# =========================================================
# ENTRY IDENTITIES
# =========================================================


def _entry_key(entry: Entry) -> Tuple[str, str, str, str, str, str]:
    return (
        _normalise_day(entry.get("day")),
        _normalise_period_id(entry.get("period_id")),
        _text(entry.get("class_id")),
        _text(entry.get("teacher_user_id")),
        _normalise_subject(entry.get("subject")),
        _text(entry.get("room_id")),
    )


def _lesson_identity(entry: Entry) -> Tuple[str, str, str]:
    return (
        _text(entry.get("class_id")),
        _text(entry.get("teacher_user_id")),
        _normalise_subject(entry.get("subject")),
    )


def _lesson_identity_counts(entries: Sequence[Entry]) -> Counter:
    return Counter(_lesson_identity(entry) for entry in entries)


def _same_required_lesson_counts(
    current_entries: Sequence[Entry],
    candidate_entries: Sequence[Entry],
) -> bool:
    return _lesson_identity_counts(current_entries) == _lesson_identity_counts(candidate_entries)


def _proposal_duplicates(entries: Sequence[Entry]) -> bool:
    keys = [_entry_key(entry) for entry in entries]
    return len(keys) != len(set(keys))


def _same_entry_identity(
    current_entries: Sequence[Entry],
    candidate_entries: Sequence[Entry],
) -> bool:
    """Compatibility helper retained for callers using the older API."""
    if len(candidate_entries) != len(current_entries):
        return False
    if _proposal_duplicates(candidate_entries):
        return False
    return _same_required_lesson_counts(current_entries, candidate_entries)


def _composition_signature(entries: Sequence[Entry]) -> Counter:
    """Return the logical lesson composition used for proposal comparison."""
    return _lesson_identity_counts(entries)


def _optional_server_identity_matches(
    current_entries: Sequence[Entry],
    candidate_entries: Sequence[Entry],
) -> bool:
    """Allow AI to omit server metadata, but reject incorrect supplied metadata."""
    current_school_ids = {
        _text(entry.get("school_id"))
        for entry in current_entries
        if entry.get("school_id") is not None
    }
    current_timetable_ids = {
        _text(entry.get("timetable_id"))
        for entry in current_entries
        if entry.get("timetable_id") is not None
    }

    for entry in candidate_entries:
        school_id = _text(entry.get("school_id"))
        timetable_id = _text(entry.get("timetable_id"))
        if school_id and current_school_ids and school_id not in current_school_ids:
            return False
        if timetable_id and current_timetable_ids and timetable_id not in current_timetable_ids:
            return False

    return True


# =========================================================
# RECONCILIATION / TRUST BOUNDARY
# =========================================================


def _merge_period_metadata(entry: Entry, context: Dict[str, Any]) -> Entry:
    """Derive timing/type from the authoritative period catalogue."""
    result = deepcopy(entry)
    period_id = _normalise_period_id(result.get("period_id"))
    period = _period_definitions(context).get(period_id)

    if not period:
        return result

    for source_key, target_key in (
        ("start_time", "start_time"),
        ("end_time", "end_time"),
        ("duration_minutes", "duration_minutes"),
    ):
        if source_key in period:
            result[target_key] = period[source_key]

    period_type = period.get("type") or period.get("kind")
    if period_type is not None:
        result["period_type"] = period_type

    return result


def _reconcile_ai_entries(
    current_entries: Sequence[Entry],
    candidate_entries: Sequence[Entry],
    context: Dict[str, Any],
) -> Tuple[bool, List[Entry], Dict[str, Any]]:
    """
    Reconcile an AI proposal against the server-owned lesson identities.

    The AI may move a lesson's day, period and room, but it cannot rewrite
    school/timetable identity, class, teacher or subject. Timing/type are
    re-derived from the authoritative period catalogue.
    """
    if len(current_entries) != len(candidate_entries):
        return False, [], {"reason": "Lesson entry count changed."}

    if _composition_signature(current_entries) != _composition_signature(candidate_entries):
        return False, [], {"reason": "Class, teacher, or subject composition changed."}

    if not _optional_server_identity_matches(current_entries, candidate_entries):
        return False, [], {"reason": "AI supplied incorrect school or timetable identity."}

    grouped_current: Dict[Tuple[str, str, str], List[Entry]] = defaultdict(list)
    grouped_candidate: Dict[Tuple[str, str, str], List[Entry]] = defaultdict(list)

    for entry in current_entries:
        grouped_current[_lesson_identity(entry)].append(entry)
    for entry in candidate_entries:
        grouped_candidate[_lesson_identity(entry)].append(entry)

    reconciled: List[Entry] = []

    for identity, current_group in grouped_current.items():
        proposed_group = grouped_candidate.get(identity)
        if proposed_group is None or len(proposed_group) != len(current_group):
            return False, [], {"reason": f"Lesson group changed for {identity}."}

        current_group = sorted(current_group, key=lambda item: _entry_sort_key(item, context))
        proposed_group = sorted(proposed_group, key=lambda item: _entry_sort_key(item, context))

        for original, proposal in zip(current_group, proposed_group):
            merged = deepcopy(original)

            day = _canonical_day_value(proposal.get("day"))
            period_id = _normalise_period_id(
                proposal.get("period_id") or proposal.get("id")
            )

            if not day or not period_id:
                return False, [], {"reason": "AI proposal contains a lesson without day or period_id."}

            merged["day"] = day
            merged["period_id"] = period_id

            # Room is intentionally movable. An omitted room means preserve the
            # current assignment rather than silently clearing it.
            if "room_id" in proposal:
                merged["room_id"] = proposal.get("room_id")

            merged = _merge_period_metadata(merged, context)
            merged["generated_by"] = "revelaai_optimizer"
            reconciled.append(merged)

    reconciled.sort(key=lambda item: _entry_sort_key(item, context))
    return True, reconciled, {"reason": "AI proposal reconciled against server-owned identities."}


# =========================================================
# SLOT / LOAD METRICS
# =========================================================


def _owner_slots(
    entries: Sequence[Entry],
    owner_field: str,
    context: Dict[str, Any],
) -> Dict[str, Dict[str, List[int]]]:
    result: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))

    for entry in entries:
        owner = entry.get(owner_field)
        day = _normalise_day(entry.get("day"))
        if owner is None or not day:
            continue
        result[str(owner)][day].append(_period_index(entry, context))

    for owner_days in result.values():
        for periods in owner_days.values():
            periods.sort()

    return result


def _calculate_real_gaps(
    entries: Sequence[Entry],
    owner_field: str,
    context: Dict[str, Any],
) -> int:
    """Count empty lesson positions inside an owner's daily teaching span."""
    owners = _owner_slots(entries, owner_field, context)
    lesson_map = _lesson_period_map(context)

    gaps = 0
    for day_map in owners.values():
        for indexes in day_map.values():
            if len(indexes) < 2:
                continue

            if lesson_map:
                # Convert full period indexes into lesson-only indexes so breaks
                # do not count as teacher/class gaps.
                full_map = _period_map(context)
                lesson_indexes = []
                for full_index in indexes:
                    period_ids = [pid for pid, idx in full_map.items() if idx == full_index]
                    if period_ids and period_ids[0] in lesson_map:
                        lesson_indexes.append(lesson_map[period_ids[0]])
                indexes = sorted(lesson_indexes)

            if len(indexes) < 2:
                continue

            first = min(indexes)
            last = max(indexes)
            occupied = set(indexes)
            gaps += len(set(range(first, last + 1)) - occupied)

    return gaps


def _daily_load_counter(entries: Sequence[Entry], owner_field: str) -> Counter:
    return Counter(
        (
            _text(entry.get(owner_field)),
            _normalise_day(entry.get("day")),
        )
        for entry in entries
        if entry.get(owner_field) is not None
    )


def _daily_load_penalty(entries: Sequence[Entry], owner_field: str) -> int:
    counter = _daily_load_counter(entries, owner_field)
    return sum(value * value for value in counter.values())


def _maximum_daily_load(entries: Sequence[Entry], owner_field: str) -> int:
    counter = _daily_load_counter(entries, owner_field)
    return max(counter.values()) if counter else 0


def _daily_limit_penalty(
    entries: Sequence[Entry],
    owner_field: str,
    maximum: Any,
) -> int:
    limit = _safe_int(maximum, 0)
    if limit <= 0:
        return 0

    penalty = 0
    for count in _daily_load_counter(entries, owner_field).values():
        if count > limit:
            penalty += (count - limit) * VERY_HIGH_PENALTY
    return penalty


def _teacher_class_collisions(entries: Sequence[Entry]) -> int:
    counters: List[Counter] = []

    for field in ("teacher_user_id", "class_id"):
        counters.append(
            Counter(
                (
                    _text(entry.get(field)),
                    _normalise_day(entry.get("day")),
                    _normalise_period_id(entry.get("period_id")),
                )
                for entry in entries
                if entry.get(field) is not None
            )
        )

    counters.append(
        Counter(
            (
                _text(entry.get("room_id")),
                _normalise_day(entry.get("day")),
                _normalise_period_id(entry.get("period_id")),
            )
            for entry in entries
            if entry.get("room_id")
        )
    )

    return sum(
        max(0, count - 1)
        for counter in counters
        for count in counter.values()
    )


# =========================================================
# REQUIREMENT LOOKUP
# =========================================================


def _requirement_lookup(requirements: Requirements) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    result: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for requirement in requirements:
        key = (
            _text(requirement.get("class_id")),
            _text(requirement.get("teacher_user_id")),
            _normalise_subject(requirement.get("subject")),
        )
        result[key] = requirement
    return result


def _entry_requirement(
    entry: Entry,
    lookup: Dict[Tuple[str, str, str], Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    return lookup.get(_lesson_identity(entry))


# =========================================================
# PREFERENCE PENALTIES
# =========================================================


def _preferred_day_penalty(entries: Sequence[Entry], requirements: Requirements) -> int:
    lookup = _requirement_lookup(requirements)
    penalty = 0

    for entry in entries:
        requirement = _entry_requirement(entry, lookup)
        if not requirement:
            continue

        preferred_days = {
            _normalise_day(value)
            for value in requirement.get("preferred_days", []) or []
        }
        if preferred_days and _normalise_day(entry.get("day")) not in preferred_days:
            penalty += 1

    return penalty


def _avoid_day_penalty(entries: Sequence[Entry], requirements: Requirements) -> int:
    lookup = _requirement_lookup(requirements)
    penalty = 0

    for entry in entries:
        requirement = _entry_requirement(entry, lookup)
        if not requirement:
            continue
        avoid_days = {
            _normalise_day(value)
            for value in requirement.get("avoid_days", []) or []
        }
        if _normalise_day(entry.get("day")) in avoid_days:
            penalty += VERY_HIGH_PENALTY

    return penalty


def _preferred_period_penalty(entries: Sequence[Entry], requirements: Requirements) -> int:
    lookup = _requirement_lookup(requirements)
    penalty = 0

    for entry in entries:
        requirement = _entry_requirement(entry, lookup)
        if not requirement:
            continue
        preferred = {
            _normalise_period_id(value)
            for value in requirement.get("preferred_period_ids", []) or []
        }
        if preferred and _normalise_period_id(entry.get("period_id")) not in preferred:
            penalty += 1

    return penalty


def _avoid_period_penalty(entries: Sequence[Entry], requirements: Requirements) -> int:
    lookup = _requirement_lookup(requirements)
    penalty = 0

    for entry in entries:
        requirement = _entry_requirement(entry, lookup)
        if not requirement:
            continue
        avoid = {
            _normalise_period_id(value)
            for value in requirement.get("avoid_period_ids", []) or []
        }
        if _normalise_period_id(entry.get("period_id")) in avoid:
            penalty += VERY_HIGH_PENALTY

    return penalty


def _blocked_slot_penalty(entries: Sequence[Entry], requirements: Requirements) -> int:
    lookup = _requirement_lookup(requirements)
    penalty = 0

    for entry in entries:
        requirement = _entry_requirement(entry, lookup)
        if not requirement:
            continue

        blocked = {
            _text(value).lower()
            for value in requirement.get("blocked_slots", []) or []
        }
        slot = f"{_normalise_day(entry.get('day'))}::{_normalise_period_id(entry.get('period_id'))}"
        if slot in blocked:
            penalty += HARD_PENALTY

    return penalty


def _requirement_daily_counts(entries: Sequence[Entry]) -> Dict[Tuple[str, str, str], Counter]:
    result: Dict[Tuple[str, str, str], Counter] = defaultdict(Counter)
    for entry in entries:
        result[_lesson_identity(entry)][_normalise_day(entry.get("day"))] += 1
    return result


def _subject_daily_limit_penalty(entries: Sequence[Entry], requirements: Requirements) -> int:
    counts = _requirement_daily_counts(entries)
    penalty = 0

    for requirement in requirements:
        maximum = requirement.get("max_lessons_per_day")
        if maximum is None:
            continue

        maximum = _safe_int(maximum, 0)
        if maximum <= 0:
            continue

        key = _lesson_identity(requirement)
        for count in counts.get(key, Counter()).values():
            if count > maximum:
                penalty += (count - maximum) * VERY_HIGH_PENALTY

    return penalty


def _same_subject_consecutive_penalty(
    entries: Sequence[Entry],
    context: Dict[str, Any],
) -> int:
    school = _school_constraints(context)
    if not _safe_bool(school.get("avoid_same_subject_consecutive"), False):
        return 0

    lookup = _requirement_lookup(_requirements_from_context(context))
    grouped: Dict[Tuple[str, str], List[Entry]] = defaultdict(list)
    for entry in entries:
        grouped[
            (_text(entry.get("class_id")), _normalise_day(entry.get("day")))
        ].append(entry)

    penalty = 0
    for group in grouped.values():
        group.sort(key=lambda item: _period_index(item, context))
        for left, right in zip(group, group[1:]):
            if _period_index(right, context) != _period_index(left, context) + 1:
                continue

            if _normalise_subject(left.get("subject")) != _normalise_subject(right.get("subject")):
                continue

            requirement = _entry_requirement(left, lookup)
            double_count = _safe_int(requirement.get("double_lessons_per_week") if requirement else None, 0)
            if double_count > 0:
                # Declared double blocks are intentional consecutive lessons.
                continue

            penalty += 1

    return penalty


def _subject_consecutive_penalty(
    entries: Sequence[Entry],
    requirements: Requirements,
    context: Dict[str, Any],
) -> int:
    lookup = _requirement_lookup(requirements)
    grouped: Dict[Tuple[str, str, str], List[Entry]] = defaultdict(list)

    for entry in entries:
        requirement = _entry_requirement(entry, lookup)
        if not requirement or not _safe_bool(requirement.get("avoid_consecutive"), False):
            continue
        grouped[
            (
                _text(entry.get("class_id")),
                _normalise_day(entry.get("day")),
                _normalise_subject(entry.get("subject")),
            )
        ].append(entry)

    penalty = 0
    for group in grouped.values():
        group.sort(key=lambda item: _period_index(item, context))
        for left, right in zip(group, group[1:]):
            if _period_index(right, context) == _period_index(left, context) + 1:
                requirement = _entry_requirement(left, lookup)
                double_count = _safe_int(
                    requirement.get("double_lessons_per_week") if requirement else None,
                    0,
                )
                if double_count <= 0:
                    penalty += 5

    return penalty


def _spread_penalty(entries: Sequence[Entry], requirements: Requirements) -> int:
    counts = _requirement_daily_counts(entries)
    penalty = 0

    for requirement in requirements:
        if not _safe_bool(requirement.get("spread_across_days"), True):
            continue

        key = _lesson_identity(requirement)
        active_days = sum(1 for count in counts.get(key, Counter()).values() if count > 0)
        lessons_per_week = _safe_int(
            requirement.get("lessons_per_week", requirement.get("periods_per_week", 0)),
            0,
        )

        if lessons_per_week >= 2:
            desired_days = min(lessons_per_week, 3)
            if active_days < desired_days:
                penalty += (desired_days - active_days) * 5

    return penalty


def _max_consecutive(entries: Sequence[Entry], owner_field: str, context: Dict[str, Any]) -> int:
    school = _school_constraints(context)
    maximum = _safe_int(school.get("max_consecutive_periods"), 0)
    if maximum <= 0:
        return 0

    period_map = _period_map(context)
    owners = _owner_slots(entries, owner_field, context)
    penalty = 0

    for day_map in owners.values():
        for indexes in day_map.values():
            if not indexes:
                continue
            current = 1
            longest = 1
            for index in range(1, len(indexes)):
                if indexes[index] == indexes[index - 1] + 1:
                    current += 1
                    longest = max(longest, current)
                else:
                    current = 1
            if longest > maximum:
                penalty += (longest - maximum) * VERY_HIGH_PENALTY

    _ = period_map
    return penalty


def _minimum_gap_penalty(
    entries: Sequence[Entry],
    requirements: Requirements,
    context: Dict[str, Any],
) -> int:
    lookup = _requirement_lookup(requirements)
    grouped: Dict[Tuple[str, str, str], Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))

    for entry in entries:
        if _entry_requirement(entry, lookup) is None:
            continue
        grouped[_lesson_identity(entry)][_normalise_day(entry.get("day"))].append(
            _period_index(entry, context)
        )

    penalty = 0
    for requirement in requirements:
        minimum_gap = _safe_int(requirement.get("min_gap_periods"), 0)
        if minimum_gap <= 0:
            continue

        key = _lesson_identity(requirement)
        for indexes in grouped.get(key, {}).values():
            indexes.sort()
            for left, right in zip(indexes, indexes[1:]):
                distance = right - left
                if distance <= minimum_gap:
                    penalty += (minimum_gap - distance + 1) * HIGH_PENALTY

    return penalty


def _minimum_day_spacing_penalty(entries: Sequence[Entry], requirements: Requirements, context: Dict[str, Any]) -> int:
    counts = _requirement_daily_counts(entries)
    penalty = 0

    configured_days = {
        _normalise_day(item.get("name") if isinstance(item, dict) else item): index
        for index, item in enumerate(context.get("weekdays") or [])
        if _normalise_day(item.get("name") if isinstance(item, dict) else item)
    }
    if not configured_days:
        configured_days = DEFAULT_DAY_ORDER

    for requirement in requirements:
        minimum_days = _safe_int(requirement.get("min_days_between"), 0)
        if minimum_days <= 0:
            continue

        key = _lesson_identity(requirement)
        active_days = sorted(
            configured_days[day]
            for day, count in counts.get(key, Counter()).items()
            if count > 0 and day in configured_days
        )

        for left, right in zip(active_days, active_days[1:]):
            distance = right - left
            if distance <= minimum_days:
                penalty += (minimum_days - distance + 1) * HIGH_PENALTY

    return penalty


def _priority_number(requirement: Dict[str, Any]) -> int:
    value = requirement.get("priority", 25)
    if isinstance(value, bool):
        return 25
    if isinstance(value, (int, float)):
        return int(value)

    text = _text(value).lower()
    try:
        return int(text)
    except ValueError:
        return {
            "low": 10,
            "normal": 25,
            "high": 50,
            "critical": 100,
        }.get(text, 25)


def _priority_preference_penalty(base: int, candidate: int, current_entries: Sequence[Entry], candidate_entries: Sequence[Entry], requirements: Requirements) -> int:
    """Weight preference violations more strongly for high-priority subjects."""
    if not requirements:
        return 0

    base_metrics = _preference_penalty_by_requirement(current_entries, requirements)
    candidate_metrics = _preference_penalty_by_requirement(candidate_entries, requirements)
    total = 0

    for key, current_value in base_metrics.items():
        candidate_value = candidate_metrics.get(key, 0)
        delta = candidate_value - current_value
        if delta > 0:
            requirement = _requirement_lookup(requirements).get(key)
            total += delta * max(1, _priority_number(requirement or {}))

    _ = base
    _ = candidate
    return total


def _preference_penalty_by_requirement(entries: Sequence[Entry], requirements: Requirements) -> Dict[Tuple[str, str, str], int]:
    lookup = _requirement_lookup(requirements)
    result: Dict[Tuple[str, str, str], int] = defaultdict(int)

    for entry in entries:
        key = _lesson_identity(entry)
        requirement = lookup.get(key)
        if not requirement:
            continue

        if requirement.get("preferred_days") and _normalise_day(entry.get("day")) not in {
            _normalise_day(item) for item in requirement.get("preferred_days", []) or []
        }:
            result[key] += 1
        if _normalise_day(entry.get("day")) in {
            _normalise_day(item) for item in requirement.get("avoid_days", []) or []
        }:
            result[key] += 100
        if requirement.get("preferred_period_ids") and _normalise_period_id(entry.get("period_id")) not in {
            _normalise_period_id(item) for item in requirement.get("preferred_period_ids", []) or []
        }:
            result[key] += 1
        if _normalise_period_id(entry.get("period_id")) in {
            _normalise_period_id(item) for item in requirement.get("avoid_period_ids", []) or []
        }:
            result[key] += 100

    return dict(result)


# =========================================================
# PUBLIC SCORE
# =========================================================


def score(
    entries: Sequence[Entry],
    constraints: Any = None,
    *,
    requirements: Optional[Requirements] = None,
    weekdays: Optional[Sequence[Any]] = None,
    periods: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return a deterministic quality score. Higher score is better."""
    safe_entries = _clone_entries(entries)
    context = _context(
        constraints,
        requirements=requirements,
        weekdays=weekdays,
        periods=periods,
    )
    reqs = _requirements_from_context(context)
    school = _school_constraints(context)

    teacher_daily_penalty = _daily_load_penalty(safe_entries, "teacher_user_id")
    class_daily_penalty = _daily_load_penalty(safe_entries, "class_id")
    room_daily_penalty = _daily_load_penalty(safe_entries, "room_id")

    teacher_gaps = _calculate_real_gaps(safe_entries, "teacher_user_id", context)
    class_gaps = _calculate_real_gaps(safe_entries, "class_id", context)
    gaps = teacher_gaps + class_gaps

    collisions = _teacher_class_collisions(safe_entries)
    preferred_day_penalty = _preferred_day_penalty(safe_entries, reqs)
    avoid_day_penalty = _avoid_day_penalty(safe_entries, reqs)
    preferred_period_penalty = _preferred_period_penalty(safe_entries, reqs)
    avoid_period_penalty = _avoid_period_penalty(safe_entries, reqs)
    blocked_penalty = _blocked_slot_penalty(safe_entries, reqs)
    subject_daily_limit_penalty = _subject_daily_limit_penalty(safe_entries, reqs)
    spread_penalty = _spread_penalty(safe_entries, reqs)
    subject_consecutive_penalty = _subject_consecutive_penalty(safe_entries, reqs, context)
    same_subject_school_penalty = _same_subject_consecutive_penalty(safe_entries, context)
    maximum_consecutive_penalty = (
        _max_consecutive(safe_entries, "teacher_user_id", context)
        + _max_consecutive(safe_entries, "class_id", context)
    )
    minimum_gap_penalty = _minimum_gap_penalty(safe_entries, reqs, context)
    minimum_day_spacing_penalty = _minimum_day_spacing_penalty(safe_entries, reqs, context)

    teacher_limit_penalty = _daily_limit_penalty(
        safe_entries,
        "teacher_user_id",
        school.get("max_teacher_lessons_per_day"),
    )
    class_limit_penalty = _daily_limit_penalty(
        safe_entries,
        "class_id",
        school.get("max_class_lessons_per_day"),
    )
    room_limit_penalty = _daily_limit_penalty(
        safe_entries,
        "room_id",
        school.get("max_room_lessons_per_day"),
    )

    if not _safe_bool(school.get("balance_teacher_workload"), True):
        teacher_daily_penalty = 0

    if not _safe_bool(school.get("spread_subjects_across_week"), True):
        spread_penalty = 0

    penalty = (
        teacher_daily_penalty
        + class_daily_penalty
        + room_daily_penalty
        + (gaps * 3)
        + (collisions * HARD_PENALTY)
        + (preferred_day_penalty * 4)
        + avoid_day_penalty
        + (preferred_period_penalty * 3)
        + avoid_period_penalty
        + blocked_penalty
        + subject_daily_limit_penalty
        + (spread_penalty * 2)
        + (subject_consecutive_penalty * 5)
        + (same_subject_school_penalty * 5)
        + maximum_consecutive_penalty
        + minimum_gap_penalty
        + minimum_day_spacing_penalty
        + teacher_limit_penalty
        + class_limit_penalty
        + room_limit_penalty
    )

    return {
        "score": -penalty,
        "penalty": penalty,
        "teacher_daily_penalty": teacher_daily_penalty,
        "class_daily_penalty": class_daily_penalty,
        "room_daily_penalty": room_daily_penalty,
        "teacher_gaps": teacher_gaps,
        "class_gaps": class_gaps,
        "gaps": gaps,
        "collisions": collisions,
        "preferred_day_penalty": preferred_day_penalty,
        "avoid_day_penalty": avoid_day_penalty,
        "preferred_period_penalty": preferred_period_penalty,
        "avoid_period_penalty": avoid_period_penalty,
        "blocked_slot_penalty": blocked_penalty,
        "subject_daily_limit_penalty": subject_daily_limit_penalty,
        "spread_penalty": spread_penalty,
        "subject_consecutive_penalty": subject_consecutive_penalty,
        "school_subject_consecutive_penalty": same_subject_school_penalty,
        "maximum_consecutive_penalty": maximum_consecutive_penalty,
        "minimum_gap_penalty": minimum_gap_penalty,
        "minimum_day_spacing_penalty": minimum_day_spacing_penalty,
        "teacher_daily_limit_penalty": teacher_limit_penalty,
        "class_daily_limit_penalty": class_limit_penalty,
        "room_daily_limit_penalty": room_limit_penalty,
    }


# =========================================================
# REVELAAI REQUEST
# =========================================================


def build_revelaai_request(
    constraints: Any,
    entries: Optional[Sequence[Entry]] = None,
    *,
    requirements: Optional[Requirements] = None,
    weekdays: Optional[Sequence[Any]] = None,
    periods: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a structured, JSON-compatible advisory request for RevelaAI."""
    context = _context(
        constraints,
        requirements=requirements,
        weekdays=weekdays,
        periods=periods,
    )
    current_entries = _clone_entries(entries or [])
    reqs = _requirements_from_context(context)

    return {
        "task": "optimize_school_timetable",
        "mode": "advisory",
        "optimizer_version": OPTIMIZER_VERSION,
        "instructions": (
            "Improve the existing school timetable while preserving every "
            "required lesson occurrence. Return JSON only. Do not invent or "
            "remove subjects, teachers, classes, rooms, or lesson occurrences. "
            "Class, teacher, subject, school_id and timetable_id are server-owned "
            "identities. Only day, period_id and room_id are movable."
        ),
        "authority": {
            "revelaai_role": "advisor",
            "server_validator": "authoritative",
            "persistence": "service_layer_only",
        },
        "hard_constraints": [
            "No teacher conflicts.",
            "No class conflicts.",
            "No room conflicts.",
            "No blocked slots.",
            "No avoided days or periods.",
            "Lesson periods only.",
            "Preserve exact required lesson composition and counts.",
            "Do not change school or timetable identity.",
        ],
        "optimization_goals": [
            "Prefer requested days and periods.",
            "Spread subjects across the week where feasible.",
            "Balance teacher workload.",
            "Reduce unnecessary teacher/class gaps.",
            "Respect subject daily limits and spacing preferences.",
            "Reduce unnecessary consecutive lessons.",
            "Respect school-wide daily and consecutive-load limits.",
        ],
        "output_schema": {
            "entries": [
                {
                    "class_id": "preserve",
                    "teacher_user_id": "preserve",
                    "subject": "preserve",
                    "day": "move as needed",
                    "period_id": "move as needed",
                    "room_id": "move only when appropriate",
                }
            ],
            "suggestions": ["optional human-readable recommendations"],
        },
        "school_constraints": _school_constraints(context),
        "requirements": reqs,
        "weekdays": context.get("weekdays", []),
        "periods": context.get("periods", []),
        "current_entries": current_entries,
    }


# =========================================================
# PROPOSAL PARSING / VALIDATION
# =========================================================


def _coerce_ai_proposal(proposal: Any) -> Any:
    """Accept a dict or a JSON string returned by a model."""
    if isinstance(proposal, dict):
        return proposal

    if isinstance(proposal, str):
        raw = proposal.strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
            return parsed
        except json.JSONDecodeError:
            # Handle common fenced JSON responses without attempting code eval.
            if raw.startswith("```") and raw.endswith("```"):
                lines = raw.splitlines()
                if len(lines) >= 3:
                    fenced = "\n".join(lines[1:-1]).strip()
                    try:
                        return json.loads(fenced)
                    except json.JSONDecodeError:
                        return None

    return None


def _validate_proposal(
    proposal: Any,
    context: Dict[str, Any],
) -> Tuple[bool, List[Entry], Dict[str, Any]]:
    proposal = _coerce_ai_proposal(proposal)
    if not isinstance(proposal, dict):
        return False, [], {"reason": "AI proposal must be a JSON object."}

    candidate = proposal.get("entries")
    if not isinstance(candidate, list):
        return False, [], {"reason": "AI proposal must contain an 'entries' array."}

    candidate_entries = _clone_entries(candidate)
    requirements = _requirements_from_context(context)

    try:
        checked = validate(
            candidate_entries,
            requirements,
            weekdays=context.get("weekdays") or None,
            periods=context.get("periods") or None,
            max_teacher_lessons_per_day=_school_constraints(context).get("max_teacher_lessons_per_day"),
            max_class_lessons_per_day=_school_constraints(context).get("max_class_lessons_per_day"),
            max_room_lessons_per_day=_school_constraints(context).get("max_room_lessons_per_day"),
            max_consecutive_periods=_school_constraints(context).get("max_consecutive_periods"),
        )
    except TypeError:
        # Compatibility with older validator signatures. The proposal still
        # receives the validator's available checks rather than being skipped.
        try:
            checked = validate(candidate_entries, requirements)
        except Exception as exc:
            return False, [], {
                "reason": "Validator raised an exception.",
                "error": str(exc),
            }
    except Exception as exc:
        return False, [], {
            "reason": "Validator raised an exception.",
            "error": str(exc),
        }

    if not isinstance(checked, dict):
        return False, [], {"reason": "Validator returned an invalid response."}

    if not checked.get("valid"):
        return False, [], {
            "reason": "AI proposal failed timetable validation.",
            "validation": checked,
        }

    return True, candidate_entries, checked


# =========================================================
# SUGGESTIONS
# =========================================================


def _extract_suggestions(proposal: Any) -> List[Any]:
    parsed = _coerce_ai_proposal(proposal)
    if not isinstance(parsed, dict):
        return []
    suggestions = parsed.get("suggestions")
    return suggestions if isinstance(suggestions, list) else []


# =========================================================
# OPTIMIZATION
# =========================================================


def optimize(
    entries: Sequence[Entry],
    constraints: Any = None,
    ai_callable: Optional[AICallable] = None,
    *,
    requirements: Optional[Requirements] = None,
    weekdays: Optional[Sequence[Any]] = None,
    periods: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Optimize an existing valid timetable.

    A candidate is accepted only when it is:
        * server-validator valid,
        * composition-preserving,
        * duplicate-free,
        * reconciled against server-owned identities, and
        * strictly better according to ``score``.
    """
    current_entries = _clone_entries(entries)
    context = _context(
        constraints,
        requirements=requirements,
        weekdays=weekdays,
        periods=periods,
    )
    reqs = _requirements_from_context(context)

    try:
        base_validation = validate(
            current_entries,
            reqs,
            weekdays=context.get("weekdays") or None,
            periods=context.get("periods") or None,
            max_teacher_lessons_per_day=_school_constraints(context).get("max_teacher_lessons_per_day"),
            max_class_lessons_per_day=_school_constraints(context).get("max_class_lessons_per_day"),
            max_room_lessons_per_day=_school_constraints(context).get("max_room_lessons_per_day"),
            max_consecutive_periods=_school_constraints(context).get("max_consecutive_periods"),
        )
    except TypeError:
        try:
            base_validation = validate(current_entries, reqs)
        except Exception as exc:
            return {
                "entries": current_entries,
                "score": score(current_entries, context),
                "ai_used": False,
                "accepted": False,
                "suggestions": [],
                "validation": {"valid": False, "error": str(exc)},
                "optimizer_version": OPTIMIZER_VERSION,
                "reason": "Current timetable could not be validated.",
            }
    except Exception as exc:
        return {
            "entries": current_entries,
            "score": score(current_entries, context),
            "ai_used": False,
            "accepted": False,
            "suggestions": [],
            "validation": {"valid": False, "error": str(exc)},
            "optimizer_version": OPTIMIZER_VERSION,
            "reason": "Current timetable could not be validated.",
        }

    if not isinstance(base_validation, dict):
        base_validation = {
            "valid": False,
            "error": "Validator returned an invalid response.",
        }

    base_score = score(current_entries, context)
    result: Dict[str, Any] = {
        "entries": current_entries,
        "score": base_score,
        "ai_used": False,
        "accepted": False,
        "suggestions": [],
        "validation": base_validation,
        "optimizer_version": OPTIMIZER_VERSION,
    }

    if not base_validation.get("valid"):
        result["reason"] = (
            "Current timetable is invalid. AI optimization cannot replace an invalid base state."
        )
        return result

    if not callable(ai_callable):
        result["reason"] = "No AI optimizer supplied."
        return result

    ai_request = build_revelaai_request(context, current_entries)
    result["ai_request"] = ai_request

    try:
        proposal = ai_callable(ai_request)
    except Exception as exc:
        result["reason"] = "RevelaAI optimization failed."
        result["ai_error"] = str(exc)
        return result

    result["ai_used"] = True
    result["suggestions"] = _extract_suggestions(proposal)

    valid, candidate_entries, proposal_validation = _validate_proposal(proposal, context)
    result["proposal_validation"] = proposal_validation

    if not valid:
        result["reason"] = "AI proposal rejected by server validation."
        return result

    if _proposal_duplicates(candidate_entries):
        result["reason"] = "AI proposal contains duplicate slot assignments."
        return result

    if not _same_required_lesson_counts(current_entries, candidate_entries):
        result["reason"] = "AI proposal changed the required lesson composition."
        return result

    if not _optional_server_identity_matches(current_entries, candidate_entries):
        result["reason"] = "AI proposal supplied incorrect school or timetable identity."
        return result

    reconciled_ok, reconciled_entries, reconcile_info = _reconcile_ai_entries(
        current_entries,
        candidate_entries,
        context,
    )
    result["reconciliation"] = reconcile_info

    if not reconciled_ok:
        result["reason"] = "AI proposal failed server-side identity reconciliation."
        return result

    # Revalidate the reconciled candidate because the service will persist this
    # exact form, not the raw model output.
    try:
        reconciled_validation = validate(
            reconciled_entries,
            reqs,
            weekdays=context.get("weekdays") or None,
            periods=context.get("periods") or None,
            max_teacher_lessons_per_day=_school_constraints(context).get("max_teacher_lessons_per_day"),
            max_class_lessons_per_day=_school_constraints(context).get("max_class_lessons_per_day"),
            max_room_lessons_per_day=_school_constraints(context).get("max_room_lessons_per_day"),
            max_consecutive_periods=_school_constraints(context).get("max_consecutive_periods"),
        )
    except TypeError:
        reconciled_validation = validate(reconciled_entries, reqs)
    except Exception as exc:
        result["reason"] = "Reconciled candidate failed validator execution."
        result["reconciled_validation_error"] = str(exc)
        return result

    result["reconciled_validation"] = reconciled_validation
    if not isinstance(reconciled_validation, dict) or not reconciled_validation.get("valid"):
        result["reason"] = "Reconciled AI proposal failed server validation."
        return result

    candidate_score = score(reconciled_entries, context)
    result["candidate_score"] = candidate_score
    result["comparison"] = {
        "base_score": base_score["score"],
        "candidate_score": candidate_score["score"],
        "improvement": candidate_score["score"] - base_score["score"],
    }

    if candidate_score["score"] <= base_score["score"]:
        result["reason"] = (
            "AI proposal was valid but did not improve the timetable according to school preferences."
        )
        return result

    result.update(
        {
            "entries": reconciled_entries,
            "score": candidate_score,
            "accepted": True,
            "reason": "AI proposal improved the timetable.",
        }
    )
    return result


# =========================================================
# SUMMARY
# =========================================================


def summarize(
    entries: Sequence[Entry],
    constraints: Any = None,
    *,
    requirements: Optional[Requirements] = None,
    weekdays: Optional[Sequence[Any]] = None,
    periods: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return a compact optimizer summary for APIs and dashboards."""
    safe_entries = _clone_entries(entries)
    context = _context(
        constraints,
        requirements=requirements,
        weekdays=weekdays,
        periods=periods,
    )
    metrics = score(safe_entries, context)

    teachers = {
        _text(entry.get("teacher_user_id"))
        for entry in safe_entries
        if entry.get("teacher_user_id") is not None
    }
    classes = {
        _text(entry.get("class_id"))
        for entry in safe_entries
        if entry.get("class_id") is not None
    }
    rooms = {
        _text(entry.get("room_id"))
        for entry in safe_entries
        if entry.get("room_id") is not None
    }

    return {
        "entries": len(safe_entries),
        "teachers": len(teachers),
        "classes": len(classes),
        "rooms": len(rooms),
        "maximum_teacher_daily_load": _maximum_daily_load(safe_entries, "teacher_user_id"),
        "maximum_class_daily_load": _maximum_daily_load(safe_entries, "class_id"),
        "maximum_room_daily_load": _maximum_daily_load(safe_entries, "room_id"),
        **metrics,
    }
