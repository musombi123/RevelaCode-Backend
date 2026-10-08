# backend/jumuiya/elimu/automation/routes.py

from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id
from backend.jumuiya.core.responses import ok, created

from . import services


# ============================================================
# BLUEPRINT
# ============================================================

automation_bp = Blueprint(
    "jumuiya_elimu_automation",
    __name__,
    url_prefix="/automation",
)


# ============================================================
# REQUEST HELPERS
# ============================================================

def body() -> dict:
    """
    Read and validate a JSON request body.
    """
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        raise APIError(
            "JSON request body is required.",
            400,
            "invalid_json",
        )

    return data


def _int_query(
    name: str,
    default: int,
    maximum: int = 500,
) -> int:
    """
    Safely parse an integer query parameter.
    """
    raw = request.args.get(name)

    if raw is None:
        return default

    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise APIError(
            f"{name} must be an integer.",
            422,
            "validation_error",
        )

    return max(
        1,
        min(value, maximum),
    )


def _service_error(error: Exception) -> APIError:
    """
    Convert domain/service validation errors into the
    application's API error format.
    """
    message = str(error).strip()

    if isinstance(error, PermissionError):
        return APIError(
            message or "Automation permission denied.",
            403,
            "permission_denied",
        )

    if isinstance(error, ValueError):
        return APIError(
            message or "Invalid automation request.",
            422,
            "automation_validation_error",
        )

    return APIError(
        message or "Automation operation failed.",
        500,
        "automation_error",
    )


# ============================================================
# RULES
# ============================================================

@automation_bp.get("/rules")
def rules():
    """
    List automation rules for the authenticated school.
    """
    try:
        return ok(
            services.list_rules(
                current_user_id()
            )
        )
    except (ValueError, PermissionError) as error:
        raise _service_error(error)


@automation_bp.get("/rules/<rule_id>")
def get_rule(rule_id: str):
    """
    Get one automation rule.
    """
    try:
        return ok(
            services.get_rule(
                current_user_id(),
                rule_id,
            )
        )
    except (ValueError, PermissionError) as error:
        raise _service_error(error)


@automation_bp.post("/rules")
def create_rule():
    """
    Create an automation rule.
    """
    data = body()

    if not str(
        data.get("name") or ""
    ).strip():
        raise APIError(
            "name is required.",
            422,
            "validation_error",
        )

    if not data.get("trigger"):
        raise APIError(
            "trigger is required.",
            422,
            "validation_error",
        )

    if not data.get("action"):
        raise APIError(
            "action is required.",
            422,
            "validation_error",
        )

    try:
        result = services.create_rule(
            current_user_id(),
            data,
        )

        return created(
            result,
            "Automation rule created.",
        )

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


@automation_bp.patch("/rules/<rule_id>")
def update_rule(rule_id: str):
    """
    Update an automation rule.
    """
    data = body()

    try:
        result = services.update_rule(
            current_user_id(),
            rule_id,
            data,
        )

        return ok(
            result,
            "Automation rule updated.",
        )

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


@automation_bp.post("/rules/<rule_id>/enable")
def enable_rule(rule_id: str):
    """
    Enable an automation rule.
    """
    try:
        result = services.set_rule_enabled(
            current_user_id(),
            rule_id,
            True,
        )

        return ok(
            result,
            "Automation rule enabled.",
        )

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


@automation_bp.post("/rules/<rule_id>/disable")
def disable_rule(rule_id: str):
    """
    Disable an automation rule.
    """
    try:
        result = services.set_rule_enabled(
            current_user_id(),
            rule_id,
            False,
        )

        return ok(
            result,
            "Automation rule disabled.",
        )

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


@automation_bp.delete("/rules/<rule_id>")
def delete_rule(rule_id: str):
    """
    Delete an automation rule.

    Historical jobs/logs remain intact.
    """
    try:
        result = services.delete_rule(
            current_user_id(),
            rule_id,
        )

        return ok(
            result,
            "Automation rule deleted.",
        )

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


# ============================================================
# RULE EXECUTION / JOB CREATION
# ============================================================

@automation_bp.post("/rules/<rule_id>/run")
def run_rule(rule_id: str):
    """
    Manually queue one automation rule.
    """
    data = body()

    try:
        result = services.run_rule(
            current_user_id(),
            rule_id,
            data,
        )

        return ok(
            result,
            "Automation job queued.",
        )

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


@automation_bp.post("/run")
def run():
    """
    Evaluate all enabled automation rules against the
    supplied trigger/context and create matching jobs.

    This endpoint creates durable jobs; it does not directly
    execute actions.
    """
    data = body()

    try:
        result = services.run_due_rules(
            current_user_id(),
            data,
        )

        return ok(
            result,
            "Automation jobs generated.",
        )

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


# ============================================================
# JOBS
# ============================================================

@automation_bp.get("/jobs")
def list_jobs():
    """
    List automation jobs for the authenticated school.
    """
    status = request.args.get("status")
    limit = _int_query(
        "limit",
        100,
        500,
    )

    try:
        result = services.list_jobs(
            current_user_id(),
            status=status,
            limit=limit,
        )

        return ok(result)

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


@automation_bp.get("/jobs/<job_id>")
def get_job(job_id: str):
    """
    Get one automation job.
    """
    try:
        result = services.get_job(
            current_user_id(),
            job_id,
        )

        if result is None:
            raise APIError(
                "Automation job not found.",
                404,
                "automation_job_not_found",
            )

        return ok(result)

    except APIError:
        raise

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


@automation_bp.post("/jobs/<job_id>/cancel")
def cancel_job(job_id: str):
    """
    Cancel a pending/running/retrying automation job.
    """
    data = body()

    reason = str(
        data.get("reason") or ""
    ).strip()

    try:
        result = services.cancel_job(
            current_user_id(),
            job_id,
            reason=reason or None,
        )

        return ok(
            result,
            "Automation job cancelled.",
        )

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


@automation_bp.post("/jobs/<job_id>/retry")
def retry_job(job_id: str):
    """
    Manually retry a failed/cancelled automation job.
    """
    try:
        result = services.retry_job(
            current_user_id(),
            job_id,
        )

        return ok(
            result,
            "Automation job queued for retry.",
        )

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


@automation_bp.post("/jobs/recover")
def recover_jobs():
    """
    Recover stale jobs left by crashed/expired workers.
    """
    try:
        result = services.recover_jobs(
            current_user_id()
        )

        return ok(
            result,
            "Automation jobs recovered.",
        )

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


# ============================================================
# STATUS
# ============================================================

@automation_bp.get("/status")
def status():
    """
    Return automation health and queue statistics.
    """
    try:
        result = services.automation_status(
            current_user_id()
        )

        return ok(result)

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


# ============================================================
# AUDIT LOGS
# ============================================================

@automation_bp.get("/logs")
def logs():
    """
    List immutable automation audit records.
    """
    rule_id = request.args.get("rule_id")
    job_id = request.args.get("job_id")

    limit = _int_query(
        "limit",
        100,
        500,
    )

    try:
        result = services.list_logs(
            current_user_id(),
            rule_id=rule_id,
            job_id=job_id,
            limit=limit,
        )

        return ok(result)

    except (ValueError, PermissionError) as error:
        raise _service_error(error)


# ============================================================
# ACTION CATALOG
# ============================================================

@automation_bp.get("/actions")
def actions():
    """
    Return the available automation action catalog.
    """
    from .actions import list_actions

    return ok(
        {
            "actions": list_actions(),
        }
    )