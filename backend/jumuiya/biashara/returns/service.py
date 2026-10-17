"""Idempotent returns, stock-restock and refund-review workflows.

A return approval never moves money. Refund review records an operational request
only; a real provider-confirmed refund, credit note and formal tax treatment require
separate verified integrations and are not inferred here.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.biashara import services as commerce_services
from backend.jumuiya.biashara.tenancy.service import require_permission
from backend.jumuiya.biashara.sync.outbox import (
    build_outbox_manifest,
    dispatch_manifest_for_record,
)


logger = logging.getLogger("jumuiya.biashara.returns")
RETURNS_COLLECTION = "jumuiya_returns"
ORDERS_COLLECTION = "jumuiya_orders"
PRODUCTS_COLLECTION = "jumuiya_products"
_MOVEMENT_TOLERANCE = Decimal("0.0000001")
_MAX_LIST_LIMIT = 100


def now_utc():
    return datetime.now(timezone.utc)


def _clean_id(value):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return value


def _serialize(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {
            ("id" if key == "_id" else key): _serialize(item)
            for key, item in value.items()
            if key not in {"request_fingerprint", "outbox_event_manifest", "outbox_enqueued_event_keys"}
        }
    return value


def _fingerprint(payload):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _business(user_id, permission, business_id=None):
    context = commerce_services._require_business_with_permission(user_id, permission, business_id)
    actual_id = str(context.get("id") or context.get("_id") or "")
    if not actual_id:
        raise APIError("Business profile has no usable ID.", 409, "business_id_missing")
    return context, actual_id


def _dispatch(source_collection, business_id, document_id):
    try:
        dispatch_manifest_for_record(source_collection, str(business_id), document_id)
    except Exception as error:
        logger.warning(
            "Biashara return event dispatch deferred (source=%s, error=%s)",
            source_collection,
            type(error).__name__,
        )


def _map_quantity(document, field):
    raw = document.get(field) or {}
    if not isinstance(raw, dict):
        raise APIError("Order return counters are inconsistent. Reconcile the order before continuing.", 409, "return_counter_invalid")
    normalized = {}
    for key, value in raw.items():
        try:
            number = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise APIError("Order return counters are inconsistent.", 409, "return_counter_invalid")
        if not number.is_finite() or number < 0:
            raise APIError("Order return counters are inconsistent.", 409, "return_counter_invalid")
        normalized[str(key)] = number
    return normalized


def _order_lines(order):
    """Aggregate sold units and original price snapshots per product."""
    quantities = {}
    unit_prices = {}
    names = {}
    for item in order.get("items", []) or []:
        product_id = str(item.get("product_id") or "").strip()
        try:
            quantity = Decimal(str(item.get("quantity")))
            unit_price_minor = int(item.get("unit_price_minor"))
        except (InvalidOperation, TypeError, ValueError):
            raise APIError("The original order lacks valid product/price snapshots.", 409, "order_snapshot_invalid")
        if (
            not product_id
            or not quantity.is_finite()
            or quantity <= 0
            or unit_price_minor < 0
        ):
            raise APIError("The original order contains an invalid line item.", 409, "order_snapshot_invalid")
        quantities[product_id] = quantities.get(product_id, Decimal("0")) + quantity
        unit_prices[product_id] = unit_prices.get(product_id, Decimal("0")) + (Decimal(unit_price_minor) * quantity)
        names[product_id] = str(item.get("name") or "Product")[:160]
    return quantities, unit_prices, names


def _normalize_return_items(order, payload_items):
    if not isinstance(payload_items, list) or not payload_items:
        raise APIError("A return must contain at least one item.", 422, "invalid_return_items")
    sold, price_totals, names = _order_lines(order)
    requested = {}
    normalized = []
    for index, item in enumerate(payload_items):
        if not isinstance(item, dict):
            raise APIError(f"Return item {index + 1} must be an object.", 422, "invalid_return_items")
        product_id = str(item.get("product_id") or "").strip()
        try:
            quantity = Decimal(str(item.get("quantity")))
        except (InvalidOperation, TypeError, ValueError):
            raise APIError("Return quantities must be valid numbers.", 422, "invalid_return_quantity")
        if not product_id or not quantity.is_finite() or quantity <= 0:
            raise APIError("Return quantities must be positive finite numbers.", 422, "invalid_return_quantity")
        if product_id not in sold:
            raise APIError("A returned product is not part of the original order.", 422, "return_item_not_in_order")
        requested[product_id] = requested.get(product_id, Decimal("0")) + quantity

    merchandise_value_minor = 0
    for product_id, quantity in requested.items():
        sold_qty = sold[product_id]
        if quantity > sold_qty:
            raise APIError("Return quantity exceeds the quantity sold.", 422, "return_quantity_exceeds_sold")
        price_per_unit = price_totals[product_id] / sold_qty
        line_value = int((price_per_unit * quantity).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        merchandise_value_minor += line_value
        normalized.append({
            "product_id": product_id,
            "product_name": names[product_id],
            "quantity": float(quantity),
            "unit_price_snapshot_minor": int(price_per_unit.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "estimated_merchandise_value_minor": line_value,
        })
    normalized.sort(key=lambda row: row["product_id"])
    return normalized, requested, merchandise_value_minor


def _marker_for(order, return_id):
    for marker in order.get("active_return_reservations") or []:
        if str(marker.get("return_id")) == str(return_id):
            return marker
    return None


def _change_order_return_reservation(return_doc, action):
    """CAS the order's return counters; retries recover a crash between two documents."""
    business_id = str(return_doc["business_id"])
    order_id = str(return_doc["order_id"])
    return_id = str(return_doc["id"])
    requested = {
        str(item["product_id"]): Decimal(str(item["quantity"]))
        for item in return_doc.get("items", [])
    }
    orders = collection(ORDERS_COLLECTION)

    for _attempt in range(20):
        order = orders.find_one({
            "_id": _clean_id(order_id),
            "business_id": business_id,
        })
        if not order:
            raise APIError("Original order not found for this business.", 404, "order_not_found")
        if order.get("status") != "completed":
            raise APIError("Only completed orders can be returned.", 409, "order_not_returnable")

        active_marker = _marker_for(order, return_id)
        accepted_ids = {str(value) for value in order.get("accepted_return_ids") or []}
        rejected_ids = {str(value) for value in order.get("rejected_return_ids") or []}
        if action == "approve" and return_id in accepted_ids:
            return order
        if action == "reject" and return_id in rejected_ids:
            return order
        if action == "approve" and not active_marker:
            raise APIError("Return reservation is missing from the original order.", 409, "return_reservation_missing")
        if action == "reject" and not active_marker:
            # The request may have been rejected after the order mutation but
            # before the return document state was updated.
            if return_id in rejected_ids:
                return order
            raise APIError("Return reservation is missing from the original order.", 409, "return_reservation_missing")

        sold, _, _ = _order_lines(order)
        reserved = _map_quantity(order, "return_reserved_quantities")
        returned = _map_quantity(order, "returned_quantities")
        next_reserved = dict(reserved)
        next_returned = dict(returned)
        for product_id, quantity in requested.items():
            reserved_now = reserved.get(product_id, Decimal("0"))
            if reserved_now + _MOVEMENT_TOLERANCE < quantity:
                raise APIError("Reserved return quantities do not reconcile. Review the order before continuing.", 409, "return_counter_conflict")
            next_reserved[product_id] = max(reserved_now - quantity, Decimal("0"))
            if action == "approve":
                completed_qty = returned.get(product_id, Decimal("0")) + quantity
                if completed_qty > sold.get(product_id, Decimal("0")) + _MOVEMENT_TOLERANCE:
                    raise APIError("Accepted return quantities exceed the original sale.", 409, "return_quantity_exceeds_sold")
                next_returned[product_id] = completed_qty

        # Avoid a race where another return request changes the aggregate between
        # our read and write. The revision also works when old records omit it.
        revision = int(order.get("return_reservation_revision", 0) or 0)
        query = {
            "_id": order["_id"],
            "business_id": business_id,
            "status": "completed",
            "return_reservation_revision": revision,
        }
        if "return_reservation_revision" not in order:
            query["return_reservation_revision"] = {"$exists": False}
        update = {
            "$set": {
                "return_reserved_quantities": {key: float(value) for key, value in next_reserved.items()},
                "returned_quantities": {key: float(value) for key, value in next_returned.items()},
                "return_reservation_revision": revision + 1,
                "updated_at": now_utc(),
            },
            "$pull": {"active_return_reservations": {"return_id": return_id}},
        }
        if action == "approve":
            update["$addToSet"] = {"accepted_return_ids": return_id}
        else:
            update["$addToSet"] = {"rejected_return_ids": return_id}
        result = orders.update_one(query, update)
        if result.matched_count:
            updated = orders.find_one({"_id": order["_id"], "business_id": business_id})
            if updated:
                return updated

    raise APIError("The original order changed repeatedly. Retry this return action.", 409, "return_order_concurrency")


def _reserve_return_in_order(return_doc):
    """Reserve quantities against the original completed sale using compare-and-set."""
    business_id = str(return_doc["business_id"])
    order_id = str(return_doc["order_id"])
    return_id = str(return_doc["id"])
    requested = {
        str(item["product_id"]): Decimal(str(item["quantity"]))
        for item in return_doc.get("items", [])
    }
    orders = collection(ORDERS_COLLECTION)

    for _attempt in range(20):
        order = orders.find_one({"_id": _clean_id(order_id), "business_id": business_id})
        if not order:
            raise APIError("Original order not found for this business.", 404, "order_not_found")
        if order.get("status") != "completed":
            raise APIError("Only completed orders can be returned.", 409, "order_not_returnable")
        if _marker_for(order, return_id):
            return order
        if return_id in {str(value) for value in order.get("accepted_return_ids") or []}:
            return order

        sold, _, _ = _order_lines(order)
        reserved = _map_quantity(order, "return_reserved_quantities")
        returned = _map_quantity(order, "returned_quantities")
        next_reserved = dict(reserved)
        for product_id, quantity in requested.items():
            available = sold.get(product_id, Decimal("0")) - reserved.get(product_id, Decimal("0")) - returned.get(product_id, Decimal("0"))
            if quantity > available + _MOVEMENT_TOLERANCE:
                raise APIError(
                    "This return exceeds the remaining quantity after other requested and completed returns.",
                    409,
                    "return_quantity_unavailable",
                )
            next_reserved[product_id] = reserved.get(product_id, Decimal("0")) + quantity

        revision = int(order.get("return_reservation_revision", 0) or 0)
        query = {
            "_id": order["_id"],
            "business_id": business_id,
            "status": "completed",
            "return_reservation_revision": revision,
        }
        if "return_reservation_revision" not in order:
            query["return_reservation_revision"] = {"$exists": False}
        marker = {
            "return_id": return_id,
            "quantities": {key: float(value) for key, value in requested.items()},
            "reserved_at": now_utc(),
        }
        result = orders.update_one(query, {
            "$set": {
                "return_reserved_quantities": {key: float(value) for key, value in next_reserved.items()},
                "return_reservation_revision": revision + 1,
                "updated_at": now_utc(),
            },
            "$addToSet": {"active_return_reservations": marker},
        })
        if result.matched_count:
            return orders.find_one({"_id": order["_id"], "business_id": business_id}) or order

    raise APIError("The original order changed repeatedly. Retry this return request.", 409, "return_order_concurrency")


def _return_event(return_doc, event_suffix, event_type, status, user_id):
    now = now_utc()
    return build_outbox_manifest(
        event_key=f"return:{return_doc['id']}:{event_suffix}",
        event_type=event_type,
        entity_type="return",
        entity_id=return_doc["id"],
        payload={
            "status": status,
            "order_id": str(return_doc["order_id"]),
            "return_id": str(return_doc["id"]),
            "amount_minor": int(return_doc.get("estimated_merchandise_value_minor", 0) or 0),
            "currency": str(return_doc.get("currency") or "KES").upper(),
            "refund_status": str(return_doc.get("refund_status") or "not_requested"),
        },
        actor_user_id=user_id,
        occurred_at=now,
    )


def _finalize_requested(return_doc, user_id):
    returns = collection(RETURNS_COLLECTION)
    event = _return_event(return_doc, "requested", "return.requested", "requested", user_id)
    now = now_utc()
    updated = returns.find_one_and_update(
        {
            "_id": _clean_id(return_doc["id"]),
            "business_id": return_doc["business_id"],
            "status": {"$in": ["reservation_pending", "requested"]},
        },
        {
            "$set": {
                "status": "requested",
                "reservation_status": "reserved",
                "updated_at": now,
            },
            "$addToSet": {"outbox_event_manifest": event},
        },
    )
    updated = updated or returns.find_one({
        "_id": _clean_id(return_doc["id"]),
        "business_id": return_doc["business_id"],
    }) or return_doc
    if updated.get("status") == "requested":
        _dispatch(RETURNS_COLLECTION, return_doc["business_id"], updated["_id"])
    return _serialize(updated)


def create_return(user_id, order_id, payload, idempotency_key):
    """Create a return request and reserve eligible quantities exactly once."""
    _business_data, business_id = _business(user_id, "orders.manage")
    key = str(idempotency_key or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", key):
        raise APIError("Idempotency-Key must be 8–128 safe characters.", 422, "invalid_idempotency_key")
    if not isinstance(payload, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")

    orders = collection(ORDERS_COLLECTION)
    order = orders.find_one({"_id": _clean_id(order_id), "business_id": business_id})
    if not order:
        raise APIError("Order not found.", 404, "order_not_found")
    if order.get("status") != "completed":
        raise APIError("Only completed orders can be returned.", 409, "order_not_returnable")

    items, requested, value_minor = _normalize_return_items(order, payload.get("items"))
    reason = str(payload.get("reason") or "").strip()[:500]
    if not reason:
        raise APIError("A return reason is required.", 422, "return_reason_required")
    restock_requested = payload.get("restock", True)
    if not isinstance(restock_requested, bool):
        raise APIError("restock must be a boolean.", 422, "invalid_return")
    stable = {
        "business_id": business_id,
        "order_id": str(order["_id"]),
        "items": [{"product_id": key, "quantity": format(value.normalize(), "f")} for key, value in sorted(requested.items())],
        "reason": reason,
        "restock": restock_requested,
    }
    fingerprint = _fingerprint(stable)
    returns = collection(RETURNS_COLLECTION)
    prior = returns.find_one({"business_id": business_id, "idempotency_key": key})
    if prior:
        if prior.get("request_fingerprint") != fingerprint:
            raise APIError("Idempotency-Key was reused for different return data.", 409, "idempotency_key_reused")
        if prior.get("status") == "reservation_pending":
            _reserve_return_in_order(prior)
            return _finalize_requested(prior, user_id)
        if prior.get("status") == "reservation_conflict":
            raise APIError("This return request could not reserve the remaining sold quantity. Review the return record.", 409, "return_quantity_unavailable")
        return _serialize(prior)

    now = now_utc()
    document = {
        "_id": ObjectId(),
        "business_id": business_id,
        "order_id": str(order["_id"]),
        "idempotency_key": key,
        "request_fingerprint": fingerprint,
        "items": items,
        "reason": reason,
        "restock_requested": restock_requested,
        "status": "reservation_pending",
        "reservation_status": "pending",
        "restock_status": "pending" if restock_requested else "not_requested",
        "refund_status": "not_requested",
        "refund_request": None,
        "estimated_merchandise_value_minor": value_minor,
        "currency": str(order.get("currency") or _business_data.get("currency") or "KES").upper(),
        "refund_value_basis": "proportional original order item price snapshots; excludes separately calculated tax/fees; informational only",
        "requested_by_user_id": str(user_id),
        "created_at": now,
        "updated_at": now,
        "outbox_event_manifest": [],
        "outbox_enqueued_event_keys": [],
    }
    try:
        returns.insert_one(document)
    except DuplicateKeyError:
        prior = returns.find_one({"business_id": business_id, "idempotency_key": key})
        if prior and prior.get("request_fingerprint") == fingerprint:
            if prior.get("status") == "reservation_pending":
                _reserve_return_in_order(prior)
                return _finalize_requested(prior, user_id)
            return _serialize(prior)
        raise APIError("Idempotency-Key was reused for different return data.", 409, "idempotency_key_reused")

    document["id"] = str(document["_id"])
    try:
        _reserve_return_in_order(document)
    except APIError as error:
        returns.update_one(
            {"_id": document["_id"], "business_id": business_id, "status": "reservation_pending"},
            {"$set": {
                "status": "reservation_conflict",
                "reservation_status": "conflict",
                "reservation_error_code": error.code,
                "updated_at": now_utc(),
            }},
        )
        raise

    result = _finalize_requested(document, user_id)
    log_action(user_id, "biashara.return_requested", "return", document["_id"], {
        "order_id": str(order["_id"]),
        "item_count": len(items),
        "restock_requested": restock_requested,
        "estimated_merchandise_value_minor": value_minor,
    })
    return result


def _finish_return_state(return_doc, status, user_id, note=""):
    returns = collection(RETURNS_COLLECTION)
    suffix = "approved" if status == "approved" else "rejected"
    event = _return_event(return_doc, suffix, "return." + status, status, user_id)
    now = now_utc()
    update = {
        "$set": {
            "status": status,
            "decision": status,
            "decision_note": str(note or "").strip()[:500],
            "decision_by_user_id": str(user_id),
            "decision_at": now,
            "updated_at": now,
        },
        "$addToSet": {"outbox_event_manifest": event},
    }
    updated = returns.find_one_and_update(
        {"_id": _clean_id(return_doc["id"]), "business_id": return_doc["business_id"], "status": "requested"},
        update,
    )
    if not updated:
        updated = returns.find_one({
            "_id": _clean_id(return_doc["id"]),
            "business_id": return_doc["business_id"],
        }) or return_doc
    _dispatch(RETURNS_COLLECTION, return_doc["business_id"], updated["_id"])
    return updated


def _apply_restock(return_doc, user_id):
    if not return_doc.get("restock_requested"):
        return {"status": "not_requested", "movements": []}
    require_permission(user_id, "inventory.manage", business_id=str(return_doc["business_id"]))
    movements = []
    return_id = str(return_doc["id"])
    for item in return_doc.get("items", []):
        product_id = str(item["product_id"])
        key = f"return:{return_id}:restock:{product_id}"
        result = commerce_services.inventory_adjustment(
            user_id,
            product_id,
            {
                "movement_type": "add",
                "quantity": item["quantity"],
                "reason": "customer_return_restock",
                "idempotency_key": key,
            },
        )
        movement = result.get("movement")
        movements.append({
            "product_id": product_id,
            "movement_id": str((movement or {}).get("id") or ""),
            "idempotency_key": key,
        })
    return {"status": "restocked", "movements": movements}


def resolve_return(user_id, return_id, decision, note=""):
    """Approve/reject a return; approval uses reservation counters and idempotent stock restock."""
    _business_data, business_id = _business(user_id, "orders.manage")
    decision = str(decision or "").strip().lower()
    if decision not in {"approve", "reject"}:
        raise APIError("decision must be approve or reject.", 422, "invalid_return_decision")
    if not isinstance(note, str):
        raise APIError("decision note must be text.", 422, "invalid_return_decision")
    returns = collection(RETURNS_COLLECTION)
    return_doc = returns.find_one({"_id": _clean_id(return_id), "business_id": business_id})
    if not return_doc:
        raise APIError("Return request not found.", 404, "return_not_found")
    return_doc["id"] = str(return_doc.get("_id") or return_id)

    if decision == "reject":
        if return_doc.get("status") == "rejected":
            return _serialize(return_doc)
        if return_doc.get("status") != "requested":
            raise APIError("Only a requested return can be rejected.", 409, "invalid_return_transition")
        _change_order_return_reservation(return_doc, "reject")
        updated = _finish_return_state(return_doc, "rejected", user_id, note)
        log_action(user_id, "biashara.return_rejected", "return", return_doc["_id"], {"order_id": return_doc["order_id"]})
        return _serialize(updated)

    if return_doc.get("status") in {"rejected", "reservation_conflict"}:
        raise APIError("This return cannot be approved from its current state.", 409, "invalid_return_transition")
    if return_doc.get("status") == "requested":
        _change_order_return_reservation(return_doc, "approve")
        return_doc = _finish_return_state(return_doc, "approved", user_id, note)
    elif return_doc.get("status") not in {"approved", "completed"}:
        raise APIError("Only a requested or interrupted approved return can be approved.", 409, "invalid_return_transition")

    return_doc["id"] = str(return_doc.get("_id") or return_id)
    if return_doc.get("status") == "completed":
        return _serialize(return_doc)

    stock_result = _apply_restock(return_doc, user_id)
    now = now_utc()
    event = _return_event(return_doc, "completed", "return.completed", "completed", user_id)
    updated = returns.find_one_and_update(
        {"_id": _clean_id(return_id), "business_id": business_id, "status": "approved"},
        {"$set": {
            "status": "completed",
            "restock_status": stock_result["status"],
            "restock_movements": stock_result["movements"],
            "completed_at": now,
            "updated_at": now,
        }, "$addToSet": {"outbox_event_manifest": event}},
    )
    updated = updated or returns.find_one({"_id": _clean_id(return_id), "business_id": business_id}) or return_doc
    _dispatch(RETURNS_COLLECTION, business_id, updated["_id"])
    log_action(user_id, "biashara.return_approved", "return", updated["_id"], {
        "restock_status": updated.get("restock_status"),
        "restock_movement_count": len(updated.get("restock_movements") or []),
    })
    return _serialize(updated)


def request_refund_review(user_id, return_id, payload, idempotency_key):
    """Record a refund review request without claiming money moved or a refund was issued."""
    _business_data, business_id = _business(user_id, "finance.manage")
    key = str(idempotency_key or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", key):
        raise APIError("Idempotency-Key must be 8–128 safe characters.", 422, "invalid_idempotency_key")
    if not isinstance(payload, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")

    returns = collection(RETURNS_COLLECTION)
    current = returns.find_one({"_id": _clean_id(return_id), "business_id": business_id})
    if not current:
        raise APIError("Return request not found.", 404, "return_not_found")
    current["id"] = str(current.get("_id") or return_id)
    if current.get("status") != "completed":
        raise APIError("Refund review can be requested only after a return has been approved and completed.", 409, "return_not_completed")

    amount_minor = int(current.get("estimated_merchandise_value_minor", 0) or 0)
    if amount_minor <= 0:
        raise APIError("This return has no positive merchandise value to review.", 409, "refund_value_not_positive")
    reason = str(payload.get("reason") or "").strip()[:500]
    if not reason:
        raise APIError("A refund review reason is required.", 422, "refund_reason_required")
    fingerprint = _fingerprint({
        "return_id": str(return_id),
        "amount_minor": amount_minor,
        "currency": str(current.get("currency") or "KES"),
        "reason": reason,
    })
    existing_request = current.get("refund_request") or {}
    if current.get("refund_status") != "not_requested":
        if (
            existing_request.get("idempotency_key") == key
            and existing_request.get("request_fingerprint") == fingerprint
        ):
            return _serialize(current)
        raise APIError("A refund request already exists for this return.", 409, "refund_request_exists")

    now = now_utc()
    event = _return_event(current, "refund-requested", "return.refund_requested", "completed", user_id)
    request_document = {
        "idempotency_key": key,
        "request_fingerprint": fingerprint,
        "amount_minor": amount_minor,
        "currency": str(current.get("currency") or "KES").upper(),
        "reason": reason,
        "status": "requested_manual_review",
        "money_moved": False,
        "provider_refund_reference": None,
        "recorded_by_user_id": str(user_id),
        "created_at": now,
        "updated_at": now,
    }
    updated = returns.find_one_and_update(
        {
            "_id": current["_id"],
            "business_id": business_id,
            "status": "completed",
            "refund_status": "not_requested",
        },
        {
            "$set": {
                "refund_status": "requested_manual_review",
                "refund_request": request_document,
                "updated_at": now,
            },
            "$addToSet": {"outbox_event_manifest": event},
        },
    )
    if not updated:
        latest = returns.find_one({"_id": current["_id"], "business_id": business_id})
        prior = (latest or {}).get("refund_request") or {}
        if prior.get("idempotency_key") == key and prior.get("request_fingerprint") == fingerprint:
            return _serialize(latest)
        raise APIError("Return changed while requesting refund review. Reload and retry.", 409, "refund_request_conflict")
    _dispatch(RETURNS_COLLECTION, business_id, current["_id"])
    log_action(user_id, "biashara.refund_review_requested", "return", current["_id"], {
        "amount_minor": amount_minor,
        "currency": current.get("currency", "KES"),
        "money_moved": False,
    })
    return _serialize(updated)


def get_return(user_id, return_id):
    _business_data, business_id = _business(user_id, "orders.view")
    document = collection(RETURNS_COLLECTION).find_one({
        "_id": _clean_id(return_id),
        "business_id": business_id,
    })
    if not document:
        raise APIError("Return request not found.", 404, "return_not_found")
    return _serialize(document)


def list_returns(user_id, status=None, order_id=None, limit=50):
    _business_data, business_id = _business(user_id, "orders.view")
    try:
        limit = min(max(int(limit), 1), _MAX_LIST_LIMIT)
    except (TypeError, ValueError):
        limit = 50
    query = {"business_id": business_id}
    if status:
        state = str(status).strip().lower()
        if state not in {"reservation_pending", "requested", "reservation_conflict", "approved", "rejected", "completed"}:
            raise APIError("Unknown return status.", 422, "invalid_return_status")
        query["status"] = state
    if order_id:
        query["order_id"] = str(order_id)
    rows = collection(RETURNS_COLLECTION).find(query).sort("created_at", -1).limit(limit)
    return [_serialize(row) for row in rows]
