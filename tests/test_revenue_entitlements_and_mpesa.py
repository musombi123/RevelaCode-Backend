from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest
from flask import Flask

from backend.revenue import subscriptions
from backend.revenue import mpesa


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
