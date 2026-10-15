"""Validation for Biashara commercial invoice and payment requests."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation


PAYMENT_METHODS = {"cash", "mpesa", "mobile_money", "bank", "card", "other"}


def _object(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")


def _text(data, key, required=False, max_len=200):
    value = data.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{key} is required.")
    if len(value) > max_len:
        raise ValueError(f"{key} must not exceed {max_len} characters.")
    if "<" in value or ">" in value:
        raise ValueError(f"{key} must be plain text.")
    return value


def invoice_payload(data):
    _object(data)
    order_id = _text(data, "order_id", required=True, max_len=128)
    due_date = _text(data, "due_date", max_len=10)
    if due_date:
        try:
            date.fromisoformat(due_date)
        except ValueError:
            raise ValueError("due_date must use YYYY-MM-DD.")
    return {
        "order_id": order_id,
        "due_date": due_date or None,
        "notes": _text(data, "notes", max_len=1000),
    }


def payment_payload(data):
    _object(data)
    try:
        amount = Decimal(str(data.get("amount")))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("amount must be a valid monetary amount.")
    if not amount.is_finite() or amount <= 0:
        raise ValueError("amount must be greater than zero.")
    amount = amount.quantize(Decimal("0.01"))
    method = _text(data, "payment_method", required=True, max_len=32).lower()
    if method not in PAYMENT_METHODS:
        raise ValueError("payment_method must be one of: " + ", ".join(sorted(PAYMENT_METHODS)) + ".")
    reference = _text(data, "reference", max_len=160)
    return {
        "amount": str(amount),
        "payment_method": method,
        "reference": reference,
    }


def mpesa_stk_payload(data):
    _object(data)
    phone_number = _text(data, "phone_number", required=True, max_len=40)
    connection_id = _text(data, "connection_id", required=True, max_len=128)
    try:
        amount = Decimal(str(data.get("amount")))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("amount must be a valid monetary amount.")
    if not amount.is_finite() or amount <= 0:
        raise ValueError("amount must be greater than zero.")
    if amount.quantize(Decimal("0.01")) != amount:
        raise ValueError("amount supports at most two decimal places.")
    return {
        "phone_number": phone_number,
        "connection_id": connection_id,
        "amount": str(amount),
    }

