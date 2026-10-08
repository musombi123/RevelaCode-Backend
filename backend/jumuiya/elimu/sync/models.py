from __future__ import annotations

"""
School synchronization data models for the Elimu hub.

Design goals
------------
This module defines the persistent state required by the offline-first
Elimu desktop/cloud synchronizer.

The synchronization subsystem must support:

- multiple school devices/connections,
- bidirectional synchronization,
- resumable jobs and checkpoints,
- record-level versioning,
- tombstones for offline deletes,
- deterministic record identity,
- checksums for change detection,
- conflicts that are auditable and manually resolvable,
- per-school adjustable synchronization policy,
- legacy/desktop field mappings,
- safe connection authentication without storing raw secrets.

This module does NOT perform synchronization and does NOT write to MongoDB.
Service/engine layers own persistence and authorization.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# =========================================================
# COLLECTIONS
# =========================================================

CONNECTIONS = "jumuiya_elimu_sync_connections"
DEVICES = "jumuiya_elimu_sync_devices"
JOBS = "jumuiya_elimu_sync_jobs"
RECORDS = "jumuiya_elimu_sync_records"
CONFLICTS = "jumuiya_elimu_sync_conflicts"


# =========================================================
# VERSIONS / LIMITS
# =========================================================

SYNC_MODEL_VERSION = "1.0"
DEFAULT_PROTOCOL_VERSION = "1.0"
DEFAULT_CONNECTION_TOKEN_DAYS = 365
DEFAULT_BATCH_SIZE = 250
MIN_BATCH_SIZE = 25
MAX_BATCH_SIZE = 5000
DEFAULT_SYNC_INTERVAL_SECONDS = 300
MIN_SYNC_INTERVAL_SECONDS = 30
MAX_SYNC_INTERVAL_SECONDS = 7 * 24 * 60 * 60


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


# Logical names. The mapper/registry resolves these names to actual MongoDB
# collections. Keeping names logical makes the synchronizer portable across
# school installations and legacy databases.
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
    return datetime.now(timezone.utc)


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _lower(value: Any, default: str = "") -> str:
    return _text(value, default).lower()


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
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

    normalized = _lower(value)
    if normalized in {"true", "1", "yes", "on", "y"}:
        return True
    if normalized in {"false", "0", "no", "off", "n"}:
        return False
    return default


def _string_list(
    value: Any,
    *,
    lower: bool = False,
    unique: bool = True,
) -> List[str]:
    if value is None:
        return []

    if isinstance(value, str):
        value = [value]

    if not isinstance(value, (list, tuple, set)):
        return []

    result: List[str] = []
    seen = set()

    for item in value:
        normalized = _lower(item) if lower else _text(item)
        if not normalized:
            continue

        key = normalized.lower() if not lower else normalized
        if unique and key in seen:
            continue

        seen.add(key)
        result.append(normalized)

    return result


def _dict(value: Any) -> Dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _bounded_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    result = _safe_int(value, default)
    return max(minimum, min(result, maximum))


# =========================================================
# AUTHENTICATION TOKEN HELPERS
# =========================================================


def connection_token() -> str:
    """Create a high-entropy connection credential."""
    return secrets.token_urlsafe(32)


def hash_connection_token(raw_token: str) -> str:
    """Return the only representation that should be persisted."""
    value = _text(raw_token)
    if not value:
        raise ValueError("Connection token is required.")

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_connection_token(raw_token: str, token_hash: str) -> bool:
    """Constant-time verification of a presented connection token."""
    if not _text(raw_token) or not _text(token_hash):
        return False

    expected = hash_connection_token(raw_token)
    return hmac.compare_digest(expected, _text(token_hash))


def token_expires_at(days: int = DEFAULT_CONNECTION_TOKEN_DAYS) -> datetime:
    days = _bounded_int(
        days,
        default=DEFAULT_CONNECTION_TOKEN_DAYS,
        minimum=1,
        maximum=3650,
    )
    return now_utc() + timedelta(days=days)


# =========================================================
# SCHOOL-ADJUSTABLE SYNC POLICY
# =========================================================


def sync_policy_doc(
    policy: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Normalize synchronization controls that a school may adjust.

    These settings deliberately live in the sync subsystem rather than
    being hard-coded into the desktop client. That allows each school to
    choose its own sync behaviour while the engine remains deterministic.
    """
    source = dict(policy or {})

    direction = _lower(
        source.get("direction"),
        "bidirectional",
    )
    if direction not in SYNC_DIRECTIONS:
        direction = "bidirectional"

    conflict_strategy = _lower(
        source.get("conflict_strategy"),
        "manual",
    )
    if conflict_strategy not in CONFLICT_STRATEGIES:
        conflict_strategy = "manual"

    delete_mode = _lower(
        source.get("delete_mode"),
        "tombstone",
    )
    if delete_mode not in DELETE_MODES:
        delete_mode = "tombstone"

    trigger = _lower(
        source.get("default_trigger"),
        "manual",
    )
    if trigger not in TRIGGER_TYPES:
        trigger = "manual"

    return {
        "enabled": _safe_bool(source.get("enabled"), True),
        "auto_sync": _safe_bool(source.get("auto_sync"), True),
        "direction": direction,
        "conflict_strategy": conflict_strategy,
        "delete_mode": delete_mode,
        "pull_before_push": _safe_bool(
            source.get("pull_before_push"),
            True,
        ),
        "continue_on_error": _safe_bool(
            source.get("continue_on_error"),
            True,
        ),
        "preserve_local_custom_fields": _safe_bool(
            source.get("preserve_local_custom_fields"),
            True,
        ),
        "allow_cloud_schema_updates": _safe_bool(
            source.get("allow_cloud_schema_updates"),
            True,
        ),
        "batch_size": _bounded_int(
            source.get("batch_size"),
            default=DEFAULT_BATCH_SIZE,
            minimum=MIN_BATCH_SIZE,
            maximum=MAX_BATCH_SIZE,
        ),
        "sync_interval_seconds": _bounded_int(
            source.get("sync_interval_seconds"),
            default=DEFAULT_SYNC_INTERVAL_SECONDS,
            minimum=MIN_SYNC_INTERVAL_SECONDS,
            maximum=MAX_SYNC_INTERVAL_SECONDS,
        ),
        "max_retries": _bounded_int(
            source.get("max_retries"),
            default=5,
            minimum=0,
            maximum=20,
        ),
        "entity_types": _string_list(
            source.get("entity_types", DEFAULT_ENTITY_TYPES),
            lower=True,
        ) or list(DEFAULT_ENTITY_TYPES),
        "excluded_fields": _string_list(
            source.get("excluded_fields"),
            lower=False,
        ),
        "metadata": _dict(source.get("metadata")),
    }


# =========================================================
# FIELD MAPPING / SCHOOL CUSTOMIZATION
# =========================================================


def field_mappings_doc(
    mappings: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Normalize legacy-to-canonical field mappings.

    Example::

        {
            "students": {
                "AdmissionNo": "admission_number",
                "StudentName": "name"
            },
            "classes": {
                "ClassName": "name"
            }
        }

    The mapper remains responsible for semantics and validation; this model
    merely stores a clean, bounded structure.
    """
    source = mappings if isinstance(mappings, Mapping) else {}
    result: Dict[str, Any] = {}

    for entity_type, mapping in source.items():
        entity = _lower(entity_type)
        if not entity or not isinstance(mapping, Mapping):
            continue

        clean: Dict[str, str] = {}
        for source_field, target_field in mapping.items():
            source_name = _text(source_field)
            target_name = _text(target_field)
            if not source_name or not target_name:
                continue
            if len(source_name) > 128 or len(target_name) > 128:
                continue
            clean[source_name] = target_name

        if clean:
            result[entity] = clean

    return result


# =========================================================
# CONNECTION
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
    capabilities: Optional[Iterable[Any]] = None,
    policy: Optional[Mapping[str, Any]] = None,
    field_mappings: Optional[Mapping[str, Any]] = None,
    entity_types: Optional[Iterable[Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    token_days: int = DEFAULT_CONNECTION_TOKEN_DAYS,
) -> Tuple[Dict[str, Any], str]:
    """
    Build a connection document and return the raw credential separately.

    IMPORTANT:
        The raw token must be delivered once to the trusted desktop/client
        provisioning flow and must never be stored in MongoDB or logs.
    """
    school = _text(school_id)
    creator = _text(created_by)
    connection_name = _text(name)
    platform_name = _lower(platform)

    if not school:
        raise ValueError("school_id is required.")
    if not creator:
        raise ValueError("created_by is required.")
    if not connection_name:
        raise ValueError("Connection name is required.")
    if platform_name not in PLATFORMS:
        raise ValueError("Unsupported synchronization platform.")

    raw_token = connection_token()
    now = now_utc()
    expires_at = token_expires_at(token_days)

    normalized_policy = sync_policy_doc(policy)

    if entity_types is not None:
        normalized_policy["entity_types"] = (
            _string_list(entity_types, lower=True)
            or list(DEFAULT_ENTITY_TYPES)
        )

    document = {
        "model_version": SYNC_MODEL_VERSION,
        "connection_id": secrets.token_hex(16),
        "school_id": school,
        "device_id": _text(device_id) or None,
        "name": connection_name,
        "platform": platform_name,
        "protocol_version": _text(
            protocol_version,
            DEFAULT_PROTOCOL_VERSION,
        ),
        "client_version": _text(client_version),
        "status": "pending",
        "token_hash": hash_connection_token(raw_token),
        "token_expires_at": expires_at,
        "capabilities": _string_list(capabilities, lower=True),
        "entity_types": list(normalized_policy["entity_types"]),
        "policy": normalized_policy,
        "field_mappings": field_mappings_doc(field_mappings),
        "metadata": _dict(metadata),
        "created_by": creator,
        "created_at": now,
        "updated_at": now,
        "last_sync_at": None,
        "last_sync_status": None,
        "last_sync_job_id": None,
        "last_error": None,
        "sync_cursor": None,
        "sync_revision": 0,
    }

    return document, raw_token


# =========================================================
# DEVICE
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
    capabilities: Optional[Iterable[Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    now = now_utc()
    normalized_platform = _lower(platform)

    if normalized_platform not in PLATFORMS:
        raise ValueError("Unsupported synchronization platform.")

    return {
        "model_version": SYNC_MODEL_VERSION,
        "device_id": _text(device_id) or secrets.token_hex(12),
        "school_id": _text(school_id),
        "name": _text(device_name),
        "platform": normalized_platform,
        "protocol_version": _text(
            protocol_version,
            DEFAULT_PROTOCOL_VERSION,
        ),
        "client_version": _text(client_version),
        "status": "active",
        "capabilities": _string_list(capabilities, lower=True),
        "metadata": _dict(metadata),
        "created_by": _text(created_by),
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
        "last_sync_at": None,
        "last_error": None,
    }


# =========================================================
# JOB / CHECKPOINT
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
    payload: Optional[Mapping[str, Any]] = None,
    cursor_before: Any = None,
) -> Dict[str, Any]:
    normalized_kind = _lower(kind)
    if normalized_kind not in JOB_KINDS:
        raise ValueError("Invalid synchronization job kind.")

    normalized_direction = _lower(direction) if direction else None
    if normalized_direction and normalized_direction not in SYNC_DIRECTIONS:
        raise ValueError("Invalid synchronization direction.")

    normalized_trigger = _lower(trigger, "manual")
    if normalized_trigger not in TRIGGER_TYPES:
        normalized_trigger = "manual"

    now = now_utc()

    return {
        "model_version": SYNC_MODEL_VERSION,
        "job_id": secrets.token_hex(16),
        "school_id": _text(school_id),
        "connection_id": _text(connection_id) or None,
        "device_id": _text(device_id) or None,
        "kind": normalized_kind,
        "direction": normalized_direction,
        "trigger": normalized_trigger,
        "status": "queued",
        "payload": _dict(payload),
        "cursor_before": cursor_before,
        "cursor_after": None,
        "checkpoint": None,
        "resume_token": None,
        "total_records": 0,
        "processed_records": 0,
        "created_records": 0,
        "updated_records": 0,
        "deleted_records": 0,
        "conflict_records": 0,
        "error_records": 0,
        "retry_count": 0,
        "error": None,
        "created_by": _text(created_by),
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
    }


# =========================================================
# SYNC RECORD
# =========================================================


def record_doc(
    school_id: Any,
    entity_type: str,
    entity_key: Any,
    payload: Optional[Mapping[str, Any]],
    *,
    connection_id: Any = None,
    source: str = "cloud",
    source_record_id: Any = None,
    operation: str = "upsert",
    revision: int = 1,
    base_revision: Optional[int] = None,
    cloud_revision: Optional[int] = None,
    checksum: Optional[str] = None,
    deleted: bool = False,
    custom_fields: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build the synchronization ledger entry for one logical record.

    `entity_key` is the stable logical identity used across local/cloud
    representations. It must not depend on a temporary database ObjectId.
    """
    entity = _lower(entity_type)
    key = _text(entity_key)
    normalized_operation = _lower(operation, "upsert")

    if not entity:
        raise ValueError("entity_type is required.")
    if not key:
        raise ValueError("entity_key is required.")
    if normalized_operation not in RECORD_OPERATIONS:
        raise ValueError("Invalid synchronization record operation.")

    now = now_utc()
    safe_payload = _dict(payload)
    safe_custom = _dict(custom_fields)

    computed_checksum = checksum or payload_checksum(safe_payload)
    revision_value = max(1, _safe_int(revision, 1))

    return {
        "model_version": SYNC_MODEL_VERSION,
        "record_id": secrets.token_hex(16),
        "school_id": _text(school_id),
        "connection_id": _text(connection_id) or None,
        "entity_type": entity,
        "entity_key": key,
        "source": _text(source, "cloud").lower(),
        "source_record_id": _text(source_record_id) or None,
        "operation": normalized_operation,
        "sync_state": "pending",
        "revision": revision_value,
        "base_revision": (
            None
            if base_revision is None
            else max(0, _safe_int(base_revision, 0))
        ),
        "cloud_revision": (
            None
            if cloud_revision is None
            else max(0, _safe_int(cloud_revision, 0))
        ),
        "checksum": computed_checksum,
        "deleted": bool(deleted),
        "payload": safe_payload,
        "custom_fields": safe_custom,
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
        "last_synced_at": None,
        "last_error": None,
    }


# =========================================================
# CHECKSUM
# =========================================================


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }

    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]

    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return str(value)


def payload_checksum(payload: Any) -> str:
    """
    Produce a deterministic SHA-256 fingerprint for change detection.
    """
    import json

    canonical = _canonicalize(payload)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


# =========================================================
# CONFLICT
# =========================================================


def conflict_doc(
    school_id: Any,
    entity_type: str,
    entity_key: Any,
    local_record: Mapping[str, Any],
    cloud_record: Mapping[str, Any],
    base_record: Optional[Mapping[str, Any]] = None,
    *,
    source: Optional[Mapping[str, Any]] = None,
    connection_id: Any = None,
    job_id: Any = None,
    field_diffs: Optional[Sequence[Mapping[str, Any]]] = None,
    strategy: str = "manual",
) -> Dict[str, Any]:
    normalized_strategy = _lower(strategy, "manual")
    if normalized_strategy not in CONFLICT_STRATEGIES:
        normalized_strategy = "manual"

    now = now_utc()

    return {
        "model_version": SYNC_MODEL_VERSION,
        "conflict_id": secrets.token_hex(16),
        "school_id": _text(school_id),
        "connection_id": _text(connection_id) or None,
        "job_id": _text(job_id) or None,
        "entity_type": _lower(entity_type),
        "entity_key": _text(entity_key),
        "status": "open",
        "strategy": normalized_strategy,
        "local_record": deepcopy(dict(local_record)),
        "cloud_record": deepcopy(dict(cloud_record)),
        "base_record": (
            deepcopy(dict(base_record))
            if isinstance(base_record, Mapping)
            else None
        ),
        "field_diffs": [
            deepcopy(dict(item))
            for item in (field_diffs or [])
            if isinstance(item, Mapping)
        ],
        "source": _dict(source),
        "resolution": None,
        "resolved_record": None,
        "resolved_by": None,
        "resolved_at": None,
        "created_at": now,
        "updated_at": now,
    }


# =========================================================
# STATE HELPERS
# =========================================================


def connection_is_expired(document: Mapping[str, Any]) -> bool:
    expires_at = document.get("token_expires_at")
    if not isinstance(expires_at, datetime):
        return False

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    return expires_at <= now_utc()


def connection_is_usable(document: Mapping[str, Any]) -> bool:
    status = _lower(document.get("status"))
    if status not in {"pending", "active"}:
        return False
    return not connection_is_expired(document)


def normalize_entity_types(
    entity_types: Any,
) -> List[str]:
    values = _string_list(entity_types, lower=True)
    if not values:
        return list(DEFAULT_ENTITY_TYPES)

    if "*" in values:
        return ["*"]

    return values


def normalize_capabilities(
    capabilities: Any,
) -> List[str]:
    return _string_list(capabilities, lower=True)
