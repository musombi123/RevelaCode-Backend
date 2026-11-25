import hashlib
import hmac

import pytest

from backend.identity_methods import (
    _active,
    _normalise_phone,
    _otp_hash,
    _phone_hash,
    _verified,
)


def test_kenyan_mobile_number_is_normalised_to_e164():
    assert _normalise_phone("0712 345 678") == "+254712345678"
    assert _normalise_phone("0112-345-678") == "+254112345678"
    assert _normalise_phone("254712345678") == "+254712345678"
    assert _normalise_phone("+254 712 345 678") == "+254712345678"


@pytest.mark.parametrize("value", ["", "071234567", "12345", "abc", "+00012345678"])
def test_invalid_phone_numbers_are_rejected(value):
    with pytest.raises(ValueError):
        _normalise_phone(value)


def test_otp_hash_is_bound_to_challenge_phone_and_code(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-only-secret")
    first = _otp_hash("challenge-a", "+254712345678", "123456")
    assert first == _otp_hash("challenge-a", "+254712345678", "123456")
    assert first != _otp_hash("challenge-b", "+254712345678", "123456")
    assert first != _otp_hash("challenge-a", "+254700000000", "123456")
    assert first != _otp_hash("challenge-a", "+254712345678", "654321")


def test_phone_hash_is_stable_and_keyed(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-only-secret")
    first = _phone_hash("+254712345678")
    assert first == _phone_hash("+254712345678")
    monkeypatch.setenv("JWT_SECRET", "rotated-secret")
    assert first != _phone_hash("+254712345678")


@pytest.mark.parametrize("user", [
    {"verified": True},
    {"is_verified": True},
    {"verified": "true"},
    {"verified": 1},
])
def test_verified_account_state_is_recognised(user):
    assert _verified(user) is True


def test_inactive_accounts_are_rejected():
    assert _active({"status": "active"}) is True
    assert _active({"status": "suspended"}) is False
    assert _active({"is_active": False}) is False
