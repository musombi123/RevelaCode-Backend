from flask import Blueprint, request

from backend.jumuiya.core.permissions import (
    require_authenticated,
    current_user_id,
)

from backend.jumuiya.core.responses import (
    ok,
    created,
)

from backend.jumuiya.core.errors import APIError

from backend.jumuiya.biashara import (
    schemas,
    services,
)


# =========================================================
# BLUEPRINT
# =========================================================

biashara_bp = Blueprint(
    "jumuiya_biashara",
    __name__,
)


# =========================================================
# HELPERS
# =========================================================

def body():
    """
    Safely read a JSON request body.
    """

    data = request.get_json(
        silent=True
    )

    if not isinstance(data, dict):
        raise APIError(
            "JSON request body is required.",
            400,
            "invalid_json",
        )

    return data


def validate(fn, data):
    """
    Convert schema ValueError exceptions
    into our standard APIError.
    """

    try:

        return fn(data)

    except ValueError as exc:

        raise APIError(
            str(exc),
            422,
            "validation_error",
        )


def user_id():
    """
    Convenience helper.
    """

    return current_user_id()


# =========================================================
# HEALTH
# =========================================================

@biashara_bp.get("/health")
def health():

    return ok({
        "hub": "biashara",
        "status": "online",
        "version": "1.0",
    })


# =========================================================
# BUSINESS PROFILE
# =========================================================

@biashara_bp.get("/business")
@require_authenticated
def get_business():

    return ok(
        services.get_business_for_user(
            user_id()
        )
    )


@biashara_bp.post("/business")
@require_authenticated
def save_business():

    payload = validate(
        schemas.business_payload,
        body(),
    )

    return ok(
        services.create_or_update_business(
            user_id(),
            payload,
        ),
        "Business profile saved.",
    )


# =========================================================
# PRODUCTS
# =========================================================

@biashara_bp.get("/products")
@require_authenticated
def get_products():

    return ok(
        services.list_products(
            user_id(),
            request.args.get("status"),
            request.args.get("category"),
        )
    )


@biashara_bp.post("/products")
@require_authenticated
def add_product():

    payload = validate(
        schemas.product_payload,
        body(),
    )

    return created(
        services.create_product(
            user_id(),
            payload,
        ),
        "Product created.",
    )


@biashara_bp.put(
    "/products/<product_id>"
)
@require_authenticated
def edit_product(product_id):

    payload = validate(
        lambda data: schemas.product_payload(
            data,
            partial=True,
        ),
        body(),
    )

    return ok(
        services.update_product(
            user_id(),
            product_id,
            payload,
        ),
        "Product updated.",
    )


@biashara_bp.delete(
    "/products/<product_id>"
)
@require_authenticated
def delete_product(product_id):

    return ok(
        services.delete_product(
            user_id(),
            product_id,
        ),
        "Product archived.",
    )


# =========================================================
# INVENTORY
# =========================================================

@biashara_bp.get(
    "/inventory/low-stock"
)
@require_authenticated
def low_stock():

    threshold = request.args.get(
        "threshold",
        5,
    )

    return ok(
        services.low_stock(
            user_id(),
            threshold,
        )
    )


@biashara_bp.post(
    "/inventory/<product_id>/adjust"
)
@require_authenticated
def adjust_inventory(product_id):

    payload = validate(
        schemas.inventory_payload,
        body(),
    )

    return ok(
        services.inventory_adjustment(
            user_id(),
            product_id,
            payload,
        ),
        "Inventory updated.",
    )


# =========================================================
# CUSTOMERS
# =========================================================

@biashara_bp.get("/customers")
@require_authenticated
def get_customers():

    return ok(
        services.list_customers(
            user_id(),
            request.args.get("search"),
        )
    )


@biashara_bp.post("/customers")
@require_authenticated
def add_customer():

    payload = validate(
        schemas.customer_payload,
        body(),
    )

    return created(
        services.create_customer(
            user_id(),
            payload,
        ),
        "Customer created.",
    )


# =========================================================
# ORDERS
# =========================================================

@biashara_bp.get("/orders")
@require_authenticated
def get_orders():

    return ok(
        services.list_orders(
            user_id(),
            request.args.get("status"),
        )
    )


@biashara_bp.post("/orders")
@require_authenticated
def add_order():

    payload = validate(
        schemas.order_payload,
        body(),
    )

    return created(
        services.create_order(
            user_id(),
            payload,
        ),
        "Order created.",
    )


@biashara_bp.get(
    "/orders/<order_id>"
)
@require_authenticated
def get_order(order_id):

    return ok(
        services.get_order(
            user_id(),
            order_id,
        )
    )


@biashara_bp.patch(
    "/orders/<order_id>/status"
)
@require_authenticated
def update_order_status(order_id):

    data = body()

    status = data.get(
        "status"
    )

    if not isinstance(
        status,
        str,
    ) or not status.strip():

        raise APIError(
            "Order status is required.",
            422,
            "validation_error",
        )

    return ok(
        services.update_order_status(
            user_id(),
            order_id,
            status.strip().lower(),
        ),
        "Order status updated.",
    )


# =========================================================
# SALES
# =========================================================

@biashara_bp.post("/sales")
@require_authenticated
def record_sale():

    payload = validate(
        schemas.sale_payload,
        body(),
    )

    return created(
        services.record_sale(
            user_id(),
            payload,
        ),
        "Sale recorded.",
    )


# =========================================================
# EXPENSES
# =========================================================

@biashara_bp.get("/expenses")
@require_authenticated
def get_expenses():

    return ok(
        services.list_expenses(
            user_id()
        )
    )


@biashara_bp.post("/expenses")
@require_authenticated
def add_expense():

    payload = validate(
        schemas.expense_payload,
        body(),
    )

    return created(
        services.create_expense(
            user_id(),
            payload,
        ),
        "Expense recorded.",
    )


# =========================================================
# DASHBOARD
# =========================================================

@biashara_bp.get("/dashboard")
@require_authenticated
def get_dashboard():

    return ok(
        services.dashboard(
            user_id()
        )
    )