# backend/jumuiya/wallet/services.py

from __future__ import annotations

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.wallet.models import transaction_document


# =========================================================
# SERIALIZATION
# =========================================================

def _ser(doc):
    """
    Convert a MongoDB transaction into a JSON-safe object.
    """

    if not doc:
        return None

    out = dict(doc)

    if "_id" in out:
        out["id"] = str(
            out.pop("_id")
        )

    for key, value in list(
        out.items()
    ):
        if hasattr(
            value,
            "isoformat",
        ):
            out[key] = value.isoformat()

    return out


# =========================================================
# LEDGER
# =========================================================

def ledger(user_id):
    """
    Return the user's wallet ledger and calculated balance.

    The transaction ledger remains the source of truth.
    """

    if user_id is None:
        raise APIError(
            "User ID is required.",
            401,
            "invalid_identity",
        )

    user_id = str(
        user_id
    )

    docs = list(
        collection(
            "jumuiya_transactions"
        )
        .find({
            "user_id": user_id
        })
        .sort(
            "created_at",
            -1,
        )
    )

    balance = 0.0
    currencies = set()
    transactions = []

    for document in docs:

        amount = float(
            document.get(
                "amount",
                0,
            )
        )

        direction = document.get(
            "direction"
        )

        currency = str(
            document.get(
                "currency",
                "KES",
            )
        ).upper()

        currencies.add(
            currency
        )

        if direction == "credit":
            balance += amount

        elif direction == "debit":
            balance -= amount

        transactions.append(
            _ser(document)
        )

    # Jumuiya currently operates primarily in KES.
    # If multiple currencies are introduced later,
    # balances must be calculated separately.
    if len(currencies) > 1:
        raise APIError(
            "Multiple currencies detected. "
            "Currency-specific balances are required.",
            409,
            "multiple_currencies",
        )

    currency = (
        next(iter(currencies))
        if currencies
        else "KES"
    )

    return {
        "balance": round(
            balance,
            2,
        ),

        "currency": currency,

        "transactions": transactions,
    }


# =========================================================
# RECORD TRANSACTION
# =========================================================

def record_transaction(
    user_id,
    data,
):
    """
    Record a wallet transaction.

    NOTE:
    This function records a verified/internal transaction.
    It should NOT be exposed as an unrestricted endpoint
    where clients can manufacture credits.
    """

    if user_id is None:
        raise APIError(
            "User ID is required.",
            401,
            "invalid_identity",
        )

    if not isinstance(
        data,
        dict,
    ):
        raise APIError(
            "Transaction data must be a JSON object.",
            400,
            "invalid_transaction_data",
        )

    # -----------------------------------------------------
    # Amount
    # -----------------------------------------------------

    try:

        amount = float(
            data.get(
                "amount"
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        raise APIError(
            "amount must be a number.",
            422,
            "validation_error",
        )

    if amount <= 0:

        raise APIError(
            "amount must be greater than zero.",
            422,
            "validation_error",
        )

    # -----------------------------------------------------
    # Direction
    # -----------------------------------------------------

    direction = str(
        data.get(
            "direction",
            "",
        )
    ).strip().lower()

    if direction not in {
        "credit",
        "debit",
    }:

        raise APIError(
            "direction must be credit or debit.",
            422,
            "validation_error",
        )

    # -----------------------------------------------------
    # Transaction type
    # -----------------------------------------------------

    transaction_type = str(
        data.get(
            "type",
            "",
        )
    ).strip()

    if not transaction_type:

        raise APIError(
            "Transaction type is required.",
            422,
            "validation_error",
        )

    # -----------------------------------------------------
    # Currency
    # -----------------------------------------------------

    currency = str(
        data.get(
            "currency",
            "KES",
        )
        or "KES"
    ).strip().upper()

    if len(currency) != 3:

        raise APIError(
            "currency must be a 3-letter currency code.",
            422,
            "validation_error",
        )

    # -----------------------------------------------------
    # Create document
    # -----------------------------------------------------

    payload = {
        **data,
        "amount": amount,
        "direction": direction,
        "type": transaction_type,
        "currency": currency,
    }

    document = transaction_document(
        user_id,
        payload,
    )

    result = collection(
        "jumuiya_transactions"
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    log_action(
        user_id,
        "wallet.transaction.recorded",
        "transaction",
        result.inserted_id,
        metadata={
            "type": transaction_type,
            "direction": direction,
            "amount": amount,
            "currency": currency,
        },
    )

    return _ser(
        document
    )