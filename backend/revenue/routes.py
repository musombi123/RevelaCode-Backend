
"""Public and authenticated endpoints for the Jumuiya OS Revenue Engine.

Generic transaction intents remain request records only. Subscription checkout
is available separately through the production Daraja adapter and is enabled
only when its production credentials and callback URL are configured.
"""

from flask import current_app, jsonify, request

from backend.jumuiya.core.permissions import (
    current_user_id,
    require_authenticated,
)
from backend.revenue import revenue_bp
from backend.revenue.constants import SUPPORTED_REVENUE_STREAMS
from backend.revenue.ledger import (
    RevenueIntentError,
    create_intent,
    list_user_intents,
)
from backend.revenue.money import (
    MoneyValidationError,
    calculate_percentage_fee,
)
from backend.revenue.plans import get_pricing_status, list_plans


def _error_response(message, status_code, error_code=None):
    body = {
        "success": False,
        "error": message,
    }

    if error_code:
        body["code"] = error_code

    return jsonify(body), status_code


@revenue_bp.get("/health")
def revenue_health():
    from backend.revenue.mpesa import checkout_is_production_configured

    return jsonify({
        "success": True,
        "service": "jumuiya-revenue",
        "status": "operational",
        "billing_enabled": checkout_is_production_configured(),
        "checkout_enabled": checkout_is_production_configured(),
        "payment_provider": "mpesa",
    }), 200


@revenue_bp.get("/plans")
def revenue_list_plans():
    hub = request.args.get("hub", "").strip().lower()

    if hub and hub not in SUPPORTED_REVENUE_STREAMS:
        return _error_response(
            "Unsupported hub or revenue stream.",
            400,
            "unsupported_revenue_stream",
        )

    from backend.revenue.mpesa import checkout_is_production_configured

    return jsonify({
        "success": True,
        "pricing_status": get_pricing_status(),
        "billing_enabled": False,
        "checkout_enabled": checkout_is_production_configured(),
        "plans": list_plans(hub=hub or None),
    }), 200


@revenue_bp.post("/fees/preview")
def revenue_preview_fee():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return _error_response(
            "A JSON request body is required.",
            400,
            "invalid_json_body",
        )

    try:
        result = calculate_percentage_fee(
            payload.get("amount"),
            payload.get("percentage"),
        )
    except MoneyValidationError as exc:
        return _error_response(
            str(exc),
            400,
            "invalid_fee_request",
        )

    return jsonify({
        "success": True,
        "preview_only": True,
        "billing_enabled": False,
        "fee": result,
    }), 200


@revenue_bp.post("/transactions/intents")
@require_authenticated
def revenue_create_intent():
    """Record a pending intent without initiating a payment."""

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return _error_response(
            "A JSON request body is required.",
            400,
            "invalid_json_body",
        )

    idempotency_key = request.headers.get("Idempotency-Key")

    try:
        result = create_intent(
            user_id=current_user_id(),
            payload=payload,
            idempotency_key=idempotency_key,
        )

    except RevenueIntentError as exc:
        return _error_response(
            exc.message,
            exc.status_code,
            exc.error_code,
        )

    except Exception:
        current_app.logger.exception(
            "Failed to create a Jumuiya revenue transaction intent."
        )
        return _error_response(
            "The transaction intent could not be recorded. Please retry.",
            503,
            "revenue_ledger_unavailable",
        )

    status_code = 200 if result["replayed"] else 201

    return jsonify({
        "success": True,
        "replayed": result["replayed"],
        "billing_enabled": False,
        "payment_required": False,
        "message": (
            "Existing transaction intent returned."
            if result["replayed"]
            else "Transaction intent recorded. No payment was initiated."
        ),
        "transaction": result["transaction"],
    }), status_code


@revenue_bp.get("/transactions")
@require_authenticated
def revenue_list_transactions():
    """List the authenticated user's own revenue transaction intents."""

    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))

        result = list_user_intents(
            user_id=current_user_id(),
            page=page,
            per_page=per_page,
        )

    except ValueError as exc:
        return _error_response(
            str(exc),
            400,
            "invalid_pagination",
        )

    except Exception:
        current_app.logger.exception(
            "Failed to list Jumuiya revenue transaction intents."
        )
        return _error_response(
            "Transaction history is temporarily unavailable.",
            503,
            "revenue_ledger_unavailable",
        )

    return jsonify({
        "success": True,
        **result,
    }), 200