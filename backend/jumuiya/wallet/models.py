# backend/jumuiya/wallet/models.py

from __future__ import annotations

from datetime import datetime, timezone


# =========================================================
# TIME
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


# =========================================================
# TRANSACTION DOCUMENT
# =========================================================

def transaction_document(user_id, data):
    """
    Create a Jumuiya wallet transaction.

    IMPORTANT:
    This represents a transaction record.

    It does NOT itself move money.

    Actual M-Pesa / bank / payment-provider operations
    must be handled by dedicated payment services.
    """

    if user_id is None:
        raise ValueError(
            "user_id is required."
        )

    if not isinstance(data, dict):
        raise ValueError(
            "Transaction data must be a dictionary."
        )

    transaction_type = str(
        data.get("type", "")
    ).strip()

    direction = str(
        data.get("direction", "")
    ).strip().lower()

    if not transaction_type:
        raise ValueError(
            "Transaction type is required."
        )

    if direction not in {
        "credit",
        "debit",
    }:
        raise ValueError(
            "Transaction direction must be credit or debit."
        )

    try:
        amount = float(
            data.get("amount")
        )
    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "Transaction amount must be a number."
        )

    if amount <= 0:
        raise ValueError(
            "Transaction amount must be greater than zero."
        )

    currency = str(
        data.get(
            "currency",
            "KES",
        )
        or "KES"
    ).strip().upper()

    if len(currency) != 3:
        raise ValueError(
            "Currency must be a valid 3-letter code."
        )

    return {
        "user_id": str(user_id),

        "type": transaction_type,

        "direction": direction,

        "amount": amount,

        "currency": currency,

        "reference": str(
            data.get(
                "reference",
                "",
            )
            or ""
        ).strip(),

        "description": str(
            data.get(
                "description",
                "",
            )
            or ""
        ).strip(),

        # Transaction records created internally can
        # receive a status from the wallet service.
        "status": str(
            data.get(
                "status",
                "completed",
            )
            or "completed"
        ).strip().lower(),

        "created_at": now_utc(),
    }