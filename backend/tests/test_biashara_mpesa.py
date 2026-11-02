from __future__ import annotations

import pytest

from backend.jumuiya.biashara import payments
from backend.jumuiya.core.errors import APIError


def test_mpesa_phone_is_normalized_to_daraja_format():
    assert payments._phone("0712 345 678") == "254712345678"
    assert payments._phone("+254 712 345 678") == "254712345678"
    assert payments._phone("112345678") == "254112345678"


@pytest.mark.parametrize("value", ["", "071234", "254812345678", "not-a-phone"])
def test_mpesa_phone_rejects_invalid_numbers(value):
    with pytest.raises(APIError):
        payments._phone(value)


def test_biashara_callback_url_requires_exact_https_path(monkeypatch):
    monkeypatch.setenv(
        "BIASHARA_MPESA_CALLBACK_URL",
        "https://api.example.co.ke/api/jumuiya/biashara/payments/mpesa/callback",
    )
    assert payments._callback_url().startswith("https://api.example.co.ke/")

    monkeypatch.setenv(
        "BIASHARA_MPESA_CALLBACK_URL",
        "http://api.example.co.ke/api/jumuiya/biashara/payments/mpesa/callback",
    )
    assert payments._callback_url() == ""

    monkeypatch.setenv(
        "BIASHARA_MPESA_CALLBACK_URL",
        "https://api.example.co.ke/api/jumuiya/biashara/payments/mpesa/callback?debug=1",
    )
    assert payments._callback_url() == ""

    monkeypatch.setenv(
        "BIASHARA_MPESA_CALLBACK_URL",
        "https://api.example.co.ke/api/revenue/providers/mpesa/callback",
    )
    assert payments._callback_url() == ""


def test_biashara_callback_metadata_is_allowlisted():
    callback = {
        "CallbackMetadata": {
            "Item": [
                {"Name": "Amount", "Value": 1250},
                {"Name": "MpesaReceiptNumber", "Value": "QAB1234567"},
                {"Name": "PhoneNumber", "Value": 254712345678},
                {"Name": "Balance", "Value": 4000},
                {"Name": "UnknownField", "Value": "ignored"},
            ]
        }
    }

    result = payments._callback_metadata(callback)

    assert result == {
        "Amount": 1250,
        "MpesaReceiptNumber": "QAB1234567",
        "PhoneNumber": 254712345678,
    }


def test_mpesa_configuration_does_not_report_ready_without_production_secrets(monkeypatch):
    for key in (
        "BIASHARA_MPESA_CALLBACK_URL",
        "MPESA_SHORTCODE",
        "MPESA_TRANSACTION_TYPE",
        "MPESA_PARTY_B",
        "MPESA_PASSKEY",
        "MPESA_CONSUMER_KEY",
        "MPESA_CONSUMER_SECRET",
        "MPESA_STK_PATH",
        "MPESA_STK_QUERY_PATH",
        "REVENUE_PAYMENT_PROVIDERS",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setattr(payments.daraja, "_environment", lambda: "sandbox")
    monkeypatch.setattr(payments.daraja, "_base_url", lambda: "https://sandbox.safaricom.co.ke")
    monkeypatch.setattr(payments.daraja, "_endpoint_path", lambda name: "/configured")

    status = payments._configuration_status()

    assert status["ready"] is False
    assert "daraja_environment" in status["blockers"]
    assert "callback_url" in status["blockers"]
    assert status["note"].find("configuration shape only") >= 0
