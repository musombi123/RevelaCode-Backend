# backend/jumuiya/marketplace/routes.py

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
from backend.jumuiya.marketplace import services


# =========================================================
# BLUEPRINT
# =========================================================

marketplace_bp = Blueprint(
    "jumuiya_marketplace",
    __name__,
)


# =========================================================
# REQUEST HELPERS
# =========================================================

def body():
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


def text(
    data,
    key,
    required=False,
    max_length=300,
):
    value = data.get(
        key,
        "",
    )

    if value is None:
        value = ""

    if not isinstance(
        value,
        str,
    ):
        raise APIError(
            f"{key} must be text.",
            422,
            "validation_error",
        )

    value = value.strip()

    if required and not value:
        raise APIError(
            f"{key} is required.",
            422,
            "validation_error",
        )

    if len(value) > max_length:
        raise APIError(
            f"{key} is too long.",
            422,
            "validation_error",
        )

    return value


def number(
    data,
    key,
    default=0,
):
    try:
        value = float(
            data.get(
                key,
                default,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        raise APIError(
            f"{key} must be a number.",
            422,
            "validation_error",
        )

    if value < 0:
        raise APIError(
            f"{key} cannot be negative.",
            422,
            "validation_error",
        )

    return value


# =========================================================
# LISTINGS
# =========================================================

@marketplace_bp.get(
    "/listings"
)
@require_authenticated
def get_listings():
    """
    Browse active marketplace listings.

    Optional filters:

        ?hub=biashara
        ?hub=shamba
        ?hub=elimu
        ?hub=community

        ?category=vegetables
    """

    return ok(
        services.listings(
            current_user_id(),
            request.args.get(
                "hub"
            ),
            request.args.get(
                "category"
            ),
        )
    )


# =========================================================
# CREATE LISTING
# =========================================================

@marketplace_bp.post(
    "/listings"
)
@require_authenticated
def add_listing():

    data = body()

    payload = {
        "title": text(
            data,
            "title",
            required=True,
            max_length=160,
        ),

        "description": text(
            data,
            "description",
            max_length=2000,
        ),

        "category": (
            text(
                data,
                "category",
                max_length=120,
            )
            or "general"
        ),

        "hub": (
            text(
                data,
                "hub",
                max_length=30,
            )
            or "community"
        ).lower(),

        "price": number(
            data,
            "price",
        ),

        "currency": (
            text(
                data,
                "currency",
                max_length=8,
            )
            or "KES"
        ).upper(),

        "unit": (
            text(
                data,
                "unit",
                max_length=40,
            )
            or "piece"
        ),

        "quantity_available": number(
            data,
            "quantity_available",
            default=1,
        ),

        "location": text(
            data,
            "location",
            max_length=200,
        ),
    }

    allowed_hubs = {
        "biashara",
        "shamba",
        "elimu",
        "community",
    }

    if payload["hub"] not in allowed_hubs:
        raise APIError(
            "Invalid marketplace hub.",
            422,
            "invalid_hub",
        )

    return created(
        services.create_listing(
            current_user_id(),
            payload,
        ),
        "Marketplace listing created.",
    )


# =========================================================
# REMOVE LISTING
# =========================================================

@marketplace_bp.delete(
    "/listings/<listing_id>"
)
@require_authenticated
def remove_listing(
    listing_id,
):

    result = services.delete_listing(
        current_user_id(),
        listing_id,
    )

    return ok(
        result,
        "Listing removed.",
    )
