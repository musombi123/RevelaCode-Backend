# backend/jumuiya/biashara/schemas.py

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_CURRENCY = "KES"

BUSINESS_STATUSES = {
    "active",
    "inactive",
    "suspended",
}

PRODUCT_STATUSES = {
    "active",
    "inactive",
    "archived",
}

PAYMENT_METHODS = {
    "cash",
    "mpesa",
    "bank",
    "card",
    "mobile_money",
    "other",
}

INVENTORY_MOVEMENTS = {
    "add",
    "remove",
    "set",
}


# =========================================================
# COMMON VALIDATORS
# =========================================================

def _object(data):
    if not isinstance(data, dict):
        raise ValueError("JSON object required.")


def _text(
    data,
    key,
    required=False,
    max_len=300,
):
    value = data.get(key)

    if value is None:
        value = ""

    if not isinstance(value, str):
        raise ValueError(f"{key} must be text.")

    value = value.strip()

    if required and not value:
        raise ValueError(f"{key} is required.")

    if len(value) > max_len:
        raise ValueError(
            f"{key} must not exceed {max_len} characters."
        )

    return value


def _choice(
    data,
    key,
    allowed,
    required=False,
    default=None,
    lowercase=True,
):
    value = data.get(key)

    if value is None or value == "":
        if required:
            raise ValueError(f"{key} is required.")

        return default

    if not isinstance(value, str):
        raise ValueError(f"{key} must be text.")

    value = value.strip()

    if lowercase:
        value = value.lower()

    if value not in allowed:
        allowed_values = ", ".join(
            sorted(allowed)
        )

        raise ValueError(
            f"{key} must be one of: {allowed_values}."
        )

    return value


def _number(
    data,
    key,
    required=False,
    minimum=0,
    maximum=None,
):
    value = data.get(key)

    if value is None:

        if required:
            raise ValueError(
                f"{key} is required."
            )

        return 0.0

    try:
        value = float(value)

    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            f"{key} must be a number."
        )

    if value < minimum:
        raise ValueError(
            f"{key} must be at least {minimum}."
        )

    if maximum is not None and value > maximum:
        raise ValueError(
            f"{key} must not exceed {maximum}."
        )

    return value


def _money(
    data,
    key,
    required=False,
    minimum=0,
):
    value = data.get(key)

    if value is None:

        if required:
            raise ValueError(
                f"{key} is required."
            )

        return 0.0

    try:

        decimal_value = Decimal(
            str(value)
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        raise ValueError(
            f"{key} must be a valid monetary amount."
        )

    if decimal_value < Decimal(
        str(minimum)
    ):
        raise ValueError(
            f"{key} must be at least {minimum}."
        )

    # Two decimal places maximum.
    decimal_value = decimal_value.quantize(
        Decimal("0.01")
    )

    return float(decimal_value)


def _email(
    data,
    key="email",
):
    value = _text(
        data,
        key,
        max_len=160,
    )

    if not value:
        return ""

    pattern = (
        r"^[A-Za-z0-9._%+-]+@"
        r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    )

    if not re.match(
        pattern,
        value,
    ):
        raise ValueError(
            f"{key} must be a valid email address."
        )

    return value.lower()


def _phone(
    data,
    key="phone",
):
    value = _text(
        data,
        key,
        max_len=30,
    )

    if not value:
        return ""

    # Accept common international / Kenyan formats
    cleaned = re.sub(
        r"[\s().-]",
        "",
        value,
    )

    if not re.match(
        r"^\+?[0-9]{9,15}$",
        cleaned,
    ):
        raise ValueError(
            f"{key} must be a valid phone number."
        )

    return value


def _string_list(
    data,
    key,
    max_items=20,
    item_max_len=80,
):
    value = data.get(key)

    if value is None:
        return []

    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            f"{key} must be a list."
        )

    if len(value) > max_items:
        raise ValueError(
            f"{key} cannot contain more than "
            f"{max_items} items."
        )

    cleaned = []

    for item in value:

        if not isinstance(
            item,
            str,
        ):
            raise ValueError(
                f"Each {key} item must be text."
            )

        item = item.strip()

        if not item:
            continue

        if len(item) > item_max_len:
            raise ValueError(
                f"Items in {key} cannot exceed "
                f"{item_max_len} characters."
            )

        cleaned.append(item)

    return cleaned


# =========================================================
# BUSINESS
# =========================================================

def business_payload(data):

    _object(data)

    business_type = _text(
        data,
        "business_type",
        max_len=80,
    )

    opening_hours = data.get(
        "opening_hours"
    )

    if opening_hours is None:
        opening_hours = {}

    if not isinstance(
        opening_hours,
        dict,
    ):
        raise ValueError(
            "opening_hours must be an object."
        )

    return {
        "name": _text(
            data,
            "name",
            required=True,
            max_len=160,
        ),

        "description": _text(
            data,
            "description",
            max_len=2000,
        ),

        "business_type": business_type,

        "phone": _phone(
            data,
        ),

        "email": _email(
            data,
        ),

        "location": _text(
            data,
            "location",
            max_len=200,
        ),

        "county": _text(
            data,
            "county",
            max_len=100,
        ),

        "category": _text(
            data,
            "category",
            max_len=120,
        ),

        "logo_url": _text(
            data,
            "logo_url",
            max_len=500,
        ),

        "currency": _text(
            data,
            "currency",
            max_len=8,
        ).upper() or DEFAULT_CURRENCY,

        "payment_methods": _string_list(
            data,
            "payment_methods",
            max_items=10,
            item_max_len=40,
        ),

        "opening_hours": opening_hours,

        "status": _choice(
            data,
            "status",
            BUSINESS_STATUSES,
            default="active",
        ),
    }


# =========================================================
# PRODUCTS
# =========================================================

def product_payload(
    data,
    partial=False,
):

    _object(data)

    result = {}

    text_fields = {
        "name": 160,
        "description": 1000,
        "category": 120,
        "sku": 80,
        "currency": 8,
        "unit": 40,
        "image_url": 500,
    }

    for key, max_len in text_fields.items():

        if partial and key not in data:
            continue

        result[key] = _text(
            data,
            key,
            required=(
                key == "name"
                and not partial
            ),
            max_len=max_len,
        )

    # -----------------------------------------------------
    # PRICE
    # -----------------------------------------------------

    if (
        not partial
        or "price" in data
    ):

        result["price"] = _money(
            data,
            "price",
            required=True,
            minimum=0,
        )

    # -----------------------------------------------------
    # COST PRICE
    # -----------------------------------------------------

    if (
        not partial
        or "cost_price" in data
    ):

        result["cost_price"] = _money(
            data,
            "cost_price",
            required=False,
            minimum=0,
        )

    # -----------------------------------------------------
    # STOCK
    # -----------------------------------------------------

    if (
        not partial
        or "stock_quantity" in data
    ):

        result["stock_quantity"] = _number(
            data,
            "stock_quantity",
            required=False,
            minimum=0,
        )

    # -----------------------------------------------------
    # LOW STOCK THRESHOLD
    # -----------------------------------------------------

    if (
        not partial
        or "low_stock_threshold" in data
    ):

        result["low_stock_threshold"] = _number(
            data,
            "low_stock_threshold",
            required=False,
            minimum=0,
        )

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    if (
        not partial
        or "status" in data
    ):

        result["status"] = _choice(
            data,
            "status",
            PRODUCT_STATUSES,
            default="active",
        )

    # -----------------------------------------------------
    # DEFAULTS
    # -----------------------------------------------------

    if not partial:

        result["currency"] = (
            result.get("currency")
            or DEFAULT_CURRENCY
        ).upper()

        result["unit"] = (
            result.get("unit")
            or "piece"
        )

        result["status"] = (
            result.get("status")
            or "active"
        )

        result["low_stock_threshold"] = (
            result.get(
                "low_stock_threshold"
            )
            or 0.0
        )

        result["cost_price"] = (
            result.get(
                "cost_price"
            )
            or 0.0
        )

    return result


# =========================================================
# CUSTOMERS
# =========================================================

def customer_payload(data):

    _object(data)

    return {
        "name": _text(
            data,
            "name",
            required=True,
            max_len=160,
        ),

        "phone": _phone(
            data,
        ),

        "email": _email(
            data,
        ),

        "notes": _text(
            data,
            "notes",
            max_len=1000,
        ),
    }


# =========================================================
# ORDER ITEMS
# =========================================================

def _order_items(items):

    if not isinstance(
        items,
        list,
    ):
        raise ValueError(
            "items must be a list."
        )

    if len(items) > 100:
        raise ValueError(
            "An order cannot contain more than 100 items."
        )

    cleaned = []

    for index, item in enumerate(items):

        if not isinstance(
            item,
            dict,
        ):
            raise ValueError(
                f"Order item {index + 1} "
                f"must be an object."
            )

        product_id = item.get(
            "product_id"
        )

        if not product_id:
            raise ValueError(
                f"Order item {index + 1} "
                f"requires product_id."
            )

        quantity = _number(
            item,
            "quantity",
            required=True,
            minimum=0.000001,
        )

        cleaned_item = {
            "product_id": str(
                product_id
            ),
            "quantity": quantity,
        }

        if item.get("name") is not None:

            name = item["name"]

            if not isinstance(
                name,
                str,
            ):
                raise ValueError(
                    f"Order item {index + 1} "
                    f"name must be text."
                )

            cleaned_item["name"] = (
                name.strip()[:160]
            )

        if item.get(
            "unit_price"
        ) is not None:

            unit_price = _money(
                item,
                "unit_price",
                required=True,
                minimum=0,
            )

            cleaned_item[
                "unit_price"
            ] = unit_price

        cleaned.append(
            cleaned_item
        )

    return cleaned


# =========================================================
# ORDERS
# =========================================================

def order_payload(data):

    _object(data)

    items = _order_items(
        data.get(
            "items",
            [],
        )
    )

    if not items:
        raise ValueError(
            "An order must contain at least one item."
        )

    return {
        "customer_id": (
            str(data["customer_id"])
            if data.get("customer_id")
            else None
        ),

        "items": items,

        "total_amount": _money(
            data,
            "total_amount",
            required=True,
            minimum=0,
        ),

        "currency": _text(
            data,
            "currency",
            max_len=8,
        ).upper() or DEFAULT_CURRENCY,

        "notes": _text(
            data,
            "notes",
            max_len=1000,
        ),
    }


# =========================================================
# EXPENSES
# =========================================================

def expense_payload(data):

    _object(data)

    return {
        "title": _text(
            data,
            "title",
            required=True,
            max_len=160,
        ),

        "category": _text(
            data,
            "category",
            max_len=120,
        ),

        "amount": _money(
            data,
            "amount",
            required=True,
            minimum=0,
        ),

        "currency": _text(
            data,
            "currency",
            max_len=8,
        ).upper() or DEFAULT_CURRENCY,

        "notes": _text(
            data,
            "notes",
            max_len=1000,
        ),
    }


# =========================================================
# SALES
# =========================================================

def sale_payload(data):

    _object(data)

    items = data.get(
        "items",
        [],
    )

    if not isinstance(
        items,
        list,
    ):
        raise ValueError(
            "items must be a list."
        )

    cleaned_items = (
        _order_items(items)
        if items
        else []
    )

    return {
        "order_id": (
            str(data["order_id"])
            if data.get("order_id")
            else None
        ),

        "customer_id": (
            str(data["customer_id"])
            if data.get("customer_id")
            else None
        ),

        "items": cleaned_items,

        "amount": _money(
            data,
            "amount",
            required=True,
            minimum=0,
        ),

        "currency": _text(
            data,
            "currency",
            max_len=8,
        ).upper() or DEFAULT_CURRENCY,

        "payment_method": _choice(
            data,
            "payment_method",
            PAYMENT_METHODS,
            default="cash",
        ),

        "reference": _text(
            data,
            "reference",
            max_len=120,
        ),
    }


# =========================================================
# INVENTORY
# =========================================================

def inventory_payload(data):

    _object(data)

    movement_type = _choice(
        data,
        "movement_type",
        INVENTORY_MOVEMENTS,
        required=True,
    )

    quantity = _number(
        data,
        "quantity",
        required=True,
        minimum=0.000001,
    )

    return {
        "movement_type": movement_type,

        "quantity": quantity,

        "reason": _text(
            data,
            "reason",
            max_len=300,
        ),
    }
