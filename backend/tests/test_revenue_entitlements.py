import sys
import types
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId

_missing_module = object()
_original_db_module = sys.modules.get("backend.db", _missing_module)
_test_db_module = types.ModuleType("backend.db")
_test_db_module.get_db = lambda: None
sys.modules["backend.db"] = _test_db_module
try:
    from backend.revenue import entitlements
finally:
    if _original_db_module is _missing_module:
        sys.modules.pop("backend.db", None)
    else:
        sys.modules["backend.db"] = _original_db_module

from backend.jumuiya.core.errors import APIError


class Cursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(deepcopy(self.documents))


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = [deepcopy(row) for row in (documents or [])]
        self.queries = []

    def find(self, query=None):
        query = query or {}
        self.queries.append(deepcopy(query))
        return Cursor([
            row for row in self.documents
            if all(row.get(key) == value for key, value in query.items())
        ])


@pytest.fixture
def subscription_store(monkeypatch):
    now = datetime.now(timezone.utc)
    good_id = ObjectId("64b000000000000000000301")
    unverified_id = ObjectId("64b000000000000000000302")
    expired_id = ObjectId("64b000000000000000000303")
    retired_plan_id = ObjectId("64b000000000000000000304")
    other_user_id = ObjectId("64b000000000000000000305")
    records = FakeCollection([
        {
            "_id": good_id,
            "user_id": "owner-1",
            "plan_code": "biashara_pro",
            "status": "active",
            "payment_status": "succeeded",
            "payment_verified": True,
            "provider_reference": "verified-provider-ref-123",
            "payment_verified_at": now - timedelta(hours=1),
            "starts_at": now - timedelta(days=1),
            "expires_at": now + timedelta(days=29),
            "revoked_at": None,
        },
        {
            "_id": unverified_id,
            "user_id": "owner-1",
            "plan_code": "biashara_pro",
            "status": "active",
            "payment_status": "succeeded",
            "payment_verified": False,
            "provider_reference": "customer-supplied-reference",
            "payment_verified_at": now - timedelta(hours=1),
            "starts_at": now - timedelta(days=1),
            "expires_at": now + timedelta(days=29),
            "revoked_at": None,
        },
        {
            "_id": expired_id,
            "user_id": "owner-1",
            "plan_code": "biashara_pro",
            "status": "active",
            "payment_status": "succeeded",
            "payment_verified": True,
            "provider_reference": "expired-provider-ref",
            "payment_verified_at": now - timedelta(days=45),
            "starts_at": now - timedelta(days=60),
            "expires_at": now - timedelta(days=30),
            "revoked_at": None,
        },
        {
            "_id": retired_plan_id,
            "user_id": "owner-1",
            "plan_code": "old_biashara",
            "status": "active",
            "payment_status": "succeeded",
            "payment_verified": True,
            "provider_reference": "retired-provider-ref",
            "payment_verified_at": now - timedelta(hours=1),
            "starts_at": now - timedelta(days=1),
            "expires_at": now + timedelta(days=29),
            "revoked_at": None,
        },
        {
            "_id": other_user_id,
            "user_id": "owner-2",
            "plan_code": "biashara_pro",
            "status": "active",
            "payment_status": "succeeded",
            "payment_verified": True,
            "provider_reference": "other-user-provider-ref",
            "payment_verified_at": now - timedelta(hours=1),
            "starts_at": now - timedelta(days=1),
            "expires_at": now + timedelta(days=29),
            "revoked_at": None,
        },
        {
            "_id": ObjectId("64b000000000000000000306"),
            "user_id": "owner-1",
            "plan_code": "biashara_pro",
            "status": "pending",
            "payment_status": "pending",
            "payment_verified": False,
            "provider_reference": None,
            "starts_at": now,
            "expires_at": now + timedelta(days=30),
        },
    ])
    plans = {
        "free": {
            "code": "free",
            "name": "Jumuiya Free",
            "hub": "all",
            "amount": "0.00",
            "currency": "KES",
            "status": "available",
            "features": ["Essential hub features", "Basic records and management"],
        },
        "biashara_pro": {
            "code": "biashara_pro",
            "name": "Biashara Pro",
            "hub": "biashara",
            "amount": "499.00",
            "currency": "KES",
            "status": "available",
            "features": ["Advanced sales analytics", "Business insights"],
        },
        "old_biashara": {
            "code": "old_biashara",
            "name": "Legacy plan",
            "hub": "biashara",
            "amount": "99.00",
            "currency": "KES",
            "status": "retired",
            "features": ["Legacy features"],
        },
    }
    monkeypatch.setattr(entitlements, "collection", lambda name: records)
    monkeypatch.setattr(entitlements, "get_plan", lambda code: plans.get(str(code or "").lower()))
    return {"records": records, "plans": plans, "now": now}


def test_billing_draft_defaults_to_free_and_never_queries_subscriptions(subscription_store, monkeypatch):
    monkeypatch.setattr(entitlements, "BILLING_ENABLED", False)
    monkeypatch.setattr(entitlements, "PRICING_STATUS", "draft")

    snapshot = entitlements.get_entitlement_snapshot("owner-1", hub="biashara")

    assert snapshot["billing_enabled"] is False
    assert snapshot["pricing_status"] == "draft"
    assert snapshot["subscription_state"] == "billing_disabled"
    assert snapshot["effective_plan"]["code"] == "free"
    assert snapshot["paid_entitlements"] == []
    assert snapshot["pending_intents_grant_access"] is False
    assert snapshot["limits"] is None
    assert subscription_store["records"].queries == []


def test_paid_entitlement_requires_verified_unexpired_subscription_and_available_plan(subscription_store, monkeypatch):
    monkeypatch.setattr(entitlements, "BILLING_ENABLED", True)
    monkeypatch.setattr(entitlements, "PRICING_STATUS", "active")

    snapshot = entitlements.get_entitlement_snapshot("owner-1", hub="biashara")

    assert snapshot["billing_enabled"] is True
    assert snapshot["subscription_state"] == "active_verified_subscription"
    assert snapshot["effective_plan"]["code"] == "biashara_pro"
    assert len(snapshot["active_subscriptions"]) == 1
    assert snapshot["active_subscriptions"][0]["subscription_id"] == "64b000000000000000000301"
    assert snapshot["paid_entitlements"] == [{
        "plan_code": "biashara_pro",
        "hub": "biashara",
        "features": ["Advanced sales analytics", "Business insights"],
    }]
    assert subscription_store["records"].queries == [{
        "user_id": "owner-1",
        "status": "active",
    }]


def test_subscription_records_are_scoped_to_authenticated_user(subscription_store, monkeypatch):
    monkeypatch.setattr(entitlements, "BILLING_ENABLED", True)
    monkeypatch.setattr(entitlements, "PRICING_STATUS", "active")

    snapshot = entitlements.get_entitlement_snapshot("owner-2", hub="biashara")

    assert snapshot["subscription_state"] == "active_verified_subscription"
    assert len(snapshot["active_subscriptions"]) == 1
    assert snapshot["active_subscriptions"][0]["subscription_id"] == "64b000000000000000000305"


def test_unknown_hub_and_missing_user_are_rejected():
    with pytest.raises(APIError) as no_user:
        entitlements.get_entitlement_snapshot("")
    assert no_user.value.code == "authentication_required"

    with pytest.raises(APIError) as bad_hub:
        entitlements.get_entitlement_snapshot("owner-1", hub="not-a-hub")
    assert bad_hub.value.code == "unsupported_revenue_stream"
