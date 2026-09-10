# backend/jumuiya/biashara/models.py

from __future__ import annotations

from datetime import datetime, timezone


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_CURRENCY = "KES"

BUSINESS_STATUS_ACTIVE = "active"

PRODUCT_STATUS_ACTIVE = "active"

ORDER_STATUS_PENDING = "pending"

ORDER_PAYMENT_UNPAID = "unpaid"


# =========================================================
# TIME
# =========================================================

def now_utc():
    """
    Return a timezone-aware UTC datetime.
    """
    return datetime.now(timezone.utc)


# =========================================================
# BUSINESS
# =========================================================

def business_document(
    user_id,
    payload,
    slug,
):
    """
    Create a Biashara business document.

    One authenticated Jumuiya user owns one primary
    business account under the current architecture.
    """

    now = now_utc()

    return {
        # -------------------------------------------------
        # OWNERSHIP
        # -------------------------------------------------

        "owner_user_id": str(
            user_id
        ),

        # -------------------------------------------------
        # BUSINESS IDENTITY
        # -------------------------------------------------

        "name": payload.get(
            "name",
            "",
        ),

        "slug": slug,

        "description": payload.get(
            "description",
            "",
        ),

        "business_type": payload.get(
            "business_type",
            "",
        ),

        "category": payload.get(
            "category",
            "",
        ),

        # -------------------------------------------------
        # CONTACT
        # -------------------------------------------------

        "phone": payload.get(
            "phone",
            "",
        ),

        "email": payload.get(
            "email",
            "",
        ),

        # -------------------------------------------------
        # LOCATION
        # -------------------------------------------------

        "location": payload.get(
            "location",
            "",
        ),

        "county": payload.get(
            "county",
            "",
        ),

        # -------------------------------------------------
        # BRANDING
        # -------------------------------------------------

        "logo_url": payload.get(
            "logo_url",
            "",
        ),

        # -------------------------------------------------
        # COMMERCE SETTINGS
        # -------------------------------------------------

        "currency": str(
            payload.get(
                "currency",
                DEFAULT_CURRENCY,
            )
            or DEFAULT_CURRENCY
        ).upper(),

        "payment_methods": payload.get(
            "payment_methods",
            [],
        ),

        "opening_hours": payload.get(
            "opening_hours",
            {},
        ),

        # -------------------------------------------------
        # BUSINESS STATE
        # -------------------------------------------------

        "status": payload.get(
            "status",
            BUSINESS_STATUS_ACTIVE,
        ),

        "profile_complete": bool(
            payload.get(
                "profile_complete",
                False,
            )
        ),

        # -------------------------------------------------
        # TIMESTAMPS
        # -------------------------------------------------

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# PRODUCTS
# =========================================================

def product_document(
    business_id,
    payload,
):
    """
    Create a product/listing belonging to a business.

    Product documents intentionally contain both selling
    price and cost price so Biashara can calculate
    approximate product margin and profitability later.
    """

    now = now_utc()

    return {
        # -------------------------------------------------
        # OWNERSHIP
        # -------------------------------------------------

        "business_id": str(
            business_id
        ),

        # -------------------------------------------------
        # PRODUCT IDENTITY
        # -------------------------------------------------

        "name": payload.get(
            "name",
            "",
        ),

        "description": payload.get(
            "description",
            "",
        ),

        "category": payload.get(
            "category",
            "",
        ),

        "sku": payload.get(
            "sku",
            "",
        ),

        # -------------------------------------------------
        # PRICING
        # -------------------------------------------------

        "price": float(
            payload.get(
                "price",
                0,
            )
        ),

        "cost_price": float(
            payload.get(
                "cost_price",
                0,
            )
        ),

        "currency": str(
            payload.get(
                "currency",
                DEFAULT_CURRENCY,
            )
            or DEFAULT_CURRENCY
        ).upper(),

        # -------------------------------------------------
        # INVENTORY
        # -------------------------------------------------

        "stock_quantity": float(
            payload.get(
                "stock_quantity",
                0,
            )
        ),

        "low_stock_threshold": float(
            payload.get(
                "low_stock_threshold",
                5,
            )
        ),

        "unit": payload.get(
            "unit",
            "piece",
        ),

        # -------------------------------------------------
        # MEDIA
        # -------------------------------------------------

        "image_url": payload.get(
            "image_url",
            "",
        ),

        # -------------------------------------------------
        # STATE
        # -------------------------------------------------

        "status": payload.get(
            "status",
            PRODUCT_STATUS_ACTIVE,
        ),

        # -------------------------------------------------
        # TIMESTAMPS
        # -------------------------------------------------

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# CUSTOMERS
# =========================================================

def customer_document(
    business_id,
    payload,
):
    """
    Create a business customer record.
    """

    now = now_utc()

    return {
        # -------------------------------------------------
        # OWNERSHIP
        # -------------------------------------------------

        "business_id": str(
            business_id
        ),

        # -------------------------------------------------
        # CUSTOMER
        # -------------------------------------------------

        "name": payload.get(
            "name",
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

        "notes": payload.get(
            "notes",
            "",
        ),

        # -------------------------------------------------
        # TIMESTAMPS
        # -------------------------------------------------

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# ORDERS
# =========================================================

def order_document(
    business_id,
    payload,
):
    """
    Create a customer order.

    Lifecycle:

        pending
            ↓
        confirmed
            ↓
        processing
            ↓
        completed

    Cancellation may occur before completion.
    """

    now = now_utc()

    return {
        # -------------------------------------------------
        # OWNERSHIP
        # -------------------------------------------------

        "business_id": str(
            business_id
        ),

        # -------------------------------------------------
        # CUSTOMER
        # -------------------------------------------------

        "customer_id": payload.get(
            "customer_id"
        ),

        # -------------------------------------------------
        # ORDER ITEMS
        # -------------------------------------------------

        "items": payload.get(
            "items",
            [],
        ),

        # -------------------------------------------------
        # FINANCIALS
        # -------------------------------------------------

        "subtotal": float(
            payload.get(
                "subtotal",
                payload.get(
                    "total_amount",
                    0,
                ),
            )
            or 0
        ),

        "discount": float(
            payload.get(
                "discount",
                0,
            )
            or 0
        ),

        "total_amount": float(
            payload.get(
                "total_amount",
                0,
            )
        ),

        "currency": str(
            payload.get(
                "currency",
                DEFAULT_CURRENCY,
            )
            or DEFAULT_CURRENCY
        ).upper(),

        # -------------------------------------------------
        # ORDER STATE
        # -------------------------------------------------

        "status": payload.get(
            "status",
            ORDER_STATUS_PENDING,
        ),

        # -------------------------------------------------
        # PAYMENT STATE
        # -------------------------------------------------

        "payment_status": payload.get(
            "payment_status",
            ORDER_PAYMENT_UNPAID,
        ),

        "payment_method": payload.get(
            "payment_method",
            "",
        ),

        "payment_reference": payload.get(
            "payment_reference",
            "",
        ),

        # -------------------------------------------------
        # NOTES
        # -------------------------------------------------

        "notes": payload.get(
            "notes",
            "",
        ),

        # -------------------------------------------------
        # TIMESTAMPS
        # -------------------------------------------------

        "created_at": now,

        "updated_at": now,
    }


# =========================================================
# EXPENSES
# =========================================================

def expense_document(
    business_id,
    payload,
):
    """
    Create a business expense record.
    """

    now = now_utc()

    spent_at = payload.get(
        "spent_at"
    )

    if not isinstance(
        spent_at,
        datetime,
    ):
        spent_at = now

    return {
        # -------------------------------------------------
        # OWNERSHIP
        # -------------------------------------------------

        "business_id": str(
            business_id
        ),

        # -------------------------------------------------
        # EXPENSE
        # -------------------------------------------------

        "title": payload.get(
            "title",
            "",
        ),

        "category": payload.get(
            "category",
            "",
        ),

        "amount": float(
            payload.get(
                "amount",
                0,
            )
        ),

        "currency": str(
            payload.get(
                "currency",
                DEFAULT_CURRENCY,
            )
            or DEFAULT_CURRENCY
        ).upper(),

        "notes": payload.get(
            "notes",
            "",
        ),

        # -------------------------------------------------
        # TIMESTAMPS
        # -------------------------------------------------

        "created_at": now,

        "spent_at": spent_at,

        "updated_at": now,
    }


# =========================================================
# SALES
# =========================================================

def sale_document(
    business_id,
    payload,
):
    """
    Record a completed business sale.

    Sales are separate from orders because Biashara
    supports walk-in, cash, mobile-money and other
    direct sales that may never originate from an order.
    """

    now = now_utc()

    sold_at = payload.get(
        "sold_at"
    )

    if not isinstance(
        sold_at,
        datetime,
    ):
        sold_at = now

    return {
        # -------------------------------------------------
        # OWNERSHIP
        # -------------------------------------------------

        "business_id": str(
            business_id
        ),

        # -------------------------------------------------
        # REFERENCES
        # -------------------------------------------------

        "order_id": payload.get(
            "order_id"
        ),

        "customer_id": payload.get(
            "customer_id"
        ),

        # -------------------------------------------------
        # ITEMS
        # -------------------------------------------------

        "items": payload.get(
            "items",
            [],
        ),

        # -------------------------------------------------
        # FINANCIALS
        # -------------------------------------------------

        "amount": float(
            payload.get(
                "amount",
                0,
            )
        ),

        "currency": str(
            payload.get(
                "currency",
                DEFAULT_CURRENCY,
            )
            or DEFAULT_CURRENCY
        ).upper(),

        # -------------------------------------------------
        # PAYMENT
        # -------------------------------------------------

        "payment_method": payload.get(
            "payment_method",
            "cash",
        ),

        "reference": payload.get(
            "reference",
            "",
        ),

        # -------------------------------------------------
        # TIMESTAMPS
        # -------------------------------------------------

        "created_at": now,

        "updated_at": now,

        "sold_at": sold_at,
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
    Create an immutable inventory movement record.

    Example:

        20 → 30 = stock added
        30 → 25 = stock removed
        25 → 50 = stock manually set
    """

    now = now_utc()

    previous_quantity = float(
        previous_quantity
    )

    new_quantity = float(
        new_quantity
    )

    quantity = float(
        payload.get(
            "quantity",
            0,
        )
    )

    return {
        # -------------------------------------------------
        # OWNERSHIP
        # -------------------------------------------------

        "business_id": str(
            business_id
        ),

        # -------------------------------------------------
        # PRODUCT
        # -------------------------------------------------

        "product_id": str(
            product_id
        ),

        # -------------------------------------------------
        # MOVEMENT
        # -------------------------------------------------

        "movement_type": payload.get(
            "movement_type",
            "",
        ),

        "quantity": quantity,

        "reason": payload.get(
            "reason",
            "",
        ),

        # -------------------------------------------------
        # SNAPSHOT
        # -------------------------------------------------

        "previous_quantity": (
            previous_quantity
        ),

        "new_quantity": (
            new_quantity
        ),

        # -------------------------------------------------
        # TIMESTAMP
        # -------------------------------------------------

        "created_at": now,
    }
