# backend/jumuiya/elimu/sync/models.py

from __future__ import annotations

"""
Elimu Sync persistent data models.

Purpose
-------
This module defines the canonical persistence contract for the Elimu
offline-first synchronization subsystem.

Architecture
------------

                Elimu Cloud
                     |
        +------------+-------------+
        |                          |
   Authoritative              Sync Ledger
   Domain Data                / Audit State
        |                          |
        +------------+-------------+
                     |
               Sync Engine
                     |
        +------------+-------------+
        |                          |
     Desktop                    Android
     School PC                  School Device
        |
     Legacy/Imported Data

Design goals
------------
- Multiple school devices and connections.
- Secure connection credentials.
- Bidirectional synchronization.
- Incremental synchronization.
- Resumable jobs and checkpoints.
- Record-level revisions.
- Deterministic record identity.
- Checksums/change detection.
- Tombstones for offline deletes.
- Auditable conflicts.
- School-adjustable sync policies.
- Legacy/custom field mappings.
- Schema/version compatibility.
- Safe metadata/extensions.

This file does NOT perform database writes.
Persistence belongs to services.py / engine.py.
"""


from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)


# =========================================================
# COLLECTIONS
# =========================================================

CONNECTIONS = "jumuiya_elimu_sync_connections"
DEVICES = "jumuiya_elimu_sync_devices"
JOBS = "jumuiya_elimu_sync_jobs"
RECORDS = "jumuiya_elimu_sync_records"
CONFLICTS = "jumuiya_elimu_sync_conflicts"


# =========================================================
# MODEL / PROTOCOL VERSION
# =========================================================

SYNC_MODEL_VERSION = "2.0"
DEFAULT_PROTOCOL_VERSION = "2.0"


# =========================================================
# SECURITY DEFAULTS
# =========================================================

DEFAULT_CONNECTION_TOKEN_DAYS = 365

MIN_CONNECTION_TOKEN_DAYS = 1
MAX_CONNECTION_TOKEN_DAYS = 3650


# =========================================================
# SYNC LIMITS
# =========================================================

DEFAULT_BATCH_SIZE = 250

MIN_BATCH_SIZE = 25

MAX_BATCH_SIZE = 5000

DEFAULT_SYNC_INTERVAL_SECONDS = 300

MIN_SYNC_INTERVAL_SECONDS = 30

MAX_SYNC_INTERVAL_SECONDS = (
    7 * 24 * 60 * 60
)

DEFAULT_MAX_RETRIES = 5

MAX_MAX_RETRIES = 20

MAX_ENTITY_TYPES = 500

MAX_EXCLUDED_FIELDS = 500

MAX_CAPABILITIES = 100


# =========================================================
# ENUM-LIKE CONSTANTS
# =========================================================

CONNECTION_STATUSES = {
    "pending",
    "active",
    "paused",
    "revoked",
    "expired",
    "error",
}


DEVICE_STATUSES = {
    "active",
    "inactive",
    "blocked",
    "revoked",
}


PLATFORMS = {
    "desktop",
    "windows",
    "macos",
    "linux",
    "android",
    "web",
    "api",
    "legacy",
    "other",
}


JOB_KINDS = {
    "full_sync",
    "incremental_sync",
    "push",
    "pull",
    "import",
    "export",
    "reconcile",
    "repair",
}


JOB_STATUSES = {
    "queued",
    "running",
    "paused",
    "completed",
    "completed_with_errors",
    "failed",
    "cancelled",
}


SYNC_DIRECTIONS = {
    "bidirectional",
    "upload",
    "download",
}


CONFLICT_STRATEGIES = {
    "manual",
    "cloud_wins",
    "local_wins",
    "latest_write",
    "base_merge",
}


DELETE_MODES = {
    "tombstone",
    "ignore",
}


TRIGGER_TYPES = {
    "manual",
    "startup",
    "scheduled",
    "reconnect",
    "import",
    "repair",
    "api",
}


RECORD_OPERATIONS = {
    "upsert",
    "delete",
}


RECORD_SYNC_STATES = {
    "pending",
    "syncing",
    "synced",
    "conflict",
    "error",
    "ignored",
}


CONFLICT_STATUSES = {
    "open",
    "in_review",
    "resolved",
    "ignored",
    "expired",
}


# =========================================================
# CANONICAL ELIMU ENTITY REGISTRY
# =========================================================
#
# Logical entity names are used throughout the protocol.
#
# They MUST NOT be replaced with Mongo collection names in
# client payloads.
#
# mapper.py is responsible for resolving these logical names
# to actual Elimu collections.
#
# =========================================================

DEFAULT_ENTITY_TYPES = [
    "school",
    "profile",
    "staff",
    "teacher_assignments",
    "classes",
    "students",
    "subjects",
    "lessons",
    "assignments",
    "attendance",
    "assessments",
    "fees",
    "cbc_projects",
    "events",
    "timetables",
    "timetable_entries",
]


# =========================================================
# TIME / BASIC HELPERS
# =========================================================

def now_utc() -> datetime:
    return datetime.now(
        timezone.utc
    )


def ensure_utc(
    value: Optional[datetime],
) -> Optional[datetime]:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(
        value
    ).strip()


def _lower(
    value: Any,
    default: str = "",
) -> str:
    return _text(
        value,
        default,
    ).lower()


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


def _safe_bool(
    value: Any,
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
        (int, float),
    ):
        return bool(
            value
        )

    normalized = _lower(
        value
    )

    if normalized in {
        "true",
        "1",
        "yes",
        "on",
        "y",
    }:
        return True

    if normalized in {
        "false",
        "0",
        "no",
        "off",
        "n",
    }:
        return False

    return default


def _string_list(
    value: Any,
    *,
    lower: bool = False,
    unique: bool = True,
    maximum: Optional[int] = None,
) -> List[str]:
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

    result: List[str] = []

    seen = set()

    for item in value:
        normalized = (
            _lower(item)
            if lower
            else _text(item)
        )

        if not normalized:
            continue

        key = (
            normalized.lower()
            if not lower
            else normalized
        )

        if (
            unique
            and key in seen
        ):
            continue

        seen.add(
            key
        )

        result.append(
            normalized
        )

        if (
            maximum is not None
            and len(result) >= maximum
        ):
            break

    return result


def _dict(
    value: Any,
) -> Dict[str, Any]:
    if not isinstance(
        value,
        Mapping,
    ):
        return {}

    return deepcopy(
        dict(value)
    )


def _bounded_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    result = _safe_int(
        value,
        default,
    )

    return max(
        minimum,
        min(
            result,
            maximum,
        ),
    )


# =========================================================
# CONNECTION TOKEN SECURITY
# =========================================================

def connection_token() -> str:
    """
    Generate a high-entropy connection credential.

    The raw token must only be returned once to the trusted
    provisioning layer.
    """
    return secrets.token_urlsafe(
        32
    )


def hash_connection_token(
    raw_token: str,
) -> str:
    """
    Return the only token representation that should be persisted.
    """

    value = _text(
        raw_token
    )

    if not value:
        raise ValueError(
            "Connection token is required."
        )

    return hashlib.sha256(
        value.encode(
            "utf-8"
        )
    ).hexdigest()


def verify_connection_token(
    raw_token: str,
    token_hash: str,
) -> bool:
    """
    Constant-time connection credential verification.
    """

    if not _text(
        raw_token
    ):
        return False

    if not _text(
        token_hash
    ):
        return False

    expected = hash_connection_token(
        raw_token
    )

    return hmac.compare_digest(
        expected,
        _text(token_hash),
    )


def token_expires_at(
    days: int = DEFAULT_CONNECTION_TOKEN_DAYS,
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
            "Connection token expiry must be a whole number of days."
        )

    if (
        days < MIN_CONNECTION_TOKEN_DAYS
        or days > MAX_CONNECTION_TOKEN_DAYS
    ):
        raise ValueError(
            "Connection token expiry is outside the allowed range."
        )

    return (
        now_utc()
        + timedelta(
            days=days
        )
    )


# =========================================================
# CHECKSUM / CANONICALIZATION
# =========================================================

def _canonicalize(
    value: Any,
) -> Any:
    """
    Convert supported values into deterministic JSON-safe data.
    """

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(key): _canonicalize(
                value[key]
            )
            for key in sorted(
                value,
                key=lambda item: str(item),
            )
        }

    if isinstance(
        value,
        (list, tuple),
    ):
        return [
            _canonicalize(item)
            for item in value
        ]

    if isinstance(
        value,
        datetime,
    ):
        normalized = ensure_utc(
            value
        )

        return normalized.isoformat()

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if value is None:
        return None

    return str(
        value
    )


def payload_checksum(
    payload: Any,
) -> str:
    """
    Deterministic SHA-256 checksum.

    Used for:
        - change detection
        - deduplication
        - transfer verification
        - corruption detection
    """

    canonical = _canonicalize(
        payload
    )

    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        encoded
    ).hexdigest()


# =========================================================
# ENTITY NORMALIZATION
# =========================================================

def normalize_entity_type(
    value: Any,
) -> str:
    entity = _lower(
        value
    )

    if not entity:
        raise ValueError(
            "entity_type is required."
        )

    if (
        entity != "*"
        and entity not in DEFAULT_ENTITY_TYPES
    ):
        raise ValueError(
            f"Unsupported Elimu sync entity type: {entity}."
        )

    return entity


def normalize_entity_types(
    entity_types: Any,
) -> List[str]:
    values = _string_list(
        entity_types,
        lower=True,
        maximum=MAX_ENTITY_TYPES,
    )

    if not values:
        return list(
            DEFAULT_ENTITY_TYPES
        )

    if "*" in values:
        return [
            "*"
        ]

    unknown = [
        value
        for value in values
        if value not in DEFAULT_ENTITY_TYPES
    ]

    if unknown:
        raise ValueError(
            "Unsupported Elimu sync entity type."
        )

    return values


# =========================================================
# SCHOOL-ADJUSTABLE SYNC POLICY
# =========================================================

def sync_policy_doc(
    policy: Optional[
        Mapping[str, Any]
    ] = None,
) -> Dict[str, Any]:
    """
    Normalize synchronization controls that each school may adjust.

    The client does not get to redefine protocol semantics.
    Policy only chooses allowed operating behaviour.
    """

    source = dict(
        policy or {}
    )

    direction = _lower(
        source.get(
            "direction"
        ),
        "bidirectional",
    )

    if direction not in SYNC_DIRECTIONS:
        direction = "bidirectional"

    conflict_strategy = _lower(
        source.get(
            "conflict_strategy"
        ),
        "manual",
    )

    if (
        conflict_strategy
        not in CONFLICT_STRATEGIES
    ):
        conflict_strategy = "manual"

    delete_mode = _lower(
        source.get(
            "delete_mode"
        ),
        "tombstone",
    )

    if delete_mode not in DELETE_MODES:
        delete_mode = "tombstone"

    trigger = _lower(
        source.get(
            "default_trigger"
        ),
        "manual",
    )

    if trigger not in TRIGGER_TYPES:
        trigger = "manual"

    entity_types = normalize_entity_types(
        source.get(
            "entity_types",
            DEFAULT_ENTITY_TYPES,
        )
    )

    excluded_fields = _string_list(
        source.get(
            "excluded_fields"
        ),
        maximum=MAX_EXCLUDED_FIELDS,
    )

    return {
        "enabled": _safe_bool(
            source.get(
                "enabled"
            ),
            True,
        ),

        "auto_sync": _safe_bool(
            source.get(
                "auto_sync"
            ),
            True,
        ),

        "direction": direction,

        "conflict_strategy": (
            conflict_strategy
        ),

        "delete_mode": delete_mode,

        "default_trigger": trigger,

        "pull_before_push": _safe_bool(
            source.get(
                "pull_before_push"
            ),
            True,
        ),

        "continue_on_error": _safe_bool(
            source.get(
                "continue_on_error"
            ),
            True,
        ),

        "preserve_local_custom_fields": _safe_bool(
            source.get(
                "preserve_local_custom_fields"
            ),
            True,
        ),

        "allow_cloud_schema_updates": _safe_bool(
            source.get(
                "allow_cloud_schema_updates"
            ),
            True,
        ),

        "batch_size": _bounded_int(
            source.get(
                "batch_size"
            ),
            default=DEFAULT_BATCH_SIZE,
            minimum=MIN_BATCH_SIZE,
            maximum=MAX_BATCH_SIZE,
        ),

        "sync_interval_seconds": _bounded_int(
            source.get(
                "sync_interval_seconds"
            ),
            default=DEFAULT_SYNC_INTERVAL_SECONDS,
            minimum=MIN_SYNC_INTERVAL_SECONDS,
            maximum=MAX_SYNC_INTERVAL_SECONDS,
        ),

        "max_retries": _bounded_int(
            source.get(
                "max_retries"
            ),
            default=DEFAULT_MAX_RETRIES,
            minimum=0,
            maximum=MAX_MAX_RETRIES,
        ),

        "entity_types": entity_types,

        "excluded_fields": excluded_fields,

        "metadata": _dict(
            source.get(
                "metadata"
            )
        ),
    }


# =========================================================
# FIELD MAPPINGS
# =========================================================

def field_mappings_doc(
    mappings: Optional[
        Mapping[str, Any]
    ] = None,
) -> Dict[str, Any]:
    """
    Normalize legacy/custom field mappings.

    Example:

        {
            "students": {
                "AdmissionNo": "admission_number",
                "StudentName": "name"
            }
        }
    """

    source = (
        mappings
        if isinstance(
            mappings,
            Mapping,
        )
        else {}
    )

    result: Dict[str, Any] = {}

    for entity_type, mapping in source.items():

        entity = _lower(
            entity_type
        )

        if (
            not entity
            or not isinstance(
                mapping,
                Mapping,
            )
        ):
            continue

        clean: Dict[str, str] = {}

        for (
            source_field,
            target_field,
        ) in mapping.items():

            source_name = _text(
                source_field
            )

            target_name = _text(
                target_field
            )

            if (
                not source_name
                or not target_name
            ):
                continue

            if (
                len(source_name) > 128
                or len(target_name) > 128
            ):
                continue

            clean[
                source_name
            ] = target_name

        if clean:
            result[
                entity
            ] = clean

    return result


# =========================================================
# CONNECTION DOCUMENT
# =========================================================

def connection_doc(
    school_id: Any,
    name: str,
    platform: str,
    created_by: Any,
    *,
    device_id: Any = None,
    client_version: str = "",
    protocol_version: str = DEFAULT_PROTOCOL_VERSION,
    capabilities: Optional[
        Iterable[Any]
    ] = None,
    policy: Optional[
        Mapping[str, Any]
    ] = None,
    field_mappings: Optional[
        Mapping[str, Any]
    ] = None,
    entity_types: Optional[
        Iterable[Any]
    ] = None,
    metadata: Optional[
        Mapping[str, Any]
    ] = None,
    token_days: int = DEFAULT_CONNECTION_TOKEN_DAYS,
) -> Tuple[
    Dict[str, Any],
    str,
]:
    """
    Build a secure school synchronization connection.

    Returns:

        (document, raw_token)

    Only token_hash is persisted.
    """

    school = _text(
        school_id
    )

    creator = _text(
        created_by
    )

    connection_name = _text(
        name
    )

    platform_name = _lower(
        platform
    )

    if not school:
        raise ValueError(
            "school_id is required."
        )

    if not creator:
        raise ValueError(
            "created_by is required."
        )

    if not connection_name:
        raise ValueError(
            "Connection name is required."
        )

    if platform_name not in PLATFORMS:
        raise ValueError(
            "Unsupported synchronization platform."
        )

    normalized_policy = sync_policy_doc(
        policy
    )

    if entity_types is not None:
        normalized_policy[
            "entity_types"
        ] = normalize_entity_types(
            entity_types
        )

    raw_token = connection_token()

    now = now_utc()

    expires_at = token_expires_at(
        token_days
    )

    connection_id = secrets.token_hex(
        16
    )

    return {
        "model_version": SYNC_MODEL_VERSION,

        "protocol_version": _text(
            protocol_version,
            DEFAULT_PROTOCOL_VERSION,
        ),

        "connection_id": connection_id,

        "school_id": school,

        "device_id": (
            _text(
                device_id
            )
            or None
        ),

        "name": connection_name,

        "platform": platform_name,

        "client_version": _text(
            client_version
        ),

        "status": "pending",

        "token_hash": hash_connection_token(
            raw_token
        ),

        "token_expires_at": expires_at,

        "capabilities": _string_list(
            capabilities,
            lower=True,
            maximum=MAX_CAPABILITIES,
        ),

        "entity_types": list(
            normalized_policy[
                "entity_types"
            ]
        ),

        "policy": normalized_policy,

        "field_mappings": field_mappings_doc(
            field_mappings
        ),

        "metadata": _dict(
            metadata
        ),

        # -------------------------------------------------
        # Lifecycle
        # -------------------------------------------------

        "created_by": creator,

        "created_at": now,

        "updated_at": now,

        "activated_at": None,

        "paused_at": None,

        "revoked_at": None,

        "last_seen_at": None,

        "last_sync_at": None,

        "last_sync_status": None,

        "last_sync_job_id": None,

        "last_error": None,

        # -------------------------------------------------
        # Incremental synchronization state
        # -------------------------------------------------

        "sync_cursor": None,

        "sync_revision": 0,

        "server_revision": 0,

        "client_revision": 0,

        "records_synced": 0,

        "records_failed": 0,

        "conflicts_open": 0,
    }, raw_token


# =========================================================
# DEVICE DOCUMENT
# =========================================================

def device_doc(
    school_id: Any,
    device_name: str,
    platform: str,
    created_by: Any,
    *,
    device_id: Optional[str] = None,
    client_version: str = "",
    protocol_version: str = DEFAULT_PROTOCOL_VERSION,
    capabilities: Optional[
        Iterable[Any]
    ] = None,
    metadata: Optional[
        Mapping[str, Any]
    ] = None,
) -> Dict[str, Any]:
    """
    Build a persistent school synchronization device record.
    """

    normalized_platform = _lower(
        platform
    )

    if normalized_platform not in PLATFORMS:
        raise ValueError(
            "Unsupported synchronization platform."
        )

    now = now_utc()

    return {
        "model_version": SYNC_MODEL_VERSION,

        "device_id": (
            _text(
                device_id
            )
            or secrets.token_hex(
                12
            )
        ),

        "school_id": _text(
            school_id
        ),

        "name": _text(
            device_name
        ),

        "platform": normalized_platform,

        "protocol_version": _text(
            protocol_version,
            DEFAULT_PROTOCOL_VERSION,
        ),

        "client_version": _text(
            client_version
        ),

        "status": "active",

        "capabilities": _string_list(
            capabilities,
            lower=True,
            maximum=MAX_CAPABILITIES,
        ),

        "metadata": _dict(
            metadata
        ),

        "created_by": _text(
            created_by
        ),

        "created_at": now,

        "updated_at": now,

        "last_seen_at": now,

        "last_sync_at": None,

        "last_sync_job_id": None,

        "last_error": None,

        "sync_cursor": None,

        "client_revision": 0,
    }


# =========================================================
# JOB DOCUMENT
# =========================================================

def job_doc(
    school_id: Any,
    kind: str,
    created_by: Any,
    *,
    connection_id: Any = None,
    device_id: Any = None,
    direction: Optional[str] = None,
    trigger: str = "manual",
    payload: Optional[
        Mapping[str, Any]
    ] = None,
    cursor_before: Any = None,
    batch_size: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Build a resumable synchronization job.
    """

    normalized_kind = _lower(
        kind
    )

    if normalized_kind not in JOB_KINDS:
        raise ValueError(
            "Invalid synchronization job kind."
        )

    normalized_direction = (
        _lower(
            direction
        )
        if direction
        else None
    )

    if (
        normalized_direction
        and normalized_direction
        not in SYNC_DIRECTIONS
    ):
        raise ValueError(
            "Invalid synchronization direction."
        )

    normalized_trigger = _lower(
        trigger,
        "manual",
    )

    if normalized_trigger not in TRIGGER_TYPES:
        normalized_trigger = "manual"

    now = now_utc()

    normalized_batch_size = _bounded_int(
        batch_size,
        default=DEFAULT_BATCH_SIZE,
        minimum=MIN_BATCH_SIZE,
        maximum=MAX_BATCH_SIZE,
    )

    return {
        "model_version": SYNC_MODEL_VERSION,

        "job_id": secrets.token_hex(
            16
        ),

        "school_id": _text(
            school_id
        ),

        "connection_id": (
            _text(
                connection_id
            )
            or None
        ),

        "device_id": (
            _text(
                device_id
            )
            or None
        ),

        "kind": normalized_kind,

        "direction": normalized_direction,

        "trigger": normalized_trigger,

        "status": "queued",

        "payload": _dict(
            payload
        ),

        # -------------------------------------------------
        # Cursor / checkpoint state
        # -------------------------------------------------

        "cursor_before": cursor_before,

        "cursor_after": None,

        "checkpoint": None,

        "resume_token": None,

        "last_entity_type": None,

        "last_entity_key": None,

        "batch_size": normalized_batch_size,

        # -------------------------------------------------
        # Counters
        # -------------------------------------------------

        "total_records": 0,

        "processed_records": 0,

        "created_records": 0,

        "updated_records": 0,

        "deleted_records": 0,

        "unchanged_records": 0,

        "conflict_records": 0,

        "ignored_records": 0,

        "error_records": 0,

        # -------------------------------------------------
        # Retry / error state
        # -------------------------------------------------

        "retry_count": 0,

        "max_retries": DEFAULT_MAX_RETRIES,

        "error": None,

        "errors": [],

        # -------------------------------------------------
        # Actor / lifecycle
        # -------------------------------------------------

        "created_by": _text(
            created_by
        ),

        "created_at": now,

        "updated_at": now,

        "started_at": None,

        "paused_at": None,

        "finished_at": None,
    }


# =========================================================
# RECORD DOCUMENT
# =========================================================

def record_doc(
    school_id: Any,
    entity_type: str,
    entity_key: Any,
    payload: Optional[
        Mapping[str, Any]
    ],
    *,
    connection_id: Any = None,
    device_id: Any = None,
    source: str = "cloud",
    source_record_id: Any = None,
    operation: str = "upsert",
    revision: int = 1,
    base_revision: Optional[int] = None,
    cloud_revision: Optional[int] = None,
    client_revision: Optional[int] = None,
    checksum: Optional[str] = None,
    deleted: bool = False,
    custom_fields: Optional[
        Mapping[str, Any]
    ] = None,
    tombstone_at: Optional[
        datetime
    ] = None,
) -> Dict[str, Any]:
    """
    Build the synchronization ledger representation of a domain record.

    Identity:
        entity_type + entity_key

    Version:
        revision

    Deletion:
        tombstone + deleted_at

    The ledger is not the authoritative Elimu domain collection.
    engine.py/services.py are responsible for applying accepted
    records to the real domain collection.
    """

    entity = normalize_entity_type(
        entity_type
    )

    key = _text(
        entity_key
    )

    normalized_source = _lower(
        source,
        "cloud",
    )

    normalized_operation = _lower(
        operation,
        "upsert",
    )

    if not key:
        raise ValueError(
            "entity_key is required."
        )

    if normalized_operation not in RECORD_OPERATIONS:
        raise ValueError(
            "Invalid synchronization record operation."
        )

    if not normalized_source:
        normalized_source = "cloud"

    safe_payload = _dict(
        payload
    )

    safe_custom_fields = _dict(
        custom_fields
    )

    deleted_flag = _safe_bool(
        deleted,
        False,
    )

    revision_value = max(
        1,
        _safe_int(
            revision,
            1,
        ),
    )

    base_revision_value = (
        None
        if base_revision is None
        else max(
            0,
            _safe_int(
                base_revision,
                0,
            ),
        )
    )

    cloud_revision_value = (
        None
        if cloud_revision is None
        else max(
            0,
            _safe_int(
                cloud_revision,
                0,
            ),
        )
    )

    client_revision_value = (
        None
        if client_revision is None
        else max(
            0,
            _safe_int(
                client_revision,
                0,
            ),
        )
    )

    now = now_utc()

    deleted_at = (
        ensure_utc(
            tombstone_at
        )
        if deleted_flag
        else None
    )

    if (
        deleted_flag
        and deleted_at is None
    ):
        deleted_at = now

    final_checksum = (
        checksum
        or payload_checksum(
            safe_payload
        )
    )

    return {
        "model_version": SYNC_MODEL_VERSION,

        "record_id": secrets.token_hex(
            16
        ),

        "school_id": _text(
            school_id
        ),

        "connection_id": (
            _text(
                connection_id
            )
            or None
        ),

        "device_id": (
            _text(
                device_id
            )
            or None
        ),

        # -------------------------------------------------
        # Logical identity
        # -------------------------------------------------

        "entity_type": entity,

        "entity_key": key,

        "source": normalized_source,

        "source_record_id": (
            _text(
                source_record_id
            )
            or None
        ),

        # -------------------------------------------------
        # Operation
        # -------------------------------------------------

        "operation": normalized_operation,

        "sync_state": "pending",

        # -------------------------------------------------
        # Versions
        # -------------------------------------------------

        "revision": revision_value,

        "base_revision": base_revision_value,

        "cloud_revision": cloud_revision_value,

        "client_revision": client_revision_value,

        # -------------------------------------------------
        # Change detection
        # -------------------------------------------------

        "checksum": final_checksum,

        "previous_checksum": None,

        # -------------------------------------------------
        # Deletion / tombstone
        # -------------------------------------------------

        "deleted": deleted_flag,

        "tombstone": deleted_flag,

        "deleted_at": deleted_at,

        # -------------------------------------------------
        # Record content
        # -------------------------------------------------

        "payload": safe_payload,

        "custom_fields": safe_custom_fields,

        # -------------------------------------------------
        # Sync lifecycle
        # -------------------------------------------------

        "created_at": now,

        "updated_at": now,

        "last_seen_at": now,

        "last_synced_at": None,

        "last_synced_revision": None,

        "last_error": None,
    }


# =========================================================
# CONFLICT DOCUMENT
# =========================================================

def conflict_doc(
    school_id: Any,
    entity_type: str,
    entity_key: Any,
    local_record: Mapping[str, Any],
    cloud_record: Mapping[str, Any],
    base_record: Optional[
        Mapping[str, Any]
    ] = None,
    *,
    source: Optional[
        Mapping[str, Any]
    ] = None,
    connection_id: Any = None,
    device_id: Any = None,
    job_id: Any = None,
    field_diffs: Optional[
        Sequence[
            Mapping[str, Any]
        ]
    ] = None,
    strategy: str = "manual",
) -> Dict[str, Any]:
    """
    Build an auditable conflict document.

    Conflicts preserve the local, cloud and optional base versions
    so resolution does not depend on the currently mutated record.
    """

    normalized_entity = normalize_entity_type(
        entity_type
    )

    normalized_strategy = _lower(
        strategy,
        "manual",
    )

    if (
        normalized_strategy
        not in CONFLICT_STRATEGIES
    ):
        normalized_strategy = "manual"

    now = now_utc()

    return {
        "model_version": SYNC_MODEL_VERSION,

        "conflict_id": secrets.token_hex(
            16
        ),

        "school_id": _text(
            school_id
        ),

        "connection_id": (
            _text(
                connection_id
            )
            or None
        ),

        "device_id": (
            _text(
                device_id
            )
            or None
        ),

        "job_id": (
            _text(
                job_id
            )
            or None
        ),

        "entity_type": normalized_entity,

        "entity_key": _text(
            entity_key
        ),

        "status": "open",

        "strategy": normalized_strategy,

        # -------------------------------------------------
        # Version snapshots
        # -------------------------------------------------

        "local_record": deepcopy(
            dict(
                local_record
            )
        ),

        "cloud_record": deepcopy(
            dict(
                cloud_record
            )
        ),

        "base_record": (
            deepcopy(
                dict(
                    base_record
                )
            )
            if isinstance(
                base_record,
                Mapping,
            )
            else None
        ),

        # -------------------------------------------------
        # Conflict analysis
        # -------------------------------------------------

        "field_diffs": [
            deepcopy(
                dict(item)
            )
            for item in (
                field_diffs
                or []
            )
            if isinstance(
                item,
                Mapping,
            )
        ],

        "source": _dict(
            source
        ),

        # -------------------------------------------------
        # Resolution
        # -------------------------------------------------

        "resolution": None,

        "resolved_record": None,

        "resolved_by": None,

        "resolved_at": None,

        # -------------------------------------------------
        # Lifecycle
        # -------------------------------------------------

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# CONNECTION STATE HELPERS
# =========================================================

def connection_is_expired(
    document: Mapping[str, Any],
) -> bool:
    expires_at = document.get(
        "token_expires_at"
    )

    if not isinstance(
        expires_at,
        datetime,
    ):
        return False

    expires_at = ensure_utc(
        expires_at
    )

    if expires_at is None:
        return False

    return expires_at <= now_utc()


def connection_is_usable(
    document: Mapping[str, Any],
) -> bool:
    if not isinstance(
        document,
        Mapping,
    ):
        return False

    status = _lower(
        document.get(
            "status"
        )
    )

    if status not in {
        "pending",
        "active",
    }:
        return False

    return not connection_is_expired(
        document
    )


def activate_connection(
    document: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Return an updated connection document without mutating the input.
    """

    result = deepcopy(
        dict(document)
    )

    timestamp = now_utc()

    result[
        "status"
    ] = "active"

    result[
        "activated_at"
    ] = (
        result.get(
            "activated_at"
        )
        or timestamp
    )

    result[
        "updated_at"
    ] = timestamp

    result[
        "last_error"
    ] = None

    return result


def pause_connection(
    document: Mapping[str, Any],
) -> Dict[str, Any]:
    result = deepcopy(
        dict(document)
    )

    timestamp = now_utc()

    result[
        "status"
    ] = "paused"

    result[
        "paused_at"
    ] = timestamp

    result[
        "updated_at"
    ] = timestamp

    return result


def revoke_connection(
    document: Mapping[str, Any],
) -> Dict[str, Any]:
    result = deepcopy(
        dict(document)
    )

    timestamp = now_utc()

    result[
        "status"
    ] = "revoked"

    result[
        "revoked_at"
    ] = timestamp

    result[
        "updated_at"
    ] = timestamp

    return result


# =========================================================
# JOB STATE HELPERS
# =========================================================

def job_is_terminal(
    status: Any,
) -> bool:
    return (
        _lower(
            status
        )
        in {
            "completed",
            "completed_with_errors",
            "failed",
            "cancelled",
        }
    )


def job_is_resumable(
    document: Mapping[str, Any],
) -> bool:
    if not isinstance(
        document,
        Mapping,
    ):
        return False

    status = _lower(
        document.get(
            "status"
        )
    )

    if status in {
        "queued",
        "running",
        "paused",
    }:
        return True

    if status == "failed":
        retry_count = _safe_int(
            document.get(
                "retry_count"
            ),
            0,
        )

        max_retries = _safe_int(
            document.get(
                "max_retries"
            ),
            DEFAULT_MAX_RETRIES,
        )

        return (
            retry_count
            < max_retries
        )

    return False


# =========================================================
# RECORD STATE HELPERS
# =========================================================

def record_is_deleted(
    document: Mapping[str, Any],
) -> bool:
    if not isinstance(
        document,
        Mapping,
    ):
        return False

    return (
        _safe_bool(
            document.get(
                "deleted"
            ),
            False,
        )
        or _safe_bool(
            document.get(
                "tombstone"
            ),
            False,
        )
        or _lower(
            document.get(
                "operation"
            )
        )
        == "delete"
    )


def record_version(
    document: Mapping[str, Any],
) -> int:
    if not isinstance(
        document,
        Mapping,
    ):
        return 0

    return max(
        0,
        _safe_int(
            document.get(
                "revision"
            ),
            0,
        ),
    )


# =========================================================
# NORMALIZED CHECKPOINT
# =========================================================

def checkpoint_doc(
    *,
    job_id: Any,
    entity_type: Any = None,
    entity_key: Any = None,
    cursor: Any = None,
    revision: int = 0,
    processed_records: int = 0,
    updated_at: Optional[
        datetime
    ] = None,
) -> Dict[str, Any]:
    """
    Canonical resumable checkpoint.

    The engine can persist this after every successful batch.
    """

    return {
        "job_id": _text(
            job_id
        ),
        "entity_type": (
            normalize_entity_type(
                entity_type
            )
            if entity_type
            else None
        ),
        "entity_key": (
            _text(
                entity_key
            )
            or None
        ),
        "cursor": cursor,
        "revision": max(
            0,
            _safe_int(
                revision,
                0,
            ),
        ),
        "processed_records": max(
            0,
            _safe_int(
                processed_records,
                0,
            ),
        ),
        "updated_at": (
            ensure_utc(
                updated_at
            )
            or now_utc()
        ),
    }


# =========================================================
# SYNC RESULT SNAPSHOT
# =========================================================

def sync_result_doc(
    *,
    school_id: Any,
    job_id: Any = None,
    connection_id: Any = None,
    direction: Any = None,
    created: int = 0,
    updated: int = 0,
    deleted: int = 0,
    unchanged: int = 0,
    conflicts: int = 0,
    errors: int = 0,
    ignored: int = 0,
    cursor: Any = None,
    revision: int = 0,
) -> Dict[str, Any]:
    """
    Small canonical result shape shared by engine/services/routes.
    """

    return {
        "school_id": _text(
            school_id
        ),

        "job_id": (
            _text(
                job_id
            )
            or None
        ),

        "connection_id": (
            _text(
                connection_id
            )
            or None
        ),

        "direction": (
            _lower(
                direction
            )
            or None
        ),

        "created": max(
            0,
            _safe_int(
                created,
                0,
            ),
        ),

        "updated": max(
            0,
            _safe_int(
                updated,
                0,
            ),
        ),

        "deleted": max(
            0,
            _safe_int(
                deleted,
                0,
            ),
        ),

        "unchanged": max(
            0,
            _safe_int(
                unchanged,
                0,
            ),
        ),

        "conflicts": max(
            0,
            _safe_int(
                conflicts,
                0,
            ),
        ),

        "errors": max(
            0,
            _safe_int(
                errors,
                0,
            ),
        ),

        "ignored": max(
            0,
            _safe_int(
                ignored,
                0,
            ),
        ),

        "cursor": cursor,

        "revision": max(
            0,
            _safe_int(
                revision,
                0,
            ),
        ),

        "completed_at": now_utc(),
    }