from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest
from bson import ObjectId
from flask import Flask

from backend.revenue import subscriptions
from backend.revenue import mpesa
from backend.revenue import trials
from backend.revenue import admin_routes


def _trial_row(ends_at, started_at=None):
    return {
        "user_id": "user-1",
        "hub": "smart_ai",
        "started_at": started_at or datetime(2026, 10, 1, tzinfo=timezone.utc),
        "ends_at": ends_at,
        "trial_days": 30,
    }


@pytest.fixture
def revenue_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


def test_essential_entitlement_remains_free_without_trial_or_subscription(monkeypatch):
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    monkeypatch.setattr(subscriptions, "now_utc", lambda: now)
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: None)
    monkeypatch.setattr(subscriptions, "collection", lambda name: Mock(find_one=lambda query: None))

    result = subscriptions.resolve_entitlement("user-1", "smart_ai", "essential")

    assert result["allowed"] is True
    assert result["tier"] == "free"
    assert result["premium_access"] is False


def test_premium_entitlement_allows_active_hub_trial(monkeypatch):
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    trial = _trial_row(now + timedelta(days=8), now - timedelta(days=22))
    monkeypatch.setattr(subscriptions, "now_utc", lambda: now)
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: None)
    monkeypatch.setattr(subscriptions, "collection", lambda name: Mock(find_one=lambda query: trial))

    result = subscriptions.resolve_entitlement("user-1", "smart_ai", "image_generation")

    assert result["allowed"] is True
    assert result["tier"] == "trial"
    assert result["trial_status"] == "active"


def test_premium_entitlement_denies_expired_trial(monkeypatch):
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    trial = _trial_row(now - timedelta(seconds=1), now - timedelta(days=31))
    monkeypatch.setattr(subscriptions, "now_utc", lambda: now)
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: None)
    monkeypatch.setattr(subscriptions, "collection", lambda name: Mock(find_one=lambda query: trial))

    result = subscriptions.resolve_entitlement("user-1", "smart_ai", "document_analysis")

    assert result["allowed"] is False
    assert result["tier"] == "free"
    assert result["trial_status"] == "expired"


def test_premium_entitlement_allows_active_paid_subscription(monkeypatch):
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    subscription = {
        "_id": "sub-1",
        "user_id": "user-1",
        "hub": "smart_ai",
        "plan_code": "ai_plus",
        "status": "active",
        "starts_at": now - timedelta(days=1),
        "ends_at": now + timedelta(days=29),
    }
    monkeypatch.setattr(subscriptions, "now_utc", lambda: now)
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: subscription)
    monkeypatch.setattr(subscriptions, "collection", lambda name: Mock(find_one=lambda query: None))

    result = subscriptions.resolve_entitlement("user-1", "smart_ai", "image_generation")

    assert result["allowed"] is True
    assert result["tier"] == "paid"
    assert result["subscription"]["plan_code"] == "ai_plus"


def test_faith_plus_unlocks_courses_workspace_and_companion_but_not_group_tools(monkeypatch):
    now = datetime(2026, 10, 23, tzinfo=timezone.utc)
    subscription = {
        "_id": "faith-plus-1",
        "user_id": "user-1",
        "hub": "faith",
        "plan_code": "faith_plus",
        "status": "active",
        "starts_at": now - timedelta(days=1),
        "ends_at": now + timedelta(days=29),
    }
    monkeypatch.setattr(subscriptions, "now_utc", lambda: now)
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: subscription)
    monkeypatch.setattr(subscriptions, "collection", lambda name: Mock(find_one=lambda query: None))

    assert subscriptions.resolve_entitlement("user-1", "faith", "faith_courses")["allowed"] is True
    assert subscriptions.resolve_entitlement("user-1", "faith", "faith_workspace")["allowed"] is True
    assert subscriptions.resolve_entitlement("user-1", "faith", "faith_companion")["allowed"] is True
    group_entitlement = subscriptions.resolve_entitlement("user-1", "faith", "faith_group_tools")
    assert group_entitlement["allowed"] is False
    assert group_entitlement["reason"] == "plan_upgrade_required"


def test_faith_pro_unlocks_group_tools(monkeypatch):
    now = datetime(2026, 10, 23, tzinfo=timezone.utc)
    subscription = {
        "_id": "faith-pro-1",
        "user_id": "user-1",
        "hub": "faith",
        "plan_code": "faith_pro",
        "status": "active",
        "starts_at": now - timedelta(days=1),
        "ends_at": now + timedelta(days=29),
    }
    monkeypatch.setattr(subscriptions, "now_utc", lambda: now)
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: subscription)
    monkeypatch.setattr(subscriptions, "collection", lambda name: Mock(find_one=lambda query: None))

    result = subscriptions.resolve_entitlement("user-1", "faith", "faith_group_tools")
    assert result["allowed"] is True
    assert result["tier"] == "paid"


def test_faith_trial_unlocks_group_tools_for_its_full_duration(monkeypatch):
    now = datetime(2026, 10, 23, tzinfo=timezone.utc)
    trial = {
        "user_id": "user-1",
        "hub": "faith",
        "status": "active",
        "started_at": now - timedelta(days=1),
        "ends_at": now + timedelta(days=29),
        "trial_days": 30,
    }
    monkeypatch.setattr(subscriptions, "now_utc", lambda: now)
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: None)
    monkeypatch.setattr(subscriptions, "collection", lambda name: Mock(find_one=lambda query: trial))

    result = subscriptions.resolve_entitlement("user-1", "faith", "faith_group_tools")
    assert result["allowed"] is True
    assert result["tier"] == "trial"
    assert result["trial_status"] == "active"


def test_proposed_plan_cannot_activate_paid_subscription(monkeypatch, revenue_app):
    monkeypatch.setattr(subscriptions, "get_plan", lambda plan_code: {
        "code": "ai_plus", "hub": "smart_ai", "status": "proposed",
        "interval": "month", "amount": "199.00", "currency": "KES",
    })
    with revenue_app.app_context():
        response, status = subscriptions.activate_verified_payment({
            "provider": "mpesa",
            "provider_transaction_id": "ws_CO_test123456",
            "user_id": "user-1",
            "plan_code": "ai_plus",
            "amount": "199.00",
            "currency": "KES",
            "receipt": "test-receipt",
            "metadata": {},
        })

    assert status == 409
    assert response.get_json()["code"] == "plan_not_purchasable"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0712345678", "254712345678"),
        ("254712345678", "254712345678"),
        ("+254 712 345 678", "254712345678"),
        ("0112345678", "254112345678"),
    ],
)
def test_mpesa_phone_normalization(raw, expected):
    assert mpesa._phone(raw) == expected


@pytest.mark.parametrize("raw", ["123", "not-a-number", "254012345678", "072345678901"])
def test_mpesa_phone_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        mpesa._phone(raw)


def test_mpesa_query_must_have_final_success_result_before_activation(monkeypatch):
    rows = Mock()
    monkeypatch.setattr(mpesa, "_checkout_rows", lambda: rows)
    checkout = {"_id": "checkout-row", "checkout_request_id": "ws_CO_test123456", "merchant_request_id": "merchant-1"}

    assert mpesa._apply_final_result(checkout, {
        "CheckoutRequestID": "ws_CO_test123456",
        "MerchantRequestID": "merchant-1",
        "ResponseCode": "0",
        "ResponseDescription": "The service request is accepted successfully",
    }) is False
    rows.update_one.assert_called_once()
    assert rows.update_one.call_args.args[1]["$set"]["status"] == "awaiting_verification"


def test_mpesa_query_rejects_checkout_id_mismatch(monkeypatch):
    rows = Mock()
    monkeypatch.setattr(mpesa, "_checkout_rows", lambda: rows)
    checkout = {"_id": "checkout-row", "checkout_request_id": "ws_CO_expected", "merchant_request_id": "merchant-1"}

    assert mpesa._apply_final_result(checkout, {
        "CheckoutRequestID": "ws_CO_other",
        "ResultCode": "0",
    }) is False
    rows.update_one.assert_not_called()


def test_mpesa_query_rejects_merchant_id_mismatch(monkeypatch):
    rows = Mock()
    monkeypatch.setattr(mpesa, "_checkout_rows", lambda: rows)
    checkout = {"_id": "checkout-row", "checkout_request_id": "ws_CO_expected", "merchant_request_id": "merchant-1"}

    assert mpesa._apply_final_result(checkout, {
        "CheckoutRequestID": "ws_CO_expected",
        "MerchantRequestID": "merchant-wrong",
        "ResultCode": "0",
    }) is False
    rows.update_one.assert_not_called()


def test_confirmed_provider_payment_is_recorded_once_in_existing_ledger(monkeypatch, revenue_app):
    from types import SimpleNamespace

    rows = []

    class FakeTransactions:
        def find_one(self, query):
            return next((row for row in rows if all(row.get(k) == v for k, v in query.items())), None)

        def insert_one(self, document):
            saved = dict(document)
            saved["_id"] = "paid-ledger-id"
            rows.append(saved)
            return SimpleNamespace(inserted_id="paid-ledger-id")

    transactions = FakeTransactions()
    monkeypatch.setattr(subscriptions, "_ensure_revenue_ledger_indexes", lambda: None)
    monkeypatch.setattr(subscriptions, "collection", lambda name: transactions)
    monkeypatch.setattr(subscriptions, "log_action", lambda *args, **kwargs: None)

    event = {
        "provider": "mpesa",
        "provider_transaction_id": "ws_CO_payment123",
        "user_id": "user-1",
        "plan_code": "ai_plus",
        "amount": "199.00",
        "currency": "KES",
        "receipt": "QAA123XYZ",
    }
    plan = {"hub": "smart_ai", "interval": "month"}
    subscription = {"_id": "subscription-id", "hub": "smart_ai"}

    with revenue_app.app_context():
        first = subscriptions._record_confirmed_revenue_transaction(event, plan, subscription)
        second = subscriptions._record_confirmed_revenue_transaction(event, plan, subscription)

    assert first["_id"] == "paid-ledger-id"
    assert second["_id"] == "paid-ledger-id"
    assert len(rows) == 1
    assert rows[0]["payment_confirmed"] is True
    assert rows[0]["status"] == "succeeded"
    assert rows[0]["payment_provider"] == "mpesa"
    assert rows[0]["provider_transaction_id"] == "ws_CO_payment123"
    assert rows[0]["amount"] == "199.00"
    assert rows[0]["receipt"] == "QAA123XYZ"



def test_sandbox_configuration_never_enables_live_checkout(monkeypatch):
    monkeypatch.setattr(mpesa, "checkout_is_configured", lambda: True)
    monkeypatch.setattr(mpesa, "_environment", lambda: "sandbox")
    monkeypatch.delenv("REVENUE_PAYMENT_PROVIDERS", raising=False)
    assert mpesa.checkout_is_production_configured() is False

    monkeypatch.setattr(mpesa, "_environment", lambda: "production")
    assert mpesa.checkout_is_production_configured() is False

    monkeypatch.setenv("REVENUE_PAYMENT_PROVIDERS", "mpesa")
    assert mpesa.checkout_is_production_configured() is True

    monkeypatch.setenv("REVENUE_PAYMENT_PROVIDERS", "stripe")
    assert mpesa.checkout_is_production_configured() is False


def test_sandbox_success_query_cannot_activate_subscription_or_revenue(monkeypatch):
    rows = Mock()
    monkeypatch.setattr(mpesa, "_checkout_rows", lambda: rows)
    monkeypatch.setattr(mpesa, "_environment", lambda: "sandbox")
    monkeypatch.setattr(
        mpesa,
        "activate_verified_payment",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("sandbox result must never call subscription activation")
        ),
    )
    checkout = {
        "_id": "checkout-row",
        "checkout_request_id": "ws_CO_sandbox123",
        "merchant_request_id": "merchant-1",
    }

    result = mpesa._apply_final_result(checkout, {
        "CheckoutRequestID": "ws_CO_sandbox123",
        "MerchantRequestID": "merchant-1",
        "ResultCode": "0",
        "ResultDesc": "The service request is processed successfully.",
    })

    assert result is False
    rows.update_one.assert_called_once()
    saved = rows.update_one.call_args.args[1]["$set"]
    assert saved["status"] == "sandbox_verified"
    assert "No subscription or revenue" in saved["result_description"]


def test_success_callback_metadata_must_match_checkout_amount_phone_and_receipt():
    checkout = {
        "amount": "199.00",
        "phone": "254712345678",
    }
    receipt = mpesa._validated_callback_receipt(checkout, {
        "Amount": 199,
        "PhoneNumber": 254712345678,
        "MpesaReceiptNumber": "QWERTY1234",
    })
    assert receipt == "QWERTY1234"

    with pytest.raises(ValueError):
        mpesa._validated_callback_receipt(checkout, {
            "Amount": 198,
            "PhoneNumber": 254712345678,
            "MpesaReceiptNumber": "QWERTY1234",
        })

    with pytest.raises(ValueError):
        mpesa._validated_callback_receipt(checkout, {
            "Amount": 199,
            "PhoneNumber": 254700000000,
            "MpesaReceiptNumber": "QWERTY1234",
        })

    with pytest.raises(ValueError):
        mpesa._validated_callback_receipt(checkout, {
            "Amount": 199,
            "PhoneNumber": 254712345678,
            "MpesaReceiptNumber": "",
        })


def test_provider_query_must_explicitly_correlate_checkout_and_merchant_ids(monkeypatch):
    rows = Mock()
    monkeypatch.setattr(mpesa, "_checkout_rows", lambda: rows)
    monkeypatch.setattr(mpesa, "_environment", lambda: "production")
    monkeypatch.setattr(
        mpesa,
        "activate_verified_payment",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unmatched provider query must never activate")
        ),
    )
    checkout = {
        "_id": "checkout-row",
        "checkout_request_id": "ws_CO_expected",
        "merchant_request_id": "merchant-expected",
        "user_id": "user-1",
        "plan_code": "ai_plus",
        "amount": "199.00",
        "currency": "KES",
    }

    assert mpesa._apply_final_result(checkout, {
        "ResultCode": "0",
        "MerchantRequestID": "merchant-expected",
    }) is False

    rows.update_one.reset_mock()
    assert mpesa._apply_final_result(checkout, {
        "CheckoutRequestID": "ws_CO_expected",
        "ResultCode": "0",
    }) is False

    rows.update_one.reset_mock()
    assert mpesa._apply_final_result(checkout, {
        "CheckoutRequestID": "ws_CO_expected",
        "MerchantRequestID": "merchant-wrong",
        "ResultCode": "0",
    }) is False


def test_idempotent_confirmed_payment_can_be_enriched_with_late_real_receipt(monkeypatch, revenue_app):
    import hashlib
    from datetime import datetime, timezone

    provider = "mpesa"
    provider_transaction_id = "ws_CO_receipt_late"
    idempotency_key = "paid:" + hashlib.sha256(
        f"{provider}:{provider_transaction_id}".encode("utf-8")
    ).hexdigest()
    row = {
        "_id": "paid-ledger-id",
        "user_id": "user-1",
        "idempotency_key": idempotency_key,
        "payment_confirmed": True,
        "payment_provider": provider,
        "provider_transaction_id": provider_transaction_id,
        "receipt": None,
        "status": "succeeded",
        "amount": "199.00",
        "currency": "KES",
    }

    class FakeTransactions:
        def find_one(self, query):
            return row if all(row.get(key) == value for key, value in query.items()) else None

        def update_one(self, query, update):
            assert row["_id"] == query["_id"]
            row.update(update["$set"])

    transactions = FakeTransactions()
    monkeypatch.setattr(subscriptions, "_ensure_revenue_ledger_indexes", lambda: None)
    monkeypatch.setattr(subscriptions, "collection", lambda name: transactions)
    monkeypatch.setattr(subscriptions, "log_action", lambda *args, **kwargs: None)

    event = {
        "provider": provider,
        "provider_transaction_id": provider_transaction_id,
        "user_id": "user-1",
        "plan_code": "ai_plus",
        "amount": "199.00",
        "currency": "KES",
        "receipt": "QWERTY1234",
    }

    with revenue_app.app_context():
        existing = subscriptions._record_confirmed_revenue_transaction(
            event, {"hub": "smart_ai"}, {"_id": "sub-1"}
        )

    assert existing["receipt"] == "QWERTY1234"
    assert row["receipt"] == "QWERTY1234"


def test_trial_is_not_consumed_when_hub_has_active_paid_subscription(monkeypatch, revenue_app):
    paid = {
        "_id": "sub-1",
        "user_id": "user-1",
        "hub": "smart_ai",
        "status": "active",
    }
    monkeypatch.setattr(trials, "current_user_id", lambda: "user-1")
    monkeypatch.setattr(trials, "now_utc", lambda: datetime(2026, 10, 22, tzinfo=timezone.utc))
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: paid)
    trial_collection = Mock()
    monkeypatch.setattr(trials, "_trials", lambda: trial_collection)

    with revenue_app.test_request_context(
        "/api/revenue/trials/start",
        method="POST",
        json={"hub": "smart_ai"},
    ):
        response, status = trials.start_hub_trial.__wrapped__()

    assert status == 409
    assert response.get_json()["code"] == "active_subscription_exists"
    trial_collection.find_one.assert_not_called()
    trial_collection.insert_one.assert_not_called()


def test_premium_entitlement_denies_cancelled_trial_even_before_end_date(monkeypatch):
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    trial = _trial_row(now + timedelta(days=8), now - timedelta(days=22))
    trial["status"] = "cancelled"
    monkeypatch.setattr(subscriptions, "now_utc", lambda: now)
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: None)
    monkeypatch.setattr(subscriptions, "collection", lambda name: Mock(find_one=lambda query: trial))

    result = subscriptions.resolve_entitlement("user-1", "smart_ai", "document_analysis")

    assert result["allowed"] is False
    assert result["premium_access"] is False
    assert result["trial_status"] == "expired"


def test_new_trial_uses_the_persisted_hub_trial_duration_for_its_end_date(monkeypatch, revenue_app):
    now = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
    rows = Mock()
    rows.find_one.return_value = None
    rows.insert_one.return_value = Mock(inserted_id="trial-1")

    monkeypatch.setattr(trials, "current_user_id", lambda: "user-1")
    monkeypatch.setattr(trials, "now_utc", lambda: now)
    monkeypatch.setattr(trials, "_trials", lambda: rows)
    monkeypatch.setattr(trials, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mpesa,
        "_checkout_rows",
        lambda: Mock(find_one=lambda query: None),
    )

    with revenue_app.test_request_context(
        "/api/revenue/trials/start",
        method="POST",
        json={"hub": "elimu"},
    ):
        response, status = trials.start_hub_trial.__wrapped__()

    assert status == 201
    trial = response.get_json()["trial"]
    assert trial["hub"] == "elimu"
    assert trial["trial_days"] == 30
    assert trial["started_at"] == now.isoformat()
    assert trial["ends_at"] == (now + timedelta(days=30)).isoformat()
    stored = rows.insert_one.call_args.args[0]
    assert stored["ends_at"] == now + timedelta(days=30)

def test_trial_start_is_blocked_while_checkout_is_unresolved(monkeypatch, revenue_app):
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    monkeypatch.setattr(trials, "current_user_id", lambda: "user-1")
    monkeypatch.setattr(trials, "now_utc", lambda: now)
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mpesa,
        "_checkout_rows",
        lambda: Mock(find_one=lambda query: {"checkout_request_id": "ws_CO_pending"}),
    )
    trial_rows = Mock()
    monkeypatch.setattr(trials, "_trials", lambda: trial_rows)

    with revenue_app.test_request_context(
        "/api/revenue/trials/start", method="POST", json={"hub": "smart_ai"}
    ):
        response, status = trials.start_hub_trial.__wrapped__()

    assert status == 409
    assert response.get_json()["code"] == "checkout_already_pending"
    trial_rows.find_one.assert_not_called()
    trial_rows.insert_one.assert_not_called()


def test_start_checkout_returns_existing_unresolved_checkout_for_new_idempotency_key(monkeypatch, revenue_app):
    existing_checkout = {
        "_id": "checkout-row",
        "user_id": "user-1",
        "hub": "smart_ai",
        "plan_code": "ai_plus",
        "phone": "254712345678",
        "status": "pending",
        "checkout_request_id": "ws_CO_pending",
    }
    rows = Mock()
    rows.find_one.side_effect = [None, existing_checkout]
    monkeypatch.setattr(mpesa, "checkout_is_production_configured", lambda: True)
    monkeypatch.setattr(mpesa, "current_user_id", lambda: "user-1")
    monkeypatch.setattr(mpesa, "get_plan", lambda code: {
        "code": "ai_plus", "hub": "smart_ai", "status": "available",
        "interval": "month", "amount": "199.00", "currency": "KES",
    })
    monkeypatch.setattr(mpesa, "_checkout_rows", lambda: rows)
    monkeypatch.setattr(mpesa, "_phone", lambda value: "254712345678")
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: None)

    with revenue_app.test_request_context(
        "/api/revenue/checkout",
        method="POST",
        json={"plan_code": "ai_plus", "phone": "0712345678"},
        headers={"Idempotency-Key": "fresh-attempt-2"},
    ):
        response, status = mpesa.revenue_start_checkout.__wrapped__()

    assert status == 409
    assert response.get_json()["code"] == "checkout_already_pending"
    assert response.get_json()["checkout"]["checkout_request_id"] == "ws_CO_pending"
    assert rows.insert_one.call_count == 0


def test_mpesa_password_builder_is_pure_and_uses_configured_credentials(monkeypatch):
    import base64

    monkeypatch.setenv("MPESA_SHORTCODE", "123456")
    monkeypatch.setenv("MPESA_PASSKEY", "test-passkey")
    timestamp = "20261023003900"

    assert mpesa._password(timestamp) == base64.b64encode(
        f"123456test-passkey{timestamp}".encode("utf-8")
    ).decode("ascii")


def test_new_checkout_is_blocked_when_paid_subscription_is_active(monkeypatch, revenue_app):
    plan = {
        "code": "ai_plus",
        "hub": "smart_ai",
        "status": "available",
        "interval": "month",
        "amount": "199.00",
        "currency": "KES",
    }
    rows = Mock()
    rows.find_one.return_value = None
    monkeypatch.setattr(mpesa, "checkout_is_production_configured", lambda: True)
    monkeypatch.setattr(mpesa, "get_plan", lambda _code: plan)
    monkeypatch.setattr(mpesa, "_checkout_rows", lambda: rows)
    monkeypatch.setattr(mpesa, "current_user_id", lambda: "user-1")
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: {"status": "active"})
    monkeypatch.setattr(mpesa, "_access_token", lambda: (_ for _ in ()).throw(
        AssertionError("must reject before making a provider request")
    ))

    with revenue_app.test_request_context(
        "/api/revenue/checkout",
        method="POST",
        headers={"Idempotency-Key": "attempt-001"},
        json={"plan_code": "ai_plus", "phone": "0712345678"},
    ):
        response, status = mpesa.revenue_start_checkout.__wrapped__()

    assert status == 409
    assert response.get_json()["code"] == "active_subscription_exists"
    rows.insert_one.assert_not_called()


def test_unknown_stk_submission_requires_admin_provider_reconciliation_before_release(monkeypatch, revenue_app):
    from types import SimpleNamespace

    row_id = "64a1b2c3d4e5f67890123456"
    row = {
        "_id": ObjectId(row_id),
        "user_id": "user-1",
        "hub": "smart_ai",
        "status": "submission_unknown",
        "active_checkout_slot": "user-1:smart_ai",
        "created_at": datetime(2026, 10, 23, tzinfo=timezone.utc),
    }

    class FakeRows:
        def __init__(self):
            self.row = dict(row)
            self.updated = None

        def find_one(self, query):
            return self.row if query.get("_id") == self.row["_id"] else None

        def update_one(self, query, update):
            assert query["status"] == "submission_unknown"
            self.row.update(update["$set"])
            for key in update.get("$unset", {}):
                self.row.pop(key, None)
            self.updated = update
            return SimpleNamespace(modified_count=1)

    rows = FakeRows()
    monkeypatch.setattr(mpesa, "_checkout_rows", lambda: rows)
    monkeypatch.setattr(mpesa, "current_user_id", lambda: "admin-1")
    monkeypatch.setattr(mpesa, "log_action", lambda *args, **kwargs: None)

    with revenue_app.test_request_context(
        f"/api/revenue/admin/checkouts/by-id/{row_id}/resolve-no-payment",
        method="POST",
        json={
            "resolution": "provider_checked_no_charge",
            "evidence_reference": "DAR AJA REVIEW-20261023",
            "notes": "Checked the provider transaction history; no matching debit or receipt was found.",
        },
    ):
        response, status = mpesa.revenue_admin_resolve_unknown_checkout.__wrapped__.__wrapped__(row_id)

    assert status == 200
    assert response.get_json()["success"] is True
    assert rows.row["status"] == "failed"
    assert "active_checkout_slot" not in rows.row
    assert rows.row["manual_resolution"]["resolution"] == "provider_checked_no_charge"


def test_published_mpesa_subscription_must_have_whole_kes_price(monkeypatch):
    monkeypatch.setattr(mpesa, "checkout_is_production_configured", lambda: True)

    with pytest.raises(ValueError, match="whole-KES"):
        admin_routes._validate_plan_values({
            "code": "ai_plus",
            "name": "Smart AI Plus",
            "hub": "smart_ai",
            "amount": "199.50",
            "interval": "month",
            "status": "available",
            "features": [],
        }, creating=True)

    values = admin_routes._validate_plan_values({
        "code": "ai_plus",
        "name": "Smart AI Plus",
        "hub": "smart_ai",
        "amount": "199",
        "interval": "month",
        "status": "available",
        "features": [],
    }, creating=True)
    assert values["amount"] == "199.00"


def test_daraja_acceptance_without_checkout_ids_keeps_slot_locked(monkeypatch, revenue_app):
    from types import SimpleNamespace

    class FakeRows:
        def __init__(self):
            self.row = None

        def find_one(self, query, sort=None):
            if self.row is None:
                return None
            if all(self.row.get(key) == value for key, value in query.items()):
                return self.row
            return None

        def insert_one(self, document):
            self.row = dict(document)
            self.row["_id"] = "checkout-row"
            return SimpleNamespace(inserted_id="checkout-row")

        def update_one(self, query, update):
            if self.row is None or self.row.get("_id") != query.get("_id"):
                return SimpleNamespace(modified_count=0)
            self.row.update(update.get("$set", {}))
            for key in update.get("$unset", {}):
                self.row.pop(key, None)
            return SimpleNamespace(modified_count=1)

    rows = FakeRows()
    plan = {
        "code": "ai_plus",
        "hub": "smart_ai",
        "status": "available",
        "interval": "month",
        "amount": "199.00",
        "currency": "KES",
    }
    monkeypatch.setattr(mpesa, "checkout_is_production_configured", lambda: True)
    monkeypatch.setattr(mpesa, "get_plan", lambda _code: plan)
    monkeypatch.setattr(mpesa, "_checkout_rows", lambda: rows)
    monkeypatch.setattr(mpesa, "current_user_id", lambda: "user-1")
    monkeypatch.setattr(mpesa, "_access_token", lambda: "test-access-token")
    monkeypatch.setattr(mpesa, "_daraja_post", lambda *args, **kwargs: {
        "ResponseCode": "0",
        "ResponseDescription": "The service request is accepted successfully",
        # Intentionally omit CheckoutRequestID and MerchantRequestID.
    })
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: None)

    with revenue_app.test_request_context(
        "/api/revenue/checkout",
        method="POST",
        headers={"Idempotency-Key": "accepted-missing-ids-001"},
        json={"plan_code": "ai_plus", "phone": "0712345678"},
    ):
        response, status = mpesa.revenue_start_checkout.__wrapped__()

    assert status == 503
    assert response.get_json()["code"] == "mpesa_checkout_reference_missing"
    assert rows.row["status"] == "submission_unknown"
    assert rows.row["active_checkout_slot"] == "user-1:smart_ai"


def test_recent_initiating_checkout_cannot_be_manually_released(monkeypatch, revenue_app):
    from types import SimpleNamespace

    row_id = ObjectId("64a1b2c3d4e5f67890123456")
    row = {
        "_id": row_id,
        "user_id": "user-1",
        "hub": "smart_ai",
        "status": "initiating",
        "active_checkout_slot": "user-1:smart_ai",
        "updated_at": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
    }

    class FakeRows:
        def find_one(self, query):
            return row if query.get("_id") == row_id else None

        def update_one(self, query, update):
            row.update(update.get("$set", {}))
            for key in update.get("$unset", {}):
                row.pop(key, None)
            return SimpleNamespace(modified_count=1)

    rows = FakeRows()
    monkeypatch.setattr(mpesa, "_checkout_rows", lambda: rows)
    monkeypatch.setattr(mpesa, "current_user_id", lambda: "admin-1")

    with revenue_app.test_request_context(
        f"/api/revenue/admin/checkouts/by-id/{row_id}/resolve-no-payment",
        method="POST",
        json={
            "resolution": "provider_checked_no_charge",
            "evidence_reference": "DAR AJA REVIEW-20261023",
            "notes": "Checked provider transaction history and confirmed no matching debit.",
        },
    ):
        response, status = mpesa.revenue_admin_resolve_unknown_checkout.__wrapped__.__wrapped__(row_id)

    assert status == 409
    assert response.get_json()["code"] == "checkout_initiation_still_fresh"
    assert row["status"] == "initiating"
    assert row["active_checkout_slot"] == "user-1:smart_ai"

@pytest.mark.parametrize("checkout_ready", [True, False])
def test_public_plan_catalog_reports_real_production_checkout_readiness(
    monkeypatch, revenue_app, checkout_ready
):
    from backend.revenue import routes

    monkeypatch.setattr(
        mpesa, "checkout_is_production_configured", lambda: checkout_ready
    )
    monkeypatch.setattr(routes, "get_pricing_status", lambda: "draft")
    monkeypatch.setattr(
        routes,
        "list_plans",
        lambda hub=None: [
            {
                "code": "free",
                "hub": "all",
                "amount": "0.00",
                "currency": "KES",
                "interval": "month",
                "status": "available",
            }
        ],
    )

    with revenue_app.test_request_context("/api/revenue/plans"):
        response, status = routes.revenue_list_plans()

    assert status == 200
    payload = response.get_json()
    assert payload["checkout_enabled"] is checkout_ready
    assert payload["billing_enabled"] is checkout_ready

def test_every_trial_hub_has_a_proposed_paid_subscription_plan(monkeypatch):
    from backend.revenue import plans

    monkeypatch.setattr(plans, "collection", lambda _name: Mock(find=lambda _query: []))
    catalogue = plans.list_plans()
    subscription_hubs = set(trials.TRIAL_HUBS)

    for hub in subscription_hubs:
        matching = [
            plan for plan in catalogue
            if plan.get("hub") == hub
            and plan.get("interval") in {"month", "year"}
            and Decimal(str(plan.get("amount", "0"))) > 0
        ]
        assert matching, f"{hub} has a trial but no paid subscription plan"

    matching = [
        plan for plan in catalogue
        if plan.get("hub") == "faith"
        and plan.get("interval") == "month"
        and Decimal(str(plan.get("amount", "0"))) > 0
    ]
    assert matching
    assert all(plan.get("status") == "proposed" for plan in matching)

    community_paid_plans = [
        plan for plan in catalogue
        if plan.get("hub") == "community"
        and plan.get("interval") in {"month", "year"}
        and Decimal(str(plan.get("amount", "0"))) > 0
    ]
    assert community_paid_plans == []
    assert "community" not in trials.TRIAL_HUBS

@pytest.mark.parametrize(
    ("hub", "expected_days"),
    [
        ("elimu", 30),
        ("biashara", 30),
        ("shamba", 30),
        ("smart_ai", 30),
        ("marketplace", 30),
        ("faith", 30),
    ],
)
def test_hub_trial_durations_are_configured(hub, expected_days):
    assert trials.trial_days_for_hub(hub) == expected_days


@pytest.mark.parametrize(
    ("hub", "expected_days"),
    [
        ("elimu", 30),
        ("biashara", 30),
        ("shamba", 30),
        ("smart_ai", 30),
        ("marketplace", 30),
        ("faith", 30),
    ],
)
def test_new_trial_snapshot_uses_hub_specific_duration(hub, expected_days):
    now = datetime(2026, 10, 24, tzinfo=timezone.utc)
    trial = {
        "hub": hub,
        "status": "active",
        "started_at": now - timedelta(hours=1),
        "ends_at": now + timedelta(days=expected_days) - timedelta(hours=1),
    }

    public = trials._public_trial(trial, now)

    assert public["status"] == "active"
    assert public["trial_days"] == expected_days
    assert public["access"] == "trial"


def test_legacy_paid_community_plans_are_hidden_from_public_catalogue():
    from backend.revenue import plans

    legacy_plan = {
        "code": "community_pro",
        "name": "Community Pro",
        "hub": "community",
        "amount": "299.00",
        "currency": "KES",
        "interval": "month",
        "status": "available",
        "features": ["Legacy paid membership"],
    }
    monkeypatch_rows = Mock(find=lambda _query: [legacy_plan])
    # The stale database entry remains visible to admins for clean-up, but is
    # never returned to the public subscription catalogue.
    from unittest.mock import patch
    with patch.object(plans, "collection", lambda _name: monkeypatch_rows):
        public = plans.list_plans()
        admin = plans.list_plans(include_retired=True)

    assert not any(
        item.get("hub") == "community"
        and item.get("interval") in {"month", "year"}
        and Decimal(str(item.get("amount", "0"))) > 0
        for item in public
    )
    assert any(item.get("code") == "community_pro" for item in admin)
    assert any(item.get("code") == "community_ads_campaign" for item in public)


def test_community_trial_cannot_be_started():
    with revenue_app.test_request_context(
        "/api/revenue/trials/start", method="POST", json={"hub": "community"}
    ):
        response, status = trials.start_hub_trial.__wrapped__()

    assert status == 400
    assert response.get_json()["code"] == "unsupported_hub"


def test_community_entitlements_are_permanently_free_without_subscription_or_trial(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Community must not query subscriptions or trials")

    monkeypatch.setattr(subscriptions, "_active_subscription", forbidden)
    monkeypatch.setattr(subscriptions, "collection", forbidden)

    result = subscriptions.resolve_entitlement(
        "user-1", "community", "advanced_analytics"
    )

    assert result["allowed"] is True
    assert result["tier"] == "free"
    assert result["access"] == "free"
    assert result["reason"] == "permanent_free_hub"
    assert result["premium_access"] is True
    assert result["paid_subscription"] is False
    assert result["trial_status"] == "not_required"
    assert result["trial"] is None
    assert result["subscription"] is None
    assert result["billing_enabled"] is False
    assert result["checkout_enabled"] is False


def test_community_cannot_be_created_as_a_paid_subscription_plan():
    with pytest.raises(ValueError, match="Community is permanently free"):
        admin_routes._validate_plan_values({
            "code": "community_growth",
            "name": "Community Growth",
            "hub": "community",
            "amount": "99",
            "interval": "month",
            "status": "proposed",
            "features": [],
        }, creating=True)


def test_community_public_catalog_disables_checkout_when_mpesa_is_ready(
    monkeypatch, revenue_app
):
    from backend.revenue import routes

    monkeypatch.setattr(
        mpesa, "checkout_is_production_configured", lambda: True
    )
    monkeypatch.setattr(routes, "get_pricing_status", lambda: "published")
    monkeypatch.setattr(routes, "list_plans", lambda hub=None: [
        {"code": "free", "hub": "all", "amount": "0.00", "status": "available"}
    ])

    with revenue_app.test_request_context("/api/revenue/plans?hub=community"):
        response, status = routes.revenue_list_plans()

    payload = response.get_json()
    assert status == 200
    assert payload["billing_enabled"] is True
    assert payload["checkout_enabled"] is False
    assert payload["subscription_enabled"] is False
    assert payload["hub"] == "community"


def test_community_checkout_is_blocked_even_if_a_legacy_plan_is_available(
    monkeypatch, revenue_app
):
    monkeypatch.setattr(mpesa, "checkout_is_production_configured", lambda: True)
    monkeypatch.setattr(mpesa, "current_user_id", lambda: "user-1")
    monkeypatch.setattr(mpesa, "get_plan", lambda _code: {
        "code": "community_pro",
        "hub": "community",
        "status": "available",
        "interval": "month",
        "amount": "299.00",
        "currency": "KES",
    })

    with revenue_app.test_request_context(
        "/api/revenue/checkout",
        method="POST",
        headers={"Idempotency-Key": "community-must-be-free-001"},
        json={"plan_code": "community_pro", "phone": "0712345678"},
    ):
        response, status = mpesa.revenue_start_checkout.__wrapped__()

    assert status == 409
    assert response.get_json()["code"] == "community_permanently_free"


@pytest.mark.parametrize(
    ("hub", "plan_code", "feature", "expected"),
    [
        ("biashara", "biashara_starter", "advanced_reports", True),
        ("biashara", "biashara_starter", "seller_tools", True),
        ("biashara", "biashara_starter", "advanced_analytics", False),
        ("biashara", "biashara_pro", "seller_tools", True),
        ("biashara", "biashara_pro", "advanced_analytics", True),
        ("elimu", "elimu_small", "advanced_reports", False),
        ("elimu", "elimu_standard", "advanced_reports", True),
        ("elimu", "elimu_advanced", "automation", True),
        ("shamba", "shamba_plus", "advanced_analytics", False),
        ("shamba", "shamba_pro", "advanced_analytics", True),
    ],
)

def test_paid_hub_plan_only_unlocks_included_features(
    monkeypatch, hub, plan_code, feature, expected
):
    now = datetime(2026, 10, 24, tzinfo=timezone.utc)
    paid = {
        "_id": "sub-1",
        "user_id": "user-1",
        "hub": hub,
        "plan_code": plan_code,
        "status": "active",
        "starts_at": now - timedelta(days=1),
        "ends_at": now + timedelta(days=29),
    }
    monkeypatch.setattr(subscriptions, "now_utc", lambda: now)
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: paid)
    monkeypatch.setattr(subscriptions, "collection", lambda name: Mock(find_one=lambda query: None))

    result = subscriptions.resolve_entitlement("user-1", hub, feature)

    assert result["allowed"] is expected
    assert result["tier"] == "paid"


@pytest.mark.parametrize(
    ("hub", "feature"),
    [
        ("biashara", "advanced_analytics"),
        ("elimu", "automation"),
        ("shamba", "advanced_analytics"),
    ],
)
def test_active_hub_trial_unlocks_all_hub_premium_features(monkeypatch, hub, feature):
    now = datetime(2026, 10, 24, tzinfo=timezone.utc)
    trial = {
        "user_id": "user-1",
        "hub": hub,
        "status": "active",
        "started_at": now - timedelta(days=1),
        "ends_at": now + timedelta(days=9),
        "trial_days": trials.trial_days_for_hub(hub),
    }
    monkeypatch.setattr(subscriptions, "now_utc", lambda: now)
    monkeypatch.setattr(subscriptions, "_active_subscription", lambda *args, **kwargs: None)
    monkeypatch.setattr(subscriptions, "collection", lambda name: Mock(find_one=lambda query: trial))

    result = subscriptions.resolve_entitlement("user-1", hub, feature)

    assert result["allowed"] is True
    assert result["tier"] == "trial"
