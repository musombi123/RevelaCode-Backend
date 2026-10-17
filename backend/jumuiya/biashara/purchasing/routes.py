"""Authenticated supplier, purchase-order and goods-receiving APIs."""
from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import created, ok
from backend.jumuiya.biashara.purchasing import service


biashara_purchasing_bp = Blueprint("jumuiya_biashara_purchasing", __name__)


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    return data


@biashara_purchasing_bp.get("/suppliers")
@require_authenticated
def get_suppliers():
    rows = service.list_suppliers(
        current_user_id(),
        search=request.args.get("search"),
        status=request.args.get("status", "active"),
        limit=request.args.get("limit", 50),
    )
    return ok(rows, "Biashara suppliers loaded.", meta={"count": len(rows)})


@biashara_purchasing_bp.post("/suppliers")
@require_authenticated
def post_supplier():
    payload = _body()
    key = request.headers.get("Idempotency-Key", "").strip()
    if key:
        payload["idempotency_key"] = key
    result = service.create_supplier(current_user_id(), payload)
    return created(result, "Supplier record created.")


@biashara_purchasing_bp.patch("/suppliers/<supplier_id>")
@require_authenticated
def patch_supplier(supplier_id):
    result = service.update_supplier(current_user_id(), supplier_id, _body())
    return ok(result, "Supplier record updated.")


@biashara_purchasing_bp.get("/purchase-orders")
@require_authenticated
def get_purchase_orders():
    rows = service.list_purchase_orders(
        current_user_id(),
        status=request.args.get("status"),
        supplier_id=request.args.get("supplier_id"),
        limit=request.args.get("limit", 50),
    )
    return ok(rows, "Biashara purchase orders loaded.", meta={"count": len(rows)})


@biashara_purchasing_bp.post("/purchase-orders")
@require_authenticated
def post_purchase_order():
    payload = _body()
    key = request.headers.get("Idempotency-Key", "").strip()
    if key:
        payload["idempotency_key"] = key
    result = service.create_purchase_order(current_user_id(), payload)
    return created(result, "Draft purchase order created. No stock was changed and no purchase order was sent to the supplier.")


@biashara_purchasing_bp.get("/purchase-orders/<purchase_order_id>")
@require_authenticated
def get_purchase_order(purchase_order_id):
    result = service.get_purchase_order(current_user_id(), purchase_order_id)
    return ok(result, "Biashara purchase order loaded.")


@biashara_purchasing_bp.patch("/purchase-orders/<purchase_order_id>/status")
@require_authenticated
def patch_purchase_order_status(purchase_order_id):
    payload = _body()
    result = service.update_purchase_order_status(
        current_user_id(),
        purchase_order_id,
        payload.get("status"),
    )
    return ok(result, "Purchase order status updated. Marking a purchase order as ordered does not send it to a supplier.")


@biashara_purchasing_bp.post("/purchase-orders/<purchase_order_id>/receipts")
@require_authenticated
def post_purchase_order_receipt(purchase_order_id):
    payload = _body()
    key = request.headers.get("Idempotency-Key", "").strip()
    result = service.receive_purchase_order_items(
        current_user_id(),
        purchase_order_id,
        payload,
        header_key=key or None,
    )
    if result.get("status") == "completed":
        message = "Goods receipt completed. Stock movements were applied idempotently."
    else:
        message = "Goods receipt is incomplete. Retry the same Idempotency-Key to repair it before starting another receipt."
    return ok(result, message)
