
"""Initial public endpoints for the Jumuiya OS Revenue Engine."""

from flask import jsonify, request

from backend.revenue import revenue_bp
from backend.revenue.constants import SUPPORTED_REVENUE_STREAMS
from backend.revenue.money import (
    MoneyValidationError,
    calculate_percentage_fee,
)
from backend.revenue.plans import PRICING_STATUS, list_plans


@revenue_bp.get("/health")
def revenue_health():
    return jsonify({
        "success": True,
        "service": "jumuiya-revenue",
        "status": "operational",
        "billing_enabled": False,
    }), 200


@revenue_bp.get("/plans")
def revenue_list_plans():
    hub = request.args.get("hub", "").strip().lower()

    if hub and hub not in SUPPORTED_REVENUE_STREAMS:
        return jsonify({
            "success": False,
            "error": "Unsupported hub or revenue stream.",
        }), 400

    return jsonify({
        "success": True,
        "pricing_status": PRICING_STATUS,
        "billing_enabled": False,
        "plans": list_plans(hub=hub or None),
    }), 200


@revenue_bp.post("/fees/preview")
def revenue_preview_fee():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({
            "success": False,
            "error": "A JSON request body is required.",
        }), 400

    try:
        result = calculate_percentage_fee(
            payload.get("amount"),
            payload.get("percentage"),
        )
    except MoneyValidationError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 400

    return jsonify({
        "success": True,
        "preview_only": True,
        "fee": result,
    }), 200