# backend/jumuiya/core/database.py

from __future__ import annotations

from pymongo import ASCENDING, DESCENDING

from backend.db import get_db


# =========================================================
# JUMUIYA COLLECTION ACCESS
# =========================================================

JUMUIYA_PREFIX = "jumuiya_"


def collection(name: str):
    """
    Return a Jumuiya collection from the existing
    RevelaCode MongoDB database.

    Jumuiya collections MUST use the jumuiya_ prefix.
    """

    if not name:
        raise ValueError(
            "Collection name is required."
        )

    if not name.startswith(
        JUMUIYA_PREFIX
    ):
        raise ValueError(
            "Jumuiya collections must use "
            "the 'jumuiya_' prefix."
        )

    return get_db()[name]


# =========================================================
# INDEXES
# =========================================================

def ensure_indexes():
    """
    Create all indexes used by the Jumuiya ecosystem.

    This function is safe to call during application startup.
    Existing MongoDB indexes are preserved.
    """

    db = get_db()

    # =====================================================
    # SHARED JUMUIYA CORE
    # =====================================================

    db["jumuiya_profiles"].create_index(
        [
            ("user_id", ASCENDING),
        ],
        unique=True,
    )

    db["jumuiya_transactions"].create_index(
        [
            ("user_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_roles"].create_index(
        [
            ("user_id", ASCENDING),
            ("role", ASCENDING),
        ],
        unique=True,
    )

    db["jumuiya_notifications"].create_index(
        [
            ("user_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_audit_logs"].create_index(
        [
            ("user_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_audit_logs"].create_index(
        [
            ("resource", ASCENDING),
            ("resource_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_audit_logs"].create_index(
        [
            ("action", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    # =====================================================
    # MARKETPLACE
    # =====================================================

    db["jumuiya_marketplace_listings"].create_index(
        [
            ("status", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_marketplace_listings"].create_index(
        [
            ("hub", ASCENDING),
            ("category", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_marketplace_listings"].create_index(
        [
            ("seller_user_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    # =====================================================
    # BIASHARA
    # =====================================================

    db["jumuiya_businesses"].create_index(
        [
            ("owner_user_id", ASCENDING),
        ],
        unique=True,
    )

    db["jumuiya_businesses"].create_index(
        [
            ("slug", ASCENDING),
        ],
        unique=True,
    )

    db["jumuiya_businesses"].create_index(
        [
            ("county", ASCENDING),
            ("category", ASCENDING),
            ("status", ASCENDING),
        ]
    )

    db["jumuiya_products"].create_index(
        [
            ("business_id", ASCENDING),
            ("status", ASCENDING),
        ]
    )

    db["jumuiya_products"].create_index(
        [
            ("business_id", ASCENDING),
            ("sku", ASCENDING),
        ]
    )

    db["jumuiya_customers"].create_index(
        [
            ("business_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_orders"].create_index(
        [
            ("business_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_orders"].create_index(
        [
            ("business_id", ASCENDING),
            ("status", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_sales"].create_index(
        [
            ("business_id", ASCENDING),
            ("sold_at", DESCENDING),
        ]
    )

    db["jumuiya_expenses"].create_index(
        [
            ("business_id", ASCENDING),
            ("spent_at", DESCENDING),
        ]
    )

    db["jumuiya_inventory_movements"].create_index(
        [
            ("business_id", ASCENDING),
            ("product_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    # =====================================================
    # SHAMBA
    # =====================================================

    db["jumuiya_farmers"].create_index(
        [
            ("user_id", ASCENDING),
        ],
        unique=True,
    )

    db["jumuiya_farms"].create_index(
        [
            ("owner_user_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_farms"].create_index(
        [
            ("county", ASCENDING),
            ("status", ASCENDING),
        ]
    )

    db["jumuiya_crops"].create_index(
        [
            ("farm_id", ASCENDING),
            ("status", ASCENDING),
        ]
    )

    db["jumuiya_crops"].create_index(
        [
            ("owner_user_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_farm_activities"].create_index(
        [
            ("farm_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_harvests"].create_index(
        [
            ("farm_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_harvests"].create_index(
        [
            ("owner_user_id", ASCENDING),
            ("market_status", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_market_prices"].create_index(
        [
            ("crop", ASCENDING),
            ("county", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    # =====================================================
    # ELIMU
    # =====================================================

    db["jumuiya_education_profiles"].create_index(
        [
            ("user_id", ASCENDING),
        ],
        unique=True,
    )

    db["jumuiya_education_profiles"].create_index(
        [
            ("profile_type", ASCENDING),
            ("status", ASCENDING),
        ]
    )

    db["jumuiya_schools"].create_index(
        [
            ("owner_user_id", ASCENDING),
        ],
        unique=True,
    )

    db["jumuiya_schools"].create_index(
        [
            ("county", ASCENDING),
            ("status", ASCENDING),
        ]
    )

    db["jumuiya_classes"].create_index(
        [
            ("school_id", ASCENDING),
            ("status", ASCENDING),
        ]
    )

    db["jumuiya_lessons"].create_index(
        [
            ("subject", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_lessons"].create_index(
        [
            ("school_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_assignments"].create_index(
        [
            ("school_id", ASCENDING),
            ("class_name", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_fees"].create_index(
        [
            ("student_user_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_fees"].create_index(
        [
            ("school_id", ASCENDING),
            ("status", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_cbc_projects"].create_index(
        [
            ("student_user_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_cbc_projects"].create_index(
        [
            ("school_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    # =====================================================
    # COMMUNITY
    # =====================================================

    db["jumuiya_community_posts"].create_index(
        [
            ("status", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_community_posts"].create_index(
        [
            ("hub", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_community_posts"].create_index(
        [
            ("category", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_community_comments"].create_index(
        [
            ("post_id", ASCENDING),
            ("created_at", DESCENDING),
        ]
    )

    db["jumuiya_community_reactions"].create_index(
        [
            ("post_id", ASCENDING),
            ("user_id", ASCENDING),
        ],
        unique=True,
    )

    return True
