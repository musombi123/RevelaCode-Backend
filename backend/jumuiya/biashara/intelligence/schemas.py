# backend/jumuiya/biashara/intelligence/schemas.py

from __future__ import annotations

import re
from typing import Any


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_FORECAST_HORIZON_DAYS = 30

MIN_FORECAST_HORIZON_DAYS = 7

MAX_FORECAST_HORIZON_DAYS = 365

DEFAULT_CONFIDENCE_THRESHOLD = 0.50

MIN_CONFIDENCE_THRESHOLD = 0.0

MAX_CONFIDENCE_THRESHOLD = 1.0

MAX_PRODUCTS = 50

MAX_CATEGORIES = 20

MAX_NOTES_LENGTH = 1000

SUPPORTED_ANALYSIS_MODES = {
    "feasibility",
    "demand",
    "pricing",
    "full",
}

SUPPORTED_FORECAST_HORIZONS = {
    "short_term",
    "medium_term",
    "custom",
}


# =========================================================
# COMMON VALIDATORS
# =========================================================

def _object(
    data: Any,
):
    """
    Require a JSON object.
    """

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "JSON object required."
        )


def _text(
    data,
    key,
    required=False,
    max_len=300,
    default="",
):
    """
    Read, trim and validate a text field.
    """

    value = data.get(
        key
    )

    if value is None:
        value = default

    if not isinstance(
        value,
        str,
    ):
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
            f"{key} must not exceed {max_len} characters."
        )

    return value


def _number(
    data,
    key,
    required=False,
    minimum=None,
    maximum=None,
    default=0.0,
):
    """
    Read and validate a numeric value.
    """

    value = data.get(
        key
    )

    if value is None:

        if required:
            raise ValueError(
                f"{key} is required."
            )

        return float(
            default
        )

    try:

        value = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        raise ValueError(
            f"{key} must be a number."
        )

    if minimum is not None and value < minimum:

        raise ValueError(
            f"{key} must be at least {minimum}."
        )

    if maximum is not None and value > maximum:

        raise ValueError(
            f"{key} must not exceed {maximum}."
        )

    return value


def _integer(
    data,
    key,
    required=False,
    minimum=None,
    maximum=None,
    default=0,
):
    """
    Read and validate an integer.
    """

    value = data.get(
        key
    )

    if value is None:

        if required:
            raise ValueError(
                f"{key} is required."
            )

        return int(
            default
        )

    try:

        numeric = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        raise ValueError(
            f"{key} must be an integer."
        )

    if not numeric.is_integer():

        raise ValueError(
            f"{key} must be an integer."
        )

    value = int(
        numeric
    )

    if minimum is not None and value < minimum:

        raise ValueError(
            f"{key} must be at least {minimum}."
        )

    if maximum is not None and value > maximum:

        raise ValueError(
            f"{key} must not exceed {maximum}."
        )

    return value


def _choice(
    data,
    key,
    allowed,
    required=False,
    default=None,
):
    """
    Validate one value against a fixed set.
    """

    value = data.get(
        key
    )

    if value is None or value == "":

        if required:
            raise ValueError(
                f"{key} is required."
            )

        return default

    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            f"{key} must be text."
        )

    value = value.strip().lower()

    if value not in allowed:

        raise ValueError(
            f"{key} must be one of: "
            f"{', '.join(sorted(allowed))}."
        )

    return value


def _string_list(
    data,
    key,
    required=False,
    max_items=20,
    item_max_len=120,
):
    """
    Validate a list of strings.
    """

    value = data.get(
        key
    )

    if value is None:

        if required:
            raise ValueError(
                f"{key} is required."
            )

        return []

    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            f"{key} must be a list."
        )

    if len(value) > max_items:

        raise ValueError(
            f"{key} cannot contain more than {max_items} items."
        )

    cleaned = []

    for index, item in enumerate(
        value
    ):

        if not isinstance(
            item,
            str,
        ):
            raise ValueError(
                f"{key}[{index}] must be text."
            )

        item = item.strip()

        if not item:
            continue

        if len(item) > item_max_len:

            raise ValueError(
                f"{key}[{index}] must not exceed "
                f"{item_max_len} characters."
            )

        cleaned.append(
            item
        )

    return cleaned


# =========================================================
# LOCATION
# =========================================================

def location_payload(
    data,
):
    """
    Validate a market-intelligence location selection.

    Supported forms:

        {
            "area_id": "nyali"
        }

    or:

        {
            "area_id": "nyali",
            "center": {
                "latitude": ...,
                "longitude": ...
            }
        }

    or a drawn map selection:

        {
            "bounds": {
                "min_latitude": ...,
                "max_latitude": ...,
                "min_longitude": ...,
                "max_longitude": ...
            }
        }
    """

    _object(
        data
    )

    result = {}

    # -----------------------------------------------------
    # CONFIGURED AREA
    # -----------------------------------------------------

    area_id = data.get(
        "area_id"
    )

    if area_id is not None:

        if not isinstance(
            area_id,
            str,
        ):
            raise ValueError(
                "area_id must be text."
            )

        area_id = area_id.strip()

        if len(area_id) > 120:

            raise ValueError(
                "area_id is too long."
            )

        if area_id:

            result[
                "area_id"
            ] = area_id

    # -----------------------------------------------------
    # CENTER
    # -----------------------------------------------------

    center = data.get(
        "center"
    )

    if center is not None:

        if not isinstance(
            center,
            dict,
        ):
            raise ValueError(
                "center must be an object."
            )

        latitude = center.get(
            "latitude"
        )

        longitude = center.get(
            "longitude"
        )

        try:

            latitude = float(
                latitude
            )
            longitude = float(
                longitude
            )

        except (
            TypeError,
            ValueError,
        ):

            raise ValueError(
                "center latitude and longitude must be numbers."
            )

        if not -90 <= latitude <= 90:

            raise ValueError(
                "center latitude must be between -90 and 90."
            )

        if not -180 <= longitude <= 180:

            raise ValueError(
                "center longitude must be between -180 and 180."
            )

        result[
            "center"
        ] = {
            "latitude": latitude,
            "longitude": longitude,
        }

    # -----------------------------------------------------
    # DRAWN BOUNDS
    # -----------------------------------------------------

    bounds = data.get(
        "bounds"
    )

    if bounds is not None:

        if not isinstance(
            bounds,
            dict,
        ):
            raise ValueError(
                "bounds must be an object."
            )

        required = [
            "min_latitude",
            "max_latitude",
            "min_longitude",
            "max_longitude",
        ]

        for key in required:

            if key not in bounds:

                raise ValueError(
                    f"bounds.{key} is required."
                )

        try:

            min_latitude = float(
                bounds[
                    "min_latitude"
                ]
            )

            max_latitude = float(
                bounds[
                    "max_latitude"
                ]
            )

            min_longitude = float(
                bounds[
                    "min_longitude"
                ]
            )

            max_longitude = float(
                bounds[
                    "max_longitude"
                ]
            )

        except (
            TypeError,
            ValueError,
        ):

            raise ValueError(
                "All geographic bounds must be numbers."
            )

        if not (
            -90
            <= min_latitude
            <= 90
        ):
            raise ValueError(
                "min_latitude must be between -90 and 90."
            )

        if not (
            -90
            <= max_latitude
            <= 90
        ):
            raise ValueError(
                "max_latitude must be between -90 and 90."
            )

        if not (
            -180
            <= min_longitude
            <= 180
        ):
            raise ValueError(
                "min_longitude must be between -180 and 180."
            )

        if not (
            -180
            <= max_longitude
            <= 180
        ):
            raise ValueError(
                "max_longitude must be between -180 and 180."
            )

        if min_latitude > max_latitude:

            raise ValueError(
                "min_latitude cannot exceed max_latitude."
            )

        if min_longitude > max_longitude:

            raise ValueError(
                "min_longitude cannot exceed max_longitude."
            )

        result[
            "bounds"
        ] = {
            "min_latitude": min_latitude,
            "max_latitude": max_latitude,
            "min_longitude": min_longitude,
            "max_longitude": max_longitude,
        }

    if not result:

        raise ValueError(
            "Provide an area_id, center, or bounds."
        )

    return result


# =========================================================
# PRODUCT TARGET
# =========================================================

def product_target_payload(
    data,
):
    """
    Validate a product/service target for market analysis.

    Example:

        {
            "name": "Smartphones",
            "category": "Electronics",
            "price": 25000,
            "cost_price": 19000
        }
    """

    _object(
        data
    )

    name = _text(
        data,
        "name",
        required=True,
        max_len=160,
    )

    category = _text(
        data,
        "category",
        max_len=120,
    )

    price = _number(
        data,
        "price",
        required=False,
        minimum=0,
        default=0,
    )

    cost_price = _number(
        data,
        "cost_price",
        required=False,
        minimum=0,
        default=0,
    )

    return {
        "name": name,

        "category": category,

        "price": price,

        "cost_price": cost_price,
    }


# =========================================================
# PRODUCT TARGETS
# =========================================================

def product_targets_payload(
    data,
):
    """
    Validate one or more products/services for analysis.
    """

    _object(
        data
    )

    products = data.get(
        "products"
    )

    if products is None:

        # Support a single target for simple requests.
        product = product_target_payload(
            data
        )

        return [
            product
        ]

    if not isinstance(
        products,
        list,
    ):
        raise ValueError(
            "products must be a list."
        )

    if not products:

        raise ValueError(
            "At least one product or service is required."
        )

    if len(products) > MAX_PRODUCTS:

        raise ValueError(
            f"No more than {MAX_PRODUCTS} products or services "
            "can be analyzed at once."
        )

    return [
        product_target_payload(
            item
        )
        for item in products
    ]


# =========================================================
# BUSINESS CONTEXT
# =========================================================

def business_context_payload(
    data,
):
    """
    Validate optional business-specific context.

    This allows the predictor to use actual Biashara
    information later without making these fields mandatory
    for a first-time market analysis.
    """

    _object(
        data
    )

    business_category = _text(
        data,
        "business_category",
        max_len=120,
    )

    business_type = _text(
        data,
        "business_type",
        max_len=100,
    )

    current_products = _string_list(
        data,
        "current_products",
        max_items=MAX_PRODUCTS,
        item_max_len=160,
    )

    current_categories = _string_list(
        data,
        "current_categories",
        max_items=MAX_CATEGORIES,
        item_max_len=120,
    )

    notes = _text(
        data,
        "notes",
        max_len=MAX_NOTES_LENGTH,
    )

    return {
        "business_category": business_category,

        "business_type": business_type,

        "current_products": current_products,

        "current_categories": current_categories,

        "notes": notes,
    }


# =========================================================
# ANALYSIS OPTIONS
# =========================================================

def analysis_options_payload(
    data,
):
    """
    Validate prediction/analysis configuration.
    """

    _object(
        data
    )

    mode = _choice(
        data,
        "analysis_mode",
        SUPPORTED_ANALYSIS_MODES,
        default="full",
    )

    forecast_horizon = _choice(
        data,
        "forecast_horizon",
        SUPPORTED_FORECAST_HORIZONS,
        default="short_term",
    )

    if forecast_horizon == "short_term":

        forecast_days = _integer(
            data,
            "forecast_days",
            minimum=MIN_FORECAST_HORIZON_DAYS,
            maximum=90,
            default=30,
        )

    elif forecast_horizon == "medium_term":

        forecast_days = _integer(
            data,
            "forecast_days",
            minimum=30,
            maximum=180,
            default=90,
        )

    else:

        forecast_days = _integer(
            data,
            "forecast_days",
            minimum=MIN_FORECAST_HORIZON_DAYS,
            maximum=MAX_FORECAST_HORIZON_DAYS,
            default=DEFAULT_FORECAST_HORIZON_DAYS,
        )

    confidence_threshold = _number(
        data,
        "confidence_threshold",
        minimum=MIN_CONFIDENCE_THRESHOLD,
        maximum=MAX_CONFIDENCE_THRESHOLD,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
    )

    include_macro = bool(
        data.get(
            "include_macro",
            True,
        )
    )

    include_demographics = bool(
        data.get(
            "include_demographics",
            True,
        )
    )

    include_market_signals = bool(
        data.get(
            "include_market_signals",
            True,
        )
    )

    include_seasonality = bool(
        data.get(
            "include_seasonality",
            True,
        )
    )

    return {
        "analysis_mode": mode,

        "forecast_horizon": forecast_horizon,

        "forecast_days": forecast_days,

        "confidence_threshold": confidence_threshold,

        "include_macro": include_macro,

        "include_demographics": include_demographics,

        "include_market_signals": include_market_signals,

        "include_seasonality": include_seasonality,
    }


# =========================================================
# MAIN MARKET ANALYSIS PAYLOAD
# =========================================================

def market_analysis_payload(
    data,
):
    """
    Validate the complete Market Intelligence analysis request.

    Example request:

        {
            "location": {
                "area_id": "nyali"
            },

            "products": [
                {
                    "name": "Smartphones",
                    "category": "Electronics",
                    "price": 25000,
                    "cost_price": 19000
                }
            ],

            "business": {
                "business_category": "Electronics"
            },

            "options": {
                "analysis_mode": "full",
                "forecast_horizon": "short_term"
            }
        }
    """

    _object(
        data
    )

    # -----------------------------------------------------
    # LOCATION
    # -----------------------------------------------------

    location = data.get(
        "location"
    )

    if location is None:

        # Also allow direct top-level area_id for
        # convenient frontend requests.
        location = {
            "area_id": data.get(
                "area_id"
            )
        }

        if not location.get(
            "area_id"
        ):

            center = data.get(
                "center"
            )

            bounds = data.get(
                "bounds"
            )

            if center:
                location[
                    "center"
                ] = center

            if bounds:
                location[
                    "bounds"
                ] = bounds

    location = location_payload(
        location
    )

    # -----------------------------------------------------
    # PRODUCTS
    # -----------------------------------------------------

    products = product_targets_payload(
        data
    )

    # -----------------------------------------------------
    # BUSINESS CONTEXT
    # -----------------------------------------------------

    business = data.get(
        "business",
        {},
    )

    if business is None:
        business = {}

    business = business_context_payload(
        business
    )

    # -----------------------------------------------------
    # OPTIONS
    # -----------------------------------------------------

    options = data.get(
        "options",
        {},
    )

    if options is None:
        options = {}

    options = analysis_options_payload(
        options
    )

    # -----------------------------------------------------
    # OPTIONAL CLIENT NOTES
    # -----------------------------------------------------

    notes = _text(
        data,
        "notes",
        max_len=MAX_NOTES_LENGTH,
    )

    return {
        "location": location,

        "products": products,

        "business": business,

        "options": options,

        "notes": notes,
    }


# =========================================================
# TREND QUERY
# =========================================================

def trend_query_payload(
    data,
):
    """
    Validate a request for market/economic trends.
    """

    _object(
        data
    )

    area_id = _text(
        data,
        "area_id",
        max_len=120,
    )

    category = _text(
        data,
        "category",
        max_len=120,
    )

    indicator = _text(
        data,
        "indicator",
        max_len=120,
    )

    days = _integer(
        data,
        "days",
        minimum=1,
        maximum=3650,
        default=365,
    )

    return {
        "area_id": area_id,

        "category": category,

        "indicator": indicator,

        "days": days,
    }


# =========================================================
# AREA QUERY
# =========================================================

def area_query_payload(
    data,
):
    """
    Validate an area lookup request.
    """

    _object(
        data
    )

    area_id = _text(
        data,
        "area_id",
        max_len=120,
    )

    search = _text(
        data,
        "search",
        max_len=160,
    )

    return {
        "area_id": area_id,

        "search": search,
    }


# =========================================================
# PUBLIC EXPORTS
# =========================================================

__all__ = [
    "location_payload",
    "product_target_payload",
    "product_targets_payload",
    "business_context_payload",
    "analysis_options_payload",
    "market_analysis_payload",
    "trend_query_payload",
    "area_query_payload",
]
