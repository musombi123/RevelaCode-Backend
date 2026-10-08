# backend/jumuiya/elimu/sync/schemas.py

from __future__ import annotations

"""
Validation and normalization contracts for Elimu synchronization.

This module validates external/API payloads before they reach:

    services.py
        ↓
    queue.py / engine.py
        ↓
    authoritative Elimu collections

The schema layer does not write to MongoDB.

Backward-compatible public functions
------------------------------------
- connection_payload()
- records_payload()
- conflict_resolution_payload()

Additional contracts are provided for the richer Sync routes.
"""

from typing import Any, Mapping, Optional

from .mapper import (
    canonical_entity_type,
)


# =========================================================
# CONSTANTS
# =========================================================

MAX_NAME_LENGTH = 120
MAX_PLATFORM_LENGTH = 32
MAX_TOKEN_LENGTH = 512
MAX_DEVICE_ID_LENGTH = 160
MAX_CONNECTION_ID_LENGTH = 160
MAX_CLIENT_VERSION_LENGTH = 80
MAX_PROTOCOL_VERSION_LENGTH = 40

MAX_ENTITY_RECORDS = 5000
MAX_BASE_RECORDS = 5000

MAX_BATCH_SIZE = 5000
MIN_BATCH_SIZE = 25

MAX_LIMIT = 10000

SUPPORTED_PLATFORMS = {
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

SUPPORTED_DIRECTIONS = {
    "bidirectional",
    "upload",
    "download",
}

SUPPORTED_TRIGGERS = {
    "manual",
    "startup",
    "scheduled",
    "reconnect",
    "import",
    "repair",
    "api",
}

SUPPORTED_CONFLICT_STRATEGIES = {
    "manual",
    "cloud_wins",
    "local_wins",
    "latest_write",
    "base_merge",
}

SUPPORTED_DELETE_MODES = {
    "tombstone",
    "ignore",
}

SUPPORTED_CONFLICT_DECISIONS = {
    "keep_local",
    "keep_cloud",
    "merge",
}

SUPPORTED_JOB_STATUSES = {
    "queued",
    "running",
    "paused",
    "completed",
    "completed_with_errors",
    "failed",
    "cancelled",
}


# =========================================================
# BASIC HELPERS
# =========================================================

def _s(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(value).strip()


def _lower(
    value: Any,
    default: str = "",
) -> str:
    return _s(
        value,
        default,
    ).lower()


def _dict(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(
        value,
        Mapping,
    ):
        return {}

    return dict(
        value
    )


def _list(
    value: Any,
) -> list[Any]:
    if not isinstance(
        value,
        list,
    ):
        return []

    return list(
        value
    )


def _optional_text(
    value: Any,
    *,
    maximum: int,
) -> Optional[str]:
    if value is None:
        return None

    result = _s(
        value
    )

    if not result:
        return None

    if len(
        result
    ) > maximum:
        raise ValueError(
            f"Value exceeds maximum length of {maximum} characters."
        )

    return result


def _required_text(
    value: Any,
    field_name: str,
    *,
    maximum: int,
) -> str:
    result = _s(
        value
    )

    if not result:
        raise ValueError(
            f"{field_name} is required."
        )

    if len(
        result
    ) > maximum:
        raise ValueError(
            f"{field_name} exceeds maximum length of {maximum} characters."
        )

    return result


def _positive_int(
    value: Any,
    field_name: str,
    *,
    minimum: int = 1,
    maximum: int = MAX_LIMIT,
    default: Optional[int] = None,
) -> int:
    if value is None:
        if default is not None:
            return default

        raise ValueError(
            f"{field_name} is required."
        )

    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            f"{field_name} must be an integer."
        )

    try:
        result = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            f"{field_name} must be an integer."
        )

    if result < minimum or result > maximum:
        raise ValueError(
            f"{field_name} must be between {minimum} and {maximum}."
        )

    return result


def _boolean(
    value: Any,
    field_name: str,
    *,
    default: Optional[bool] = None,
) -> bool:
    if value is None:
        if default is not None:
            return default

        raise ValueError(
            f"{field_name} must be true or false."
        )

    if isinstance(
        value,
        bool,
    ):
        return value

    if isinstance(
        value,
        int,
    ) and value in {
        0,
        1,
    }:
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
    }:
        return True

    if normalized in {
        "false",
        "0",
        "no",
        "off",
    }:
        return False

    raise ValueError(
        f"{field_name} must be true or false."
    )


def _records(
    value: Any,
    field_name: str = "records",
    *,
    maximum: int = MAX_ENTITY_RECORDS,
) -> list[dict[str, Any]]:
    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            f"{field_name} must be an array."
        )

    if len(
        value
    ) > maximum:
        raise ValueError(
            f"{field_name} cannot contain more than {maximum} records."
        )

    result: list[
        dict[str, Any]
    ] = []

    for index, item in enumerate(
        value
    ):
        if not isinstance(
            item,
            Mapping,
        ):
            raise ValueError(
                f"{field_name}[{index}] must be a JSON object."
            )

        result.append(
            dict(
                item
            )
        )

    return result


def _string_list(
    value: Any,
    field_name: str,
    *,
    maximum_items: int = 100,
    maximum_length: int = 160,
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
            f"{field_name} must be an array of strings."
        )

    if len(
        value
    ) > maximum_items:
        raise ValueError(
            f"{field_name} cannot contain more than {maximum_items} items."
        )

    result: list[
        str
    ] = []

    seen: set[str] = set()

    for index, item in enumerate(
        value
    ):
        text = _s(
            item
        )

        if not text:
            continue

        if len(
            text
        ) > maximum_length:
            raise ValueError(
                f"{field_name}[{index}] exceeds maximum length of "
                f"{maximum_length} characters."
            )

        if text.casefold() in seen:
            continue

        seen.add(
            text.casefold()
        )

        result.append(
            text
        )

    return result


# =========================================================
# POLICY VALIDATION
# =========================================================

def _policy(
    value: Any,
) -> dict[str, Any]:
    if value is None:
        return {}

    if not isinstance(
        value,
        Mapping,
    ):
        raise ValueError(
            "policy must be a JSON object."
        )

    source = dict(
        value
    )

    result: dict[str, Any] = {}

    if "enabled" in source:
        result[
            "enabled"
        ] = _boolean(
            source.get(
                "enabled"
            ),
            "policy.enabled",
        )

    if "auto_sync" in source:
        result[
            "auto_sync"
        ] = _boolean(
            source.get(
                "auto_sync"
            ),
            "policy.auto_sync",
        )

    if "direction" in source:
        direction = _lower(
            source.get(
                "direction"
            )
        )

        if direction not in SUPPORTED_DIRECTIONS:
            raise ValueError(
                "Invalid policy.direction."
            )

        result[
            "direction"
        ] = direction

    if "conflict_strategy" in source:
        strategy = _lower(
            source.get(
                "conflict_strategy"
            )
        )

        if strategy not in SUPPORTED_CONFLICT_STRATEGIES:
            raise ValueError(
                "Invalid policy.conflict_strategy."
            )

        result[
            "conflict_strategy"
        ] = strategy

    if "delete_mode" in source:
        delete_mode = _lower(
            source.get(
                "delete_mode"
            )
        )

        if delete_mode not in SUPPORTED_DELETE_MODES:
            raise ValueError(
                "Invalid policy.delete_mode."
            )

        result[
            "delete_mode"
        ] = delete_mode

    for field in (
        "pull_before_push",
        "continue_on_error",
        "preserve_local_custom_fields",
        "allow_cloud_schema_updates",
    ):
        if field in source:
            result[
                field
            ] = _boolean(
                source.get(
                    field
                ),
                f"policy.{field}",
            )

    if "batch_size" in source:
        result[
            "batch_size"
        ] = _positive_int(
            source.get(
                "batch_size"
            ),
            "policy.batch_size",
            minimum=MIN_BATCH_SIZE,
            maximum=MAX_BATCH_SIZE,
        )

    if "sync_interval_seconds" in source:
        result[
            "sync_interval_seconds"
        ] = _positive_int(
            source.get(
                "sync_interval_seconds"
            ),
            "policy.sync_interval_seconds",
            minimum=30,
            maximum=604800,
        )

    if "max_retries" in source:
        result[
            "max_retries"
        ] = _positive_int(
            source.get(
                "max_retries"
            ),
            "policy.max_retries",
            minimum=0,
            maximum=20,
        )

    if "entity_types" in source:
        result[
            "entity_types"
        ] = _string_list(
            source.get(
                "entity_types"
            ),
            "policy.entity_types",
        )

        # Validate logical entity names now.
        if "*" not in result[
            "entity_types"
        ]:
            result[
                "entity_types"
            ] = [
                canonical_entity_type(
                    item
                )
                for item in result[
                    "entity_types"
                ]
            ]
            result[
                "entity_types"
            ] = list(
                dict.fromkeys(
                    result[
                        "entity_types"
                    ]
                )
            )

    if "excluded_fields" in source:
        result[
            "excluded_fields"
        ] = _string_list(
            source.get(
                "excluded_fields"
            ),
            "policy.excluded_fields",
            maximum_items=500,
            maximum_length=255,
        )

    if "metadata" in source:
        metadata = source.get(
            "metadata"
        )

        if not isinstance(
            metadata,
            Mapping,
        ):
            raise ValueError(
                "policy.metadata must be a JSON object."
            )

        result[
            "metadata"
        ] = dict(
            metadata
        )

    return result


# =========================================================
# FIELD MAPPINGS
# =========================================================

def _field_mappings(
    value: Any,
) -> dict[str, dict[str, str]]:
    if value is None:
        return {}

    if not isinstance(
        value,
        Mapping,
    ):
        raise ValueError(
            "field_mappings must be a JSON object."
        )

    result: dict[
        str,
        dict[str, str],
    ] = {}

    for entity_type, mapping in value.items():
        canonical = canonical_entity_type(
            entity_type
        )

        if not isinstance(
            mapping,
            Mapping,
        ):
            raise ValueError(
                f"field_mappings.{entity_type} must be a JSON object."
            )

        clean: dict[
            str,
            str,
        ] = {}

        for source_field, target_field in mapping.items():
            source_name = _required_text(
                source_field,
                "source field",
                maximum=255,
            )

            target_name = _required_text(
                target_field,
                "target field",
                maximum=255,
            )

            if target_name.startswith(
                "$"
            ):
                raise ValueError(
                    f"Invalid mapped target field: {target_name}"
                )

            clean[
                source_name
            ] = target_name

        result[
            canonical
        ] = clean

    return result


# =========================================================
# CONNECTION
# =========================================================

def connection_payload(
    d: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Validate connection provisioning data.

    Existing clients can continue sending only:

        name
        platform
        metadata

    Richer clients may send:

        device_id
        client_version
        protocol_version
        capabilities
        policy
        field_mappings
        entity_types
        token_days
    """
    if not isinstance(
        d,
        Mapping,
    ):
        raise ValueError(
            "JSON object is required."
        )

    name = (
        _s(
            d.get(
                "name"
            )
        )
        or "School Desktop"
    )

    if len(
        name
    ) > MAX_NAME_LENGTH:
        raise ValueError(
            "name exceeds the maximum allowed length."
        )

    platform = (
        _lower(
            d.get(
                "platform"
            )
        )
        or "windows"
    )

    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(
            "Unsupported synchronization platform."
        )

    metadata = d.get(
        "metadata"
    )

    if metadata is None:
        metadata = {}

    if not isinstance(
        metadata,
        Mapping,
    ):
        raise ValueError(
            "metadata must be a JSON object."
        )

    device_id = _optional_text(
        d.get(
            "device_id"
        ),
        maximum=MAX_DEVICE_ID_LENGTH,
    )

    client_version = _optional_text(
        d.get(
            "client_version"
        ),
        maximum=MAX_CLIENT_VERSION_LENGTH,
    )

    protocol_version = _optional_text(
        d.get(
            "protocol_version"
        ),
        maximum=MAX_PROTOCOL_VERSION_LENGTH,
    )

    capabilities = _string_list(
        d.get(
            "capabilities"
        ),
        "capabilities",
        maximum_items=100,
        maximum_length=100,
    )

    entity_types = d.get(
        "entity_types"
    )

    if entity_types is not None:
        entity_types = _string_list(
            entity_types,
            "entity_types",
            maximum_items=100,
            maximum_length=100,
        )

        if "*" not in entity_types:
            entity_types = [
                canonical_entity_type(
                    item
                )
                for item in entity_types
            ]

        entity_types = list(
            dict.fromkeys(
                entity_types
            )
        )

    token_days = _positive_int(
        d.get(
            "token_days"
        ),
        "token_days",
        minimum=1,
        maximum=3650,
        default=365,
    )

    result = {
        "name": name,
        "platform": platform,
        "device_id": device_id,
        "client_version": client_version,
        "protocol_version": protocol_version,
        "capabilities": capabilities,
        "entity_types": entity_types,
        "policy": _policy(
            d.get(
                "policy"
            )
        ),
        "field_mappings": _field_mappings(
            d.get(
                "field_mappings"
            )
        ),
        "metadata": dict(
            metadata
        ),
        "token_days": token_days,
    }

    return result


# =========================================================
# RECORD INGEST
# =========================================================

def records_payload(
    d: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Validate a synchronization ingest request.

    Existing contract remains valid:

        {
            "entity_type": "...",
            "records": [...]
        }

    Rich client contract can additionally include:

        connection_id
        connection_token
        device_id
        source
        base_records
        conflict_strategy
        delete_mode
        direction
        trigger
        batch_size
        field_mappings
        policy
    """
    if not isinstance(
        d,
        Mapping,
    ):
        raise ValueError(
            "JSON object is required."
        )

    entity_type_raw = _required_text(
        d.get(
            "entity_type"
        ),
        "entity_type",
        maximum=100,
    )

    entity_type = canonical_entity_type(
        entity_type_raw
    )

    records = _records(
        d.get(
            "records"
        ),
        maximum=MAX_ENTITY_RECORDS,
    )

    # Base snapshots are keyed by the mapper's logical entity key.
    raw_base_records = d.get(
        "base_records"
    )

    if raw_base_records is None:
        base_records: dict[
            str,
            dict[str, Any],
        ] = {}

    elif isinstance(
        raw_base_records,
        Mapping,
    ):
        if len(
            raw_base_records
        ) > MAX_BASE_RECORDS:
            raise ValueError(
                f"base_records cannot contain more than "
                f"{MAX_BASE_RECORDS} records."
            )

        base_records = {}

        for key, value in raw_base_records.items():
            key_text = _required_text(
                key,
                "base record key",
                maximum=1000,
            )

            if not isinstance(
                value,
                Mapping,
            ):
                raise ValueError(
                    f"base_records['{key_text}'] must be a JSON object."
                )

            base_records[
                key_text
            ] = dict(
                value
            )

    else:
        raise ValueError(
            "base_records must be a JSON object."
        )

    connection_id = _optional_text(
        d.get(
            "connection_id"
        ),
        maximum=MAX_CONNECTION_ID_LENGTH,
    )

    connection_token = _optional_text(
        d.get(
            "connection_token"
        ),
        maximum=MAX_TOKEN_LENGTH,
    )

    # Legacy alias.
    if not connection_token:
        connection_token = _optional_text(
            d.get(
                "token"
            ),
            maximum=MAX_TOKEN_LENGTH,
        )

    device_id = _optional_text(
        d.get(
            "device_id"
        ),
        maximum=MAX_DEVICE_ID_LENGTH,
    )

    source = (
        _s(
            d.get(
                "source"
            )
        )
        or "desktop"
    )

    if len(
        source
    ) > 50:
        raise ValueError(
            "source exceeds the maximum allowed length."
        )

    conflict_strategy = _lower(
        d.get(
            "conflict_strategy"
        )
    )

    if conflict_strategy:
        if conflict_strategy not in SUPPORTED_CONFLICT_STRATEGIES:
            raise ValueError(
                "Invalid conflict_strategy."
            )
    else:
        conflict_strategy = None

    delete_mode = _lower(
        d.get(
            "delete_mode"
        )
    )

    if delete_mode:
        if delete_mode not in SUPPORTED_DELETE_MODES:
            raise ValueError(
                "Invalid delete_mode."
            )
    else:
        delete_mode = None

    direction = _lower(
        d.get(
            "direction"
        )
    )

    if direction:
        if direction not in SUPPORTED_DIRECTIONS:
            raise ValueError(
                "Invalid direction."
            )
    else:
        direction = None

    trigger = _lower(
        d.get(
            "trigger"
        )
    )

    if trigger:
        if trigger not in SUPPORTED_TRIGGERS:
            raise ValueError(
                "Invalid trigger."
            )
    else:
        trigger = "api"

    batch_size = None

    if d.get(
        "batch_size"
    ) is not None:
        batch_size = _positive_int(
            d.get(
                "batch_size"
            ),
            "batch_size",
            minimum=MIN_BATCH_SIZE,
            maximum=MAX_BATCH_SIZE,
        )

    request_policy = _policy(
        d.get(
            "policy"
        )
    )

    request_mappings = _field_mappings(
        d.get(
            "field_mappings"
        )
    )

    return {
        "entity_type": entity_type,
        "records": records,
        "base_records": base_records,
        "connection_id": connection_id,
        "connection_token": connection_token,
        "device_id": device_id,
        "source": source,
        "conflict_strategy": conflict_strategy,
        "delete_mode": delete_mode,
        "direction": direction,
        "trigger": trigger,
        "batch_size": batch_size,
        "policy": request_policy,
        "field_mappings": request_mappings,
    }


# =========================================================
# CONFLICT RESOLUTION
# =========================================================

def conflict_resolution_payload(
    d: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Validate an explicit administrative conflict resolution.

    `manual` is accepted for backward compatibility with the previous
    schema, but it is converted into an unresolved/no-op decision.
    """
    if not isinstance(
        d,
        Mapping,
    ):
        raise ValueError(
            "JSON object is required."
        )

    decision = _lower(
        d.get(
            "decision"
        )
    )

    # Preserve old clients that may still submit manual.
    if decision == "manual":
        return {
            "decision": "manual",
            "merged_record": None,
            "note": _optional_text(
                d.get(
                    "note"
                ),
                maximum=2000,
            ),
        }

    if decision not in SUPPORTED_CONFLICT_DECISIONS:
        raise ValueError(
            "Invalid conflict decision."
        )

    merged_record = d.get(
        "merged_record"
    )

    if decision == "merge":
        if not isinstance(
            merged_record,
            Mapping,
        ):
            raise ValueError(
                "merged_record is required when decision is merge."
            )

        merged_record = dict(
            merged_record
        )

    elif merged_record is not None:
        if not isinstance(
            merged_record,
            Mapping,
        ):
            raise ValueError(
                "merged_record must be a JSON object."
            )

        merged_record = dict(
            merged_record
        )

    note = _optional_text(
        d.get(
            "note"
        ),
        maximum=2000,
    )

    return {
        "decision": decision,
        "merged_record": merged_record,
        "note": note,
    }


# =========================================================
# JOB QUERY
# =========================================================

def job_query_params(
    d: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Validate optional filters for Sync job listing.
    """
    if not isinstance(
        d,
        Mapping,
    ):
        raise ValueError(
            "JSON object is required."
        )

    status = _lower(
        d.get(
            "status"
        )
    )

    if status and status not in SUPPORTED_JOB_STATUSES:
        raise ValueError(
            "Invalid job status."
        )

    connection_id = _optional_text(
        d.get(
            "connection_id"
        ),
        maximum=MAX_CONNECTION_ID_LENGTH,
    )

    device_id = _optional_text(
        d.get(
            "device_id"
        ),
        maximum=MAX_DEVICE_ID_LENGTH,
    )

    limit = _positive_int(
        d.get(
            "limit"
        ),
        "limit",
        minimum=1,
        maximum=MAX_LIMIT,
        default=50,
    )

    return {
        "status": status or None,
        "connection_id": connection_id,
        "device_id": device_id,
        "limit": limit,
    }


# =========================================================
# JOB CONTROL
# =========================================================

def job_control_payload(
    d: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Validate pause/cancel/retry control payloads.
    """
    if d is None:
        d = {}

    if not isinstance(
        d,
        Mapping,
    ):
        raise ValueError(
            "JSON object is required."
        )

    reason = _optional_text(
        d.get(
            "reason"
        ),
        maximum=2000,
    )

    return {
        "reason": reason,
    }


# =========================================================
# DEVICE
# =========================================================

def device_payload(
    d: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Validate device registration/update data.
    """
    if not isinstance(
        d,
        Mapping,
    ):
        raise ValueError(
            "JSON object is required."
        )

    device_id = _required_text(
        d.get(
            "device_id"
        ),
        "device_id",
        maximum=MAX_DEVICE_ID_LENGTH,
    )

    name = (
        _s(
            d.get(
                "name"
            )
        )
        or "School Desktop"
    )

    if len(
        name
    ) > MAX_NAME_LENGTH:
        raise ValueError(
            "name exceeds the maximum allowed length."
        )

    platform = (
        _lower(
            d.get(
                "platform"
            )
        )
        or "windows"
    )

    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(
            "Unsupported synchronization platform."
        )

    capabilities = _string_list(
        d.get(
            "capabilities"
        ),
        "capabilities",
        maximum_items=100,
        maximum_length=100,
    )

    metadata = d.get(
        "metadata"
    )

    if metadata is None:
        metadata = {}

    if not isinstance(
        metadata,
        Mapping,
    ):
        raise ValueError(
            "metadata must be a JSON object."
        )

    return {
        "device_id": device_id,
        "name": name,
        "platform": platform,
        "client_version": _optional_text(
            d.get(
                "client_version"
            ),
            maximum=MAX_CLIENT_VERSION_LENGTH,
        ),
        "protocol_version": _optional_text(
            d.get(
                "protocol_version"
            ),
            maximum=MAX_PROTOCOL_VERSION_LENGTH,
        ),
        "capabilities": capabilities,
        "metadata": dict(
            metadata
        ),
    }


# =========================================================
# EXPORT PARAMETERS
# =========================================================

def export_params(
    d: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Validate export query parameters supplied as a dictionary.
    """
    if not isinstance(
        d,
        Mapping,
    ):
        raise ValueError(
            "JSON object is required."
        )

    entity_type = _required_text(
        d.get(
            "entity_type"
        ),
        "entity_type",
        maximum=100,
    )

    entity_type = canonical_entity_type(
        entity_type
    )

    include_deleted = _boolean(
        d.get(
            "include_deleted"
        ),
        "include_deleted",
        default=False,
    )

    include_mongo_id = _boolean(
        d.get(
            "include_mongo_id"
        ),
        "include_mongo_id",
        default=False,
    )

    format_name = (
        _lower(
            d.get(
                "format"
            )
        )
        or "json"
    )

    if format_name not in {
        "json",
        "csv",
        "xlsx",
        "excel",
        "excel_xlsx",
    }:
        raise ValueError(
            "Unsupported export format."
        )

    limit = _positive_int(
        d.get(
            "limit"
        ),
        "limit",
        minimum=1,
        maximum=MAX_LIMIT,
        default=5000,
    )

    return {
        "entity_type": entity_type,
        "include_deleted": include_deleted,
        "include_mongo_id": include_mongo_id,
        "format": format_name,
        "limit": limit,
    }


# =========================================================
# SYNC START PAYLOAD
# =========================================================

def sync_start_payload(
    d: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Validate a future/full-job start request.

    Useful for the richer routes layer when synchronization is moved
    fully into background workers.
    """
    if not isinstance(
        d,
        Mapping,
    ):
        raise ValueError(
            "JSON object is required."
        )

    connection_id = _optional_text(
        d.get(
            "connection_id"
        ),
        maximum=MAX_CONNECTION_ID_LENGTH,
    )

    connection_token = _optional_text(
        d.get(
            "connection_token"
        ),
        maximum=MAX_TOKEN_LENGTH,
    )

    entity_types = d.get(
        "entity_types"
    )

    if entity_types is not None:
        entity_types = _string_list(
            entity_types,
            "entity_types",
            maximum_items=100,
            maximum_length=100,
        )

        if "*" not in entity_types:
            entity_types = [
                canonical_entity_type(
                    item
                )
                for item in entity_types
            ]

    direction = (
        _lower(
            d.get(
                "direction"
            )
        )
        or "bidirectional"
    )

    if direction not in SUPPORTED_DIRECTIONS:
        raise ValueError(
            "Invalid direction."
        )

    trigger = (
        _lower(
            d.get(
                "trigger"
            )
        )
        or "manual"
    )

    if trigger not in SUPPORTED_TRIGGERS:
        raise ValueError(
            "Invalid trigger."
        )

    return {
        "connection_id": connection_id,
        "connection_token": connection_token,
        "entity_types": entity_types,
        "direction": direction,
        "trigger": trigger,
        "conflict_strategy": _lower(
            d.get(
                "conflict_strategy"
            )
        )
        or None,
        "delete_mode": _lower(
            d.get(
                "delete_mode"
            )
        )
        or None,
        "batch_size": (
            _positive_int(
                d.get(
                    "batch_size"
                ),
                "batch_size",
                minimum=MIN_BATCH_SIZE,
                maximum=MAX_BATCH_SIZE,
            )
            if d.get(
                "batch_size"
            ) is not None
            else None
        ),
    }