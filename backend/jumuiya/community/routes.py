from __future__ import annotations

from pymongo import ASCENDING, DESCENDING

from backend.db import get_db


def collection(name: str):
    if not name.startswith("jumuiya_"):
        raise ValueError(
            "Jumuiya collections must use the jumuiya_ prefix."
        )

    return get_db()[name]


def ensure_indexes():
    db = get_db()

    # =====================================================
    # SHARED JUMUIYA
    # =====================================================

    db["jumuiya_profiles"].create_index(
        [("user_id", ASCENDING)],
        unique=True,
    )

    db["jumuiya_transactions"].create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)]
    )

    db["jumuiya_roles"].create_index(
        [("user_id", ASCENDING), ("role", ASCENDING)],
        unique=True,
    )

    db["jumuiya_notifications"].create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)]
    )

    db["jumuiya_audit_logs"].create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)]
    )

    # =====================================================
    # MARKETPLACE
    # =====================================================

    db["jumuiya_marketplace_listings"].create_index(
        [("status", ASCENDING), ("created_at", DESCENDING)]
    )

    db["jumuiya_marketplace_listings"].create_index(
        [("hub", ASCENDING), ("category", ASCENDING)]
    )

    # =====================================================
    # BIASHARA
    # =====================================================

    db["jumuiya_businesses"].create_index(
        [("owner_user_id", ASCENDING)],
        unique=True,
    )

    db["jumuiya_businesses"].create_index(
        [("slug", ASCENDING)],
        unique=True,
    )

    db["jumuiya_products"].create_index(
        [("business_id", ASCENDING), ("status", ASCENDING)]
    )

    db["jumuiya_products"].create_index(
        [("business_id", ASCENDING), ("sku", ASCENDING)]
    )

    db["jumuiya_customers"].create_index(
        [("business_id", ASCENDING), ("created_at", DESCENDING)]
    )

    db["jumuiya_orders"].create_index(
        [("business_id", ASCENDING), ("created_at", DESCENDING)]
    )

    db["jumuiya_sales"].create_index(
        [("business_id", ASCENDING), ("sold_at", DESCENDING)]
    )

    db["jumuiya_expenses"].create_index(
        [("business_id", ASCENDING), ("spent_at", DESCENDING)]
    )

    db["jumuiya_inventory_movements"].create_index(
        [
            ("business_id", ASCENDING),
            ("product_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    return True