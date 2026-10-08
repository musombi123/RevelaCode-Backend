from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.elimu.permissions import authorize

from .generator import (
    GENERATOR_VERSION,
    GenerationError,
    generate,
)
from .models import (
    ENTRIES,
    TIMETABLES,
    STATUS_ARCHIVED,
    STATUS_DRAFT,
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_PUBLISHED,
    STATUS_READY,
    entry_doc,
    now_utc,
    timetable_doc,
)
from .optimizer import optimize
from .validator import validate


# =========================================================
# COLLECTIONS
# =========================================================

TIMETABLE_COLLECTION = TIMETABLES
ENTRY_COLLECTION = ENTRIES


# =========================================================
# HELPERS
# =========================================================

def sid(
    member: dict,
) -> str:
    school_id = str(
        member.get(
            "school_id",
            "",
        )
    ).strip()

    if not school_id:
        raise APIError(
            "Active Elimu membership has no school.",
            500,
            "invalid_school_membership",
        )

    return school_id


def _uid(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(
        value
    ).strip()


def _object_id(
    value: Any,
    *,
    field_name: str,
) -> ObjectId:
    text_value = _uid(
        value
    )

    if not text_value:
        raise APIError(
            f"{field_name} is required.",
            422,
            f"{field_name}_required",
        )

    if not ObjectId.is_valid(
        text_value
    ):
        raise APIError(
            f"Invalid {field_name}.",
            422,
            f"invalid_{field_name}",
        )

    return ObjectId(
        text_value
    )


def _ser(
    document: dict | None,
) -> dict | None:
    if not document:
        return None

    data = dict(
        document
    )

    if isinstance(
        data.get("_id"),
        ObjectId,
    ):
        data["_id"] = str(
            data["_id"]
        )

    for key in (
        "created_at",
        "updated_at",
        "published_at",
        "generated_at",
        "generation_started_at",
    ):
        value = data.get(
            key
        )

        if isinstance(
            value,
            datetime,
        ):
            data[key] = value.isoformat()

    return data


def _many(
    documents,
) -> list[dict]:
    return [
        _ser(document)
        for document in documents
    ]


# =========================================================
# PERIOD HELPERS
# =========================================================

def _lesson_periods(
    periods: list[dict],
) -> list[dict]:
    return [
        period
        for period in periods
        if str(
            period.get(
                "type",
                "lesson",
            )
        ).strip().lower()
        == "lesson"
    ]


def _period_map(
    periods: list[dict],
) -> dict[str, dict]:
    return {
        _uid(
            period.get(
                "period_id"
            )
        ): period
        for period in periods
        if _uid(
            period.get(
                "period_id"
            )
        )
    }


def _period_ids(
    periods: list[dict],
) -> set[str]:
    return {
        _uid(
            period.get(
                "period_id"
            )
        )
        for period in periods
        if _uid(
            period.get(
                "period_id"
            )
        )
    }


def _validate_slot_exists(
    timetable: dict,
    day: str,
    period_id: str,
) -> None:

    weekdays = {
        str(
            day_value
        ).strip().lower()
        for day_value in timetable.get(
            "weekdays",
            [],
        )
    }

    normalized_day = (
        _uid(day).lower()
    )

    if normalized_day not in weekdays:
        raise APIError(
            "The selected day is not enabled for this timetable.",
            422,
            "invalid_timetable_day",
        )

    periods = timetable.get(
        "periods",
        [],
    )

    period = _period_map(
        periods
    ).get(
        _uid(period_id)
    )

    if not period:
        raise APIError(
            "The selected timetable period does not exist.",
            422,
            "invalid_timetable_period",
        )

    period_type = str(
        period.get(
            "type",
            "lesson",
        )
    ).strip().lower()

    if period_type != "lesson":
        raise APIError(
            "Timetable entries can only be placed in lesson periods.",
            422,
            "invalid_lesson_period",
        )


# =========================================================
# GENERATOR COMPATIBILITY ADAPTER
# =========================================================

def _legacy_periods(
    periods: list[dict],
) -> list[dict]:
    """
    Convert the canonical Elimu period schema to the generator schema.

    Canonical:
        period_id
        label
        type

    Generator:
        id
        name
        kind
    """

    output = []

    for period in periods:

        period_id = _uid(
            period.get(
                "period_id"
            )
        )

        if not period_id:
            continue

        output.append(
            {
                "id": period_id,
                "name": (
                    _uid(
                        period.get(
                            "label"
                        )
                    )
                    or period_id
                ),
                "start_time": period.get(
                    "start_time"
                ),
                "end_time": period.get(
                    "end_time"
                ),
                "kind": (
                    _uid(
                        period.get(
                            "type",
                            "lesson",
                        )
                    ).lower()
                    or "lesson"
                ),
            }
        )

    return output


# =========================================================
# SCHOOL CONSTRAINT ADAPTER
# =========================================================

def _generator_rules(
    constraints: dict | None,
) -> dict:
    """
    Map canonical Elimu school constraint names to generator
    v3 rule names.

    Canonical Elimu:
        max_teacher_lessons_per_day
        max_class_lessons_per_day
        max_room_lessons_per_day
        max_consecutive_periods

    Generator:
        max_teacher_periods_per_day
        max_class_periods_per_day
        max_room_periods_per_day
        max_consecutive_periods
    """

    constraints = (
        constraints
        if isinstance(
            constraints,
            dict,
        )
        else {}
    )

    output = {}

    mappings = {
        "max_teacher_lessons_per_day":
            "max_teacher_periods_per_day",

        "max_class_lessons_per_day":
            "max_class_periods_per_day",

        "max_room_lessons_per_day":
            "max_room_periods_per_day",

        "max_consecutive_periods":
            "max_consecutive_periods",
    }

    for source, target in mappings.items():

        value = constraints.get(
            source
        )

        if value is None:
            continue

        output[
            target
        ] = value

    return output


# =========================================================
# BLOCKED SLOT ADAPTER
# =========================================================

def _blocked_slots(
    requirement: dict,
    weekdays: list[str],
    lesson_periods: list[dict],
) -> list[str]:
    """
    Combine explicit blocked slots with canonical avoid_days and
    avoid_period_ids.

    Explicit blocked slots are preserved.

    Example:

        monday::p1
    """

    blocked = set()

    # -----------------------------------------------------
    # Explicit blocked slots
    # -----------------------------------------------------

    for value in requirement.get(
        "blocked_slots",
        [],
    ) or []:

        normalized = (
            _uid(value).lower()
        )

        if normalized:
            blocked.add(
                normalized
            )

    # -----------------------------------------------------
    # Avoid days
    # -----------------------------------------------------

    avoid_days = {
        _uid(day).lower()
        for day in requirement.get(
            "avoid_days",
            [],
        ) or []
        if _uid(day)
    }

    # -----------------------------------------------------
    # Avoid periods
    # -----------------------------------------------------

    avoid_period_ids = {
        _uid(period_id)
        for period_id in requirement.get(
            "avoid_period_ids",
            [],
        ) or []
        if _uid(period_id)
    }

    # -----------------------------------------------------
    # Expand hard avoid rules into slot exclusions.
    # -----------------------------------------------------

    for day in weekdays:

        normalized_day = (
            _uid(day).lower()
        )

        for period in lesson_periods:

            period_id = _uid(
                period.get(
                    "period_id"
                )
            )

            if not period_id:
                continue

            if (
                normalized_day
                in avoid_days
            ):
                blocked.add(
                    f"{normalized_day}::{period_id}"
                )

            if (
                period_id
                in avoid_period_ids
            ):
                blocked.add(
                    f"{normalized_day}::{period_id}"
                )

    return sorted(
        blocked
    )


# =========================================================
# REQUIREMENT ADAPTER
# =========================================================

def _legacy_requirements(
    requirements: list[dict],
    weekdays: list[str],
    periods: list[dict],
) -> list[dict]:
    """
    Adapt canonical Elimu timetable requirements to generator v3.

    Canonical Elimu fields are preserved in the timetable document.
    The generator receives its compatibility vocabulary.
    """

    lesson_periods = _lesson_periods(
        periods
    )

    output = []

    for requirement in requirements:

        lessons_per_week = int(
            requirement.get(
                "lessons_per_week",
                0,
            )
            or 0
        )

        double_lesson = bool(
            requirement.get(
                "double_lesson",
                False,
            )
        )

        double_lessons_per_week = int(
            requirement.get(
                "double_lessons_per_week",
                0,
            )
            or 0
        )

        output.append(
            {
                # -----------------------------------------
                # Identity
                # -----------------------------------------

                "class_id": _uid(
                    requirement.get(
                        "class_id"
                    )
                ),

                "teacher_user_id": _uid(
                    requirement.get(
                        "teacher_user_id"
                    )
                ),

                "subject": _uid(
                    requirement.get(
                        "subject"
                    )
                ),

                # -----------------------------------------
                # Weekly workload
                # -----------------------------------------

                "periods_per_week": (
                    lessons_per_week
                ),

                # -----------------------------------------
                # Room
                # -----------------------------------------

                "room_id": (
                    _uid(
                        requirement.get(
                            "room_id"
                        )
                    )
                    or None
                ),

                # -----------------------------------------
                # Double lessons
                # -----------------------------------------

                "allow_double": (
                    double_lesson
                ),

                "double_lessons_per_week": (
                    double_lessons_per_week
                ),

                # -----------------------------------------
                # Preferences
                # -----------------------------------------

                "preferred_days": [
                    _uid(day).lower()
                    for day in requirement.get(
                        "preferred_days",
                        [],
                    ) or []
                    if _uid(day)
                ],

                "preferred_period_ids": [
                    _uid(period_id)
                    for period_id in requirement.get(
                        "preferred_period_ids",
                        [],
                    ) or []
                    if _uid(period_id)
                ],

                # -----------------------------------------
                # Hard avoidance rules
                # -----------------------------------------

                "avoid_days": [
                    _uid(day).lower()
                    for day in requirement.get(
                        "avoid_days",
                        [],
                    ) or []
                    if _uid(day)
                ],

                "avoid_period_ids": [
                    _uid(period_id)
                    for period_id in requirement.get(
                        "avoid_period_ids",
                        [],
                    ) or []
                    if _uid(period_id)
                ],

                "blocked_slots": _blocked_slots(
                    requirement,
                    weekdays,
                    lesson_periods,
                ),

                # -----------------------------------------
                # Distribution
                # -----------------------------------------

                "max_lessons_per_day": (
                    requirement.get(
                        "max_lessons_per_day"
                    )
                ),

                "min_gap_periods": (
                    int(
                        requirement.get(
                            "min_gap_periods",
                            0,
                        )
                        or 0
                    )
                ),

                "min_days_between": (
                    int(
                        requirement.get(
                            "min_days_between",
                            0,
                        )
                        or 0
                    )
                ),

                "spread_across_days": bool(
                    requirement.get(
                        "spread_across_days",
                        True,
                    )
                ),

                "avoid_consecutive": bool(
                    requirement.get(
                        "avoid_consecutive",
                        False,
                    )
                ),

                # -----------------------------------------
                # Priority
                # -----------------------------------------

                "priority": _priority_number(
                    requirement
                ),

                # -----------------------------------------
                # Display context
                # -----------------------------------------

                "teacher_name": (
                    requirement.get(
                        "teacher_name"
                    )
                ),

                "class_name": (
                    requirement.get(
                        "class_name"
                    )
                ),
            }
        )

    return output


def _priority_number(
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


# =========================================================
# GENERATED ENTRY ADAPTER
# =========================================================

def _canonical_entry(
    school_id: str,
    timetable_id: str,
    generated: dict,
    requirement: dict,
    created_by: Any = None,
) -> dict:
    """
    Convert a generator v3 entry into the canonical Elimu entry document.
    """

    slot = {
        "day": generated.get(
            "day"
        ),
        "period_id": generated.get(
            "period_id"
        ),
        "start_time": generated.get(
            "start_time"
        ),
        "end_time": generated.get(
            "end_time"
        ),
        "period_type": "lesson",
    }

    return entry_doc(
        school_id=school_id,
        timetable_id=timetable_id,
        requirement={
            "class_id": generated.get(
                "class_id",
                requirement.get(
                    "class_id"
                ),
            ),
            "teacher_user_id": generated.get(
                "teacher_user_id",
                requirement.get(
                    "teacher_user_id"
                ),
            ),
            "subject": generated.get(
                "subject",
                requirement.get(
                    "subject"
                ),
            ),
            "lessons_per_week": requirement.get(
                "lessons_per_week",
                1,
            ),
            "room_id": generated.get(
                "room_id",
                requirement.get(
                    "room_id"
                ),
            ),
        },
        slot=slot,
        generated_by=created_by,
    )


def _requirement_lookup(
    requirements: list[dict],
) -> dict[
    tuple[str, str, str],
    dict,
]:
    result = {}

    for requirement in requirements:

        key = (
            _uid(
                requirement.get(
                    "class_id"
                )
            ),
            _uid(
                requirement.get(
                    "teacher_user_id"
                )
            ),
            _uid(
                requirement.get(
                    "subject"
                )
            ),
        )

        result[
            key
        ] = requirement

    return result


# =========================================================
# CREATE
# =========================================================

def create(
    user_id: Any,
    payload: dict,
) -> dict:

    member = authorize(
        user_id,
        "timetable.generate",
    )

    school_id = sid(
        member
    )

    document = timetable_doc(
        school_id=school_id,
        weekdays=payload[
            "weekdays"
        ],
        periods=payload[
            "periods"
        ],
        requirements=payload[
            "requirements"
        ],
        created_by=user_id,
        status=STATUS_DRAFT,
        name=payload.get(
            "name"
        ),
        academic_year=payload.get(
            "academic_year"
        ),
        term=payload.get(
            "term"
        ),
        constraints=payload.get(
            "constraints"
        ),
        generation={
            "method": "manual",
            "engine": None,
            "version": None,
            "ai_assisted": False,
            "request_id": None,
        },
    )

    document[
        "metadata"
    ] = dict(
        payload.get(
            "metadata"
        ) or {}
    )

    result = collection(
        TIMETABLE_COLLECTION
    ).insert_one(
        document
    )

    document[
        "_id"
    ] = result.inserted_id

    return _ser(
        document
    )


# =========================================================
# LIST
# =========================================================

def list_timetables(
    user_id: Any,
) -> dict:

    member = authorize(
        user_id,
        "timetable.view",
    )

    school_id = sid(
        member
    )

    documents = (
        collection(
            TIMETABLE_COLLECTION
        )
        .find(
            {
                "school_id": school_id,
            }
        )
        .sort(
            "created_at",
            -1,
        )
    )

    return {
        "school_id": school_id,
        "timetables": _many(
            documents
        ),
    }


# =========================================================
# GET
# =========================================================

def get(
    user_id: Any,
    timetable_id: Any,
) -> dict:

    member = authorize(
        user_id,
        "timetable.view",
    )

    school_id = sid(
        member
    )

    oid = _object_id(
        timetable_id,
        field_name="timetable_id",
    )

    document = (
        collection(
            TIMETABLE_COLLECTION
        ).find_one(
            {
                "_id": oid,
                "school_id": school_id,
            }
        )
    )

    if not document:

        raise APIError(
            "Timetable not found.",
            404,
            "timetable_not_found",
        )

    result = _ser(
        document
    )

    entries = list(
        collection(
            ENTRY_COLLECTION
        ).find(
            {
                "school_id": school_id,
                "timetable_id": _uid(
                    timetable_id
                ),
            }
        )
    )

    result[
        "entries"
    ] = _sort_entries(
        entries,
        document.get(
            "weekdays",
            [],
        ),
        document.get(
            "periods",
            [],
        ),
    )

    return result


# =========================================================
# ENTRY SORTING
# =========================================================

def _sort_entries(
    entries: list[dict],
    weekdays: list[str],
    periods: list[dict],
) -> list[dict]:

    day_order = {
        str(
            day
        ).lower(): index
        for index, day in enumerate(
            weekdays
        )
    }

    period_order = {
        _uid(
            period.get(
                "period_id"
            )
        ): index
        for index, period in enumerate(
            periods
        )
    }

    serialized = [
        _ser(
            entry
        )
        for entry in entries
    ]

    serialized.sort(
        key=lambda entry: (
            day_order.get(
                str(
                    entry.get(
                        "day",
                        "",
                    )
                ).lower(),
                999,
            ),
            period_order.get(
                _uid(
                    entry.get(
                        "period_id"
                    )
                ),
                999,
            ),
            str(
                entry.get(
                    "class_id",
                    "",
                )
            ),
            str(
                entry.get(
                    "subject",
                    "",
                )
            ),
        )
    )

    return serialized


# =========================================================
# GENERATE
# =========================================================

def generate_for(
    user_id: Any,
    timetable_id: Any,
) -> dict:

    member = authorize(
        user_id,
        "timetable.generate",
    )

    school_id = sid(
        member
    )

    oid = _object_id(
        timetable_id,
        field_name="timetable_id",
    )

    document = (
        collection(
            TIMETABLE_COLLECTION
        ).find_one(
            {
                "_id": oid,
                "school_id": school_id,
            }
        )
    )

    if not document:

        raise APIError(
            "Timetable not found.",
            404,
            "timetable_not_found",
        )

    if document.get(
        "status"
    ) == STATUS_ARCHIVED:

        raise APIError(
            "Archived timetables cannot be regenerated.",
            409,
            "timetable_archived",
        )

    generation_started = now_utc()

    collection(
        TIMETABLE_COLLECTION
    ).update_one(
        {
            "_id": oid,
            "school_id": school_id,
        },
        {
            "$set": {
                "status": STATUS_GENERATING,
                "generation_started_at": generation_started,
                "generation_error": None,
                "updated_at": generation_started,
            }
        },
    )

    canonical_requirements = list(
        document.get(
            "requirements",
            [],
        )
    )

    canonical_periods = list(
        document.get(
            "periods",
            [],
        )
    )

    weekdays = list(
        document.get(
            "weekdays",
            [],
        )
    )

    legacy_periods = _legacy_periods(
        canonical_periods
    )

    legacy_requirements = _legacy_requirements(
        canonical_requirements,
        weekdays,
        canonical_periods,
    )

    generator_rules = _generator_rules(
        document.get(
            "constraints",
            {},
        )
    )

    # -----------------------------------------------------
    # Generate
    # -----------------------------------------------------

    try:

        result = generate(
            weekdays,
            legacy_periods,
            legacy_requirements,
            rules=generator_rules,
        )

    except GenerationError as exc:

        collection(
            TIMETABLE_COLLECTION
        ).update_one(
            {
                "_id": oid,
                "school_id": school_id,
            },
            {
                "$set": {
                    "status": STATUS_FAILED,
                    "generation_error": str(exc),
                    "generation": {
                        "method": "automatic",
                        "engine": (
                            "elimu_timetable_generator"
                        ),
                        "version": GENERATOR_VERSION,
                        "ai_assisted": False,
                        "request_id": None,
                        "generated_at": now_utc(),
                        "generated_by": _uid(
                            user_id
                        ),
                    },
                    "updated_at": now_utc(),
                }
            },
        )

        raise APIError(
            str(exc),
            422,
            "timetable_generation_failed",
        )

    generated_entries = result.get(
        "entries",
        []
    )

    requirement_lookup = _requirement_lookup(
        canonical_requirements
    )

    canonical_entries = []

    for generated in generated_entries:

        key = (
            _uid(
                generated.get(
                    "class_id"
                )
            ),
            _uid(
                generated.get(
                    "teacher_user_id"
                )
            ),
            _uid(
                generated.get(
                    "subject"
                )
            ),
        )

        requirement = requirement_lookup.get(
            key
        )

        if not requirement:

            collection(
                TIMETABLE_COLLECTION
            ).update_one(
                {
                    "_id": oid,
                    "school_id": school_id,
                },
                {
                    "$set": {
                        "status": STATUS_FAILED,
                        "generation_error": (
                            "Generator returned an entry "
                            "without a matching requirement."
                        ),
                        "updated_at": now_utc(),
                    }
                },
            )

            raise APIError(
                "Generated timetable contains an unknown requirement.",
                422,
                "timetable_generation_invalid",
            )

        canonical_entries.append(
            _canonical_entry(
                school_id=school_id,
                timetable_id=_uid(
                    timetable_id
                ),
                generated=generated,
                requirement=requirement,
                created_by=user_id,
            )
        )

    # -----------------------------------------------------
    # Final server validation
    # -----------------------------------------------------

    validation = validate(
        canonical_entries,
        legacy_requirements,
    )

    if not validation.get(
        "valid"
    ):

        collection(
            TIMETABLE_COLLECTION
        ).update_one(
            {
                "_id": oid,
                "school_id": school_id,
            },
            {
                "$set": {
                    "status": STATUS_FAILED,
                    "validation": validation,
                    "generation_error": (
                        "Generated timetable failed "
                        "server-side validation."
                    ),
                    "updated_at": now_utc(),
                }
            },
        )

        raise APIError(
            "Generated timetable failed validation.",
            422,
            "timetable_validation_failed",
        )

    # -----------------------------------------------------
    # Replace stored entries only after validation.
    # -----------------------------------------------------

    collection(
        ENTRY_COLLECTION
    ).delete_many(
        {
            "school_id": school_id,
            "timetable_id": _uid(
                timetable_id
            ),
        }
    )

    if canonical_entries:

        try:

            collection(
                ENTRY_COLLECTION
            ).insert_many(
                canonical_entries
            )

        except DuplicateKeyError:

            collection(
                TIMETABLE_COLLECTION
            ).update_one(
                {
                    "_id": oid,
                    "school_id": school_id,
                },
                {
                    "$set": {
                        "status": STATUS_FAILED,
                        "generation_error": (
                            "Timetable entries could not be "
                            "stored because of a duplicate slot."
                        ),
                        "updated_at": now_utc(),
                    }
                },
            )

            raise APIError(
                "Timetable entries could not be stored because of a duplicate slot.",
                409,
                "timetable_duplicate_entry",
            )

    timestamp = now_utc()

    generation_metadata = {
        "method": "automatic",
        "engine": "elimu_timetable_generator",
        "version": GENERATOR_VERSION,
        "ai_assisted": False,
        "request_id": None,
        "nodes_explored": result.get(
            "nodes_explored",
            0,
        ),
        "quality_score": result.get(
            "quality_score",
            0,
        ),
        "scheduled_periods": result.get(
            "scheduled_periods",
            len(
                canonical_entries
            ),
        ),
        "double_blocks": result.get(
            "double_blocks",
            0,
        ),
        "generated_at": timestamp,
        "generated_by": _uid(
            user_id
        ),
        "rules": generator_rules,
    }

    collection(
        TIMETABLE_COLLECTION
    ).update_one(
        {
            "_id": oid,
            "school_id": school_id,
        },
        {
            "$set": {
                "status": STATUS_READY,
                "validation": validation,
                "generation": generation_metadata,
                "updated_at": timestamp,
            }
        },
    )

    return {
        "timetable_id": _uid(
            timetable_id
        ),
        "entries": _many(
            canonical_entries
        ),
        "validation": validation,
        "generation": {
            **result,
            **generation_metadata,
            "method": "automatic",
            "engine": "elimu_timetable_generator",
        },
    }


# =========================================================
# UPDATE ENTRY
# =========================================================

def update_entry(
    user_id: Any,
    entry_id: Any,
    payload: dict,
) -> dict:

    member = authorize(
        user_id,
        "timetable.update",
    )

    school_id = sid(
        member
    )

    entry_oid = _object_id(
        entry_id,
        field_name="entry_id",
    )

    entry = (
        collection(
            ENTRY_COLLECTION
        ).find_one(
            {
                "_id": entry_oid,
                "school_id": school_id,
            }
        )
    )

    if not entry:

        raise APIError(
            "Timetable entry not found.",
            404,
            "timetable_entry_not_found",
        )

    timetable_oid = _object_id(
        entry.get(
            "timetable_id"
        ),
        field_name="timetable_id",
    )

    timetable = (
        collection(
            TIMETABLE_COLLECTION
        ).find_one(
            {
                "_id": timetable_oid,
                "school_id": school_id,
            }
        )
    )

    if not timetable:

        raise APIError(
            "Parent timetable not found.",
            404,
            "timetable_not_found",
        )

    if timetable.get(
        "status"
    ) == STATUS_ARCHIVED:

        raise APIError(
            "Archived timetables cannot be edited.",
            409,
            "timetable_archived",
        )

    if timetable.get(
        "status"
    ) == STATUS_PUBLISHED:

        raise APIError(
            "Published timetables cannot be edited directly. "
            "Create a revision first.",
            409,
            "published_timetable_locked",
        )

    day = payload.get(
        "day",
        entry.get(
            "day"
        ),
    )

    period_id = payload.get(
        "period_id",
        entry.get(
            "period_id"
        ),
    )

    room_id = payload.get(
        "room_id",
        entry.get(
            "room_id"
        ),
    )

    _validate_slot_exists(
        timetable,
        day,
        period_id,
    )

    candidate = {
        "class_id": entry.get(
            "class_id"
        ),
        "teacher_user_id": entry.get(
            "teacher_user_id"
        ),
        "subject": entry.get(
            "subject"
        ),
        "room_id": room_id,
        "day": _uid(
            day
        ).lower(),
        "period_id": _uid(
            period_id
        ),
    }

    all_entries = list(
        collection(
            ENTRY_COLLECTION
        ).find(
            {
                "school_id": school_id,
                "timetable_id": _uid(
                    entry.get(
                        "timetable_id"
                    )
                ),
                "_id": {
                    "$ne": entry_oid
                },
            }
        )
    )

    serialized_entries = [
        _ser(
            item
        )
        for item in all_entries
    ]

    validation = validate(
        serialized_entries + [
            candidate
        ],
        _legacy_requirements(
            timetable.get(
                "requirements",
                [],
            ),
            timetable.get(
                "weekdays",
                [],
            ),
            timetable.get(
                "periods",
                [],
            ),
        ),
    )

    if not validation.get(
        "valid"
    ):

        raise APIError(
            "The timetable change creates a conflict.",
            422,
            "timetable_conflict",
        )

    period = _period_map(
        timetable.get(
            "periods",
            [],
        )
    ).get(
        _uid(
            period_id
        )
    )

    timestamp = now_utc()

    update = {
        "day": _uid(
            day
        ).lower(),
        "period_id": _uid(
            period_id
        ),
        "room_id": (
            _uid(
                room_id
            )
            or None
        ),
        "start_time": (
            period.get(
                "start_time"
            )
            if period
            else None
        ),
        "end_time": (
            period.get(
                "end_time"
            )
            if period
            else None
        ),
        "updated_at": timestamp,
    }

    collection(
        ENTRY_COLLECTION
    ).update_one(
        {
            "_id": entry_oid,
            "school_id": school_id,
        },
        {
            "$set": update
        },
    )

    collection(
        TIMETABLE_COLLECTION
    ).update_one(
        {
            "_id": timetable_oid,
            "school_id": school_id,
        },
        {
            "$set": {
                "status": STATUS_DRAFT,
                "validation": validation,
                "updated_at": timestamp,
            }
        },
    )

    updated = (
        collection(
            ENTRY_COLLECTION
        ).find_one(
            {
                "_id": entry_oid,
                "school_id": school_id,
            }
        )
    )

    return _ser(
        updated
    )


# =========================================================
# PUBLISH
# =========================================================

def publish(
    user_id: Any,
    timetable_id: Any,
) -> dict:

    member = authorize(
        user_id,
        "timetable.publish",
    )

    school_id = sid(
        member
    )

    oid = _object_id(
        timetable_id,
        field_name="timetable_id",
    )

    timetable = (
        collection(
            TIMETABLE_COLLECTION
        ).find_one(
            {
                "_id": oid,
                "school_id": school_id,
            }
        )
    )

    if not timetable:

        raise APIError(
            "Timetable not found.",
            404,
            "timetable_not_found",
        )

    if timetable.get(
        "status"
    ) == STATUS_ARCHIVED:

        raise APIError(
            "Archived timetables cannot be published.",
            409,
            "timetable_archived",
        )

    entries = list(
        collection(
            ENTRY_COLLECTION
        ).find(
            {
                "school_id": school_id,
                "timetable_id": _uid(
                    timetable_id
                ),
            }
        )
    )

    if not entries:

        raise APIError(
            "A timetable must contain entries before it can be published.",
            422,
            "timetable_empty",
        )

    canonical_requirements = timetable.get(
        "requirements",
        [],
    )

    legacy_requirements = _legacy_requirements(
        canonical_requirements,
        timetable.get(
            "weekdays",
            [],
        ),
        timetable.get(
            "periods",
            [],
        ),
    )

    validation = validate(
        [
            _ser(entry)
            for entry in entries
        ],
        legacy_requirements,
    )

    if not validation.get(
        "valid"
    ):

        raise APIError(
            "Timetable contains conflicts and cannot be published.",
            422,
            "timetable_publish_blocked",
        )

    timestamp = now_utc()

    collection(
        TIMETABLE_COLLECTION
    ).update_one(
        {
            "_id": oid,
            "school_id": school_id,
        },
        {
            "$set": {
                "status": STATUS_PUBLISHED,
                "validation": validation,
                "published_at": timestamp,
                "published_by": _uid(
                    user_id
                ),
                "updated_at": timestamp,
            }
        },
    )

    return {
        "published": True,
        "timetable_id": _uid(
            timetable_id
        ),
        "published_at": timestamp.isoformat(),
        "validation": validation,
    }


# =========================================================
# TEACHER VIEW
# =========================================================

def view_for_teacher(
    user_id: Any,
) -> dict:

    member = authorize(
        user_id,
        "timetable.view",
    )

    school_id = sid(
        member
    )

    entries = list(
        collection(
            ENTRY_COLLECTION
        ).find(
            {
                "school_id": school_id,
                "teacher_user_id": _uid(
                    user_id
                ),
            }
        )
    )

    return {
        "school_id": school_id,
        "teacher_user_id": _uid(
            user_id
        ),
        "entries": _sort_teacher_entries(
            entries
        ),
    }


def _sort_teacher_entries(
    entries: list[dict],
) -> list[dict]:

    weekday_order = {
        "monday": 1,
        "tuesday": 2,
        "wednesday": 3,
        "thursday": 4,
        "friday": 5,
        "saturday": 6,
        "sunday": 7,
    }

    result = [
        _ser(
            entry
        )
        for entry in entries
    ]

    result.sort(
        key=lambda entry: (
            weekday_order.get(
                str(
                    entry.get(
                        "day",
                        "",
                    )
                ).lower(),
                99,
            ),
            str(
                entry.get(
                    "period_id",
                    "",
                )
            ),
        )
    )

    return result


# =========================================================
# CLASS VIEW
# =========================================================

def view_for_class(
    user_id: Any,
    class_id: Any,
) -> dict:

    member = authorize(
        user_id,
        "timetable.view",
        class_id=class_id,
    )

    school_id = sid(
        member
    )

    normalized_class_id = _uid(
        class_id
    )

    entries = list(
        collection(
            ENTRY_COLLECTION
        ).find(
            {
                "school_id": school_id,
                "class_id": normalized_class_id,
            }
        )
    )

    return {
        "school_id": school_id,
        "class_id": normalized_class_id,
        "entries": _sort_teacher_entries(
            entries
        ),
    }


# =========================================================
# AI OPTIMIZATION
# =========================================================

def ai_optimize(
    user_id: Any,
    timetable_id: Any,
    ai_callable,
) -> dict:
    """
    Ask RevelaAI to improve an existing timetable.

    RevelaAI does NOT write directly to MongoDB.

    Flow:

        existing timetable
                ↓
          school requirements
                ↓
             RevelaAI
                ↓
          candidate entries
                ↓
       server-side validation
                ↓
             persist
    """

    member = authorize(
        user_id,
        "timetable.update",
    )

    school_id = sid(
        member
    )

    timetable_id_text = _uid(
        timetable_id
    )

    timetable = get(
        user_id,
        timetable_id_text,
    )

    entries = timetable.get(
        "entries",
        [],
    )

    if not entries:

        raise APIError(
            "There are no timetable entries to optimize.",
            422,
            "timetable_empty",
        )

    canonical_requirements = timetable.get(
        "requirements",
        [],
    )

    legacy_requirements = _legacy_requirements(
        canonical_requirements,
        timetable.get(
            "weekdays",
            [],
        ),
        timetable.get(
            "periods",
            [],
        ),
    )

    generator_rules = _generator_rules(
        timetable.get(
            "constraints",
            {},
        )
    )

    optimizer_context = {
        "requirements": legacy_requirements,
        "constraints": generator_rules,

        "school_requirements": (
            canonical_requirements
        ),

        "weekdays": timetable.get(
            "weekdays",
            [],
        ),

        "periods": timetable.get(
            "periods",
            [],
        ),

        "timetable_id": timetable_id_text,

        "generator_version": GENERATOR_VERSION,

        "instructions": {
            "must_preserve_hard_constraints": True,
            "must_preserve_school_requirements": True,
            "must_return_structured_entries": True,
            "server_validator_is_authoritative": True,
        },
    }

    result = optimize(
        entries,
        optimizer_context,
        ai_callable,
    )

    if not isinstance(
        result,
        dict,
    ):

        raise APIError(
            "Timetable optimizer returned an invalid response.",
            502,
            "timetable_optimizer_invalid",
        )

    candidate_entries = result.get(
        "entries",
        [],
    )

    if not candidate_entries:

        return {
            **result,
            "updated": False,
            "timetable_id": timetable_id_text,
        }

    # -----------------------------------------------------
    # Final server-side validation
    # -----------------------------------------------------

    validation = validate(
        candidate_entries,
        legacy_requirements,
    )

    if not validation.get(
        "valid"
    ):

        raise APIError(
            "The optimized timetable failed validation.",
            422,
            "timetable_optimization_invalid",
        )

    # -----------------------------------------------------
    # Published schedules remain protected.
    # -----------------------------------------------------

    if (
        timetable.get(
            "status"
        )
        == STATUS_PUBLISHED
    ):

        raise APIError(
            "Published timetables cannot be optimized directly. "
            "Create a revision first.",
            409,
            "published_timetable_locked",
        )

    if (
        timetable.get(
            "status"
        )
        == STATUS_ARCHIVED
    ):

        raise APIError(
            "Archived timetables cannot be optimized.",
            409,
            "timetable_archived",
        )

    # -----------------------------------------------------
    # Replace only after successful validation.
    # -----------------------------------------------------

    collection(
        ENTRY_COLLECTION
    ).delete_many(
        {
            "school_id": school_id,
            "timetable_id": timetable_id_text,
        }
    )

    documents = []

    timestamp = now_utc()

    for entry in candidate_entries:

        documents.append(
            {
                "school_id": school_id,
                "timetable_id": timetable_id_text,

                "class_id": _uid(
                    entry.get(
                        "class_id"
                    )
                ),

                "teacher_user_id": _uid(
                    entry.get(
                        "teacher_user_id"
                    )
                ),

                "subject": _uid(
                    entry.get(
                        "subject"
                    )
                ),

                "room_id": (
                    _uid(
                        entry.get(
                            "room_id"
                        )
                    )
                    or None
                ),

                "day": _uid(
                    entry.get(
                        "day"
                    )
                ).lower(),

                "period_id": _uid(
                    entry.get(
                        "period_id"
                    )
                ),

                "start_time": entry.get(
                    "start_time"
                ),

                "end_time": entry.get(
                    "end_time"
                ),

                "period_type": "lesson",

                "created_at": timestamp,
                "updated_at": timestamp,

                "generated_by": _uid(
                    user_id
                ),
            }
        )

    if documents:

        try:

            collection(
                ENTRY_COLLECTION
            ).insert_many(
                documents
            )

        except DuplicateKeyError:

            raise APIError(
                "Optimized timetable contains duplicate entries.",
                409,
                "timetable_duplicate_entry",
            )

    generation_metadata = {
        "method": "ai_assisted",
        "engine": "revelaai",
        "version": GENERATOR_VERSION,
        "ai_assisted": True,
        "request_id": (
            result.get(
                "request_id"
            )
        ),
        "optimized_by": _uid(
            user_id
        ),
        "generated_at": timestamp,
        "constraints": generator_rules,
    }

    collection(
        TIMETABLE_COLLECTION
    ).update_one(
        {
            "_id": _object_id(
                timetable_id_text,
                field_name="timetable_id",
            ),
            "school_id": school_id,
        },
        {
            "$set": {
                "status": STATUS_READY,
                "validation": validation,
                "generation": generation_metadata,
                "updated_at": timestamp,
            }
        },
    )

    return {
        **result,
        "updated": True,
        "timetable_id": timetable_id_text,
        "validation": validation,
        "generation": generation_metadata,
    }