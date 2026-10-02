# backend/jumuiya/biashara/analytics/service.py

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from backend.jumuiya.core.database import collection

from backend.jumuiya.biashara.services import (
    _require_business,
)

from backend.jumuiya.biashara.models import (
    DEFAULT_CURRENCY,
    PRODUCT_STATUS_ACTIVE,
)


# =========================================================
# CONSTANTS
# =========================================================

PRODUCT_ACTIVE_STATUS = PRODUCT_STATUS_ACTIVE
PRODUCT_DELETED_STATUS = "deleted"


# =========================================================
# COLLECTION HELPERS
# =========================================================

def businesses_collection():
    return collection(
        "jumuiya_businesses"
    )


def products_collection():
    return collection(
        "jumuiya_products"
    )


def customers_collection():
    return collection(
        "jumuiya_customers"
    )


def orders_collection():
    return collection(
        "jumuiya_orders"
    )


def sales_collection():
    return collection(
        "jumuiya_sales"
    )


def expenses_collection():
    return collection(
        "jumuiya_expenses"
    )


# =========================================================
# NUMERIC HELPERS
# =========================================================

def safe_float(value: Any) -> float:
    """
    Safely convert a value to float.
    """

    try:
        return float(
            value
            if value is not None
            else 0
        )

    except (
        TypeError,
        ValueError,
    ):
        return 0.0


def money(value: Any) -> float:
    """
    Normalize monetary values to two decimal places.
    """

    return round(
        safe_float(value),
        2,
    )


# =========================================================
# DATE HELPERS
# =========================================================

DEFAULT_DAYS = 30
MAX_DAYS = 365


def now_utc():
    return datetime.now(timezone.utc)


def date_bounds(days=DEFAULT_DAYS):
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = DEFAULT_DAYS

    days = max(1, min(days, MAX_DAYS))

    end = now_utc()
    start = end - timedelta(days=days)

    return start, end


def previous_period_bounds(days=DEFAULT_DAYS):
    """
    Return the immediately preceding period having the
    same length as the requested period.
    """

    try:
        days = int(days)
    except (TypeError, ValueError):
        days = DEFAULT_DAYS

    days = max(1, min(days, MAX_DAYS))

    end = now_utc()
    current_start = end - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)

    return previous_start, current_start


def percentage_change(current, previous):
    current = safe_float(current)
    previous = safe_float(previous)

    if previous == 0:
        if current == 0:
            return 0.0

        return 100.0

    return round(
        ((current - previous) / previous) * 100,
        2,
    )


# =========================================================
# COMMON AGGREGATION
# =========================================================

def aggregate_sum(
    mongo_collection,
    match,
    field,
):
    result = list(
        mongo_collection.aggregate([
            {
                "$match": match
            },
            {
                "$group": {
                    "_id": None,
                    "total": {
                        "$sum": field
                    },
                }
            },
        ])
    )

    if not result:
        return 0.0

    return money(
        result[0].get(
            "total",
            0,
        )
    )


def aggregate_count(
    mongo_collection,
    match,
):
    return mongo_collection.count_documents(
        match
    )


# =========================================================
# OVERVIEW
# =========================================================

def overview(
    user_id,
    days=DEFAULT_DAYS,
):
    """
    Main analytics overview.

    Provides current-period financial and operational
    performance together with comparison against the
    previous period.
    """

    business = _require_business(
        user_id
    )

    business_id = business["id"]

    start, end = date_bounds(days)

    previous_start, previous_end = (
        previous_period_bounds(days)
    )

    sales = sales_collection()
    orders = orders_collection()
    customers = customers_collection()
    expenses = expenses_collection()
    products = products_collection()

    current_sales = aggregate_sum(
        sales,
        {
            "business_id": business_id,
            "created_at": {
                "$gte": start,
                "$lt": end,
            },
        },
        "$amount",
    )

    previous_sales = aggregate_sum(
        sales,
        {
            "business_id": business_id,
            "created_at": {
                "$gte": previous_start,
                "$lt": previous_end,
            },
        },
        "$amount",
    )

    current_expenses = aggregate_sum(
        expenses,
        {
            "business_id": business_id,
            "created_at": {
                "$gte": start,
                "$lt": end,
            },
        },
        "$amount",
    )

    previous_expenses = aggregate_sum(
        expenses,
        {
            "business_id": business_id,
            "created_at": {
                "$gte": previous_start,
                "$lt": previous_end,
            },
        },
        "$amount",
    )

    current_orders = aggregate_count(
        orders,
        {
            "business_id": business_id,
            "created_at": {
                "$gte": start,
                "$lt": end,
            },
        },
    )

    previous_orders = aggregate_count(
        orders,
        {
            "business_id": business_id,
            "created_at": {
                "$gte": previous_start,
                "$lt": previous_end,
            },
        },
    )

    current_customers = aggregate_count(
        customers,
        {
            "business_id": business_id,
            "created_at": {
                "$gte": start,
                "$lt": end,
            },
        },
    )

    previous_customers = aggregate_count(
        customers,
        {
            "business_id": business_id,
            "created_at": {
                "$gte": previous_start,
                "$lt": previous_end,
            },
        },
    )

    current_profit = money(
        current_sales - current_expenses
    )

    previous_profit = money(
        previous_sales - previous_expenses
    )

    active_products = products.count_documents({
        "business_id": business_id,
        "status": PRODUCT_ACTIVE_STATUS,
    })

    low_stock = products.count_documents({
        "business_id": business_id,
        "status": PRODUCT_ACTIVE_STATUS,
        "$expr": {
            "$lte": [
                "$stock_quantity",
                {
                    "$ifNull": [
                        "$low_stock_threshold",
                        5.0,
                    ]
                },
            ]
        },
    })

    return {
        "period": {
            "days": days,
            "start": start.isoformat(),
            "end": end.isoformat(),
        },

        "previous_period": {
            "start": previous_start.isoformat(),
            "end": previous_end.isoformat(),
        },

        "currency": business.get(
            "currency",
            DEFAULT_CURRENCY,
        ),

        "sales": {
            "value": current_sales,
            "previous": previous_sales,
            "change_percent": percentage_change(
                current_sales,
                previous_sales,
            ),
        },

        "expenses": {
            "value": current_expenses,
            "previous": previous_expenses,
            "change_percent": percentage_change(
                current_expenses,
                previous_expenses,
            ),
        },

        "profit": {
            "value": current_profit,
            "previous": previous_profit,
            "change_percent": percentage_change(
                current_profit,
                previous_profit,
            ),
        },

        "orders": {
            "value": current_orders,
            "previous": previous_orders,
            "change_percent": percentage_change(
                current_orders,
                previous_orders,
            ),
        },

        "customers": {
            "value": current_customers,
            "previous": previous_customers,
            "change_percent": percentage_change(
                current_customers,
                previous_customers,
            ),
        },

        "products": {
            "active": active_products,
            "low_stock": low_stock,
        },
    }


# =========================================================
# SALES ANALYTICS
# =========================================================

def sales_analytics(
    user_id,
    days=DEFAULT_DAYS,
):
    business = _require_business(
        user_id
    )

    business_id = business["id"]

    start, end = date_bounds(days)

    result = list(
        sales_collection().aggregate([
            {
                "$match": {
                    "business_id": business_id,
                    "created_at": {
                        "$gte": start,
                        "$lt": end,
                    },
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$created_at",
                        }
                    },
                    "sales": {
                        "$sum": "$amount"
                    },
                    "transactions": {
                        "$sum": 1
                    },
                }
            },
            {
                "$sort": {
                    "_id": 1
                }
            },
        ])
    )

    values = {
        item["_id"]: {
            "sales": money(
                item.get(
                    "sales",
                    0,
                )
            ),
            "transactions": item.get(
                "transactions",
                0,
            ),
        }
        for item in result
    }

    trend = []

    for offset in range(days):

        day = (
            start
            + timedelta(days=offset)
        ).strftime("%Y-%m-%d")

        item = values.get(
            day,
            {},
        )

        trend.append({
            "date": day,
            "sales": item.get(
                "sales",
                0.0,
            ),
            "transactions": item.get(
                "transactions",
                0,
            ),
        })

    total_sales = sum(
        item["sales"]
        for item in trend
    )

    transactions = sum(
        item["transactions"]
        for item in trend
    )

    return {
        "currency": business.get(
            "currency",
            DEFAULT_CURRENCY,
        ),
        "period_days": days,
        "total_sales": money(
            total_sales
        ),
        "transactions": transactions,
        "average_sale": (
            money(
                total_sales / transactions
            )
            if transactions
            else 0.0
        ),
        "trend": trend,
    }


# =========================================================
# REVENUE ANALYTICS
# =========================================================

def revenue_analytics(
    user_id,
    days=DEFAULT_DAYS,
):
    business = _require_business(
        user_id
    )

    business_id = business["id"]

    start, end = date_bounds(days)

    result = list(
        sales_collection().aggregate([
            {
                "$match": {
                    "business_id": business_id,
                    "created_at": {
                        "$gte": start,
                        "$lt": end,
                    },
                }
            },
            {
                "$unwind": "$items"
            },
            {
                "$group": {
                    "_id": "$items.product_id",
                    "name": {
                        "$first": "$items.name"
                    },
                    "revenue": {
                        "$sum": "$items.line_total"
                    },
                    "units": {
                        "$sum": "$items.quantity"
                    },
                }
            },
            {
                "$sort": {
                    "revenue": -1
                }
            },
            {
                "$limit": 20
            },
        ])
    )

    products = []

    total_revenue = 0.0

    for item in result:

        revenue = money(
            item.get(
                "revenue",
                0,
            )
        )

        total_revenue += revenue

        products.append({
            "product_id": str(
                item.get(
                    "_id",
                    "",
                )
            ),
            "name": item.get(
                "name",
                "Product",
            ),
            "revenue": revenue,
            "units": safe_float(
                item.get(
                    "units",
                    0,
                )
            ),
        })

    return {
        "currency": business.get(
            "currency",
            DEFAULT_CURRENCY,
        ),
        "period_days": days,
        "total_revenue": money(
            total_revenue
        ),
        "products": products,
    }


# =========================================================
# ORDER ANALYTICS
# =========================================================

def orders_analytics(
    user_id,
    days=DEFAULT_DAYS,
):
    business = _require_business(
        user_id
    )

    business_id = business["id"]

    start, end = date_bounds(days)

    result = list(
        orders_collection().aggregate([
            {
                "$match": {
                    "business_id": business_id,
                    "created_at": {
                        "$gte": start,
                        "$lt": end,
                    },
                }
            },
            {
                "$group": {
                    "_id": "$status",
                    "count": {
                        "$sum": 1
                    },
                    "value": {
                        "$sum": "$total_amount"
                    },
                }
            },
        ])
    )

    by_status = {}

    total_orders = 0
    total_value = 0.0

    for item in result:

        status = item.get(
            "_id",
            "unknown",
        )

        count = item.get(
            "count",
            0,
        )

        value = money(
            item.get(
                "value",
                0,
            )
        )

        by_status[status] = {
            "count": count,
            "value": value,
        }

        total_orders += count
        total_value += value

    return {
        "currency": business.get(
            "currency",
            DEFAULT_CURRENCY,
        ),
        "period_days": days,
        "total_orders": total_orders,
        "total_value": money(
            total_value
        ),
        "average_order_value": (
            money(
                total_value / total_orders
            )
            if total_orders
            else 0.0
        ),
        "by_status": by_status,
    }


# =========================================================
# CUSTOMER ANALYTICS
# =========================================================

def customers_analytics(
    user_id,
    days=DEFAULT_DAYS,
):
    business = _require_business(
        user_id
    )

    business_id = business["id"]

    start, end = date_bounds(days)

    new_customers = customers_collection().count_documents({
        "business_id": business_id,
        "created_at": {
            "$gte": start,
            "$lt": end,
        },
    })

    total_customers = customers_collection().count_documents({
        "business_id": business_id
    })

    sales_customers = list(
        sales_collection().aggregate([
            {
                "$match": {
                    "business_id": business_id,
                    "created_at": {
                        "$gte": start,
                        "$lt": end,
                    },
                    "customer_id": {
                        "$exists": True,
                        "$ne": None,
                    },
                }
            },
            {
                "$group": {
                    "_id": "$customer_id",
                    "spent": {
                        "$sum": "$amount"
                    },
                    "transactions": {
                        "$sum": 1
                    },
                }
            },
            {
                "$sort": {
                    "spent": -1
                }
            },
            {
                "$limit": 20
            },
        ])
    )

    top_customers = []

    for item in sales_customers:

        top_customers.append({
            "customer_id": str(
                item.get(
                    "_id",
                    "",
                )
            ),
            "spent": money(
                item.get(
                    "spent",
                    0,
                )
            ),
            "transactions": item.get(
                "transactions",
                0,
            ),
        })

    return {
        "period_days": days,
        "total_customers": total_customers,
        "new_customers": new_customers,
        "top_customers": top_customers,
    }


# =========================================================
# PRODUCT ANALYTICS
# =========================================================

def products_analytics(
    user_id,
    days=DEFAULT_DAYS,
):
    business = _require_business(
        user_id
    )

    business_id = business["id"]

    start, end = date_bounds(days)

    product_count = products_collection().count_documents({
        "business_id": business_id,
        "status": {
            "$ne": PRODUCT_DELETED_STATUS
        },
    })

    active_count = products_collection().count_documents({
        "business_id": business_id,
        "status": PRODUCT_ACTIVE_STATUS,
    })

    low_stock_count = products_collection().count_documents({
        "business_id": business_id,
        "status": PRODUCT_ACTIVE_STATUS,
        "$expr": {
            "$lte": [
                "$stock_quantity",
                {
                    "$ifNull": [
                        "$low_stock_threshold",
                        5.0,
                    ]
                },
            ]
        },
    })

    top_products = list(
        sales_collection().aggregate([
            {
                "$match": {
                    "business_id": business_id,
                    "created_at": {
                        "$gte": start,
                        "$lt": end,
                    },
                }
            },
            {
                "$unwind": "$items"
            },
            {
                "$group": {
                    "_id": "$items.product_id",
                    "name": {
                        "$first": "$items.name"
                    },
                    "units": {
                        "$sum": "$items.quantity"
                    },
                    "revenue": {
                        "$sum": "$items.line_total"
                    },
                }
            },
            {
                "$sort": {
                    "units": -1,
                    "revenue": -1,
                }
            },
            {
                "$limit": 20
            },
        ])
    )

    best_sellers = []

    for item in top_products:

        best_sellers.append({
            "product_id": str(
                item.get(
                    "_id",
                    "",
                )
            ),
            "name": item.get(
                "name",
                "Product",
            ),
            "units": safe_float(
                item.get(
                    "units",
                    0,
                )
            ),
            "revenue": money(
                item.get(
                    "revenue",
                    0,
                )
            ),
        })

    return {
        "period_days": days,
        "total_products": product_count,
        "active_products": active_count,
        "low_stock_products": low_stock_count,
        "best_sellers": best_sellers,
    }


# =========================================================
# EXPENSE ANALYTICS
# =========================================================

def expenses_analytics(
    user_id,
    days=DEFAULT_DAYS,
):
    business = _require_business(
        user_id
    )

    business_id = business["id"]

    start, end = date_bounds(days)

    result = list(
        expenses_collection().aggregate([
            {
                "$match": {
                    "business_id": business_id,
                    "created_at": {
                        "$gte": start,
                        "$lt": end,
                    },
                }
            },
            {
                "$group": {
                    "_id": {
                        "$ifNull": [
                            "$category",
                            "Other",
                        ]
                    },
                    "amount": {
                        "$sum": "$amount"
                    },
                    "count": {
                        "$sum": 1
                    },
                }
            },
            {
                "$sort": {
                    "amount": -1
                }
            },
        ])
    )

    categories = []

    total_expenses = 0.0

    for item in result:

        amount = money(
            item.get(
                "amount",
                0,
            )
        )

        total_expenses += amount

        categories.append({
            "category": item.get(
                "_id",
                "Other",
            ),
            "amount": amount,
            "count": item.get(
                "count",
                0,
            ),
        })

    return {
        "currency": business.get(
            "currency",
            DEFAULT_CURRENCY,
        ),
        "period_days": days,
        "total_expenses": money(
            total_expenses
        ),
        "categories": categories,
    }


# =========================================================
# PROFIT ANALYTICS
# =========================================================

def profit_analytics(
    user_id,
    days=DEFAULT_DAYS,
):
    business = _require_business(
        user_id
    )

    business_id = business["id"]

    start, end = date_bounds(days)

    revenue = aggregate_sum(
        sales_collection(),
        {
            "business_id": business_id,
            "created_at": {
                "$gte": start,
                "$lt": end,
            },
        },
        "$amount",
    )

    expenses = aggregate_sum(
        expenses_collection(),
        {
            "business_id": business_id,
            "created_at": {
                "$gte": start,
                "$lt": end,
            },
        },
        "$amount",
    )

    profit = money(
        revenue - expenses
    )

    margin = (
        round(
            (profit / revenue) * 100,
            2,
        )
        if revenue
        else 0.0
    )

    return {
        "currency": business.get(
            "currency",
            DEFAULT_CURRENCY,
        ),
        "period_days": days,
        "revenue": revenue,
        "expenses": expenses,
        "profit": profit,
        "profit_margin": margin,
    }
