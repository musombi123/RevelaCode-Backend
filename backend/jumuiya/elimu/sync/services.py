# backend/jumuiya/elimu/sync/services.py

from __future__ import annotations

"""
Application/service layer for Elimu synchronization.

Responsibilities
----------------
- authorization;
- connection provisioning and authentication;
- connection lifecycle;
- policy resolution;
- job lifecycle;
- batch ingestion;
- conflict listing/resolution;
- authoritative exports;
- synchronization status.

The service layer owns security and orchestration.

The engine owns record reconciliation.

The queue owns persistent job state.

The authoritative Elimu collections remain the source of truth.
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.elimu.permissions import authorize

from .engine import (
    reconcile,
    resolve_conflict_record,
)
from .mapper import (
    canonical_entity_type,
    entity_collection,
)
from .models import (
    CONNECTIONS,
    CONFLICTS,
    DEVICES,
    JOBS,
    RECORDS,
    connection_doc,
    connection_is_expired,
    connection_is_usable,
    device_doc,
    normalize_entity_types,
    verify_connection_token,
)
from .queue import (
    cancel as queue_cancel,
    checkpoint as queue_checkpoint,
    complete as queue_complete,
    enqueue as queue_enqueue,
    fail as queue_fail,
    get as queue_get,
    heartbeat as queue_heartbeat,
    increment_progress as queue_increment_progress,
    list_jobs as queue_list_jobs,
    pause as queue_pause,
    recover_stale as queue_recover_stale,
    resume as queue_resume,
    retry as queue_retry,
)


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_SOURCE = "desktop"

DEFAULT_CONFLICT_STRATEGY = "manual"
DEFAULT_DELETE_MODE = "tombstone"

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


# =========================================================
# TIME
# =========================================================

def now_utc() -> datetime:
    return datetime.now(
        timezone.utc
    )


# =========================================================
# BASIC HELPERS
# =========================================================

def sid(
    membership: Mapping[str, Any],
) -> str:
    value = str(
        membership.get(
            "school_id",
            ""
        )
    ).strip()

    if not value:
        raise APIError(
            "A school is required for Elimu synchronization.",
            403,
            "school_required",
        )

    return value


def _text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(value).strip()


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
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return default


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


# =========================================================
# SERIALIZATION
# =========================================================

def _serialize(
    value: Any,
) -> Any:
    """
    Recursively serialize Mongo/Python values for Flask responses.
    """
    if isinstance(
        value,
        ObjectId,
    ):
        return str(
            value
        )

    if isinstance(
        value,
        datetime,
    ):
        if value.tzinfo is None:
            value = value.replace(
                tzinfo=timezone.utc
            )
        else:
            value = value.astimezone(
                timezone.utc
            )

        return value.isoformat()

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(key): _serialize(
                item
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        (list, tuple),
    ):
        return [
            _serialize(
                item
            )
            for item in value
        ]

    return value


def ser(
    document: Optional[
        Mapping[str, Any]
    ],
) -> Optional[dict[str, Any]]:
    if not document:
        return None

    return _serialize(
        dict(document)
    )


def _serialize_many(
    documents: Any,
) -> list[dict[str, Any]]:
    return [
        _serialize(
            dict(document)
        )
        for document in documents
        if isinstance(
            document,
            Mapping,
        )
    ]


# =========================================================
# CONNECTION LOOKUP
# =========================================================

def _connection_by_id(
    school_id: str,
    connection_id: Any,
) -> Optional[
    dict[str, Any]
]:
    value = _text(
        connection_id
    )

    if not value:
        return None

    query = {
        "school_id": str(
            school_id
        ),
        "connection_id": value,
    }

    document = collection(
        CONNECTIONS
    ).find_one(
        query
    )

    if document:
        return dict(
            document
        )

    # Compatibility with clients that still send Mongo _id.
    if ObjectId.is_valid(
        value
    ):
        document = collection(
            CONNECTIONS
        ).find_one(
            {
                "school_id": str(
                    school_id
                ),
                "_id": ObjectId(
                    value
                ),
            }
        )

        if document:
            return dict(
                document
            )

    return None


def _connection_by_token(
    school_id: str,
    raw_token: str,
) -> Optional[
    dict[str, Any]
]:
    token = _text(
        raw_token
    )

    if not token:
        return None

    # Avoid querying using the raw token. Hash it first.
    from .models import hash_connection_token

    token_hash = hash_connection_token(
        token
    )

    document = collection(
        CONNECTIONS
    ).find_one(
        {
            "school_id": str(
                school_id
            ),
            "token_hash": token_hash,
        }
    )

    return (
        dict(document)
        if document
        else None
    )


def _connection_for_request(
    school_id: str,
    payload: Mapping[str, Any],
    *,
    require_token: bool = False,
) -> Optional[
    dict[str, Any]
]:
    """
    Resolve and authenticate a sync connection.

    Rules
    -----
    - connection_id + token -> validate both;
    - token only -> locate connection by hashed token;
    - connection_id only -> reject because it is insufficient for
      desktop authentication;
    - neither -> allow authenticated Elimu staff access for trusted
      web/admin operations unless require_token=True.
    """
    connection_id = _text(
        payload.get(
            "connection_id"
        )
    )

    raw_token = _text(
        payload.get(
            "connection_token"
        )
        or payload.get(
            "token"
        )
    )

    if (
        not connection_id
        and not raw_token
    ):
        if require_token:
            raise APIError(
                "A synchronization connection token is required.",
                401,
                "sync_connection_token_required",
            )

        return None

    connection = None

    if connection_id:
        connection = _connection_by_id(
            school_id,
            connection_id,
        )

        if not connection:
            raise APIError(
                "Synchronization connection not found.",
                404,
                "sync_connection_not_found",
            )

        # An identified external device must authenticate with its token.
        if not raw_token:
            raise APIError(
                "Connection token is required.",
                401,
                "sync_connection_token_required",
            )

        if not verify_connection_token(
            raw_token,
            connection.get(
                "token_hash",
                ""
            ),
        ):
            raise APIError(
                "Invalid synchronization connection token.",
                401,
                "invalid_sync_connection_token",
            )

    else:
        connection = _connection_by_token(
            school_id,
            raw_token,
        )

        if not connection:
            raise APIError(
                "Invalid synchronization connection token.",
                401,
                "invalid_sync_connection_token",
            )

    if connection_is_expired(
        connection
    ):
        collection(
            CONNECTIONS
        ).update_one(
            {
                "_id": connection[
                    "_id"
                ],
                "school_id": str(
                    school_id
                ),
            },
            {
                "$set": {
                    "status": "expired",
                    "updated_at": now_utc(),
                    "last_error": (
                        "Synchronization connection token expired."
                    ),
                }
            },
        )

        raise APIError(
            "Synchronization connection has expired.",
            401,
            "sync_connection_expired",
        )

    if not connection_is_usable(
        connection
    ):
        raise APIError(
            "Synchronization connection is not active.",
            403,
            "sync_connection_unavailable",
        )

    # First authenticated use promotes pending -> active.
    if connection.get(
        "status"
    ) == "pending":
        connection = _activate_connection(
            school_id,
            connection,
        )

    _touch_connection(
        school_id,
        connection,
    )

    return connection


# =========================================================
# CONNECTION LIFECYCLE
# =========================================================

def _activate_connection(
    school_id: str,
    connection: Mapping[str, Any],
) -> dict[str, Any]:
    timestamp = now_utc()

    result = collection(
        CONNECTIONS
    ).find_one_and_update(
        {
            "_id": connection[
                "_id"
            ],
            "school_id": str(
                school_id
            ),
            "status": {
                "$in": [
                    "pending",
                    "active",
                ]
            },
        },
        {
            "$set": {
                "status": "active",
                "activated_at": (
                    connection.get(
                        "activated_at"
                    )
                    or timestamp
                ),
                "updated_at": timestamp,
                "last_seen_at": timestamp,
                "last_error": None,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    return (
        dict(result)
        if result
        else dict(connection)
    )


def _touch_connection(
    school_id: str,
    connection: Mapping[str, Any],
) -> None:
    collection(
        CONNECTIONS
    ).update_one(
        {
            "_id": connection[
                "_id"
            ],
            "school_id": str(
                school_id
            ),
        },
        {
            "$set": {
                "last_seen_at": now_utc(),
                "updated_at": now_utc(),
            }
        },
    )


def activate_connection(
    user_id: Any,
    connection_id: str,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.import",
    )

    school_id = sid(
        member
    )

    connection = _connection_by_id(
        school_id,
        connection_id,
    )

    if not connection:
        raise APIError(
            "Synchronization connection not found.",
            404,
            "sync_connection_not_found",
        )

    updated = _activate_connection(
        school_id,
        connection,
    )

    return {
        "connection": _safe_connection_response(
            updated
        )
    }


def pause_connection(
    user_id: Any,
    connection_id: str,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.import",
    )

    school_id = sid(
        member
    )

    connection = _connection_by_id(
        school_id,
        connection_id,
    )

    if not connection:
        raise APIError(
            "Synchronization connection not found.",
            404,
            "sync_connection_not_found",
        )

    timestamp = now_utc()

    updated = collection(
        CONNECTIONS
    ).find_one_and_update(
        {
            "_id": connection[
                "_id"
            ],
            "school_id": school_id,
            "status": {
                "$nin": [
                    "revoked",
                    "expired",
                ]
            },
        },
        {
            "$set": {
                "status": "paused",
                "paused_at": timestamp,
                "updated_at": timestamp,
                "last_error": (
                    _text(reason)
                    if reason
                    else None
                ),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not updated:
        raise APIError(
            "Synchronization connection cannot be paused.",
            409,
            "sync_connection_state_error",
        )

    return {
        "connection": _safe_connection_response(
            updated
        )
    }


def revoke_connection(
    user_id: Any,
    connection_id: str,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.import",
    )

    school_id = sid(
        member
    )

    connection = _connection_by_id(
        school_id,
        connection_id,
    )

    if not connection:
        raise APIError(
            "Synchronization connection not found.",
            404,
            "sync_connection_not_found",
        )

    timestamp = now_utc()

    updated = collection(
        CONNECTIONS
    ).find_one_and_update(
        {
            "_id": connection[
                "_id"
            ],
            "school_id": school_id,
        },
        {
            "$set": {
                "status": "revoked",
                "revoked_at": timestamp,
                "updated_at": timestamp,
            },
            "$unset": {
                "token_hash": "",
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if not updated:
        raise APIError(
            "Unable to revoke synchronization connection.",
            409,
            "sync_connection_state_error",
        )

    return {
        "connection": _safe_connection_response(
            updated,
            include_credentials=False,
        )
    }


# =========================================================
# CONNECTION RESPONSE
# =========================================================

def _safe_connection_response(
    document: Mapping[str, Any],
    *,
    raw_token: Optional[str] = None,
    include_credentials: bool = False,
) -> dict[str, Any]:
    """
    Never expose token_hash.

    A raw connection token is returned only during connection creation
    or an explicitly credential-bearing provisioning response.
    """
    result = dict(
        document
    )

    result.pop(
        "token_hash",
        None,
    )

    result.pop(
        "_id",
        None,
    )

    result[
        "has_credentials"
    ] = bool(
        document.get(
            "token_hash"
        )
    )

    if (
        include_credentials
        and raw_token
    ):
        result[
            "connection_token"
        ] = raw_token

    return _serialize(
        result
    )


# =========================================================
# CONNECTION CREATE
# =========================================================

def create_connection(
    user_id: Any,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.import",
    )

    school_id = sid(
        member
    )

    data = _dict(
        payload
    )

    name = (
        _text(
            data.get(
                "name"
            )
        )
        or "School Desktop"
    )

    platform = (
        _text(
            data.get(
                "platform"
            )
        )
        or "windows"
    ).lower()

    if platform not in SUPPORTED_PLATFORMS:
        raise APIError(
            "Unsupported synchronization platform.",
            422,
            "invalid_sync_platform",
        )

    policy = _dict(
        data.get(
            "policy"
        )
    )

    field_mappings = _dict(
        data.get(
            "field_mappings"
        )
    )

    entity_types = data.get(
        "entity_types"
    )

    metadata = _dict(
        data.get(
            "metadata"
        )
    )

    # Do not trust a client-supplied school_id.
    metadata.pop(
        "school_id",
        None,
    )

    try:
        document, raw_token = connection_doc(
            school_id,
            name,
            platform,
            user_id,
            device_id=data.get(
                "device_id"
            ),
            client_version=_text(
                data.get(
                    "client_version"
                )
            ),
            protocol_version=_text(
                data.get(
                    "protocol_version"
                )
            )
            or "2.0",
            capabilities=data.get(
                "capabilities"
            ),
            policy=policy,
            field_mappings=field_mappings,
            entity_types=entity_types,
            metadata=metadata,
            token_days=_safe_int(
                data.get(
                    "token_days"
                ),
                365,
            ),
        )

    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "sync_connection_validation_error",
        )

    inserted = collection(
        CONNECTIONS
    ).insert_one(
        document
    )

    document[
        "_id"
    ] = inserted.inserted_id

    # If a device ID was supplied, keep a companion device document.
    device_id = _text(
        data.get(
            "device_id"
        )
    )

    if device_id:
        existing_device = collection(
            DEVICES
        ).find_one(
            {
                "school_id": school_id,
                "device_id": device_id,
            }
        )

        if not existing_device:
            try:
                device = device_doc(
                    school_id,
                    name,
                    platform,
                    user_id,
                    device_id=device_id,
                    client_version=_text(
                        data.get(
                            "client_version"
                        )
                    ),
                    protocol_version=_text(
                        data.get(
                            "protocol_version"
                        )
                    )
                    or "2.0",
                    capabilities=data.get(
                        "capabilities"
                    ),
                    metadata=metadata,
                )

                collection(
                    DEVICES
                ).insert_one(
                    device
                )

            except ValueError:
                # Connection itself has already been created.
                # Device registration should not break provisioning.
                pass

    response = _safe_connection_response(
        document,
        raw_token=raw_token,
        include_credentials=True,
    )

    response[
        "warning"
    ] = (
        "Store this connection token securely. "
        "It is not persisted in plaintext and will not be shown again."
    )

    return {
        "connection": response
    }


# =========================================================
# CONNECTION LIST
# =========================================================

def list_connections(
    user_id: Any,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.view",
    )

    school_id = sid(
        member
    )

    rows = list(
        collection(
            CONNECTIONS
        )
        .find(
            {
                "school_id": school_id
            }
        )
        .sort(
            "created_at",
            -1,
        )
    )

    return {
        "connections": [
            _safe_connection_response(
                row
            )
            for row in rows
        ]
    }


# =========================================================
# CONNECTION DETAILS
# =========================================================

def get_connection(
    user_id: Any,
    connection_id: str,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.view",
    )

    school_id = sid(
        member
    )

    connection = _connection_by_id(
        school_id,
        connection_id,
    )

    if not connection:
        raise APIError(
            "Synchronization connection not found.",
            404,
            "sync_connection_not_found",
        )

    return {
        "connection": _safe_connection_response(
            connection
        )
    }


# =========================================================
# POLICY RESOLUTION
# =========================================================

def _policy(
    connection: Optional[
        Mapping[str, Any]
    ],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    connection_policy = _dict(
        (
            connection or {}
        ).get(
            "policy"
        )
    )

    request_policy = _dict(
        payload.get(
            "policy"
        )
    )

    merged = {
        **connection_policy,
        **request_policy,
    }

    strategy = (
        _text(
            payload.get(
                "conflict_strategy"
            )
        ).lower()
        or _text(
            merged.get(
                "conflict_strategy"
            )
        ).lower()
        or DEFAULT_CONFLICT_STRATEGY
    )

    if strategy not in SUPPORTED_CONFLICT_STRATEGIES:
        raise APIError(
            "Invalid synchronization conflict strategy.",
            422,
            "invalid_sync_conflict_strategy",
        )

    delete_mode = (
        _text(
            payload.get(
                "delete_mode"
            )
        ).lower()
        or _text(
            merged.get(
                "delete_mode"
            )
        ).lower()
        or DEFAULT_DELETE_MODE
    )

    if delete_mode not in SUPPORTED_DELETE_MODES:
        raise APIError(
            "Invalid synchronization delete mode.",
            422,
            "invalid_sync_delete_mode",
        )

    raw_entity_types = (
        payload.get(
            "entity_types"
        )
        if payload.get(
            "entity_types"
        ) is not None
        else merged.get(
            "entity_types"
        )
    )

    return {
        "enabled": merged.get(
            "enabled",
            True,
        ),
        "auto_sync": merged.get(
            "auto_sync",
            True,
        ),
        "direction": _text(
            payload.get(
                "direction"
            )
            or merged.get(
                "direction"
            )
            or "bidirectional"
        ).lower(),
        "conflict_strategy": strategy,
        "delete_mode": delete_mode,
        "pull_before_push": bool(
            merged.get(
                "pull_before_push",
                True,
            )
        ),
        "continue_on_error": bool(
            merged.get(
                "continue_on_error",
                True,
            )
        ),
        "preserve_local_custom_fields": bool(
            merged.get(
                "preserve_local_custom_fields",
                True,
            )
        ),
        "allow_cloud_schema_updates": bool(
            merged.get(
                "allow_cloud_schema_updates",
                True,
            )
        ),
        "batch_size": max(
            25,
            min(
                5000,
                _safe_int(
                    payload.get(
                        "batch_size"
                    )
                    or merged.get(
                        "batch_size"
                    ),
                    250,
                ),
            ),
        ),
        "entity_types": normalize_entity_types(
            raw_entity_types
        ),
        "excluded_fields": (
            list(
                merged.get(
                    "excluded_fields",
                    [],
                )
            )
            if isinstance(
                merged.get(
                    "excluded_fields",
                    [],
                ),
                list,
            )
            else []
        ),
    }


def _assert_entity_allowed(
    entity_type: str,
    policy: Mapping[str, Any],
) -> str:
    canonical = canonical_entity_type(
        entity_type
    )

    allowed = set(
        policy.get(
            "entity_types",
            [],
        )
    )

    if (
        allowed
        and "*"
        not in allowed
        and canonical
        not in allowed
    ):
        raise APIError(
            f"Entity '{canonical}' is not enabled for this synchronization connection.",
            403,
            "sync_entity_not_allowed",
        )

    # Virtual entities cannot be imported/exported as standalone
    # Mongo documents.
    try:
        entity_collection(
            canonical
        )
    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "sync_entity_not_persistable",
        )

    return canonical


# =========================================================
# JOB CREATION
# =========================================================

def _create_job(
    school_id: str,
    *,
    kind: str,
    created_by: Any,
    payload: Mapping[str, Any],
    connection_id: Any = None,
    device_id: Any = None,
    direction: str = "upload",
    trigger: str = "api",
    cursor_before: Any = None,
) -> str:
    try:
        return queue_enqueue(
            school_id,
            kind,
            payload,
            created_by,
            connection_id=connection_id,
            device_id=device_id,
            direction=direction,
            trigger=trigger,
            cursor_before=cursor_before,
        )

    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "sync_job_validation_error",
        )


def _start_job(
    job_id: str,
    school_id: str,
) -> dict[str, Any]:
    """
    Start the exact job created by this service call.

    The queue's global claim() method is intended for worker processes.
    Request/response ingestion needs an exact job transition.
    """
    result = collection(
        JOBS
    ).find_one_and_update(
        {
            "job_id": str(
                job_id
            ),
            "school_id": str(
                school_id
            ),
            "status": "queued",
        },
        {
            "$set": {
                "status": "running",
                "started_at": now_utc(),
                "updated_at": now_utc(),
                "last_heartbeat_at": now_utc(),
                "lease_expires_at": (
                    now_utc()
                )
                + __import__(
                    "datetime"
                ).timedelta(
                    seconds=300
                ),
                "worker_id": "http-ingest",
            },
            "$inc": {
                "claim_count": 1,
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if not result:
        raise APIError(
            "Unable to start synchronization job.",
            409,
            "sync_job_start_failed",
        )

    return dict(
        result
    )


# =========================================================
# INGEST
# =========================================================

def ingest(
    user_id: Any,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Process a synchronization batch.

    This remains synchronous for the current API contract, but every
    request is represented by a persistent queue job.

    That gives us:

        auditability
        job status
        retries
        checkpoint support
        conflict association
    """
    member = authorize(
        user_id,
        "sync.import",
    )

    school_id = sid(
        member
    )

    data = _dict(
        payload
    )

    entity_type_raw = _text(
        data.get(
            "entity_type"
        )
    )

    if not entity_type_raw:
        raise APIError(
            "entity_type is required.",
            422,
            "sync_entity_type_required",
        )

    records = data.get(
        "records"
    )

    if not isinstance(
        records,
        list,
    ):
        raise APIError(
            "records must be a list.",
            422,
            "sync_records_required",
        )

    if not records:
        return {
            "school_id": school_id,
            "entity_type": entity_type_raw,
            "total": 0,
            "created": 0,
            "updated": 0,
            "deleted": 0,
            "merged": 0,
            "unchanged": 0,
            "conflicts": 0,
            "ignored": 0,
            "errors": 0,
            "successful": 0,
            "failed": 0,
            "completed": True,
            "items": [],
        }

    connection = _connection_for_request(
        school_id,
        data,
        require_token=bool(
            data.get(
                "connection_id"
            )
        )
        or bool(
            data.get(
                "connection_token"
            )
        ),
    )

    policy = _policy(
        connection,
        data,
    )

    canonical = _assert_entity_allowed(
        entity_type_raw,
        policy,
    )

    connection_id = (
        connection.get(
            "connection_id"
        )
        if connection
        else None
    )

    device_id = (
        connection.get(
            "device_id"
        )
        if connection
        else _text(
            data.get(
                "device_id"
            )
        )
        or None
    )

    base_records = data.get(
        "base_records"
    )

    if not isinstance(
        base_records,
        Mapping,
    ):
        base_records = {}

    # -----------------------------------------------------
    # CREATE JOB
    # -----------------------------------------------------

    job_payload = {
        "entity_type": canonical,
        "records_count": len(
            records
        ),
        "source": _text(
            data.get(
                "source"
            )
        )
        or DEFAULT_SOURCE,
        "batch_size": policy[
            "batch_size"
        ],
        "conflict_strategy": policy[
            "conflict_strategy"
        ],
        "delete_mode": policy[
            "delete_mode"
        ],
    }

    job_id = _create_job(
        school_id,
        kind=(
            "incremental_sync"
            if connection
            else "import"
        ),
        created_by=user_id,
        payload=job_payload,
        connection_id=connection_id,
        device_id=device_id,
        direction="upload",
        trigger=_text(
            data.get(
                "trigger"
            )
        ).lower()
        or "api",
        cursor_before=(
            connection.get(
                "sync_cursor"
            )
            if connection
            else None
        ),
    )

    _start_job(
        job_id,
        school_id,
    )

    try:
        result = reconcile(
            school_id,
            canonical,
            records,
            base_records=base_records,
            source=(
                _text(
                    data.get(
                        "source"
                    )
                )
                or DEFAULT_SOURCE
            ),
            field_mappings=(
                connection.get(
                    "field_mappings"
                )
                if connection
                else data.get(
                    "field_mappings"
                )
            ),
            excluded_fields=policy[
                "excluded_fields"
            ],
            conflict_strategy=policy[
                "conflict_strategy"
            ],
            delete_mode=policy[
                "delete_mode"
            ],
            connection_id=connection_id,
            job_id=job_id,
        )

        # -------------------------------------------------
        # CHECKPOINT
        # -------------------------------------------------

        queue_checkpoint(
            job_id,
            checkpoint_data={
                "entity_type": canonical,
                "records_count": len(
                    records
                ),
                "completed": True,
            },
            last_entity_type=canonical,
            processed_records=result.get(
                "successful",
                0,
            )
            + result.get(
                "failed",
                0,
            ),
            created_records=result.get(
                "created",
                0,
            ),
            updated_records=(
                result.get(
                    "updated",
                    0,
                )
                + result.get(
                    "merged",
                    0,
                )
            ),
            deleted_records=result.get(
                "deleted",
                0,
            ),
            conflict_records=result.get(
                "conflicts",
                0,
            ),
            error_records=result.get(
                "errors",
                0,
            ),
        )

        completed_with_errors = (
            result.get(
                "errors",
                0,
            )
            > 0
        )

        queue_complete(
            job_id,
            result,
            completed_with_errors=completed_with_errors,
        )

        # -------------------------------------------------
        # UPDATE CONNECTION
        # -------------------------------------------------

        if connection:
            _record_sync_completion(
                school_id,
                connection,
                job_id,
                result,
            )

        return {
            **result,
            "job_id": job_id,
            "connection_id": connection_id,
        }

    except Exception as exc:
        queue_fail(
            job_id,
            str(
                exc
            ),
        )

        if connection:
            _record_sync_failure(
                school_id,
                connection,
                job_id,
                str(
                    exc
                ),
            )

        if isinstance(
            exc,
            APIError,
        ):
            raise

        raise APIError(
            "Synchronization failed.",
            500,
            "sync_failed",
        )


# =========================================================
# CONNECTION SYNC METRICS
# =========================================================

def _record_sync_completion(
    school_id: str,
    connection: Mapping[str, Any],
    job_id: str,
    result: Mapping[str, Any],
) -> None:
    timestamp = now_utc()

    conflicts_open = collection(
        CONFLICTS
    ).count_documents(
        {
            "school_id": school_id,
            "status": "open",
        }
    )

    records_synced = (
        _safe_int(
            result.get(
                "created"
            ),
            0,
        )
        + _safe_int(
            result.get(
                "updated"
            ),
            0,
        )
        + _safe_int(
            result.get(
                "merged"
            ),
            0,
        )
        + _safe_int(
            result.get(
                "unchanged"
            ),
            0,
        )
        + _safe_int(
            result.get(
                "deleted"
            ),
            0,
        )
    )

    updates = {
        "status": "active",
        "last_sync_at": timestamp,
        "last_sync_status": (
            "completed_with_errors"
            if _safe_int(
                result.get(
                    "errors"
                ),
                0,
            )
            > 0
            else (
                "completed_with_conflicts"
                if _safe_int(
                    result.get(
                        "conflicts"
                    ),
                    0,
                )
                > 0
                else "completed"
            )
        ),
        "last_sync_job_id": str(
            job_id
        ),
        "last_error": None,
        "updated_at": timestamp,
        "last_seen_at": timestamp,
        "records_synced": records_synced,
        "records_failed": _safe_int(
            result.get(
                "errors"
            ),
            0,
        ),
        "conflicts_open": conflicts_open,
    }

    collection(
        CONNECTIONS
    ).update_one(
        {
            "_id": connection[
                "_id"
            ],
            "school_id": school_id,
        },
        {
            "$set": updates,
            "$inc": {
                "sync_revision": 1,
            },
        },
    )


def _record_sync_failure(
    school_id: str,
    connection: Mapping[str, Any],
    job_id: str,
    error: str,
) -> None:
    collection(
        CONNECTIONS
    ).update_one(
        {
            "_id": connection[
                "_id"
            ],
            "school_id": school_id,
        },
        {
            "$set": {
                "last_sync_at": now_utc(),
                "last_sync_status": "failed",
                "last_sync_job_id": str(
                    job_id
                ),
                "last_error": _text(
                    error
                ),
                "updated_at": now_utc(),
            },
            "$inc": {
                "sync_revision": 1,
            },
        },
    )


# =========================================================
# CONFLICT LIST
# =========================================================

def conflicts(
    user_id: Any,
    status: str = "open",
    *,
    limit: int = 100,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.resolve",
    )

    school_id = sid(
        member
    )

    normalized_status = (
        _text(
            status
        ).lower()
        or "open"
    )

    allowed_statuses = {
        "open",
        "in_review",
        "resolved",
        "ignored",
        "expired",
    }

    if normalized_status not in allowed_statuses:
        raise APIError(
            "Invalid conflict status.",
            422,
            "invalid_sync_conflict_status",
        )

    limit = max(
        1,
        min(
            _safe_int(
                limit,
                100,
            ),
            500,
        ),
    )

    rows = list(
        collection(
            CONFLICTS
        )
        .find(
            {
                "school_id": school_id,
                "status": normalized_status,
            }
        )
        .sort(
            "created_at",
            -1,
        )
        .limit(
            limit
        )
    )

    return {
        "conflicts": _serialize_many(
            rows
        ),
        "count": len(
            rows
        ),
        "status": normalized_status,
    }


# =========================================================
# CONFLICT RESOLUTION
# =========================================================

def _find_conflict(
    school_id: str,
    conflict_id: str,
) -> Optional[
    dict[str, Any]
]:
    value = _text(
        conflict_id
    )

    if not value:
        return None

    # Canonical identifier.
    document = collection(
        CONFLICTS
    ).find_one(
        {
            "school_id": school_id,
            "conflict_id": value,
        }
    )

    if document:
        return dict(
            document
        )

    # Backward compatibility with old records storing Mongo _id
    # in client URLs.
    if ObjectId.is_valid(
        value
    ):
        document = collection(
            CONFLICTS
        ).find_one(
            {
                "school_id": school_id,
                "_id": ObjectId(
                    value
                ),
            }
        )

        if document:
            return dict(
                document
            )

    return None


def resolve_conflict(
    user_id: Any,
    conflict_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.resolve",
    )

    school_id = sid(
        member
    )

    conflict = _find_conflict(
        school_id,
        conflict_id,
    )

    if not conflict:
        raise APIError(
            "Sync conflict not found.",
            404,
            "sync_conflict_not_found",
        )

    if conflict.get(
        "status"
    ) not in {
        "open",
        "in_review",
    }:
        raise APIError(
            "This synchronization conflict has already been resolved.",
            409,
            "sync_conflict_already_resolved",
        )

    data = _dict(
        payload
    )

    decision = (
        _text(
            data.get(
                "decision"
            )
        ).lower()
    )

    if decision not in {
        "keep_local",
        "keep_cloud",
        "merge",
    }:
        raise APIError(
            "Invalid conflict resolution decision.",
            422,
            "invalid_sync_conflict_decision",
        )

    merged_record = data.get(
        "merged_record"
    )

    if (
        decision == "merge"
        and not isinstance(
            merged_record,
            Mapping,
        )
    ):
        raise APIError(
            "merged_record is required for merge resolution.",
            422,
            "merged_record_required",
        )

    try:
        result = resolve_conflict_record(
            school_id,
            conflict,
            decision=decision,
            merged_record=(
                merged_record
                if isinstance(
                    merged_record,
                    Mapping,
                )
                else None
            ),
        )

    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "sync_conflict_resolution_error",
        )

    # Refresh open conflict count.
    open_conflicts = collection(
        CONFLICTS
    ).count_documents(
        {
            "school_id": school_id,
            "status": "open",
        }
    )

    if conflict.get(
        "connection_id"
    ):
        collection(
            CONNECTIONS
        ).update_one(
            {
                "school_id": school_id,
                "connection_id": conflict[
                    "connection_id"
                ],
            },
            {
                "$set": {
                    "conflicts_open": open_conflicts,
                    "updated_at": now_utc(),
                }
            },
        )

    return _serialize(
        {
            "resolved": True,
            "conflict_id": str(
                conflict.get(
                    "conflict_id"
                )
                or conflict_id
            ),
            "decision": decision,
            "result": result,
            "open_conflicts": open_conflicts,
        }
    )


# =========================================================
# EXPORT
# =========================================================

def export_records(
    user_id: Any,
    entity_type: str,
    *,
    include_deleted: bool = False,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    """
    Export the authoritative Elimu records.

    IMPORTANT:
    This deliberately does not export the synchronization ledger.
    """
    member = authorize(
        user_id,
        "sync.export",
    )

    school_id = sid(
        member
    )

    canonical = canonical_entity_type(
        entity_type
    )

    try:
        mongo_collection = entity_collection(
            canonical
        )
    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "sync_entity_not_persistable",
        )

    limit = max(
        1,
        min(
            _safe_int(
                limit,
                5000,
            ),
            10000,
        ),
    )

    query: dict[str, Any]

    if canonical == "school":
        # School is stored in the school collection and ownership is
        # represented by owner_user_id.
        query = {
            "owner_user_id": str(
                user_id
            )
        }

    else:
        query = {
            "school_id": school_id
        }

        if not include_deleted:
            query[
                "deleted"
            ] = {
                "$ne": True
            }

    rows = list(
        collection(
            mongo_collection
        )
        .find(
            query
        )
        .sort(
            "updated_at",
            1,
        )
        .limit(
            limit
        )
    )

    return [
        _serialize(
            dict(
                row
            )
        )
        for row in rows
    ]


# =========================================================
# EXPORT PACKAGE
# =========================================================

def export_package(
    user_id: Any,
    entity_type: str,
    *,
    include_deleted: bool = False,
    limit: int = 5000,
) -> dict[str, Any]:
    records = export_records(
        user_id,
        entity_type,
        include_deleted=include_deleted,
        limit=limit,
    )

    return {
        "hub": "elimu",
        "entity_type": canonical_entity_type(
            entity_type
        ),
        "count": len(
            records
        ),
        "generated_at": now_utc().isoformat(),
        "records": records,
    }


# =========================================================
# JOBS
# =========================================================

def jobs(
    user_id: Any,
    *,
    status: Optional[str] = None,
    connection_id: Optional[str] = None,
    device_id: Optional[str] = None,
    limit: int = 50,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.view",
    )

    school_id = sid(
        member
    )

    rows = queue_list_jobs(
        school_id,
        status=status,
        connection_id=connection_id,
        device_id=device_id,
        limit=limit,
        serialize=True,
    )

    return {
        "jobs": rows,
        "count": len(
            rows
        ),
    }


def job(
    user_id: Any,
    job_id: str,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.view",
    )

    school_id = sid(
        member
    )

    document = queue_get(
        job_id,
        school_id=school_id,
        serialize=True,
    )

    if not document:
        raise APIError(
            "Synchronization job not found.",
            404,
            "sync_job_not_found",
        )

    return {
        "job": document
    }


# =========================================================
# JOB CONTROL
# =========================================================

def pause_job(
    user_id: Any,
    job_id: str,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.import",
    )

    school_id = sid(
        member
    )

    document = queue_get(
        job_id,
        school_id=school_id,
    )

    if not document:
        raise APIError(
            "Synchronization job not found.",
            404,
            "sync_job_not_found",
        )

    updated = queue_pause(
        job_id,
        reason=reason,
    )

    if not updated:
        raise APIError(
            "Synchronization job cannot be paused.",
            409,
            "sync_job_pause_failed",
        )

    return {
        "job": ser(
            updated
        )
    }


def resume_job(
    user_id: Any,
    job_id: str,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.import",
    )

    school_id = sid(
        member
    )

    document = queue_get(
        job_id,
        school_id=school_id,
    )

    if not document:
        raise APIError(
            "Synchronization job not found.",
            404,
            "sync_job_not_found",
        )

    updated = queue_resume(
        job_id
    )

    if not updated:
        raise APIError(
            "Synchronization job cannot be resumed.",
            409,
            "sync_job_resume_failed",
        )

    return {
        "job": ser(
            updated
        )
    }


def cancel_job(
    user_id: Any,
    job_id: str,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.import",
    )

    school_id = sid(
        member
    )

    document = queue_get(
        job_id,
        school_id=school_id,
    )

    if not document:
        raise APIError(
            "Synchronization job not found.",
            404,
            "sync_job_not_found",
        )

    updated = queue_cancel(
        job_id,
        reason=reason,
        cancelled_by=user_id,
    )

    if not updated:
        raise APIError(
            "Synchronization job cannot be cancelled.",
            409,
            "sync_job_cancel_failed",
        )

    return {
        "job": ser(
            updated
        )
    }


def retry_job(
    user_id: Any,
    job_id: str,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.import",
    )

    school_id = sid(
        member
    )

    document = queue_get(
        job_id,
        school_id=school_id,
    )

    if not document:
        raise APIError(
            "Synchronization job not found.",
            404,
            "sync_job_not_found",
        )

    max_retries = _safe_int(
        _dict(
            document.get(
                "payload"
            )
        ).get(
            "max_retries"
        ),
        5,
    )

    updated = queue_retry(
        job_id,
        reason=(
            f"Manual retry requested by {user_id}"
        ),
        max_retries=max_retries,
    )

    if not updated:
        raise APIError(
            "Synchronization job cannot be retried.",
            409,
            "sync_job_retry_failed",
        )

    return {
        "job": ser(
            updated
        )
    }


# =========================================================
# CONNECTION HEARTBEAT
# =========================================================

def heartbeat(
    user_id: Any,
    connection_id: str,
    job_id: Optional[str] = None,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.import",
    )

    school_id = sid(
        member
    )

    connection = _connection_by_id(
        school_id,
        connection_id,
    )

    if not connection:
        raise APIError(
            "Synchronization connection not found.",
            404,
            "sync_connection_not_found",
        )

    # Verify the connection is still usable.
    if not connection_is_usable(
        connection
    ):
        raise APIError(
            "Synchronization connection is not active.",
            403,
            "sync_connection_unavailable",
        )

    _touch_connection(
        school_id,
        connection,
    )

    updated_job = None

    if job_id:
        updated_job = queue_heartbeat(
            job_id,
            worker_id="http-ingest",
        )

    return {
        "connection": _safe_connection_response(
            connection
        ),
        "job": ser(
            updated_job
        ),
    }


# =========================================================
# RECOVER STALE JOBS
# =========================================================

def recover_jobs(
    user_id: Any,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.import",
    )

    school_id = sid(
        member
    )

    result = queue_recover_stale(
        school_id
    )

    return result


# =========================================================
# SYNC STATUS
# =========================================================

def sync_status(
    user_id: Any,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.view",
    )

    school_id = sid(
        member
    )

    connections = list(
        collection(
            CONNECTIONS
        )
        .find(
            {
                "school_id": school_id
            }
        )
        .sort(
            "created_at",
            -1,
        )
    )

    open_conflicts = collection(
        CONFLICTS
    ).count_documents(
        {
            "school_id": school_id,
            "status": "open",
        }
    )

    queued = collection(
        JOBS
    ).count_documents(
        {
            "school_id": school_id,
            "status": "queued",
        }
    )

    running = collection(
        JOBS
    ).count_documents(
        {
            "school_id": school_id,
            "status": "running",
        }
    )

    failed = collection(
        JOBS
    ).count_documents(
        {
            "school_id": school_id,
            "status": "failed",
        }
    )

    completed = collection(
        JOBS
    ).count_documents(
        {
            "school_id": school_id,
            "status": {
                "$in": [
                    "completed",
                    "completed_with_errors",
                ]
            },
        }
    )

    return {
        "school_id": school_id,
        "connections": [
            _safe_connection_response(
                connection
            )
            for connection in connections
        ],
        "summary": {
            "connections": len(
                connections
            ),
            "active_connections": sum(
                1
                for connection in connections
                if connection.get(
                    "status"
                ) == "active"
            ),
            "open_conflicts": open_conflicts,
            "queued_jobs": queued,
            "running_jobs": running,
            "failed_jobs": failed,
            "completed_jobs": completed,
        },
    }


# =========================================================
# DEVICE REGISTRATION
# =========================================================

def register_device(
    user_id: Any,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.import",
    )

    school_id = sid(
        member
    )

    data = _dict(
        payload
    )

    name = (
        _text(
            data.get(
                "name"
            )
        )
        or "School Desktop"
    )

    platform = (
        _text(
            data.get(
                "platform"
            )
        )
        or "windows"
    ).lower()

    if platform not in SUPPORTED_PLATFORMS:
        raise APIError(
            "Unsupported synchronization platform.",
            422,
            "invalid_sync_platform",
        )

    device_id = _text(
        data.get(
            "device_id"
        )
    )

    if not device_id:
        raise APIError(
            "device_id is required.",
            422,
            "device_id_required",
        )

    existing = collection(
        DEVICES
    ).find_one(
        {
            "school_id": school_id,
            "device_id": device_id,
        }
    )

    if existing:
        updated = collection(
            DEVICES
        ).find_one_and_update(
            {
                "_id": existing[
                    "_id"
                ]
            },
            {
                "$set": {
                    "name": name,
                    "platform": platform,
                    "client_version": _text(
                        data.get(
                            "client_version"
                        )
                    ),
                    "capabilities": _list(
                        data.get(
                            "capabilities"
                        )
                    ),
                    "metadata": _dict(
                        data.get(
                            "metadata"
                        )
                    ),
                    "status": "active",
                    "last_seen_at": now_utc(),
                    "updated_at": now_utc(),
                    "last_error": None,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

        return {
            "device": ser(
                updated
            )
        }

    try:
        document = device_doc(
            school_id,
            name,
            platform,
            user_id,
            device_id=device_id,
            client_version=_text(
                data.get(
                    "client_version"
                )
            ),
            protocol_version=_text(
                data.get(
                    "protocol_version"
                )
            )
            or "2.0",
            capabilities=data.get(
                "capabilities"
            ),
            metadata=data.get(
                "metadata"
            ),
        )

    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "sync_device_validation_error",
        )

    result = collection(
        DEVICES
    ).insert_one(
        document
    )

    document[
        "_id"
    ] = result.inserted_id

    return {
        "device": ser(
            document
        )
    }


# =========================================================
# DEVICE LIST
# =========================================================

def list_devices(
    user_id: Any,
) -> dict[str, Any]:
    member = authorize(
        user_id,
        "sync.view",
    )

    school_id = sid(
        member
    )

    rows = list(
        collection(
            DEVICES
        )
        .find(
            {
                "school_id": school_id
            }
        )
        .sort(
            "created_at",
            -1,
        )
    )

    return {
        "devices": _serialize_many(
            rows
        )
    }