"""Read-only plan entitlement resolver.

The revenue ledger currently stores payment intents only. This module never
creates a subscription or promotes an intent to a paid entitlement. Paid
access can resolve only from a separate, provider-verified and unexpired
subscription record once billing has been explicitly enabled.
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.revenue.constants import SUPPORTED_REVENUE_STREAMS
from backend.revenue.plans import PRICING_STATUS, get_plan


SUBSCRIPTIONS_COLLECTION = "jumuiya_revenue_subscriptions"

# Deliberately false until provider verification, reconciliation and subscription
# lifecycle support are implemented and reviewed. Do not toggle via a client input.
BILLING_ENABLED = False

VERIFIED_SUBSCRIPTION_CONTRACT = {
    "status": "active",
    "payment_status": "succeeded",
    "payment_verified": True,
    "provider_reference": "non-empty string",
    "payment_verified_at": "datetime",
    "starts_at": "datetime <= now",
    "expires_at": "datetime > now",
    "revoked_at": "missing or null",
}


def now_utc():
    return datetime.now(timezone.utc)


def _as_datetime(value):
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _public_subscription(subscription, plan):
    return {
        "subscription_id": str(subscription.get("_id") or ""),
        "plan_code": plan.get("code"),
        "plan_name": plan.get("name"),
        "hub": plan.get("hub"),
        "status": "active",
        "starts_at": _as_datetime(subscription.get("starts_at")).isoformat(),
        "expires_at": _as_datetime(subscription.get("expires_at")).isoformat(),
        "features": list(plan.get("features") or []),
        "source": "verified_subscription",
    }


def _verified_and_current(subscription, now):
    if subscription.get("status") != "active":
        return False
    if subscription.get("payment_status") != "succeeded":
        return False
    if subscription.get("payment_verified") is not True:
        return False
    if not str(subscription.get("provider_reference") or "").strip():
        return False
    if not _as_datetime(subscription.get("payment_verified_at")):
        return False
    starts_at = _as_datetime(subscription.get("starts_at"))
    expires_at = _as_datetime(subscription.get("expires_at"))
    if not starts_at or not expires_at:
        return False
    if starts_at > now or expires_at <= now:
        return False
    if subscription.get("revoked_at") is not None:
        return False
    return True


def get_entitlement_snapshot(user_id, hub=None):
    """Describe effective plan access without activating or charging anything."""
    user_id = str(user_id or "").strip()
    if not user_id:
        raise APIError("An authenticated user ID is required.", 401, "authentication_required")

    selected_hub = str(hub or "").strip().lower()
    if selected_hub and selected_hub not in SUPPORTED_REVENUE_STREAMS:
        raise APIError("Unsupported hub or revenue stream.", 400, "unsupported_revenue_stream")

    free_plan = get_plan("free") or {
        "code": "free",
        "name": "Jumuiya Free",
        "hub": "all",
        "features": [],
        "status": "available",
        "amount": "0.00",
        "currency": "KES",
    }

    # The current catalog says draft and billing is disabled. Do not even read
    # subscription records in this mode; pending payment intents cannot grant access.
    if not BILLING_ENABLED or str(PRICING_STATUS).strip().lower() != "active":
        return {
            "user_id": user_id,
            "hub": selected_hub or "all",
            "billing_enabled": False,
            "pricing_status": PRICING_STATUS,
            "subscription_state": "billing_disabled",
            "effective_plan": {
                "code": free_plan.get("code", "free"),
                "name": free_plan.get("name", "Jumuiya Free"),
                "hub": free_plan.get("hub", "all"),
                "status": "baseline",
                "features": list(free_plan.get("features") or []),
            },
            "active_subscriptions": [],
            "paid_entitlements": [],
            "limits": None,
            "pending_intents_grant_access": False,
            "policy_note": (
                "Paid subscriptions are not active while billing is disabled. "
                "Selecting a plan or recording a payment intent does not grant paid access."
            ),
        }

    now = now_utc()
    records = collection(SUBSCRIPTIONS_COLLECTION).find({
        "user_id": user_id,
        "status": "active",
    }).limit(100)

    active = []
    for subscription in records:
        if not _verified_and_current(subscription, now):
            continue
        plan = get_plan(subscription.get("plan_code"))
        if not plan or str(plan.get("status") or "").lower() != "available":
            continue
        plan_hub = str(plan.get("hub") or "").lower()
        if selected_hub and plan_hub not in {selected_hub, "all"}:
            continue
        active.append(_public_subscription(subscription, plan))

    active.sort(key=lambda item: (item.get("hub") or "", item.get("plan_code") or ""))
    selected = next(
        (item for item in active if item.get("hub") == selected_hub),
        None,
    ) if selected_hub else (active[0] if active else None)

    if selected:
        effective_plan = {
            "code": selected["plan_code"],
            "name": selected["plan_name"],
            "hub": selected["hub"],
            "status": "active",
            "features": selected["features"],
        }
        state = "active_verified_subscription"
        paid = [{
            "plan_code": selected["plan_code"],
            "hub": selected["hub"],
            "features": selected["features"],
        }]
    else:
        effective_plan = {
            "code": free_plan.get("code", "free"),
            "name": free_plan.get("name", "Jumuiya Free"),
            "hub": free_plan.get("hub", "all"),
            "status": "baseline",
            "features": list(free_plan.get("features") or []),
        }
        state = "free_baseline"
        paid = []

    return {
        "user_id": user_id,
        "hub": selected_hub or "all",
        "billing_enabled": True,
        "pricing_status": PRICING_STATUS,
        "subscription_state": state,
        "effective_plan": effective_plan,
        "active_subscriptions": active,
        "paid_entitlements": paid,
        "limits": None,
        "pending_intents_grant_access": False,
        "policy_note": (
            "Subscription records are considered only when the payment is provider-verified, "
            "the subscription is active and within its validity period, and the plan is currently available."
        ),
    }
