
"""Secure transaction-intent ledger for the Jumuiya OS Revenue Engine.

This module records pending payment intents only. It does not charge
customers, confirm payments, credit wallets, or settle seller balances.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from threading import Lock

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.audit import log_action, now_utc
from backend.jumuiya.core.database import collection
from backend.revenue.constants import (
    CURRENCY_DEFAULT,
    MAX_IDEMPOTENCY_KEY_LENGTH,
    SUPPORTED_REVENUE_STREAMS,
)
from backend.revenue.money import MoneyValidationError, to_money
from backend.revenue.plans import get_plan


COLLECTION_NAME = "jumuiya_revenue_transactions"

_INDEX_LOCK = Lock()
_INDEXES_READY = False


class RevenueIntentError(ValueError):
    """A validated and safe error for a transaction-intent request."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "invalid_revenue_intent",
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


def _ensure_indexes():
    """Create the ledger indexes once per running application process.

    The unique user/idempotency index protects against duplicate intents,
    including concurrent requests reaching different application workers.
    """

    global _INDEXES_READY

    if _INDEXES_READY:
        return

    with _INDEX_LOCK:
        if _INDEXES_READY:
            return

        transactions = collection(COLLECTION_NAME)

        transactions.create_index(
            [
                ("user_id", ASCENDING),
                ("idempotency_key", ASCENDING),
            ],
            unique=True,
            name="ix_revenue_user_idempotency_unique",
        )

        transactions.create_index(
            [
                ("user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],
            name="ix_revenue_user_created",
        )

        _INDEXES_READY = True


def _validate_idempotency_key(value):
    """Validate a caller-supplied key used to safely retry a request."""

    if not isinstance(value, str):
        raise RevenueIntentError(
            "The Idempotency-Key header is required."
        )

    key = value.strip()

    if not key:
        raise RevenueIntentError(
            "The Idempotency-Key header is required."
        )

    if len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise RevenueIntentError(
            "The Idempotency-Key exceeds the maximum allowed length."
        )

    if any(ord(character) < 33 or ord(character) == 127 for character in key):
        raise RevenueIntentError(
            "The Idempotency-Key contains invalid characters."
        )

    return key


def _normalize_payload(payload):
    """Validate an intent, using server-managed pricing when plan_code is supplied."""

    if not isinstance(payload, dict):
        raise RevenueIntentError("A JSON object is required.")

    allowed_fields = {"stream", "amount", "currency", "description", "plan_code"}
    unexpected = set(payload) - allowed_fields
    if unexpected:
        raise RevenueIntentError(
            "Unsupported intent fields: " + ", ".join(sorted(unexpected))
        )

    # Subscription/upgrade interest must use the price currently stored in the
    # platform-admin-managed catalogue. Never trust a browser-supplied amount.
    if "plan_code" in payload:
        if set(payload) - {"plan_code", "stream", "description"}:
            raise RevenueIntentError(
                "Plan intents accept only plan_code, stream, and description. The plan price is server-managed."
            )

        code_value = payload.get("plan_code")
        if not isinstance(code_value, str) or not code_value.strip():
            raise RevenueIntentError("A valid plan_code is required.")
        plan_code = code_value.strip().lower()
        if len(plan_code) > 60:
            raise RevenueIntentError("Plan code cannot exceed 60 characters.")

        plan = get_plan(plan_code)
        if not plan:
            raise RevenueIntentError("The requested plan does not exist.", 404, "plan_not_found")
        if str(plan.get("status", "proposed")).strip().lower() == "retired":
            raise RevenueIntentError("The requested plan has been retired.", 409, "plan_retired")

        plan_hub = str(plan.get("hub", "")).strip().lower()
        requested_stream = payload.get("stream")
        if requested_stream is None or requested_stream == "":
            requested_stream = plan_hub
        if not isinstance(requested_stream, str):
            raise RevenueIntentError("A valid revenue stream is required.")
        stream = requested_stream.strip().lower()
        if stream not in SUPPORTED_REVENUE_STREAMS:
            raise RevenueIntentError("Unsupported revenue stream.")
        if plan_hub != "all" and plan_hub != stream:
            raise RevenueIntentError("The selected plan does not belong to this revenue stream.", 400, "plan_stream_mismatch")

        try:
            amount = to_money(plan.get("amount"), allow_zero=False)
        except MoneyValidationError as exc:
            raise RevenueIntentError(
                "This plan has no positive price configured for an intent request."
            ) from None

        currency_value = str(plan.get("currency", CURRENCY_DEFAULT)).strip().upper()
        if currency_value != CURRENCY_DEFAULT:
            raise RevenueIntentError(f"Only {CURRENCY_DEFAULT} is currently supported.")

        description_value = payload.get("description", "")
        if description_value is None:
            description_value = ""
        if not isinstance(description_value, str):
            raise RevenueIntentError("Description must be text.")
        description = description_value.strip() or f"Plan interest: {plan_code}"
        if len(description) > 240:
            raise RevenueIntentError("Description cannot exceed 240 characters.")
        if any(ord(character) < 32 or ord(character) == 127 for character in description):
            raise RevenueIntentError("Description contains invalid control characters.")

        return {
            "plan_code": plan_code,
            "stream": stream,
            "amount": f"{amount:.2f}",
            "currency": currency_value,
            "description": description,
        }

    # Compatibility path for non-plan intents. These are still unverified
    # intents only; the values are not payment evidence or recognized revenue.
    stream_value = payload.get("stream")
    if not isinstance(stream_value, str):
        raise RevenueIntentError("A valid revenue stream is required.")
    stream = stream_value.strip().lower()
    if stream not in SUPPORTED_REVENUE_STREAMS:
        raise RevenueIntentError("Unsupported revenue stream.")

    try:
        amount = to_money(payload.get("amount"), allow_zero=False)
    except MoneyValidationError as exc:
        raise RevenueIntentError(str(exc)) from None

    currency_value = payload.get("currency", CURRENCY_DEFAULT)
    if not isinstance(currency_value, str):
        raise RevenueIntentError("A valid currency is required.")
    currency = currency_value.strip().upper()
    if currency != CURRENCY_DEFAULT:
        raise RevenueIntentError(f"Only {CURRENCY_DEFAULT} is currently supported.")

    description_value = payload.get("description", "")
    if description_value is None:
        description_value = ""
    if not isinstance(description_value, str):
        raise RevenueIntentError("Description must be text.")
    description = description_value.strip()
    if len(description) > 240:
        raise RevenueIntentError("Description cannot exceed 240 characters.")
    if any(ord(character) < 32 or ord(character) == 127 for character in description):
        raise RevenueIntentError("Description contains invalid control characters.")

    return {
        "stream": stream,
        "amount": f"{amount:.2f}",
        "currency": currency,
        "description": description,
    }

def _fingerprint(normalized_payload):
    """Produce a deterministic fingerprint for idempotency comparison."""

    canonical = json.dumps(
        normalized_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _serialize_datetime(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    return value


def serialize_intent(document):
    """Return public fields only; never expose idempotency keys or fingerprints."""

    return {
        "id": str(document.get("_id", "")),
        "stream": document.get("stream"),
        "plan_code": document.get("plan_code"),
        "amount": document.get("amount"),
        "currency": document.get("currency", CURRENCY_DEFAULT),
        "description": document.get("description", ""),
        "status": document.get("status", "pending"),
        "billing_enabled": bool(document.get("billing_enabled", False)),
        "charge_attempted": bool(document.get("charge_attempted", False)),
        "payment_confirmed": bool(document.get("payment_confirmed", False)),
        "payment_provider": document.get("payment_provider"),
        "provider_transaction_id": document.get("provider_transaction_id"),
        "receipt": document.get("receipt"),
        "paid_at": _serialize_datetime(document.get("paid_at")),
        "created_at": _serialize_datetime(document.get("created_at")),
        "updated_at": _serialize_datetime(document.get("updated_at")),
    }


def create_intent(user_id, payload, idempotency_key):
    """Create a pending intent, safely supporting retries.

    The authenticated user ID is supplied by the server-side permissions
    layer. It is never accepted from the request body.

    Reusing the same idempotency key and payload returns the original intent.
    Reusing the key with a different payload returns HTTP 409.
    """

    if not isinstance(user_id, str) or not user_id.strip():
        raise RevenueIntentError(
            "An authenticated user ID is required.",
            401,
            "authentication_required",
        )

    user_id = user_id.strip()
    key = _validate_idempotency_key(idempotency_key)
    normalized = _normalize_payload(payload)
    fingerprint = _fingerprint(normalized)

    _ensure_indexes()

    transactions = collection(COLLECTION_NAME)

    existing = transactions.find_one({
        "user_id": user_id,
        "idempotency_key": key,
    })

    if existing:
        if existing.get("request_fingerprint") != fingerprint:
            raise RevenueIntentError(
                "This Idempotency-Key was already used with a different request.",
                409,
                "idempotency_conflict",
            )

        return {
            "transaction": serialize_intent(existing),
            "replayed": True,
        }

    timestamp = now_utc()

    document = {
        "user_id": user_id,
        **normalized,
        "idempotency_key": key,
        "request_fingerprint": fingerprint,
        "status": "pending",
        "billing_enabled": False,
        "charge_attempted": False,
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    try:
        result = transactions.insert_one(document)
        document["_id"] = result.inserted_id

    except DuplicateKeyError:
        # Another concurrent request may have created this intent first.
        existing = transactions.find_one({
            "user_id": user_id,
            "idempotency_key": key,
        })

        if not existing:
            raise RevenueIntentError(
                "The request could not be safely completed. Please retry.",
                409,
                "idempotency_conflict",
            ) from None

        if existing.get("request_fingerprint") != fingerprint:
            raise RevenueIntentError(
                "This Idempotency-Key was already used with a different request.",
                409,
                "idempotency_conflict",
            ) from None

        return {
            "transaction": serialize_intent(existing),
            "replayed": True,
        }

    log_action(
        user_id=user_id,
        action="revenue.transaction.intent_created",
        resource="revenue_transaction",
        resource_id=str(document["_id"]),
        metadata={
            "stream": normalized["stream"],
            "amount": normalized["amount"],
            "currency": normalized["currency"],
            "status": "pending",
        },
    )

    return {
        "transaction": serialize_intent(document),
        "replayed": False,
    }


def list_user_intents(user_id, *, page=1, per_page=20):
    """Return only the authenticated user's transaction intents."""

    if not isinstance(user_id, str) or not user_id.strip():
        raise RevenueIntentError(
            "An authenticated user ID is required.",
            401,
            "authentication_required",
        )

    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise RevenueIntentError(
            "Page must be a positive integer."
        )

    if (
        isinstance(per_page, bool)
        or not isinstance(per_page, int)
        or not 1 <= per_page <= 100
    ):
        raise RevenueIntentError(
            "per_page must be between 1 and 100."
        )

    _ensure_indexes()

    transactions = collection(COLLECTION_NAME)
    query = {"user_id": user_id.strip()}

    total = transactions.count_documents(query)

    cursor = (
        transactions.find(query)
        .sort("created_at", DESCENDING)
        .skip((page - 1) * per_page)
        .limit(per_page)
    )

    items = [serialize_intent(document) for document in cursor]

    return {
        "items": items,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
        "billing_enabled": False,
    }