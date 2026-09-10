# backend/jumuiya/biashara/routes.py

from __future__ import annotations

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
# CONSTANTS
# =========================================================

DEFAULT_LIST_LIMIT = 50

MAX_LIST_LIMIT = 100


# =========================================================
# HELPERS
# =========================================================

def body():
    """
    Safely read a JSON request body.

    Every write endpoint in Biashara uses this helper so
    malformed JSON receives the same API error structure.
    """

    data = request.get_json(
        silent=True
    )

    if not isinstance(
        data,
        dict,
    ):

        raise APIError(
            "JSON request body is required.",
            400,
            "invalid_json",
        )

    return data


def validate(
    fn,
    data,
):
    """
    Convert schema ValueError exceptions
    into the standard Biashara APIError.
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
    Return the authenticated RevelaCode/Jumuiya user ID.
    """

    return current_user_id()


def query_limit(
    default=DEFAULT_LIST_LIMIT,
):
    """
    Safely parse and clamp pagination limits.
    """

    raw = request.args.get(
        "limit"
    )

    if raw is None:
        return default

    try:

        value = int(
            raw
        )

    except (
        TypeError,
        ValueError,
    ):

        raise APIError(
            "limit must be a valid integer.",
            422,
            "invalid_limit",
        )

    if value < 1:

        raise APIError(
            "limit must be at least 1.",
            422,
            "invalid_limit",
        )

    return min(
        value,
        MAX_LIST_LIMIT,
    )


# =========================================================
# HEALTH
# =========================================================

@biashara_bp.get(
    "/health"
)
def health():
    """
    Public Biashara service health endpoint.
    """

    return ok({
        "hub": "biashara",
        "status": "online",
        "version": "1.1",
    })


# =========================================================
# BUSINESS PROFILE
# =========================================================

@biashara_bp.get(
    "/business"
)
@require_authenticated
def get_business():
    """
    Return the authenticated user's business profile.

    If the user has not created a business yet,
    the endpoint returns null through the standard
    response wrapper rather than incorrectly creating
    an empty business.
    """

    return ok(
        services.get_business_for_user(
            user_id()
        )
    )


@biashara_bp.post(
    "/business"
)
@require_authenticated
def save_business():
    """
    Create or update the user's primary business profile.
    """

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

@biashara_bp.get(
    "/products"
)
@require_authenticated
def get_products():
    """
    List the authenticated business products.

    Supported query parameters:

        ?status=active
        ?category=electronics
        ?search=phone
        ?limit=50
    """

    return ok(
        services.list_products(
            user_id(),
            request.args.get(
                "status"
            ),
            request.args.get(
                "category"
            ),
            request.args.get(
                "search"
            ),
            query_limit(),
        )
    )


@biashara_bp.post(
    "/products"
)
@require_authenticated
def add_product():
    """
    Create a product.
    """

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
def edit_product(
    product_id,
):
    """
    Update an existing product.
    """

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
def delete_product(
    product_id,
):
    """
    Soft-delete/archive a product.

    Historical orders and sales remain intact.
    """

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
    """
    Return products that have reached the low-stock threshold.

    Example:

        /inventory/low-stock?threshold=5
    """

    threshold = request.args.get(
        "threshold"
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
def adjust_inventory(
    product_id,
):
    """
    Add, remove or set product stock.
    """

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


@biashara_bp.get(
    "/inventory/history"
)
@require_authenticated
def inventory_history():
    """
    Return recent inventory movements.

    Optional:

        ?product_id=<id>
        ?limit=50
    """

    return ok(
        services.inventory_history(
            user_id(),
            request.args.get(
                "product_id"
            ),
            query_limit(),
        )
    )


# =========================================================
# CUSTOMERS
# =========================================================

@biashara_bp.get(
    "/customers"
)
@require_authenticated
def get_customers():
    """
    List customers with optional search.
    """

    return ok(
        services.list_customers(
            user_id(),
            request.args.get(
                "search"
            ),
            query_limit(),
        )
    )


@biashara_bp.post(
    "/customers"
)
@require_authenticated
def add_customer():
    """
    Create a customer record.
    """

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

@biashara_bp.get(
    "/orders"
)
@require_authenticated
def get_orders():
    """
    List business orders.

    Optional:

        ?status=pending
        ?limit=50
    """

    return ok(
        services.list_orders(
            user_id(),
            request.args.get(
                "status"
            ),
            query_limit(),
        )
    )


@biashara_bp.post(
    "/orders"
)
@require_authenticated
def add_order():
    """
    Create an order.

    Product prices are resolved by the backend.
    """

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
def get_order(
    order_id,
):
    """
    Return a single business order.
    """

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
def update_order_status(
    order_id,
):
    """
    Move an order through the controlled lifecycle.
    """

    data = body()

    status = data.get(
        "status"
    )

    if not isinstance(
        status,
        str,
    ):

        raise APIError(
            "Order status is required.",
            422,
            "validation_error",
        )

    status = status.strip().lower()

    if not status:

        raise APIError(
            "Order status is required.",
            422,
            "validation_error",
        )

    return ok(
        services.update_order_status(
            user_id(),
            order_id,
            status,
        ),
        "Order status updated.",
    )


# =========================================================
# SALES
# =========================================================

@biashara_bp.post(
    "/sales"
)
@require_authenticated
def record_sale():
    """
    Record a completed business sale.

    Sales can represent direct/walk-in sales or
    sales associated with existing orders.
    """

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

@biashara_bp.get(
    "/expenses"
)
@require_authenticated
def get_expenses():
    """
    List recent business expenses.
    """

    return ok(
        services.list_expenses(
            user_id(),
            query_limit(),
        )
    )


@biashara_bp.post(
    "/expenses"
)
@require_authenticated
def add_expense():
    """
    Record a business expense.
    """

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

@biashara_bp.get(
    "/dashboard"
)
@require_authenticated
def get_dashboard():
    """
    Return the complete Biashara operating dashboard.

    Includes:

        - Business profile
        - Today metrics
        - Lifetime metrics
        - Top products
        - Recent orders
        - Recent sales
        - Low-stock products
        - Sales trend
    """

    return ok(
        services.dashboard(
            user_id()
        )
    )
