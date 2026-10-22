"""Platform-admin controls for the shared Jumuiya Revenue Engine.

This blueprint is attached to the existing /api/revenue blueprint. It exposes
admin-only intent reporting and pricing catalogue management. It never marks an
intent as paid and never activates billing or paid entitlements.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from flask import jsonify, request
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.audit import log_action, now_utc
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.permissions import (
    current_user_id,
    require_authenticated,
    require_roles,
)
from backend.revenue import revenue_bp
from backend.revenue.constants import SUPPORTED_REVENUE_STREAMS
from backend.revenue.ledger import COLLECTION_NAME as TRANSACTIONS_COLLECTION
from backend.revenue.money import MoneyValidationError, to_money
from backend.revenue.plans import (
    PLANS_COLLECTION,
    get_pricing_status,
    get_plan,
    list_plans,
)

PLATFORM_ADMIN_ROLES = (
    "admin",
    "platform_admin",
    "super_admin",
    "revelacode_admin",
)
ALLOWED_PLAN_STATUSES = {"proposed", "available", "retired"}
ALLOWED_INTERVALS = {"month", "year", "one_time"}


def _error(message, status=400, code="invalid_request"):
    return jsonify({"success": False, "message": message, "error": {"message": message, "code": code}, "code": code}), status


def _parse_positive_int(value, label, default, maximum=None):
    try:
        number = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a whole number.") from None
    if number < 1:
        raise ValueError(f"{label} must be at least 1.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label} cannot exceed {maximum}.")
    return number


def _json_date(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _intent_for_admin(document):
    """Serialize safe reconciliation fields, never idempotency secrets."""
    return {
        "id": str(document.get("_id", "")),
        "user_id": str(document.get("user_id", "")),
        "stream": document.get("stream", "unknown"),
        "plan_code": document.get("plan_code"),
        "amount": document.get("amount", "0.00"),
        "currency": document.get("currency", "KES"),
        "description": document.get("description", ""),
        "status": document.get("status", "pending"),
        "billing_enabled": bool(document.get("billing_enabled", False)),
        "charge_attempted": bool(document.get("charge_attempted", False)),
        "payment_confirmed": bool(document.get("payment_confirmed", False)),
        "payment_provider": document.get("payment_provider"),
        "provider_transaction_id": document.get("provider_transaction_id"),
        "receipt": document.get("receipt"),
        "paid_at": _json_date(document.get("paid_at")),
        "created_at": _json_date(document.get("created_at")),
        "updated_at": _json_date(document.get("updated_at")),
    }


def _all_intents():
    return collection(TRANSACTIONS_COLLECTION)


def _validate_features(value):
    if not isinstance(value, list):
        raise ValueError("Features must be a list of text items.")
    if len(value) > 20:
        raise ValueError("A plan cannot contain more than 20 features.")
    result = []
    for feature in value:
        if not isinstance(feature, str):
            raise ValueError("Each plan feature must be text.")
        feature = feature.strip()
        if not feature or len(feature) > 160:
            raise ValueError("Each feature must contain 1 to 160 characters.")
        if any(ord(char) < 32 and char not in "\t" for char in feature):
            raise ValueError("Features cannot contain control characters.")
        result.append(feature)
    return result


def _validate_plan_values(data, *, creating, existing=None):
    existing = existing or {}
    allowed = {"code", "name", "hub", "amount", "interval", "status", "features"} if creating else {
        "name", "amount", "interval", "status", "features"
    }
    extra = set(data) - allowed
    if extra:
        raise ValueError("Unsupported fields: " + ", ".join(sorted(extra)))

    values = {}
    if creating:
        code = data.get("code")
        if not isinstance(code, str) or not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", code.strip()):
            raise ValueError("Plan code must use lowercase letters, numbers, and underscores.")
        if len(code.strip()) > 60:
            raise ValueError("Plan code cannot exceed 60 characters.")
        values["code"] = code.strip()

        hub = data.get("hub")
        supported_hubs = set(SUPPORTED_REVENUE_STREAMS) | {"all"}
        if not isinstance(hub, str) or hub.strip().lower() not in supported_hubs:
            raise ValueError("A supported revenue hub is required.")
        values["hub"] = hub.strip().lower()

    name = data.get("name", existing.get("name"))
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise ValueError("Plan name must contain 1 to 100 characters.")
    values["name"] = name.strip()

    amount_value = data.get("amount", existing.get("amount", "0.00"))
    try:
        amount = to_money(amount_value, allow_zero=True)
    except MoneyValidationError as exc:
        raise ValueError(str(exc)) from None
    values["amount"] = f"{amount:.2f}"

    interval = data.get("interval", existing.get("interval", "month"))
    if not isinstance(interval, str) or interval.strip().lower() not in ALLOWED_INTERVALS:
        raise ValueError("Interval must be month, year, or one_time.")
    values["interval"] = interval.strip().lower()

    status = data.get("status", existing.get("status", "proposed"))
    if not isinstance(status, str) or status.strip().lower() not in ALLOWED_PLAN_STATUSES:
        raise ValueError("Status must be proposed, available, or retired.")
    values["status"] = status.strip().lower()

    features = data.get("features", existing.get("features", []))
    values["features"] = _validate_features(features)
    values["currency"] = "KES"

    if values["status"] == "available":
        # "Available" means genuinely purchasable, not merely visible in the
        # catalogue. Only configured monthly/yearly hub subscriptions are enabled.
        from backend.revenue.mpesa import checkout_is_production_configured
        from backend.revenue.subscriptions import HUBS

        hub = values.get("hub", existing.get("hub", ""))
        if hub not in HUBS:
            raise ValueError("Only individual hub subscriptions can be published for checkout.")
        if values["interval"] not in {"month", "year"}:
            raise ValueError("Only monthly and yearly subscription plans can be published for checkout.")
        if values["amount"] == "0.00":
            raise ValueError("A published subscription must have a positive price.")
        if not checkout_is_production_configured():
            raise ValueError("Configure production M-Pesa Daraja credentials and a registered public HTTPS callback before publishing a plan.")
    return values


@revenue_bp.get("/admin/overview")
@require_authenticated
@require_roles(*PLATFORM_ADMIN_ROLES)
def revenue_admin_overview():
    """Return cross-ecosystem intent metrics (not paid revenue)."""
    transactions = _all_intents()
    intent_filter = {"payment_confirmed": {"$ne": True}}
    total = transactions.count_documents(intent_filter)
    pending = transactions.count_documents({"$and": [intent_filter, {"status": "pending"}]})

    stream_rows = transactions.aggregate([
        {"$match": intent_filter},
        {"$group": {"_id": "$stream", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ])
    status_rows = transactions.aggregate([
        {"$match": intent_filter},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ])
    paid_filter = {"payment_confirmed": True, "status": "succeeded"}
    paid_count = transactions.count_documents(paid_filter)
    paid_rollup = list(transactions.aggregate([
        {"$match": paid_filter},
        {"$group": {
            "_id": "$currency",
            "amount": {"$sum": {"$convert": {
                "input": "$amount", "to": "decimal", "onError": 0, "onNull": 0,
            }}},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]))
    plans = list_plans(include_retired=True)
    latest = transactions.find_one(intent_filter, sort=[("created_at", DESCENDING)])
    latest_paid = transactions.find_one(paid_filter, sort=[("paid_at", DESCENDING)])

    from backend.revenue.mpesa import checkout_is_production_configured

    live_checkout = checkout_is_production_configured()
    return jsonify({
        "success": True,
        "billing_enabled": live_checkout,
        "checkout_enabled": live_checkout,
        "pricing_status": get_pricing_status(),
        "metrics": {
            "total_intents": total,
            "pending_intents": pending,
            "confirmed_payment_count": paid_count,
            "latest_intent_at": _json_date(latest.get("created_at")) if latest else None,
            "latest_payment_at": _json_date(latest_paid.get("paid_at")) if latest_paid else None,
            "plan_count": len(plans),
            "retired_plan_count": sum(1 for plan in plans if plan.get("status") == "retired"),
        },
        "confirmed_payment_totals": [
            {"currency": row.get("_id") or "KES", "amount": str(row.get("amount", "0")), "count": row.get("count", 0)}
            for row in paid_rollup
        ],
        "stream_breakdown": [
            {"stream": row.get("_id") or "unknown", "count": row.get("count", 0)}
            for row in stream_rows
        ],
        "status_breakdown": [
            {"status": row.get("_id") or "unknown", "count": row.get("count", 0)}
            for row in status_rows
        ],
        "financial_note": "Only verified provider-confirmed payment records are included in confirmed totals; payment intents are excluded.",
    }), 200


@revenue_bp.get("/admin/payments")
@require_authenticated
@require_roles(*PLATFORM_ADMIN_ROLES)
def revenue_admin_payments():
    """List provider-confirmed payments separately from unpaid intent records."""
    try:
        page = _parse_positive_int(request.args.get("page"), "page", 1)
        per_page = _parse_positive_int(request.args.get("per_page"), "per_page", 25, 100)
    except ValueError as exc:
        return _error(str(exc), 400, "invalid_pagination")

    query = {"payment_confirmed": True, "status": "succeeded"}
    stream = request.args.get("stream", "").strip().lower()
    if stream:
        if stream not in SUPPORTED_REVENUE_STREAMS:
            return _error("Unsupported revenue stream.", 400, "unsupported_revenue_stream")
        query["stream"] = stream
    provider = request.args.get("provider", "").strip().lower()
    if provider:
        if provider not in {"mpesa"}:
            return _error("Unsupported payment provider.", 400, "unsupported_provider")
        query["payment_provider"] = provider

    transactions = _all_intents()
    total = transactions.count_documents(query)
    cursor = (
        transactions.find(query)
        .sort("paid_at", DESCENDING)
        .skip((page - 1) * per_page)
        .limit(per_page)
    )
    items = [_intent_for_admin(item) for item in cursor]
    rollups = list(transactions.aggregate([
        {"$match": query},
        {"$group": {
            "_id": {"currency": "$currency", "stream": "$stream"},
            "amount": {"$sum": {"$convert": {
                "input": "$amount", "to": "decimal", "onError": 0, "onNull": 0,
            }}},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id.stream": 1, "_id.currency": 1}},
    ]))
    return jsonify({
        "success": True,
        "items": items,
        "totals": [
            {
                "currency": row.get("_id", {}).get("currency") or "KES",
                "stream": row.get("_id", {}).get("stream") or "unknown",
                "amount": str(row.get("amount", "0")),
                "count": row.get("count", 0),
            }
            for row in rollups
        ],
        "pagination": {
            "page": page, "per_page": per_page, "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
        "financial_note": "These records come only from verified provider payments; pending intents are not counted as revenue.",
    }), 200


@revenue_bp.get("/admin/transactions")
@require_authenticated
@require_roles(*PLATFORM_ADMIN_ROLES)
def revenue_admin_transactions():
    """Paginate all-user intent records for platform-admin review."""
    try:
        page = _parse_positive_int(request.args.get("page"), "page", 1)
        per_page = _parse_positive_int(request.args.get("per_page"), "per_page", 25, 100)
    except ValueError as exc:
        return _error(str(exc), 400, "invalid_pagination")

    query_parts = []
    stream = request.args.get("stream", "").strip().lower()
    if stream:
        if stream not in SUPPORTED_REVENUE_STREAMS:
            return _error("Unsupported revenue stream.", 400, "unsupported_revenue_stream")
        query_parts.append({"stream": stream})

    status = request.args.get("status", "").strip().lower()
    if status:
        if status not in {"pending", "processing", "succeeded", "failed", "cancelled", "refunded", "partially_refunded"}:
            return _error("Unsupported transaction status.", 400, "unsupported_status")
        query_parts.append({"status": status})

    search = request.args.get("search", "").strip()
    if len(search) > 120:
        return _error("Search cannot exceed 120 characters.", 400, "search_too_long")
    if search:
        pattern = re.escape(search)
        query_parts.append({"$or": [
            {"user_id": {"$regex": pattern, "$options": "i"}},
            {"description": {"$regex": pattern, "$options": "i"}},
            {"stream": {"$regex": pattern, "$options": "i"}},
        ]})

    query = {"$and": query_parts} if len(query_parts) > 1 else (query_parts[0] if query_parts else {})
    transactions = _all_intents()
    total = transactions.count_documents(query)
    cursor = (
        transactions.find(query)
        .sort("created_at", DESCENDING)
        .skip((page - 1) * per_page)
        .limit(per_page)
    )
    items = [_intent_for_admin(item) for item in cursor]
    pages = (total + per_page - 1) // per_page

    return jsonify({
        "success": True,
        "items": items,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
            "has_previous": page > 1,
            "has_next": page < pages,
        },
        "billing_enabled": False,
    }), 200


@revenue_bp.get("/admin/plans")
@require_authenticated
@require_roles(*PLATFORM_ADMIN_ROLES)
def revenue_admin_list_plans():
    from backend.revenue.mpesa import checkout_is_production_configured
    live_checkout = checkout_is_production_configured()
    return jsonify({
        "success": True,
        "pricing_status": get_pricing_status(),
        "billing_enabled": live_checkout,
        "checkout_enabled": live_checkout,
        "plans": list_plans(include_retired=True),
    }), 200


@revenue_bp.post("/admin/plans")
@require_authenticated
@require_roles(*PLATFORM_ADMIN_ROLES)
def revenue_admin_create_plan():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("A JSON request body is required.", 400, "invalid_json_body")

    try:
        values = _validate_plan_values(data, creating=True)
    except ValueError as exc:
        return _error(str(exc), 400, "invalid_plan")

    code = values["code"]
    plans_collection = collection(PLANS_COLLECTION)
    plans_collection.create_index("code", unique=True, sparse=True, name="uq_jumuiya_revenue_plan_code")
    if get_plan(code) is not None:
        return _error("A plan with this code already exists.", 409, "plan_code_conflict")

    timestamp = now_utc()
    actor_id = current_user_id()
    document = {
        **values,
        "created_at": timestamp,
        "updated_at": timestamp,
        "created_by": actor_id,
        "updated_by": actor_id,
        "managed_by": "platform_admin",
    }
    try:
        plans_collection.insert_one(document)
    except DuplicateKeyError:
        return _error("A plan with this code already exists.", 409, "plan_code_conflict")

    log_action(
        user_id=actor_id,
        action="revenue.plan.created",
        resource="revenue_plan",
        resource_id=code,
        metadata={"hub": values["hub"], "status": values["status"]},
    )

    plan = get_plan(code)
    from backend.revenue.mpesa import checkout_is_production_configured
    published = values["status"] == "available" and checkout_is_production_configured()
    return jsonify({
        "success": True,
        "message": (
            "Plan published for M-Pesa subscription checkout."
            if published else
            "Plan saved to the proposed catalogue; it is not purchasable until published."
        ),
        "plan": plan,
        "billing_enabled": published,
        "checkout_enabled": published,
    }), 201


@revenue_bp.put("/admin/plans/<plan_code>")
@require_authenticated
@require_roles(*PLATFORM_ADMIN_ROLES)
def revenue_admin_update_plan(plan_code):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("A JSON request body is required.", 400, "invalid_json_body")

    existing = get_plan(plan_code)
    if existing is None:
        return _error("Plan not found.", 404, "plan_not_found")

    try:
        values = _validate_plan_values(data, creating=False, existing=existing)
    except ValueError as exc:
        return _error(str(exc), 400, "invalid_plan")

    actor_id = current_user_id()
    timestamp = now_utc()
    values.update({
        "code": existing["code"],
        "hub": existing["hub"],
        "updated_at": timestamp,
        "updated_by": actor_id,
        "managed_by": "platform_admin",
    })

    collection(PLANS_COLLECTION).update_one(
        {"code": existing["code"]},
        {"$set": values},
        upsert=True,
    )
    log_action(
        user_id=actor_id,
        action="revenue.plan.updated",
        resource="revenue_plan",
        resource_id=existing["code"],
        metadata={"changed_fields": sorted(data.keys()), "status": values["status"]},
    )

    from backend.revenue.mpesa import checkout_is_production_configured
    published = values["status"] == "available" and checkout_is_production_configured()
    return jsonify({
        "success": True,
        "message": (
            "Plan published for M-Pesa subscription checkout."
            if published else
            "Plan moved to proposed status and is no longer purchasable."
            if values["status"] == "proposed" else
            "Plan retired and is no longer purchasable."
        ),
        "plan": get_plan(existing["code"]),
        "billing_enabled": published,
        "checkout_enabled": published,
    }), 200
