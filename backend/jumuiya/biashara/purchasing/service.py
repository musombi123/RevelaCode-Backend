"""Tenant-scoped suppliers, purchase orders and recoverable goods receiving."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.biashara import services as biashara_services
from backend.jumuiya.biashara.sync.outbox import build_outbox_manifest, dispatch_manifest_for_record
from backend.jumuiya.biashara.tenancy.service import require_permission


logger = logging.getLogger("jumuiya.biashara.purchasing")

SUPPLIERS_COLLECTION = "jumuiya_suppliers"
PURCHASE_ORDERS_COLLECTION = "jumuiya_purchase_orders"
RECEIPTS_COLLECTION = "jumuiya_purchase_order_receipts"
MAX_LINES = 50
MAX_LIST_LIMIT = 100
RECEIVING_LEASE_SECONDS = 180
SAFE_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


def now_utc():
    return datetime.now(timezone.utc)


def _clean_id(value):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return value


def _serialise(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value, list):
        return [_serialise(item) for item in value]
    if isinstance(value, dict):
        return {
            ("id" if key == "_id" else key): _serialise(item)
            for key, item in value.items()
            if key not in {
                "request_fingerprint",
                "receiving_lease_token",
                "outbox_event_manifest",
                "outbox_enqueued_event_keys",
                "pending_inventory_mutations",
            }
        }
    return value


def _fingerprint(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _context(user_id, permission):
    business = require_permission(user_id, permission)
    business_id = str(business.get("id") or "")
    if not business_id:
        raise APIError("Selected business is unavailable.", 409, "business_id_missing")
    return business, business_id


def _key(value, field_name="Idempotency-Key", required=False):
    value = str(value or "").strip()
    if not value and not required:
        return None
    if not SAFE_IDEMPOTENCY_KEY.fullmatch(value):
        raise APIError(f"{field_name} must contain 8–128 safe characters.", 422, "invalid_idempotency_key")
    return value


def _text(value, field_name, maximum, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise APIError(f"{field_name} must be text.", 422, "invalid_purchasing_input")
    value = value.strip()
    if required and not value:
        raise APIError(f"{field_name} is required.", 422, "invalid_purchasing_input")
    if len(value) > maximum:
        raise APIError(f"{field_name} must not exceed {maximum} characters.", 422, "invalid_purchasing_input")
    return value


def _positive_decimal(value, field_name, allow_zero=False):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise APIError(f"{field_name} must be a valid number.", 422, "invalid_purchasing_quantity")
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        qualifier = "non-negative" if allow_zero else "greater than zero"
        raise APIError(f"{field_name} must be {qualifier}.", 422, "invalid_purchasing_quantity")
    return number


def _minor_amount(value, field_name, allow_zero=False):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise APIError(f"{field_name} must be a valid monetary amount.", 422, "invalid_purchasing_amount")
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        qualifier = "non-negative" if allow_zero else "greater than zero"
        raise APIError(f"{field_name} must be {qualifier}.", 422, "invalid_purchasing_amount")
    return int(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def _dispatch_source(source_collection, business_id, record_id):
    try:
        return dispatch_manifest_for_record(source_collection, str(business_id), record_id)
    except Exception as error:
        logger.warning(
            "Biashara purchasing outbox dispatch deferred (source=%s, error=%s)",
            source_collection,
            type(error).__name__,
        )
        return {"enqueued": 0, "pending": 1, "errors": 1}


def _record_event(event_key, event_type, entity_type, entity_id, payload, user_id, occurred_at=None):
    return build_outbox_manifest(
        event_key=event_key,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload=payload,
        actor_user_id=user_id,
        occurred_at=occurred_at or now_utc(),
    )


def create_supplier(user_id, payload):
    business, business_id = _context(user_id, "suppliers.manage")
    if not isinstance(payload, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")

    key = _key(payload.get("idempotency_key"))
    name = _text(payload.get("name"), "name", 160, required=True)
    contact_name = _text(payload.get("contact_name"), "contact_name", 160)
    phone = _text(payload.get("phone"), "phone", 40)
    email = _text(payload.get("email"), "email", 254).lower()
    tax_identifier = _text(payload.get("tax_identifier"), "tax_identifier", 80)
    notes = _text(payload.get("notes"), "notes", 1000)
    try:
        lead_time = int(payload.get("lead_time_days", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        raise APIError("lead_time_days must be an integer between 0 and 365.", 422, "invalid_supplier_lead_time")
    if lead_time < 0 or lead_time > 365:
        raise APIError("lead_time_days must be between 0 and 365.", 422, "invalid_supplier_lead_time")

    stable = {
        "name": name,
        "contact_name": contact_name,
        "phone": phone,
        "email": email,
        "tax_identifier": tax_identifier,
        "notes": notes,
        "lead_time_days": lead_time,
    }
    fingerprint = _fingerprint(stable)
    suppliers = collection(SUPPLIERS_COLLECTION)
    if key:
        existing = suppliers.find_one({"business_id": business_id, "idempotency_key": key})
        if existing:
            if existing.get("request_fingerprint") != fingerprint:
                raise APIError("Idempotency-Key was reused for different supplier data.", 409, "idempotency_key_reused")
            _dispatch_source(SUPPLIERS_COLLECTION, business_id, existing["_id"])
            return _serialise(existing)

    now = now_utc()
    document = {
        "_id": ObjectId(),
        "business_id": business_id,
        **stable,
        "status": "active",
        "idempotency_key": key,
        "request_fingerprint": fingerprint,
        "created_by_user_id": str(user_id),
        "created_at": now,
        "updated_at": now,
        "outbox_enqueued_event_keys": [],
    }
    document["outbox_event_manifest"] = [
        _record_event(
            f"supplier:{document['_id']}:created",
            "supplier.created",
            "supplier",
            document["_id"],
            {"status": "active"},
            user_id,
            now,
        )
    ]
    try:
        suppliers.insert_one(document)
    except DuplicateKeyError:
        if key:
            existing = suppliers.find_one({"business_id": business_id, "idempotency_key": key})
            if existing and existing.get("request_fingerprint") == fingerprint:
                return _serialise(existing)
            if existing:
                raise APIError("Idempotency-Key was reused for different supplier data.", 409, "idempotency_key_reused")
        raise

    _dispatch_source(SUPPLIERS_COLLECTION, business_id, document["_id"])
    log_action(user_id, "biashara.supplier_created", "supplier", document["_id"])
    return _serialise(document)


def list_suppliers(user_id, search=None, status="active", limit=50):
    _business_data, business_id = _context(user_id, "suppliers.view")
    try:
        limit = min(max(int(limit), 1), MAX_LIST_LIMIT)
    except (TypeError, ValueError, OverflowError):
        limit = 50
    query = {"business_id": business_id}
    if status:
        normalized = str(status).strip().lower()
        if normalized not in {"active", "inactive", "all"}:
            raise APIError("Supplier status must be active, inactive or all.", 422, "invalid_supplier_status")
        if normalized != "all":
            query["status"] = normalized
    rows = list(collection(SUPPLIERS_COLLECTION).find(query).sort("created_at", -1).limit(limit))
    needle = str(search or "").strip().lower()[:120]
    if needle:
        rows = [
            row for row in rows
            if any(needle in str(row.get(field) or "").lower() for field in ("name", "contact_name", "phone", "email", "tax_identifier"))
        ]
    return [_serialise(row) for row in rows]


def update_supplier(user_id, supplier_id, payload):
    _business_data, business_id = _context(user_id, "suppliers.manage")
    if not isinstance(payload, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    suppliers = collection(SUPPLIERS_COLLECTION)
    query = {"_id": _clean_id(supplier_id), "business_id": business_id}
    current = suppliers.find_one(query)
    if not current:
        raise APIError("Supplier not found.", 404, "supplier_not_found")
    fields = {
        "name": (160, True),
        "contact_name": (160, False),
        "phone": (40, False),
        "email": (254, False),
        "tax_identifier": (80, False),
        "notes": (1000, False),
    }
    updates = {}
    for field, (maximum, required) in fields.items():
        if field in payload:
            value = _text(payload[field], field, maximum, required=required)
            updates[field] = value.lower() if field == "email" else value
    if "lead_time_days" in payload:
        try:
            lead_time = int(payload["lead_time_days"])
        except (TypeError, ValueError, OverflowError):
            raise APIError("lead_time_days must be an integer between 0 and 365.", 422, "invalid_supplier_lead_time")
        if lead_time < 0 or lead_time > 365:
            raise APIError("lead_time_days must be between 0 and 365.", 422, "invalid_supplier_lead_time")
        updates["lead_time_days"] = lead_time
    if "status" in payload:
        status = str(payload["status"] or "").strip().lower()
        if status not in {"active", "inactive"}:
            raise APIError("Supplier status must be active or inactive.", 422, "invalid_supplier_status")
        updates["status"] = status
    if not updates:
        raise APIError("No editable supplier fields were provided.", 422, "empty_update")
    updates["updated_at"] = now_utc()
    saved = suppliers.find_one_and_update(query, {"$set": updates}, return_document=ReturnDocument.AFTER)
    if not saved:
        raise APIError("Supplier changed while it was being edited. Reload and retry.", 409, "supplier_concurrent_update")
    log_action(user_id, "biashara.supplier_updated", "supplier", current["_id"], {"changed_fields": sorted(set(updates) - {"updated_at"})})
    return _serialise(saved)


def _normalise_po_lines(business_id, currency, raw_lines):
    if not isinstance(raw_lines, list) or not raw_lines or len(raw_lines) > MAX_LINES:
        raise APIError("Purchase order must contain 1–50 product lines.", 422, "invalid_purchase_order_lines")
    seen = set()
    normalised = []
    subtotal_minor = 0
    products = collection("jumuiya_products")
    for index, raw in enumerate(raw_lines):
        if not isinstance(raw, dict):
            raise APIError(f"Purchase order line {index + 1} must be an object.", 422, "invalid_purchase_order_lines")
        product_id = str(raw.get("product_id") or "").strip()
        if not product_id:
            raise APIError(f"Purchase order line {index + 1} requires product_id.", 422, "invalid_purchase_order_lines")
        product_key = product_id
        if product_key in seen:
            raise APIError("Each product may appear only once in a purchase order; combine duplicate lines first.", 422, "duplicate_purchase_order_product")
        seen.add(product_key)
        product = products.find_one({"_id": _clean_id(product_id), "business_id": business_id})
        if not product or str(product.get("status") or "active").lower() in {"deleted", "archived"}:
            raise APIError(f"Purchase order line {index + 1} references an unavailable product.", 404, "purchase_order_product_not_found")

        product_currency = str(product.get("currency") or currency).strip().upper()
        if product_currency != currency:
            raise APIError("Purchase order currency must match every selected product currency.", 409, "purchase_order_currency_mismatch")

        quantity = _positive_decimal(raw.get("quantity"), f"lines[{index}].quantity")
        raw_unit_cost = raw.get("unit_cost")
        if raw_unit_cost is None or str(raw_unit_cost).strip() == "":
            raw_unit_cost = product.get("cost_price")
        unit_cost_minor = _minor_amount(raw_unit_cost, f"lines[{index}].unit_cost")
        line_total_minor = int(
            (Decimal(unit_cost_minor) * quantity).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        subtotal_minor += line_total_minor
        normalised.append({
            "line_id": str(product["_id"]),
            "product_id": str(product["_id"]),
            "product_name": _text(str(product.get("name") or ""), f"lines[{index}].product_name", 160, required=True),
            "sku": str(product.get("sku") or "")[:80],
            "quantity_ordered": float(quantity),
            "quantity_received": 0.0,
            "unit_cost_minor": unit_cost_minor,
            "line_total_minor": line_total_minor,
            "currency": currency,
        })
    return normalised, subtotal_minor


def create_purchase_order(user_id, payload):
    business, business_id = _context(user_id, "purchasing.manage")
    if not isinstance(payload, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    key = _key(payload.get("idempotency_key"))
    supplier_id = str(payload.get("supplier_id") or "").strip()
    supplier = collection(SUPPLIERS_COLLECTION).find_one({
        "_id": _clean_id(supplier_id),
        "business_id": business_id,
        "status": "active",
    })
    if not supplier:
        raise APIError("An active supplier for this business is required.", 404, "supplier_not_found")

    currency = str(payload.get("currency") or business.get("currency") or "KES").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise APIError("Purchase order currency must be a three-letter ISO currency code.", 422, "invalid_purchase_order_currency")
    expected_date = payload.get("expected_delivery_date")
    if expected_date:
        if not isinstance(expected_date, str):
            raise APIError("expected_delivery_date must use YYYY-MM-DD.", 422, "invalid_purchase_order_date")
        try:
            date.fromisoformat(expected_date)
        except ValueError:
            raise APIError("expected_delivery_date must use YYYY-MM-DD.", 422, "invalid_purchase_order_date")
    notes = _text(payload.get("notes"), "notes", 1000)
    lines, subtotal_minor = _normalise_po_lines(business_id, currency, payload.get("lines"))

    stable = {
        "supplier_id": str(supplier["_id"]),
        "currency": currency,
        "expected_delivery_date": expected_date or None,
        "notes": notes,
        "lines": [
            {
                "product_id": line["product_id"],
                "quantity": format(Decimal(str(line["quantity_ordered"])).normalize(), "f"),
                "unit_cost_minor": line["unit_cost_minor"],
            }
            for line in lines
        ],
    }
    fingerprint = _fingerprint(stable)
    orders = collection(PURCHASE_ORDERS_COLLECTION)
    if key:
        existing = orders.find_one({"business_id": business_id, "idempotency_key": key})
        if existing:
            if existing.get("request_fingerprint") != fingerprint:
                raise APIError("Idempotency-Key was reused for different purchase order data.", 409, "idempotency_key_reused")
            _dispatch_source(PURCHASE_ORDERS_COLLECTION, business_id, existing["_id"])
            return _serialise(existing)

    now = now_utc()
    document_id = ObjectId()
    po_number = f"PO-{now.strftime('%Y%m%d')}-{str(document_id)[-6:].upper()}"
    document = {
        "_id": document_id,
        "business_id": business_id,
        "po_number": po_number,
        "supplier_id": str(supplier["_id"]),
        "supplier_snapshot": {
            "name": supplier["name"],
            "phone": supplier.get("phone", ""),
            "email": supplier.get("email", ""),
        },
        "currency": currency,
        "expected_delivery_date": expected_date or None,
        "notes": notes,
        "lines": lines,
        "subtotal_minor": subtotal_minor,
        "total_amount_minor": subtotal_minor,
        "status": "draft",
        "status_history": [{
            "from": None,
            "to": "draft",
            "at": now,
            "actor_user_id": str(user_id),
        }],
        "applied_receipt_ids": [],
        "receiving_lease_token": None,
        "receiving_lease_expires_at": None,
        "idempotency_key": key,
        "request_fingerprint": fingerprint,
        "created_by_user_id": str(user_id),
        "created_at": now,
        "updated_at": now,
        "outbox_enqueued_event_keys": [],
    }
    document["outbox_event_manifest"] = [
        _record_event(
            f"purchase-order:{document_id}:created",
            "purchase_order.created",
            "purchase_order",
            document_id,
            {
                "status": "draft",
                "purchase_order_id": str(document_id),
                "total_amount_minor": subtotal_minor,
                "currency": currency,
                "supplier_id": str(supplier["_id"]),
            },
            user_id,
            now,
        )
    ]
    try:
        orders.insert_one(document)
    except DuplicateKeyError:
        if key:
            existing = orders.find_one({"business_id": business_id, "idempotency_key": key})
            if existing and existing.get("request_fingerprint") == fingerprint:
                return _serialise(existing)
            if existing:
                raise APIError("Idempotency-Key was reused for different purchase order data.", 409, "idempotency_key_reused")
        raise

    _dispatch_source(PURCHASE_ORDERS_COLLECTION, business_id, document_id)
    log_action(user_id, "biashara.purchase_order_created", "purchase_order", document_id, {
        "po_number": po_number,
        "line_count": len(lines),
        "total_amount_minor": subtotal_minor,
        "currency": currency,
    })
    return _serialise(document)


def list_purchase_orders(user_id, status=None, supplier_id=None, limit=50):
    _business_data, business_id = _context(user_id, "purchasing.view")
    try:
        limit = min(max(int(limit), 1), MAX_LIST_LIMIT)
    except (TypeError, ValueError, OverflowError):
        limit = 50
    query = {"business_id": business_id}
    if status:
        normalized = str(status).strip().lower()
        if normalized not in {"draft", "ordered", "partially_received", "received", "cancelled"}:
            raise APIError("Unknown purchase order status.", 422, "invalid_purchase_order_status")
        query["status"] = normalized
    if supplier_id:
        query["supplier_id"] = str(_clean_id(supplier_id))
    rows = collection(PURCHASE_ORDERS_COLLECTION).find(query).sort("created_at", -1).limit(limit)
    return [_serialise(row) for row in rows]


def get_purchase_order(user_id, purchase_order_id):
    _business_data, business_id = _context(user_id, "purchasing.view")
    order = collection(PURCHASE_ORDERS_COLLECTION).find_one({
        "_id": _clean_id(purchase_order_id),
        "business_id": business_id,
    })
    if not order:
        raise APIError("Purchase order not found.", 404, "purchase_order_not_found")
    return _serialise(order)


def update_purchase_order_status(user_id, purchase_order_id, next_status):
    _business_data, business_id = _context(user_id, "purchasing.manage")
    next_status = str(next_status or "").strip().lower()
    if next_status not in {"ordered", "cancelled"}:
        raise APIError("Only draft-to-ordered or eligible-to-cancel transitions are allowed here.", 422, "invalid_purchase_order_transition")
    orders = collection(PURCHASE_ORDERS_COLLECTION)
    query = {"_id": _clean_id(purchase_order_id), "business_id": business_id}
    current = orders.find_one(query)
    if not current:
        raise APIError("Purchase order not found.", 404, "purchase_order_not_found")
    status = str(current.get("status") or "draft")
    if status == next_status:
        return _serialise(current)
    if status == "draft" and next_status == "ordered":
        pass
    elif next_status == "cancelled" and status in {"draft", "ordered"}:
        if any(float(line.get("quantity_received", 0) or 0) > 0 for line in current.get("lines") or []):
            raise APIError("A purchase order with received stock cannot be cancelled. Record a supplier return or resolve it manually.", 409, "purchase_order_has_receipts")
    else:
        raise APIError(f"Purchase order cannot transition from {status} to {next_status}.", 409, "invalid_purchase_order_transition")

    now = now_utc()
    event_history = {
        "from": status,
        "to": next_status,
        "at": now,
        "actor_user_id": str(user_id),
    }
    manifest = _record_event(
        f"purchase-order:{current['_id']}:status:{next_status}",
        "purchase_order.status_changed",
        "purchase_order",
        current["_id"],
        {
            "status": next_status,
            "purchase_order_id": str(current["_id"]),
            "total_amount_minor": int(current.get("total_amount_minor", 0) or 0),
            "currency": current.get("currency", "KES"),
        },
        user_id,
        now,
    )
    updated = orders.find_one_and_update(
        {"_id": current["_id"], "business_id": business_id, "status": status},
        {
            "$set": {"status": next_status, "updated_at": now},
            "$push": {"status_history": event_history},
            "$addToSet": {"outbox_event_manifest": manifest},
        },
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise APIError("Purchase order changed while saving the status. Reload and retry.", 409, "purchase_order_concurrent_update")
    _dispatch_source(PURCHASE_ORDERS_COLLECTION, business_id, updated["_id"])
    log_action(user_id, "biashara.purchase_order_status_changed", "purchase_order", updated["_id"], {
        "from": status,
        "to": next_status,
    })
    return _serialise(updated)


def _receipt_fingerprint(purchase_order_id, normalised_lines):
    stable = {
        "purchase_order_id": str(purchase_order_id),
        "lines": sorted(
            [
                {
                    "product_id": str(item["product_id"]),
                    "quantity": format(Decimal(str(item["quantity"])).normalize(), "f"),
                }
                for item in normalised_lines
            ],
            key=lambda item: item["product_id"],
        ),
    }
    return _fingerprint(stable)


def _normalise_receipt_lines(payload):
    raw_lines = payload.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines or len(raw_lines) > MAX_LINES:
        raise APIError("A receipt must contain 1–50 product lines.", 422, "invalid_purchase_receipt_lines")
    normalised = []
    seen = set()
    for index, raw in enumerate(raw_lines):
        if not isinstance(raw, dict):
            raise APIError(f"Receipt line {index + 1} must be an object.", 422, "invalid_purchase_receipt_lines")
        product_id = str(raw.get("product_id") or "").strip()
        if not product_id:
            raise APIError(f"Receipt line {index + 1} requires product_id.", 422, "invalid_purchase_receipt_lines")
        if product_id in seen:
            raise APIError("Each product may appear only once per receipt; combine duplicate lines first.", 422, "duplicate_purchase_receipt_product")
        seen.add(product_id)
        quantity = _positive_decimal(raw.get("quantity"), f"lines[{index}].quantity")
        normalised.append({"product_id": product_id, "quantity": float(quantity)})
    return normalised


def _release_receiving_lease(purchase_order_id, business_id, token):
    collection(PURCHASE_ORDERS_COLLECTION).update_one(
        {
            "_id": _clean_id(purchase_order_id),
            "business_id": str(business_id),
            "receiving_lease_token": token,
        },
        {"$set": {
            "receiving_lease_token": None,
            "receiving_lease_expires_at": None,
        }},
    )


def _dispatch_receipt_event(purchase_order, receipt, user_id):
    event = _record_event(
        f"purchase-order:{purchase_order['_id']}:receipt:{receipt['_id']}",
        "purchase_order.receipt_recorded",
        "purchase_order",
        purchase_order["_id"],
        {
            "status": "received",
            "purchase_order_id": str(purchase_order["_id"]),
            "receipt_id": str(receipt["_id"]),
            "received_item_count": len(receipt.get("lines") or []),
            "currency": purchase_order.get("currency", "KES"),
        },
        user_id,
        receipt.get("completed_at") or now_utc(),
    )
    return event


def receive_purchase_order_items(user_id, purchase_order_id, payload, header_key=None):
    """Receive inventory idempotently; interrupted receipt replays repair effects, not duplicate stock."""
    business, business_id = _context(user_id, "purchasing.manage")
    require_permission(user_id, "inventory.manage", business_id=business_id)
    if not isinstance(payload, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    key = _key(header_key or payload.get("idempotency_key"), required=True)
    receipt_lines = _normalise_receipt_lines(payload)
    purchase_order_id = str(purchase_order_id)
    fingerprint = _receipt_fingerprint(purchase_order_id, receipt_lines)
    receipts = collection(RECEIPTS_COLLECTION)
    receipt_query = {
        "business_id": business_id,
        "purchase_order_id": purchase_order_id,
        "idempotency_key": key,
    }
    receipt = receipts.find_one(receipt_query)
    if receipt:
        if receipt.get("request_fingerprint") != fingerprint:
            raise APIError("Idempotency-Key was reused for different receipt data.", 409, "idempotency_key_reused")
        if receipt.get("status") == "completed":
            return _serialise(receipt)
    else:
        incomplete = receipts.find_one({
            "business_id": business_id,
            "purchase_order_id": purchase_order_id,
            "status": {"$in": ["pending", "processing", "partial"]},
        })
        if incomplete:
            raise APIError(
                "Another goods receipt is incomplete. Retry its original Idempotency-Key before starting a new receipt.",
                409,
                "purchase_receipt_recovery_required",
                details={"receipt_id": str(incomplete.get("_id") or ""), "status": incomplete.get("status")},
            )

    orders = collection(PURCHASE_ORDERS_COLLECTION)
    order_query = {"_id": _clean_id(purchase_order_id), "business_id": business_id}
    current_order = orders.find_one(order_query)
    if not current_order:
        raise APIError("Purchase order not found.", 404, "purchase_order_not_found")
    if current_order.get("status") not in {"ordered", "partially_received"}:
        raise APIError("Goods can be received only against an ordered or partially received purchase order.", 409, "purchase_order_not_receivable")
    if current_order.get("receiving_lease_token") and isinstance(current_order.get("receiving_lease_expires_at"), datetime):
        if current_order["receiving_lease_expires_at"] > now_utc():
            raise APIError("Another goods receipt is currently being processed. Retry the same receipt after it completes.", 409, "purchase_receipt_in_progress")

    lease_token = ObjectId().binary.hex()
    claimed = orders.find_one_and_update(
        {
            **order_query,
            "status": current_order["status"],
            "receiving_lease_token": current_order.get("receiving_lease_token"),
        },
        {"$set": {
            "receiving_lease_token": lease_token,
            "receiving_lease_expires_at": now_utc() + timedelta(seconds=RECEIVING_LEASE_SECONDS),
            "updated_at": now_utc(),
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        raise APIError("Purchase order receiving state changed. Reload and retry the same receipt key.", 409, "purchase_receipt_lease_conflict")

    try:
        # A different receipt might have appeared between the initial check and
        # our lease claim; reject it before stock is mutated.
        if receipt is None:
            incomplete = receipts.find_one({
                "business_id": business_id,
                "purchase_order_id": purchase_order_id,
                "status": {"$in": ["pending", "processing", "partial"]},
                "idempotency_key": {"$ne": key},
            })
            if incomplete:
                raise APIError(
                    "Another goods receipt is incomplete. Retry its original Idempotency-Key first.",
                    409,
                    "purchase_receipt_recovery_required",
                )

            line_by_product = {str(line.get("product_id")): line for line in claimed.get("lines") or []}
            if len(receipt_lines) != len({str(line["product_id"]) for line in receipt_lines}):
                raise APIError("Receipt product lines are invalid.", 422, "invalid_purchase_receipt_lines")
            receipt_doc_lines = []
            for item in receipt_lines:
                po_line = line_by_product.get(str(item["product_id"]))
                if not po_line:
                    raise APIError("Receipt includes a product not present in this purchase order.", 422, "receipt_product_not_in_purchase_order")
                ordered = _positive_decimal(po_line.get("quantity_ordered"), "quantity_ordered")
                already_received = _positive_decimal(po_line.get("quantity_received", 0), "quantity_received", allow_zero=True)
                requested = _positive_decimal(item["quantity"], "received_quantity")
                remaining = ordered - already_received
                if requested > remaining:
                    raise APIError("Receipt quantity exceeds the purchase order's remaining quantity.", 409, "purchase_receipt_exceeds_ordered_quantity")
                receipt_doc_lines.append({
                    "product_id": str(item["product_id"]),
                    "quantity": float(requested),
                    "status": "pending",
                    "movement_id": None,
                    "error_code": None,
                })
            now = now_utc()
            receipt = {
                "_id": ObjectId(),
                "business_id": business_id,
                "purchase_order_id": purchase_order_id,
                "purchase_order_number": claimed.get("po_number"),
                "idempotency_key": key,
                "request_fingerprint": fingerprint,
                "status": "pending",
                "lines": receipt_doc_lines,
                "created_by_user_id": str(user_id),
                "created_at": now,
                "updated_at": now,
                "completed_at": None,
            }
            try:
                receipts.insert_one(receipt)
            except DuplicateKeyError:
                receipt = receipts.find_one(receipt_query)
                if not receipt or receipt.get("request_fingerprint") != fingerprint:
                    raise APIError("Goods receipt conflicts with an existing receipt record.", 409, "purchase_receipt_conflict")

        receipt = receipts.find_one(receipt_query) or receipt
        receipt_lines_state = receipt.get("lines") or []
        receipt["status"] = "processing"
        receipt["updated_at"] = now_utc()
        receipts.update_one({"_id": receipt["_id"], "business_id": business_id}, {"$set": {
            "status": "processing",
            "updated_at": receipt["updated_at"],
        }})

        for index, receipt_line in enumerate(receipt_lines_state):
            if receipt_line.get("status") == "applied":
                continue
            product_id = str(receipt_line.get("product_id") or "")
            movement_key = f"po-receipt:{str(receipt['_id'])}:{product_id}"
            try:
                result = biashara_services.inventory_adjustment(
                    user_id,
                    product_id,
                    {
                        "movement_type": "add",
                        "quantity": receipt_line["quantity"],
                        "reason": f"purchase_order_receipt:{purchase_order_id}",
                        "idempotency_key": movement_key,
                    },
                )
                receipt_line["status"] = "applied"
                receipt_line["movement_id"] = (result.get("movement") or {}).get("id")
                receipt_line["error_code"] = None
                receipt_line["applied_at"] = now_utc()
                receipts.update_one({"_id": receipt["_id"], "business_id": business_id}, {"$set": {
                    "lines": receipt_lines_state,
                    "updated_at": now_utc(),
                }})
            except Exception as error:
                code = error.code if isinstance(error, APIError) else "inventory_receipt_apply_failed"
                receipt_line["status"] = "pending"
                receipt_line["error_code"] = code
                receipts.update_one({"_id": receipt["_id"], "business_id": business_id}, {"$set": {
                    "status": "partial",
                    "lines": receipt_lines_state,
                    "last_error_code": code,
                    "updated_at": now_utc(),
                }})
                log_action(user_id, "biashara.purchase_receipt_interrupted", "purchase_order_receipt", receipt["_id"], {
                    "purchase_order_id": purchase_order_id,
                    "error_code": code,
                    "completed_lines": sum(1 for line in receipt_lines_state if line.get("status") == "applied"),
                })
                return _serialise(receipts.find_one({"_id": receipt["_id"], "business_id": business_id}) or receipt)

        # Apply receipt quantities once, atomically guarded by applied_receipt_ids.
        latest_order = orders.find_one(order_query)
        if not latest_order:
            raise APIError("Purchase order disappeared while receiving stock.", 409, "purchase_order_missing_after_receipt")
        receipt_id = str(receipt["_id"])
        if receipt_id not in (latest_order.get("applied_receipt_ids") or []):
            po_lines = latest_order.get("lines") or []
            index_by_product = {str(line.get("product_id")): idx for idx, line in enumerate(po_lines)}
            increments = {}
            for line in receipt_lines_state:
                po_line_index = index_by_product.get(str(line.get("product_id")))
                if po_line_index is None:
                    raise APIError("Purchase order line changed during receipt.", 409, "purchase_order_line_missing")
                increments[f"lines.{po_line_index}.quantity_received"] = float(line.get("quantity", 0) or 0)
            receipt_event = _dispatch_receipt_event(latest_order, receipt, user_id)
            result = orders.update_one(
                {**order_query, "applied_receipt_ids": {"$ne": receipt_id}},
                {
                    "$inc": increments,
                    "$addToSet": {
                        "applied_receipt_ids": receipt_id,
                        "outbox_event_manifest": receipt_event,
                    },
                    "$set": {"updated_at": now_utc()},
                },
            )
            if not result.matched_count:
                latest_order = orders.find_one(order_query)
                if not latest_order or receipt_id not in (latest_order.get("applied_receipt_ids") or []):
                    raise APIError("Receipt could not be applied to the purchase order. Retry the same Idempotency-Key.", 409, "purchase_receipt_apply_conflict")

        latest_order = orders.find_one(order_query) or latest_order
        order_lines = latest_order.get("lines") or []
        received_values = [
            (_positive_decimal(line.get("quantity_received", 0), "quantity_received", allow_zero=True),
             _positive_decimal(line.get("quantity_ordered"), "quantity_ordered"))
            for line in order_lines
        ]
        if received_values and all(received >= ordered for received, ordered in received_values):
            target_status = "received"
        elif any(received > 0 for received, _ordered in received_values):
            target_status = "partially_received"
        else:
            target_status = "ordered"

        old_status = str(latest_order.get("status") or "ordered")
        if old_status != target_status:
            now = now_utc()
            status_event = _record_event(
                f"purchase-order:{latest_order['_id']}:status:{target_status}:receipt:{receipt_id}",
                "purchase_order.status_changed",
                "purchase_order",
                latest_order["_id"],
                {
                    "status": target_status,
                    "purchase_order_id": str(latest_order["_id"]),
                    "receipt_id": receipt_id,
                    "total_amount_minor": int(latest_order.get("total_amount_minor", 0) or 0),
                    "currency": latest_order.get("currency", "KES"),
                },
                user_id,
                now,
            )
            orders.update_one(
                {**order_query, "status": old_status},
                {
                    "$set": {"status": target_status, "updated_at": now},
                    "$push": {"status_history": {
                        "from": old_status,
                        "to": target_status,
                        "at": now,
                        "actor_user_id": str(user_id),
                    }},
                    "$addToSet": {"outbox_event_manifest": status_event},
                },
            )

        latest_order = orders.find_one(order_query) or latest_order
        completed_at = now_utc()
        receipts.update_one({"_id": receipt["_id"], "business_id": business_id}, {"$set": {
            "status": "completed",
            "completed_at": completed_at,
            "last_error_code": None,
            "lines": receipt_lines_state,
            "updated_at": completed_at,
        }})
        _dispatch_source(PURCHASE_ORDERS_COLLECTION, business_id, latest_order["_id"])
        completed = receipts.find_one({"_id": receipt["_id"], "business_id": business_id}) or receipt
        log_action(user_id, "biashara.purchase_receipt_completed", "purchase_order_receipt", receipt["_id"], {
            "purchase_order_id": purchase_order_id,
            "line_count": len(receipt_lines_state),
            "purchase_order_status": latest_order.get("status"),
        })
        return _serialise(completed)
    finally:
        _release_receiving_lease(purchase_order_id, business_id, lease_token)
