# backend/jumuiya/elimu/sync/engine.py

from __future__ import annotations

"""
Authoritative synchronization engine for the Elimu school OS.

Architecture
------------

Desktop / Android / legacy client
                |
                v
        canonical mapper
                |
                v
       conflict comparison
                |
        +-------+-------+
        |               |
     safe write      conflict
        |               |
        v               v
 authoritative       conflict
 Elimu collection   ledger record
        |
        v
   sync ledger snapshot

Important
---------
RECORDS is a synchronization ledger.

It is NOT the authoritative school database.

The authoritative records live in the actual Elimu collections such as:

    jumuiya_students
    jumuiya_classes
    jumuiya_elimu_school_members
    jumuiya_elimu_teacher_assignments
    jumuiya_attendance
    jumuiya_assessments
    jumuiya_elimu_timetables
    jumuiya_elimu_timetable_entries

This engine keeps those records synchronized while maintaining a
separate audit/revision/conflict ledger.
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from backend.jumuiya.core.database import collection

from .conflict import (
    changed_fields,
    compare,
    resolve_by_strategy,
)
from .mapper import (
    canonical_entity_type,
    canonical_record,
    comparable_record,
    entity_collection,
    identity_fields,
    identity_key,
    is_deleted_record,
    record_revision,
    record_updated_at,
)
from .models import (
    CONFLICTS,
    RECORDS,
    conflict_doc,
    payload_checksum,
    record_doc,
)


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_DELETE_MODE = "tombstone"
DEFAULT_CONFLICT_STRATEGY = "manual"

PROTECTED_AUTH_FIELDS = {
    "_id",
    "created_at",
}

VOLATILE_SYNC_FIELDS = {
    "source_system",
    "sync_updated_at",
}


# =========================================================
# TIME
# =========================================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# =========================================================
# BASIC HELPERS
# =========================================================

def _text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    if isinstance(value, bool):
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mapping(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(
        value,
        Mapping,
    ):
        return {}

    return dict(value)


def _school_id(
    value: Any,
) -> str:
    school = _text(value)

    if not school:
        raise ValueError(
            "school_id is required."
        )

    return school


# =========================================================
# MONGO OBJECT ID
# =========================================================

def _object_id(
    value: Any,
) -> Any:
    """
    Convert a string to ObjectId when possible.

    Returns the original value when BSON is unavailable or the value
    is not a valid ObjectId. This keeps the engine compatible with
    existing deployments that use string identifiers.
    """
    try:
        from bson import ObjectId
    except Exception:
        return value

    if isinstance(
        value,
        ObjectId,
    ):
        return value

    text = _text(value)

    if not text:
        return value

    if ObjectId.is_valid(
        text
    ):
        return ObjectId(text)

    return value


# =========================================================
# ENTITY VALIDATION
# =========================================================

def _entity(
    entity_type: Any,
) -> str:
    return canonical_entity_type(
        entity_type
    )


def _collection(
    entity_type: Any,
):
    return collection(
        entity_collection(
            entity_type
        )
    )


# =========================================================
# SCHOOL SCOPING
# =========================================================

def _school_filter(
    school_id: str,
    entity_type: str,
) -> dict[str, Any]:
    """
    Build the ownership portion of an authoritative query.

    All ordinary Elimu entities are school scoped through school_id.

    The school document itself is special because the existing Elimu
    school collection uses the Mongo document _id as the school identity.
    """
    if entity_type == "school":
        return {}

    return {
        "school_id": str(
            school_id
        )
    }


# =========================================================
# IDENTITY QUERY
# =========================================================

def _non_empty(
    record: Mapping[str, Any],
    field: str,
) -> Any:
    value = record.get(
        field
    )

    if value is None:
        return None

    if isinstance(
        value,
        str,
    ):
        if not value.strip():
            return None

        return value.strip()

    return value


def _explicit_identity_field(
    entity_type: str,
    record: Mapping[str, Any],
) -> tuple[
    Optional[str],
    Any,
]:
    """
    Find the first useful identity field while avoiding Mongo _id
    unless it is the final fallback.
    """
    for field in identity_fields(
        entity_type
    ):
        value = _non_empty(
            record,
            field,
        )

        if value is None:
            continue

        return field, value

    return None, None


def _identity_query(
    school_id: str,
    entity_type: str,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Build a direct Mongo query for the authoritative record.

    Composite natural identities are preferred for records that need
    cross-device matching.
    """
    canonical = _entity(
        entity_type
    )

    scope = _school_filter(
        school_id,
        canonical,
    )

    # -----------------------------------------------------
    # SCHOOL
    # -----------------------------------------------------

    if canonical == "school":
        school_value = (
            record.get(
                "school_id"
            )
            or record.get(
                "_id"
            )
        )

        if school_value is None:
            raise ValueError(
                "School synchronization requires school_id or _id."
            )

        return {
            "_id": _object_id(
                school_value
            )
        }

    # -----------------------------------------------------
    # TEACHER ASSIGNMENT
    # -----------------------------------------------------

    if canonical == "teacher_assignments":
        assignment_id = (
            _non_empty(
                record,
                "assignment_id",
            )
            or _non_empty(
                record,
                "external_id",
            )
        )

        if assignment_id is not None:
            return {
                **scope,
                "assignment_id": assignment_id,
            }

        teacher_user_id = (
            _non_empty(
                record,
                "teacher_user_id",
            )
            or _non_empty(
                record,
                "user_id",
            )
        )

        class_id = _non_empty(
            record,
            "class_id",
        )

        if (
            teacher_user_id is not None
            and class_id is not None
        ):
            return {
                **scope,
                "teacher_user_id": str(
                    teacher_user_id
                ),
                "class_id": str(
                    class_id
                ),
            }

    # -----------------------------------------------------
    # ATTENDANCE
    # -----------------------------------------------------

    if canonical == "attendance":
        attendance_id = (
            _non_empty(
                record,
                "attendance_id",
            )
            or _non_empty(
                record,
                "external_id",
            )
        )

        if attendance_id is not None:
            return {
                **scope,
                "attendance_id": attendance_id,
            }

        student_id = (
            _non_empty(
                record,
                "student_id",
            )
            or _non_empty(
                record,
                "student_user_id",
            )
            or _non_empty(
                record,
                "admission_number",
            )
        )

        attendance_date = (
            _non_empty(
                record,
                "date",
            )
            or _non_empty(
                record,
                "attendance_date",
            )
        )

        if (
            student_id is not None
            and attendance_date is not None
        ):
            query = {
                **scope,
            }

            # Prefer lesson/timetable identity where present.
            lesson_id = (
                _non_empty(
                    record,
                    "lesson_id",
                )
                or _non_empty(
                    record,
                    "timetable_entry_id",
                )
            )

            if lesson_id is not None:
                query.update(
                    {
                        "student_id": str(
                            student_id
                        ),
                        "date": attendance_date,
                    }
                )

                if record.get(
                    "lesson_id"
                ) is not None:
                    query["lesson_id"] = str(
                        record["lesson_id"]
                    )
                else:
                    query[
                        "timetable_entry_id"
                    ] = str(
                        record[
                            "timetable_entry_id"
                        ]
                    )

                return query

            # Natural fallback.
            query.update(
                {
                    "date": attendance_date,
                }
            )

            if record.get(
                "student_id"
            ) is not None:
                query["student_id"] = str(
                    student_id
                )
            elif record.get(
                "student_user_id"
            ) is not None:
                query[
                    "student_user_id"
                ] = str(
                    student_id
                )
            else:
                query[
                    "admission_number"
                ] = str(
                    student_id
                )

            if record.get(
                "class_id"
            ) is not None:
                query["class_id"] = str(
                    record[
                        "class_id"
                    ]
                )

            subject = (
                record.get(
                    "subject_id"
                )
                or record.get(
                    "subject"
                )
            )

            if subject is not None:
                query["subject"] = str(
                    subject
                )

            return query

    # -----------------------------------------------------
    # ASSESSMENTS
    # -----------------------------------------------------

    if canonical == "assessments":
        assessment_id = (
            _non_empty(
                record,
                "assessment_id",
            )
            or _non_empty(
                record,
                "external_id",
            )
        )

        if assessment_id is not None:
            return {
                **scope,
                "assessment_id": assessment_id,
            }

        student_id = (
            _non_empty(
                record,
                "student_id",
            )
            or _non_empty(
                record,
                "student_user_id",
            )
            or _non_empty(
                record,
                "admission_number",
            )
        )

        subject = (
            _non_empty(
                record,
                "subject_id",
            )
            or _non_empty(
                record,
                "subject",
            )
        )

        assessment_date = (
            _non_empty(
                record,
                "date",
            )
            or _non_empty(
                record,
                "assessment_date",
            )
            or _non_empty(
                record,
                "exam_date",
            )
        )

        title = (
            _non_empty(
                record,
                "assessment_name",
            )
            or _non_empty(
                record,
                "exam_name",
            )
            or _non_empty(
                record,
                "title",
            )
        )

        if student_id is not None:
            query = {
                **scope,
            }

            if record.get(
                "student_id"
            ) is not None:
                query["student_id"] = str(
                    student_id
                )
            elif record.get(
                "student_user_id"
            ) is not None:
                query[
                    "student_user_id"
                ] = str(
                    student_id
                )
            else:
                query[
                    "admission_number"
                ] = str(
                    student_id
                )

            if subject is not None:
                query["subject"] = str(
                    subject
                )

            if assessment_date is not None:
                # Keep exact business field where supplied.
                if record.get(
                    "date"
                ) is not None:
                    query["date"] = assessment_date
                elif record.get(
                    "assessment_date"
                ) is not None:
                    query[
                        "assessment_date"
                    ] = assessment_date
                else:
                    query[
                        "exam_date"
                    ] = assessment_date

            if title is not None:
                if record.get(
                    "assessment_name"
                ) is not None:
                    query[
                        "assessment_name"
                    ] = title
                elif record.get(
                    "exam_name"
                ) is not None:
                    query[
                        "exam_name"
                    ] = title
                else:
                    query[
                        "title"
                    ] = title

            return query

    # -----------------------------------------------------
    # TIMETABLE ENTRY
    # -----------------------------------------------------

    if canonical == "timetable_entries":
        entry_id = (
            _non_empty(
                record,
                "entry_id",
            )
            or _non_empty(
                record,
                "timetable_entry_id",
            )
            or _non_empty(
                record,
                "external_id",
            )
        )

        if entry_id is not None:
            return {
                **scope,
                "entry_id": entry_id,
            }

        day = _non_empty(
            record,
            "day",
        )

        period_id = (
            _non_empty(
                record,
                "period_id",
            )
            or _non_empty(
                record,
                "period",
            )
        )

        class_id = _non_empty(
            record,
            "class_id",
        )

        teacher_user_id = _non_empty(
            record,
            "teacher_user_id",
        )

        subject = (
            _non_empty(
                record,
                "subject_id",
            )
            or _non_empty(
                record,
                "subject",
            )
        )

        if all(
            value is not None
            for value in (
                day,
                period_id,
                class_id,
                teacher_user_id,
                subject,
            )
        ):
            return {
                **scope,
                "day": day,
                "period_id": str(
                    period_id
                ),
                "class_id": str(
                    class_id
                ),
                "teacher_user_id": str(
                    teacher_user_id
                ),
                "subject": str(
                    subject
                ),
            }

    # -----------------------------------------------------
    # NORMAL IDENTITY
    # -----------------------------------------------------

    field, value = (
        _explicit_identity_field(
            canonical,
            record,
        )
    )

    if field is None:
        raise ValueError(
            f"Unable to build authoritative query "
            f"for {canonical} record."
        )

    # Mongo _id needs ObjectId conversion when appropriate.
    if field == "_id":
        return {
            **scope,
            "_id": _object_id(
                value
            ),
        }

    return {
        **scope,
        field: value,
    }


# =========================================================
# AUTHORITATIVE LOOKUP
# =========================================================

def find_authoritative(
    school_id: str,
    entity_type: str,
    record: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    """
    Find the current cloud/authoritative Elimu document.

    The sync ledger is never consulted as the authoritative source.
    """
    canonical = _entity(
        entity_type
    )

    target = _collection(
        canonical
    )

    query = _identity_query(
        school_id,
        canonical,
        record,
    )

    document = target.find_one(
        query
    )

    if not document:
        return None

    return dict(
        document
    )


# =========================================================
# AUTHORITATIVE WRITE PREPARATION
# =========================================================

def _clean_write_payload(
    record: Mapping[str, Any],
    school_id: str,
) -> dict[str, Any]:
    """
    Build a safe cloud payload.

    Mongo-local identity and volatile sync fields are not copied from
    the client. Ownership is always server-controlled.
    """
    payload = deepcopy(
        dict(record)
    )

    payload.pop(
        "_id",
        None,
    )

    for field in VOLATILE_SYNC_FIELDS:
        payload.pop(
            field,
            None,
        )

    # Prevent Mongo operator injection at the top level.
    payload = {
        key: value
        for key, value in payload.items()
        if isinstance(
            key,
            str,
        )
        and not key.startswith("$")
    }

    # The server always owns school_id.
    payload[
        "school_id"
    ] = str(
        school_id
    )

    return payload


def _write_authoritative(
    school_id: str,
    entity_type: str,
    record: Mapping[str, Any],
    existing: Optional[
        Mapping[str, Any]
    ] = None,
) -> dict[str, Any]:
    """
    Upsert business fields into the authoritative Elimu collection.

    Existing records are updated using $set rather than full document
    replacement. This is intentional: legacy/locally-added fields not
    present in the incoming payload are preserved unless explicitly
    changed.
    """
    canonical = _entity(
        entity_type
    )

    target = _collection(
        canonical
    )

    query = _identity_query(
        school_id,
        canonical,
        record,
    )

    payload = _clean_write_payload(
        record,
        school_id,
    )

    if existing:
        existing_id = existing.get(
            "_id"
        )

        if existing_id is not None:
            # Never allow a client to change the database identity.
            query = {
                "_id": existing_id
            }

        # Do not overwrite the original creation timestamp.
        if "created_at" in payload:
            payload.pop(
                "created_at",
                None,
            )

        result = target.update_one(
            query,
            {
                "$set": {
                    **payload,
                    "updated_at": now_utc(),
                }
            },
        )

        if result.matched_count == 0:
            raise RuntimeError(
                f"Authoritative {canonical} record disappeared "
                "during synchronization."
            )

        refreshed = target.find_one(
            query
        )

        if not refreshed:
            raise RuntimeError(
                f"Unable to reload synchronized {canonical} record."
            )

        return dict(
            refreshed
        )

    # New record.
    document = {
        **payload,
    }

    now = now_utc()

    document.setdefault(
        "created_at",
        now,
    )

    document[
        "updated_at"
    ] = now

    result = target.insert_one(
        document
    )

    created = target.find_one(
        {
            "_id": result.inserted_id
        }
    )

    if not created:
        raise RuntimeError(
            f"Unable to reload newly synchronized {canonical} record."
        )

    return dict(
        created
    )


# =========================================================
# TOMBSTONE
# =========================================================

def _tombstone_authoritative(
    school_id: str,
    entity_type: str,
    local_record: Mapping[str, Any],
    existing: Optional[
        Mapping[str, Any]
    ],
) -> Optional[dict[str, Any]]:
    """
    Apply an offline delete without physically destroying the cloud
    document.

    If the cloud record does not exist, the deletion remains represented
    by the synchronization ledger. The engine intentionally avoids
    creating a partial invalid domain record merely to represent a
    tombstone.
    """
    if not existing:
        return None

    canonical = _entity(
        entity_type
    )

    target = _collection(
        canonical
    )

    query = {
        "_id": existing[
            "_id"
        ]
    }

    timestamp = now_utc()

    target.update_one(
        query,
        {
            "$set": {
                "deleted": True,
                "tombstone": True,
                "deleted_at": timestamp,
                "updated_at": timestamp,
                "sync_deleted_at": timestamp,
                "sync_source": _text(
                    local_record.get(
                        "source_system"
                    )
                )
                or "desktop",
                "school_id": str(
                    school_id
                ),
            }
        },
    )

    updated = target.find_one(
        query
    )

    return (
        dict(updated)
        if updated
        else None
    )


# =========================================================
# LEDGER
# =========================================================

def _ledger_find(
    school_id: str,
    entity_type: str,
    entity_key: str,
) -> Optional[dict[str, Any]]:
    document = collection(
        RECORDS
    ).find_one(
        {
            "school_id": str(
                school_id
            ),
            "entity_type": str(
                entity_type
            ),
            "entity_key": str(
                entity_key
            ),
        }
    )

    return (
        dict(document)
        if document
        else None
    )


def _ledger_revision(
    ledger: Optional[
        Mapping[str, Any]
    ],
    cloud: Optional[
        Mapping[str, Any]
    ],
) -> int:
    """
    Determine the next cloud synchronization revision.
    """
    ledger_revision = (
        _safe_int(
            ledger.get(
                "revision"
            ),
            0,
        )
        if ledger
        else 0
    )

    cloud_revision = (
        record_revision(
            cloud
        )
        if cloud
        else None
    )

    cloud_revision_value = (
        cloud_revision
        if cloud_revision is not None
        else 0
    )

    return max(
        ledger_revision,
        cloud_revision_value,
    ) + 1


def _ledger_upsert(
    school_id: str,
    entity_type: str,
    entity_key: str,
    payload: Mapping[str, Any],
    *,
    source: str,
    operation: str,
    revision: int,
    connection_id: Any = None,
    cloud_revision: Optional[int] = None,
    base_revision: Optional[int] = None,
    deleted: bool = False,
    state: str = "synced",
    source_record_id: Any = None,
    error: Optional[str] = None,
) -> dict[str, Any]:
    """
    Persist the synchronization snapshot.

    The ledger is deliberately updated only after authoritative writes
    succeed.
    """
    ledger_collection = collection(
        RECORDS
    )

    safe_payload = deepcopy(
        dict(payload)
    )

    checksum = payload_checksum(
        safe_payload
    )

    existing = _ledger_find(
        school_id,
        entity_type,
        entity_key,
    )

    created_at = (
        existing.get(
            "created_at"
        )
        if existing
        else now_utc()
    )

    document = {
        "school_id": str(
            school_id
        ),
        "entity_type": str(
            entity_type
        ),
        "entity_key": str(
            entity_key
        ),
        "source": _text(
            source
        )
        or "desktop",
        "operation": _text(
            operation
        )
        or "upsert",
        "sync_state": state,
        "revision": max(
            1,
            int(
                revision
            ),
        ),
        "base_revision": (
            base_revision
            if base_revision is None
            else max(
                0,
                int(
                    base_revision
                ),
            )
        ),
        "cloud_revision": (
            cloud_revision
            if cloud_revision is None
            else max(
                0,
                int(
                    cloud_revision
                ),
            )
        ),
        "checksum": checksum,
        "deleted": bool(
            deleted
        ),
        "payload": safe_payload,
        "last_error": error,
        "updated_at": now_utc(),
        "last_seen_at": now_utc(),
        "last_synced_at": (
            now_utc()
            if state == "synced"
            else (
                existing.get(
                    "last_synced_at"
                )
                if existing
                else None
            )
        ),
        "created_at": created_at,
    }

    # Preserve existing audit identifiers where available.
    if existing:
        if existing.get(
            "record_id"
        ) is not None:
            document[
                "record_id"
            ] = existing[
                "record_id"
            ]

        if existing.get(
            "connection_id"
        ) is not None:
            document[
                "connection_id"
            ] = existing[
                "connection_id"
            ]

        if existing.get(
            "source_record_id"
        ) is not None:
            document[
                "source_record_id"
            ] = existing[
                "source_record_id"
            ]

    if connection_id is not None:
        document[
            "connection_id"
        ] = _text(
            connection_id
        )

    if source_record_id is not None:
        document[
            "source_record_id"
        ] = _text(
            source_record_id
        )

    ledger_collection.update_one(
        {
            "school_id": str(
                school_id
            ),
            "entity_type": str(
                entity_type
            ),
            "entity_key": str(
                entity_key
            ),
        },
        {
            "$set": document,
            "$setOnInsert": {
                "record_id": (
                    document.get(
                        "record_id"
                    )
                    or record_doc(
                        school_id,
                        entity_type,
                        entity_key,
                        safe_payload,
                    )[
                        "record_id"
                    ]
                )
            },
        },
        upsert=True,
    )

    result = ledger_collection.find_one(
        {
            "school_id": str(
                school_id
            ),
            "entity_type": str(
                entity_type
            ),
            "entity_key": str(
                entity_key
            ),
        }
    )

    return (
        dict(result)
        if result
        else document
    )


# =========================================================
# CONFLICT LEDGER
# =========================================================

def _open_conflict(
    school_id: str,
    entity_type: str,
    entity_key: str,
    local: Mapping[str, Any],
    cloud: Mapping[str, Any],
    base: Optional[
        Mapping[str, Any]
    ],
    *,
    source: str,
    connection_id: Any = None,
    job_id: Any = None,
    strategy: str = DEFAULT_CONFLICT_STRATEGY,
    fields: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Create one open conflict per logical record rather than generating
    duplicate conflict rows on every retry.
    """
    conflicts = collection(
        CONFLICTS
    )

    query = {
        "school_id": str(
            school_id
        ),
        "entity_type": str(
            entity_type
        ),
        "entity_key": str(
            entity_key
        ),
        "status": "open",
    }

    existing = conflicts.find_one(
        query
    )

    field_diffs = [
        {
            "field": field,
        }
        for field in (
            fields or []
        )
    ]

    payload = {
        "source": {
            "source": _text(
                source
            )
            or "desktop",
        },
        "strategy": strategy,
        "field_diffs": field_diffs,
    }

    if existing:
        conflicts.update_one(
            {
                "_id": existing[
                    "_id"
                ]
            },
            {
                "$set": {
                    "local_record": deepcopy(
                        dict(local)
                    ),
                    "cloud_record": deepcopy(
                        dict(cloud)
                    ),
                    "base_record": (
                        deepcopy(
                            dict(base)
                        )
                        if isinstance(
                            base,
                            Mapping,
                        )
                        else None
                    ),
                    "field_diffs": field_diffs,
                    "source": payload[
                        "source"
                    ],
                    "strategy": strategy,
                    "connection_id": (
                        _text(
                            connection_id
                        )
                        or existing.get(
                            "connection_id"
                        )
                    ),
                    "job_id": (
                        _text(
                            job_id
                        )
                        or existing.get(
                            "job_id"
                        )
                    ),
                    "updated_at": now_utc(),
                }
            },
        )

        refreshed = conflicts.find_one(
            {
                "_id": existing[
                    "_id"
                ]
            }
        )

        return (
            dict(refreshed)
            if refreshed
            else dict(existing)
        )

    document = conflict_doc(
        school_id,
        entity_type,
        entity_key,
        local,
        cloud,
        base,
        source=payload[
            "source"
        ],
        connection_id=connection_id,
        job_id=job_id,
        field_diffs=field_diffs,
        strategy=strategy,
    )

    result = conflicts.insert_one(
        document
    )

    document[
        "_id"
    ] = result.inserted_id

    return document


# =========================================================
# APPLY ONE DECISION
# =========================================================

def _apply_decision(
    school_id: str,
    entity_type: str,
    entity_key: str,
    status: str,
    local: Mapping[str, Any],
    cloud: Optional[
        Mapping[str, Any]
    ],
    decision_record: Optional[
        Mapping[str, Any]
    ],
    *,
    source: str,
    delete_mode: str,
    connection_id: Any = None,
    base_revision: Optional[int] = None,
) -> dict[str, Any]:
    """
    Apply a resolved synchronization decision to the authoritative
    collection and then update the ledger.
    """
    ledger = _ledger_find(
        school_id,
        entity_type,
        entity_key,
    )

    next_revision = _ledger_revision(
        ledger,
        cloud,
    )

    # -----------------------------------------------------
    # IGNORE DELETE POLICY
    # -----------------------------------------------------

    if (
        status in {
            "local_deleted",
            "delete_conflict",
        }
        and delete_mode == "ignore"
    ):
        payload = (
            comparable_record(
                local
            )
            if status
            == "local_deleted"
            else (
                comparable_record(
                    cloud or {}
                )
            )
        )

        ledger_document = _ledger_upsert(
            school_id,
            entity_type,
            entity_key,
            payload,
            source=source,
            operation="delete"
            if status
            == "local_deleted"
            else "upsert",
            revision=next_revision,
            connection_id=connection_id,
            base_revision=base_revision,
            deleted=(
                status
                == "local_deleted"
            ),
            state="ignored",
        )

        return {
            "status": "ignored",
            "record": ledger_document,
        }

    # -----------------------------------------------------
    # LOCAL DELETE
    # -----------------------------------------------------

    if status == "local_deleted":
        tombstoned = _tombstone_authoritative(
            school_id,
            entity_type,
            local,
            cloud,
        )

        payload = (
            comparable_record(
                tombstoned
                or local
            )
        )

        ledger_document = _ledger_upsert(
            school_id,
            entity_type,
            entity_key,
            payload,
            source=source,
            operation="delete",
            revision=next_revision,
            connection_id=connection_id,
            base_revision=base_revision,
            deleted=True,
            state="synced",
            source_record_id=(
                (tombstoned or {}).get(
                    "_id"
                )
                if tombstoned
                else local.get(
                    "_id"
                )
            ),
        )

        return {
            "status": "deleted",
            "record": ledger_document,
            "authoritative_record": tombstoned,
        }

    # -----------------------------------------------------
    # CLOUD DELETE
    # -----------------------------------------------------

    if status == "cloud_deleted":
        cloud_payload = (
            comparable_record(
                cloud or {}
            )
        )

        ledger_document = _ledger_upsert(
            school_id,
            entity_type,
            entity_key,
            cloud_payload,
            source="cloud",
            operation="delete",
            revision=(
                _safe_int(
                    ledger.get(
                        "revision"
                    ),
                    1,
                )
                if ledger
                else 1
            ),
            connection_id=connection_id,
            deleted=True,
            state="synced",
            source_record_id=(
                (cloud or {}).get(
                    "_id"
                )
            ),
        )

        return {
            "status": "cloud_deleted",
            "record": ledger_document,
            "authoritative_record": (
                dict(cloud)
                if cloud
                else None
            ),
        }

    # -----------------------------------------------------
    # NORMAL WRITE
    # -----------------------------------------------------

    if decision_record is None:
        raise ValueError(
            "A synchronization decision requires a record."
        )

    authoritative = _write_authoritative(
        school_id,
        entity_type,
        decision_record,
        cloud,
    )

    payload = comparable_record(
        authoritative
    )

    ledger_document = _ledger_upsert(
        school_id,
        entity_type,
        entity_key,
        payload,
        source=source,
        operation="upsert",
        revision=next_revision,
        connection_id=connection_id,
        base_revision=base_revision,
        cloud_revision=(
            record_revision(
                authoritative
            )
        ),
        deleted=is_deleted_record(
            authoritative
        ),
        state="synced",
        source_record_id=authoritative.get(
            "_id"
        ),
    )

    return {
        "status": (
            "created"
            if cloud is None
            else (
                "updated"
                if status
                in {
                    "new_local",
                    "local_newer",
                    "merged",
                }
                else status
            )
        ),
        "record": ledger_document,
        "authoritative_record": authoritative,
    }


# =========================================================
# ONE RECORD RECONCILIATION
# =========================================================

def reconcile_one(
    school_id: Any,
    entity_type: str,
    raw_record: Mapping[str, Any],
    *,
    base_record: Optional[
        Mapping[str, Any]
    ] = None,
    source: str = "desktop",
    field_mappings: Optional[
        Mapping[str, Any]
    ] = None,
    excluded_fields: Optional[
        list[str]
    ] = None,
    conflict_strategy: str = DEFAULT_CONFLICT_STRATEGY,
    delete_mode: str = DEFAULT_DELETE_MODE,
    connection_id: Any = None,
    job_id: Any = None,
) -> dict[str, Any]:
    """
    Reconcile one incoming local record against the authoritative
    Elimu cloud record.
    """
    sid = _school_id(
        school_id
    )

    canonical = _entity(
        entity_type
    )

    local = canonical_record(
        canonical,
        raw_record,
        source,
        field_mappings=field_mappings,
        excluded_fields=excluded_fields,
        school_id=sid,
    )

    key = identity_key(
        canonical,
        local,
    )

    cloud = find_authoritative(
        sid,
        canonical,
        local,
    )

    base = (
        deepcopy(
            dict(base_record)
        )
        if isinstance(
            base_record,
            Mapping,
        )
        else None
    )

    comparison = compare(
        local,
        cloud,
        base,
        entity_type=canonical,
    )

    status = comparison.get(
        "status",
        "conflict",
    )

    # -----------------------------------------------------
    # DIRECT SUCCESS STATES
    # -----------------------------------------------------

    if status == "identical":
        cloud_payload = comparable_record(
            cloud or local
        )

        ledger = _ledger_find(
            sid,
            canonical,
            key,
        )

        revision = (
            _safe_int(
                ledger.get(
                    "revision"
                ),
                1,
            )
            if ledger
            else 1
        )

        ledger_document = _ledger_upsert(
            sid,
            canonical,
            key,
            cloud_payload,
            source="cloud",
            operation="upsert",
            revision=revision,
            connection_id=connection_id,
            deleted=is_deleted_record(
                cloud or {}
            ),
            state="synced",
            source_record_id=(
                (cloud or {}).get(
                    "_id"
                )
            ),
        )

        return {
            "entity_type": canonical,
            "entity_key": key,
            "status": "identical",
            "changed": False,
            "record": ledger_document,
            "authoritative_record": cloud,
        }

    # -----------------------------------------------------
    # CLOUD NEWER
    # -----------------------------------------------------

    if status == "cloud_newer":
        cloud_payload = comparable_record(
            cloud or {}
        )

        ledger = _ledger_find(
            sid,
            canonical,
            key,
        )

        revision = (
            _safe_int(
                ledger.get(
                    "revision"
                ),
                1,
            )
            if ledger
            else 1
        )

        ledger_document = _ledger_upsert(
            sid,
            canonical,
            key,
            cloud_payload,
            source="cloud",
            operation="upsert",
            revision=revision,
            connection_id=connection_id,
            cloud_revision=record_revision(
                cloud or {}
            ),
            deleted=is_deleted_record(
                cloud or {}
            ),
            state="synced",
            source_record_id=(
                (cloud or {}).get(
                    "_id"
                )
            ),
        )

        return {
            "entity_type": canonical,
            "entity_key": key,
            "status": "cloud_newer",
            "changed": False,
            "record": ledger_document,
            "authoritative_record": cloud,
        }

    # -----------------------------------------------------
    # CLOUD DELETED
    # -----------------------------------------------------

    if status == "cloud_deleted":
        result = _apply_decision(
            sid,
            canonical,
            key,
            "cloud_deleted",
            local,
            cloud,
            cloud,
            source=source,
            delete_mode=delete_mode,
            connection_id=connection_id,
        )

        return {
            "entity_type": canonical,
            "entity_key": key,
            "status": "cloud_deleted",
            "changed": False,
            **result,
        }

    # -----------------------------------------------------
    # AUTOMATICALLY MERGED
    # -----------------------------------------------------

    if status == "merged":
        result = _apply_decision(
            sid,
            canonical,
            key,
            "merged",
            local,
            cloud,
            comparison.get(
                "record"
            ),
            source=source,
            delete_mode=delete_mode,
            connection_id=connection_id,
            base_revision=(
                record_revision(
                    base
                )
                if base
                else None
            ),
        )

        return {
            "entity_type": canonical,
            "entity_key": key,
            "status": "merged",
            "changed": True,
            "fields": comparison.get(
                "fields",
                [],
            ),
            **result,
        }

    # -----------------------------------------------------
    # LOCAL NEW / LOCAL NEWER
    # -----------------------------------------------------

    if status in {
        "new_local",
        "local_newer",
    }:
        result = _apply_decision(
            sid,
            canonical,
            key,
            status,
            local,
            cloud,
            comparison.get(
                "record"
            )
            or local,
            source=source,
            delete_mode=delete_mode,
            connection_id=connection_id,
            base_revision=(
                record_revision(
                    base
                )
                if base
                else None
            ),
        )

        return {
            "entity_type": canonical,
            "entity_key": key,
            "status": status,
            "changed": True,
            "fields": changed_fields(
                cloud or {},
                local,
            ),
            **result,
        }

    # -----------------------------------------------------
    # LOCAL DELETE
    # -----------------------------------------------------

    if status == "local_deleted":
        result = _apply_decision(
            sid,
            canonical,
            key,
            "local_deleted",
            local,
            cloud,
            local,
            source=source,
            delete_mode=delete_mode,
            connection_id=connection_id,
            base_revision=(
                record_revision(
                    base
                )
                if base
                else None
            ),
        )

        return {
            "entity_type": canonical,
            "entity_key": key,
            "status": (
                "ignored"
                if result[
                    "status"
                ]
                == "ignored"
                else "deleted"
            ),
            "changed": (
                result[
                    "status"
                ]
                != "ignored"
            ),
            **result,
        }

    # -----------------------------------------------------
    # CONFLICT / DELETE CONFLICT
    # -----------------------------------------------------

    conflict_fields = comparison.get(
        "fields",
        [],
    )

    # Apply school policy first.
    policy_result = resolve_by_strategy(
        conflict_strategy,
        local,
        cloud or {},
        base=base,
    )

    if policy_result.get(
        "resolved"
    ):
        resolved_record = policy_result.get(
            "record"
        )

        decision = policy_result.get(
            "decision",
            "manual",
        )

        resolved_status = (
            "local_newer"
            if decision
            == "keep_local"
            else "cloud_newer"
            if decision
            == "keep_cloud"
            else "merged"
        )

        # For cloud_wins, no authoritative write is required because
        # cloud is already the authoritative state.
        if decision == "keep_cloud":
            cloud_payload = comparable_record(
                cloud or {}
            )

            ledger = _ledger_find(
                sid,
                canonical,
                key,
            )

            revision = (
                _safe_int(
                    ledger.get(
                        "revision"
                    ),
                    1,
                )
                if ledger
                else 1
            )

            ledger_document = _ledger_upsert(
                sid,
                canonical,
                key,
                cloud_payload,
                source="cloud",
                operation="upsert",
                revision=revision,
                connection_id=connection_id,
                state="synced",
                source_record_id=(
                    (cloud or {}).get(
                        "_id"
                    )
                ),
            )

            return {
                "entity_type": canonical,
                "entity_key": key,
                "status": "cloud_wins",
                "changed": False,
                "fields": conflict_fields,
                "record": ledger_document,
                "authoritative_record": cloud,
            }

        result = _apply_decision(
            sid,
            canonical,
            key,
            resolved_status,
            local,
            cloud,
            resolved_record,
            source=source,
            delete_mode=delete_mode,
            connection_id=connection_id,
            base_revision=(
                record_revision(
                    base
                )
                if base
                else None
            ),
        )

        return {
            "entity_type": canonical,
            "entity_key": key,
            "status": (
                "local_wins"
                if decision
                == "keep_local"
                else "merged"
            ),
            "changed": True,
            "fields": conflict_fields,
            **result,
        }

    # -----------------------------------------------------
    # MANUAL CONFLICT
    # -----------------------------------------------------

    conflict = _open_conflict(
        sid,
        canonical,
        key,
        local,
        cloud or {},
        base,
        source=source,
        connection_id=connection_id,
        job_id=job_id,
        strategy=conflict_strategy,
        fields=list(
            conflict_fields
        ),
    )

    # Keep the current cloud snapshot in the ledger so a subsequent
    # resolution has an accurate cloud baseline.
    cloud_payload = comparable_record(
        cloud or {}
    )

    ledger = _ledger_find(
        sid,
        canonical,
        key,
    )

    revision = (
        _safe_int(
            ledger.get(
                "revision"
            ),
            1,
        )
        if ledger
        else 1
    )

    ledger_document = _ledger_upsert(
        sid,
        canonical,
        key,
        cloud_payload,
        source="cloud",
        operation="upsert",
        revision=revision,
        connection_id=connection_id,
        state="conflict",
        source_record_id=(
            (cloud or {}).get(
                "_id"
            )
        ),
    )

    return {
        "entity_type": canonical,
        "entity_key": key,
        "status": (
            "delete_conflict"
            if status
            == "delete_conflict"
            else "conflict"
        ),
        "changed": False,
        "fields": conflict_fields,
        "conflict": conflict,
        "record": ledger_document,
        "authoritative_record": cloud,
    }


# =========================================================
# BASE RECORD MAP
# =========================================================

def _base_for_key(
    base_records: Any,
    key: str,
) -> Optional[
    Mapping[str, Any]
]:
    if not isinstance(
        base_records,
        Mapping,
    ):
        return None

    value = base_records.get(
        key
    )

    if isinstance(
        value,
        Mapping,
    ):
        return value

    return None


# =========================================================
# PUBLIC RECONCILIATION API
# =========================================================

def reconcile(
    school_id: Any,
    entity_type: str,
    records: Any,
    base_records: Optional[
        Mapping[str, Mapping[str, Any]]
    ] = None,
    source: str = "desktop",
    *,
    field_mappings: Optional[
        Mapping[str, Any]
    ] = None,
    excluded_fields: Optional[
        list[str]
    ] = None,
    conflict_strategy: str = DEFAULT_CONFLICT_STRATEGY,
    delete_mode: str = DEFAULT_DELETE_MODE,
    connection_id: Any = None,
    job_id: Any = None,
) -> dict[str, Any]:
    """
    Reconcile a batch of client records.

    Backward-compatible call:

        reconcile(
            school_id,
            entity_type,
            records,
            base_records=None,
            source="desktop",
        )

    Enhanced call supports:

        field_mappings
        excluded_fields
        conflict_strategy
        delete_mode
        connection_id
        job_id
    """
    sid = _school_id(
        school_id
    )

    canonical = _entity(
        entity_type
    )

    if not isinstance(
        records,
        list,
    ):
        raise ValueError(
            "records must be a list."
        )

    # Subjects are a logical/virtual entity in current Elimu and cannot
    # be persisted as a standalone collection.
    entity_collection(
        canonical
    )

    if (
        conflict_strategy
        not in {
            "manual",
            "cloud_wins",
            "local_wins",
            "latest_write",
            "base_merge",
        }
    ):
        conflict_strategy = (
            DEFAULT_CONFLICT_STRATEGY
        )

    if delete_mode not in {
        "tombstone",
        "ignore",
    }:
        delete_mode = (
            DEFAULT_DELETE_MODE
        )

    results: dict[str, Any] = {
        "school_id": sid,
        "entity_type": canonical,
        "source": _text(
            source
        )
        or "desktop",

        "total": len(
            records
        ),

        "created": 0,
        "updated": 0,
        "deleted": 0,
        "merged": 0,
        "unchanged": 0,
        "conflicts": 0,
        "ignored": 0,
        "errors": 0,

        "items": [],
    }

    for index, raw in enumerate(
        records
    ):
        if not isinstance(
            raw,
            Mapping,
        ):
            results[
                "errors"
            ] += 1

            results[
                "items"
            ].append(
                {
                    "index": index,
                    "status": "error",
                    "error": (
                        "Record must be a JSON object."
                    ),
                }
            )

            continue

        try:
            # We need the canonical identity before reconcile_one so the
            # base snapshot can be selected.
            prepared = canonical_record(
                canonical,
                raw,
                source,
                field_mappings=field_mappings,
                excluded_fields=excluded_fields,
                school_id=sid,
            )

            key = identity_key(
                canonical,
                prepared,
            )

            base = _base_for_key(
                base_records,
                key,
            )

            item = reconcile_one(
                sid,
                canonical,
                prepared,
                base_record=base,
                source=source,
                field_mappings=None,
                excluded_fields=None,
                conflict_strategy=conflict_strategy,
                delete_mode=delete_mode,
                connection_id=connection_id,
                job_id=job_id,
            )

            item_status = item.get(
                "status"
            )

            if item_status == "created":
                results[
                    "created"
                ] += 1

            elif item_status in {
                "updated",
                "local_newer",
                "local_wins",
            }:
                results[
                    "updated"
                ] += 1

            elif item_status == "merged":
                results[
                    "merged"
                ] += 1

            elif item_status in {
                "deleted",
                "local_deleted",
            }:
                results[
                    "deleted"
                ] += 1

            elif item_status in {
                "identical",
                "cloud_newer",
                "cloud_deleted",
            }:
                results[
                    "unchanged"
                ] += 1

            elif item_status == "ignored":
                results[
                    "ignored"
                ] += 1

            elif item_status in {
                "conflict",
                "delete_conflict",
            }:
                results[
                    "conflicts"
                ] += 1

            else:
                # Defensive fallback.
                results[
                    "unchanged"
                ] += 1

            results[
                "items"
            ].append(
                {
                    "index": index,
                    "entity_key": key,
                    **{
                        field: value
                        for field, value
                        in item.items()
                        if field in {
                            "status",
                            "changed",
                            "fields",
                        }
                    },
                }
            )

        except Exception as exc:
            results[
                "errors"
            ] += 1

            # Attempt to recover the logical key for diagnostics.
            try:
                diagnostic_key = identity_key(
                    canonical,
                    raw,
                )
            except Exception:
                diagnostic_key = None

            results[
                "items"
            ].append(
                {
                    "index": index,
                    "entity_key": diagnostic_key,
                    "status": "error",
                    "error": str(
                        exc
                    ),
                }
            )

    results[
        "successful"
    ] = (
        results[
            "created"
        ]
        + results[
            "updated"
        ]
        + results[
            "deleted"
        ]
        + results[
            "merged"
        ]
        + results[
            "unchanged"
        ]
        + results[
            "ignored"
        ]
    )

    results[
        "failed"
    ] = results[
        "errors"
    ]

    results[
        "completed"
    ] = (
        results[
            "errors"
        ] == 0
    )

    return results


# =========================================================
# CONFLICT RESOLUTION HELPERS
# =========================================================

def resolve_conflict_record(
    school_id: Any,
    conflict: Mapping[str, Any],
    *,
    decision: str,
    merged_record: Optional[
        Mapping[str, Any]
    ] = None,
    connection_id: Any = None,
) -> dict[str, Any]:
    """
    Apply a manually resolved conflict to the authoritative Elimu
    collection and update both the conflict and sync ledgers.

    This function is intentionally separate from reconcile() because
    conflict resolution is an explicit administrative action.
    """
    sid = _school_id(
        school_id
    )

    if not isinstance(
        conflict,
        Mapping,
    ):
        raise ValueError(
            "Conflict document is required."
        )

    entity_type = _entity(
        conflict.get(
            "entity_type"
        )
    )

    entity_key = _text(
        conflict.get(
            "entity_key"
        )
    )

    if not entity_key:
        raise ValueError(
            "Conflict entity_key is required."
        )

    local = _mapping(
        conflict.get(
            "local_record"
        )
    )

    cloud = _mapping(
        conflict.get(
            "cloud_record"
        )
    )

    base = _mapping(
        conflict.get(
            "base_record"
        )
    )

    decision_name = (
        _text(
            decision
        )
        .lower()
    )

    if decision_name == "merge":
        if not isinstance(
            merged_record,
            Mapping,
        ):
            raise ValueError(
                "merged_record is required for merge resolution."
            )

        resolved = deepcopy(
            dict(
                merged_record
            )
        )

    elif decision_name == "keep_local":
        resolved = deepcopy(
            local
        )

    elif decision_name == "keep_cloud":
        resolved = deepcopy(
            cloud
        )

    else:
        raise ValueError(
            "Unsupported conflict resolution decision."
        )

    key_check = identity_key(
        entity_type,
        resolved,
    )

    if key_check != entity_key:
        raise ValueError(
            "Resolved record identity does not match the conflict."
        )

    # Cloud-wins does not need a domain write because cloud is already
    # authoritative, but the ledger/conflict must still be resolved.
    existing = find_authoritative(
        sid,
        entity_type,
        resolved,
    )

    if decision_name == "keep_cloud":
        authoritative = (
            existing
            or cloud
        )
    else:
        authoritative = _write_authoritative(
            sid,
            entity_type,
            resolved,
            existing,
        )

    ledger = _ledger_find(
        sid,
        entity_type,
        entity_key,
    )

    next_revision = _ledger_revision(
        ledger,
        authoritative,
    )

    ledger_document = _ledger_upsert(
        sid,
        entity_type,
        entity_key,
        comparable_record(
            authoritative
        ),
        source=(
            "cloud"
            if decision_name
            == "keep_cloud"
            else "manual"
        ),
        operation="upsert",
        revision=next_revision,
        connection_id=connection_id,
        deleted=is_deleted_record(
            authoritative
        ),
        state="synced",
        source_record_id=(
            authoritative.get(
                "_id"
            )
            if isinstance(
                authoritative,
                Mapping,
            )
            else None
        ),
    )

    conflict_id = conflict.get(
        "conflict_id"
    )

    conflicts = collection(
        CONFLICTS
    )

    conflict_query: dict[str, Any]

    if conflict.get(
        "_id"
    ) is not None:
        conflict_query = {
            "_id": conflict[
                "_id"
            ],
            "school_id": sid,
        }
    elif conflict_id:
        conflict_query = {
            "conflict_id": str(
                conflict_id
            ),
            "school_id": sid,
        }
    else:
        conflict_query = {
            "school_id": sid,
            "entity_type": entity_type,
            "entity_key": entity_key,
            "status": "open",
        }

    resolution_payload = {
        "decision": decision_name,
        "resolved_record": comparable_record(
            authoritative
        ),
        "resolved_at": now_utc(),
    }

    conflicts.update_one(
        conflict_query,
        {
            "$set": {
                "status": "resolved",
                "resolution": resolution_payload,
                "resolved_record": comparable_record(
                    authoritative
                ),
                "resolved_at": now_utc(),
                "updated_at": now_utc(),
            }
        },
    )

    refreshed_conflict = conflicts.find_one(
        conflict_query
    )

    return {
        "resolved": True,
        "school_id": sid,
        "entity_type": entity_type,
        "entity_key": entity_key,
        "decision": decision_name,
        "authoritative_record": authoritative,
        "ledger_record": ledger_document,
        "conflict": (
            dict(
                refreshed_conflict
            )
            if refreshed_conflict
            else None
        ),
        "base_record": base or None,
    }


# =========================================================
# BATCH RECONCILIATION ALIAS
# =========================================================

def reconcile_records(
    school_id: Any,
    entity_type: str,
    records: list[Mapping[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Explicit alias for callers that prefer a verbose method name.
    """
    return reconcile(
        school_id,
        entity_type,
        records,
        **kwargs,
    )