# backend/jumuiya/biashara/services.py

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.audit import log_action

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
# CONSTANTS
# =========================================================

BUSINESS_ACTIVE_STATUS = "active"
BUSINESS_SUSPENDED_STATUS = "suspended"

PRODUCT_ACTIVE_STATUS = "active"
PRODUCT_DELETED_STATUS = "deleted"

ORDER_STATUSES = {
    "pending",
    "confirmed",
    "processing",
    "completed",
    "cancelled",
}

ORDER_TRANSITIONS = {
    "pending": {
        "confirmed",
        "cancelled",
    },
    "confirmed": {
        "processing",
        "cancelled",
    },
    "processing": {
        "completed",
        "cancelled",
    },
    "completed": set(),
    "cancelled": set(),
}

DEFAULT_LOW_STOCK_THRESHOLD = 5.0
DEFAULT_CURRENCY = "KES"

MAX_LIST_LIMIT = 100


# =========================================================
# COLLECTION HELPERS
# =========================================================

def businesses_collection():
    return collection(
        "jumuiya_businesses"
    )


def products_collection():
    return collection(
        "jumuiya_products"
    )


def customers_collection():
    return collection(
        "jumuiya_customers"
    )


def orders_collection():
    return collection(
        "jumuiya_orders"
    )


def sales_collection():
    return collection(
        "jumuiya_sales"
    )


def expenses_collection():
    return collection(
        "jumuiya_expenses"
    )


def inventory_collection():
    return collection(
        "jumuiya_inventory_movements"
    )


# =========================================================
# COMMON HELPERS
# =========================================================

def now_utc():
    return datetime.now(
        timezone.utc
    )


def clean_id(value):
    """
    Convert a valid MongoDB ObjectId string
    into ObjectId.

    Invalid values are returned unchanged so MongoDB
    queries fail safely rather than crashing.
    """

    try:
        return ObjectId(value)

    except (
        InvalidId,
        TypeError,
    ):
        return value


def serialise(doc):
    """
    Convert MongoDB document into a JSON-safe dictionary.
    """

    if not doc:
        return None

    out = dict(doc)

    if "_id" in out:
        out["id"] = str(
            out.pop("_id")
        )

    for key, value in list(
        out.items()
    ):

        if isinstance(
            value,
            ObjectId,
        ):
            out[key] = str(
                value
            )

        elif isinstance(
            value,
            datetime,
        ):
            out[key] = value.isoformat()

    return out


def serialise_many(docs):
    return [
        serialise(doc)
        for doc in docs
    ]


def safe_float(
    value,
    default=0.0,
):
    """
    Safely convert numeric database values
    into floats.
    """

    try:
        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def money(value):
    """
    Normalize monetary values to two decimals.
    """

    try:

        return float(
            Decimal(
                str(
                    value or 0
                )
            ).quantize(
                Decimal("0.01")
            )
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return 0.0


def normalise_currency(
    value,
):
    value = str(
        value or DEFAULT_CURRENCY
    ).strip().upper()

    return value[:8]


def clamp_limit(
    value,
    default=25,
):
    try:
        value = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return default

    return max(
        1,
        min(
            value,
            MAX_LIST_LIMIT,
        ),
    )


# =========================================================
# SLUGS
# =========================================================

def slugify(
    value,
):
    value = re.sub(
        r"[^a-zA-Z0-9\s-]",
        "",
        str(value or "").lower(),
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
    Generate a unique public business slug.
    """

    base = slugify(
        name
    )

    slug = base
    number = 2

    businesses = businesses_collection()

    while True:

        query = {
            "slug": slug
        }

        if current_id:

            query["_id"] = {
                "$ne": current_id
            }

        if not businesses.find_one(
            query,
            {
                "_id": 1
            },
        ):
            return slug

        slug = (
            f"{base}-{number}"
        )

        number += 1


# =========================================================
# BUSINESS
# =========================================================

def get_business_for_user(
    user_id,
):
    """
    Fetch the business owned by the authenticated
    Jumuiya/RevelaCode user.
    """

    return serialise(
        businesses_collection().find_one(
            {
                "owner_user_id": str(
                    user_id
                )
            }
        )
    )


def _require_business(
    user_id,
):
    """
    Require the authenticated user to have a valid
    active Biashara business.
    """

    business = get_business_for_user(
        user_id
    )

    if not business:

        raise APIError(
            "Create your business profile first.",
            409,
            "business_required",
        )

    status = business.get(
        "status",
        BUSINESS_ACTIVE_STATUS,
    )

    if status == BUSINESS_SUSPENDED_STATUS:

        raise APIError(
            "This business account is currently suspended.",
            403,
            "business_suspended",
        )

    if status != BUSINESS_ACTIVE_STATUS:

        raise APIError(
            "This business account is not currently active.",
            403,
            "business_inactive",
        )

    return business


def _business_id(
    user_id,
):
    return _require_business(
        user_id
    )["id"]


def _business_profile_complete(
    payload,
):
    """
    Determine whether the core business profile
    has enough information for normal operation.
    """

    required_fields = [
        "name",
        "category",
        "phone",
        "location",
        "county",
    ]

    return all(
        bool(
            str(
                payload.get(
                    field,
                    ""
                )
            ).strip()
        )
        for field in required_fields
    )


def create_or_update_business(
    user_id,
    payload,
):
    """
    Create a new business account for the user,
    or update the user's existing business profile.

    One owner -> one business is preserved to match
    the current architecture.
    """

    businesses = businesses_collection()

    owner_id = str(
        user_id
    )

    timestamp = now_utc()

    existing = businesses.find_one(
        {
            "owner_user_id": owner_id
        }
    )

    profile = {
        "name": payload["name"].strip(),

        "description": payload.get(
            "description",
            "",
        ),

        "phone": payload.get(
            "phone",
            "",
        ),

        "email": payload.get(
            "email",
            "",
        ),

        "location": payload.get(
            "location",
            "",
        ),

        "county": payload.get(
            "county",
            "",
        ),

        "category": payload.get(
            "category",
            "",
        ),

        "business_type": payload.get(
            "business_type",
            "",
        ),

        "logo_url": payload.get(
            "logo_url",
            "",
        ),

        "currency": normalise_currency(
            payload.get(
                "currency"
            )
        ),

        "payment_methods": payload.get(
            "payment_methods",
            [],
        ),

        "opening_hours": payload.get(
            "opening_hours",
            {},
        ),
    }

    profile["profile_complete"] = (
        _business_profile_complete(
            profile
        )
    )

    # -----------------------------------------------------
    # UPDATE
    # -----------------------------------------------------

    if existing:

        update = dict(
            profile
        )

        update["slug"] = unique_slug(
            profile["name"],
            existing["_id"],
        )

        update["created_at"] = (
            existing.get(
                "created_at",
                timestamp,
            )
        )

        update["updated_at"] = timestamp

        # Never silently reactivate or suspend
        # a business through profile editing.
        update["status"] = (
            existing.get(
                "status",
                BUSINESS_ACTIVE_STATUS,
            )
        )

        document = businesses.find_one_and_update(
            {
                "_id": existing["_id"],
                "owner_user_id": owner_id,
            },
            {
                "$set": update
            },
            return_document=ReturnDocument.AFTER,
        )

        if not document:

            raise APIError(
                "Unable to update business profile.",
                500,
                "business_update_failed",
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
        profile,
        unique_slug(
            profile["name"]
        ),
    )

    document.setdefault(
        "status",
        BUSINESS_ACTIVE_STATUS,
    )

    document.setdefault(
        "created_at",
        timestamp,
    )

    document[
        "updated_at"
    ] = timestamp

    document[
        "profile_complete"
    ] = profile[
        "profile_complete"
    ]

    result = businesses.insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

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

def _find_product(
    business_id,
    product_id,
    include_deleted=False,
):
    query = {
        "_id": clean_id(
            product_id
        ),
        "business_id": business_id,
    }

    if not include_deleted:

        query["status"] = {
            "$ne": PRODUCT_DELETED_STATUS
        }

    return products_collection().find_one(
        query
    )


def _ensure_unique_sku(
    business_id,
    sku,
    current_product_id=None,
):
    sku = str(
        sku or ""
    ).strip()

    if not sku:
        return

    query = {
        "business_id": business_id,
        "sku": sku,
        "status": {
            "$ne": PRODUCT_DELETED_STATUS
        },
    }

    if current_product_id:

        query["_id"] = {
            "$ne": current_product_id
        }

    duplicate = products_collection().find_one(
        query,
        {
            "_id": 1
        },
    )

    if duplicate:

        raise APIError(
            "A product with this SKU already exists.",
            409,
            "duplicate_sku",
        )


def create_product(
    user_id,
    payload,
):

    business = _require_business(
        user_id
    )

    business_id = business["id"]

    _ensure_unique_sku(
        business_id,
        payload.get(
            "sku"
        ),
    )

    document = product_document(
        business_id,
        payload,
    )

    document.setdefault(
        "status",
        PRODUCT_ACTIVE_STATUS,
    )

    document.setdefault(
        "stock_quantity",
        0.0,
    )

    document.setdefault(
        "cost_price",
        0.0,
    )

    document.setdefault(
        "low_stock_threshold",
        DEFAULT_LOW_STOCK_THRESHOLD,
    )

    document.setdefault(
        "currency",
        business.get(
            "currency",
            DEFAULT_CURRENCY,
        ),
    )

    timestamp = now_utc()

    document.setdefault(
        "created_at",
        timestamp,
    )

    document[
        "updated_at"
    ] = timestamp

    result = products_collection().insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

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
    """
    List products belonging only to the authenticated
    user's business.
    """

    business = _require_business(
        user_id
    )

    query = {
        "business_id": business["id"]
    }

    if status:

        query["status"] = status

    else:

        query["status"] = {
            "$ne": PRODUCT_DELETED_STATUS
        }

    if category:

        query["category"] = category.strip()

    if search:

        search = search.strip()

        if search:

            pattern = re.escape(
                search
            )

            query["$or"] = [
                {
                    "name": {
                        "$regex": pattern,
                        "$options": "i",
                    }
                },
                {
                    "sku": {
                        "$regex": pattern,
                        "$options": "i",
                    }
                },
                {
                    "category": {
                        "$regex": pattern,
                        "$options": "i",
                    }
                },
            ]

    documents = (
        products_collection()
        .find(query)
        .sort(
            "created_at",
            -1,
        )
        .limit(
            clamp_limit(
                limit,
                50,
            )
        )
    )

    return serialise_many(
        documents
    )


def update_product(
    user_id,
    product_id,
    payload,
):

    business = _require_business(
        user_id
    )

    products = products_collection()

    product_object_id = clean_id(
        product_id
    )

    existing = products.find_one({
        "_id": product_object_id,
        "business_id": business["id"],
    })

    if not existing:

        raise APIError(
            "Product not found.",
            404,
            "product_not_found",
        )

    allowed = {
        "name",
        "description",
        "category",
        "sku",
        "price",
        "cost_price",
        "currency",
        "stock_quantity",
        "low_stock_threshold",
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

    if "sku" in update:

        _ensure_unique_sku(
            business["id"],
            update["sku"],
            existing["_id"],
        )

    if "currency" in update:

        update[
            "currency"
        ] = normalise_currency(
            update["currency"]
        )

    if "stock_quantity" in update:

        stock = safe_float(
            update["stock_quantity"],
            -1,
        )

        if stock < 0:

            raise APIError(
                "Stock quantity cannot be negative.",
                422,
                "invalid_stock",
            )

        update[
            "stock_quantity"
        ] = stock

    if "cost_price" in update:

        cost_price = safe_float(
            update["cost_price"],
            -1,
        )

        if cost_price < 0:

            raise APIError(
                "Cost price cannot be negative.",
                422,
                "invalid_cost_price",
            )

        update[
            "cost_price"
        ] = money(
            cost_price
        )

    if "price" in update:

        price = safe_float(
            update["price"],
            -1,
        )

        if price < 0:

            raise APIError(
                "Price cannot be negative.",
                422,
                "invalid_price",
            )

        update[
            "price"
        ] = money(
            price
        )

    update[
        "updated_at"
    ] = now_utc()

    document = products.find_one_and_update(
        {
            "_id": product_object_id,
            "business_id": business["id"],
        },
        {
            "$set": update
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:

        raise APIError(
            "Unable to update product.",
            500,
            "product_update_failed",
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
    """
    Soft-delete product so historical sales,
    orders and reports remain intact.
    """

    business = _require_business(
        user_id
    )

    products = products_collection()

    document = products.find_one_and_update(
        {
            "_id": clean_id(
                product_id
            ),
            "business_id": business["id"],
            "status": {
                "$ne": PRODUCT_DELETED_STATUS
            },
        },
        {
            "$set": {
                "status": PRODUCT_DELETED_STATUS,
                "deleted_at": now_utc(),
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
    threshold=None,
):

    business = _require_business(
        user_id
    )

    if threshold is None:

        threshold = DEFAULT_LOW_STOCK_THRESHOLD

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

    documents = (
        products_collection()
        .find({
            "business_id": business["id"],
            "status": PRODUCT_ACTIVE_STATUS,
            "stock_quantity": {
                "$lte": threshold
            },
        })
        .sort(
            "stock_quantity",
            1,
        )
    )

    return serialise_many(
        documents
    )


def inventory_adjustment(
    user_id,
    product_id,
    payload,
):
    """
    Adjust inventory atomically and record an immutable
    inventory movement.
    """

    business = _require_business(
        user_id
    )

    products = products_collection()

    product_id_clean = clean_id(
        product_id
    )

    product = products.find_one({
        "_id": product_id_clean,
        "business_id": business["id"],
        "status": PRODUCT_ACTIVE_STATUS,
    })

    if not product:

        raise APIError(
            "Product not found.",
            404,
            "product_not_found",
        )

    previous_quantity = safe_float(
        product.get(
            "stock_quantity",
            0,
        )
    )

    movement_type = str(
        payload.get(
            "movement_type"
        )
    ).lower()

    quantity = safe_float(
        payload.get(
            "quantity"
        ),
        -1,
    )

    if quantity <= 0:

        raise APIError(
            "Inventory quantity must be greater than zero.",
            422,
            "invalid_quantity",
        )

    if movement_type == "add":

        new_quantity = (
            previous_quantity
            + quantity
        )

    elif movement_type == "remove":

        if quantity > previous_quantity:

            raise APIError(
                "Insufficient stock.",
                409,
                "insufficient_stock",
            )

        new_quantity = (
            previous_quantity
            - quantity
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
            "_id": product_id_clean,
            "business_id": business["id"],
            "status": PRODUCT_ACTIVE_STATUS,
            "stock_quantity": previous_quantity,
        },
        {
            "$set": {
                "stock_quantity": new_quantity,
                "updated_at": now_utc(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not updated:

        raise APIError(
            "Inventory changed before this operation completed. Please retry.",
            409,
            "inventory_conflict",
        )

    movement_payload = {
        **payload,
        "movement_type": movement_type,
        "quantity": quantity,
    }

    movement = inventory_movement_document(
        business["id"],
        product_id_clean,
        movement_payload,
        previous_quantity,
        new_quantity,
    )

    movement_result = inventory_collection().insert_one(
        movement
    )

    movement["_id"] = (
        movement_result.inserted_id
    )

    log_action(
        user_id,
        "inventory.adjusted",
        "product",
        product_id_clean,
    )

    return {
        "product": serialise(
            updated
        ),
        "movement": serialise(
            movement
        ),
    }


def inventory_history(
    user_id,
    product_id=None,
    limit=50,
):
    """
    Return recent inventory movement history.
    """

    business = _require_business(
        user_id
    )

    query = {
        "business_id": business["id"]
    }

    if product_id:

        query[
            "product_id"
        ] = str(
            product_id
        )

    documents = (
        inventory_collection()
        .find(query)
        .sort(
            "created_at",
            -1,
        )
        .limit(
            clamp_limit(
                limit,
                50,
            )
        )
    )

    return serialise_many(
        documents
    )


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

    timestamp = now_utc()

    document.setdefault(
        "created_at",
        timestamp,
    )

    document[
        "updated_at"
    ] = timestamp

    result = customers_collection().insert_one(
        document
    )

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
    business = _require_business(
        user_id
    )

    query = {
        "business_id": business["id"]
    }

    if search:

        search = search.strip()

        if search:

            pattern = re.escape(
                search
            )

            query["$or"] = [
                {
                    "name": {
                        "$regex": pattern,
                        "$options": "i",
                    }
                },
                {
                    "phone": {
                        "$regex": pattern,
                        "$options": "i",
                    }
                },
                {
                    "email": {
                        "$regex": pattern,
                        "$options": "i",
                    }
                },
            ]

    documents = (
        customers_collection()
        .find(query)
        .sort(
            "created_at",
            -1,
        )
        .limit(
            clamp_limit(
                limit,
                50,
            )
        )
    )

    return serialise_many(
        documents
    )


# =========================================================
# ORDER HELPERS
# =========================================================

def _get_owned_customer(
    business_id,
    customer_id,
):
    if not customer_id:
        return None

    customer = customers_collection().find_one({
        "_id": clean_id(
            customer_id
        ),
        "business_id": business_id,
    })

    if not customer:

        raise APIError(
            "Customer does not belong to this business.",
            422,
            "invalid_customer",
        )

    return customer


def _get_owned_product(
    business_id,
    product_id,
):
    product = products_collection().find_one({
        "_id": clean_id(
            product_id
        ),
        "business_id": business_id,
        "status": {
            "$ne": PRODUCT_DELETED_STATUS
        },
    })

    if not product:

        raise APIError(
            f"Product {product_id} was not found.",
            422,
            "invalid_product",
        )

    return product


def _build_order_items(
    business_id,
    items,
):
    """
    Resolve requested products against the database
    and return price snapshots controlled by the backend.

    This prevents a client from changing a product's
    price while creating an order.
    """

    normalized = []

    total = Decimal("0.00")

    for item in items:

        product = _get_owned_product(
            business_id,
            item["product_id"],
        )

        quantity = Decimal(
            str(
                item.get(
                    "quantity",
                    0,
                )
            )
        )

        if quantity <= 0:

            raise APIError(
                "Order quantity must be greater than zero.",
                422,
                "invalid_quantity",
            )

        unit_price = Decimal(
            str(
                product.get(
                    "price",
                    0,
                )
            )
        )

        line_total = (
            unit_price
            * quantity
        )

        normalized.append({
            "product_id": str(
                product["_id"]
            ),
            "name": product.get(
                "name",
                "",
            ),
            "quantity": float(
                quantity
            ),
            "unit_price": money(
                unit_price
            ),
            "line_total": money(
                line_total
            ),
        })

        total += line_total

    return (
        normalized,
        money(total),
    )


# =========================================================
# ORDERS
# =========================================================

def create_order(
    user_id,
    payload,
):
    """
    Create a business order using backend-controlled
    product pricing.
    """

    business = _require_business(
        user_id
    )

    business_id = business["id"]

    _get_owned_customer(
        business_id,
        payload.get(
            "customer_id"
        ),
    )

    normalized_items, calculated_total = (
        _build_order_items(
            business_id,
            payload.get(
                "items",
                [],
            ),
        )
    )

    if not normalized_items:

        raise APIError(
            "An order must contain at least one item.",
            422,
            "empty_order",
        )

    if calculated_total < 0:

        raise APIError(
            "Order total cannot be negative.",
            422,
            "invalid_total",
        )

    final_payload = {
        **payload,
        "items": normalized_items,
        "total_amount": calculated_total,
        "currency": normalise_currency(
            payload.get(
                "currency",
                business.get(
                    "currency",
                    DEFAULT_CURRENCY,
                ),
            )
        ),
    }

    document = order_document(
        business_id,
        final_payload,
    )

    timestamp = now_utc()

    document.setdefault(
        "status",
        "pending",
    )

    document.setdefault(
        "created_at",
        timestamp,
    )

    document[
        "updated_at"
    ] = timestamp

    result = orders_collection().insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    log_action(
        user_id,
        "order.created",
        "order",
        result.inserted_id,
    )

    return serialise(
        document
    )


def list_orders(
    user_id,
    status=None,
    limit=50,
):
    business = _require_business(
        user_id
    )

    query = {
        "business_id": business["id"]
    }

    if status:

        if status not in ORDER_STATUSES:

            raise APIError(
                "Invalid order status.",
                422,
                "invalid_order_status",
            )

        query[
            "status"
        ] = status

    documents = (
        orders_collection()
        .find(query)
        .sort(
            "created_at",
            -1,
        )
        .limit(
            clamp_limit(
                limit,
                50,
            )
        )
    )

    return serialise_many(
        documents
    )


def get_order(
    user_id,
    order_id,
):
    business = _require_business(
        user_id
    )

    document = orders_collection().find_one({
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
    """
    Enforce a controlled order lifecycle.
    """

    status = str(
        status or ""
    ).lower().strip()

    if status not in ORDER_STATUSES:

        raise APIError(
            "Invalid order status.",
            422,
            "invalid_order_status",
        )

    business = _require_business(
        user_id
    )

    orders = orders_collection()

    document = orders.find_one({
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

    previous_status = document.get(
        "status",
        "pending",
    )

    if previous_status == status:

        return serialise(
            document
        )

    allowed_next = ORDER_TRANSITIONS.get(
        previous_status,
        set(),
    )

    if status not in allowed_next:

        raise APIError(
            (
                f"Order cannot move from "
                f"{previous_status} to {status}."
            ),
            409,
            "invalid_order_transition",
        )

    timestamp = now_utc()

    update = {
        "status": status,
        "updated_at": timestamp,
    }

    if status == "completed":

        update[
            "completed_at"
        ] = timestamp

    if status == "cancelled":

        update[
            "cancelled_at"
        ] = timestamp

    updated = orders.find_one_and_update(
        {
            "_id": document["_id"],
            "business_id": business["id"],
            "status": previous_status,
        },
        {
            "$set": update
        },
        return_document=ReturnDocument.AFTER,
    )

    if not updated:

        raise APIError(
            "Order changed before this operation completed. Please retry.",
            409,
            "order_conflict",
        )

    log_action(
        user_id,
        "order.status_updated",
        "order",
        document["_id"],
    )

    return serialise(
        updated
    )


# =========================================================
# SALES
# =========================================================

def record_sale(
    user_id,
    payload,
):
    """
    Record a sale, deduct stock safely and create
    inventory history.

    Product pricing is resolved from the database
    rather than blindly trusting client-supplied prices.
    """

    business = _require_business(
        user_id
    )

    business_id = business["id"]

    customer_id = payload.get(
        "customer_id"
    )

    _get_owned_customer(
        business_id,
        customer_id,
    )

    items = payload.get(
        "items",
        [],
    )

    # -----------------------------------------------------
    # Normalize products and verify inventory first
    # -----------------------------------------------------

    resolved_items = []

    requested_by_product = {}

    for item in items:

        product = collection(
            "jumuiya_products"
        ).find_one({
            "_id": clean_id(
                item["product_id"]
            ),
            "business_id": business_id,
            "status": PRODUCT_ACTIVE_STATUS,
        })

        if not product:

            raise APIError(
                f"Product {item['product_id']} was not found.",
                422,
                "invalid_product",
            )

        quantity = safe_float(
            item.get(
                "quantity"
            ),
            0,
        )

        if quantity <= 0:

            raise APIError(
                "Sale quantity must be greater than zero.",
                422,
                "invalid_quantity",
            )

        product_id = product["_id"]

        requested_by_product[
            product_id
        ] = (
            requested_by_product.get(
                product_id,
                0.0,
            )
            + quantity
        )

        resolved_items.append({
            "product": product,
            "quantity": quantity,
        })

    # -----------------------------------------------------
    # Check all available stock
    # -----------------------------------------------------

    for product_id, requested in (
        requested_by_product.items()
    ):

        product = products_collection().find_one({
            "_id": product_id,
            "business_id": business_id,
            "status": PRODUCT_ACTIVE_STATUS,
        })

        if not product:
            raise APIError(
                "One or more products are unavailable.",
                409,
                "product_unavailable",
            )

        available = safe_float(
            product.get(
                "stock_quantity",
                0,
            )
        )

        if requested > available:

            raise APIError(
                (
                    f"Insufficient stock for "
                    f"{product.get('name', 'product')}."
                ),
                409,
                "insufficient_stock",
            )

    # -----------------------------------------------------
    # Build backend-controlled financial snapshot
    # -----------------------------------------------------

    calculated_total = Decimal(
        "0.00"
    )

    sale_items = []

    for entry in resolved_items:

        product = entry[
            "product"
        ]

        quantity = Decimal(
            str(
                entry["quantity"]
            )
        )

        unit_price = Decimal(
            str(
                product.get(
                    "price",
                    0,
                )
            )
        )

        line_total = (
            unit_price
            * quantity
        )

        calculated_total += line_total

        sale_items.append({
            "product_id": str(
                product["_id"]
            ),
            "name": product.get(
                "name",
                "",
            ),
            "quantity": float(
                quantity
            ),
            "unit_price": money(
                unit_price
            ),
            "line_total": money(
                line_total
            ),
        })

    final_amount = money(
        calculated_total
    )

    sale_payload_data = {
        **payload,

        "items": sale_items,

        "amount": final_amount,

        "currency": normalise_currency(
            payload.get(
                "currency",
                business.get(
                    "currency",
                    DEFAULT_CURRENCY,
                ),
            )
        ),
    }

    # -----------------------------------------------------
    # Create sale document
    # -----------------------------------------------------

    document = sale_document(
        business_id,
        sale_payload_data,
    )

    timestamp = now_utc()

    document.setdefault(
        "created_at",
        timestamp,
    )

    document[
        "updated_at"
    ] = timestamp

    result = sales_collection().insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    # -----------------------------------------------------
    # Atomic inventory deductions
    # -----------------------------------------------------

    movement_docs = []

    for product_id, requested in (
        requested_by_product.items()
    ):

        requested = float(
            requested
        )

        current = products_collection().find_one({
            "_id": product_id,
            "business_id": business_id,
            "status": PRODUCT_ACTIVE_STATUS,
        })

        if not current:

            raise APIError(
                "Product disappeared during sale processing.",
                409,
                "inventory_conflict",
            )

        previous_quantity = safe_float(
            current.get(
                "stock_quantity",
                0,
            )
        )

        updated = products_collection().find_one_and_update(
            {
                "_id": product_id,
                "business_id": business_id,
                "status": PRODUCT_ACTIVE_STATUS,
                "stock_quantity": {
                    "$gte": requested
                },
            },
            {
                "$inc": {
                    "stock_quantity": -requested
                },
                "$set": {
                    "updated_at": now_utc(),
                },
            },
            return_document=ReturnDocument.AFTER,
        )

        if not updated:

            raise APIError(
                (
                    "Stock changed while the sale was "
                    "being processed. Please retry."
                ),
                409,
                "inventory_conflict",
            )

        new_quantity = safe_float(
            updated.get(
                "stock_quantity",
                0,
            )
        )

        movement = inventory_movement_document(
            business_id,
            product_id,
            {
                "movement_type": "remove",
                "quantity": requested,
                "reason": "sale",
            },
            previous_quantity,
            new_quantity,
        )

        movement_docs.append(
            movement
        )

    # -----------------------------------------------------
    # Persist inventory movements
    # -----------------------------------------------------

    if movement_docs:

        inventory_collection().insert_many(
            movement_docs
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

    timestamp = now_utc()

    document.setdefault(
        "created_at",
        timestamp,
    )

    document.setdefault(
        "spent_at",
        timestamp,
    )

    document[
        "updated_at"
    ] = timestamp

    result = expenses_collection().insert_one(
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
    limit=50,
):
    business = _require_business(
        user_id
    )

    documents = (
        expenses_collection()
        .find({
            "business_id": business["id"]
        })
        .sort(
            "spent_at",
            -1,
        )
        .limit(
            clamp_limit(
                limit,
                50,
            )
        )
    )

    return serialise_many(
        documents
    )


# =========================================================
# DASHBOARD HELPERS
# =========================================================

def _date_bounds(
    days=1,
):
    """
    Return UTC bounds for the requested number of
    recent calendar days.
    """

    end = now_utc()

    start = (
        end
        - timedelta(
            days=days
        )
    )

    return start, end


def _aggregate_total(
    mongo_collection,
    match,
    field,
):
    result = list(
        mongo_collection.aggregate([
            {
                "$match": match
            },
            {
                "$group": {
                    "_id": None,
                    "total": {
                        "$sum": field
                    },
                },
            },
        ])
    )

    if not result:

        return 0.0

    return money(
        result[0].get(
            "total",
            0,
        )
    )


def _today_sales(
    business_id,
):
    start, end = _date_bounds(
        1
    )

    return _aggregate_total(
        sales_collection(),
        {
            "business_id": business_id,
            "created_at": {
                "$gte": start,
                "$lt": end,
            },
        },
        "$amount",
    )


def _today_orders(
    business_id,
):
    start, end = _date_bounds(
        1
    )

    return orders_collection().count_documents({
        "business_id": business_id,
        "created_at": {
            "$gte": start,
            "$lt": end,
        },
    })


def _top_products(
    business_id,
    limit=5,
):
    """
    Rank products by sales volume using sale snapshots.
    """

    result = list(
        sales_collection().aggregate([
            {
                "$match": {
                    "business_id": business_id
                }
            },
            {
                "$unwind": {
                    "path": "$items",
                    "preserveNullAndEmptyArrays": False,
                }
            },
            {
                "$group": {
                    "_id": "$items.product_id",
                    "name": {
                        "$first": "$items.name"
                    },
                    "units": {
                        "$sum": "$items.quantity"
                    },
                    "revenue": {
                        "$sum": "$items.line_total"
                    },
                }
            },
            {
                "$sort": {
                    "revenue": -1,
                    "units": -1,
                }
            },
            {
                "$limit": clamp_limit(
                    limit,
                    5,
                )
            },
        ])
    )

    output = []

    for item in result:

        output.append({
            "product_id": str(
                item["_id"]
            ),
            "name": item.get(
                "name",
                "Product",
            ),
            "units": safe_float(
                item.get(
                    "units",
                    0,
                )
            ),
            "revenue": money(
                item.get(
                    "revenue",
                    0,
                )
            ),
        })

    return output


def _recent_orders(
    business_id,
    limit=5,
):
    documents = (
        orders_collection()
        .find({
            "business_id": business_id
        })
        .sort(
            "created_at",
            -1,
        )
        .limit(
            clamp_limit(
                limit,
                5,
            )
        )
    )

    return serialise_many(
        documents
    )


def _recent_sales(
    business_id,
    limit=5,
):
    documents = (
        sales_collection()
        .find({
            "business_id": business_id
        })
        .sort(
            "created_at",
            -1,
        )
        .limit(
            clamp_limit(
                limit,
                5,
            )
        )
    )

    return serialise_many(
        documents
    )


def _recent_low_stock(
    business_id,
    limit=5,
):
    documents = (
        products_collection()
        .find({
            "business_id": business_id,
            "status": PRODUCT_ACTIVE_STATUS,
            "$expr": {
                "$lte": [
                    "$stock_quantity",
                    {
                        "$ifNull": [
                            "$low_stock_threshold",
                            DEFAULT_LOW_STOCK_THRESHOLD,
                        ]
                    },
                ]
            },
        })
        .sort(
            "stock_quantity",
            1,
        )
        .limit(
            clamp_limit(
                limit,
                5,
            )
        )
    )

    return serialise_many(
        documents
    )


def _sales_trend(
    business_id,
    days=7,
):
    """
    Return daily sales totals for the last N days.
    """

    end = now_utc()

    start = (
        end
        - timedelta(
            days=days
        )
    )

    result = list(
        sales_collection().aggregate([
            {
                "$match": {
                    "business_id": business_id,
                    "created_at": {
                        "$gte": start,
                        "$lt": end,
                    },
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$created_at",
                        }
                    },
                    "sales": {
                        "$sum": "$amount"
                    },
                }
            },
            {
                "$sort": {
                    "_id": 1
                }
            },
        ])
    )

    values = {
        item["_id"]: money(
            item.get(
                "sales",
                0,
            )
        )
        for item in result
    }

    trend = []

    for offset in range(
        days
    ):

        day = (
            start
            + timedelta(
                days=offset
            )
        ).strftime(
            "%Y-%m-%d"
        )

        trend.append({
            "date": day,
            "sales": values.get(
                day,
                0.0,
            ),
        })

    return trend


# =========================================================
# DASHBOARD
# =========================================================

def dashboard(
    user_id,
):
    """
    Full Biashara operating dashboard.

    Designed for the premium Biashara frontend:
    overview metrics, today metrics, products,
    customers, orders, low stock, top products,
    recent orders and sales trends.
    """

    business = _require_business(
        user_id
    )

    business_id = business["id"]

    products = products_collection()
    customers = customers_collection()
    orders = orders_collection()
    sales = sales_collection()
    expenses = expenses_collection()

    # -----------------------------------------------------
    # LIFETIME FINANCIALS
    # -----------------------------------------------------

    total_sales = _aggregate_total(
        sales,
        {
            "business_id": business_id
        },
        "$amount",
    )

    total_expenses = _aggregate_total(
        expenses,
        {
            "business_id": business_id
        },
        "$amount",
    )

    net_estimate = money(
        total_sales
        - total_expenses
    )

    # -----------------------------------------------------
    # TODAY
    # -----------------------------------------------------

    today_sales = _today_sales(
        business_id
    )

    today_orders = _today_orders(
        business_id
    )

    # -----------------------------------------------------
    # COUNTS
    # -----------------------------------------------------

    product_count = products.count_documents({
        "business_id": business_id,
        "status": {
            "$ne": PRODUCT_DELETED_STATUS
        },
    })

    active_product_count = products.count_documents({
        "business_id": business_id,
        "status": PRODUCT_ACTIVE_STATUS,
    })

    low_stock_count = products.count_documents({
        "business_id": business_id,
        "status": PRODUCT_ACTIVE_STATUS,
        "$expr": {
            "$lte": [
                "$stock_quantity",
                {
                    "$ifNull": [
                        "$low_stock_threshold",
                        DEFAULT_LOW_STOCK_THRESHOLD,
                    ]
                },
            ]
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

    cancelled_orders = orders.count_documents({
        "business_id": business_id,
        "status": "cancelled",
    })

    total_orders = orders.count_documents({
        "business_id": business_id
    })

    total_sales_count = sales.count_documents({
        "business_id": business_id
    })

    # -----------------------------------------------------
    # AVERAGE ORDER VALUE
    # -----------------------------------------------------

    average_order_value = (
        money(
            total_sales
            / total_sales_count
        )
        if total_sales_count
        else 0.0
    )

    # -----------------------------------------------------
    # DASHBOARD DATA
    # -----------------------------------------------------

    return {
        "business": business,

        "currency": business.get(
            "currency",
            DEFAULT_CURRENCY,
        ),

        "today": {
            "sales": today_sales,
            "orders": today_orders,
        },

        "metrics": {
            "products": product_count,
            "active_products": active_product_count,
            "low_stock": low_stock_count,

            "customers": customer_count,

            "orders": total_orders,
            "pending_orders": pending_orders,
            "completed_orders": completed_orders,
            "cancelled_orders": cancelled_orders,

            "sales_total": total_sales,
            "expenses_total": total_expenses,

            "net_estimate": net_estimate,

            "average_order_value": (
                average_order_value
            ),
        },

        "top_products": _top_products(
            business_id,
            5,
        ),

        "recent_orders": _recent_orders(
            business_id,
            5,
        ),

        "recent_sales": _recent_sales(
            business_id,
            5,
        ),

        "low_stock_products": _recent_low_stock(
            business_id,
            5,
        ),

        "sales_trend": _sales_trend(
            business_id,
            7,
        ),
    }
