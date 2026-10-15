"""Authenticated API for owner-controlled Biashara automations."""
from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import created, ok
from backend.jumuiya.biashara.tenancy.service import (
    require_any_business_permission,
    require_business_permission,
)
from backend.jumuiya.biashara.automation import services


biashara_automation_bp = Blueprint("jumuiya_biashara_automation", __name__)


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    return data


@biashara_automation_bp.get("/rules")
@require_authenticated
@require_business_permission("automation.view")
def get_rules():
    enabled = request.args.get("enabled")
    if enabled is None or not enabled.strip():
        filter_enabled = None
    elif enabled.strip().lower() in {"true", "1"}:
        filter_enabled = True
    elif enabled.strip().lower() in {"false", "0"}:
        filter_enabled = False
    else:
        raise APIError("enabled must be true or false.", 422, "invalid_automation_rule")
    rows = services.list_rules(current_user_id(), enabled=filter_enabled)
    return ok(rows, "Biashara automation rules loaded.", meta={"count": len(rows)})


@biashara_automation_bp.post("/rules")
@require_authenticated
@require_business_permission("automation.manage")
def post_rule():
    result = services.create_rule(current_user_id(), _body())
    return created(result, "Biashara automation rule created.")


@biashara_automation_bp.patch("/rules/<rule_id>/enabled")
@require_authenticated
@require_business_permission("automation.manage")
def patch_rule_enabled(rule_id):
    payload = _body()
    if "enabled" not in payload or not isinstance(payload["enabled"], bool):
        raise APIError("enabled must be a boolean.", 422, "invalid_automation_rule")
    result = services.set_rule_enabled(current_user_id(), rule_id, payload["enabled"])
    return ok(result, "Biashara automation rule updated.")


@biashara_automation_bp.get("/runs")
@require_authenticated
@require_business_permission("automation.view")
def get_runs():
    rows = services.list_runs(
        current_user_id(),
        limit=request.args.get("limit", 50),
        status=request.args.get("status"),
    )
    return ok(rows, "Biashara automation runs loaded.", meta={"count": len(rows)})


@biashara_automation_bp.get("/tasks")
@require_authenticated
@require_any_business_permission("automation.view", "orders.manage", "finance.manage", "inventory.manage")
def get_tasks():
    rows = services.list_tasks(
        current_user_id(),
        limit=request.args.get("limit", 50),
        status=request.args.get("status"),
        task_type=request.args.get("task_type"),
    )
    return ok(rows, "Biashara automation tasks loaded.", meta={"count": len(rows)})


@biashara_automation_bp.post("/tasks/<task_id>/decision")
@require_authenticated
@require_any_business_permission("automation.manage", "finance.manage", "orders.manage")
def decide_task(task_id):
    payload = _body()
    result = services.decide_task(
        current_user_id(),
        task_id,
        payload.get("decision"),
        payload.get("note", ""),
    )
    decision = result.get("decision")
    if decision == "approve" and result.get("task_type") == "reorder_suggestion":
        message = "Reorder suggestion approved for manual action. No purchase order was created or sent."
    elif decision == "acknowledge" and result.get("task_type") == "payment_evidence_review":
        message = "Payment evidence review recorded as unverified. Payment status was not verified or changed."
    else:
        message = "Biashara automation task decision saved."
    return ok(result, message)


@biashara_automation_bp.post("/repair")
@require_authenticated
@require_business_permission("automation.manage")
def repair_dispatches():
    result = services.replay_failed_automation_dispatches(current_user_id(), limit=100)
    return ok(result, "Failed automation dispatches checked for recovery.")
