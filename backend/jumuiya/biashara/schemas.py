# backend/jumuiya/biashara/schemas.py


# =========================================================
# COMMON VALIDATORS
# =========================================================

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
        raise ValueError(
            f"{key} must be text."
        )

    value = value.strip()

    if required and not value:
        raise ValueError(
            f"{key} is required."
        )

    if len(value) > max_len:
        raise ValueError(
            f"{key} is too long."
        )

    return value


def _number(
    data,
    key,
    required=False,
    minimum=0,
):
    value = data.get(key)

    if value is None and not required:
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

    return value


def _object(data):
    if not isinstance(data, dict):
        raise ValueError(
            "JSON object required."
        )


# =========================================================
# BUSINESS
# =========================================================

def business_payload(data):

    _object(data)

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

        "phone": _text(
            data,
            "phone",
            max_len=30,
        ),

        "email": _text(
            data,
            "email",
            max_len=160,
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

    # -----------------------------------------------------
    # TEXT FIELDS
    # -----------------------------------------------------

    text_fields = {
        "name": 160,
        "description": 1000,
        "category": 120,
        "sku": 80,
        "currency": 8,
        "unit": 40,
        "image_url": 500,
        "status": 30,
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

    if not partial or "price" in data:

        result["price"] = _number(
            data,
            "price",
            required=True,
            minimum=0,
        )

    # -----------------------------------------------------
    # STOCK
    # -----------------------------------------------------

    if not partial or "stock_quantity" in data:

        result["stock_quantity"] = _number(
            data,
            "stock_quantity",
            required=False,
            minimum=0,
        )

    # -----------------------------------------------------
    # DEFAULTS
    # -----------------------------------------------------

    if not partial:

        result["currency"] = (
            result.get("currency")
            or "KES"
        )

        result["unit"] = (
            result.get("unit")
            or "piece"
        )

        result["status"] = (
            result.get("status")
            or "active"
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

        "phone": _text(
            data,
            "phone",
            max_len=30,
        ),

        "email": _text(
            data,
            "email",
            max_len=160,
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
                f"Order item {index + 1} must be an object."
            )

        product_id = item.get(
            "product_id"
        )

        if not product_id:
            raise ValueError(
                f"Order item {index + 1} requires product_id."
            )

        try:

            quantity = float(
                item.get(
                    "quantity",
                    0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            raise ValueError(
                f"Order item {index + 1} quantity must be a number."
            )

        if quantity <= 0:

            raise ValueError(
                f"Order item {index + 1} quantity must be greater than zero."
            )

        cleaned_item = {
            "product_id": str(
                product_id
            ),
            "quantity": quantity,
        }

        # Optional snapshot information.
        if item.get("name") is not None:
            cleaned_item["name"] = str(
                item["name"]
            )[:160]

        if item.get("unit_price") is not None:

            try:
                unit_price = float(
                    item["unit_price"]
                )

            except (
                TypeError,
                ValueError,
            ):

                raise ValueError(
                    f"Order item {index + 1} unit_price must be a number."
                )

            if unit_price < 0:

                raise ValueError(
                    f"Order item {index + 1} unit_price cannot be negative."
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

        "total_amount": _number(
            data,
            "total_amount",
            required=True,
            minimum=0,
        ),

        "currency": _text(
            data,
            "currency",
            max_len=8,
        ) or "KES",

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

        "amount": _number(
            data,
            "amount",
            required=True,
            minimum=0,
        ),

        "currency": _text(
            data,
            "currency",
            max_len=8,
        ) or "KES",

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

    cleaned_items = _order_items(
        items
    ) if items else []

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

        "amount": _number(
            data,
            "amount",
            required=True,
            minimum=0,
        ),

        "currency": _text(
            data,
            "currency",
            max_len=8,
        ) or "KES",

        "payment_method": _text(
            data,
            "payment_method",
            max_len=40,
        ) or "cash",

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

    movement_type = _text(
        data,
        "movement_type",
        required=True,
        max_len=30,
    ).lower()

    allowed = {
        "add",
        "remove",
        "set",
    }

    if movement_type not in allowed:

        raise ValueError(
            "movement_type must be add, remove, or set."
        )

    return {
        "movement_type": movement_type,

        "quantity": _number(
            data,
            "quantity",
            required=True,
            minimum=0,
        ),

        "reason": _text(
            data,
            "reason",
            max_len=300,
        ),
    }