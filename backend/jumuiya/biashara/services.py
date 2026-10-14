# backend/jumuiya/biashara/services.py

import re
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

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
                "available": float(product.get("stock_quantity", 0) or 0) > 0,
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
