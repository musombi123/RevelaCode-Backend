"""Subscription and entitlement services for the existing Jumuiya Revenue Engine.

Paid subscriptions are created only from a provider-adapter callback that is
HMAC-authenticated after that adapter independently verifies the payment with
the payment provider. This module never assumes that a browser return or an
unsigned provider callback means money was received.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from functools import wraps
from threading import Lock
from datetime import datetime, timedelta, timezone

from flask import current_app, jsonify, request
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.audit import log_action, now_utc
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.permissions import current_user_id, require_authenticated, require_roles
from backend.revenue import revenue_bp
from backend.revenue.constants import CURRENCY_DEFAULT
from backend.revenue.money import MoneyValidationError, to_money
from backend.revenue.ledger import COLLECTION_NAME as REVENUE_TRANSACTIONS_COLLECTION, _ensure_indexes as _ensure_revenue_ledger_indexes
from backend.revenue.plans import get_plan

SUBSCRIPTIONS_COLLECTION = "jumuiya_revenue_subscriptions"
PAYMENT_EVENTS_COLLECTION = "jumuiya_revenue_payment_events"
TRIALS_COLLECTION = "jumuiya_revenue_trials"

_SUBSCRIPTION_INDEX_LOCK = Lock()
_SUBSCRIPTION_INDEXES_READY = False

HUBS = {
    "shamba", "biashara", "elimu", "community", "smart_ai",
    "marketplace", "faith",
}
ADMIN_ROLES = ("admin", "platform_admin", "super_admin", "revelacode_admin")
PREMIUM_FEATURES = {
    "premium", "advanced_ai", "image_generation", "document_analysis",
    "voice_generation", "long_memory", "advanced_analytics",
    "advanced_reports", "automation", "expanded_history", "seller_tools", "vision_analysis",
}


def _as_utc(value):
    if value is None:
        return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _iso(value):
    normalized = _as_utc(value)
    return normalized.isoformat() if normalized else None


def _subscription_collection():
    global _SUBSCRIPTION_INDEXES_READY
    rows = collection(SUBSCRIPTIONS_COLLECTION)
    if not _SUBSCRIPTION_INDEXES_READY:
        with _SUBSCRIPTION_INDEX_LOCK:
            if not _SUBSCRIPTION_INDEXES_READY:
                rows.create_index(
                    [("provider", ASCENDING), ("provider_transaction_id", ASCENDING)],
                    unique=True,
                    name="uq_revenue_subscription_provider_transaction",
                )
                rows.create_index(
                    [("user_id", ASCENDING), ("hub", ASCENDING), ("ends_at", DESCENDING)],
                    name="ix_revenue_subscription_user_hub_end",
                )
                _SUBSCRIPTION_INDEXES_READY = True
    return rows


def _events_collection():
    rows = collection(PAYMENT_EVENTS_COLLECTION)
    rows.create_index(
        [("provider", ASCENDING), ("provider_transaction_id", ASCENDING)],
        unique=True,
        name="uq_revenue_payment_event_provider_transaction",
    )
    rows.create_index([("created_at", DESCENDING)], name="ix_revenue_payment_event_created")
    return rows


def _record_confirmed_revenue_transaction(event, plan, subscription):
    """Idempotently append a successful provider-confirmed payment to the shared ledger."""
    _ensure_revenue_ledger_indexes()
    rows = collection(REVENUE_TRANSACTIONS_COLLECTION)
    provider = str(event["provider"]).strip().lower()
    provider_transaction_id = str(event["provider_transaction_id"]).strip()
    user_id = str(event["user_id"]).strip()
    idempotency_key = "paid:" + hashlib.sha256(
        f"{provider}:{provider_transaction_id}".encode("utf-8")
    ).hexdigest()
    key_query = {"user_id": user_id, "idempotency_key": idempotency_key}
    existing = rows.find_one(key_query)
    if existing:
        if (
            existing.get("payment_confirmed") is True
            and existing.get("payment_provider") == provider
            and existing.get("provider_transaction_id") == provider_transaction_id
        ):
            return existing
        raise RuntimeError("The verified provider payment conflicts with an existing revenue ledger key.")

    now = now_utc()
    hub = str(plan.get("hub") or subscription.get("hub") or "").strip().lower()
    document = {
        "user_id": user_id,
        "stream": hub,
        "plan_code": str(event["plan_code"]),
        "amount": str(event["amount"]),
        "currency": str(event["currency"]),
        "description": f"Verified subscription payment: {event['plan_code']}",
        "idempotency_key": idempotency_key,
        "request_fingerprint": hashlib.sha256(
            json.dumps({
                "provider": provider,
                "provider_transaction_id": provider_transaction_id,
                "user_id": user_id,
                "plan_code": str(event["plan_code"]),
                "amount": str(event["amount"]),
                "currency": str(event["currency"]),
            }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "status": "succeeded",
        "billing_enabled": True,
        "charge_attempted": True,
        "payment_confirmed": True,
        "payment_provider": provider,
        "provider_transaction_id": provider_transaction_id,
        "receipt": str(event.get("receipt") or provider_transaction_id)[:128],
        "paid_at": now,
        "subscription_id": str(subscription.get("_id", "")),
        "created_at": now,
        "updated_at": now,
        "source": "verified_provider_payment",
    }
    try:
        result = rows.insert_one(document)
        document["_id"] = result.inserted_id
    except DuplicateKeyError:
        existing = rows.find_one(key_query)
        if existing and (
            existing.get("payment_confirmed") is True
            and existing.get("payment_provider") == provider
            and existing.get("provider_transaction_id") == provider_transaction_id
        ):
            return existing
        raise RuntimeError("The verified payment could not be safely appended to the revenue ledger.") from None

    try:
        log_action(
            user_id=user_id,
            action="revenue.payment.verified",
            resource="revenue_transaction",
            resource_id=str(document["_id"]),
            metadata={
                "hub": hub,
                "plan_code": event["plan_code"],
                "provider": provider,
                "amount": event["amount"],
                "currency": event["currency"],
                "provider_transaction_id": provider_transaction_id,
            },
        )
    except Exception:
        current_app.logger.exception("Verified payment was recorded but the audit record could not be written")
    return document


def _public_subscription(row):
    status = str(row.get("status", "active"))
    now = _as_utc(now_utc())
    starts_at = _as_utc(row.get("starts_at"))
    ends_at = _as_utc(row.get("ends_at"))
    if status == "active" and ends_at and ends_at <= now:
        status = "expired"
    elif status == "active" and starts_at and starts_at > now:
        status = "scheduled"
    return {
        "id": str(row.get("_id", "")),
        "hub": row.get("hub"),
        "plan_code": row.get("plan_code"),
        "provider": row.get("provider"),
        "provider_transaction_id": row.get("provider_transaction_id"),
        "amount": row.get("amount"),
        "currency": row.get("currency", CURRENCY_DEFAULT),
        "status": status,
        "starts_at": _iso(starts_at),
        "ends_at": _iso(ends_at),
        "created_at": _iso(row.get("created_at")),
    }


def _active_subscription(user_id, hub, now=None):
    now = _as_utc(now or now_utc())
    rows = _subscription_collection().find({
        "user_id": str(user_id),
        "hub": {"$in": [hub, "all"]},
        "status": "active",
    }).sort("ends_at", DESCENDING)
    for row in rows:
        starts_at = _as_utc(row.get("starts_at"))
        ends_at = _as_utc(row.get("ends_at"))
        if starts_at and ends_at and starts_at <= now < ends_at:
            return row
    return None


def resolve_entitlement(user_id, hub, feature="essential"):
    """Resolve an entitlement centrally; free essential access is never removed."""
    hub = str(hub or "").strip().lower()
    feature = str(feature or "essential").strip().lower()
    if hub not in HUBS:
        raise ValueError("Unsupported hub.")
    if feature not in PREMIUM_FEATURES | {"essential"}:
        raise ValueError("Unsupported entitlement feature.")

    now = _as_utc(now_utc())
    subscription = _active_subscription(user_id, hub, now)
    trial = collection(TRIALS_COLLECTION).find_one({"user_id": str(user_id), "hub": hub})
    trial_ends = _as_utc(trial.get("ends_at")) if trial else None
    trial_starts = _as_utc(trial.get("started_at")) if trial else None
    trial_active = bool(trial_ends and trial_starts and trial_starts <= now < trial_ends)
    paid = bool(subscription)
    premium_access = paid or trial_active
    premium_feature = feature in PREMIUM_FEATURES
    allowed = True if not premium_feature else premium_access

    if paid:
        tier = "paid"
        reason = "active_subscription"
    elif trial_active:
        tier = "trial"
        reason = "active_trial"
    else:
        tier = "free"
        reason = "free_tier"
    if premium_feature and not allowed:
        reason = "premium_entitlement_required"

    result = {
        "success": True,
        "user_id": str(user_id),
        "hub": hub,
        "feature": feature,
        "allowed": allowed,
        "tier": tier,
        "access": tier,
        "reason": reason,
        "premium_access": premium_access,
        "paid_subscription": paid,
        "trial_status": (
            "active" if trial_active else
            "expired" if trial else
            "not_started"
        ),
        "trial": {
            "started_at": _iso(trial_starts),
            "ends_at": _iso(trial_ends),
            "trial_days": int(trial.get("trial_days", 30)) if trial else 30,
        } if trial else None,
        "subscription": _public_subscription(subscription) if subscription else None,
        "billing_enabled": False,
    }
    return result


def _error(message, status=400, code="invalid_request"):
    return jsonify({
        "success": False,
        "message": message,
        "error": {"message": message, "code": code},
        "code": code,
    }), status
def require_revenue_entitlement(hub, feature):
    """Protect a premium hub capability while preserving essential free access."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                entitlement = resolve_entitlement(current_user_id(), hub, feature)
            except ValueError as exc:
                return _error(str(exc), 400, "invalid_entitlement_request")
            except Exception:
                current_app.logger.exception(
                    "Could not resolve revenue entitlement | hub=%s feature=%s",
                    hub, feature,
                )
                return _error(
                    "Access could not be verified right now. Please retry.",
                    503,
                    "revenue_entitlement_unavailable",
                )
            if entitlement.get("allowed") is not True:
                return jsonify({
                    "success": False,
                    "code": "premium_entitlement_required",
                    "message": "Start this hub's free trial or subscribe to unlock this feature.",
                    "entitlement": entitlement,
                }), 402
            return fn(*args, **kwargs)
        return wrapper
    return decorator



def _read_verified_payment():
    """Validate a signed provider-adapter event; raw unsigned callbacks cannot activate access."""
    secret = os.getenv("REVENUE_PROVIDER_WEBHOOK_SECRET", "").strip()
    if len(secret) < 32:
        raise ValueError("Verified payment activation is not configured.")
    raw = request.get_data(cache=True, as_text=False)
    supplied = request.headers.get("X-Revenue-Signature", "").strip()
    if supplied.startswith("sha256="):
        supplied = supplied[7:]
    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(supplied.lower(), expected):
        raise PermissionError("Invalid provider signature.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("A valid JSON payment event is required.") from None
    if not isinstance(payload, dict):
        raise ValueError("A JSON object payment event is required.")
    required = {"provider", "provider_transaction_id", "user_id", "plan_code", "amount", "currency"}
    missing = required - set(payload)
    extra = set(payload) - (required | {"paid_at", "receipt", "metadata"})
    if missing or extra:
        raise ValueError(
            ("Missing fields: " + ", ".join(sorted(missing)) + ". ") if missing else
            ("Unsupported fields: " + ", ".join(sorted(extra)) + ".")
        )
    provider = str(payload["provider"]).strip().lower()
    allowed_providers = {
        item.strip().lower()
        for item in os.getenv("REVENUE_PAYMENT_PROVIDERS", "mpesa").split(",")
        if item.strip()
    }
    if provider not in allowed_providers:
        raise ValueError("This payment provider is not enabled.")
    transaction_id = str(payload["provider_transaction_id"]).strip()
    user_id = str(payload["user_id"]).strip()
    plan_code = str(payload["plan_code"]).strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{3,128}", transaction_id):
        raise ValueError("Invalid provider transaction reference.")
    if not user_id or len(user_id) > 128 or any(ord(ch) < 33 for ch in user_id):
        raise ValueError("Invalid user identifier.")
    if not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", plan_code) or len(plan_code) > 60:
        raise ValueError("Invalid plan code.")
    currency = str(payload["currency"]).strip().upper()
    if currency != CURRENCY_DEFAULT:
        raise ValueError(f"Only {CURRENCY_DEFAULT} payments are supported.")
    try:
        amount = to_money(payload["amount"], allow_zero=False)
    except MoneyValidationError:
        raise ValueError("The verified payment amount is invalid.") from None
    return {
        "provider": provider,
        "provider_transaction_id": transaction_id,
        "user_id": user_id,
        "plan_code": plan_code,
        "amount": f"{amount:.2f}",
        "currency": currency,
        "receipt": str(payload.get("receipt") or transaction_id)[:128],
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }


@revenue_bp.get("/admin/billing/status")
@require_authenticated
@require_roles(*ADMIN_ROLES)
def revenue_billing_status():
    """Report configuration state without leaking secrets or claiming checkout is live."""
    secret_ready = len(os.getenv("REVENUE_PROVIDER_WEBHOOK_SECRET", "").strip()) >= 32
    from backend.revenue.mpesa import checkout_is_configured
    mpesa_ready = checkout_is_configured()
    providers = [
        item.strip().lower()
        for item in os.getenv("REVENUE_PAYMENT_PROVIDERS", "mpesa").split(",")
        if item.strip()
    ]
    return jsonify({
        "success": True,
        "checkout_enabled": mpesa_ready,
        "mpesa_checkout_enabled": mpesa_ready,
        "provider_callback_enabled": secret_ready or mpesa_ready,
        "providers_allowed": providers,
        "activation_mode": "verified_provider_adapter_only",
        "message": (
            "Daraja checkout is configured. Keep plan prices in proposed status until the published price and live callback have been verified."
            if mpesa_ready else
            "A signed provider activation endpoint is configured; checkout still requires an enabled payment adapter."
            if secret_ready else
            "Configure Daraja credentials and a public HTTPS callback URL before checkout can start."
        ),
    }), 200


def activate_verified_payment(event):
    """Activate a subscription after a provider-specific adapter verified payment."""
    plan = get_plan(event["plan_code"])
    if not plan:
        return _error("The purchased plan does not exist.", 404, "plan_not_found")
    if str(plan.get("status", "")).lower() != "available":
        return _error("This plan is not enabled for paid checkout.", 409, "plan_not_purchasable")
    if str(plan.get("hub", "")).lower() not in HUBS:
        return _error("One-time campaigns are not subscription plans.", 400, "subscription_plan_required")
    if str(plan.get("interval", "")).lower() not in {"month", "year"}:
        return _error("Only monthly and yearly subscriptions can activate hub access.", 400, "invalid_subscription_interval")
    try:
        expected = to_money(plan.get("amount"), allow_zero=False)
        received = to_money(event["amount"], allow_zero=False)
    except MoneyValidationError:
        return _error("The plan price is not configured as a positive amount.", 409, "invalid_plan_price")
    if expected != received or str(plan.get("currency", CURRENCY_DEFAULT)).upper() != event["currency"]:
        return _error("Verified payment does not match the configured plan price.", 409, "payment_amount_mismatch")

    events = _events_collection()
    query = {
        "provider": event["provider"],
        "provider_transaction_id": event["provider_transaction_id"],
    }
    now = now_utc()
    existing = events.find_one(query)
    if existing and existing.get("subscription_activated") is True:
        # Repair a prior successful activation if an older release marked the
        # event complete before writing the shared revenue history.
        applied_subscription = _subscription_collection().find_one(query)
        if applied_subscription:
            try:
                _record_confirmed_revenue_transaction(event, plan, applied_subscription)
            except Exception:
                current_app.logger.exception("Verified payment could not be reconciled into the revenue ledger")
                return _error("Payment was verified but the transaction history needs reconciliation. Retry status refresh; do not pay again.", 503, "revenue_ledger_reconciliation_pending")
        return jsonify({
            "success": True,
            "replayed": True,
            "subscription": existing.get("subscription"),
            "message": "This verified payment was already applied.",
        }), 200
    if not existing:
        try:
            events.insert_one({
                **event,
                "status": "verified",
                "subscription_activated": False,
                "created_at": now,
                "updated_at": now,
            })
        except DuplicateKeyError:
            existing = events.find_one(query)
            if existing and existing.get("subscription_activated") is True:
                applied_subscription = _subscription_collection().find_one(query)
                if applied_subscription:
                    _record_confirmed_revenue_transaction(event, plan, applied_subscription)
                return jsonify({"success": True, "replayed": True, "subscription": existing.get("subscription")}), 200

    subs = _subscription_collection()
    already_applied = subs.find_one({
        "provider": event["provider"],
        "provider_transaction_id": event["provider_transaction_id"],
    })
    if already_applied:
        try:
            _record_confirmed_revenue_transaction(event, plan, already_applied)
        except Exception:
            current_app.logger.exception("Verified payment could not be reconciled into the revenue ledger")
            return _error("Payment was verified but the transaction history needs reconciliation. Retry status refresh; do not pay again.", 503, "revenue_ledger_reconciliation_pending")
        public = _public_subscription(already_applied)
        events.update_one(query, {"$set": {
            "subscription_activated": True,
            "subscription": public,
            "updated_at": now,
        }})
        return jsonify({"success": True, "replayed": True, "subscription": public}), 200

    previous_ends = []
    for row in subs.find({
        "user_id": event["user_id"],
        "hub": str(plan["hub"]).lower(),
        "status": "active",
    }):
        ends_at = _as_utc(row.get("ends_at"))
        if ends_at and ends_at > now:
            previous_ends.append(ends_at)
    starts_at = max([_as_utc(now), *previous_ends])
    interval = str(plan["interval"]).lower()
    ends_at = starts_at + (timedelta(days=365) if interval == "year" else timedelta(days=30))
    subscription = {
        "user_id": event["user_id"],
        "hub": str(plan["hub"]).lower(),
        "plan_code": event["plan_code"],
        "provider": event["provider"],
        "provider_transaction_id": event["provider_transaction_id"],
        "receipt": event["receipt"],
        "amount": event["amount"],
        "currency": event["currency"],
        "interval": interval,
        "status": "active",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "created_at": now,
        "source": "verified_provider_adapter",
    }
    try:
        inserted = subs.insert_one(subscription)
        subscription["_id"] = inserted.inserted_id
    except DuplicateKeyError:
        already_applied = subs.find_one(query)
        if not already_applied:
            return _error("The payment was verified but subscription activation needs retry.", 503, "subscription_activation_retry")
        subscription = already_applied

    # Do not call the payment event applied until the confirmed payment is
    # durably present in the same transaction history the Revenue Center reads.
    try:
        _record_confirmed_revenue_transaction(event, plan, subscription)
    except Exception:
        current_app.logger.exception("Subscription exists but verified payment ledger reconciliation failed")
        return _error("Payment was verified but the transaction history needs reconciliation. Retry status refresh; do not pay again.", 503, "revenue_ledger_reconciliation_pending")
    public = _public_subscription(subscription)
    events.update_one(query, {"$set": {
        "subscription_activated": True,
        "subscription": public,
        "updated_at": now_utc(),
    }})
    try:
        log_action(
            user_id=event["user_id"],
            action="revenue.subscription.activated",
            resource="revenue_subscription",
            resource_id=public["id"],
            metadata={
                "hub": public["hub"],
                "plan_code": public["plan_code"],
                "provider": event["provider"],
                "amount": event["amount"],
                "currency": event["currency"],
                "provider_transaction_id": event["provider_transaction_id"],
            },
        )
    except Exception:
        current_app.logger.exception("Subscription activated but the audit record could not be written")

    return jsonify({
        "success": True,
        "replayed": False,
        "subscription": public,
        "message": "Verified payment applied and subscription activated.",
    }), 201


@revenue_bp.post("/providers/verified-payment")
def revenue_verified_payment():
    """Activate a subscription only from a trusted, signed, provider-verified event.

    Provider adapters must verify the actual payment against the provider before
    signing and forwarding this canonical event. The endpoint does not accept a
    browser redirect as proof of payment.
    """
    try:
        event = _read_verified_payment()
    except PermissionError:
        return _error("The provider signature could not be verified.", 401, "invalid_provider_signature")
    except ValueError as exc:
        status = 503 if "not configured" in str(exc).lower() else 400
        return _error(str(exc), status, "payment_activation_not_configured" if status == 503 else "invalid_payment_event")

    return activate_verified_payment(event)

@revenue_bp.get("/subscriptions")
@require_authenticated
def revenue_my_subscriptions():
    """List the authenticated user's own subscriptions and their expiry state."""
    user_id = current_user_id()
    rows = _subscription_collection().find({"user_id": user_id}).sort("created_at", DESCENDING)
    items = [_public_subscription(row) for row in rows.limit(100)]
    return jsonify({"success": True, "items": items}), 200


@revenue_bp.get("/admin/subscriptions")
@require_authenticated
@require_roles(*ADMIN_ROLES)
def revenue_admin_subscriptions():
    try:
        page = max(1, int(request.args.get("page", "1")))
        per_page = min(100, max(1, int(request.args.get("per_page", "25"))))
    except (TypeError, ValueError):
        return _error("Pagination values must be whole numbers.", 400, "invalid_pagination")
    hub = request.args.get("hub", "").strip().lower()
    status = request.args.get("status", "").strip().lower()
    query = {}
    if hub:
        if hub not in HUBS:
            return _error("Unsupported hub.", 400, "unsupported_hub")
        query["hub"] = hub
    if status:
        if status not in {"active", "cancelled", "expired", "past_due"}:
            return _error("Unsupported subscription status.", 400, "unsupported_status")
        query["status"] = status
    rows = _subscription_collection()
    total = rows.count_documents(query)
    items = [
        _public_subscription(row)
        for row in rows.find(query).sort("created_at", DESCENDING).skip((page - 1) * per_page).limit(per_page)
    ]
    return jsonify({
        "success": True,
        "items": items,
        "pagination": {
            "page": page, "per_page": per_page, "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
    }), 200


@revenue_bp.get("/admin/trials")
@require_authenticated
@require_roles(*ADMIN_ROLES)
def revenue_admin_trials():
    try:
        page = max(1, int(request.args.get("page", "1")))
        per_page = min(100, max(1, int(request.args.get("per_page", "25"))))
    except (TypeError, ValueError):
        return _error("Pagination values must be whole numbers.", 400, "invalid_pagination")
    trials = collection(TRIALS_COLLECTION)
    total = trials.count_documents({})
    items = []
    for row in trials.find({}).sort("started_at", DESCENDING).skip((page - 1) * per_page).limit(per_page):
        items.append({
            "id": str(row.get("_id", "")),
            "user_id": str(row.get("user_id", "")),
            "hub": row.get("hub"),
            "status": row.get("status", "active"),
            "started_at": _iso(row.get("started_at")),
            "ends_at": _iso(row.get("ends_at")),
            "trial_days": row.get("trial_days", 30),
        })
    return jsonify({
        "success": True,
        "items": items,
        "pagination": {
            "page": page, "per_page": per_page, "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
    }), 200
