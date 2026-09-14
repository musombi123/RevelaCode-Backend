# backend/jumuiya/biashara/analytics/routes.py

from flask import Blueprint, request

from backend.jumuiya.core.identity import current_user_id
from backend.jumuiya.core.responses import success_response

from backend.jumuiya.biashara.analytics import service


analytics_bp = Blueprint(
    "jumuiya_biashara_analytics",
    __name__,
)


# =========================================================
# HELPERS
# =========================================================

def user_id():
    return current_user_id()


def query_days():
    value = request.args.get(
        "days",
        30,
    )

    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 30

    return max(
        1,
        min(
            value,
            365,
        ),
    )


# =========================================================
# OVERVIEW
# =========================================================

@analytics_bp.get("")
def analytics_overview():

    data = service.overview(
        user_id(),
        query_days(),
    )

    return success_response(
        data
    )


# =========================================================
# SALES
# =========================================================

@analytics_bp.get("/sales")
def analytics_sales():

    data = service.sales_analytics(
        user_id(),
        query_days(),
    )

    return success_response(
        data
    )


# =========================================================
# REVENUE
# =========================================================

@analytics_bp.get("/revenue")
def analytics_revenue():

    data = service.revenue_analytics(
        user_id(),
        query_days(),
    )

    return success_response(
        data
    )


# =========================================================
# ORDERS
# =========================================================

@analytics_bp.get("/orders")
def analytics_orders():

    data = service.orders_analytics(
        user_id(),
        query_days(),
    )

    return success_response(
        data
    )


# =========================================================
# CUSTOMERS
# =========================================================

@analytics_bp.get("/customers")
def analytics_customers():

    data = service.customers_analytics(
        user_id(),
        query_days(),
    )

    return success_response(
        data
    )


# =========================================================
# PRODUCTS
# =========================================================

@analytics_bp.get("/products")
def analytics_products():

    data = service.products_analytics(
        user_id(),
        query_days(),
    )

    return success_response(
        data
    )


# =========================================================
# EXPENSES
# =========================================================

@analytics_bp.get("/expenses")
def analytics_expenses():

    data = service.expenses_analytics(
        user_id(),
        query_days(),
    )

    return success_response(
        data
    )


# =========================================================
# PROFIT
# =========================================================

@analytics_bp.get("/profit")
def analytics_profit():

    data = service.profit_analytics(
        user_id(),
        query_days(),
    )

    return success_response(
        data
    )
