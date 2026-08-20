# backend/jumuiya/wallet/routes.py

from __future__ import annotations

from flask import Blueprint

from backend.jumuiya.core.permissions import (
    require_authenticated,
    current_user_id,
)
from backend.jumuiya.core.responses import ok
from backend.jumuiya.wallet import services


# =========================================================
# BLUEPRINT
# =========================================================

wallet_bp = Blueprint(
    "jumuiya_wallet",
    __name__,
)


# =========================================================
# WALLET LEDGER
# =========================================================

@wallet_bp.get("/ledger")
@require_authenticated
def get_ledger():
    """
    Return the authenticated user's wallet balance
    and transaction history.
    """

    return ok(
        services.ledger(
            current_user_id()
        )
    )