"""Authenticated controlled stock-count API."""
from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import created, ok
from backend.jumuiya.biashara.tenancy.service import require_business_permission
from backend.jumuiya.biashara.inventory import counts


biashara_inventory_bp = Blueprint("jumuiya_biashara_inventory", __name__)


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    return data


@biashara_inventory_bp.get("/counts")
@require_authenticated
@require_business_permission("inventory.view")
def get_stock_counts():
    rows = counts.list_count_sessions(
        current_user_id(),
        status=request.args.get("status"),
        limit=request.args.get("limit", 50),
    )
    return ok(rows, "Biashara stock count sessions loaded.", meta={"count": len(rows)})


@biashara_inventory_bp.post("/counts")
@require_authenticated
@require_business_permission("inventory.manage")
def post_stock_count():
    key = request.headers.get("Idempotency-Key", "").strip()
    result = counts.create_count_session(current_user_id(), _body(), key)
    return created(
        result,
        "Stock count started from a system snapshot. No inventory quantity has been changed.",
    )


@biashara_inventory_bp.get("/counts/<session_id>")
@require_authenticated
@require_business_permission("inventory.view")
def get_stock_count(session_id):
    result = counts.get_count_session(current_user_id(), session_id)
    return ok(result, "Biashara stock count loaded.")


@biashara_inventory_bp.post("/counts/<session_id>/items/<product_id>")
@require_authenticated
@require_business_permission("inventory.manage")
def post_counted_quantity(session_id, product_id):
    payload = _body()
    if "counted_quantity" not in payload:
        raise APIError("counted_quantity is required.", 422, "invalid_stock_count_quantity")
    result = counts.record_count(
        current_user_id(),
        session_id,
        product_id,
        payload["counted_quantity"],
    )
    return ok(result, "Physical quantity recorded. Stock is not changed until finalization.")


@biashara_inventory_bp.post("/counts/<session_id>/items/<product_id>/recount")
@require_authenticated
@require_business_permission("inventory.manage")
def post_recount_item(session_id, product_id):
    result = counts.recount_item(current_user_id(), session_id, product_id)
    return ok(result, "System snapshot refreshed for this line. Record a new physical count before finalizing.")


@biashara_inventory_bp.post("/counts/<session_id>/finalize")
@require_authenticated
@require_business_permission("inventory.manage")
def post_finalize_stock_count(session_id):
    result = counts.finalize_count_session(current_user_id(), session_id)
    return ok(
        result,
        "Stock count finalized through inventory movements. Retries use the same movement keys and do not apply a variance twice.",
    )
