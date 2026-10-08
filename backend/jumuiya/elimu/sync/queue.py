# backend/jumuiya/elimu/sync/queue.py

from __future__ import annotations

"""
Persistent synchronization job queue for the Elimu Sync subsystem.

Features
--------
- atomic job claiming;
- logical job IDs;
- resumable checkpoints;
- retry support;
- pause / resume;
- cancellation;
- stale-job recovery;
- heartbeat/lease renewal;
- progress counters;
- safe serialization;
- backward-compatible enqueue / claim / complete / fail helpers.

MongoDB collection
------------------
Uses:

    jumuiya_elimu_sync_jobs

Jobs are school-scoped and never claimed across schools.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from backend.jumuiya.core.database import collection

from .models import (
    JOBS,
    JOB_STATUSES,
    SYNC_DIRECTIONS,
    TRIGGER_TYPES,
    job_doc,
)


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_LEASE_SECONDS = 300
MIN_LEASE_SECONDS = 30
MAX_LEASE_SECONDS = 60 * 60

DEFAULT_MAX_RETRIES = 5

TERMINAL_STATUSES = {
    "completed",
    "completed_with_errors",
    "failed",
    "cancelled",
}

RESUMABLE_STATUSES = {
    "queued",
    "paused",
    "running",
}


# =========================================================
# TIME
# =========================================================

def now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _utc(value: Any) -> Optional[datetime]:
    if not isinstance(
        value,
        datetime,
    ):
        return None

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _lease_expiry(
    seconds: int = DEFAULT_LEASE_SECONDS,
) -> datetime:
    seconds = max(
        MIN_LEASE_SECONDS,
        min(
            int(seconds),
            MAX_LEASE_SECONDS,
        ),
    )

    return now() + timedelta(
        seconds=seconds
    )


# =========================================================
# BASIC HELPERS
# =========================================================

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
    return (
        dict(value)
        if isinstance(
            value,
            Mapping,
        )
        else {}
    )


# =========================================================
# JOB ID / MONGO ID SUPPORT
# =========================================================

def _job_query(
    job_id: Any,
) -> dict[str, Any]:
    """
    Support both:

        Mongo ObjectId
        logical job_id

    This keeps the queue compatible with the original implementation
    while moving the system toward portable logical IDs.
    """
    if isinstance(
        job_id,
        ObjectId,
    ):
        return {
            "_id": job_id
        }

    text = _text(
        job_id
    )

    if not text:
        raise ValueError(
            "job_id is required."
        )

    if ObjectId.is_valid(
        text
    ):
        return {
            "$or": [
                {
                    "_id": ObjectId(
                        text
                    )
                },
                {
                    "job_id": text
                },
            ]
        }

    return {
        "job_id": text
    }


# =========================================================
# SERIALIZATION
# =========================================================

def _serialize_value(
    value: Any,
) -> Any:
    if isinstance(
        value,
        ObjectId,
    ):
        return str(value)

    if isinstance(
        value,
        datetime,
    ):
        return _utc(
            value
        ).isoformat()

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(key): _serialize_value(
                item
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        (list, tuple),
    ):
        return [
            _serialize_value(
                item
            )
            for item in value
        ]

    return value


def serialize_job(
    document: Optional[
        Mapping[str, Any]
    ],
) -> Optional[dict[str, Any]]:
    if not document:
        return None

    return _serialize_value(
        dict(document)
    )


# =========================================================
# JOB STATE HELPERS
# =========================================================

def is_terminal(
    document: Optional[
        Mapping[str, Any]
    ],
) -> bool:
    if not document:
        return False

    return _text(
        document.get(
            "status"
        )
    ).lower() in TERMINAL_STATUSES


def is_resumable(
    document: Optional[
        Mapping[str, Any]
    ],
) -> bool:
    if not document:
        return False

    return _text(
        document.get(
            "status"
        )
    ).lower() in RESUMABLE_STATUSES


def is_lease_expired(
    document: Optional[
        Mapping[str, Any]
    ],
) -> bool:
    if not document:
        return True

    expires_at = _utc(
        document.get(
            "lease_expires_at"
        )
    )

    if expires_at is None:
        return True

    return expires_at <= now()


# =========================================================
# ENQUEUE
# =========================================================

def enqueue(
    school_id: Any,
    kind: str,
    payload: Optional[
        Mapping[str, Any]
    ],
    created_by: Any,
    *,
    connection_id: Any = None,
    device_id: Any = None,
    direction: Optional[str] = None,
    trigger: str = "manual",
    cursor_before: Any = None,
) -> str:
    """
    Create a persistent synchronization job.

    Returns the logical `job_id`, not Mongo's internal _id.

    The old function signature remains valid:

        enqueue(
            school_id,
            kind,
            payload,
            created_by,
        )
    """
    school = _text(
        school_id
    )

    if not school:
        raise ValueError(
            "school_id is required."
        )

    creator = _text(
        created_by
    )

    if not creator:
        raise ValueError(
            "created_by is required."
        )

    document = job_doc(
        school,
        kind,
        creator,
        connection_id=connection_id,
        device_id=device_id,
        direction=direction,
        trigger=trigger,
        payload=payload,
        cursor_before=cursor_before,
    )

    created = collection(
        JOBS
    ).insert_one(
        document
    )

    # Store the Mongo identity too for operational diagnostics.
    collection(
        JOBS
    ).update_one(
        {
            "_id": created.inserted_id
        },
        {
            "$set": {
                "mongo_job_id": str(
                    created.inserted_id
                ),
            }
        },
    )

    return str(
        document[
            "job_id"
        ]
    )


# =========================================================
# GET JOB
# =========================================================

def get(
    job_id: Any,
    *,
    school_id: Any = None,
    serialize: bool = False,
) -> Optional[
    dict[str, Any]
]:
    """
    Retrieve a single synchronization job.

    Optional school_id adds an ownership boundary.
    """
    query = _job_query(
        job_id
    )

    if school_id is not None:
        query = {
            "$and": [
                query,
                {
                    "school_id": _text(
                        school_id
                    )
                },
            ]
        }

    document = collection(
        JOBS
    ).find_one(
        query
    )

    if not document:
        return None

    result = dict(
        document
    )

    return (
        serialize_job(
            result
        )
        if serialize
        else result
    )


# =========================================================
# LIST JOBS
# =========================================================

def list_jobs(
    school_id: Any,
    *,
    status: Optional[str] = None,
    connection_id: Any = None,
    device_id: Any = None,
    limit: int = 50,
    serialize: bool = False,
) -> list[
    dict[str, Any]
]:
    """
    Return the most recent jobs for one school.
    """
    school = _text(
        school_id
    )

    if not school:
        raise ValueError(
            "school_id is required."
        )

    limit = max(
        1,
        min(
            _safe_int(
                limit,
                50,
            ),
            500,
        ),
    )

    query: dict[str, Any] = {
        "school_id": school
    }

    if status:
        normalized_status = _text(
            status
        ).lower()

        if normalized_status not in JOB_STATUSES:
            raise ValueError(
                "Invalid synchronization job status."
            )

        query[
            "status"
        ] = normalized_status

    if connection_id is not None:
        query[
            "connection_id"
        ] = _text(
            connection_id
        )

    if device_id is not None:
        query[
            "device_id"
        ] = _text(
            device_id
        )

    cursor = (
        collection(
            JOBS
        )
        .find(
            query
        )
        .sort(
            "created_at",
            -1,
        )
        .limit(
            limit
        )
    )

    result = [
        dict(
            document
        )
        for document in cursor
    ]

    if serialize:
        return [
            serialize_job(
                document
            )
            for document in result
        ]

    return result


# =========================================================
# CLAIM
# =========================================================

def claim(
    school_id: Any,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    worker_id: Optional[str] = None,
) -> Optional[
    dict[str, Any]
]:
    """
    Atomically claim the oldest available job.

    A job is claimable when:

        queued

    OR:

        running + expired lease

    OR:

        paused + explicitly resumed before claiming.

    Only one worker can successfully transition a particular job
    into running at a time.
    """
    school = _text(
        school_id
    )

    if not school:
        raise ValueError(
            "school_id is required."
        )

    timestamp = now()

    expired_running = {
        "status": "running",
        "lease_expires_at": {
            "$lte": timestamp
        },
    }

    query = {
        "school_id": school,
        "$or": [
            {
                "status": "queued"
            },
            expired_running,
        ],
    }

    lease_expires = _lease_expiry(
        lease_seconds
    )

    worker = (
        _text(
            worker_id
        )
        or None
    )

    update = {
        "$set": {
            "status": "running",
            "started_at": timestamp,
            "updated_at": timestamp,
            "last_heartbeat_at": timestamp,
            "lease_expires_at": lease_expires,
            "worker_id": worker,
            "error": None,
        },
        "$inc": {
            "claim_count": 1,
        },
    }

    document = collection(
        JOBS
    ).find_one_and_update(
        query,
        update,
        sort=[
            (
                "created_at",
                1,
            )
        ],
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        return None

    return dict(
        document
    )


# =========================================================
# HEARTBEAT
# =========================================================

def heartbeat(
    job_id: Any,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    worker_id: Optional[str] = None,
) -> Optional[
    dict[str, Any]
]:
    """
    Renew a running job's lease.

    This prevents a long synchronization from being reclaimed by
    another worker while it is still alive.
    """
    query = {
        **_job_query(
            job_id
        ),
        "status": "running",
    }

    if worker_id:
        query[
            "worker_id"
        ] = _text(
            worker_id
        )

    timestamp = now()

    document = collection(
        JOBS
    ).find_one_and_update(
        query,
        {
            "$set": {
                "last_heartbeat_at": timestamp,
                "lease_expires_at": _lease_expiry(
                    lease_seconds
                ),
                "updated_at": timestamp,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        return None

    return dict(
        document
    )


# =========================================================
# CHECKPOINT
# =========================================================

def checkpoint(
    job_id: Any,
    *,
    checkpoint_data: Optional[
        Mapping[str, Any]
    ] = None,
    cursor_after: Any = None,
    resume_token: Any = None,
    last_entity_type: Optional[str] = None,
    last_entity_key: Optional[str] = None,
    processed_records: Optional[int] = None,
    created_records: Optional[int] = None,
    updated_records: Optional[int] = None,
    deleted_records: Optional[int] = None,
    conflict_records: Optional[int] = None,
    error_records: Optional[int] = None,
    worker_id: Optional[str] = None,
) -> Optional[
    dict[str, Any]
]:
    """
    Persist a resumable checkpoint.

    This is intentionally a single atomic update so a process can safely
    checkpoint after each batch.
    """
    query = {
        **_job_query(
            job_id
        ),
        "status": {
            "$in": [
                "queued",
                "running",
                "paused",
            ]
        },
    }

    if worker_id:
        query[
            "worker_id"
        ] = _text(
            worker_id
        )

    update_set: dict[str, Any] = {
        "updated_at": now(),
    }

    if checkpoint_data is not None:
        update_set[
            "checkpoint"
        ] = _dict(
            checkpoint_data
        )

    if cursor_after is not None:
        update_set[
            "cursor_after"
        ] = cursor_after

    if resume_token is not None:
        update_set[
            "resume_token"
        ] = resume_token

    if last_entity_type is not None:
        update_set[
            "last_entity_type"
        ] = _text(
            last_entity_type
        )

    if last_entity_key is not None:
        update_set[
            "last_entity_key"
        ] = _text(
            last_entity_key
        )

    counters = {
        "processed_records": processed_records,
        "created_records": created_records,
        "updated_records": updated_records,
        "deleted_records": deleted_records,
        "conflict_records": conflict_records,
        "error_records": error_records,
    }

    for field, value in counters.items():
        if value is not None:
            update_set[
                field
            ] = max(
                0,
                _safe_int(
                    value
                ),
            )

    document = collection(
        JOBS
    ).find_one_and_update(
        query,
        {
            "$set": update_set
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        return None

    return dict(
        document
    )


# =========================================================
# INCREMENT PROGRESS
# =========================================================

def increment_progress(
    job_id: Any,
    *,
    processed_records: int = 0,
    created_records: int = 0,
    updated_records: int = 0,
    deleted_records: int = 0,
    conflict_records: int = 0,
    error_records: int = 0,
) -> Optional[
    dict[str, Any]
]:
    """
    Increment counters without replacing a concurrently updated
    checkpoint.
    """
    update = {
        "$inc": {
            "processed_records": max(
                0,
                int(
                    processed_records
                ),
            ),
            "created_records": max(
                0,
                int(
                    created_records
                ),
            ),
            "updated_records": max(
                0,
                int(
                    updated_records
                ),
            ),
            "deleted_records": max(
                0,
                int(
                    deleted_records
                ),
            ),
            "conflict_records": max(
                0,
                int(
                    conflict_records
                ),
            ),
            "error_records": max(
                0,
                int(
                    error_records
                ),
            ),
        },
        "$set": {
            "updated_at": now(),
        },
    }

    document = collection(
        JOBS
    ).find_one_and_update(
        {
            **_job_query(
                job_id
            ),
            "status": {
                "$in": [
                    "running",
                    "paused",
                ]
            },
        },
        update,
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        return None

    return dict(
        document
    )


# =========================================================
# PAUSE
# =========================================================

def pause(
    job_id: Any,
    *,
    reason: Optional[str] = None,
    worker_id: Optional[str] = None,
) -> Optional[
    dict[str, Any]
]:
    """
    Pause a running job without losing its checkpoint.
    """
    query = {
        **_job_query(
            job_id
        ),
        "status": "running",
    }

    if worker_id:
        query[
            "worker_id"
        ] = _text(
            worker_id
        )

    update_set = {
        "status": "paused",
        "updated_at": now(),
        "paused_at": now(),
    }

    if reason:
        update_set[
            "pause_reason"
        ] = _text(
            reason
        )

    document = collection(
        JOBS
    ).find_one_and_update(
        query,
        {
            "$set": update_set,
            "$unset": {
                "lease_expires_at": "",
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        return None

    return dict(
        document
    )


# =========================================================
# RESUME
# =========================================================

def resume(
    job_id: Any,
) -> Optional[
    dict[str, Any]
]:
    """
    Put a paused job back into the queued state.

    Existing checkpoint/cursor information is retained.
    """
    document = collection(
        JOBS
    ).find_one_and_update(
        {
            **_job_query(
                job_id
            ),
            "status": "paused",
        },
        {
            "$set": {
                "status": "queued",
                "updated_at": now(),
                "resumed_at": now(),
            },
            "$unset": {
                "worker_id": "",
                "lease_expires_at": "",
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        return None

    return dict(
        document
    )


# =========================================================
# CANCEL
# =========================================================

def cancel(
    job_id: Any,
    *,
    reason: Optional[str] = None,
    cancelled_by: Any = None,
) -> Optional[
    dict[str, Any]
]:
    """
    Cancel a queued/running/paused job.

    The checkpoint remains available for auditing, but the job will
    no longer be claimable.
    """
    query = {
        **_job_query(
            job_id
        ),
        "status": {
            "$in": [
                "queued",
                "running",
                "paused",
            ]
        },
    }

    update_set = {
        "status": "cancelled",
        "cancelled_at": now(),
        "updated_at": now(),
    }

    if reason:
        update_set[
            "cancel_reason"
        ] = _text(
            reason
        )

    if cancelled_by is not None:
        update_set[
            "cancelled_by"
        ] = _text(
            cancelled_by
        )

    document = collection(
        JOBS
    ).find_one_and_update(
        query,
        {
            "$set": update_set,
            "$unset": {
                "lease_expires_at": "",
                "worker_id": "",
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        return None

    return dict(
        document
    )


# =========================================================
# RETRY
# =========================================================

def retry(
    job_id: Any,
    *,
    reason: Optional[str] = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> Optional[
    dict[str, Any]
]:
    """
    Requeue a failed job when its retry budget has not been exhausted.

    The same job ID is retained so its full lifecycle remains auditable.
    """
    maximum = max(
        0,
        min(
            _safe_int(
                max_retries,
                DEFAULT_MAX_RETRIES,
            ),
            20,
        ),
    )

    existing = get(
        job_id
    )

    if not existing:
        return None

    current_retry_count = _safe_int(
        existing.get(
            "retry_count"
        ),
        0,
    )

    if current_retry_count >= maximum:
        return None

    if existing.get(
        "status"
    ) not in {
        "failed",
        "completed_with_errors",
    }:
        return None

    update_set = {
        "status": "queued",
        "retry_count": (
            current_retry_count
            + 1
        ),
        "updated_at": now(),
        "retry_reason": (
            _text(reason)
            if reason
            else None
        ),
        "error": None,
    }

    document = collection(
        JOBS
    ).find_one_and_update(
        {
            **_job_query(
                job_id
            ),
            "status": {
                "$in": [
                    "failed",
                    "completed_with_errors",
                ]
            },
        },
        {
            "$set": update_set,
            "$unset": {
                "started_at": "",
                "finished_at": "",
                "worker_id": "",
                "lease_expires_at": "",
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        return None

    return dict(
        document
    )


# =========================================================
# COMPLETE
# =========================================================

def complete(
    job_id: Any,
    result: Optional[
        Mapping[str, Any]
    ] = None,
    *,
    completed_with_errors: bool = False,
    cursor_after: Any = None,
) -> Optional[
    dict[str, Any]
]:
    """
    Complete a synchronization job.

    A job can finish as either:

        completed

    or:

        completed_with_errors
    """
    status = (
        "completed_with_errors"
        if completed_with_errors
        else "completed"
    )

    update_set: dict[str, Any] = {
        "status": status,
        "result": _dict(
            result
        ),
        "finished_at": now(),
        "updated_at": now(),
    }

    if cursor_after is not None:
        update_set[
            "cursor_after"
        ] = cursor_after

    document = collection(
        JOBS
    ).find_one_and_update(
        {
            **_job_query(
                job_id
            ),
            "status": {
                "$in": [
                    "running",
                    "paused",
                ]
            },
        },
        {
            "$set": update_set,
            "$unset": {
                "lease_expires_at": "",
                "worker_id": "",
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        return None

    return dict(
        document
    )


# =========================================================
# FAIL
# =========================================================

def fail(
    job_id: Any,
    error: Any,
    *,
    retryable: bool = True,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> Optional[
    dict[str, Any]
]:
    """
    Mark a job as failed.

    By default, a failed job becomes retryable while preserving its
    checkpoint. Automatic retry itself is deliberately explicit through
    retry(), so workers do not accidentally create infinite retry loops.
    """
    existing = get(
        job_id
    )

    if not existing:
        return None

    retry_count = _safe_int(
        existing.get(
            "retry_count"
        ),
        0,
    )

    max_retry = max(
        0,
        min(
            _safe_int(
                max_retries,
                DEFAULT_MAX_RETRIES,
            ),
            20,
        ),
    )

    exhausted = (
        retry_count
        >= max_retry
    )

    update_set = {
        "status": "failed",
        "error": _text(
            error
        ),
        "finished_at": now(),
        "updated_at": now(),
        "retryable": bool(
            retryable
            and not exhausted
        ),
    }

    document = collection(
        JOBS
    ).find_one_and_update(
        {
            **_job_query(
                job_id
            ),
            "status": {
                "$in": [
                    "running",
                    "paused",
                    "queued",
                ]
            },
        },
        {
            "$set": update_set,
            "$unset": {
                "lease_expires_at": "",
                "worker_id": "",
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        return None

    return dict(
        document
    )


# =========================================================
# RECOVER STALE JOBS
# =========================================================

def recover_stale(
    school_id: Any,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """
    Recover running jobs whose worker lease expired.

    This is essential for desktop/offline environments because a
    process may terminate while synchronizing without getting the
    opportunity to call fail().
    """
    school = _text(
        school_id
    )

    if not school:
        raise ValueError(
            "school_id is required."
        )

    timestamp = now()

    stale_jobs = list(
        collection(
            JOBS
        ).find(
            {
                "school_id": school,
                "status": "running",
                "lease_expires_at": {
                    "$lte": timestamp
                },
            }
        )
    )

    recovered = 0
    exhausted = 0

    for job in stale_jobs:
        retry_count = _safe_int(
            job.get(
                "retry_count"
            ),
            0,
        )

        if retry_count < max_retries:
            collection(
                JOBS
            ).update_one(
                {
                    "_id": job[
                        "_id"
                    ],
                    "status": "running",
                },
                {
                    "$set": {
                        "status": "queued",
                        "retryable": True,
                        "updated_at": timestamp,
                        "recovered_at": timestamp,
                        "recovery_reason": (
                            "worker_lease_expired"
                        ),
                    },
                    "$inc": {
                        "retry_count": 1,
                    },
                    "$unset": {
                        "worker_id": "",
                        "lease_expires_at": "",
                        "started_at": "",
                    },
                },
            )

            recovered += 1

        else:
            collection(
                JOBS
            ).update_one(
                {
                    "_id": job[
                        "_id"
                    ],
                    "status": "running",
                },
                {
                    "$set": {
                        "status": "failed",
                        "retryable": False,
                        "error": (
                            "Synchronization worker lease expired "
                            "and retry limit was exhausted."
                        ),
                        "finished_at": timestamp,
                        "updated_at": timestamp,
                    },
                    "$unset": {
                        "worker_id": "",
                        "lease_expires_at": "",
                    },
                },
            )

            exhausted += 1

    return {
        "school_id": school,
        "found": len(
            stale_jobs
        ),
        "recovered": recovered,
        "exhausted": exhausted,
    }


# =========================================================
# RESUME INFORMATION
# =========================================================

def resume_state(
    job_id: Any,
) -> Optional[
    dict[str, Any]
]:
    """
    Return only the information a worker needs to resume a job.
    """
    document = get(
        job_id
    )

    if not document:
        return None

    return {
        "job_id": document.get(
            "job_id"
        ),
        "status": document.get(
            "status"
        ),
        "cursor_before": document.get(
            "cursor_before"
        ),
        "cursor_after": document.get(
            "cursor_after"
        ),
        "checkpoint": document.get(
            "checkpoint"
        ),
        "resume_token": document.get(
            "resume_token"
        ),
        "last_entity_type": document.get(
            "last_entity_type"
        ),
        "last_entity_key": document.get(
            "last_entity_key"
        ),
        "processed_records": _safe_int(
            document.get(
                "processed_records"
            ),
            0,
        ),
        "created_records": _safe_int(
            document.get(
                "created_records"
            ),
            0,
        ),
        "updated_records": _safe_int(
            document.get(
                "updated_records"
            ),
            0,
        ),
        "deleted_records": _safe_int(
            document.get(
                "deleted_records"
            ),
            0,
        ),
        "conflict_records": _safe_int(
            document.get(
                "conflict_records"
            ),
            0,
        ),
        "error_records": _safe_int(
            document.get(
                "error_records"
            ),
            0,
        ),
        "retry_count": _safe_int(
            document.get(
                "retry_count"
            ),
            0,
        ),
    }


# =========================================================
# JOB SUMMARY
# =========================================================

def summary(
    school_id: Any,
) -> dict[str, Any]:
    """
    Return queue health statistics for a school.
    """
    school = _text(
        school_id
    )

    if not school:
        raise ValueError(
            "school_id is required."
        )

    jobs = collection(
        JOBS
    )

    return {
        "school_id": school,
        "queued": jobs.count_documents(
            {
                "school_id": school,
                "status": "queued",
            }
        ),
        "running": jobs.count_documents(
            {
                "school_id": school,
                "status": "running",
            }
        ),
        "paused": jobs.count_documents(
            {
                "school_id": school,
                "status": "paused",
            }
        ),
        "completed": jobs.count_documents(
            {
                "school_id": school,
                "status": "completed",
            }
        ),
        "completed_with_errors": jobs.count_documents(
            {
                "school_id": school,
                "status": "completed_with_errors",
            }
        ),
        "failed": jobs.count_documents(
            {
                "school_id": school,
                "status": "failed",
            }
        ),
        "cancelled": jobs.count_documents(
            {
                "school_id": school,
                "status": "cancelled",
            }
        ),
    }