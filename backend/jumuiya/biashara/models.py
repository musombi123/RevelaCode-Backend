from datetime import datetime, timezone


# =========================================================
# TIME
# =========================================================

def now_utc():
    """
    Return timezone-aware UTC datetime.
    """
    return datetime.now(timezone.utc)


# =========================================================
# BUSINESS
# =========================================================

def business_document(user_id, payload, slug):
    """
    Create a Biashara business document.

    One authenticated Jumuiya user owns one primary business.
    """

    now = now_utc()

    return {
        "owner_user_id": str(user_id),

        "name": payload["name"],
        "slug": slug,

        "description": payload.get("description", ""),

        "phone": payload.get("phone", ""),
        "email": payload.get("email", ""),

        "location": payload.get("location", ""),
        "county": payload.get("county", ""),

        "category": payload.get("category", ""),

        "logo_url": payload.get("logo_url", ""),

        "status": "active",

        "created_at": now,
        "updated_at": now,
    }


# =========================================================
# PRODUCTS
# =========================================================

def product_document(business_id, payload):
    """
    Create a product/listing belonging to a business.
    """

    now = now_utc()

    return {
        "business_id": str(business_id),

        "name": payload["name"],
        "description": payload.get("description", ""),

        "category": payload.get("category", ""),

        "sku": payload.get("sku", ""),

        "price": float(
            payload.get("price", 0)
        ),

        "currency": payload.get(
            "currency",
            "KES",
        ),

        "stock_quantity": float(
            payload.get("stock_quantity", 0)
        ),

        "unit": payload.get(
            "unit",
            "piece",
        ),

        "image_url": payload.get(
            "image_url",
            "",
        ),

        "status": payload.get(
            "status",
            "active",
        ),

        "created_at": now,
        "updated_at": now,
    }


# =========================================================
# CUSTOMERS
# =========================================================

def customer_document(business_id, payload):
    """
    Create a business customer record.
    """

    now = now_utc()

    return {
        "business_id": str(business_id),

        "name": payload["name"],

        "phone": payload.get(
            "phone",
            "",
        ),

        "email": payload.get(
            "email",
            "",
        ),

        "notes": payload.get(
            "notes",
            "",
        ),

        "created_at": now,
        "updated_at": now,
    }


# =========================================================
# ORDERS
# =========================================================

def order_document(business_id, payload):
    """
    Create a customer order.

    Order lifecycle:

        pending
            ↓
        confirmed
            ↓
        processing
            ↓
        completed

    Or:

        pending/confirmed/processing
            ↓
        cancelled
    """

    now = now_utc()

    return {
        "business_id": str(business_id),

        "customer_id": payload.get(
            "customer_id"
        ),

        "items": payload.get(
            "items",
            [],
        ),

        "total_amount": float(
            payload.get(
                "total_amount",
                0,
            )
        ),

        "currency": payload.get(
            "currency",
            "KES",
        ),

        "status": "pending",

        "payment_status": "unpaid",

        "notes": payload.get(
            "notes",
            "",
        ),

        "created_at": now,
        "updated_at": now,
    }


# =========================================================
# EXPENSES
# =========================================================

def expense_document(business_id, payload):
    """
    Create a business expense record.
    """

    now = now_utc()

    return {
        "business_id": str(business_id),

        "title": payload["title"],

        "category": payload.get(
            "category",
            "",
        ),

        "amount": float(
            payload["amount"]
        ),

        "currency": payload.get(
            "currency",
            "KES",
        ),

        "notes": payload.get(
            "notes",
            "",
        ),

        "created_at": now,

        "spent_at": now,
    }


# =========================================================
# SALES
# =========================================================

def sale_document(business_id, payload):
    """
    Record a completed business sale.

    Sales are separate from orders because a business
    can record walk-in/cash sales that never originated
    from an online order.
    """

    return {
        "business_id": str(business_id),

        "order_id": payload.get(
            "order_id"
        ),

        "customer_id": payload.get(
            "customer_id"
        ),

        "items": payload.get(
            "items",
            [],
        ),

        "amount": float(
            payload["amount"]
        ),

        "currency": payload.get(
            "currency",
            "KES",
        ),

        "payment_method": payload.get(
            "payment_method",
            "cash",
        ),

        "reference": payload.get(
            "reference",
            "",
        ),

        "sold_at": now_utc(),
    }


# =========================================================
# INVENTORY MOVEMENTS
# =========================================================

def inventory_movement_document(
    business_id,
    product_id,
    payload,
    previous_quantity,
    new_quantity,
):
    """
    Record every stock movement.

    Example:

        20 → 30  = stock added
        30 → 25  = stock removed
        25 → 50  = stock manually set
    """

    return {
        "business_id": str(
            business_id
        ),

        "product_id": str(
            product_id
        ),

        "movement_type": payload[
            "movement_type"
        ],

        "quantity": float(
            payload["quantity"]
        ),

        "reason": payload.get(
            "reason",
            "",
        ),

        "previous_quantity": float(
            previous_quantity
        ),

        "new_quantity": float(
            new_quantity
        ),

        "created_at": now_utc(),
    }