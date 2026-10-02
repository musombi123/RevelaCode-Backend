from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.permissions import current_user_id
from backend.jumuiya.core.responses import ok
from backend.jumuiya.biashara.analytics import service


# =========================================================
# BLUEPRINT
# =========================================================

analytics_bp = Blueprint(
    "jumuiya_biashara_analytics",
    __name__,
)


# =========================================================
# HELPERS
# =========================================================

def user_id():
    """
    Get the authenticated Jumuiya/RevelaCode user ID.
    """
    return current_user_id()


def query_days():
    """
    Read ?days= from the request.

    Allowed range:
        1 - 365 days

    Defaults to:
        30 days
    """

    value = request.args.get("days", 30)

    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 30

    return max(
        1,
        min(value, 365),
    )


# =========================================================
# OVERVIEW
# =========================================================

@analytics_bp.get("")
def analytics_overview():
    """
    GET /api/jumuiya/biashara/analytics

    Business analytics overview.
    """

    data = service.overview(
        user_id(),
        query_days(),
    )

    return ok(
        data=data,
        message="Business analytics loaded.",
    )


# =========================================================
# SALES
# =========================================================

@analytics_bp.get("/sales")
def sales_analytics():
    """
    GET /api/jumuiya/biashara/analytics/sales
    """

    data = service.sales_analytics(
        user_id(),
        query_days(),
    )

    return ok(
        data=data,
        message="Sales analytics loaded.",
    )


# =========================================================
# REVENUE
# =========================================================

@analytics_bp.get("/revenue")
def revenue_analytics():
    """
    GET /api/jumuiya/biashara/analytics/revenue
    """

    data = service.revenue_analytics(
        user_id(),
        query_days(),
    )

    return ok(
        data=data,
        message="Revenue analytics loaded.",
    )


# =========================================================
# ORDERS
# =========================================================

@analytics_bp.get("/orders")
def orders_analytics():
    """
    GET /api/jumuiya/biashara/analytics/orders
    """

    data = service.orders_analytics(
        user_id(),
        query_days(),
    )

    return ok(
        data=data,
        message="Order analytics loaded.",
    )


# =========================================================
# CUSTOMERS
# =========================================================

@analytics_bp.get("/customers")
def customers_analytics():
    """
    GET /api/jumuiya/biashara/analytics/customers
    """

    data = service.customers_analytics(
        user_id(),
        query_days(),
    )

    return ok(
        data=data,
        message="Customer analytics loaded.",
    )


# =========================================================
# PRODUCTS
# =========================================================

@analytics_bp.get("/products")
def products_analytics():
    """
    GET /api/jumuiya/biashara/analytics/products
    """

    data = service.products_analytics(
        user_id(),
        query_days(),
    )

    return ok(
        data=data,
        message="Product analytics loaded.",
    )


# =========================================================
# EXPENSES
# =========================================================

@analytics_bp.get("/expenses")
def expenses_analytics():
    """
    GET /api/jumuiya/biashara/analytics/expenses
    """

    data = service.expenses_analytics(
        user_id(),
        query_days(),
    )

    return ok(
        data=data,
        message="Expense analytics loaded.",
    )


# =========================================================
# PROFIT
# =========================================================

@analytics_bp.get("/profit")
def profit_analytics():
    """
    GET /api/jumuiya/biashara/analytics/profit
    """

    data = service.profit_analytics(
        user_id(),
        query_days(),
    )

    return ok(
        data=data,
        message="Profit analytics loaded.",
    )
