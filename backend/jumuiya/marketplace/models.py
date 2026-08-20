# backend/jumuiya/marketplace/models.py

from __future__ import annotations

from datetime import datetime, timezone


# =========================================================
# TIME
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


# =========================================================
# LISTING DOCUMENT
# =========================================================

def listing_document(user_id, data):
    """
    Create a Jumuiya marketplace listing.

    Marketplace is shared across:

        Biashara
        Shamba
        Elimu
        Community

    `seller_user_id` always points back to the existing
    RevelaCode/Jumuiya identity.
    """

    if user_id is None:
        raise ValueError(
            "seller user ID is required."
        )

    if not isinstance(data, dict):
        raise ValueError(
            "Listing data must be a dictionary."
        )

    title = str(
        data.get("title", "")
        or ""
    ).strip()

    if not title:
        raise ValueError(
            "Listing title is required."
        )

    description = str(
        data.get("description", "")
        or ""
    ).strip()

    category = str(
        data.get(
            "category",
            "general",
        )
        or "general"
    ).strip().lower()

    hub = str(
        data.get(
            "hub",
            "community",
        )
        or "community"
    ).strip().lower()

    allowed_hubs = {
        "biashara",
        "shamba",
        "elimu",
        "community",
    }

    if hub not in allowed_hubs:
        raise ValueError(
            "hub must be biashara, shamba, elimu, or community."
        )

    try:
        price = float(
            data.get(
                "price",
                0,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "price must be a number."
        )

    if price < 0:
        raise ValueError(
            "price cannot be negative."
        )

    try:
        quantity = float(
            data.get(
                "quantity_available",
                1,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "quantity_available must be a number."
        )

    if quantity < 0:
        raise ValueError(
            "quantity_available cannot be negative."
        )

    currency = str(
        data.get(
            "currency",
            "KES",
        )
        or "KES"
    ).strip().upper()

    if len(currency) != 3:
        raise ValueError(
            "currency must be a 3-letter currency code."
        )

    unit = str(
        data.get(
            "unit",
            "piece",
        )
        or "piece"
    ).strip()

    location = str(
        data.get(
            "location",
            "",
        )
        or ""
    ).strip()

    now = now_utc()

    return {
        "seller_user_id": str(
            user_id
        ),

        "title": title,

        "description": description,

        "category": category,

        "hub": hub,

        "price": price,

        "currency": currency,

        "unit": unit,

        "quantity_available": quantity,

        "location": location,

        "status": "active",

        "created_at": now,

        "updated_at": now,
    }