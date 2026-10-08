# backend/jumuiya/elimu/automation/services.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from backend.jumuiya.core.database import collection
from backend.jumuiya.elimu.permissions import authorize

from . import jobs


# ============================================================
# COLLECTIONS
# ============================================================

RULES = "jumuiya_elimu_automation_rules"
LOGS = "jumuiya_elimu_automation_logs"


# ============================================================
# CONSTANTS
# ============================================================

SUPPORTED_TRIGGERS = {
    # Event triggers
    "student.created",
    "student.updated",
    "student.deleted",

    "attendance.recorded",
    "attendance.threshold_reached",

    "assessment.created",
    "assessment.completed",

    "fee.created",
    "fee.overdue",

    "lesson.created",
    "assignment.created",
    "assignment.due",

    "timetable.generated",
    "timetable.published",

    "staff.created",
    "staff.updated",
    "staff.assigned",

    "sync.completed",
    "sync.failed",
    "sync.conflict",

    # Schedule triggers
    "daily",
    "weekly",
    "monthly",
    "term_start",
    "term_end",
    "academic_year_start",
    "academic_year_end",

    # Generic trigger categories
    "event",
    "schedule",
}


SUPPORTED_ACTIONS = {
    "notify",
    "create_report",
    "publish_report",
    "send_reminder",
    "flag_student",
    "flag_class",
    "generate_timetable",
    "run_sync",
    "retry_sync",
    "create_alert",
    "request_ai_analysis",
}


DEFAULT_MAX_ATTEMPTS = 3


# ============================================================
# TIME
# ============================================================

def now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# BASIC HELPERS
# ============================================================

def sid(membership: dict) -> str:
    """
    Return the canonical school ID from an Elimu membership.
    """
    return str(membership["school_id"])


def _oid(value: Any) -> Any:
    """
    Convert a value to ObjectId where possible.

    String IDs remain supported for compatibility.
    """
    if isinstance(value, ObjectId):
        return value

    try:
        return ObjectId(str(value))
    except Exception:
        return value


def _serialize(value: Any) -> Any:
    """
    Convert MongoDB documents into API-safe structures.
    """
    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()

    if isinstance(value, list):
        return [_serialize(item) for item in value]

    if isinstance(value, dict):
        return {
            str(key): _serialize(item)
            for key, item in value.items()
        }

    return value


def _rule_query(
    school_id: str,
    rule_id: str,
) -> dict:
    return {
        "school_id": str(school_id),
        "_id": _oid(rule_id),
    }


def _get_rule(
    school_id: str,
    rule_id: str,
) -> dict | None:
    return collection(RULES).find_one(
        _rule_query(
            school_id,
            rule_id,
        )
    )


# ============================================================
# VALIDATION
# ============================================================

def normalize_trigger(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_action(value: Any) -> str:
    return str(value or "").strip().lower()


def validate_trigger(trigger: Any) -> str:
    """
    Validate and normalize an automation trigger.

    Wildcard triggers such as:

        attendance.*
        sync.*
        student.*

    are also supported.
    """
    normalized = normalize_trigger(trigger)

    if not normalized:
        raise ValueError("Automation trigger is required.")

    if normalized in SUPPORTED_TRIGGERS:
        return normalized

    if normalized.endswith(".*"):
        prefix = normalized[:-2]

        if any(
            item.startswith(prefix + ".")
            for item in SUPPORTED_TRIGGERS
            if "." in item
        ):
            return normalized

    raise ValueError(
        f"Unsupported automation trigger: {normalized}"
    )


def validate_action(action: Any) -> str:
    """
    Validate and normalize an automation action.
    """
    normalized = normalize_action(action)

    if not normalized:
        raise ValueError("Automation action is required.")

    if normalized not in SUPPORTED_ACTIONS:
        raise ValueError(
            f"Unsupported automation action: {normalized}"
        )

    return normalized


def normalize_rule_payload(
    payload: dict,
) -> dict:
    """
    Normalize and validate an incoming rule payload.
    """
    if not isinstance(payload, dict):
        raise ValueError("Automation rule payload must be an object.")

    name = str(payload.get("name") or "").strip()

    if not name:
        raise ValueError("Automation rule name is required.")

    if len(name) > 160:
        raise ValueError(
            "Automation rule name cannot exceed 160 characters."
        )

    trigger = validate_trigger(
        payload.get("trigger")
    )

    action = validate_action(
        payload.get("action")
    )

    enabled = bool(
        payload.get(
            "enabled",
            True,
        )
    )

    max_attempts = payload.get(
        "max_attempts",
        DEFAULT_MAX_ATTEMPTS,
    )

    try:
        max_attempts = int(max_attempts)
    except (TypeError, ValueError):
        raise ValueError(
            "max_attempts must be an integer."
        )

    max_attempts = max(
        1,
        min(max_attempts, 10),
    )

    conditions = payload.get("conditions") or {}

    if not isinstance(conditions, dict):
        raise ValueError(
            "Automation conditions must be an object."
        )

    configuration = payload.get(
        "configuration"
    ) or {}

    if not isinstance(configuration, dict):
        raise ValueError(
            "Automation configuration must be an object."
        )

    description = str(
        payload.get("description") or ""
    ).strip()

    return {
        "name": name,
        "description": description,
        "trigger": trigger,
        "action": action,
        "enabled": enabled,
        "max_attempts": max_attempts,
        "conditions": conditions,
        "configuration": configuration,
    }


# ============================================================
# AUDIT / LOGGING
# ============================================================

def write_log(
    school_id: str,
    *,
    rule_id: str | None = None,
    job_id: str | None = None,
    user_id: str | None = None,
    event: str,
    status: str,
    context: dict | None = None,
    result: Any = None,
    error: Any = None,
) -> dict:
    """
    Write an immutable automation lifecycle log.
    """
    document = {
        "school_id": str(school_id),
        "rule_id": str(rule_id) if rule_id else None,
        "job_id": str(job_id) if job_id else None,
        "user_id": str(user_id) if user_id else None,
        "event": str(event),
        "status": str(status),
        "context": context or {},
        "result": result,
        "error": str(error) if error else None,
        "created_at": now(),
    }

    result_insert = collection(LOGS).insert_one(
        document
    )

    document["_id"] = result_insert.inserted_id

    return _serialize(document)


# ============================================================
# DUPLICATE RULE PROTECTION
# ============================================================

def _find_duplicate_rule(
    school_id: str,
    name: str,
    exclude_rule_id: str | None = None,
) -> dict | None:
    query: dict[str, Any] = {
        "school_id": str(school_id),
        "name": str(name),
    }

    if exclude_rule_id:
        query["_id"] = {
            "$ne": _oid(exclude_rule_id),
        }

    return collection(RULES).find_one(query)


# ============================================================
# CREATE RULE
# ============================================================

def create_rule(
    user_id,
    payload: dict,
) -> dict:
    """
    Create a school automation rule.

    Requires automation.manage.
    """
    membership = authorize(
        user_id,
        "automation.manage",
    )

    school_id = sid(membership)

    data = normalize_rule_payload(payload)

    duplicate = _find_duplicate_rule(
        school_id,
        data["name"],
    )

    if duplicate:
        raise ValueError(
            "An automation rule with this name already exists."
        )

    timestamp = now()

    document = {
        "school_id": school_id,
        "name": data["name"],
        "description": data["description"],
        "trigger": data["trigger"],
        "action": data["action"],
        "enabled": data["enabled"],
        "max_attempts": data["max_attempts"],
        "conditions": data["conditions"],
        "configuration": data["configuration"],
        "created_by": str(user_id),
        "updated_by": str(user_id),
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    result = collection(RULES).insert_one(
        document
    )

    document["_id"] = result.inserted_id

    write_log(
        school_id,
        rule_id=str(result.inserted_id),
        user_id=str(user_id),
        event="rule.created",
        status="success",
        result={
            "name": data["name"],
            "trigger": data["trigger"],
            "action": data["action"],
        },
    )

    return _serialize(document)


# ============================================================
# LIST RULES
# ============================================================

def list_rules(
    user_id,
) -> dict:
    """
    List automation rules for the authenticated school.
    """
    membership = authorize(
        user_id,
        "automation.view",
    )

    school_id = sid(membership)

    rules = collection(RULES).find(
        {
            "school_id": school_id,
        }
    ).sort(
        [
            ("enabled", -1),
            ("created_at", -1),
        ]
    )

    return {
        "rules": [
            _serialize(rule)
            for rule in rules
        ]
    }


# ============================================================
# GET RULE
# ============================================================

def get_rule(
    user_id,
    rule_id: str,
) -> dict:
    """
    Get one automation rule within the user's school scope.
    """
    membership = authorize(
        user_id,
        "automation.view",
    )

    school_id = sid(membership)

    rule = _get_rule(
        school_id,
        rule_id,
    )

    if not rule:
        raise ValueError(
            "Automation rule not found."
        )

    return _serialize(rule)


# ============================================================
# UPDATE RULE
# ============================================================

def update_rule(
    user_id,
    rule_id: str,
    payload: dict,
) -> dict:
    """
    Update an existing automation rule.
    """
    membership = authorize(
        user_id,
        "automation.manage",
    )

    school_id = sid(membership)

    current = _get_rule(
        school_id,
        rule_id,
    )

    if not current:
        raise ValueError(
            "Automation rule not found."
        )

    merged = {
        "name": payload.get(
            "name",
            current.get("name"),
        ),
        "description": payload.get(
            "description",
            current.get("description", ""),
        ),
        "trigger": payload.get(
            "trigger",
            current.get("trigger"),
        ),
        "action": payload.get(
            "action",
            current.get("action"),
        ),
        "enabled": payload.get(
            "enabled",
            current.get("enabled", True),
        ),
        "max_attempts": payload.get(
            "max_attempts",
            current.get(
                "max_attempts",
                DEFAULT_MAX_ATTEMPTS,
            ),
        ),
        "conditions": payload.get(
            "conditions",
            current.get("conditions", {}),
        ),
        "configuration": payload.get(
            "configuration",
            current.get("configuration", {}),
        ),
    }

    data = normalize_rule_payload(
        merged
    )

    duplicate = _find_duplicate_rule(
        school_id,
        data["name"],
        exclude_rule_id=rule_id,
    )

    if duplicate:
        raise ValueError(
            "An automation rule with this name already exists."
        )

    timestamp = now()

    updated = collection(RULES).find_one_and_update(
        _rule_query(
            school_id,
            rule_id,
        ),
        {
            "$set": {
                **data,
                "updated_by": str(user_id),
                "updated_at": timestamp,
            }
        },
        return_document=True,
    )

    if not updated:
        raise ValueError(
            "Automation rule could not be updated."
        )

    write_log(
        school_id,
        rule_id=rule_id,
        user_id=str(user_id),
        event="rule.updated",
        status="success",
        result={
            "trigger": data["trigger"],
            "action": data["action"],
        },
    )

    return _serialize(updated)


# ============================================================
# ENABLE / DISABLE
# ============================================================

def set_rule_enabled(
    user_id,
    rule_id: str,
    enabled: bool,
) -> dict:
    """
    Enable or disable an automation rule.
    """
    membership = authorize(
        user_id,
        "automation.manage",
    )

    school_id = sid(membership)

    rule = _get_rule(
        school_id,
        rule_id,
    )

    if not rule:
        raise ValueError(
            "Automation rule not found."
        )

    timestamp = now()

    updated = collection(RULES).find_one_and_update(
        _rule_query(
            school_id,
            rule_id,
        ),
        {
            "$set": {
                "enabled": bool(enabled),
                "updated_by": str(user_id),
                "updated_at": timestamp,
            }
        },
        return_document=True,
    )

    write_log(
        school_id,
        rule_id=rule_id,
        user_id=str(user_id),
        event=(
            "rule.enabled"
            if enabled
            else "rule.disabled"
        ),
        status="success",
    )

    return _serialize(updated)


# ============================================================
# DELETE RULE
# ============================================================

def delete_rule(
    user_id,
    rule_id: str,
) -> dict:
    """
    Delete an automation rule.

    Historical job and audit records are intentionally
    preserved.
    """
    membership = authorize(
        user_id,
        "automation.manage",
    )

    school_id = sid(membership)

    rule = _get_rule(
        school_id,
        rule_id,
    )

    if not rule:
        raise ValueError(
            "Automation rule not found."
        )

    result = collection(RULES).delete_one(
        _rule_query(
            school_id,
            rule_id,
        )
    )

    if not result.deleted_count:
        raise ValueError(
            "Automation rule could not be deleted."
        )

    write_log(
        school_id,
        rule_id=rule_id,
        user_id=str(user_id),
        event="rule.deleted",
        status="success",
        result={
            "name": rule.get("name"),
        },
    )

    return {
        "rule_id": str(rule_id),
        "deleted": True,
    }


# ============================================================
# RUN ONE RULE
# ============================================================

def run_rule(
    user_id,
    rule_id: str,
    context: dict | None = None,
) -> dict:
    """
    Generate a durable job for one specific rule.

    This replaces the old "simulated" execution behavior.

    The job is NOT executed here. The executor layer is
    responsible for executing the action safely.
    """
    membership = authorize(
        user_id,
        "automation.manage",
    )

    school_id = sid(membership)

    rule = _get_rule(
        school_id,
        rule_id,
    )

    if not rule:
        raise ValueError(
            "Automation rule not found."
        )

    if not rule.get("enabled", True):
        raise ValueError(
            "Automation rule is disabled."
        )

    context = dict(context or {})

    context.setdefault(
        "trigger",
        rule.get("trigger"),
    )

    context.setdefault(
        "manual",
        True,
    )

    context.setdefault(
        "requested_by",
        str(user_id),
    )

    job = jobs.create_job(
        school_id,
        rule,
        context,
    )

    write_log(
        school_id,
        rule_id=rule_id,
        job_id=job.get("_id"),
        user_id=str(user_id),
        event="rule.run_requested",
        status="success",
        context=context,
        result={
            "job_id": job.get("_id"),
            "action": rule.get("action"),
        },
    )

    return {
        "rule_id": str(rule_id),
        "job": job,
        "status": "queued",
        "action": rule.get("action"),
    }


# ============================================================
# RUN MATCHING RULES
# ============================================================

def run_due_rules(
    user_id,
    context: dict | None = None,
) -> dict:
    """
    Generate durable jobs for all rules whose trigger matches
    the supplied context.
    """
    membership = authorize(
        user_id,
        "automation.manage",
    )

    school_id = sid(membership)

    context = dict(context or {})

    result = jobs.run_due_jobs(
        school_id,
        context,
    )

    for job in result.get("jobs", []):
        write_log(
            school_id,
            rule_id=job.get("rule_id"),
            job_id=job.get("_id"),
            user_id=str(user_id),
            event="job.created",
            status="success",
            context=context,
            result={
                "action": job.get("action"),
                "trigger": job.get("trigger"),
            },
        )

    return result


# ============================================================
# JOB QUERIES
# ============================================================

def get_job(
    user_id,
    job_id: str,
) -> dict | None:
    """
    Retrieve an automation job within the authenticated
    school scope.
    """
    membership = authorize(
        user_id,
        "automation.view",
    )

    school_id = sid(membership)

    return jobs.get_job(
        school_id,
        job_id,
    )


def list_jobs(
    user_id,
    status: str | None = None,
    limit: int = 100,
) -> dict:
    """
    List automation jobs for the authenticated school.
    """
    membership = authorize(
        user_id,
        "automation.view",
    )

    school_id = sid(membership)

    return {
        "jobs": jobs.list_jobs(
            school_id,
            status=status,
            limit=limit,
        )
    }


# ============================================================
# JOB CONTROL
# ============================================================

def cancel_job(
    user_id,
    job_id: str,
    reason: str | None = None,
) -> dict:
    """
    Cancel an automation job.
    """
    membership = authorize(
        user_id,
        "automation.manage",
    )

    school_id = sid(membership)

    result = jobs.cancel_job(
        school_id,
        job_id,
        reason=reason,
    )

    if not result:
        raise ValueError(
            "Automation job not found or cannot be cancelled."
        )

    write_log(
        school_id,
        job_id=job_id,
        user_id=str(user_id),
        event="job.cancelled",
        status="success",
        error=reason,
    )

    return result


def retry_job(
    user_id,
    job_id: str,
) -> dict:
    """
    Manually place a failed job back into the retry queue.
    """
    membership = authorize(
        user_id,
        "automation.manage",
    )

    school_id = sid(membership)

    current = jobs.get_job(
        school_id,
        job_id,
    )

    if not current:
        raise ValueError(
            "Automation job not found."
        )

    if current.get("status") not in {
        jobs.STATUS_FAILED,
        jobs.STATUS_CANCELLED,
    }:
        raise ValueError(
            "Only failed or cancelled jobs can be retried."
        )

    # Re-open the job without changing its original
    # idempotency key. This is a deliberate manual retry.
    timestamp = now()

    updated = collection(
        jobs.JOBS
    ).find_one_and_update(
        {
            "school_id": school_id,
            "_id": _oid(job_id),
        },
        {
            "$set": {
                "status": jobs.STATUS_RETRYING,
                "next_retry_at": timestamp,
                "updated_at": timestamp,
                "error": None,
                "locked_until": None,
            }
        },
        return_document=True,
    )

    if not updated:
        raise ValueError(
            "Automation job could not be queued for retry."
        )

    write_log(
        school_id,
        job_id=job_id,
        user_id=str(user_id),
        event="job.retry_requested",
        status="success",
    )

    return _serialize(updated)


def recover_jobs(
    user_id,
) -> dict:
    """
    Recover stale automation workers/jobs.
    """
    membership = authorize(
        user_id,
        "automation.manage",
    )

    school_id = sid(membership)

    result = jobs.recover_stale_jobs(
        school_id,
    )

    write_log(
        school_id,
        user_id=str(user_id),
        event="jobs.recovered",
        status="success",
        result=result,
    )

    return result


# ============================================================
# AUTOMATION STATUS
# ============================================================

def automation_status(
    user_id,
) -> dict:
    """
    Return a high-level automation health snapshot.
    """
    membership = authorize(
        user_id,
        "automation.view",
    )

    school_id = sid(membership)

    rules_total = collection(RULES).count_documents(
        {
            "school_id": school_id,
        }
    )

    rules_enabled = collection(RULES).count_documents(
        {
            "school_id": school_id,
            "enabled": True,
        }
    )

    jobs_total = collection(jobs.JOBS).count_documents(
        {
            "school_id": school_id,
        }
    )

    pending = collection(jobs.JOBS).count_documents(
        {
            "school_id": school_id,
            "status": jobs.STATUS_PENDING,
        }
    )

    running = collection(jobs.JOBS).count_documents(
        {
            "school_id": school_id,
            "status": jobs.STATUS_RUNNING,
        }
    )

    retrying = collection(jobs.JOBS).count_documents(
        {
            "school_id": school_id,
            "status": jobs.STATUS_RETRYING,
        }
    )

    failed = collection(jobs.JOBS).count_documents(
        {
            "school_id": school_id,
            "status": jobs.STATUS_FAILED,
        }
    )

    succeeded = collection(jobs.JOBS).count_documents(
        {
            "school_id": school_id,
            "status": jobs.STATUS_SUCCEEDED,
        }
    )

    return {
        "school_id": school_id,
        "rules": {
            "total": rules_total,
            "enabled": rules_enabled,
            "disabled": rules_total - rules_enabled,
        },
        "jobs": {
            "total": jobs_total,
            "pending": pending,
            "running": running,
            "retrying": retrying,
            "failed": failed,
            "succeeded": succeeded,
        },
        "healthy": (
            failed == 0
            and running >= 0
        ),
        "generated_at": now().isoformat(),
    }


# ============================================================
# AUTOMATION LOGS
# ============================================================

def list_logs(
    user_id,
    *,
    rule_id: str | None = None,
    job_id: str | None = None,
    limit: int = 100,
) -> dict:
    """
    Return immutable automation audit logs scoped to the
    authenticated school.
    """
    membership = authorize(
        user_id,
        "automation.view",
    )

    school_id = sid(membership)

    limit = max(
        1,
        min(int(limit or 100), 500),
    )

    query: dict[str, Any] = {
        "school_id": school_id,
    }

    if rule_id:
        query["rule_id"] = str(rule_id)

    if job_id:
        query["job_id"] = str(job_id)

    documents = (
        collection(LOGS)
        .find(query)
        .sort(
            [
                ("created_at", -1),
                ("_id", -1),
            ]
        )
        .limit(limit)
    )

    return {
        "logs": [
            _serialize(document)
            for document in documents
        ]
    }