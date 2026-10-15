"""Constrained Biashara automation rules and durable task execution.

Automations create records/tasks from real business events. They do not send
messages, spend money, issue purchase orders, change payment verification, or
publish customer-facing content. High-impact suggestions require owner review.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.audit import log_action
from backend.jumuiya.biashara import services as biashara_services


logger = logging.getLogger("jumuiya.biashara.automation")

RULES_COLLECTION = "jumuiya_automation_rules"
RUNS_COLLECTION = "jumuiya_automation_runs"
TASKS_COLLECTION = "jumuiya_automation_tasks"
MAX_RULES_PER_EVENT = 100
MAX_LIST_LIMIT = 100

TRIGGER_ACTIONS = {
    "order.created": {"create_fulfillment_task"},
    "order.status_changed": {"create_fulfillment_task"},
    "invoice.issued": {"create_invoice_follow_up"},
    "payment.recorded": {"create_payment_review_task"},
    "payment.allocation_conflict": {"create_payment_review_task"},
    "inventory.movement_recorded": {"create_reorder_suggestion"},
    "product.inventory_adjusted": {"create_reorder_suggestion"},
    "product.created": {"create_reorder_suggestion"},
}
ALL_ACTIONS = {action for actions in TRIGGER_ACTIONS.values() for action in actions}
REQUIRES_APPROVAL = {"create_reorder_suggestion"}


def now_utc():
    return datetime.now(timezone.utc)


def _clean_id(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return value


def _serialize(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {
            ("id" if key == "_id" else key): _serialize(item)
            for key, item in value.items()
            if key not in {"request_fingerprint", "internal_event"}
        }
    return value


def _business(user_id):
    business = biashara_services._require_business(user_id)
    business_id = str(business.get("id") or business.get("_id") or "")
    if not business_id:
        raise APIError("Business profile has no usable ID.", 409, "business_id_missing")
    return business, business_id


def _fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_rule_payload(payload, existing=None):
    if not isinstance(payload, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")

    existing = existing or {}
    name = payload.get("name", existing.get("name", ""))
    if not isinstance(name, str):
        raise APIError("Rule name must be text.", 422, "invalid_automation_rule")
    name = name.strip()
    if len(name) < 3 or len(name) > 120:
        raise APIError("Rule name must contain 3–120 characters.", 422, "invalid_automation_rule")

    trigger = str(payload.get("trigger_event", existing.get("trigger_event", ""))).strip().lower()
    if trigger not in TRIGGER_ACTIONS:
        raise APIError("This trigger event is not supported by Biashara automation.", 422, "invalid_automation_trigger")

    action = str(payload.get("action_type", existing.get("action_type", ""))).strip().lower()
    if action not in TRIGGER_ACTIONS[trigger]:
        raise APIError("This action is not allowed for the selected trigger.", 422, "invalid_automation_action")

    conditions = payload.get("conditions", existing.get("conditions", {}))
    if not isinstance(conditions, dict):
        raise APIError("Rule conditions must be an object.", 422, "invalid_automation_conditions")
    clean_conditions = {}
    allowed_conditions = {
        "create_fulfillment_task": {"minimum_amount_minor", "only_statuses"},
        "create_invoice_follow_up": set(),
        "create_payment_review_task": set(),
        "create_reorder_suggestion": {"available_quantity_lte", "target_stock_quantity"},
    }[action]
    unknown = set(conditions) - allowed_conditions
    if unknown:
        raise APIError("Unsupported condition(s): " + ", ".join(sorted(unknown)), 422, "invalid_automation_conditions")

    if "minimum_amount_minor" in conditions:
        try:
            value = int(conditions["minimum_amount_minor"])
        except (TypeError, ValueError, OverflowError):
            raise APIError("minimum_amount_minor must be a non-negative integer.", 422, "invalid_automation_conditions")
        if value < 0:
            raise APIError("minimum_amount_minor must be non-negative.", 422, "invalid_automation_conditions")
        clean_conditions["minimum_amount_minor"] = value

    if "only_statuses" in conditions:
        statuses = conditions["only_statuses"]
        allowed_statuses = {"pending", "confirmed", "processing", "completed", "cancelled"}
        if not isinstance(statuses, list) or not statuses or any(
            not isinstance(item, str) or item.strip().lower() not in allowed_statuses
            for item in statuses
        ):
            raise APIError("only_statuses must be a non-empty list of supported order states.", 422, "invalid_automation_conditions")
        clean_conditions["only_statuses"] = sorted({item.strip().lower() for item in statuses})

    if action == "create_reorder_suggestion":
        try:
            threshold = Decimal(str(conditions.get("available_quantity_lte")))
            target = Decimal(str(conditions.get("target_stock_quantity")))
        except (InvalidOperation, TypeError, ValueError):
            raise APIError("Reorder rules require available_quantity_lte and target_stock_quantity.", 422, "invalid_automation_conditions")
        if (
            not threshold.is_finite() or not target.is_finite()
            or threshold < 0 or target <= threshold
        ):
            raise APIError("target_stock_quantity must be greater than a non-negative available_quantity_lte.", 422, "invalid_automation_conditions")
        clean_conditions["available_quantity_lte"] = float(threshold)
        clean_conditions["target_stock_quantity"] = float(target)

    enabled = payload.get("enabled", existing.get("enabled", True))
    if not isinstance(enabled, bool):
        raise APIError("enabled must be a boolean.", 422, "invalid_automation_rule")
    return {
        "name": name,
        "trigger_event": trigger,
        "action_type": action,
        "conditions": clean_conditions,
        "enabled": enabled,
        "requires_approval": action in REQUIRES_APPROVAL,
    }


def create_rule(user_id, payload):
    _business_data, business_id = _business(user_id)
    clean = _validate_rule_payload(payload)
    now = now_utc()
    document = {
        "_id": ObjectId(),
        "business_id": business_id,
        **clean,
        "version": 1,
        "created_by_user_id": str(user_id),
        "created_at": now,
        "updated_at": now,
    }
    collection(RULES_COLLECTION).insert_one(document)
    log_action(user_id, "biashara.automation_rule_created", "automation_rule", document["_id"], {
        "trigger_event": clean["trigger_event"],
        "action_type": clean["action_type"],
        "requires_approval": clean["requires_approval"],
    })
    return _serialize(document)


def list_rules(user_id, enabled=None):
    _business_data, business_id = _business(user_id)
    query = {"business_id": business_id}
    if enabled is not None:
        if not isinstance(enabled, bool):
            raise APIError("enabled filter must be boolean.", 422, "invalid_automation_rule")
        query["enabled"] = enabled
    rows = collection(RULES_COLLECTION).find(query).sort("created_at", -1).limit(MAX_RULES_PER_EVENT)
    return [_serialize(row) for row in rows]


def set_rule_enabled(user_id, rule_id, enabled):
    _business_data, business_id = _business(user_id)
    if not isinstance(enabled, bool):
        raise APIError("enabled must be a boolean.", 422, "invalid_automation_rule")
    rules = collection(RULES_COLLECTION)
    current = rules.find_one({"_id": _clean_id(rule_id), "business_id": business_id})
    if not current:
        raise APIError("Automation rule not found.", 404, "automation_rule_not_found")
    updated = rules.find_one_and_update(
        {"_id": current["_id"], "business_id": business_id, "version": current.get("version", 1)},
        {"$set": {"enabled": enabled, "updated_at": now_utc()}, "$inc": {"version": 1}},
    )
    if not updated:
        raise APIError("Automation rule changed while updating. Reload and retry.", 409, "automation_rule_conflict")
    log_action(user_id, "biashara.automation_rule_toggled", "automation_rule", current["_id"], {"enabled": enabled})
    return _serialize(updated)


def _condition_matches(rule, event):
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    conditions = rule.get("conditions") if isinstance(rule.get("conditions"), dict) else {}
    action = rule.get("action_type")

    if action == "create_fulfillment_task":
        minimum = conditions.get("minimum_amount_minor")
        amount = payload.get("total_amount_minor")
        if minimum is not None and (amount is None or int(amount) < int(minimum)):
            return False, "order_below_minimum_amount"
        only_statuses = conditions.get("only_statuses")
        status = str(payload.get("status") or "").lower()
        if only_statuses and status not in only_statuses:
            return False, "order_status_not_selected"
        if status in {"cancelled", "completed"}:
            return False, "order_not_actionable"
    elif action == "create_reorder_suggestion":
        product_id = payload.get("product_id")
        if not product_id and event.get("entity_type") == "product":
            product_id = event.get("entity_id")
        product = collection("jumuiya_products").find_one({
            "_id": _clean_id(product_id),
            "business_id": str(event["business_id"]),
        }) if product_id else None
        if not product:
            return False, "product_not_found"
        try:
            physical = Decimal(str(product.get("stock_quantity", 0) or 0))
            reserved = Decimal(str(product.get("reserved_quantity", 0) or 0))
            available = physical - reserved
            threshold = Decimal(str(conditions.get("available_quantity_lte", 0)))
            target = Decimal(str(conditions.get("target_stock_quantity", 0)))
        except (InvalidOperation, TypeError, ValueError):
            return False, "inventory_state_invalid"
        if not available.is_finite() or not threshold.is_finite() or not target.is_finite():
            return False, "inventory_state_invalid"
        if available > threshold:
            return False, "stock_above_threshold"
    elif action == "create_payment_review_task":
        if (
            payload.get("payment_status") == "manual_attested"
            and payload.get("payment_verification_status") == "manual_attested"
            and payload.get("status") not in {"allocation_conflict", "not_allocated_pending_verification"}
        ):
            return False, "payment_already_manually_attested"

    return True, None


def _task_blueprint(rule, event):
    business_id = str(event["business_id"])
    event_id = str(event["event_id"])
    entity_id = str(event.get("entity_id") or "")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    action = rule["action_type"]
    common = {
        "business_id": business_id,
        "source_event_id": event_id,
        "source_event_type": event.get("event_type"),
        "source_entity_type": event.get("entity_type"),
        "source_entity_id": entity_id,
        "automation_rule_id": str(rule["_id"]),
        "automation_rule_version": int(rule.get("version", 1)),
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "decision": None,
        "decision_by_user_id": None,
        "decision_at": None,
        "approval_required": bool(rule.get("requires_approval")),
    }

    if action == "create_fulfillment_task":
        short_id = entity_id[-8:] if entity_id else "unknown"
        return {
            **common,
            "task_type": "fulfillment_follow_up",
            "title": f"Review fulfilment for order {short_id}",
            "description": "Confirm the order state, stock allocation and next fulfilment step in Biashara. No customer message was sent by this automation.",
            "status": "open",
            "details": {
                "order_id": entity_id,
                "order_status": payload.get("status"),
                "source_channel": payload.get("source_channel"),
                "total_amount_minor": payload.get("total_amount_minor"),
                "currency": payload.get("currency"),
            },
        }

    if action == "create_invoice_follow_up":
        invoice = collection("jumuiya_invoices").find_one({
            "_id": _clean_id(entity_id),
            "business_id": business_id,
        })
        if not invoice:
            return None
        total = int(invoice.get("total_amount_minor", 0) or 0)
        paid = int(invoice.get("amount_paid_minor", 0) or 0)
        balance = max(total - paid, 0)
        if invoice.get("status") != "issued" or balance <= 0:
            return None
        number = str(invoice.get("invoice_number") or entity_id[-8:])
        due_date = invoice.get("due_date")
        return {
            **common,
            "task_type": "invoice_follow_up",
            "title": f"Review outstanding invoice {number}",
            "description": "Review the outstanding balance and due date. This task does not send an invoice reminder automatically.",
            "status": "open",
            "details": {
                "invoice_id": entity_id,
                "invoice_number": number,
                "due_date": due_date,
                "balance_due_minor": balance,
                "currency": invoice.get("currency", "KES"),
            },
        }

    if action == "create_payment_review_task":
        payment = collection("jumuiya_payments").find_one({
            "_id": _clean_id(entity_id),
            "business_id": business_id,
        })
        if not payment:
            return None
        status = str(payment.get("payment_status") or "")
        allocation_status = str(payment.get("allocation_status") or "")
        if status == "manual_attested" and allocation_status == "allocated":
            return None
        return {
            **common,
            "task_type": "payment_evidence_review",
            "title": "Review unverified payment evidence",
            "description": "Compare this manual payment reference with the configured provider or settlement record. The automation does not mark the payment verified.",
            "status": "pending_review",
            "approval_required": True,
            "details": {
                "payment_id": entity_id,
                "invoice_id": payment.get("invoice_id"),
                "amount_minor": payment.get("amount_minor"),
                "currency": payment.get("currency", "KES"),
                "payment_method": payment.get("payment_method"),
                "payment_status": status,
                "verification_status": payment.get("verification_status"),
                "allocation_status": allocation_status,
                "provider_verified": bool(payment.get("provider_verified", False)),
            },
        }

    if action == "create_reorder_suggestion":
        product_id = payload.get("product_id")
        if not product_id and event.get("entity_type") == "product":
            product_id = entity_id
        product = collection("jumuiya_products").find_one({
            "_id": _clean_id(product_id),
            "business_id": business_id,
        }) if product_id else None
        if not product:
            return None
        try:
            physical = Decimal(str(product.get("stock_quantity", 0) or 0))
            reserved = Decimal(str(product.get("reserved_quantity", 0) or 0))
            available = physical - reserved
            target = Decimal(str((rule.get("conditions") or {}).get("target_stock_quantity", 0)))
        except (InvalidOperation, TypeError, ValueError):
            return None
        suggested = max(target - available, Decimal("0"))
        if suggested <= 0:
            return None
        return {
            **common,
            "task_type": "reorder_suggestion",
            "title": f"Review reorder suggestion for {str(product.get('name') or 'product')[:100]}",
            "description": "Stock is at or below the rule threshold. Review the suggested quantity and supplier before creating a purchase order. No order was sent.",
            "status": "pending_approval",
            "approval_required": True,
            "details": {
                "product_id": str(product.get("_id") or ""),
                "product_name": str(product.get("name") or "Product")[:160],
                "sku": str(product.get("sku") or "")[:80],
                "stock_quantity": float(physical),
                "reserved_quantity": float(reserved),
                "available_quantity": float(available),
                "threshold_quantity": float((rule.get("conditions") or {}).get("available_quantity_lte", 0)),
                "target_stock_quantity": float(target),
                "suggested_reorder_quantity": float(suggested),
                "purchase_order_created": False,
            },
        }

    return None


def _upsert_task(rule, event, blueprint):
    business_id = str(event["business_id"])
    event_id = str(event["event_id"])
    task_key = _fingerprint({
        "business_id": business_id,
        "event_id": event_id,
        "rule_id": str(rule["_id"]),
        "rule_version": int(rule.get("version", 1)),
        "action_type": rule["action_type"],
    })
    tasks = collection(TASKS_COLLECTION)
    existing = tasks.find_one({"business_id": business_id, "task_key": task_key})
    if existing:
        return existing
    document = {
        "_id": ObjectId(),
        "task_key": task_key,
        "created_by_user_id": None,
        **blueprint,
    }
    try:
        tasks.insert_one(document)
        return document
    except DuplicateKeyError:
        existing = tasks.find_one({"business_id": business_id, "task_key": task_key})
        if existing:
            return existing
        raise


def _record_run(rule, event, status, task=None, skip_reason=None, error_code=None):
    business_id = str(event["business_id"])
    event_id = str(event["event_id"])
    run_key = _fingerprint({
        "business_id": business_id,
        "event_id": event_id,
        "rule_id": str(rule["_id"]),
        "rule_version": int(rule.get("version", 1)),
    })
    runs = collection(RUNS_COLLECTION)
    prior = runs.find_one({"business_id": business_id, "run_key": run_key})
    if prior:
        return prior
    now = now_utc()
    document = {
        "_id": ObjectId(),
        "business_id": business_id,
        "run_key": run_key,
        "rule_id": str(rule["_id"]),
        "rule_name": rule.get("name"),
        "rule_version": int(rule.get("version", 1)),
        "trigger_event": event.get("event_type"),
        "source_event_id": event_id,
        "source_entity_type": event.get("entity_type"),
        "source_entity_id": str(event.get("entity_id") or ""),
        "action_type": rule.get("action_type"),
        "status": status,
        "task_id": str(task.get("_id")) if task else None,
        "skip_reason": skip_reason,
        "error_code": error_code,
        "created_at": now,
        "completed_at": now if status in {"created", "skipped", "failed"} else None,
    }
    try:
        runs.insert_one(document)
        return document
    except DuplicateKeyError:
        prior = runs.find_one({"business_id": business_id, "run_key": run_key})
        if prior:
            return prior
        raise


def dispatch_event_automations(event):
    """Execute active matching rules once for a durable outbox event.

    Repeated delivery of the same event is safe. Failures are surfaced to the
    outbox publisher so it can flag the event for replay.
    """
    if not isinstance(event, dict):
        raise APIError("Automation event must be an object.", 422, "invalid_automation_event")
    business_id = str(event.get("business_id") or "")
    event_id = str(event.get("event_id") or "")
    event_type = str(event.get("event_type") or "")
    if not business_id or not event_id or event_type not in TRIGGER_ACTIONS:
        return {"matched_rules": 0, "created_runs": 0, "created_tasks": 0, "skipped_runs": 0}

    rules = list(collection(RULES_COLLECTION).find({
        "business_id": business_id,
        "trigger_event": event_type,
        "enabled": True,
    }).sort("created_at", 1).limit(MAX_RULES_PER_EVENT))
    report = {"matched_rules": len(rules), "created_runs": 0, "created_tasks": 0, "skipped_runs": 0}

    for rule in rules:
        run_key = _fingerprint({
            "business_id": business_id,
            "event_id": event_id,
            "rule_id": str(rule["_id"]),
            "rule_version": int(rule.get("version", 1)),
        })
        if collection(RUNS_COLLECTION).find_one({"business_id": business_id, "run_key": run_key}):
            continue

        matched, reason = _condition_matches(rule, event)
        if not matched:
            _record_run(rule, event, "skipped", skip_reason=reason)
            report["created_runs"] += 1
            report["skipped_runs"] += 1
            continue

        task = _task_blueprint(rule, event)
        if task is None:
            _record_run(rule, event, "skipped", skip_reason="action_source_not_actionable")
            report["created_runs"] += 1
            report["skipped_runs"] += 1
            continue

        task = _upsert_task(rule, event, task)
        _record_run(rule, event, "created", task=task)
        report["created_runs"] += 1
        report["created_tasks"] += 1
    return report


def process_event_for_automations(event):
    """Best-effort wrapper called by the outbox publisher after durable insertion."""
    try:
        report = dispatch_event_automations(event)
        return {"processed": True, **report}
    except Exception as error:
        logger.warning(
            "Biashara automation dispatch deferred (event_id_hash=%s, error=%s)",
            hashlib.sha256(str(event.get("event_id", "")).encode("utf-8")).hexdigest()[:12],
            type(error).__name__,
        )
        return {"processed": False, "error_code": "automation_dispatch_failed"}


def list_runs(user_id, limit=50, status=None):
    _business_data, business_id = _business(user_id)
    try:
        limit = min(max(int(limit), 1), MAX_LIST_LIMIT)
    except (TypeError, ValueError):
        limit = 50
    query = {"business_id": business_id}
    if status:
        state = str(status).strip().lower()
        if state not in {"created", "skipped", "failed"}:
            raise APIError("Unknown automation run status.", 422, "invalid_automation_run_status")
        query["status"] = state
    rows = collection(RUNS_COLLECTION).find(query).sort("created_at", -1).limit(limit)
    return [_serialize(row) for row in rows]


def list_tasks(user_id, limit=50, status=None, task_type=None):
    _business_data, business_id = _business(user_id)
    try:
        limit = min(max(int(limit), 1), MAX_LIST_LIMIT)
    except (TypeError, ValueError):
        limit = 50
    query = {"business_id": business_id}
    if status:
        state = str(status).strip().lower()
        if state not in {"open", "in_progress", "pending_review", "pending_approval", "approved_for_manual_action", "reviewed_unverified", "completed", "dismissed"}:
            raise APIError("Unknown automation task status.", 422, "invalid_automation_task_status")
        query["status"] = state
    if task_type:
        query["task_type"] = str(task_type).strip().lower()
    rows = collection(TASKS_COLLECTION).find(query).sort("created_at", -1).limit(limit)
    return [_serialize(row) for row in rows]


def decide_task(user_id, task_id, decision, note=""):
    _business_data, business_id = _business(user_id)
    decision = str(decision or "").strip().lower()
    if decision not in {"approve", "acknowledge", "complete", "dismiss"}:
        raise APIError("Decision must be approve, acknowledge, complete or dismiss.", 422, "invalid_automation_decision")
    if not isinstance(note, str):
        raise APIError("Decision note must be text.", 422, "invalid_automation_decision")
    note = note.strip()[:500]

    tasks = collection(TASKS_COLLECTION)
    task = tasks.find_one({"_id": _clean_id(task_id), "business_id": business_id})
    if not task:
        raise APIError("Automation task not found.", 404, "automation_task_not_found")
    status = task.get("status")
    if status in {"completed", "dismissed"}:
        if decision == "complete" and status == "completed":
            return _serialize(task)
        if decision == "dismiss" and status == "dismissed":
            return _serialize(task)
        raise APIError("This automation task is already closed.", 409, "automation_task_closed")

    if decision == "approve":
        if task.get("task_type") != "reorder_suggestion" or status != "pending_approval":
            raise APIError("Only a reorder suggestion awaiting approval can be approved. Approval does not create or send a purchase order.", 409, "invalid_automation_decision")
        next_status = "approved_for_manual_action"
        audit_action = "biashara.reorder_suggestion_approved"
    elif decision == "acknowledge":
        if task.get("task_type") != "payment_evidence_review" or status != "pending_review":
            raise APIError("Only unverified payment evidence awaiting review can be acknowledged.", 409, "invalid_automation_decision")
        next_status = "reviewed_unverified"
        audit_action = "biashara.payment_evidence_reviewed_unverified"
    elif decision == "complete":
        if status not in {"open", "in_progress", "approved_for_manual_action", "reviewed_unverified"}:
            raise APIError("This task cannot be completed from its current state.", 409, "invalid_automation_decision")
        next_status = "completed"
        audit_action = "biashara.automation_task_completed"
    else:
        next_status = "dismissed"
        audit_action = "biashara.automation_task_dismissed"

    now = now_utc()
    updated = tasks.find_one_and_update(
        {"_id": task["_id"], "business_id": business_id, "status": status},
        {"$set": {
            "status": next_status,
            "decision": decision,
            "decision_by_user_id": str(user_id),
            "decision_note": note,
            "decision_at": now,
            "updated_at": now,
        }},
    )
    if not updated:
        raise APIError("Automation task changed while saving the decision. Reload and retry.", 409, "automation_task_conflict")
    log_action(user_id, audit_action, "automation_task", task["_id"], {
        "task_type": task.get("task_type"),
        "decision": decision,
        "status": next_status,
    })
    return _serialize(updated)
