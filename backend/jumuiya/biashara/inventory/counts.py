"""Controlled stock-count sessions with stale-snapshot protection and recovery."""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
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


logger = logging.getLogger("jumuiya.biashara.inventory.counts")
COUNTS_COLLECTION = "jumuiya_stock_counts"
PRODUCTS_COLLECTION = "jumuiya_products"
MAX_SESSION_PRODUCTS = 200
MAX_LIST_LIMIT = 100
QUANTITY_TOLERANCE = Decimal("0.0000001")


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


def _business(user_id, permission):
    business = commerce_services._require_business_with_permission(user_id, permission)
    business_id = str(business.get("id") or business.get("_id") or "")
    if not business_id:
        raise APIError("Business profile has no usable ID.", 409, "business_id_missing")
    return business, business_id


def _decimal(value, label, allow_zero=True):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise APIError(f"{label} must be a valid number.", 422, "invalid_stock_count_quantity")
    if not result.is_finite() or result < 0 or (not allow_zero and result == 0):
        raise APIError(f"{label} must be a non-negative finite number.", 422, "invalid_stock_count_quantity")
    return result


def _dispatch_count(document):
    try:
        dispatch_manifest_for_record(COUNTS_COLLECTION, str(document["business_id"]), document["_id"])
    except Exception as error:
        logger.warning("Biashara stock count event dispatch deferred (%s).", type(error).__name__)


def _event(document, suffix, event_type, status, actor_user_id):
    return build_outbox_manifest(
        event_key=f"stock-count:{document['id']}:{suffix}",
        event_type=event_type,
        entity_type="stock_count",
        entity_id=document["id"],
        payload={
            "status": status,
            "stock_count_id": document["id"],
            "line_count": len(document.get("items") or []),
            "currency": str(document.get("currency") or "KES").upper(),
        },
        actor_user_id=actor_user_id,
        occurred_at=now_utc(),
    )


def _session(business_id, session_id):
    document = collection(COUNTS_COLLECTION).find_one({
        "_id": _clean_id(session_id),
        "business_id": str(business_id),
    })
    if not document:
        raise APIError("Stock count session not found.", 404, "stock_count_not_found")
    document["id"] = str(document.get("_id") or session_id)
    return document


def _mutate_session(business_id, session_id, mutate):
    """Update the session using an optimistic revision so concurrent edits do not overwrite each other."""
    counts = collection(COUNTS_COLLECTION)
    for _attempt in range(12):
        current = _session(business_id, session_id)
        revision = int(current.get("revision", 0) or 0)
        updated = copy.deepcopy(current)
        mutate(updated)
        updated["updated_at"] = now_utc()
        query = {
            "_id": _clean_id(session_id),
            "business_id": str(business_id),
            "revision": revision,
        }
        result = counts.find_one_and_update(query, {
            "$set": {
                "items": updated.get("items", []),
                "status": updated.get("status", current.get("status")),
                "finalization_started_at": updated.get("finalization_started_at"),
                "completed_at": updated.get("completed_at"),
                "completed_by_user_id": updated.get("completed_by_user_id"),
                "last_error_code": updated.get("last_error_code"),
                "updated_at": updated["updated_at"],
            },
            "$inc": {"revision": 1},
        })
        if result:
            return _session(business_id, session_id)
    raise APIError("Stock count session changed repeatedly. Reload and retry.", 409, "stock_count_concurrent_update")


def _item_for(session, product_id):
    for item in session.get("items") or []:
        if str(item.get("product_id")) == str(product_id):
            return item
    return None


def _change_item(session, product_id, **changes):
    item = _item_for(session, product_id)
    if item is None:
        raise APIError("Product is not included in this stock count session.", 404, "stock_count_item_not_found")
    item.update(copy.deepcopy(changes))


def _product_snapshot(business_id, product_id):
    product = collection(PRODUCTS_COLLECTION).find_one({
        "_id": _clean_id(product_id),
        "business_id": str(business_id),
    })
    if not product:
        raise APIError("A counted product is no longer available to this business.", 409, "stock_count_product_missing")
    stock = _decimal(product.get("stock_quantity", 0) or 0, "System stock")
    reserved = _decimal(product.get("reserved_quantity", 0) or 0, "Reserved stock")
    if reserved > stock:
        raise APIError("Product reserved stock exceeds physical system stock. Reconcile orders before counting.", 409, "invalid_inventory_state")
    return product, stock, reserved


def create_count_session(user_id, payload, idempotency_key):
    """Create a snapshot session. No stock is changed until successful finalization."""
    business, business_id = _business(user_id, "inventory.manage")
    key = str(idempotency_key or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", key):
        raise APIError("Idempotency-Key must be 8–128 safe characters.", 422, "invalid_idempotency_key")
    if not isinstance(payload, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")

    selection = payload.get("product_ids")
    if selection is None:
        selection_fingerprint = "all_active"
    else:
        if not isinstance(selection, list) or not selection or len(selection) > MAX_SESSION_PRODUCTS:
            raise APIError(f"product_ids must contain 1–{MAX_SESSION_PRODUCTS} product IDs.", 422, "invalid_stock_count_products")
        clean_selection = []
        for raw in selection:
            value = str(raw or "").strip()
            if not value or len(value) > 128:
                raise APIError("Every product ID must be a valid identifier.", 422, "invalid_stock_count_products")
            if value not in clean_selection:
                clean_selection.append(value)
        selection = sorted(clean_selection)
        selection_fingerprint = selection

    fingerprint = _fingerprint({
        "business_id": business_id,
        "selection": selection_fingerprint,
    })
    counts = collection(COUNTS_COLLECTION)
    prior = counts.find_one({"business_id": business_id, "idempotency_key": key})
    if prior:
        if prior.get("request_fingerprint") != fingerprint:
            raise APIError("Idempotency-Key was reused for a different stock count selection.", 409, "idempotency_key_reused")
        prior["id"] = str(prior.get("_id") or "")
        return _serialize(prior)

    products = collection(PRODUCTS_COLLECTION)
    if selection is None:
        product_rows = list(
            products.find({"business_id": business_id, "status": "active"})
            .sort("name", 1)
            .limit(MAX_SESSION_PRODUCTS + 1)
        )
        if len(product_rows) > MAX_SESSION_PRODUCTS:
            raise APIError(
                f"This count includes more than {MAX_SESSION_PRODUCTS} products. Select a smaller batch.",
                422,
                "stock_count_batch_too_large",
            )
    else:
        product_rows = []
        for product_id in selection:
            product = products.find_one({
                "_id": _clean_id(product_id),
                "business_id": business_id,
                "status": "active",
            })
            if not product:
                raise APIError("One or more products are not active in this business.", 422, "invalid_stock_count_product")
            product_rows.append(product)

    if not product_rows:
        raise APIError("There are no active products to count.", 409, "no_active_products")

    items = []
    for product in product_rows:
        _, stock, reserved = _product_snapshot(business_id, product["_id"])
        items.append({
            "product_id": str(product["_id"]),
            "product_name": str(product.get("name") or "Product")[:160],
            "sku": str(product.get("sku") or "")[:80],
            "system_stock_quantity": float(stock),
            "system_reserved_quantity": float(reserved),
            "counted_quantity": None,
            "count_status": "pending",
            "counted_by_user_id": None,
            "counted_at": None,
            "count_attempt": 1,
            "adjustment_idempotency_key": None,
            "movement_id": None,
            "variance_quantity": None,
            "conflict_code": None,
        })
    document = {
        "_id": ObjectId(),
        "business_id": business_id,
        "idempotency_key": key,
        "request_fingerprint": fingerprint,
        "status": "in_progress",
        "revision": 0,
        "items": items,
        "currency": str(business.get("currency") or "KES").upper(),
        "created_by_user_id": str(user_id),
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "finalization_started_at": None,
        "completed_at": None,
        "completed_by_user_id": None,
        "last_error_code": None,
        "outbox_enqueued_event_keys": [],
    }
    document["id"] = str(document["_id"])
    started_event = _event(document, "started", "inventory.stock_count_started", "in_progress", user_id)
    document["outbox_event_manifest"] = [started_event]
    try:
        counts.insert_one(document)
    except DuplicateKeyError:
        prior = counts.find_one({"business_id": business_id, "idempotency_key": key})
        if prior and prior.get("request_fingerprint") == fingerprint:
            prior["id"] = str(prior.get("_id") or "")
            return _serialize(prior)
        raise APIError("Idempotency-Key conflicts with an existing stock count.", 409, "idempotency_key_reused")

    _dispatch_count(document)
    log_action(user_id, "biashara.stock_count_started", "stock_count", document["_id"], {"item_count": len(items)})
    return _serialize(document)


def list_count_sessions(user_id, status=None, limit=50):
    _business, business_id = _business(user_id, "inventory.view")
    try:
        limit = min(max(int(limit), 1), MAX_LIST_LIMIT)
    except (TypeError, ValueError):
        limit = 50
    query = {"business_id": business_id}
    if status:
        state = str(status).strip().lower()
        if state not in {"in_progress", "finalizing", "conflict", "completed"}:
            raise APIError("Unknown stock count status.", 422, "invalid_stock_count_status")
        query["status"] = state
    rows = collection(COUNTS_COLLECTION).find(query).sort("created_at", -1).limit(limit)
    return [_serialize(row) for row in rows]


def get_count_session(user_id, session_id):
    _business, business_id = _business(user_id, "inventory.view")
    return _serialize(_session(business_id, session_id))


def record_count(user_id, session_id, product_id, counted_quantity):
    """Record a physical count; it does not mutate catalogue stock."""
    _business, business_id = _business(user_id, "inventory.manage")
    quantity = _decimal(counted_quantity, "counted_quantity")
    session = _session(business_id, session_id)
    if session.get("status") != "in_progress":
        raise APIError("Only an in-progress stock count can accept physical counts. Recount conflicted lines first.", 409, "stock_count_not_editable")
    if _item_for(session, product_id) is None:
        raise APIError("Product is not included in this stock count session.", 404, "stock_count_item_not_found")
    now = now_utc()

    def mutate(updated):
        if updated.get("status") != "in_progress":
            raise APIError("Stock count session changed while recording this count.", 409, "stock_count_not_editable")
        item = _item_for(updated, product_id)
        if item is None:
            raise APIError("Product is not included in this stock count session.", 404, "stock_count_item_not_found")
        if item.get("count_status") in {"applied", "no_adjustment"}:
            raise APIError("A reconciled line cannot be edited.", 409, "stock_count_line_finalized")
        item.update({
            "counted_quantity": float(quantity),
            "count_status": "counted",
            "counted_by_user_id": str(user_id),
            "counted_at": now,
            "conflict_code": None,
            "variance_quantity": float(quantity - Decimal(str(item.get("system_stock_quantity", 0) or 0))),
        })
    updated = _mutate_session(business_id, session_id, mutate)
    log_action(user_id, "biashara.stock_count_quantity_recorded", "stock_count", updated["_id"], {
        "product_id": str(product_id),
        "counted_quantity": float(quantity),
    })
    return _serialize(updated)


def recount_item(user_id, session_id, product_id):
    """Refresh an item's system snapshot after a concurrent movement, then require a new physical count."""
    _business, business_id = _business(user_id, "inventory.manage")
    session = _session(business_id, session_id)
    if session.get("status") not in {"in_progress", "conflict", "finalizing"}:
        raise APIError("A completed stock count cannot be reopened.", 409, "stock_count_not_reopenable")
    item_before = _item_for(session, product_id)
    if item_before is None:
        raise APIError("Product is not included in this stock count session.", 404, "stock_count_item_not_found")
    if item_before.get("count_status") in {"applied", "no_adjustment"}:
        raise APIError("A reconciled line cannot be recounted in the same session.", 409, "stock_count_line_finalized")
    product, stock, reserved = _product_snapshot(business_id, product_id)
    now = now_utc()

    def mutate(updated):
        if updated.get("status") not in {"in_progress", "conflict", "finalizing"}:
            raise APIError("Stock count session changed while reopening this line.", 409, "stock_count_not_reopenable")
        item = _item_for(updated, product_id)
        if item is None or item.get("count_status") in {"applied", "no_adjustment"}:
            raise APIError("This stock count line cannot be reopened.", 409, "stock_count_line_finalized")
        item.update({
            "product_name": str(product.get("name") or item.get("product_name") or "Product")[:160],
            "sku": str(product.get("sku") or item.get("sku") or "")[:80],
            "system_stock_quantity": float(stock),
            "system_reserved_quantity": float(reserved),
            "counted_quantity": None,
            "count_status": "pending",
            "counted_by_user_id": None,
            "counted_at": None,
            "count_attempt": int(item.get("count_attempt", 1) or 1) + 1,
            "adjustment_idempotency_key": None,
            "movement_id": None,
            "variance_quantity": None,
            "conflict_code": None,
        })
        updated["status"] = "in_progress"
        updated["last_error_code"] = None
        updated["finalization_started_at"] = None
    updated = _mutate_session(business_id, session_id, mutate)
    log_action(user_id, "biashara.stock_count_item_reopened", "stock_count", updated["_id"], {
        "product_id": str(product_id),
        "count_attempt": _item_for(updated, product_id).get("count_attempt"),
    })
    return _serialize(updated)


def _mark_conflict(business_id, session_id, product_id, error_code):
    now = now_utc()

    def mutate(updated):
        item = _item_for(updated, product_id)
        if item:
            item["count_status"] = "conflict"
            item["conflict_code"] = str(error_code)[:100]
        updated["status"] = "conflict"
        updated["last_error_code"] = str(error_code)[:100]
        updated["finalization_started_at"] = updated.get("finalization_started_at") or now
    return _mutate_session(business_id, session_id, mutate)


def finalize_count_session(user_id, session_id):
    """Apply counted differences through the stock ledger; retries recover one item at a time."""
    business, business_id = _business(user_id, "inventory.manage")
    session = _session(business_id, session_id)
    if session.get("status") == "completed":
        return _serialize(session)
    if session.get("status") not in {"in_progress", "conflict", "finalizing"}:
        raise APIError("This stock count cannot be finalized from its current state.", 409, "stock_count_not_finalizable")
    for item in session.get("items") or []:
        if item.get("count_status") == "conflict":
            raise APIError("At least one line requires a recount before finalization.", 409, "stock_count_recount_required")
        if item.get("count_status") not in {"counted", "applied", "no_adjustment"}:
            raise APIError("Every product must have a physical count before finalization.", 409, "stock_count_incomplete")

    # Preflight catches changes that occurred while the count was in progress.
    for item in session.get("items") or []:
        if item.get("count_status") != "counted":
            continue
        try:
            _product, stock, reserved = _product_snapshot(business_id, item["product_id"])
        except APIError as error:
            _mark_conflict(business_id, session_id, item["product_id"], error.code)
            raise
        expected_stock = Decimal(str(item.get("system_stock_quantity", 0) or 0))
        expected_reserved = Decimal(str(item.get("system_reserved_quantity", 0) or 0))
        if (
            abs(stock - expected_stock) > QUANTITY_TOLERANCE
            or abs(reserved - expected_reserved) > QUANTITY_TOLERANCE
        ):
            _mark_conflict(business_id, session_id, item["product_id"], "stock_count_snapshot_stale")
            raise APIError(
                "Inventory changed after counting began. Recount the flagged item; no stale quantity was written.",
                409,
                "stock_count_snapshot_stale",
            )

    def begin(updated):
        if updated.get("status") == "completed":
            return
        updated["status"] = "finalizing"
        updated["finalization_started_at"] = updated.get("finalization_started_at") or now_utc()
        updated["last_error_code"] = None
    session = _mutate_session(business_id, session_id, begin)

    for item in list(session.get("items") or []):
        if item.get("count_status") in {"applied", "no_adjustment"}:
            continue
        product_id = str(item["product_id"])
        system_stock = Decimal(str(item.get("system_stock_quantity", 0) or 0))
        reserved = Decimal(str(item.get("system_reserved_quantity", 0) or 0))
        counted = _decimal(item.get("counted_quantity"), "counted_quantity")
        variance = counted - system_stock
        idem_key = (
            item.get("adjustment_idempotency_key")
            or f"stock-count:{session['id']}:{product_id}:{int(item.get('count_attempt', 1) or 1)}"
        )

        # A zero variance is still retained in the count record, but it creates
        # no fictitious inventory movement because stock did not change.
        if abs(variance) <= QUANTITY_TOLERANCE:
            def mark_no_adjustment(updated, pid=product_id, variance_value=variance):
                _change_item(
                    updated, pid,
                    count_status="no_adjustment",
                    variance_quantity=float(variance_value),
                    adjustment_idempotency_key=idem_key,
                    movement_id=None,
                    conflict_code=None,
                )
            session = _mutate_session(business_id, session_id, mark_no_adjustment)
            continue

        try:
            result = commerce_services.inventory_adjustment(
                user_id,
                product_id,
                {
                    "movement_type": "set",
                    "quantity": float(counted),
                    "reason": "cycle_count_reconciliation",
                    "idempotency_key": idem_key,
                    "expected_stock_quantity": float(system_stock),
                    "expected_reserved_quantity": float(reserved),
                },
            )
        except APIError as error:
            _mark_conflict(business_id, session_id, product_id, error.code)
            raise APIError(
                "Stock count was paused for " + product_id + ". Resolve the flagged line and retry finalization.",
                409,
                error.code if error.code else "stock_count_reconcile_failed",
            )

        movement = result.get("movement") or {}
        movement_id = str(movement.get("id") or "") or None
        def mark_applied(updated, pid=product_id, movement_key=idem_key, movement_value=movement_id, variance_value=variance):
            _change_item(
                updated, pid,
                count_status="applied",
                variance_quantity=float(variance_value),
                adjustment_idempotency_key=movement_key,
                movement_id=movement_value,
                conflict_code=None,
            )
        session = _mutate_session(business_id, session_id, mark_applied)

    # A no-change line could be affected by a sale/order while other lines are
    # being reconciled. Verify it again before declaring the whole count complete.
    session = _session(business_id, session_id)
    for item in session.get("items") or []:
        if item.get("count_status") != "no_adjustment":
            continue
        product, stock, reserved = _product_snapshot(business_id, item["product_id"])
        expected_stock = Decimal(str(item.get("system_stock_quantity", 0) or 0))
        expected_reserved = Decimal(str(item.get("system_reserved_quantity", 0) or 0))
        if (
            abs(stock - expected_stock) > QUANTITY_TOLERANCE
            or abs(reserved - expected_reserved) > QUANTITY_TOLERANCE
        ):
            _mark_conflict(business_id, session_id, item["product_id"], "stock_count_snapshot_stale")
            raise APIError(
                "Inventory changed while finalizing the stock count. Recount the flagged item.",
                409,
                "stock_count_snapshot_stale",
            )

    session = _session(business_id, session_id)
    if any(item.get("count_status") not in {"applied", "no_adjustment"} for item in session.get("items") or []):
        raise APIError("Stock count has unfinished lines and remains recoverable.", 409, "stock_count_incomplete")

    session["id"] = str(session.get("_id") or session_id)
    completed_event = _event(session, "completed", "inventory.stock_count_completed", "completed", user_id)
    now = now_utc()
    result = collection(COUNTS_COLLECTION).update_one(
        {"_id": _clean_id(session_id), "business_id": business_id, "status": "finalizing"},
        {
            "$set": {
                "status": "completed",
                "completed_at": now,
                "completed_by_user_id": str(user_id),
                "updated_at": now,
                "last_error_code": None,
            },
            "$addToSet": {"outbox_event_manifest": completed_event},
            "$inc": {"revision": 1},
        },
    )
    final_session = _session(business_id, session_id)
    if not result.matched_count and final_session.get("status") != "completed":
        raise APIError("Stock count changed while completing. Retry finalization.", 409, "stock_count_concurrent_update")
    _dispatch_count(final_session)
    log_action(user_id, "biashara.stock_count_completed", "stock_count", final_session["_id"], {
        "item_count": len(final_session.get("items") or []),
        "adjustment_count": sum(1 for row in final_session.get("items") or [] if row.get("count_status") == "applied"),
        "no_adjustment_count": sum(1 for row in final_session.get("items") or [] if row.get("count_status") == "no_adjustment"),
    })
    return _serialize(final_session)
