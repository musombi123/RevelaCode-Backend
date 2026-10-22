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
        response, status = mpesa.revenue_admin_resolve_unknown_checkout.__wrapped__.__wrapped__()

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
        response, status = mpesa.revenue_admin_resolve_unknown_checkout.__wrapped__.__wrapped__()

    assert status == 409
    assert response.get_json()["code"] == "checkout_initiation_still_fresh"
    assert row["status"] == "initiating"
    assert row["active_checkout_slot"] == "user-1:smart_ai"
