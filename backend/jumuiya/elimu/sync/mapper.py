# backend/jumuiya/elimu/sync/mapper.py

from __future__ import annotations

"""
Canonical mapping layer for the Elimu synchronization subsystem.

Responsibilities
----------------
This module provides one consistent contract for:

- logical Elimu entity names;
- legacy entity aliases;
- authoritative MongoDB collection names;
- recursive deterministic normalization;
- school-configurable legacy field mappings;
- stable cross-device record identity;
- composite identities for attendance/timetable/teacher assignments;
- sync metadata handling;
- checksum-safe comparable payloads.

Important
---------
The historical API is preserved:

    canonical_record(entity_type, record, source="desktop")
    identity_key(entity_type, record)

Additional functionality is exposed through optional keyword arguments.
"""

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping, Optional


# =========================================================
# OPTIONAL BSON SUPPORT
# =========================================================

try:
    from bson import ObjectId
except Exception:  # pragma: no cover
    ObjectId = None  # type: ignore


# =========================================================
# ENTITY ALIASES
# =========================================================

ENTITY_ALIASES: dict[str, str] = {
    # -----------------------------------------------------
    # SCHOOL
    # -----------------------------------------------------
    "school": "school",
    "schools": "school",

    # -----------------------------------------------------
    # PROFILE
    # -----------------------------------------------------
    "profile": "profile",
    "profiles": "profile",
    "education_profile": "profile",
    "education_profiles": "profile",

    # -----------------------------------------------------
    # STAFF
    # -----------------------------------------------------
    "staff": "staff",
    "member": "staff",
    "members": "staff",
    "school_member": "staff",
    "school_members": "staff",

    # -----------------------------------------------------
    # TEACHER ASSIGNMENTS
    # -----------------------------------------------------
    "teacher_assignment": "teacher_assignments",
    "teacher_assignments": "teacher_assignments",
    "teaching_assignment": "teacher_assignments",
    "teaching_assignments": "teacher_assignments",

    # -----------------------------------------------------
    # CLASSES
    # -----------------------------------------------------
    "class": "classes",
    "classes": "classes",

    # -----------------------------------------------------
    # STUDENTS
    # -----------------------------------------------------
    "student": "students",
    "students": "students",

    # -----------------------------------------------------
    # SUBJECTS
    # -----------------------------------------------------
    "subject": "subjects",
    "subjects": "subjects",

    # -----------------------------------------------------
    # LESSONS
    # -----------------------------------------------------
    "lesson": "lessons",
    "lessons": "lessons",

    # -----------------------------------------------------
    # ASSIGNMENTS
    # -----------------------------------------------------
    "assignment": "assignments",
    "assignments": "assignments",

    # -----------------------------------------------------
    # ATTENDANCE
    # -----------------------------------------------------
    "attendance": "attendance",

    # -----------------------------------------------------
    # ASSESSMENTS
    # -----------------------------------------------------
    "assessment": "assessments",
    "assessments": "assessments",

    # -----------------------------------------------------
    # FEES
    # -----------------------------------------------------
    "fee": "fees",
    "fees": "fees",
    "student_fee": "fees",
    "student_fees": "fees",

    # -----------------------------------------------------
    # CBC
    # -----------------------------------------------------
    "cbc": "cbc_projects",
    "cbc_project": "cbc_projects",
    "cbc_projects": "cbc_projects",

    # -----------------------------------------------------
    # EVENTS
    # -----------------------------------------------------
    "event": "events",
    "events": "events",
    "school_event": "events",
    "school_events": "events",

    # -----------------------------------------------------
    # TIMETABLE
    # -----------------------------------------------------
    "timetable": "timetables",
    "timetables": "timetables",

    # -----------------------------------------------------
    # TIMETABLE ENTRIES
    # -----------------------------------------------------
    "timetable_entry": "timetable_entries",
    "timetable_entries": "timetable_entries",
}


# =========================================================
# AUTHORITATIVE COLLECTION REGISTRY
# =========================================================
#
# These are the actual Elimu collections currently used by
# the backend.
#
# Subjects intentionally has no standalone collection because
# current Elimu stores subject information in:
#
#   - teacher assignments
#   - timetable entries
#   - lessons
#   - assessments
#
# Do not invent a subject collection during synchronization.
# =========================================================

ENTITY_COLLECTIONS: dict[str, Optional[str]] = {
    "school": "jumuiya_schools",
    "profile": "jumuiya_education_profiles",
    "staff": "jumuiya_elimu_school_members",
    "teacher_assignments": "jumuiya_elimu_teacher_assignments",
    "classes": "jumuiya_classes",
    "students": "jumuiya_students",
    "subjects": None,
    "lessons": "jumuiya_lessons",
    "assignments": "jumuiya_assignments",
    "attendance": "jumuiya_attendance",
    "assessments": "jumuiya_assessments",
    "fees": "jumuiya_fees",
    "cbc_projects": "jumuiya_cbc_projects",
    "events": "jumuiya_school_events",
    "timetables": "jumuiya_elimu_timetables",
    "timetable_entries": "jumuiya_elimu_timetable_entries",
}


# =========================================================
# IDENTITY REGISTRY
# =========================================================
#
# Ordered from strongest identity to weakest fallback.
#
# IMPORTANT:
# Mongo _id is deliberately kept near the bottom.
# A Mongo ObjectId is database-local and should not normally
# be the cross-device identity.
# =========================================================

IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "school": (
        "school_id",
        "external_id",
        "registration_number",
        "code",
        "_id",
    ),

    "profile": (
        "profile_id",
        "user_id",
        "external_id",
        "_id",
    ),

    "staff": (
        "staff_id",
        "user_id",
        "employee_number",
        "employee_id",
        "external_id",
        "email",
        "_id",
    ),

    "teacher_assignments": (
        "assignment_id",
        "external_id",
        "_id",
    ),

    "classes": (
        "class_id",
        "external_id",
        "_id",
    ),

    "students": (
        "student_id",
        "admission_number",
        "student_code",
        "student_user_id",
        "external_id",
        "_id",
    ),

    "subjects": (
        "subject_id",
        "code",
        "external_id",
        "name",
        "subject",
    ),

    "lessons": (
        "lesson_id",
        "external_id",
        "_id",
    ),

    "assignments": (
        "assignment_id",
        "external_id",
        "_id",
    ),

    "attendance": (
        "attendance_id",
        "external_id",
        "_id",
    ),

    "assessments": (
        "assessment_id",
        "external_id",
        "_id",
    ),

    "fees": (
        "fee_id",
        "external_id",
        "receipt_number",
        "invoice_number",
        "_id",
    ),

    "cbc_projects": (
        "project_id",
        "cbc_project_id",
        "external_id",
        "_id",
    ),

    "events": (
        "event_id",
        "external_id",
        "_id",
    ),

    "timetables": (
        "timetable_id",
        "external_id",
        "_id",
    ),

    "timetable_entries": (
        "entry_id",
        "timetable_entry_id",
        "external_id",
        "_id",
    ),
}


# =========================================================
# PROTECTED FIELDS
# =========================================================
#
# School-provided legacy mappings must never be allowed to
# rewrite these structural/security-owned fields.
# =========================================================

PROTECTED_FIELDS = {
    "_id",
    "_created_at",
    "_updated_at",

    "school_id",

    "user_id",
    "student_user_id",
    "teacher_user_id",
    "staff_id",

    "created_at",
    "updated_at",

    "deleted",
    "deleted_at",
    "tombstone",

    "source_system",
    "sync_updated_at",
}


# =========================================================
# SYNC-ONLY METADATA
# =========================================================
#
# These fields are not business data and must not make an
# unchanged record appear modified during checksum comparison.
# =========================================================

SYNC_METADATA_FIELDS = {
    "source_system",
    "sync_updated_at",
}


# =========================================================
# TEXT / IDENTITY HELPERS
# =========================================================

def _text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _identity_text(value: Any) -> str:
    """
    Normalize a single identity component.

    Email addresses are case-insensitive.

    Other identifiers retain their case because school codes such
    as S1A and s1a should not automatically become identical.
    """
    value = _text(value)

    if "@" in value and " " not in value:
        return value.casefold()

    return value


# =========================================================
# DATETIME NORMALIZATION
# =========================================================

def _normalize_datetime(value: datetime) -> datetime:
    """
    Normalize datetimes to UTC.

    Naive timestamps are treated as UTC rather than silently being
    converted using the server machine's local timezone.
    """
    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


# =========================================================
# RECURSIVE NORMALIZATION
# =========================================================

def normalize(value: Any) -> Any:
    """
    Recursively normalize a value without unnecessarily destroying
    useful Python types.

    Rules
    -----
    str       -> surrounding whitespace removed
    Mapping   -> keys/values normalized recursively
    list      -> normalized recursively
    tuple     -> list
    set       -> deterministic sorted list
    ObjectId  -> string
    Decimal   -> exact decimal string
    datetime  -> timezone-aware UTC datetime
    date      -> preserved
    others    -> preserved unchanged
    """

    if value is None:
        return None

    # Mongo ObjectId -> portable string.
    if (
        ObjectId is not None
        and isinstance(value, ObjectId)
    ):
        return str(value)

    # Strings.
    if isinstance(value, str):
        return value.strip()

    # Datetime must be checked before date because datetime subclasses date.
    if isinstance(value, datetime):
        return _normalize_datetime(value)

    # Date-only values.
    if isinstance(value, date):
        return value

    # Decimal is converted to a string so financial values do not lose
    # precision during transport.
    if isinstance(value, Decimal):
        return format(value, "f")

    # Dictionaries / mappings.
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}

        for key, item in value.items():
            normalized_key = (
                key.strip()
                if isinstance(key, str)
                else str(key)
            )

            if not normalized_key:
                continue

            result[normalized_key] = normalize(
                item
            )

        return result

    # Lists / tuples.
    if isinstance(value, (list, tuple)):
        return [
            normalize(item)
            for item in value
        ]

    # Sets need deterministic ordering.
    if isinstance(value, set):
        normalized_items = [
            normalize(item)
            for item in value
        ]

        return sorted(
            normalized_items,
            key=lambda item: repr(item),
        )

    return value


# =========================================================
# ENTITY TYPE HELPERS
# =========================================================

def canonical_entity_type(
    entity_type: Any,
) -> str:
    """
    Resolve a user/client/legacy entity type to one canonical
    Elimu logical entity name.
    """
    raw = _text(entity_type).casefold()

    if not raw:
        raise ValueError(
            "entity_type is required."
        )

    canonical = ENTITY_ALIASES.get(
        raw
    )

    if canonical is None:
        raise ValueError(
            f"Unsupported Elimu sync entity type: {entity_type}"
        )

    return canonical


def entity_collection(
    entity_type: Any,
) -> str:
    """
    Resolve a logical entity to its authoritative MongoDB collection.

    Raises a clear error for virtual entities such as subjects instead
    of silently creating an incorrect collection.
    """
    canonical = canonical_entity_type(
        entity_type
    )

    collection_name = ENTITY_COLLECTIONS.get(
        canonical
    )

    if not collection_name:
        raise ValueError(
            f"Entity '{canonical}' has no standalone "
            "authoritative collection."
        )

    return collection_name


def is_virtual_entity(
    entity_type: Any,
) -> bool:
    canonical = canonical_entity_type(
        entity_type
    )

    return ENTITY_COLLECTIONS.get(
        canonical
    ) is None


def identity_fields(
    entity_type: Any,
) -> tuple[str, ...]:
    canonical = canonical_entity_type(
        entity_type
    )

    return IDENTITY_FIELDS.get(
        canonical,
        (
            "id",
            "external_id",
            "_id",
        ),
    )


# =========================================================
# FIELD MAPPING
# =========================================================

def _mapping_for_entity(
    entity_type: str,
    field_mappings: Optional[
        Mapping[str, Any]
    ],
) -> Mapping[str, Any]:
    """
    Support both:

        {
            "students": {
                "AdmissionNo": "admission_number"
            }
        }

    and direct:

        {
            "AdmissionNo": "admission_number"
        }
    """
    if not isinstance(
        field_mappings,
        Mapping,
    ):
        return {}

    canonical = canonical_entity_type(
        entity_type
    )

    # Preferred nested representation.
    mapping = field_mappings.get(
        canonical
    )

    if isinstance(
        mapping,
        Mapping,
    ):
        return mapping

    # Allow callers using a legacy alias.
    alias_mapping = field_mappings.get(
        _text(entity_type)
    )

    if isinstance(
        alias_mapping,
        Mapping,
    ):
        return alias_mapping

    # Direct field map.
    if field_mappings and all(
        isinstance(key, str)
        and isinstance(value, str)
        for key, value in field_mappings.items()
    ):
        return field_mappings

    return {}


def apply_field_mappings(
    entity_type: Any,
    record: Mapping[str, Any],
    field_mappings: Optional[
        Mapping[str, Any]
    ] = None,
) -> dict[str, Any]:
    """
    Translate legacy/desktop field names into canonical Elimu names.

    Canonical fields already present in the source record always win.
    This prevents stale aliases from overwriting canonical values.
    """
    if not isinstance(
        record,
        Mapping,
    ):
        raise ValueError(
            "record must be a JSON object."
        )

    canonical = canonical_entity_type(
        entity_type
    )

    mapping = _mapping_for_entity(
        canonical,
        field_mappings,
    )

    source = dict(record)
    result = dict(source)

    for source_field, target_field in mapping.items():
        source_name = _text(
            source_field
        )

        target_name = _text(
            target_field
        )

        if not source_name:
            continue

        if not target_name:
            continue

        # Mongo/operator injection protection.
        if target_name.startswith("$"):
            continue

        # Server/system fields may not be rewritten via a school mapping.
        if target_name in PROTECTED_FIELDS:
            continue

        if source_name not in source:
            continue

        # Canonical source wins.
        if target_name in source:
            continue

        result[target_name] = source[
            source_name
        ]

    return result


def exclude_fields(
    record: Mapping[str, Any],
    fields: Optional[
        Iterable[Any]
    ] = None,
) -> dict[str, Any]:
    """
    Remove configured fields before synchronization.

    Field names are exact so a school's exclusion policy does not
    unexpectedly remove similarly named business fields.
    """
    blocked = {
        _text(field)
        for field in (
            fields or []
        )
        if _text(field)
    }

    if not blocked:
        return dict(record)

    return {
        key: value
        for key, value in record.items()
        if key not in blocked
    }


# =========================================================
# CANONICAL RECORD
# =========================================================

def canonical_record(
    entity_type: Any,
    record: Mapping[str, Any],
    source: str = "desktop",
    *,
    field_mappings: Optional[
        Mapping[str, Any]
    ] = None,
    excluded_fields: Optional[
        Iterable[Any]
    ] = None,
    school_id: Any = None,
) -> dict[str, Any]:
    """
    Build the canonical Elimu sync record.

    CRITICAL:
    This function intentionally does NOT set:

        sync_updated_at = datetime.now(...)

    on every invocation.

    Doing that would cause every unchanged record to appear changed on
    every sync cycle.
    """
    canonical = canonical_entity_type(
        entity_type
    )

    if not isinstance(
        record,
        Mapping,
    ):
        raise ValueError(
            f"{canonical} record must be a JSON object."
        )

    mapped = apply_field_mappings(
        canonical,
        record,
        field_mappings,
    )

    filtered = exclude_fields(
        mapped,
        excluded_fields,
    )

    normalized = normalize(
        filtered
    )

    if not isinstance(
        normalized,
        dict,
    ):
        raise ValueError(
            "Canonical record must be an object."
        )

    # The trusted service layer may inject school ownership.
    # Never use an external payload to replace an existing school_id.
    if (
        school_id is not None
        and not normalized.get("school_id")
    ):
        normalized["school_id"] = _text(
            school_id
        )

    normalized_source = (
        _text(source)
        or "desktop"
    )

    # Preserve an existing authoritative value.
    normalized.setdefault(
        "source_system",
        normalized_source,
    )

    return normalized


# =========================================================
# FIRST-NON-EMPTY IDENTITY FIELD
# =========================================================

def _first_non_empty(
    record: Mapping[str, Any],
    candidates: Iterable[str],
) -> tuple[
    Optional[str],
    Any,
]:
    for field in candidates:
        value = record.get(
            field
        )

        if value is None:
            continue

        if isinstance(
            value,
            str,
        ):
            if not value.strip():
                continue

        elif value == "":
            continue

        return field, value

    return None, None


# =========================================================
# IDENTITY COMPONENTS
# =========================================================

def _component(
    field: str,
    value: Any,
) -> str:
    normalized = normalize(
        value
    )

    if isinstance(
        normalized,
        (
            dict,
            list,
            tuple,
            set,
        ),
    ):
        normalized = repr(
            normalized
        )

    return (
        f"{field}="
        f"{_identity_text(normalized)}"
    )


def _composite_key(
    parts: Iterable[
        tuple[str, Any]
    ],
) -> Optional[str]:
    """
    Construct a stable field-labelled composite key.

    Example:

        teacher_user_id=abc|class_id=class-01
    """
    usable: list[str] = []

    for field, value in parts:
        if value is None:
            return None

        if (
            isinstance(value, str)
            and not value.strip()
        ):
            return None

        usable.append(
            _component(
                field,
                value,
            )
        )

    if not usable:
        return None

    return "|".join(
        usable
    )


# =========================================================
# TEACHER ASSIGNMENT IDENTITY
# =========================================================

def _teacher_assignment_identity(
    record: Mapping[str, Any],
) -> Optional[str]:
    """
    Durable identity for a teacher/class assignment.

    The Staff contract is:

        teacher_user_id
            +
        class_id

    That relationship is more portable than a Mongo ObjectId.
    """
    teacher_user_id = (
        record.get(
            "teacher_user_id"
        )
        or record.get(
            "user_id"
        )
    )

    class_id = record.get(
        "class_id"
    )

    return _composite_key(
        (
            (
                "teacher_user_id",
                teacher_user_id,
            ),
            (
                "class_id",
                class_id,
            ),
        )
    )


# =========================================================
# ATTENDANCE IDENTITY
# =========================================================

def _attendance_identity(
    record: Mapping[str, Any],
) -> Optional[str]:
    """
    Build a durable natural attendance key when an explicit
    attendance id is unavailable.

    Preferred fallback:

        student + date + lesson/timetable entry

    If lesson identity is absent:

        student + date + class + subject
    """
    student = (
        record.get(
            "student_id"
        )
        or record.get(
            "student_user_id"
        )
        or record.get(
            "admission_number"
        )
    )

    attendance_date = (
        record.get(
            "date"
        )
        or record.get(
            "attendance_date"
        )
    )

    lesson = (
        record.get(
            "lesson_id"
        )
        or record.get(
            "timetable_entry_id"
        )
    )

    if (
        student is None
        or attendance_date is None
    ):
        return None

    parts: list[
        tuple[str, Any]
    ] = [
        (
            "student",
            student,
        ),
        (
            "date",
            attendance_date,
        ),
    ]

    if lesson is not None:
        parts.append(
            (
                "lesson",
                lesson,
            )
        )
    else:
        class_id = record.get(
            "class_id"
        )

        subject = (
            record.get(
                "subject_id"
            )
            or record.get(
                "subject"
            )
        )

        if class_id is not None:
            parts.append(
                (
                    "class",
                    class_id,
                )
            )

        if subject is not None:
            parts.append(
                (
                    "subject",
                    subject,
                )
            )

    return _composite_key(
        parts
    )


# =========================================================
# ASSESSMENT IDENTITY
# =========================================================

def _assessment_identity(
    record: Mapping[str, Any],
) -> Optional[str]:
    """
    Build a deterministic assessment natural key.

    Student identity is included so two students taking the same
    assessment cannot collapse into one synchronization record.
    """
    student = (
        record.get(
            "student_id"
        )
        or record.get(
            "student_user_id"
        )
        or record.get(
            "admission_number"
        )
    )

    assessment = (
        record.get(
            "assessment_id"
        )
        or record.get(
            "assessment_name"
        )
        or record.get(
            "exam_name"
        )
        or record.get(
            "title"
        )
    )

    subject = (
        record.get(
            "subject_id"
        )
        or record.get(
            "subject"
        )
    )

    assessment_date = (
        record.get(
            "date"
        )
        or record.get(
            "assessment_date"
        )
        or record.get(
            "exam_date"
        )
    )

    return _composite_key(
        (
            (
                "student",
                student,
            ),
            (
                "assessment",
                assessment,
            ),
            (
                "subject",
                subject,
            ),
            (
                "date",
                assessment_date,
            ),
        )
    )


# =========================================================
# TIMETABLE ENTRY IDENTITY
# =========================================================

def _timetable_entry_identity(
    record: Mapping[str, Any],
) -> Optional[str]:
    """
    Timetable entry identity follows the immutable dimensions used
    by the Elimu timetable validator/optimizer:

        day
        period_id
        class_id
        teacher_user_id
        subject
    """
    day = record.get(
        "day"
    )

    period_id = (
        record.get(
            "period_id"
        )
        or record.get(
            "period"
        )
    )

    class_id = record.get(
        "class_id"
    )

    teacher_user_id = record.get(
        "teacher_user_id"
    )

    subject = (
        record.get(
            "subject_id"
        )
        or record.get(
            "subject"
        )
    )

    if any(
        value is None
        or (
            isinstance(
                value,
                str,
            )
            and not value.strip()
        )
        for value in (
            day,
            period_id,
            class_id,
            teacher_user_id,
            subject,
        )
    ):
        return None

    return _composite_key(
        (
            (
                "day",
                day,
            ),
            (
                "period_id",
                period_id,
            ),
            (
                "class_id",
                class_id,
            ),
            (
                "teacher_user_id",
                teacher_user_id,
            ),
            (
                "subject",
                subject,
            ),
        )
    )


# =========================================================
# IDENTITY KEY
# =========================================================

def identity_key(
    entity_type: Any,
    record: Mapping[str, Any],
) -> str:
    """
    Return the durable logical identity of an Elimu record.

    Composite identities are deliberately checked before Mongo _id
    so offline devices can match the same logical record even when
    their local database ObjectIds are different.
    """
    canonical = canonical_entity_type(
        entity_type
    )

    if not isinstance(
        record,
        Mapping,
    ):
        raise ValueError(
            "record must be a JSON object."
        )

    # -----------------------------------------------------
    # TEACHER ASSIGNMENTS
    # -----------------------------------------------------
    if canonical == "teacher_assignments":
        explicit_field, explicit_value = (
            _first_non_empty(
                record,
                (
                    "assignment_id",
                    "external_id",
                ),
            )
        )

        if explicit_field is not None:
            return _component(
                explicit_field,
                explicit_value,
            )

        composite = (
            _teacher_assignment_identity(
                record
            )
        )

        if composite:
            return composite

        # Last resort only.
        mongo_field, mongo_value = (
            _first_non_empty(
                record,
                ("_id",),
            )
        )

        if mongo_field is not None:
            return _component(
                mongo_field,
                mongo_value,
            )

    # -----------------------------------------------------
    # ATTENDANCE
    # -----------------------------------------------------
    elif canonical == "attendance":
        explicit_field, explicit_value = (
            _first_non_empty(
                record,
                (
                    "attendance_id",
                    "external_id",
                ),
            )
        )

        if explicit_field is not None:
            return _component(
                explicit_field,
                explicit_value,
            )

        composite = (
            _attendance_identity(
                record
            )
        )

        if composite:
            return composite

        mongo_field, mongo_value = (
            _first_non_empty(
                record,
                ("_id",),
            )
        )

        if mongo_field is not None:
            return _component(
                mongo_field,
                mongo_value,
            )

    # -----------------------------------------------------
    # ASSESSMENTS
    # -----------------------------------------------------
    elif canonical == "assessments":
        explicit_field, explicit_value = (
            _first_non_empty(
                record,
                (
                    "assessment_id",
                    "external_id",
                ),
            )
        )

        if explicit_field is not None:
            return _component(
                explicit_field,
                explicit_value,
            )

        composite = (
            _assessment_identity(
                record
            )
        )

        if composite:
            return composite

        mongo_field, mongo_value = (
            _first_non_empty(
                record,
                ("_id",),
            )
        )

        if mongo_field is not None:
            return _component(
                mongo_field,
                mongo_value,
            )

    # -----------------------------------------------------
    # TIMETABLE ENTRIES
    # -----------------------------------------------------
    elif canonical == "timetable_entries":
        explicit_field, explicit_value = (
            _first_non_empty(
                record,
                (
                    "entry_id",
                    "timetable_entry_id",
                    "external_id",
                ),
            )
        )

        if explicit_field is not None:
            return _component(
                explicit_field,
                explicit_value,
            )

        composite = (
            _timetable_entry_identity(
                record
            )
        )

        if composite:
            return composite

        mongo_field, mongo_value = (
            _first_non_empty(
                record,
                ("_id",),
            )
        )

        if mongo_field is not None:
            return _component(
                mongo_field,
                mongo_value,
            )

    # -----------------------------------------------------
    # NORMAL ENTITY IDENTITY
    # -----------------------------------------------------
    field, value = _first_non_empty(
        record,
        identity_fields(
            canonical
        ),
    )

    if field is None:
        raise ValueError(
            f"Unable to determine identity "
            f"for {canonical} record."
        )

    return _component(
        field,
        value,
    )


# =========================================================
# IDENTITY COMPONENTS
# =========================================================

def identity_components(
    entity_type: Any,
    record: Mapping[str, Any],
) -> list[dict[str, str]]:
    """
    Return identity information suitable for audit logs,
    diagnostics and sync debugging.
    """
    canonical = canonical_entity_type(
        entity_type
    )

    if not isinstance(
        record,
        Mapping,
    ):
        raise ValueError(
            "record must be a JSON object."
        )

    # -----------------------------------------------------
    # TEACHER ASSIGNMENT
    # -----------------------------------------------------
    if canonical == "teacher_assignments":
        explicit_field, explicit_value = (
            _first_non_empty(
                record,
                (
                    "assignment_id",
                    "external_id",
                ),
            )
        )

        if explicit_field is not None:
            return [
                {
                    "field": explicit_field,
                    "value": _identity_text(
                        explicit_value
                    ),
                }
            ]

        parts = [
            (
                "teacher_user_id",
                record.get(
                    "teacher_user_id"
                )
                or record.get(
                    "user_id"
                ),
            ),
            (
                "class_id",
                record.get(
                    "class_id"
                ),
            ),
        ]

        return [
            {
                "field": field,
                "value": _identity_text(
                    value
                ),
            }
            for field, value in parts
            if value is not None
            and _text(value)
        ]

    # -----------------------------------------------------
    # ATTENDANCE
    # -----------------------------------------------------
    if canonical == "attendance":
        explicit_field, explicit_value = (
            _first_non_empty(
                record,
                (
                    "attendance_id",
                    "external_id",
                ),
            )
        )

        if explicit_field is not None:
            return [
                {
                    "field": explicit_field,
                    "value": _identity_text(
                        explicit_value
                    ),
                }
            ]

        natural = (
            _attendance_identity(
                record
            )
        )

        if natural:
            return [
                {
                    "field": "composite",
                    "value": natural,
                }
            ]

    # -----------------------------------------------------
    # ASSESSMENTS
    # -----------------------------------------------------
    if canonical == "assessments":
        explicit_field, explicit_value = (
            _first_non_empty(
                record,
                (
                    "assessment_id",
                    "external_id",
                ),
            )
        )

        if explicit_field is not None:
            return [
                {
                    "field": explicit_field,
                    "value": _identity_text(
                        explicit_value
                    ),
                }
            ]

        natural = (
            _assessment_identity(
                record
            )
        )

        if natural:
            return [
                {
                    "field": "composite",
                    "value": natural,
                }
            ]

    # -----------------------------------------------------
    # TIMETABLE ENTRY
    # -----------------------------------------------------
    if canonical == "timetable_entries":
        explicit_field, explicit_value = (
            _first_non_empty(
                record,
                (
                    "entry_id",
                    "timetable_entry_id",
                    "external_id",
                ),
            )
        )

        if explicit_field is not None:
            return [
                {
                    "field": explicit_field,
                    "value": _identity_text(
                        explicit_value
                    ),
                }
            ]

        natural = (
            _timetable_entry_identity(
                record
            )
        )

        if natural:
            return [
                {
                    "field": "composite",
                    "value": natural,
                }
            ]

    # -----------------------------------------------------
    # NORMAL ENTITY
    # -----------------------------------------------------
    field, value = _first_non_empty(
        record,
        identity_fields(
            canonical
        ),
    )

    if field is None:
        # Raise the same canonical identity error.
        identity_key(
            canonical,
            record,
        )

    return [
        {
            "field": field or "unknown",
            "value": _identity_text(
                value
            ),
        }
    ]


# =========================================================
# IDENTITY DOCUMENT
# =========================================================

def identity_document(
    entity_type: Any,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Return a structured identity object useful to the sync ledger.
    """
    canonical = canonical_entity_type(
        entity_type
    )

    return {
        "entity_type": canonical,
        "entity_key": identity_key(
            canonical,
            record,
        ),
        "components": identity_components(
            canonical,
            record,
        ),
    }


# =========================================================
# SYNC METADATA STRIPPING
# =========================================================

def strip_sync_metadata(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Remove only volatile synchronization metadata.

    Business fields such as created_at and updated_at are intentionally
    preserved because they may represent real domain revision information.
    """
    if not isinstance(
        record,
        Mapping,
    ):
        raise ValueError(
            "record must be a JSON object."
        )

    return {
        key: deepcopy(value)
        for key, value in record.items()
        if key not in SYNC_METADATA_FIELDS
    }


# =========================================================
# TRANSPORT PAYLOAD
# =========================================================

def sync_payload(
    record: Mapping[str, Any],
    *,
    include_mongo_id: bool = False,
) -> dict[str, Any]:
    """
    Prepare a portable transport payload.

    By default Mongo _id is removed because ObjectIds are database-local.

    The stable cross-device identity is represented separately through:

        entity_type
        entity_key
    """
    payload = strip_sync_metadata(
        record
    )

    if not include_mongo_id:
        payload.pop(
            "_id",
            None,
        )

    return normalize(
        payload
    )


# =========================================================
# CHECKSUM-SAFE COMPARABLE RECORD
# =========================================================

def comparable_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Return the deterministic business representation used by
    conflict/checksum logic.

    Volatile synchronization metadata is removed.
    Mongo _id is removed because it is database-local.
    """
    return sync_payload(
        record,
        include_mongo_id=False,
    )


# =========================================================
# RECORD REVISION HELPERS
# =========================================================

def record_updated_at(
    record: Mapping[str, Any],
) -> Any:
    """
    Return the strongest available timestamp for conflict ordering.
    """
    return (
        record.get(
            "updated_at"
        )
        or record.get(
            "modified_at"
        )
        or record.get(
            "last_modified_at"
        )
        or record.get(
            "created_at"
        )
    )


def record_revision(
    record: Mapping[str, Any],
) -> Optional[int]:
    """
    Extract an explicit numeric revision/version where available.
    """
    for field in (
        "revision",
        "version",
        "sync_revision",
    ):
        value = record.get(
            field
        )

        if value is None:
            continue

        if isinstance(
            value,
            bool,
        ):
            continue

        try:
            return int(
                value
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

    return None


# =========================================================
# DELETE / TOMBSTONE HELPERS
# =========================================================

def is_deleted_record(
    record: Mapping[str, Any],
) -> bool:
    """
    Detect both explicit deletes and tombstone representations.
    """
    if not isinstance(
        record,
        Mapping,
    ):
        return False

    deleted = record.get(
        "deleted"
    )

    if isinstance(
        deleted,
        bool,
    ) and deleted:
        return True

    tombstone = record.get(
        "tombstone"
    )

    if isinstance(
        tombstone,
        bool,
    ) and tombstone:
        return True

    operation = _text(
        record.get(
            "operation"
        )
    ).casefold()

    return operation == "delete"


# =========================================================
# LEGACY COMPATIBILITY
# =========================================================

def normalize_entity_type(
    entity_type: Any,
) -> str:
    """
    Compatibility alias for callers that prefer the models.py naming.
    """
    return canonical_entity_type(
        entity_type
    )


def collection_for_entity(
    entity_type: Any,
) -> str:
    """
    Compatibility alias for callers that use collection_for_entity().
    """
    return entity_collection(
        entity_type
    )