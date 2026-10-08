# backend/jumuiya/elimu/automation/jobs.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId

from backend.jumuiya.core.database import collection

from .constants import (
    DEFAULT_LOCK_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_RETRY_DELAY_SECONDS,
    JOB_CANCELLED,
    JOB_FAILED,
    JOB_PENDING,
    JOB_RETRYING,
    JOB_RUNNING,
    JOB_SUCCEEDED,
    JOBS,
    RULES,
)


# ============================================================
# COLLECTIONS
# ============================================================

JOBS = "jumuiya_elimu_automation_jobs"



ACTIVE_STATUSES = {
    JOB_PENDING,
    JOB_RUNNING,
    JOB_RETRYING,
}

TERMINAL_STATUSES = {
    JOB_SUCCEEDED,
    JOB_FAILED,
    JOB_CANCELLED,
}

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 60
DEFAULT_LOCK_SECONDS = 300


# ============================================================
# TIME / SERIALIZATION HELPERS
# ============================================================

def now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def _iso(value: Any) -> Any:
    """Convert datetime values to ISO strings for API responses."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()

    return value


def _serialize(document: dict | None) -> dict | None:
    """
    Convert a MongoDB document into a JSON-safe dictionary.
    """
    if not document:
        return None

    result = dict(document)

    if "_id" in result:
        result["_id"] = str(result["_id"])

    for key in (
        "created_at",
        "updated_at",
        "scheduled_at",
        "started_at",
        "completed_at",
        "next_retry_at",
        "locked_until",
    ):
        if key in result:
            result[key] = _iso(result[key])

    return result


def _oid(value: Any) -> Any:
    """
    Convert a valid ObjectId string into ObjectId.

    If conversion fails, return the original value so that
    deployments using string identifiers remain compatible.
    """
    if isinstance(value, ObjectId):
        return value

    try:
        return ObjectId(str(value))
    except Exception:
        return value


# ============================================================
# RULE HELPERS
# ============================================================

def due_rules(school_id: str | Any) -> list[dict]:
    """
    Return enabled automation rules belonging to a school.

    Rules are sorted deterministically so that automation
    execution order is predictable.
    """
    return list(
        collection(RULES)
        .find(
            {
                "school_id": str(school_id),
                "enabled": True,
            }
        )
        .sort(
            [
                ("created_at", 1),
                ("_id", 1),
            ]
        )
    )


# ============================================================
# TRIGGER MATCHING
# ============================================================

def _normalize_trigger(trigger: Any) -> str:
    return str(trigger or "").strip().lower()


def trigger_matches(
    rule: dict,
    context: dict | None = None,
) -> bool:
    """
    Determine whether an automation rule should generate a job.

    Supported context examples:

        {
            "trigger": "daily",
            "schedule": "daily"
        }

        {
            "trigger": "attendance.recorded"
        }

        {
            "event": "student.created"
        }

        {
            "trigger": "sync.failed"
        }

    Rules without a trigger are ignored.
    """
    context = context or {}

    rule_trigger = _normalize_trigger(rule.get("trigger"))

    if not rule_trigger:
        return False

    context_trigger = _normalize_trigger(
        context.get("trigger")
        or context.get("event")
        or context.get("schedule")
    )

    # Scheduled/manual execution without an explicit context
    # can still generate jobs for schedule-compatible rules.
    if not context_trigger:
        return True

    if rule_trigger == context_trigger:
        return True

    # Allow wildcard rules:
    #
    # attendance.*
    # sync.*
    # student.*
    #
    if rule_trigger.endswith(".*"):
        prefix = rule_trigger[:-2]

        if context_trigger.startswith(prefix + "."):
            return True

    # Allow a generic "event" trigger to accept event contexts.
    if rule_trigger == "event" and context.get("event"):
        return True

    # Allow a generic "schedule" trigger to accept schedule contexts.
    if rule_trigger == "schedule" and context.get("schedule"):
        return True

    return False


# ============================================================
# IDEMPOTENCY
# ============================================================

def build_idempotency_key(
    school_id: str | Any,
    rule: dict,
    context: dict | None = None,
) -> str:
    """
    Generate a deterministic idempotency key.

    Explicit context event IDs are preferred.

    Examples:

        school:rule:event

        school:rule:daily:2026-10-08
    """
    context = context or {}

    school = str(school_id)
    rule_id = str(rule.get("_id"))

    event_id = (
        context.get("event_id")
        or context.get("idempotency_key")
        or context.get("source_event_id")
    )

    if event_id:
        return f"{school}:{rule_id}:event:{event_id}"

    schedule = context.get("schedule")

    if schedule:
        day = now().date().isoformat()
        return f"{school}:{rule_id}:schedule:{schedule}:{day}"

    trigger = (
        context.get("trigger")
        or context.get("event")
        or context.get("schedule")
        or rule.get("trigger")
        or "manual"
    )

    return f"{school}:{rule_id}:{trigger}"


def find_existing_job(
    school_id: str | Any,
    idempotency_key: str,
) -> dict | None:
    """
    Find an existing job with the same idempotency key.

    This prevents repeated event delivery from generating
    duplicate automation jobs.
    """
    return collection(JOBS).find_one(
        {
            "school_id": str(school_id),
            "idempotency_key": str(idempotency_key),
        }
    )


# ============================================================
# JOB CREATION
# ============================================================

def create_job(
    school_id: str | Any,
    rule: dict,
    context: dict | None = None,
) -> dict:
    """
    Create one durable automation job.

    The job is intentionally created as PENDING.

    Action execution is handled separately by the future
    Action Registry / executor layer.
    """
    context = dict(context or {})

    school = str(school_id)

    idempotency_key = build_idempotency_key(
        school,
        rule,
        context,
    )

    existing = find_existing_job(
        school,
        idempotency_key,
    )

    if existing:
        return _serialize(existing)

    timestamp = now()

    scheduled_at = context.get("scheduled_at")

    if not isinstance(scheduled_at, datetime):
        scheduled_at = timestamp

    document = {
        "school_id": school,
        "rule_id": str(rule.get("_id")),
        "rule_name": rule.get("name"),
        "trigger": rule.get("trigger"),
        "action": rule.get("action"),
        "payload": context,
        "status": STATUS_PENDING,
        "attempt": 0,
        "max_attempts": int(
            rule.get(
                "max_attempts",
                DEFAULT_MAX_ATTEMPTS,
            )
        ),
        "scheduled_at": scheduled_at,
        "started_at": None,
        "completed_at": None,
        "next_retry_at": None,
        "locked_until": None,
        "error": None,
        "result": None,
        "idempotency_key": idempotency_key,
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    result = collection(JOBS).insert_one(document)

    document["_id"] = result.inserted_id

    return _serialize(document)


# ============================================================
# JOB GENERATION
# ============================================================

def generate_jobs(
    school_id: str | Any,
    context: dict | None = None,
) -> list[dict]:
    """
    Evaluate enabled rules and create durable jobs for
    matching triggers.
    """
    school = str(school_id)
    context = dict(context or {})

    generated: list[dict] = []

    for rule in due_rules(school):
        if not trigger_matches(rule, context):
            continue

        job = create_job(
            school,
            rule,
            context,
        )

        generated.append(job)

    return generated


def run_due_jobs(
    school_id: str | Any,
    context: dict | None = None,
) -> dict:
    """
    Generate durable automation jobs for matching rules.

    Backward-compatible replacement for the original function.

    IMPORTANT:
        This function creates jobs.
        It does not execute actions yet.

    That separation allows us to introduce a safe Action Registry
    and executor in the next upgrade.
    """
    context = dict(context or {})

    jobs = generate_jobs(
        school_id,
        context,
    )

    return {
        "generated_at": now().isoformat(),
        "count": len(jobs),
        "jobs": jobs,
    }


# ============================================================
# SCHEDULED SCHOOL JOBS
# ============================================================

def daily_school_jobs(
    school_id: str | Any,
) -> dict:
    """
    Generate jobs for rules triggered by the daily schedule.
    """
    return run_due_jobs(
        school_id,
        {
            "trigger": "daily",
            "schedule": "daily",
            "scheduled_at": now(),
        },
    )


# ============================================================
# JOB RETRIEVAL
# ============================================================

def get_job(
    school_id: str | Any,
    job_id: str,
) -> dict | None:
    """
    Retrieve one automation job belonging to a school.
    """
    document = collection(JOBS).find_one(
        {
            "school_id": str(school_id),
            "_id": _oid(job_id),
        }
    )

    return _serialize(document)


def list_jobs(
    school_id: str | Any,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    List automation jobs for a school.
    """
    limit = max(1, min(int(limit or 100), 500))

    query: dict[str, Any] = {
        "school_id": str(school_id),
    }

    if status:
        query["status"] = str(status).strip().lower()

    documents = (
        collection(JOBS)
        .find(query)
        .sort(
            [
                ("created_at", -1),
                ("_id", -1),
            ]
        )
        .limit(limit)
    )

    return [
        _serialize(document)
        for document in documents
    ]


# ============================================================
# JOB CLAIMING
# ============================================================

def claim_job(
    school_id: str | Any,
    job_id: str,
    lock_seconds: int = DEFAULT_LOCK_SECONDS,
) -> dict | None:
    """
    Atomically claim a pending/retrying job.

    This prevents multiple workers from executing the same
    automation job simultaneously.
    """
    timestamp = now()
    locked_until = timestamp + timedelta(
        seconds=max(1, int(lock_seconds))
    )

    query = {
        "school_id": str(school_id),
        "_id": _oid(job_id),
        "status": {
            "$in": [
                STATUS_PENDING,
                STATUS_RETRYING,
            ]
        },
        "$or": [
            {
                "locked_until": None,
            },
            {
                "locked_until": {
                    "$lte": timestamp,
                }
            },
            {
                "locked_until": {
                    "$exists": False,
                }
            },
        ],
    }

    update = {
        "$set": {
            "status": STATUS_RUNNING,
            "started_at": timestamp,
            "locked_until": locked_until,
            "updated_at": timestamp,
        },
        "$inc": {
            "attempt": 1,
        },
    }

    document = collection(JOBS).find_one_and_update(
        query,
        update,
        return_document=True,
    )

    return _serialize(document)


# ============================================================
# JOB COMPLETION
# ============================================================

def complete_job(
    school_id: str | Any,
    job_id: str,
    result: Any = None,
) -> dict | None:
    """
    Mark a claimed job as successfully completed.
    """
    timestamp = now()

    document = collection(JOBS).find_one_and_update(
        {
            "school_id": str(school_id),
            "_id": _oid(job_id),
            "status": STATUS_RUNNING,
        },
        {
            "$set": {
                "status": STATUS_SUCCEEDED,
                "completed_at": timestamp,
                "updated_at": timestamp,
                "result": result,
                "error": None,
                "locked_until": None,
            }
        },
        return_document=True,
    )

    return _serialize(document)


# ============================================================
# JOB FAILURE / RETRY
# ============================================================

def fail_job(
    school_id: str | Any,
    job_id: str,
    error: Any,
    retry: bool = True,
    retry_delay_seconds: int = DEFAULT_RETRY_DELAY_SECONDS,
) -> dict | None:
    """
    Fail a running job.

    If retries remain, the job moves to RETRYING.

    Otherwise it becomes permanently FAILED.
    """
    timestamp = now()

    current = collection(JOBS).find_one(
        {
            "school_id": str(school_id),
            "_id": _oid(job_id),
        }
    )

    if not current:
        return None

    attempt = int(current.get("attempt", 0))
    max_attempts = int(
        current.get(
            "max_attempts",
            DEFAULT_MAX_ATTEMPTS,
        )
    )

    should_retry = (
        retry
        and attempt < max_attempts
    )

    if should_retry:
        next_retry_at = timestamp + timedelta(
            seconds=max(
                1,
                int(retry_delay_seconds),
            )
        )

        update = {
            "$set": {
                "status": STATUS_RETRYING,
                "next_retry_at": next_retry_at,
                "updated_at": timestamp,
                "error": str(error),
                "locked_until": None,
            }
        }

    else:
        update = {
            "$set": {
                "status": STATUS_FAILED,
                "completed_at": timestamp,
                "updated_at": timestamp,
                "error": str(error),
                "locked_until": None,
            }
        }

    document = collection(JOBS).find_one_and_update(
        {
            "school_id": str(school_id),
            "_id": _oid(job_id),
        },
        update,
        return_document=True,
    )

    return _serialize(document)


# ============================================================
# JOB CANCELLATION
# ============================================================

def cancel_job(
    school_id: str | Any,
    job_id: str,
    reason: str | None = None,
) -> dict | None:
    """
    Cancel a pending, retrying, or running job.
    """
    timestamp = now()

    document = collection(JOBS).find_one_and_update(
        {
            "school_id": str(school_id),
            "_id": _oid(job_id),
            "status": {
                "$in": list(ACTIVE_STATUSES),
            },
        },
        {
            "$set": {
                "status": STATUS_CANCELLED,
                "completed_at": timestamp,
                "updated_at": timestamp,
                "error": reason,
                "locked_until": None,
            }
        },
        return_document=True,
    )

    return _serialize(document)


# ============================================================
# RECOVERY
# ============================================================

def recover_stale_jobs(
    school_id: str | Any,
    lock_timeout_seconds: int = DEFAULT_LOCK_SECONDS,
) -> dict:
    """
    Recover jobs whose worker lock expired.

    A crashed worker must not permanently leave a job stuck
    in RUNNING.
    """
    timestamp = now()

    cutoff = timestamp - timedelta(
        seconds=max(
            1,
            int(lock_timeout_seconds),
        )
    )

    query = {
        "school_id": str(school_id),
        "status": STATUS_RUNNING,
        "$or": [
            {
                "locked_until": {
                    "$lte": timestamp,
                }
            },
            {
                "started_at": {
                    "$lte": cutoff,
                }
            },
        ],
    }

    result = collection(JOBS).update_many(
        query,
        {
            "$set": {
                "status": STATUS_RETRYING,
                "next_retry_at": timestamp,
                "updated_at": timestamp,
                "error": "Automation worker lock expired.",
                "locked_until": None,
            }
        },
    )

    return {
        "recovered": int(result.modified_count),
        "recovered_at": timestamp.isoformat(),
    }


# ============================================================
# READY JOBS
# ============================================================

def ready_jobs(
    school_id: str | Any,
    limit: int = 50,
) -> list[dict]:
    """
    Return jobs that are eligible for execution.

    Execution itself remains outside this module.
    """
    timestamp = now()

    limit = max(1, min(int(limit or 50), 500))

    query = {
        "school_id": str(school_id),
        "$or": [
            {
                "status": STATUS_PENDING,
                "scheduled_at": {
                    "$lte": timestamp,
                },
            },
            {
                "status": STATUS_RETRYING,
                "next_retry_at": {
                    "$lte": timestamp,
                },
            },
        ],
    }

    documents = (
        collection(JOBS)
        .find(query)
        .sort(
            [
                ("scheduled_at", 1),
                ("created_at", 1),
            ]
        )
        .limit(limit)
    )

    return [
        _serialize(document)
        for document in documents
    ]