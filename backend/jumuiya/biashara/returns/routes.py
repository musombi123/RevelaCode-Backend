"""Authenticated Biashara returns and refund-review APIs."""
from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import created, ok
from backend.jumuiya.biashara.tenancy.service import require_business_permission
from backend.jumuiya.biashara.returns import service


biashara_returns_bp = Blueprint("jumuiya_biashara_returns", __name__)


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    return data


@biashara_returns_bp.get("")
@require_authenticated
@require_business_permission("orders.view")
def get_returns():
    rows = service.list_returns(
        current_user_id(),
        status=request.args.get("status"),
        order_id=request.args.get("order_id"),
        limit=request.args.get("limit", 50),
    )
    return ok(rows, "Biashara return requests loaded.", meta={"count": len(rows)})


@biashara_returns_bp.post("/orders/<order_id>")
@require_authenticated
@require_business_permission("orders.manage")
def post_return(order_id):
    key = request.headers.get("Idempotency-Key", "").strip()
    result = service.create_return(current_user_id(), order_id, _body(), key)
    return created(
        result,
        "Return request saved and eligible quantities reserved against the completed order. No refund has been issued.",
    )


@biashara_returns_bp.get("/<return_id>")
@require_authenticated
@require_business_permission("orders.view")
def get_return(return_id):
    result = service.get_return(current_user_id(), return_id)
    return ok(result, "Biashara return request loaded.")


@biashara_returns_bp.post("/<return_id>/decision")
@require_authenticated
@require_business_permission("orders.manage")
def decide_return(return_id):
    payload = _body()
    result = service.resolve_return(
        current_user_id(),
        return_id,
        payload.get("decision"),
        payload.get("note", ""),
    )
    if result.get("status") == "completed" and result.get("restock_status") == "restocked":
        message = "Return approved and stock was restocked through idempotent inventory movements. No refund was issued."
    elif result.get("status") == "completed":
        message = "Return approved. Stock restocking was not requested. No refund was issued."
    else:
        message = "Return decision saved."
    return ok(result, message)


@biashara_returns_bp.post("/<return_id>/refund-review")
@require_authenticated
@require_business_permission("finance.manage")
def post_refund_review(return_id):
    key = request.headers.get("Idempotency-Key", "").strip()
    result = service.request_refund_review(
        current_user_id(),
        return_id,
        _body(),
        key,
    )
    return created(
        result,
        "Refund review request recorded. This does not move money, issue a credit note, or confirm a provider refund.",
    )
