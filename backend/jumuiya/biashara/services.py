# backend/jumuiya/biashara/services.py

import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.audit import log_action

from backend.jumuiya.biashara.website import (
    DEFAULT_BIASHARA_WEBSITE_SETTINGS,
    normalize_biashara_website_settings,
)

from backend.jumuiya.biashara.models import (
    business_document,
    product_document,
    customer_document,
    order_document,
    expense_document,
    sale_document,
    inventory_movement_document,
)


# =========================================================
# HELPERS
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


def clean_id(value):
    """
    Convert a valid MongoDB ObjectId string to ObjectId.

    If the value is not a valid ObjectId, return it unchanged
    so the query simply won't accidentally match another object.
    """

    try:
        return ObjectId(value)

    except (InvalidId, TypeError):
        return value


def serialise(doc):
    """
    Convert MongoDB documents into JSON-safe dictionaries.
    """

    if not doc:
        return None

    out = dict(doc)

    if "_id" in out:
        out["id"] = str(out.pop("_id"))

    for key, value in list(out.items()):

        if isinstance(value, ObjectId):
            out[key] = str(value)

        elif hasattr(value, "isoformat"):
            out[key] = value.isoformat()

    return out


def serialise_many(docs):
    return [
        serialise(doc)
        for doc in docs
    ]


def _bounded_list_limit(value=50):
    """Clamp list sizes even when a service is called without a route validator."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 50
    return min(max(parsed, 1), 100)


# =========================================================
# SLUGS
# =========================================================

def slugify(value):
    value = re.sub(
        r"[^a-zA-Z0-9\s-]",
        "",
        value.lower(),
    )

    value = re.sub(
        r"[\s_-]+",
        "-",
        value,
    )

    return (
        value.strip("-")
        or "business"
    )


def unique_slug(
    name,
    current_id=None,
):
    """
    Generate a unique business slug.
    """

    base = slugify(name)
    slug = base
    number = 2

    businesses = collection(
        "jumuiya_businesses"
    )

    while True:

        query = {
            "slug": slug
        }

        if current_id:
            query["_id"] = {
                "$ne": current_id
            }

        if not businesses.find_one(
            query
        ):
            return slug

        slug = f"{base}-{number}"
        number += 1


# =========================================================
# BUSINESS
# =========================================================

def get_business_for_user(
    user_id,
):
    return serialise(
        collection(
            "jumuiya_businesses"
        ).find_one({
            "owner_user_id": str(
                user_id
            )
        })
    )


def _require_business(user_id):

    business = get_business_for_user(
        user_id
    )

    if not business:

        raise APIError(
            "Create your business profile first.",
            409,
            "business_required",
        )

    return business


def create_or_update_business(
    user_id,
    payload,
):

    businesses = collection(
        "jumuiya_businesses"
    )

    owner_id = str(user_id)

    old = businesses.find_one({
        "owner_user_id": owner_id
    })

    # -----------------------------------------------------
    # UPDATE
    # -----------------------------------------------------

    if old:

        fields = [
            "name",
            "description",
            "phone",
            "email",
            "location",
            "county",
            "category",
            "logo_url",
        ]

        update = {
            key: payload.get(
                key,
                "",
            )
            for key in fields
        }

        update["slug"] = unique_slug(
            payload["name"],
            old["_id"],
        )

        update["updated_at"] = now_utc()

        document = businesses.find_one_and_update(
            {
                "_id": old["_id"]
            },
            {
                "$set": update
            },
            return_document=ReturnDocument.AFTER,
        )

        log_action(
            user_id,
            "business.updated",
            "business",
            document["_id"],
        )

        return serialise(
            document
        )

    # -----------------------------------------------------
    # CREATE
    # -----------------------------------------------------

    document = business_document(
        owner_id,
        payload,
        unique_slug(
            payload["name"]
        ),
    )

    result = businesses.insert_one(
        document
    )

    document["_id"] = result.inserted_id

    log_action(
        user_id,
        "business.created",
        "business",
        result.inserted_id,
    )

    return serialise(
        document
    )


# =========================================================
# PRODUCTS
# =========================================================

def create_product(
    user_id,
    payload,
):

    business = _require_business(
        user_id
    )

    document = product_document(
        business["id"],
        payload,
    )

    result = collection(
        "jumuiya_products"
    ).insert_one(document)

    document["_id"] = result.inserted_id

    log_action(
        user_id,
        "product.created",
        "product",
        result.inserted_id,
    )

    return serialise(
        document
    )


def list_products(
    user_id,
    status=None,
    category=None,
    search=None,
    limit=50,
):
    """List this business's products with filtering and a bounded limit."""
    business = _require_business(user_id)
    query = {"business_id": business["id"]}

    if status:
        query["status"] = status
    if category:
        query["category"] = category

    search_text = str(search or "").strip()
    if search_text:
        expression = {"$regex": re.escape(search_text), "$options": "i"}
        query["$or"] = [
            {"name": expression},
            {"sku": expression},
            {"category": expression},
        ]

    documents = (
        collection("jumuiya_products")
        .find(query)
        .sort("created_at", -1)
        .limit(_bounded_list_limit(limit))
    )
    return serialise_many(documents)



def update_product(user_id, product_id, payload):
    business = _require_business(user_id)
    allowed = {
        "name", "description", "category", "sku", "price", "currency",
        "stock_quantity", "unit", "image_url", "status",
    }
    update = {key: payload[key] for key in allowed if key in payload}
    if not update:
        raise APIError("No product fields were provided.", 422, "empty_update")

    products = collection("jumuiya_products")
    query = {"_id": clean_id(product_id), "business_id": business["id"]}
    current = products.find_one(query)
    if not current:
        raise APIError("Product not found.", 404, "product_not_found")

    if "stock_quantity" in update:
        try:
            target_stock = Decimal(str(update["stock_quantity"]))
            reserved_stock = Decimal(str(current.get("reserved_quantity", 0) or 0))
            current_stock = Decimal(str(current.get("stock_quantity", 0) or 0))
        except (InvalidOperation, TypeError, ValueError):
            raise APIError("Stock quantity must be a valid number.", 422, "invalid_stock_quantity")
        if not target_stock.is_finite() or target_stock < 0:
            raise APIError("Stock quantity must be a non-negative finite number.", 422, "invalid_stock_quantity")
        if target_stock < reserved_stock:
            raise APIError(
                "Stock cannot be set below the quantity reserved by open orders. Cancel or fulfil reservations first.",
                409,
                "stock_below_reserved",
            )
        # Compare-and-set prevents a stock edit from overwriting a concurrent
        # order reservation. Other metadata edits remain independent.
        query["stock_quantity"] = current.get("stock_quantity", 0)
        if "reserved_quantity" in current:
            query["reserved_quantity"] = current["reserved_quantity"]
        else:
            query["reserved_quantity"] = {"$exists": False}

    document = products.find_one_and_update(
        query,
        {"$set": {**update, "updated_at": now_utc()}},
        return_document=ReturnDocument.AFTER,
    )
    if not document:
        if "stock_quantity" in update:
            raise APIError(
                "Inventory changed while this product was being edited. Reload and retry.",
                409,
                "inventory_concurrent_update",
            )
        raise APIError("Product not found.", 404, "product_not_found")

    log_action(user_id, "product.updated", "product", document["_id"])
    return serialise(document)

def delete_product(
    user_id,
    product_id,
):

    business = _require_business(
        user_id
    )

    products = collection(
        "jumuiya_products"
    )

    document = products.find_one_and_update(
        {
            "_id": clean_id(
                product_id
            ),
            "business_id": business["id"],
        },
        {
            "$set": {
                "status": "deleted",
                "updated_at": now_utc(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:

        raise APIError(
            "Product not found.",
            404,
            "product_not_found",
        )

    log_action(
        user_id,
        "product.deleted",
        "product",
        document["_id"],
    )

    return serialise(
        document
    )


# =========================================================
# INVENTORY
# =========================================================

def low_stock(
    user_id,
    threshold=5,
):

    business = _require_business(
        user_id
    )

    try:
        threshold = float(
            threshold
        )

    except (
        TypeError,
        ValueError,
    ):

        raise APIError(
            "threshold must be a number.",
            422,
            "invalid_threshold",
        )

    if threshold < 0:

        raise APIError(
            "threshold cannot be negative.",
            422,
            "invalid_threshold",
        )

    documents = collection(
        "jumuiya_products"
    ).find({
        "business_id": business["id"],
        "status": "active",
        "$expr": {
            "$lte": [
                {
                    "$subtract": [
                        {"$ifNull": ["$stock_quantity", 0]},
                        {"$ifNull": ["$reserved_quantity", 0]},
                    ]
                },
                threshold,
            ]
        },
    }).sort(
        "stock_quantity",
        1,
    )

    rows = list(documents)
    for row in rows:
        try:
            row["available_quantity"] = max(
                float(row.get("stock_quantity", 0) or 0)
                - float(row.get("reserved_quantity", 0) or 0),
                0,
            )
        except (TypeError, ValueError):
            row["available_quantity"] = 0
    return serialise_many(rows)



def inventory_adjustment(user_id, product_id, payload):
    """Compare-and-set stock adjustment that never consumes reserved units."""
    business = _require_business(user_id)
    products = collection("jumuiya_products")
    product_query = {
        "_id": clean_id(product_id),
        "business_id": business["id"],
    }
    product = products.find_one(product_query)
    if not product:
        raise APIError("Product not found.", 404, "product_not_found")

    try:
        previous_stock = Decimal(str(product.get("stock_quantity", 0) or 0))
        reserved_stock = Decimal(str(product.get("reserved_quantity", 0) or 0))
        quantity = Decimal(str(payload["quantity"]))
    except (InvalidOperation, TypeError, ValueError, KeyError):
        raise APIError("Stock quantities must be valid numbers.", 422, "invalid_stock_quantity")
    if (
        not previous_stock.is_finite()
        or not reserved_stock.is_finite()
        or not quantity.is_finite()
        or previous_stock < 0
        or reserved_stock < 0
        or reserved_stock > previous_stock
        or quantity <= 0
    ):
        raise APIError("Product inventory state or adjustment quantity is invalid.", 422, "invalid_stock_quantity")

    movement_type = payload.get("movement_type")
    if movement_type == "add":
        new_stock = previous_stock + quantity
    elif movement_type == "remove":
        available_stock = previous_stock - reserved_stock
        if quantity > available_stock:
            raise APIError(
                "Insufficient available stock. Some units are reserved for open orders.",
                409,
                "insufficient_stock",
            )
        new_stock = previous_stock - quantity
    elif movement_type == "set":
        if quantity < reserved_stock:
            raise APIError(
                "Stock cannot be set below the quantity reserved by open orders.",
                409,
                "stock_below_reserved",
            )
        new_stock = quantity
    else:
        raise APIError("Invalid inventory movement.", 422, "invalid_movement")

    filter_doc = {
        **product_query,
        "stock_quantity": product.get("stock_quantity", 0),
    }
    if "reserved_quantity" in product:
        filter_doc["reserved_quantity"] = product["reserved_quantity"]
    else:
        filter_doc["reserved_quantity"] = {"$exists": False}

    updated = products.find_one_and_update(
        filter_doc,
        {
            "$set": {
                "stock_quantity": float(new_stock),
                "updated_at": now_utc(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise APIError(
            "Inventory changed while this adjustment was being saved. Reload and retry.",
            409,
            "inventory_concurrent_update",
        )

    movement_payload = {
        **payload,
        "quantity": float(quantity),
        "reason": str(payload.get("reason") or "manual_adjustment"),
    }
    movement = inventory_movement_document(
        business["id"],
        product["_id"],
        movement_payload,
        float(previous_stock - reserved_stock),
        float(new_stock - reserved_stock),
    )
    movement["actor_user_id"] = str(user_id)
    movement["source"] = "manual_adjustment"
    movement_result = collection("jumuiya_inventory_movements").insert_one(movement)
    movement["_id"] = movement_result.inserted_id

    log_action(user_id, "inventory.adjusted", "product", product["_id"], {
        "movement_type": movement_type,
        "quantity": float(quantity),
    })
    return {
        "product": serialise(updated),
        "movement": serialise(movement),
    }


# =========================================================
# CUSTOMERS
# =========================================================

def create_customer(
    user_id,
    payload,
):

    business = _require_business(
        user_id
    )

    document = customer_document(
        business["id"],
        payload,
    )

    result = collection(
        "jumuiya_customers"
    ).insert_one(document)

    document["_id"] = (
        result.inserted_id
    )

    log_action(
        user_id,
        "customer.created",
        "customer",
        result.inserted_id,
    )

    return serialise(
        document
    )


def list_customers(
    user_id,
    search=None,
    limit=50,
):
    """List this business's customers with search and bounded pagination."""
    business = _require_business(user_id)
    query = {"business_id": business["id"]}

    search_text = str(search or "").strip()
    if search_text:
        expression = {"$regex": re.escape(search_text), "$options": "i"}
        query["$or"] = [
            {"name": expression},
            {"phone": expression},
            {"email": expression},
        ]

    documents = (
        collection("jumuiya_customers")
        .find(query)
        .sort("created_at", -1)
        .limit(_bounded_list_limit(limit))
    )
    return serialise_many(documents)


# =========================================================
# ORDERS
# =========================================================



def _order_fingerprint(payload):
    """Stable fingerprint of customer intent, excluding client prices/totals."""
    items = []
    for item in payload.get("items", []):
        quantity = Decimal(str(item.get("quantity", 0)))
        items.append({
            "product_id": str(item.get("product_id") or ""),
            "quantity": format(quantity.normalize(), "f"),
        })
    canonical = {
        "customer_id": str(payload.get("customer_id") or ""),
        "items": items,
        "notes": str(payload.get("notes") or "").strip(),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _order_quantities(order):
    quantities = {}
    for item in order.get("items", []):
        product_id = str(item.get("product_id") or "")
        try:
            quantity = Decimal(str(item.get("quantity")))
        except (InvalidOperation, TypeError, ValueError):
            raise APIError("Stored order quantity is invalid.", 409, "invalid_order_inventory")
        if not product_id or not quantity.is_finite() or quantity <= 0:
            raise APIError("Stored order item is invalid.", 409, "invalid_order_inventory")
        quantities[product_id] = quantities.get(product_id, Decimal("0")) + quantity
    return quantities


def _reservation_for(product, order_id):
    for reservation in product.get("active_reservations", []) or []:
        if str(reservation.get("order_id")) == str(order_id):
            return reservation
    return None


def _inventory_movement_key(order_id, product_id, operation):
    return f"biashara:order:{order_id}:{operation}:{product_id}"


def _ensure_order_movement(
    business_id,
    user_id,
    order_id,
    product_id,
    operation,
    movement_type,
    reason,
    quantity,
    previous_quantity,
    new_quantity,
):
    """Persist a uniquely-keyed inventory fact; safe to call during recovery."""
    movements = collection("jumuiya_inventory_movements")
    key = _inventory_movement_key(order_id, product_id, operation)
    existing = movements.find_one({
        "business_id": str(business_id),
        "idempotency_key": key,
    })
    if existing:
        return existing

    document = inventory_movement_document(
        str(business_id),
        clean_id(product_id),
        {
            "movement_type": movement_type,
            "quantity": float(quantity),
            "reason": reason,
        },
        float(previous_quantity),
        float(new_quantity),
    )
    document.update({
        "idempotency_key": key,
        "order_id": str(order_id),
        "actor_user_id": str(user_id),
        "source": "order_lifecycle",
    })
    try:
        result = movements.insert_one(document)
        document["_id"] = result.inserted_id
        return document
    except DuplicateKeyError:
        existing = movements.find_one({
            "business_id": str(business_id),
            "idempotency_key": key,
        })
        if existing:
            return existing
        raise


def _ensure_reservation_movement(business_id, user_id, order_id, product_id, reservation):
    return _ensure_order_movement(
        business_id=business_id,
        user_id=user_id,
        order_id=order_id,
        product_id=product_id,
        operation="reserve",
        movement_type="remove",
        reason="order_reservation",
        quantity=reservation["quantity"],
        previous_quantity=reservation["previous_available_quantity"],
        new_quantity=reservation["new_available_quantity"],
    )


def _release_order_inventory(order, user_id, allow_missing=False):
    """Release open-order reservations exactly once and recover interrupted releases."""
    business_id = str(order["business_id"])
    order_id = str(order.get("_id") or order.get("id"))
    products = collection("jumuiya_products")
    movements = collection("jumuiya_inventory_movements")

    for product_id, quantity in _order_quantities(order).items():
        release_key = _inventory_movement_key(order_id, product_id, "release")
        consume_key = _inventory_movement_key(order_id, product_id, "consume")
        while True:
            product = products.find_one({
                "_id": clean_id(product_id),
                "business_id": business_id,
            })
            if not product:
                if movements.find_one({"business_id": business_id, "idempotency_key": release_key}):
                    break
                if allow_missing:
                    break
                raise APIError(
                    "A reserved product is missing; inventory needs reconciliation.",
                    409,
                    "inventory_reservation_missing",
                )

            reservation = _reservation_for(product, order_id)
            if reservation is None:
                if movements.find_one({"business_id": business_id, "idempotency_key": release_key}):
                    break
                if movements.find_one({"business_id": business_id, "idempotency_key": consume_key}):
                    raise APIError(
                        "Stock has already been consumed by this order and cannot be released as a cancellation.",
                        409,
                        "order_inventory_consumed",
                    )
                if allow_missing or order.get("inventory_status") in {None, "", "not_reserved", "reservation_failed", "reservation_pending"}:
                    break
                raise APIError(
                    "The order reservation marker is missing; inventory needs reconciliation.",
                    409,
                    "inventory_reservation_missing",
                )

            state = reservation.get("state", "reserved")
            if state == "consumed":
                raise APIError(
                    "Stock has already been consumed by this order and cannot be released as a cancellation.",
                    409,
                    "order_inventory_consumed",
                )

            if state == "released":
                _ensure_order_movement(
                    business_id, user_id, order_id, product_id, "release", "add",
                    "order_cancelled", reservation["quantity"],
                    reservation["release_previous_available_quantity"],
                    reservation["release_new_available_quantity"],
                )
                products.update_one(
                    {"_id": product["_id"], "business_id": business_id},
                    {"$pull": {"active_reservations": {"order_id": order_id}}},
                )
                break

            try:
                stock = Decimal(str(product.get("stock_quantity", 0) or 0))
                reserved = Decimal(str(product.get("reserved_quantity", 0) or 0))
            except (InvalidOperation, TypeError, ValueError):
                raise APIError("Product inventory state is invalid.", 409, "invalid_inventory_state")
            if not stock.is_finite() or not reserved.is_finite() or reserved < quantity:
                raise APIError("Reserved inventory is inconsistent and needs reconciliation.", 409, "invalid_inventory_state")

            previous_available = stock - reserved
            new_reserved = reserved - quantity
            new_available = stock - new_reserved
            now = now_utc()
            updated = products.find_one_and_update(
                {
                    "_id": product["_id"],
                    "business_id": business_id,
                    "stock_quantity": product.get("stock_quantity", 0),
                    "reserved_quantity": product.get("reserved_quantity", 0),
                    "active_reservations": {
                        "$elemMatch": {"order_id": order_id, "state": "reserved"}
                    },
                },
                {
                    "$inc": {"reserved_quantity": -float(quantity)},
                    "$set": {
                        "updated_at": now,
                        "active_reservations.$[reservation].state": "released",
                        "active_reservations.$[reservation].release_previous_available_quantity": float(previous_available),
                        "active_reservations.$[reservation].release_new_available_quantity": float(new_available),
                        "active_reservations.$[reservation].released_at": now,
                    },
                },
                array_filters=[{"reservation.order_id": order_id, "reservation.state": "reserved"}],
                return_document=ReturnDocument.AFTER,
            )
            if not updated:
                continue

            updated_reservation = _reservation_for(updated, order_id)
            if not updated_reservation:
                raise APIError("Reservation release needs reconciliation.", 409, "inventory_reservation_missing")
            _ensure_order_movement(
                business_id, user_id, order_id, product_id, "release", "add",
                "order_cancelled", quantity,
                updated_reservation["release_previous_available_quantity"],
                updated_reservation["release_new_available_quantity"],
            )
            products.update_one(
                {"_id": product["_id"], "business_id": business_id},
                {"$pull": {"active_reservations": {"order_id": order_id}}},
            )
            break

    collection("jumuiya_orders").update_one(
        {"_id": clean_id(order_id), "business_id": business_id},
        {"$set": {"inventory_status": "released", "inventory_released_at": now_utc()}},
    )


def _reserve_order_inventory(order, user_id):
    """Reserve available stock with compare-and-set writes and crash-recoverable markers."""
    business_id = str(order["business_id"])
    order_id = str(order.get("_id") or order.get("id"))
    products = collection("jumuiya_products")
    quantities = _order_quantities(order)

    for product_id, quantity in quantities.items():
        reserved_done = False
        for _attempt in range(12):
            product = products.find_one({
                "_id": clean_id(product_id),
                "business_id": business_id,
            })
            if not product:
                raise APIError("One or more products are no longer available.", 422, "invalid_product")

            reservation = _reservation_for(product, order_id)
            if reservation:
                state = reservation.get("state", "reserved")
                if state == "reserved":
                    _ensure_reservation_movement(business_id, user_id, order_id, product_id, reservation)
                    reserved_done = True
                    break
                if state == "consumed":
                    # A duplicate request after fulfilment must not reserve again.
                    reserved_done = True
                    break
                if state == "released":
                    raise APIError("This order's inventory reservation was already released.", 409, "order_inventory_released")

            if product.get("status", "active") != "active":
                raise APIError("One or more products are no longer available.", 422, "invalid_product")

            try:
                stock = Decimal(str(product.get("stock_quantity", 0) or 0))
                reserved = Decimal(str(product.get("reserved_quantity", 0) or 0))
            except (InvalidOperation, TypeError, ValueError):
                raise APIError("Product inventory state is invalid.", 409, "invalid_inventory_state")
            if not stock.is_finite() or not reserved.is_finite() or stock < 0 or reserved < 0 or reserved > stock:
                raise APIError("Product inventory state is inconsistent.", 409, "invalid_inventory_state")

            available = stock - reserved
            if available < quantity:
                raise APIError(
                    f"Insufficient available stock for {product.get('name', 'product')}.",
                    409,
                    "insufficient_stock",
                )

            new_reserved = reserved + quantity
            now = now_utc()
            marker = {
                "order_id": order_id,
                "quantity": float(quantity),
                "state": "reserved",
                "previous_available_quantity": float(available),
                "new_available_quantity": float(stock - new_reserved),
                "previous_reserved_quantity": float(reserved),
                "new_reserved_quantity": float(new_reserved),
                "reserved_at": now,
            }
            filter_doc = {
                "_id": product["_id"],
                "business_id": business_id,
                "status": "active",
                "stock_quantity": product.get("stock_quantity", 0),
                "active_reservations.order_id": {"$ne": order_id},
            }
            if "reserved_quantity" in product:
                filter_doc["reserved_quantity"] = product["reserved_quantity"]
            else:
                filter_doc["reserved_quantity"] = {"$exists": False}

            updated = products.find_one_and_update(
                filter_doc,
                {
                    "$inc": {"reserved_quantity": float(quantity)},
                    "$set": {"updated_at": now},
                    "$addToSet": {"active_reservations": marker},
                },
                return_document=ReturnDocument.AFTER,
            )
            if updated:
                saved_marker = _reservation_for(updated, order_id)
                if not saved_marker:
                    raise APIError("Inventory reservation needs reconciliation.", 409, "inventory_reservation_missing")
                _ensure_reservation_movement(business_id, user_id, order_id, product_id, saved_marker)
                reserved_done = True
                break

        if not reserved_done:
            # Re-check after bounded compare-and-set retries; never overbook stock.
            raise APIError(
                "Inventory changed while reserving this order. Retry with the same idempotency key.",
                409,
                "inventory_reservation_conflict",
            )

    current = collection("jumuiya_orders").find_one({
        "_id": clean_id(order_id),
        "business_id": business_id,
    })
    if not current:
        raise APIError("Order record disappeared during reservation.", 409, "order_reservation_missing")
    if current.get("status") not in {"pending", "confirmed"}:
        _release_order_inventory(current, user_id, allow_missing=True)
        raise APIError("The order changed while inventory was being reserved.", 409, "order_state_conflict")

    collection("jumuiya_orders").update_one(
        {"_id": clean_id(order_id), "business_id": business_id, "status": {"$in": ["pending", "confirmed"]}},
        {"$set": {"inventory_status": "reserved", "reserved_at": now_utc()}},
    )


def _fail_order_reservation(order, user_id, error):
    order_id = str(order.get("_id") or order.get("id"))
    business_id = str(order["business_id"])
    try:
        _release_order_inventory(order, user_id, allow_missing=True)
        collection("jumuiya_orders").update_one(
            {"_id": clean_id(order_id), "business_id": business_id, "status": "pending"},
            {
                "$set": {
                    "status": "cancelled",
                    "inventory_status": "reservation_failed",
                    "cancellation_reason": "inventory_reservation_failed",
                    "cancelled_at": now_utc(),
                    "updated_at": now_utc(),
                },
                "$push": {
                    "status_history": {
                        "from": "pending",
                        "to": "cancelled",
                        "at": now_utc().isoformat(),
                        "actor_user_id": str(user_id),
                        "reason": "inventory_reservation_failed",
                    }
                },
            },
        )
    except Exception:
        # Preserve the failed reservation record for operator recovery; never
        # silently claim the stock was released if compensation did not finish.
        collection("jumuiya_orders").update_one(
            {"_id": clean_id(order_id), "business_id": business_id},
            {"$set": {
                "inventory_status": "release_reconciliation_required",
                "inventory_reconciliation_required_at": now_utc(),
            }},
        )
        log_action(
            user_id,
            "inventory.reservation_reconciliation_required",
            "order",
            order_id,
            {"error_code": getattr(error, "code", "reservation_failed")},
        )


def create_order(user_id, payload):
    """Create an order with catalogue-authoritative pricing and recoverable stock reservation."""
    business = _require_business(user_id)
    customer_id = payload.get("customer_id")
    if customer_id:
        customer = collection("jumuiya_customers").find_one({
            "_id": clean_id(customer_id),
            "business_id": business["id"],
        })
        if not customer:
            raise APIError("Customer does not belong to this business.", 422, "invalid_customer")

    submitted_items = payload.get("items")
    if not isinstance(submitted_items, list) or not submitted_items:
        raise APIError("An order must contain at least one item.", 422, "invalid_order_items")

    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if idempotency_key and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", idempotency_key):
        raise APIError("Idempotency-Key must be 8–128 safe characters.", 422, "invalid_idempotency_key")

    fingerprint = _order_fingerprint(payload)
    orders = collection("jumuiya_orders")
    if idempotency_key:
        existing = orders.find_one({
            "business_id": str(business["id"]),
            "idempotency_key": idempotency_key,
        })
        if existing:
            if existing.get("request_fingerprint") != fingerprint:
                raise APIError(
                    "This Idempotency-Key was already used for a different order payload.",
                    409,
                    "idempotency_key_reused",
                )
            if existing.get("inventory_status") == "reservation_pending" and existing.get("status") in {"pending", "confirmed"}:
                try:
                    _reserve_order_inventory(existing, user_id)
                except APIError as error:
                    _fail_order_reservation(existing, user_id, error)
                    raise
                existing = orders.find_one({"_id": existing["_id"], "business_id": str(business["id"])}) or existing
            if existing.get("inventory_status") in {"reservation_failed", "release_reconciliation_required"}:
                raise APIError(
                    "This order's stock reservation did not complete. Review the order before creating another request.",
                    409,
                    "order_reservation_failed",
                )
            return serialise(existing)

    currency = str(business.get("currency") or "KES").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        currency = "KES"

    product_cache = {}
    quantities = {}
    priced_items = []
    subtotal = Decimal("0.00")
    for index, item in enumerate(submitted_items):
        if not isinstance(item, dict):
            raise APIError(f"Order item {index + 1} must be an object.", 422, "invalid_order_items")
        product_id = str(item.get("product_id") or "")
        if not product_id:
            raise APIError(f"Order item {index + 1} requires a product.", 422, "invalid_order_items")
        product = product_cache.get(product_id)
        if product is None:
            product = collection("jumuiya_products").find_one({
                "_id": clean_id(product_id),
                "business_id": str(business["id"]),
                "status": "active",
            })
            if not product:
                raise APIError("One or more products are no longer available.", 422, "invalid_product")
            product_cache[product_id] = product

        try:
            quantity = Decimal(str(item.get("quantity")))
            unit_price = Decimal(str(product.get("price", 0)))
        except (InvalidOperation, TypeError, ValueError):
            raise APIError("Order quantity or catalogue price is invalid.", 422, "invalid_order_amount")
        if not quantity.is_finite() or quantity <= 0:
            raise APIError("Order quantities must be positive finite numbers.", 422, "invalid_order_quantity")
        if not unit_price.is_finite() or unit_price < 0:
            raise APIError(f"Catalogue price for {product.get('name', 'product')} is invalid.", 409, "invalid_catalogue_price")
        if str(product.get("currency") or currency).upper() != currency:
            raise APIError("All products in one order must use the business currency.", 422, "mixed_order_currency")

        rounded_price = unit_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        line_total = (rounded_price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        subtotal += line_total
        quantities[product_id] = quantities.get(product_id, Decimal("0")) + quantity
        priced_items.append({
            "product_id": str(product.get("_id")),
            "name": str(product.get("name") or "Product")[:160],
            "sku": str(product.get("sku") or "")[:80],
            "quantity": float(quantity),
            "unit_price": float(rounded_price),
            "unit_price_minor": int(rounded_price * 100),
            "line_total": float(line_total),
            "line_total_minor": int(line_total * 100),
            "currency": currency,
        })

    subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    now = now_utc()
    trusted_payload = {
        "customer_id": str(customer_id) if customer_id else None,
        "items": priced_items,
        "subtotal": float(subtotal),
        "discount": 0,
        "total_amount": float(subtotal),
        "currency": currency,
        "notes": str(payload.get("notes") or "")[:1000],
        "status": "pending",
        "payment_status": "unpaid",
    }
    document = order_document(str(business["id"]), trusted_payload)
    document.update({
        "_id": ObjectId(),
        "subtotal_minor": int(subtotal * 100),
        "total_amount_minor": int(subtotal * 100),
        "currency": currency,
        "source_channel": str(payload.get("source_channel") or "manual"),
        "inventory_status": "reservation_pending",
        "inventory_reserved_quantity": {key: float(value) for key, value in quantities.items()},
        "request_fingerprint": fingerprint,
        "status_history": [{
            "from": None,
            "to": "pending",
            "at": now.isoformat(),
            "actor_user_id": str(user_id),
        }],
    })
    if idempotency_key:
        document["idempotency_key"] = idempotency_key

    try:
        orders.insert_one(document)
    except DuplicateKeyError:
        if idempotency_key:
            existing = orders.find_one({
                "business_id": str(business["id"]),
                "idempotency_key": idempotency_key,
            })
            if existing and existing.get("request_fingerprint") == fingerprint:
                return create_order(user_id, {**payload, "idempotency_key": idempotency_key})
            if existing:
                raise APIError("Idempotency-Key was reused for a different order.", 409, "idempotency_key_reused")
        raise

    log_action(user_id, "order.created", "order", document["_id"], {"source_channel": document["source_channel"]})
    try:
        _reserve_order_inventory(document, user_id)
    except APIError as error:
        _fail_order_reservation(document, user_id, error)
        raise

    saved = orders.find_one({"_id": document["_id"], "business_id": str(business["id"])}) or document
    log_action(user_id, "inventory.order_reserved", "order", document["_id"])
    return serialise(saved)

def list_orders(
    user_id,
    status=None,
    limit=50,
):
    """List this business's orders with optional status and bounded limit."""
    business = _require_business(user_id)
    query = {"business_id": business["id"]}

    if status:
        query["status"] = status

    documents = (
        collection("jumuiya_orders")
        .find(query)
        .sort("created_at", -1)
        .limit(_bounded_list_limit(limit))
    )
    return serialise_many(documents)


def get_order(
    user_id,
    order_id,
):

    business = _require_business(
        user_id
    )

    document = collection(
        "jumuiya_orders"
    ).find_one({
        "_id": clean_id(
            order_id
        ),
        "business_id": business["id"],
    })

    if not document:

        raise APIError(
            "Order not found.",
            404,
            "order_not_found",
        )

    return serialise(
        document
    )



def _consume_order_inventory(order, user_id):
    """Convert reserved units into sold/on-hand stock exactly once."""
    business_id = str(order["business_id"])
    order_id = str(order.get("_id") or order.get("id"))
    products = collection("jumuiya_products")
    movements = collection("jumuiya_inventory_movements")
    quantities = _order_quantities(order)

    # Legacy orders created before reservations existed are reserved now before
    # processing. This prevents old records from bypassing stock validation.
    has_reservation = False
    for product_id in quantities:
        product = products.find_one({"_id": clean_id(product_id), "business_id": business_id})
        if product and _reservation_for(product, order_id):
            has_reservation = True
            break
    if not has_reservation and order.get("inventory_status") in {None, "", "not_reserved"}:
        _reserve_order_inventory(order, user_id)
        order = collection("jumuiya_orders").find_one({
            "_id": clean_id(order_id),
            "business_id": business_id,
        }) or order

    for product_id, quantity in quantities.items():
        consume_key = _inventory_movement_key(order_id, product_id, "consume")
        done = False
        for _attempt in range(12):
            product = products.find_one({
                "_id": clean_id(product_id),
                "business_id": business_id,
            })
            if not product:
                if movements.find_one({"business_id": business_id, "idempotency_key": consume_key}):
                    done = True
                    break
                raise APIError("Reserved product is missing; inventory needs reconciliation.", 409, "inventory_reservation_missing")

            reservation = _reservation_for(product, order_id)
            if reservation is None:
                if movements.find_one({"business_id": business_id, "idempotency_key": consume_key}):
                    done = True
                    break
                raise APIError("Order stock reservation is missing; inventory needs reconciliation.", 409, "inventory_reservation_missing")

            state = reservation.get("state", "reserved")
            if state == "released":
                raise APIError("Order stock reservation has already been released.", 409, "order_inventory_released")
            if state == "consumed":
                _ensure_order_movement(
                    business_id, user_id, order_id, product_id, "consume", "remove",
                    "order_fulfilled", reservation["quantity"],
                    reservation["consumption_previous_stock_quantity"],
                    reservation["consumption_new_stock_quantity"],
                )
                products.update_one(
                    {"_id": product["_id"], "business_id": business_id},
                    {"$pull": {"active_reservations": {"order_id": order_id}}},
                )
                done = True
                break

            try:
                stock = Decimal(str(product.get("stock_quantity", 0) or 0))
                reserved = Decimal(str(product.get("reserved_quantity", 0) or 0))
            except (InvalidOperation, TypeError, ValueError):
                raise APIError("Product inventory state is invalid.", 409, "invalid_inventory_state")
            if not stock.is_finite() or not reserved.is_finite() or stock < quantity or reserved < quantity:
                raise APIError("Reserved inventory is inconsistent and needs reconciliation.", 409, "invalid_inventory_state")

            new_stock = stock - quantity
            new_reserved = reserved - quantity
            now = now_utc()
            updated = products.find_one_and_update(
                {
                    "_id": product["_id"],
                    "business_id": business_id,
                    "stock_quantity": product.get("stock_quantity", 0),
                    "reserved_quantity": product.get("reserved_quantity", 0),
                    "active_reservations": {
                        "$elemMatch": {"order_id": order_id, "state": "reserved"}
                    },
                },
                {
                    "$inc": {
                        "stock_quantity": -float(quantity),
                        "reserved_quantity": -float(quantity),
                    },
                    "$set": {
                        "updated_at": now,
                        "active_reservations.$[reservation].state": "consumed",
                        "active_reservations.$[reservation].consumption_previous_stock_quantity": float(stock),
                        "active_reservations.$[reservation].consumption_new_stock_quantity": float(new_stock),
                        "active_reservations.$[reservation].consumption_previous_available_quantity": float(stock - reserved),
                        "active_reservations.$[reservation].consumption_new_available_quantity": float(new_stock - new_reserved),
                        "active_reservations.$[reservation].consumed_at": now,
                    },
                },
                array_filters=[{"reservation.order_id": order_id, "reservation.state": "reserved"}],
                return_document=ReturnDocument.AFTER,
            )
            if not updated:
                continue

            saved_reservation = _reservation_for(updated, order_id)
            if not saved_reservation:
                raise APIError("Stock consumption needs reconciliation.", 409, "inventory_reservation_missing")
            _ensure_order_movement(
                business_id, user_id, order_id, product_id, "consume", "remove",
                "order_fulfilled", quantity,
                saved_reservation["consumption_previous_stock_quantity"],
                saved_reservation["consumption_new_stock_quantity"],
            )
            products.update_one(
                {"_id": product["_id"], "business_id": business_id},
                {"$pull": {"active_reservations": {"order_id": order_id}}},
            )
            done = True
            break

        if not done:
            raise APIError(
                "Inventory changed while fulfilling this order. Retry the same status update.",
                409,
                "inventory_consumption_conflict",
            )

    collection("jumuiya_orders").update_one(
        {"_id": clean_id(order_id), "business_id": business_id, "status": "confirmed"},
        {"$set": {"inventory_status": "consumed", "inventory_consumed_at": now_utc()}},
    )


def update_order_status(user_id, order_id, status):
    """Apply legal order transitions and make stock effects recoverable."""
    transitions = {
        "pending": {"confirmed", "cancelled"},
        "confirmed": {"processing", "cancelled"},
        "processing": {"completed"},
        "completed": set(),
        "cancelled": set(),
    }
    if not isinstance(status, str) or status not in transitions:
        raise APIError("Invalid order status.", 422, "invalid_order_status")

    business = _require_business(user_id)
    orders = collection("jumuiya_orders")
    document = orders.find_one({
        "_id": clean_id(order_id),
        "business_id": business["id"],
    })
    if not document:
        raise APIError("Order not found.", 404, "order_not_found")

    previous_status = str(document.get("status") or "pending").lower()
    if previous_status == status:
        return serialise(document)
    if status not in transitions.get(previous_status, set()):
        raise APIError(
            f"Order cannot move from {previous_status} to {status}.",
            409,
            "invalid_order_transition",
        )

    order_id_string = str(document.get("_id") or document.get("id"))
    if status == "processing":
        _consume_order_inventory(document, user_id)
    elif status == "cancelled":
        _release_order_inventory(document, user_id)

    now = now_utc()
    update = {"status": status, "updated_at": now}
    if status == "completed":
        update["completed_at"] = now
    elif status == "cancelled":
        update["cancelled_at"] = now

    event = {
        "from": previous_status,
        "to": status,
        "at": now.isoformat(),
        "actor_user_id": str(user_id),
    }
    updated = orders.find_one_and_update(
        {
            "_id": document["_id"],
            "business_id": business["id"],
            "status": previous_status,
        },
        {
            "$set": update,
            "$push": {"status_history": event},
        },
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        # Inventory operations are idempotent, so a retry can complete the
        # state transition without decrementing or releasing stock twice.
        latest = orders.find_one({"_id": document["_id"], "business_id": business["id"]})
        if latest and latest.get("status") == status:
            return serialise(latest)
        raise APIError(
            "The order changed while this update was being saved. Reload and retry.",
            409,
            "order_state_conflict",
        )

    log_action(user_id, "order.status_updated", "order", order_id_string, {
        "from": previous_status,
        "to": status,
        "inventory_status": updated.get("inventory_status"),
    })
    return serialise(updated)


# =========================================================
# SALES
# =========================================================

def record_sale(
    user_id,
    payload,
):

    business = _require_business(
        user_id
    )

    # -----------------------------------------------------
    # Validate customer
    # -----------------------------------------------------

    customer_id = payload.get(
        "customer_id"
    )

    if customer_id:

        customer = collection(
            "jumuiya_customers"
        ).find_one({
            "_id": clean_id(
                customer_id
            ),
            "business_id": business["id"],
        })

        if not customer:

            raise APIError(
                "Customer does not belong to this business.",
                422,
                "invalid_customer",
            )

    # -----------------------------------------------------
    # Validate stock
    # -----------------------------------------------------

    for item in payload.get(
        "items",
        [],
    ):

        product = collection(
            "jumuiya_products"
        ).find_one({
            "_id": clean_id(
                item["product_id"]
            ),
            "business_id": business["id"],
            "status": "active",
        })

        if not product:

            raise APIError(
                "One or more products were not found.",
                422,
                "invalid_product",
            )

        requested = float(
            item["quantity"]
        )

        available = float(
            product.get(
                "stock_quantity",
                0,
            )
        )

        if requested > available:

            raise APIError(
                f"Insufficient stock for {product.get('name', 'product')}.",
                409,
                "insufficient_stock",
            )

    # -----------------------------------------------------
    # Create sale
    # -----------------------------------------------------

    document = sale_document(
        business["id"],
        payload,
    )

    result = collection(
        "jumuiya_sales"
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    # -----------------------------------------------------
    # Deduct inventory
    # -----------------------------------------------------

    for item in payload.get(
        "items",
        [],
    ):

        product_id = clean_id(
            item["product_id"]
        )

        quantity = float(
            item["quantity"]
        )

        product = collection(
            "jumuiya_products"
        ).find_one({
            "_id": product_id,
            "business_id": business["id"],
        })

        if not product:
            continue

        previous_quantity = float(
            product.get(
                "stock_quantity",
                0,
            )
        )

        new_quantity = (
            previous_quantity
            - quantity
        )

        collection(
            "jumuiya_products"
        ).update_one(
            {
                "_id": product_id,
                "business_id": business["id"],
            },
            {
                "$set": {
                    "stock_quantity": new_quantity,
                    "updated_at": now_utc(),
                }
            },
        )

        movement = inventory_movement_document(
            business["id"],
            product_id,
            {
                "movement_type": "remove",
                "quantity": quantity,
                "reason": "sale",
            },
            previous_quantity,
            new_quantity,
        )

        collection(
            "jumuiya_inventory_movements"
        ).insert_one(
            movement
        )

    log_action(
        user_id,
        "sale.created",
        "sale",
        result.inserted_id,
    )

    return serialise(
        document
    )


# =========================================================
# EXPENSES
# =========================================================

def create_expense(
    user_id,
    payload,
):

    business = _require_business(
        user_id
    )

    document = expense_document(
        business["id"],
        payload,
    )

    result = collection(
        "jumuiya_expenses"
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    log_action(
        user_id,
        "expense.created",
        "expense",
        result.inserted_id,
    )

    return serialise(
        document
    )


def list_expenses(
    user_id,
):

    business = _require_business(
        user_id
    )

    documents = (
        collection(
            "jumuiya_expenses"
        )
        .find({
            "business_id": business["id"]
        })
        .sort(
            "spent_at",
            -1,
        )
    )

    return serialise_many(
        documents
    )


# =========================================================
# DASHBOARD
# =========================================================

def dashboard(
    user_id,
):

    business = _require_business(
        user_id
    )

    business_id = business["id"]

    products = collection(
        "jumuiya_products"
    )

    orders = collection(
        "jumuiya_orders"
    )

    sales = collection(
        "jumuiya_sales"
    )

    expenses = collection(
        "jumuiya_expenses"
    )

    customers = collection(
        "jumuiya_customers"
    )

    # -----------------------------------------------------
    # SALES
    # -----------------------------------------------------

    sales_result = list(
        sales.aggregate([
            {
                "$match": {
                    "business_id": business_id
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {
                        "$sum": "$amount"
                    }
                }
            },
        ])
    )

    # -----------------------------------------------------
    # EXPENSES
    # -----------------------------------------------------

    expenses_result = list(
        expenses.aggregate([
            {
                "$match": {
                    "business_id": business_id
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {
                        "$sum": "$amount"
                    }
                }
            },
        ])
    )

    total_sales = (
        float(
            sales_result[0]["total"]
        )
        if sales_result
        else 0.0
    )

    total_expenses = (
        float(
            expenses_result[0]["total"]
        )
        if expenses_result
        else 0.0
    )

    # -----------------------------------------------------
    # COUNTS
    # -----------------------------------------------------

    product_count = products.count_documents({
        "business_id": business_id,
        "status": {
            "$ne": "deleted"
        },
    })

    low_stock_count = products.count_documents({
        "business_id": business_id,
        "status": "active",
        "stock_quantity": {
            "$lte": 5
        },
    })

    customer_count = customers.count_documents({
        "business_id": business_id
    })

    pending_orders = orders.count_documents({
        "business_id": business_id,
        "status": {
            "$in": [
                "pending",
                "confirmed",
                "processing",
            ]
        },
    })

    completed_orders = orders.count_documents({
        "business_id": business_id,
        "status": "completed",
    })

    return {
        "business": business,

        "metrics": {
            "products": product_count,
            "low_stock": low_stock_count,
            "customers": customer_count,
            "pending_orders": pending_orders,
            "completed_orders": completed_orders,

            "sales_total": total_sales,

            "expenses_total": total_expenses,

            "net_estimate": (
                total_sales
                - total_expenses
            ),
        },
    }

# =========================================================
# BUSINESS WEBSITE / PUBLIC STOREFRONT
# =========================================================


def get_biashara_website_settings(user_id):
    business = _require_business(user_id)
    settings = dict(DEFAULT_BIASHARA_WEBSITE_SETTINGS)
    stored = business.get("website")
    if isinstance(stored, dict):
        settings.update(stored)
    return {
        "slug": business.get("slug", ""),
        "url_path": "/b/" + str(business.get("slug", "")),
        "settings": settings,
    }


def save_biashara_website_settings(user_id, payload):
    business = _require_business(user_id)
    now = now_utc()
    current = business.get("website") if isinstance(business.get("website"), dict) else {}
    settings = normalize_biashara_website_settings(payload, current)
    settings["updated_at"] = now.isoformat()
    if settings.get("published"):
        settings["published_at"] = settings.get("published_at") or now.isoformat()
    else:
        settings["published_at"] = None

    collection("jumuiya_businesses").update_one(
        {"_id": clean_id(business["id"]), "owner_user_id": str(user_id)},
        {"$set": {"website": settings, "updated_at": now}},
    )
    log_action(user_id, "business.website_updated", "business", clean_id(business["id"]))
    return {
        "slug": business.get("slug", ""),
        "url_path": "/b/" + str(business.get("slug", "")),
        "settings": settings,
    }


def get_public_biashara_website(slug):
    normalized_slug = str(slug or "").strip().lower()
    if not normalized_slug or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized_slug):
        raise APIError("Business website not found.", 404, "website_not_found")

    business = collection("jumuiya_businesses").find_one({
        "slug": normalized_slug,
        "status": "active",
        "website.published": True,
    })
    if not business:
        raise APIError("Business website not found or not published.", 404, "website_not_found")

    website = business.get("website") if isinstance(business.get("website"), dict) else {}
    public_business = {
        "name": business.get("name", ""),
        "slug": business.get("slug", ""),
        "description": business.get("description", ""),
        "phone": business.get("phone", "") if website.get("contact_enabled", True) is True else "",
        "email": business.get("email", "") if website.get("contact_enabled", True) is True else "",
        "location": business.get("location", ""),
        "county": business.get("county", ""),
        "currency": business.get("currency", "KES") or "KES",
        "logo_url": business.get("logo_url", ""),
    }
    public_website = {
        "headline": website.get("headline") or business.get("name", ""),
        "tagline": website.get("tagline", ""),
        "about": website.get("about") or business.get("description", ""),
        "hero_image_url": website.get("hero_image_url", ""),
        "primary_color": website.get("primary_color", "#1d4ed8"),
        "accent_color": website.get("accent_color", "#0f766e"),
        "seo_title": website.get("seo_title") or business.get("name", ""),
        "seo_description": website.get("seo_description") or business.get("description", ""),
        "whatsapp_number": website.get("whatsapp_number", "") if website.get("contact_enabled", True) is True else "",
        "show_products": website.get("show_products", True) is True,
        "contact_enabled": website.get("contact_enabled", True) is True,
    }

    products = []
    if public_website["show_products"]:
        product_docs = collection("jumuiya_products").find(
            {
                "business_id": str(business["_id"]),
                "status": "active",
            },
            {
                "_id": 1,
                "name": 1,
                "description": 1,
                "category": 1,
                "price": 1,
                "currency": 1,
                "image_url": 1,
                "stock_quantity": 1,
            },
        ).sort("created_at", -1).limit(60)
        for product in product_docs:
            products.append({
                "id": str(product.get("_id", "")),
                "name": product.get("name", ""),
                "description": product.get("description", ""),
                "category": product.get("category", ""),
                "price": product.get("price", 0),
                "currency": product.get("currency") or public_business["currency"],
                "image_url": product.get("image_url", ""),
                "available": (
                    float(product.get("stock_quantity", 0) or 0)
                    - float(product.get("reserved_quantity", 0) or 0)
                ) > 0,
            })

    return {
        "business": public_business,
        "website": public_website,
        "products": products,
    }


def submit_public_biashara_inquiry(slug, payload):
    if not isinstance(payload, dict):
        raise APIError("A JSON request body is required.", 400, "invalid_json")

    # Low-cost honeypot: automated submissions that fill this field are accepted
    # without creating a lead. Production should also enable request rate limits.
    if str(payload.get("website", "")).strip():
        return {"accepted": True}

    normalized_slug = str(slug or "").strip().lower()
    business = collection("jumuiya_businesses").find_one({
        "slug": normalized_slug,
        "status": "active",
        "website.published": True,
        "website.contact_enabled": True,
    })
    if not business:
        raise APIError("Business website not found or contact is disabled.", 404, "website_not_found")

    def text_field(name, limit, required=False):
        value = payload.get(name, "")
        if not isinstance(value, str):
            raise APIError(name.replace("_", " ").capitalize() + " must be text.", 422, "validation_error")
        value = value.strip()
        if required and not value:
            raise APIError(name.replace("_", " ").capitalize() + " is required.", 422, "validation_error")
        if len(value) > limit:
            raise APIError(name.replace("_", " ").capitalize() + " is too long.", 422, "validation_error")
        if "<" in value or ">" in value:
            raise APIError("HTML is not allowed in inquiry fields.", 422, "invalid_inquiry_text")
        return value

    name = text_field("name", 80, True)
    email = text_field("email", 254)
    phone = text_field("phone", 32)
    message = text_field("message", 2000, True)
    if not email and not phone:
        raise APIError("Provide an email address or phone number.", 422, "contact_required")
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise APIError("Enter a valid email address.", 422, "invalid_email")
    if phone and not re.fullmatch(r"[+0-9() .-]{7,32}", phone):
        raise APIError("Enter a valid phone number.", 422, "invalid_phone")

    now = now_utc()
    document = {
        "business_id": str(business["_id"]),
        "owner_user_id": str(business.get("owner_user_id", "")),
        "business_slug": normalized_slug,
        "source": "public_website",
        "name": name,
        "email": email,
        "phone": phone,
        "message": message,
        "status": "new",
        "created_at": now,
        "updated_at": now,
    }
    collection("jumuiya_business_website_inquiries").insert_one(document)
    return {"accepted": True}


def list_biashara_website_inquiries(user_id, limit=30):
    business = _require_business(user_id)
    documents = collection("jumuiya_business_website_inquiries").find(
        {
            "business_id": business["id"],
            "owner_user_id": str(user_id),
        }
    ).sort("created_at", -1).limit(_bounded_list_limit(limit))
    return serialise_many(documents)
