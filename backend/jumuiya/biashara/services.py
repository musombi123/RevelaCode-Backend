# backend/jumuiya/biashara/services.py

import re
from datetime import datetime, timezone

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
):

    business = _require_business(
        user_id
    )

    query = {
        "business_id": business["id"]
    }

    if status:
        query["status"] = status

    if category:
        query["category"] = category

    documents = (
        collection(
            "jumuiya_products"
        )
        .find(query)
        .sort(
            "created_at",
            -1,
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

    business = _require_business(
        user_id
    )

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

            query["$or"] = [
                {
                    "name": {
                        "$regex": re.escape(
                            search
                        ),
                        "$options": "i",
                    }
                },
                {
                    "phone": {
                        "$regex": re.escape(
                            search
                        ),
                        "$options": "i",
                    }
                },
                {
                    "email": {
                        "$regex": re.escape(
                            search
                        ),
                        "$options": "i",
                    }
                },
            ]

    documents = (
        collection(
            "jumuiya_customers"
        )
        .find(query)
        .sort(
            "created_at",
            -1,
        )
    )

    return serialise_many(
        documents
    )


# =========================================================
# ORDERS
# =========================================================

def create_order(
    user_id,
    payload,
):

    business = _require_business(
        user_id
    )

    # -----------------------------------------------------
    # Validate customer ownership
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
    # Validate products
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
            "status": {
                "$ne": "deleted"
            },
        })

        if not product:

            raise APIError(
                f"Product {item['product_id']} was not found.",
                422,
                "invalid_product",
            )

    document = order_document(
        business["id"],
        payload,
    )

    result = collection(
        "jumuiya_orders"
    ).insert_one(
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
):

    business = _require_business(
        user_id
    )

    query = {
        "business_id": business["id"]
    }

    if status:
        query["status"] = status

    documents = (
        collection(
            "jumuiya_orders"
        )
        .find(query)
        .sort(
            "created_at",
            -1,
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

    allowed = {
        "pending",
        "confirmed",
        "processing",
        "completed",
        "cancelled",
    }

    if status not in allowed:

        raise APIError(
            "Invalid order status.",
            422,
            "invalid_order_status",
        )

    business = _require_business(
        user_id
    )

    orders = collection(
        "jumuiya_orders"
    )

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

    # Don't allow pointless changes.
    if previous_status == status:

        return serialise(
            document
        )

    update = {
        "status": status,
        "updated_at": now_utc(),
    }

    # Completed orders get completed_at.
    if status == "completed":

        update["completed_at"] = now_utc()

    updated = orders.find_one_and_update(
        {
            "_id": document["_id"],
            "business_id": business["id"],
        },
        {
            "$set": update
        },
        return_document=ReturnDocument.AFTER,
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