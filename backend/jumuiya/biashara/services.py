# backend/jumuiya/biashara/services.py

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.audit import log_action
from backend.jumuiya.biashara.access import resolve_business_access

from backend.jumuiya.biashara.website import (
    DEFAULT_BIASHARA_WEBSITE_SETTINGS,
    normalize_biashara_website_settings,
)

from backend.jumuiya.biashara.models import (
    business_document,
    product_document,
    service_document,
    customer_document,
    order_document,
    expense_document,
    sale_document,
    inventory_movement_document,
)
from backend.jumuiya.notifications.services import notify as notify_jumuiya


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
    """
    Resolve the user's selected business only when that business is
    owned by the authenticated user. Fall back to the existing primary
    owner business for accounts without a saved selection.
    """
    owner_id = str(user_id)
    active = collection("jumuiya_biashara_active_business").find_one({
        "user_id": owner_id
    })
    if active and active.get("business_id"):
        selected = collection("jumuiya_businesses").find_one({
            "_id": clean_id(active["business_id"]),
            "owner_user_id": owner_id,
        })
        if selected:
            return serialise(selected)

    return serialise(
        collection("jumuiya_businesses").find_one({
            "owner_user_id": owner_id
        })
    )


def get_active_business_for_user(user_id):
    """Return the active owned/member business without weakening owner-only lookup."""
    context = resolve_business_access(user_id)
    if not context:
        return None
    return serialise(context.get("business"))


def _require_business(user_id, allowed_roles=None):
    """Resolve the active business and enforce its member role and verification."""
    access = resolve_business_access(user_id)
    business = serialise(access.get("business")) if access else None

    if not business:
        raise APIError(
            "Create a business profile or accept a business invitation first.",
            409,
            "business_required",
        )

    role = str((access or {}).get("role") or "owner").strip().lower()
    allowed = set(allowed_roles or {"owner"})
    allowed.add("owner")
    if role not in allowed:
        raise APIError(
            "Your business role does not permit this operation.",
            403,
            "business_role_forbidden",
        )

    verification_status = str(business.get("verification_status") or "").strip().lower()
    status = str(business.get("status") or "").strip().lower()

    if verification_status == "verified" and status == "active":
        return business

    if verification_status == "rejected" or status == "rejected":
        raise APIError(
            "Your business application was rejected. Review the admin notes and resubmit it for verification.",
            403,
            "business_verification_rejected",
        )

    if status == "suspended":
        raise APIError(
            "This business account is suspended. Contact platform support.",
            403,
            "business_suspended",
        )

    raise APIError(
        "Your business application must be verified by a platform administrator before you can access the business workspace.",
        403,
        "business_verification_required",
    )

def create_or_update_business(user_id, payload):
    businesses = collection("jumuiya_businesses")
    owner_id = str(user_id)
    old = businesses.find_one({"owner_user_id": owner_id})

    if old:
        fields = [
            "name",
            "business_type",
            "description",
            "phone",
            "email",
            "location",
            "county",
            "category",
            "logo_url",
        ]
        update = {
            key: payload.get(key, old.get(key, ""))
            for key in fields
        }
        update["slug"] = unique_slug(payload["name"], old["_id"])
        now = now_utc()
        update["updated_at"] = now

        is_verified = (
            old.get("verification_status") == "verified"
            and old.get("status") == "active"
        )
        sensitive_fields = (
            "name",
            "business_type",
            "phone",
            "email",
            "location",
            "county",
            "category",
        )
        identity_changed = any(
            str(old.get(key) or "").strip()
            != str(update.get(key) or "").strip()
            for key in sensitive_fields
        )
        needs_review = not is_verified or identity_changed

        update_query = {"$set": update}
        if needs_review:
            update.update({
                "status": "pending_verification",
                "verification_status": "pending",
                "submitted_at": now,
                "review_notes": "",
            })
            update_query["$unset"] = {
                "reviewed_at": "",
                "reviewed_by_user_id": "",
                "verified_at": "",
                "verified_by_user_id": "",
                "rejected_at": "",
                "rejected_by_user_id": "",
            }
            update_query["$push"] = {
                "verification_history": {
                    "event": "resubmitted",
                    "actor_user_id": owner_id,
                    "at": now.isoformat(),
                }
            }

        document = businesses.find_one_and_update(
            {
                "_id": old["_id"],
                "owner_user_id": owner_id,
            },
            update_query,
            return_document=ReturnDocument.AFTER,
        )
        if not document:
            raise APIError(
                "The business profile changed while you were saving it. Refresh and try again.",
                409,
                "business_profile_conflict",
            )

        log_action(
            user_id,
            "business.application.resubmitted" if needs_review else "business.updated",
            "business",
            document["_id"],
        )
        return serialise(document)

    now = now_utc()
    document = business_document(
        owner_id,
        payload,
        unique_slug(payload["name"]),
    )
    # Business data is an application until a platform administrator
    # explicitly verifies it. Client-supplied status is never trusted.
    document.update({
        "status": "pending_verification",
        "verification_status": "pending",
        "submitted_at": now,
        "review_notes": "",
        "verification_history": [{
            "event": "submitted",
            "actor_user_id": owner_id,
            "at": now.isoformat(),
        }],
    })

    result = businesses.insert_one(document)
    document["_id"] = result.inserted_id

    log_action(
        user_id,
        "business.application.submitted",
        "business",
        result.inserted_id,
        {"verification_status": "pending"},
    )
    return serialise(document)


# =========================================================
# PRODUCTS
# =========================================================

def create_product(
    user_id,
    payload,
):

    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'inventory']))

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
    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'sales', 'inventory', 'viewer']))
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


def update_product(
    user_id,
    product_id,
    payload,
):

    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'inventory']))

    allowed = {
        "name",
        "description",
        "category",
        "sku",
        "price",
        "currency",
        "stock_quantity",
        "unit",
        "image_url",
        "status",
    }

    update = {
        key: payload[key]
        for key in allowed
        if key in payload
    }

    if not update:

        raise APIError(
            "No product fields were provided.",
            422,
            "empty_update",
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
                **update,
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
        "product.updated",
        "product",
        document["_id"],
    )

    return serialise(
        document
    )


def delete_product(
    user_id,
    product_id,
):

    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'inventory']))

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
# BUSINESS SERVICES CATALOGUE
# =========================================================

def create_service(user_id, payload):
    business = _require_business(user_id, allowed_roles=set(["owner", "admin", "manager"]))
    document = service_document(business["id"], payload)
    result = collection("jumuiya_business_services").insert_one(document)
    document["_id"] = result.inserted_id
    log_action(user_id, "business_service.created", "business_service", result.inserted_id)
    return serialise(document)


def list_services(user_id, status=None, search=None, limit=50):
    business = _require_business(user_id, allowed_roles=set(["owner", "admin", "manager", "sales", "viewer"]))
    query = {"business_id": business["id"], "status": {"$ne": "deleted"}}
    if status:
        query["status"] = status
    search_text = str(search or "").strip()
    if search_text:
        expression = {"$regex": re.escape(search_text), "$options": "i"}
        query["$or"] = [
            {"name": expression},
            {"category": expression},
            {"service_type": expression},
            {"description": expression},
        ]
    documents = (
        collection("jumuiya_business_services")
        .find(query)
        .sort("created_at", -1)
        .limit(_bounded_list_limit(limit))
    )
    return serialise_many(documents)


def update_service(user_id, service_id, payload):
    business = _require_business(user_id, allowed_roles=set(["owner", "admin", "manager"]))
    allowed = {"name", "description", "category", "service_type", "price", "currency", "unit", "duration_minutes", "status"}
    update = {key: payload[key] for key in allowed if key in payload}
    if not update:
        raise APIError("No service fields were provided.", 422, "empty_update")
    document = collection("jumuiya_business_services").find_one_and_update(
        {"_id": clean_id(service_id), "business_id": business["id"]},
        {"$set": {**update, "updated_at": now_utc()}},
        return_document=ReturnDocument.AFTER,
    )
    if not document:
        raise APIError("Service not found.", 404, "service_not_found")
    log_action(user_id, "business_service.updated", "business_service", document["_id"])
    return serialise(document)


def delete_service(user_id, service_id):
    business = _require_business(user_id, allowed_roles=set(["owner", "admin", "manager"]))
    document = collection("jumuiya_business_services").find_one_and_update(
        {"_id": clean_id(service_id), "business_id": business["id"]},
        {"$set": {"status": "deleted", "updated_at": now_utc()}},
        return_document=ReturnDocument.AFTER,
    )
    if not document:
        raise APIError("Service not found.", 404, "service_not_found")
    log_action(user_id, "business_service.deleted", "business_service", document["_id"])
    return serialise(document)


def _notify_business_owner(business, title, message, notification_type, data=None):
    owner_user_id = str(business.get("owner_user_id") or "").strip()
    if not owner_user_id:
        return None
    try:
        return notify_jumuiya(owner_user_id, {
            "title": title,
            "message": message,
            "type": notification_type,
            "data": data if isinstance(data, dict) else {},
        })
    except Exception:
        # Notification persistence must not undo an accepted business operation.
        return None


# =========================================================
# INVENTORY
# =========================================================

def low_stock(
    user_id,
    threshold=5,
):

    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'sales', 'inventory', 'viewer']))

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
        "stock_quantity": {
            "$lte": threshold
        },
    }).sort(
        "stock_quantity",
        1,
    )

    return serialise_many(
        documents
    )


def inventory_adjustment(
    user_id,
    product_id,
    payload,
):

    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'inventory']))

    products = collection(
        "jumuiya_products"
    )

    product = products.find_one({
        "_id": clean_id(
            product_id
        ),
        "business_id": business["id"],
    })

    if not product:

        raise APIError(
            "Product not found.",
            404,
            "product_not_found",
        )

    previous_quantity = float(
        product.get(
            "stock_quantity",
            0,
        )
    )

    movement_type = payload[
        "movement_type"
    ]

    quantity = float(
        payload["quantity"]
    )

    if movement_type == "add":

        new_quantity = (
            previous_quantity
            + quantity
        )

    elif movement_type == "remove":

        new_quantity = (
            previous_quantity
            - quantity
        )

        if new_quantity < 0:

            raise APIError(
                "Insufficient stock.",
                409,
                "insufficient_stock",
            )

    elif movement_type == "set":

        new_quantity = quantity

    else:

        raise APIError(
            "Invalid inventory movement.",
            422,
            "invalid_movement",
        )

    updated = products.find_one_and_update(
        {
            "_id": product["_id"],
            "business_id": business["id"],
        },
        {
            "$set": {
                "stock_quantity": new_quantity,
                "updated_at": now_utc(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    movement = inventory_movement_document(
        business["id"],
        product["_id"],
        payload,
        previous_quantity,
        new_quantity,
    )

    movement_result = collection(
        "jumuiya_inventory_movements"
    ).insert_one(
        movement
    )

    movement["_id"] = (
        movement_result.inserted_id
    )

    log_action(
        user_id,
        "inventory.adjusted",
        "product",
        product["_id"],
    )

    return {
        "product": serialise(
            updated
        ),
        "movement": serialise(
            movement
        ),
    }


# =========================================================
# CUSTOMERS
# =========================================================

def create_customer(
    user_id,
    payload,
):

    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'sales']))

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
    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'sales', 'inventory', 'viewer']))
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


def create_order(
    user_id,
    payload,
):
    """Create a pending order using server-authoritative catalogue prices.

    Submitted line names/prices/totals are never trusted. The current stock
    check is advisory because pending orders do not reserve inventory yet;
    that limitation is recorded on the order until reservation/fulfilment is
    implemented as a separate, idempotent workflow.
    """
    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'sales']))

    customer_id = payload.get("customer_id")
    if customer_id:
        customer = collection("jumuiya_customers").find_one({
            "_id": clean_id(customer_id),
            "business_id": business["id"],
        })
        if not customer:
            raise APIError(
                "Customer does not belong to this business.",
                422,
                "invalid_customer",
            )

    submitted_items = payload.get("items")
    if not isinstance(submitted_items, list) or not submitted_items:
        raise APIError("An order must contain at least one item.", 422, "invalid_order_items")

    currency = str(business.get("currency") or "KES").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        currency = "KES"

    product_cache = {}
    stock_by_product = {}
    requested_by_product = {}
    priced_items = []
    subtotal = Decimal("0.00")

    for index, item in enumerate(submitted_items):
        if not isinstance(item, dict):
            raise APIError(
                f"Order item {index + 1} must be an object.",
                422,
                "invalid_order_items",
            )

        raw_product_id = item.get("product_id")
        if not raw_product_id:
            raise APIError(
                f"Order item {index + 1} requires a product.",
                422,
                "invalid_order_items",
            )

        product_key = str(raw_product_id)
        product = product_cache.get(product_key)
        if product is None:
            product = collection("jumuiya_products").find_one({
                "_id": clean_id(raw_product_id),
                "business_id": business["id"],
                "status": "active",
            })
            if not product:
                raise APIError(
                    "One or more products are no longer available.",
                    422,
                    "invalid_product",
                )
            product_cache[product_key] = product

        try:
            quantity = Decimal(str(item.get("quantity")))
            unit_price = Decimal(str(product.get("price", 0)))
            available = Decimal(str(product.get("stock_quantity", 0) or 0))
        except (InvalidOperation, TypeError, ValueError):
            raise APIError(
                "Order quantity or catalogue price is invalid.",
                422,
                "invalid_order_amount",
            )

        if not quantity.is_finite() or quantity <= 0:
            raise APIError(
                "Order quantities must be positive finite numbers.",
                422,
                "invalid_order_quantity",
            )
        if not unit_price.is_finite() or unit_price < 0:
            raise APIError(
                f"Catalogue price for {product.get('name', 'product')} is invalid.",
                409,
                "invalid_catalogue_price",
            )
        if not available.is_finite() or available < 0:
            available = Decimal("0")
        stock_by_product[product_key] = available
        if str(product.get("currency") or currency).upper() != currency:
            raise APIError(
                "All products in one order must use the business currency.",
                422,
                "mixed_order_currency",
            )

        rounded_price = unit_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        line_total = (rounded_price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        subtotal += line_total
        requested_by_product[product_key] = requested_by_product.get(product_key, Decimal("0")) + quantity

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

    # Atomically reserve inventory when an order is accepted. This makes the
    # displayed remaining quantity authoritative even when two customers order
    # close together.
    products_collection = collection("jumuiya_products")
    reserved = []
    for product_key, requested in requested_by_product.items():
        product = product_cache[product_key]
        requested_float = float(requested)
        updated_product = products_collection.find_one_and_update(
            {
                "_id": product["_id"],
                "business_id": business["id"],
                "status": "active",
                "stock_quantity": {"$gte": requested_float},
            },
            {
                "$inc": {"stock_quantity": -requested_float},
                "$set": {"updated_at": now_utc()},
            },
            return_document=ReturnDocument.AFTER,
        )
        if not updated_product:
            for reservation in reversed(reserved):
                products_collection.update_one(
                    {"_id": reservation["product_id"], "business_id": business["id"]},
                    {"$inc": {"stock_quantity": reservation["quantity"]}, "$set": {"updated_at": now_utc()}},
                )
            current = products_collection.find_one({"_id": product["_id"], "business_id": business["id"]})
            remaining = float((current or {}).get("stock_quantity", 0) or 0)
            raise APIError(
                f"Insufficient stock for {product.get('name', 'product')}. Remaining: {remaining:g}.",
                409,
                "insufficient_stock",
            )
        reserved.append({
            "product_id": product["_id"],
            "product_name": str(product.get("name") or "Product"),
            "quantity": requested_float,
            "previous_quantity": float(updated_product.get("stock_quantity", 0) or 0) + requested_float,
            "new_quantity": float(updated_product.get("stock_quantity", 0) or 0),
            "low_stock_threshold": float(product.get("low_stock_threshold", 0) or 0),
        })

    subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = subtotal
    now = now_utc()
    trusted_payload = {
        "customer_id": str(customer_id) if customer_id else None,
        "items": priced_items,
        "subtotal": float(subtotal),
        "subtotal_minor": int(subtotal * 100),
        "discount": 0,
        "total_amount": float(total),
        "total_amount_minor": int(total * 100),
        "currency": currency,
        "status": "pending",
        "payment_status": "unpaid",
        "payment_method": "",
        "payment_reference": "",
        "notes": str(payload.get("notes") or "")[:1000],
    }

    document = order_document(business["id"], trusted_payload)
    document.update({
        "subtotal_minor": int(subtotal * 100),
        "total_amount_minor": int(total * 100),
        "currency": currency,
        "source_channel": "manual",
        "inventory_status": "reserved",
        "inventory_reserved_at": now,
        "status_history": [{
            "from": None,
            "to": "pending",
            "at": now.isoformat(),
            "actor_user_id": str(user_id),
        }],
    })

    try:
        result = collection("jumuiya_orders").insert_one(document)
    except Exception:
        for reservation in reversed(reserved):
            products_collection.update_one(
                {"_id": reservation["product_id"], "business_id": business["id"]},
                {"$inc": {"stock_quantity": reservation["quantity"]}, "$set": {"updated_at": now_utc()}},
            )
        raise
    document["_id"] = result.inserted_id

    for reservation in reserved:
        movement_payload = {
            "movement_type": "remove",
            "quantity": reservation["quantity"],
            "reason": "Order " + str(result.inserted_id) + " reserved stock",
        }
        try:
            movement = inventory_movement_document(
                business["id"],
                reservation["product_id"],
                movement_payload,
                reservation["previous_quantity"],
                reservation["new_quantity"],
            )
            collection("jumuiya_inventory_movements").insert_one(movement)
        except Exception:
            pass
        threshold = reservation["low_stock_threshold"]
        if reservation["new_quantity"] <= threshold and reservation["previous_quantity"] > threshold:
            _notify_business_owner(
                business,
                "Low stock: " + reservation["product_name"],
                f"{reservation['product_name']} has {reservation['new_quantity']:g} units remaining after an order.",
                "inventory_low",
                {"product_id": str(reservation["product_id"]), "remaining_stock": reservation["new_quantity"], "order_id": str(result.inserted_id)},
            )

    log_action(user_id, "order.created", "order", result.inserted_id)
    return serialise(document)

def list_orders(
    user_id,
    status=None,
    limit=50,
):
    """List this business's orders with optional status and bounded limit."""
    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'sales', 'inventory', 'viewer']))
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

    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'sales', 'inventory', 'viewer']))

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


def update_order_status(
    user_id,
    order_id,
    status,
):
    """Apply a legal order transition and append an immutable status event."""
    transitions = {
        "pending": {"confirmed", "cancelled"},
        "confirmed": {"processing", "cancelled"},
        "processing": {"completed", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    }
    if not isinstance(status, str) or status not in transitions:
        raise APIError("Invalid order status.", 422, "invalid_order_status")

    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'sales']))
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

    now = now_utc()
    update = {"status": status, "updated_at": now}
    if status == "completed":
        update["completed_at"] = now
    if status == "cancelled":
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
        raise APIError(
            "The order changed while this update was being saved. Reload and try again.",
            409,
            "order_state_conflict",
        )

    # Stock is reserved at order creation. If an uncompleted order is cancelled,
    # release that reservation exactly once after the successful state transition.
    if status == "cancelled" and str(document.get("inventory_status") or "") == "reserved":
        for item in document.get("items") or []:
            if not isinstance(item, dict):
                continue
            product_id = item.get("product_id")
            try:
                quantity = float(item.get("quantity") or 0)
            except (TypeError, ValueError):
                quantity = 0
            if not product_id or quantity <= 0:
                continue
            product_before = collection("jumuiya_products").find_one({
                "_id": clean_id(product_id),
                "business_id": business["id"],
            })
            if not product_before:
                continue
            previous_quantity = float(product_before.get("stock_quantity", 0) or 0)
            product_after = collection("jumuiya_products").find_one_and_update(
                {"_id": product_before["_id"], "business_id": business["id"]},
                {"$inc": {"stock_quantity": quantity}, "$set": {"updated_at": now_utc()}},
                return_document=ReturnDocument.AFTER,
            )
            if product_after:
                movement_payload = {
                    "movement_type": "add",
                    "quantity": quantity,
                    "reason": "Order " + str(document["_id"]) + " cancellation released reservation",
                }
                try:
                    movement = inventory_movement_document(
                        business["id"], product_before["_id"], movement_payload,
                        previous_quantity, float(product_after.get("stock_quantity", 0) or 0),
                    )
                    collection("jumuiya_inventory_movements").insert_one(movement)
                except Exception:
                    pass
        orders.update_one(
            {"_id": document["_id"], "business_id": business["id"], "status": "cancelled"},
            {"$set": {"inventory_status": "released", "inventory_released_at": now_utc()}},
        )
        updated["inventory_status"] = "released"
    elif status == "completed" and str(document.get("inventory_status") or "") == "reserved":
        orders.update_one(
            {"_id": document["_id"], "business_id": business["id"], "status": "completed"},
            {"$set": {"inventory_status": "deducted", "inventory_deducted_at": now_utc()}},
        )
        updated["inventory_status"] = "deducted"

    log_action(user_id, "order.status_updated", "order", document["_id"])
    return serialise(updated)


# =========================================================
# SALES
# =========================================================

def record_sale(
    user_id,
    payload,
):

    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'sales']))

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

    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager']))

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

    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager']))

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

    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'sales', 'inventory', 'viewer']))

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
    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'sales', 'inventory', 'viewer']))
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
    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager']))
    now = now_utc()
    current = business.get("website") if isinstance(business.get("website"), dict) else {}
    settings = normalize_biashara_website_settings(payload, current)

    # Website publishing is part of the Biashara seller-tools entitlement.
    # Owners can always disable a previously published site, even after access expires.
    if settings.get("published") is True:
        from backend.revenue.subscriptions import resolve_entitlement
        entitlement = resolve_entitlement(str(user_id), "biashara", "seller_tools")
        if entitlement.get("allowed") is not True:
            raise APIError(
                "Publishing a Biashara website requires an active Biashara trial or a plan that includes website tools.",
                402,
                "biashara_website_entitlement_required",
            )

    old_domain = str(current.get("custom_domain", "") or "").strip().lower()
    new_domain = str(settings.get("custom_domain", "") or "").strip().lower()
    if new_domain != old_domain:
        settings["domain_status"] = "pending_platform_setup" if new_domain else "not_configured"
        settings["domain_setup_requested_at"] = now.isoformat() if new_domain else None
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
        "verification_status": "verified",
        "website.published": True,
    })
    if not business:
        raise APIError("Business website not found or not published.", 404, "website_not_found")

    # A saved published flag is not perpetual entitlement. Once a trial expires,
    # the public storefront stays hidden until the owner activates a qualifying plan.
    from backend.revenue.subscriptions import resolve_entitlement
    entitlement = resolve_entitlement(
        str(business.get("owner_user_id") or ""),
        "biashara",
        "seller_tools",
    )
    if entitlement.get("allowed") is not True:
        raise APIError("This business website needs an active Biashara trial or an eligible plan.", 404, "website_not_found")

    website = business.get("website") if isinstance(business.get("website"), dict) else {}
    public_business = {
        "name": business.get("name", ""),
        "slug": business.get("slug", ""),
        "description": business.get("description", ""),
        "business_type": business.get("business_type", ""),
        "category": business.get("category", ""),
        "opening_hours": business.get("opening_hours", {}) if isinstance(business.get("opening_hours", {}), dict) else {},
        "phone": business.get("phone", "") if website.get("contact_enabled", True) is True else "",
        "email": business.get("email", "") if website.get("contact_enabled", True) is True else "",
        "location": business.get("location", ""),
        "county": business.get("county", ""),
        "currency": business.get("currency", "KES") or "KES",
        "logo_url": (business.get("website") if isinstance(business.get("website"), dict) else {}).get("logo_url") or business.get("logo_url", ""),
    }
    public_website = {
        "headline": website.get("headline") or business.get("name", ""),
        "tagline": website.get("tagline", ""),
        "about": website.get("about") or business.get("description", ""),
        "logo_url": website.get("logo_url") or business.get("logo_url", ""),
        "cover_image_url": website.get("cover_image_url", "") or website.get("hero_image_url", ""),
        "hero_image_url": website.get("hero_image_url", ""),
        "hero_video_url": website.get("hero_video_url", ""),
        "hero_slides": website.get("hero_slides", []) if isinstance(website.get("hero_slides", []), list) else [],
        "service_items": website.get("service_items", []) if isinstance(website.get("service_items", []), list) else [],
        "gallery_items": website.get("gallery_items", []) if isinstance(website.get("gallery_items", []), list) else [],
        "social_links": website.get("social_links", {}) if isinstance(website.get("social_links", {}), dict) else {},
        "announcement": website.get("announcement", ""),
        "footer_message": website.get("footer_message", ""),
        "custom_domain": website.get("custom_domain", ""),
        "domain_status": website.get("domain_status", "not_configured"),
        "primary_color": website.get("primary_color", "#1d4ed8"),
        "accent_color": website.get("accent_color", "#0f766e"),
        "seo_title": website.get("seo_title") or business.get("name", ""),
        "seo_description": website.get("seo_description") or business.get("description", ""),
        "whatsapp_number": website.get("whatsapp_number", "") if website.get("contact_enabled", True) is True else "",
        "show_products": website.get("show_products", True) is True,
        "show_services": website.get("show_services", True) is True,
        "show_gallery": website.get("show_gallery", True) is True,
        "show_social_links": website.get("show_social_links", True) is True,
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
                "stock_quantity": float(product.get("stock_quantity", 0) or 0),
                "available": float(product.get("stock_quantity", 0) or 0) > 0,
            })

    public_services = []
    if public_website["show_services"]:
        service_docs = collection("jumuiya_business_services").find({
            "business_id": str(business["_id"]),
            "status": "active",
        }).sort("created_at", -1).limit(60)
        for service in service_docs:
            public_services.append({
                "id": str(service.get("_id", "")),
                "name": service.get("name", ""),
                "description": service.get("description", ""),
                "category": service.get("category", ""),
                "service_type": service.get("service_type", "general"),
                "price": service.get("price", 0),
                "currency": service.get("currency") or public_business["currency"],
                "unit": service.get("unit", "service"),
                "duration_minutes": service.get("duration_minutes", 0),
            })

    return {
        "business": public_business,
        "website": public_website,
        "products": products,
        "services": public_services,
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


def create_public_biashara_order(slug, payload):
    """Create a customer order through a published business storefront."""
    if not isinstance(payload, dict):
        raise APIError("A JSON request body is required.", 400, "invalid_json")
    if str(payload.get("website") or "").strip():
        return {"accepted": True}

    normalized_slug = str(slug or "").strip().lower()
    if not normalized_slug or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized_slug):
        raise APIError("Business website not found.", 404, "website_not_found")
    business = collection("jumuiya_businesses").find_one({
        "slug": normalized_slug,
        "status": "active",
        "verification_status": "verified",
        "website.published": True,
        "website.show_products": True,
    })
    if not business:
        raise APIError("This business does not currently accept website orders.", 404, "website_not_found")

    from backend.revenue.subscriptions import resolve_entitlement
    entitlement = resolve_entitlement(str(business.get("owner_user_id") or ""), "biashara", "seller_tools")
    if entitlement.get("allowed") is not True:
        raise APIError("This business website is not currently available for orders.", 404, "website_not_found")

    def clean_text(key, limit, required=False):
        value = payload.get(key, "")
        if not isinstance(value, str):
            raise APIError(key.replace("_", " ").capitalize() + " must be text.", 422, "validation_error")
        value = value.strip()
        if required and not value:
            raise APIError(key.replace("_", " ").capitalize() + " is required.", 422, "validation_error")
        if len(value) > limit or "<" in value or ">" in value:
            raise APIError(key.replace("_", " ").capitalize() + " is invalid or too long.", 422, "validation_error")
        return value

    name = clean_text("name", 160, True)
    email = clean_text("email", 254)
    phone = clean_text("phone", 40)
    notes = clean_text("notes", 1000)
    if not email and not phone:
        raise APIError("Provide a phone number or email address so the business can contact you.", 422, "contact_required")
    if email and not re.fullmatch(r"[^@\\s]+@[^@\\s]+\\.[^@\\s]+", email):
        raise APIError("Enter a valid email address.", 422, "invalid_email")
    if phone and not re.fullmatch(r"[+0-9() .-]{7,40}", phone):
        raise APIError("Enter a valid phone number.", 422, "invalid_phone")
    if not isinstance(payload.get("items"), list) or not payload.get("items"):
        raise APIError("Add at least one product to your order.", 422, "invalid_order_items")

    owner_user_id = str(business.get("owner_user_id") or "")
    if not owner_user_id:
        raise APIError("This business cannot receive orders right now.", 409, "business_owner_missing")

    order = create_order(
        owner_user_id,
        {"items": payload["items"], "notes": notes},
    )
    order_id = clean_id(order.get("id"))
    collection("jumuiya_orders").update_one(
        {"_id": order_id, "business_id": str(business["_id"])},
        {"$set": {
            "source_channel": "public_website",
            "customer_name": name,
            "customer_email": email,
            "customer_phone": phone,
        }},
    )
    _notify_business_owner(
        business,
        "New website order",
        f"{name} placed an order for {order.get('currency', 'KES')} {float(order.get('total_amount') or 0):,.2f}. Stock was reserved automatically.",
        "order_created",
        {"order_id": str(order.get("id") or ""), "business_slug": normalized_slug, "total_amount": order.get("total_amount"), "currency": order.get("currency", "KES")},
    )
    return {
        "accepted": True,
        "order": {
            "id": order.get("id"),
            "order_number": order.get("id"),
            "status": order.get("status"),
            "total_amount": order.get("total_amount"),
            "currency": order.get("currency"),
            "inventory_status": "reserved",
        },
    }


def list_biashara_website_inquiries(user_id, limit=30):
    business = _require_business(user_id, allowed_roles=set(['owner', 'admin', 'manager', 'sales']))
    documents = collection("jumuiya_business_website_inquiries").find(
        {"business_id": business["id"]}
    ).sort("created_at", -1).limit(_bounded_list_limit(limit))
    return serialise_many(documents)

