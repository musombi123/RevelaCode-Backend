# backend/jumuiya/biashara/intelligence/service.py

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.biashara import services as biashara_services

from backend.jumuiya.biashara.intelligence.geography import (
    find_area,
    nearest_area,
    normalize_area,
    normalize_map_selection,
)

from backend.jumuiya.biashara.intelligence.scoring import (
    category_market_score,
    calculate_confidence,
    clamp,
    explain_score,
)

from backend.jumuiya.biashara.intelligence.forecasting import (
    demand_forecast,
    forecast_product,
    macro_demand_adjustment,
)

from backend.jumuiya.biashara.intelligence.recommendations import (
    generate_recommendations,
    recommendation_summary,
    top_recommendations,
)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data",
)

AREAS_FILE = os.path.join(
    DATA_DIR,
    "kenya_locations_merged.json",
)

DEMOGRAPHICS_FILE = os.path.join(
    DATA_DIR,
    "demographics.json",
)

ECONOMIC_FILE = os.path.join(
    DATA_DIR,
    "economic_indicators.json",
)

MARKET_SIGNALS_FILE = os.path.join(
    DATA_DIR,
    "market_signals.json",
)


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_CURRENCY = "KES"

DEFAULT_FORECAST_DAYS = 30

DEFAULT_AREA_RADIUS_KM = 15

DATA_VERSION = "1.0"


# =========================================================
# TIME
# =========================================================

def now_utc() -> datetime:
    return datetime.now(
        timezone.utc
    )


# =========================================================
# SAFE VALUE HELPERS
# =========================================================

def as_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return default


def as_string(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(
        value
    ).strip()


def as_dict(
    value: Any,
) -> dict:
    if isinstance(
        value,
        dict,
    ):
        return value

    return {}


def as_list(
    value: Any,
) -> list:
    if isinstance(
        value,
        list,
    ):
        return value

    return []


# =========================================================
# FILE DATA LOADING
# =========================================================

def _load_json_file(
    filepath: str,
    default: Any,
):
    """
    Safely load a local intelligence dataset.

    Returning the supplied default instead of crashing allows
    the API to remain available while a dataset is missing
    or temporarily malformed.
    """

    if not os.path.exists(
        filepath
    ):
        return default

    try:

        with open(
            filepath,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        return data

    except (
        json.JSONDecodeError,
        OSError,
        TypeError,
    ):

        return default


def load_areas() -> list[dict]:
    """
    Load configured geographic market areas.
    """

    data = _load_json_file(
        AREAS_FILE,
        [],
    )

    if isinstance(
        data,
        dict,
    ):

        areas = (
            data.get(
                "areas"
            )
            or data.get(
                "data"
            )
            or []
        )

    else:

        areas = data

    if not isinstance(
        areas,
        list,
    ):
        return []

    normalized = []

    for item in areas:

        if not isinstance(
            item,
            dict,
        ):
            continue

        try:

            normalized.append(
                normalize_area(
                    item
                )
            )

        except ValueError:

            continue

    return normalized


def load_demographics() -> dict:
    """
    Load demographic data.

    Expected general structure:

        {
            "nyali": {
                ...
            }
        }

    Or:

        {
            "areas": {
                "nyali": {
                    ...
                }
            }
        }
    """

    data = _load_json_file(
        DEMOGRAPHICS_FILE,
        {},
    )

    if not isinstance(
        data,
        dict,
    ):
        return {}

    areas = data.get(
        "areas"
    )

    if isinstance(
        areas,
        dict,
    ):
        return areas

    return data


def load_economic_indicators() -> dict:
    """
    Load macro-economic indicators.
    """

    data = _load_json_file(
        ECONOMIC_FILE,
        {},
    )

    if not isinstance(
        data,
        dict,
    ):
        return {}

    return data


def load_market_signals() -> dict:
    """
    Load current market-demand and competition signals.
    """

    data = _load_json_file(
        MARKET_SIGNALS_FILE,
        {},
    )

    if not isinstance(
        data,
        dict,
    ):
        return {}

    return data


# =========================================================
# DATA ACCESS HELPERS
# =========================================================

def _lookup_area_dataset(
    dataset: dict,
    area: dict,
) -> dict:
    """
    Find area-specific data using multiple identifiers.
    """

    if not isinstance(
        dataset,
        dict,
    ):
        return {}

    area_id = as_string(
        area.get(
            "id"
        )
    )

    area_name = as_string(
        area.get(
            "name"
        )
    ).lower()

    sub_county = as_string(
        area.get(
            "sub_county"
        )
    ).lower()

    candidates = [
        area_id,
        area_name,
        sub_county,
    ]

    for candidate in candidates:

        if not candidate:
            continue

        if candidate in dataset:

            value = dataset.get(
                candidate
            )

            if isinstance(
                value,
                dict,
            ):
                return value

    # Case-insensitive fallback.
    normalized_keys = {
        as_string(key).lower(): value
        for key, value in dataset.items()
    }

    for candidate in candidates:

        if not candidate:
            continue

        value = normalized_keys.get(
            candidate.lower()
        )

        if isinstance(
            value,
            dict,
        ):
            return value

    return {}


def _lookup_category_dataset(
    dataset: dict,
    category: str,
) -> dict:
    """
    Find category-specific market information.
    """

    if not isinstance(
        dataset,
        dict,
    ):
        return {}

    category = as_string(
        category
    ).lower()

    if not category:
        return {}

    if category in dataset:

        value = dataset.get(
            category
        )

        return (
            value
            if isinstance(
                value,
                dict,
            )
            else {}
        )

    normalized = {
        as_string(key).lower(): value
        for key, value in dataset.items()
    }

    value = normalized.get(
        category
    )

    return (
        value
        if isinstance(
            value,
            dict,
        )
        else {}
    )


# =========================================================
# BUSINESS CONTEXT
# =========================================================

def get_business_context(
    user_id,
) -> dict:
    """
    Obtain the authenticated user's Biashara business,
    if one exists.

    Market Intelligence is allowed to run without an
    existing business account for discovery purposes.
    """

    business = (
        biashara_services.get_business_for_user(
            user_id
        )
    )

    if not isinstance(
        business,
        dict,
    ):
        return {}

    return business


def _business_performance(
    user_id,
) -> dict:
    """
    Pull lightweight business performance data from the
    existing Biashara dashboard.

    Failure to load business dashboard data should not
    prevent a general market analysis.
    """

    try:

        dashboard = (
            biashara_services.dashboard(
                user_id
            )
        )

    except Exception:

        return {}

    if not isinstance(
        dashboard,
        dict,
    ):
        return {}

    metrics = as_dict(
        dashboard.get(
            "metrics"
        )
    )

    sales_total = as_float(
        metrics.get(
            "sales_total"
        )
    )

    completed_orders = as_float(
        metrics.get(
            "completed_orders"
        )
    )

    customers = as_float(
        metrics.get(
            "customers"
        )
    )

    average_order_value = (
        as_float(
            metrics.get(
                "average_order_value"
            )
        )
    )

    if (
        average_order_value <= 0
        and completed_orders > 0
    ):

        average_order_value = (
            sales_total
            / completed_orders
        )

    return {
        "sales_total": sales_total,

        "completed_orders": (
            completed_orders
        ),

        "customers": customers,

        "average_order_value": (
            average_order_value
        ),
    }


# =========================================================
# AREA RESOLUTION
# =========================================================

def resolve_location(
    selection: dict,
    areas: list[dict] | None = None,
) -> dict:
    """
    Resolve an intelligence location selection to a
    configured market area where possible.
    """

    if not isinstance(
        selection,
        dict,
    ):
        raise APIError(
            "Location selection is required.",
            422,
            "invalid_location",
        )

    normalized_selection = (
        normalize_map_selection(
            selection
        )
    )

    areas = (
        areas
        if isinstance(
            areas,
            list,
        )
        else load_areas()
    )

    # -----------------------------------------------------
    # Explicit area
    # -----------------------------------------------------

    area_id = normalized_selection.get(
        "area_id"
    )

    if area_id:

        area = find_area(
            areas,
            area_id,
        )

        if area:

            return {
                "selection": normalized_selection,
                "area": area,
                "match_type": "configured_area",
            }

        raise APIError(
            f"Market area '{area_id}' was not found.",
            404,
            "area_not_found",
        )

    # -----------------------------------------------------
    # Center-point selection
    # -----------------------------------------------------

    center = normalized_selection.get(
        "center"
    )

    if center:

        result = nearest_area(
            areas,
            center[
                "latitude"
            ],
            center[
                "longitude"
            ],
        )

        if result:

            return {
                "selection": normalized_selection,
                "area": result[
                    "area"
                ],
                "distance_km": result[
                    "distance_km"
                ],
                "match_type": "nearest_configured_area",
            }

    # -----------------------------------------------------
    # Drawn bounds
    # -----------------------------------------------------

    bounds = normalized_selection.get(
        "bounds"
    )

    if bounds:

        center_latitude = (
            (
                bounds[
                    "min_latitude"
                ]
                +
                bounds[
                    "max_latitude"
                ]
            )
            / 2
        )

        center_longitude = (
            (
                bounds[
                    "min_longitude"
                ]
                +
                bounds[
                    "max_longitude"
                ]
            )
            / 2
        )

        result = nearest_area(
            areas,
            center_latitude,
            center_longitude,
        )

        if result:

            return {
                "selection": normalized_selection,
                "area": result[
                    "area"
                ],
                "distance_km": result[
                    "distance_km"
                ],
                "match_type": "nearest_configured_area",
            }

        return {
            "selection": normalized_selection,
            "area": None,
            "match_type": "custom_bounds",
        }

    raise APIError(
        "Unable to resolve market location.",
        422,
        "location_resolution_failed",
    )


# =========================================================
# MARKET SIGNAL RESOLUTION
# =========================================================

def resolve_market_data(
    area: dict | None,
    category: str,
    market_dataset: dict | None,
) -> dict:
    """
    Combine area-level and category-level market signals.
    """

    market_dataset = (
        market_dataset
        if isinstance(
            market_dataset,
            dict,
        )
        else {}
    )

    area_data = {}

    category_data = {}

    if area:

        area_data = _lookup_area_dataset(
            market_dataset,
            area,
        )

    # Some datasets use a structure such as:
    #
    # {
    #   "areas": {...},
    #   "categories": {...}
    # }

    if "areas" in market_dataset:

        structured_areas = market_dataset.get(
            "areas"
        )

        if isinstance(
            structured_areas,
            dict,
        ) and area:

            area_data = (
                _lookup_area_dataset(
                    structured_areas,
                    area,
                )
                or area_data
            )

    if "categories" in market_dataset:

        structured_categories = (
            market_dataset.get(
                "categories"
            )
        )

        if isinstance(
            structured_categories,
            dict,
        ):

            category_data = (
                _lookup_category_dataset(
                    structured_categories,
                    category,
                )
            )

    else:

        category_data = (
            _lookup_category_dataset(
                market_dataset,
                category,
            )
        )

    result = {}

    result.update(
        category_data
    )

    result.update(
        area_data
    )

    return result


# =========================================================
# ECONOMIC DATA RESOLUTION
# =========================================================

def resolve_economic_data(
    economic_dataset: dict,
    category: str = "",
) -> dict:
    """
    Resolve current economic indicators.

    Handles both direct indicators and category-specific
    structures.
    """

    if not isinstance(
        economic_dataset,
        dict,
    ):
        return {}

    result = {}

    indicators = economic_dataset.get(
        "indicators"
    )

    if isinstance(
        indicators,
        dict,
    ):

        result.update(
            indicators
        )

    else:

        # Copy direct scalar indicators.
        for key, value in economic_dataset.items():

            if isinstance(
                value,
                (
                    int,
                    float,
                ),
            ):

                result[
                    key
                ] = value

    categories = economic_dataset.get(
        "categories"
    )

    if (
        isinstance(
            categories,
            dict,
        )
        and category
    ):

        category_data = (
            _lookup_category_dataset(
                categories,
                category,
            )
        )

        if category_data:

            result.update(
                category_data
            )

    return result


# =========================================================
# DEMOGRAPHIC TARGET PROFILE
# =========================================================

def infer_target_profile(
    product: dict,
) -> dict:
    """
    Create a conservative market-fit profile from a
    product/service category.

    This is a simple MVP rule layer. It does not infer
    characteristics about individual users.
    """

    category = as_string(
        product.get(
            "category"
        )
    ).lower()

    name = as_string(
        product.get(
            "name"
        )
    ).lower()

    text = (
        f"{category} {name}"
    )

    profile = {
        "youth": 1.0,
        "working_age": 1.0,
        "senior": 1.0,
        "households": 1.0,
        "density": 1.0,
    }

    youth_terms = {
        "fashion",
        "gaming",
        "phone",
        "smartphone",
        "electronics",
        "entertainment",
        "education",
        "student",
        "sports",
    }

    household_terms = {
        "grocery",
        "food",
        "furniture",
        "household",
        "appliance",
        "water",
        "retail",
    }

    professional_terms = {
        "consulting",
        "professional",
        "office",
        "finance",
        "accounting",
        "business",
        "logistics",
    }

    if any(
        term in text
        for term in youth_terms
    ):

        profile[
            "youth"
        ] = 1.30

        profile[
            "density"
        ] = 1.10

    if any(
        term in text
        for term in household_terms
    ):

        profile[
            "households"
        ] = 1.30

    if any(
        term in text
        for term in professional_terms
    ):

        profile[
            "working_age"
        ] = 1.30

    return profile


# =========================================================
# PRODUCT HISTORY
# =========================================================

def load_product_history(
    user_id,
    product: dict,
) -> list[dict]:
    """
    Attempt to use current Biashara sales history for
    a matching product.

    The current service layer stores sale snapshots,
    so history is reconstructed from existing sales.
    """

    name = as_string(
        product.get(
            "name"
        )
    ).lower()

    if not name:
        return []

    try:

        business = (
            biashara_services.get_business_for_user(
                user_id
            )
        )

        if not isinstance(
            business,
            dict,
        ):
            return []

        business_id = business.get(
            "id"
        )

        if not business_id:
            return []

        from backend.jumuiya.core.database import collection

        sales = collection(
            "jumuiya_sales"
        )

        documents = (
            sales.find({
                "business_id": str(
                    business_id
                )
            })
            .sort(
                "sold_at",
                1,
            )
        )

    except Exception:

        return []

    history = []

    for sale in documents:

        if not isinstance(
            sale,
            dict,
        ):
            continue

        sold_at = (
            sale.get(
                "sold_at"
            )
            or sale.get(
                "created_at"
            )
        )

        items = sale.get(
            "items",
            []
        )

        if not isinstance(
            items,
            list,
        ):
            continue

        quantity_total = 0.0

        for item in items:

            if not isinstance(
                item,
                dict,
            ):
                continue

            item_name = as_string(
                item.get(
                    "name"
                )
            ).lower()

            if item_name != name:
                continue

            quantity_total += (
                as_float(
                    item.get(
                        "quantity"
                    )
                )
            )

        if quantity_total <= 0:
            continue

        history.append({
            "date": (
                sold_at.isoformat()
                if hasattr(
                    sold_at,
                    "isoformat",
                )
                else as_string(
                    sold_at
                )
            ),
            "value": quantity_total,
        })

    return history


# =========================================================
# PRODUCT MARKET CONTEXT
# =========================================================

def build_product_context(
    user_id,
    product: dict,
    area: dict | None,
    demographics_dataset: dict,
    economic_dataset: dict,
    market_dataset: dict,
) -> dict:
    """
    Construct the full analytical context for a single
    product/service.
    """

    category = as_string(
        product.get(
            "category"
        )
    )

    demographics = {}

    if area:

        demographics = (
            _lookup_area_dataset(
                demographics_dataset,
                area,
            )
        )

        if "areas" in demographics_dataset:

            structured = (
                demographics_dataset.get(
                    "areas"
                )
            )

            if isinstance(
                structured,
                dict,
            ):

                demographics = (
                    _lookup_area_dataset(
                        structured,
                        area,
                    )
                    or demographics
                )

    market = resolve_market_data(
        area,
        category,
        market_dataset,
    )

    economics = resolve_economic_data(
        economic_dataset,
        category,
    )

    business_performance = (
        _business_performance(
            user_id
        )
    )

    # -----------------------------------------------------
    # Product history
    # -----------------------------------------------------

    history = load_product_history(
        user_id,
        product,
    )

    # -----------------------------------------------------
    # Inject history-derived growth when available
    # -----------------------------------------------------

    if history:

        values = [
            as_float(
                item.get(
                    "value"
                )
            )
            for item in history
            if isinstance(
                item,
                dict,
            )
        ]

        if len(values) >= 2:

            start = values[0]
            end = values[-1]

            if start > 0:

                market[
                    "sales_growth"
                ] = (
                    end - start
                ) / start

    return {
        "product": product,

        "category": category,

        "demographics": demographics,

        "market": market,

        "economics": economics,

        "business": business_performance,

        "history": history,
    }


# =========================================================
# FORECAST CONTEXT
# =========================================================

def _seasonal_index(
    data: dict,
) -> float:
    """
    Safely resolve a seasonal multiplier.
    """

    for key in (
        "seasonal_index",
        "demand_multiplier",
    ):

        if data.get(
            key
        ) is not None:

            value = as_float(
                data.get(
                    key
                ),
                1.0,
            )

            if value < 0:
                return 1.0

            return value

    return 1.0


def _macro_multiplier(
    economics: dict,
) -> float:
    """
    Convert macro conditions into a demand multiplier.
    """

    return macro_demand_adjustment(
        inflation=as_float(
            economics.get(
                "inflation"
            )
        ),
        transport_inflation=as_float(
            economics.get(
                "transport_inflation"
            )
        ),
        supply_pressure=as_float(
            economics.get(
                "supply_pressure"
            )
        ),
        demand_sensitivity=as_float(
            economics.get(
                "demand_sensitivity",
                0.5,
            ),
            0.5,
        ),
    )


# =========================================================
# SINGLE PRODUCT ANALYSIS
# =========================================================

def analyze_product(
    user_id,
    product: dict,
    area: dict | None,
    demographics_dataset: dict,
    economic_dataset: dict,
    market_dataset: dict,
    forecast_days: int = DEFAULT_FORECAST_DAYS,
) -> dict:
    """
    Analyze a single product/service within a market area.
    """

    context = build_product_context(
        user_id,
        product,
        area,
        demographics_dataset,
        economic_dataset,
        market_dataset,
    )

    demographics = context[
        "demographics"
    ]

    market = context[
        "market"
    ]

    economics = context[
        "economics"
    ]

    business_data = context[
        "business"
    ]

    history = context[
        "history"
    ]

    # -----------------------------------------------------
    # Resolve individual signals
    # -----------------------------------------------------

    target_profile = (
        infer_target_profile(
            product
        )
    )

    scores = category_market_score(
        demographics=demographics,
        market=market,
        economics=economics,
        competition=market,
        seasonality=market,
        business=business_data,
        target_profile=target_profile,
    )

    # -----------------------------------------------------
    # Forecast
    # -----------------------------------------------------

    seasonal_index = _seasonal_index(
        market
    )

    macro_multiplier = _macro_multiplier(
        economics
    )

    forecast_input = {
        **product,
        "sales_history": history,
        "seasonal_index": seasonal_index,
        "macro_multiplier": macro_multiplier,
    }

    forecast = forecast_product(
        forecast_input,
        forecast_days=forecast_days,
    )

    # -----------------------------------------------------
    # Confidence
    # -----------------------------------------------------

    source_count = 0

    if demographics:
        source_count += 1

    if economics:
        source_count += 1

    if market:
        source_count += 1

    if history:
        source_count += 1

    confidence = calculate_confidence(
        available_sources=source_count,
        total_expected_sources=4,
        data_freshness_score=(
            as_float(
                market.get(
                    "data_freshness_score",
                    70,
                ),
                70,
            )
        ),
        consistency_score=(
            as_float(
                market.get(
                    "consistency_score",
                    75,
                ),
                75,
            )
        ),
    )

    # -----------------------------------------------------
    # Recommendations
    # -----------------------------------------------------

    recommendation_scores = (
        scores.get(
            "signals",
            {}
        )
    )

    recommendations = (
        generate_recommendations(
            scores=recommendation_scores,
            forecast=forecast.get(
                "forecast",
                {}
            )
            if isinstance(
                forecast.get(
                    "forecast"
                ),
                dict,
            )
            else forecast,
            demographics=demographics,
            economics=economics,
            market=market,
            competition=market,
            seasonality=market,
            business=business_data,
            product=product,
            confidence=confidence,
        )
    )

    recommendations = top_recommendations(
        recommendations,
        6,
    )

    # -----------------------------------------------------
    # Explanations
    # -----------------------------------------------------

    explanations = explain_score(
        scores
    )

    # -----------------------------------------------------
    # Demand outlook
    # -----------------------------------------------------

    forecast_summary = as_dict(
        forecast.get(
            "forecast",
        )
    )

    direction = as_string(
        forecast_summary.get(
            "summary",
            {}
        ).get(
            "direction"
        )
        if isinstance(
            forecast_summary.get(
                "summary",
                {}
            ),
            dict,
        )
        else
        forecast.get(
            "summary",
            {}
        ).get(
            "direction"
        )
        if isinstance(
            forecast.get(
                "summary",
                {}
            ),
            dict,
        )
        else ""
    ).lower()

    if not direction:

        direction = as_string(
            forecast.get(
                "summary",
                {}
            ).get(
                "direction",
                "stable",
            )
            if isinstance(
                forecast.get(
                    "summary",
                    {},
                ),
                dict,
            )
            else "stable"
        ).lower()

    return {
        "product": {
            "name": product.get(
                "name",
                "",
            ),
            "category": product.get(
                "category",
                "",
            ),
            "price": as_float(
                product.get(
                    "price"
                )
            ),
            "cost_price": as_float(
                product.get(
                    "cost_price"
                )
            ),
        },

        "score": scores.get(
            "score",
            50,
        ),

        "score_label": scores.get(
            "label",
            "moderate",
        ),

        "score_level": scores.get(
            "level",
            "medium",
        ),

        "signals": scores.get(
            "signals",
            {},
        ),

        "explanations": explanations,

        "forecast": forecast,

        "demand_outlook": {
            "direction": direction,
            "confidence": forecast.get(
                "confidence",
                0.0,
            ),
        },

        "confidence": confidence,

        "recommendations": recommendations,

        "data": {
            "demographics": demographics,
            "market": market,
            "economics": economics,
            "business": business_data,
            "history_points": len(
                history
            ),
        },
    }


# =========================================================
# FULL MARKET ANALYSIS
# =========================================================

def analyze_market(
    user_id,
    payload: dict,
) -> dict:
    """
    Run a complete location + category + product market
    intelligence analysis.
    """

    if not isinstance(
        payload,
        dict,
    ):
        raise APIError(
            "Analysis payload is required.",
            422,
            "invalid_payload",
        )

    # -----------------------------------------------------
    # Load datasets
    # -----------------------------------------------------

    areas = load_areas()

    demographics_dataset = (
        load_demographics()
    )

    economic_dataset = (
        load_economic_indicators()
    )

    market_dataset = (
        load_market_signals()
    )

    # -----------------------------------------------------
    # Resolve location
    # -----------------------------------------------------

    location = resolve_location(
        payload.get(
            "location",
            {}
        ),
        areas,
    )

    area = location.get(
        "area"
    )

    # -----------------------------------------------------
    # Products
    # -----------------------------------------------------

    products = as_list(
        payload.get(
            "products"
        )
    )

    if not products:

        raise APIError(
            "At least one product or service is required.",
            422,
            "products_required",
        )

    options = as_dict(
        payload.get(
            "options"
        )
    )

    forecast_days = int(
        options.get(
            "forecast_days",
            DEFAULT_FORECAST_DAYS,
        )
    )

    forecast_days = max(
        7,
        min(
            forecast_days,
            365,
        )
    )

    # -----------------------------------------------------
    # Analyze products
    # -----------------------------------------------------

    product_results = []

    for product in products:

        if not isinstance(
            product,
            dict,
        ):
            continue

        result = analyze_product(
            user_id=user_id,
            product=product,
            area=area,
            demographics_dataset=(
                demographics_dataset
            ),
            economic_dataset=(
                economic_dataset
            ),
            market_dataset=(
                market_dataset
            ),
            forecast_days=forecast_days,
        )

        product_results.append(
            result
        )

    if not product_results:

        raise APIError(
            "No valid products were available for analysis.",
            422,
            "invalid_products",
        )

    # -----------------------------------------------------
    # Overall score
    # -----------------------------------------------------

    product_scores = [
        as_float(
            item.get(
                "score",
                0,
            )
        )
        for item in product_results
    ]

    overall_score = round(
        sum(
            product_scores
        )
        / len(
            product_scores
        ),
        2,
    )

    # -----------------------------------------------------
    # Aggregate confidence
    # -----------------------------------------------------

    product_confidences = [
        as_float(
            item.get(
                "confidence",
                0,
            )
        )
        for item in product_results
    ]

    overall_confidence = round(
        sum(
            product_confidences
        )
        / len(
            product_confidences
        ),
        3,
    )

    # -----------------------------------------------------
    # Aggregate recommendations
    # -----------------------------------------------------

    all_recommendations = []

    for item in product_results:

        all_recommendations.extend(
            as_list(
                item.get(
                    "recommendations"
                )
            )
        )

    recommendation_info = (
        recommendation_summary(
            all_recommendations
        )
    )

    # -----------------------------------------------------
    # Average signal values
    # -----------------------------------------------------

    signal_names = [
        "demographic_fit",
        "demand_signal",
        "price_environment",
        "competition",
        "seasonality",
        "business_performance",
    ]

    aggregated_signals = {}

    for signal_name in signal_names:

        values = []

        for item in product_results:

            signals = as_dict(
                item.get(
                    "signals"
                )
            )

            if signal_name in signals:

                values.append(
                    as_float(
                        signals[
                            signal_name
                        ]
                    )
                )

        aggregated_signals[
            signal_name
        ] = round(
            (
                sum(values)
                / len(values)
            )
            if values
            else 50.0,
            2,
        )

    # -----------------------------------------------------
    # Overall label
    # -----------------------------------------------------

    if overall_score >= 80:
        overall_label = "excellent"

    elif overall_score >= 65:
        overall_label = "strong"

    elif overall_score >= 50:
        overall_label = "moderate"

    elif overall_score >= 35:
        overall_label = "risky"

    else:
        overall_label = "weak"

    # -----------------------------------------------------
    # Forecast summary
    # -----------------------------------------------------

    forecast_directions = []

    for item in product_results:

        outlook = as_dict(
            item.get(
                "demand_outlook"
            )
        )

        direction = as_string(
            outlook.get(
                "direction"
            )
        ).lower()

        if direction:
            forecast_directions.append(
                direction
            )

    rising = forecast_directions.count(
        "rising"
    )

    falling = forecast_directions.count(
        "falling"
    )

    if rising > falling and rising > 0:

        overall_demand_direction = (
            "rising"
        )

    elif falling > rising and falling > 0:

        overall_demand_direction = (
            "falling"
        )

    else:

        overall_demand_direction = (
            "stable"
        )

    # -----------------------------------------------------
    # Location response
    # -----------------------------------------------------

    area_response = None

    if area:

        area_response = {
            "id": area.get(
                "id"
            ),
            "name": area.get(
                "name"
            ),
            "sub_county": area.get(
                "sub_county"
            ),
            "county": area.get(
                "county"
            ),
            "center": area.get(
                "center"
            ),
        }

    return {
        "analysis": {
            "id": (
                f"market-"
                f"{now_utc().strftime('%Y%m%d%H%M%S')}"
            ),
            "generated_at": now_utc().isoformat(),
            "data_version": DATA_VERSION,
            "forecast_days": forecast_days,
        },

        "location": {
            "selection": location.get(
                "selection"
            ),
            "area": area_response,
            "match_type": location.get(
                "match_type"
            ),
            "distance_km": location.get(
                "distance_km"
            ),
        },

        "summary": {
            "score": overall_score,
            "label": overall_label,
            "demand_direction": (
                overall_demand_direction
            ),
            "confidence": overall_confidence,
            "signals": aggregated_signals,
        },

        "products": product_results,

        "recommendations": (
            recommendation_info
        ),

        "sources": {
            "geography": (
                os.path.basename(
                    AREAS_FILE
                )
            ),
            "demographics": (
                os.path.basename(
                    DEMOGRAPHICS_FILE
                )
            ),
            "economic_indicators": (
                os.path.basename(
                    ECONOMIC_FILE
                )
            ),
            "market_signals": (
                os.path.basename(
                    MARKET_SIGNALS_FILE
                )
            ),
        },
    }


# =========================================================
# MARKET AREAS
# =========================================================

def list_market_areas(
    search: str = "",
) -> list[dict]:
    """
    Return configured geographic market areas.
    """

    areas = load_areas()

    search = as_string(
        search
    ).lower()

    if not search:
        return areas

    results = []

    for area in areas:

        searchable = " ".join([
            as_string(
                area.get(
                    "id"
                )
            ),
            as_string(
                area.get(
                    "name"
                )
            ),
            as_string(
                area.get(
                    "sub_county"
                )
            ),
            as_string(
                area.get(
                    "county"
                )
            ),
        ]).lower()

        if search in searchable:

            results.append(
                area
            )

    return results


# =========================================================
# AREA DETAILS
# =========================================================

def get_market_area(
    area_id: str,
) -> dict:
    """
    Return geographic, demographic and current market
    information for a configured area.
    """

    areas = load_areas()

    area = find_area(
        areas,
        area_id,
    )

    if not area:

        raise APIError(
            "Market area not found.",
            404,
            "area_not_found",
        )

    demographics_dataset = (
        load_demographics()
    )

    market_dataset = (
        load_market_signals()
    )

    demographics = (
        _lookup_area_dataset(
            demographics_dataset,
            area,
        )
    )

    if "areas" in demographics_dataset:

        structured = (
            demographics_dataset.get(
                "areas"
            )
        )

        if isinstance(
            structured,
            dict,
        ):

            demographics = (
                _lookup_area_dataset(
                    structured,
                    area,
                )
                or demographics
            )

    market = (
        _lookup_area_dataset(
            market_dataset,
            area,
        )
    )

    if "areas" in market_dataset:

        structured_market = (
            market_dataset.get(
                "areas"
            )
        )

        if isinstance(
            structured_market,
            dict,
        ):

            market = (
                _lookup_area_dataset(
                    structured_market,
                    area,
                )
                or market
            )

    return {
        "area": area,

        "demographics": demographics,

        "market": market,

        "data_version": DATA_VERSION,
    }


# =========================================================
# MARKET TRENDS
# =========================================================

def market_trends(
    area_id: str = "",
    category: str = "",
    indicator: str = "",
    days: int = 365,
) -> dict:
    """
    Return available macro/market trend information.

    The local MVP dataset may contain current snapshots
    instead of a full historical time series. The function
    therefore returns the available records without
    fabricating missing historical points.
    """

    economic_dataset = (
        load_economic_indicators()
    )

    market_dataset = (
        load_market_signals()
    )

    result = {
        "area_id": as_string(
            area_id
        ),
        "category": as_string(
            category
        ),
        "indicator": as_string(
            indicator
        ),
        "days": max(
            1,
            min(
                int(days),
                3650,
            ),
        ),
        "economic": economic_dataset,
        "market": market_dataset,
        "data_version": DATA_VERSION,
    }

    return result


# =========================================================
# PRODUCT FORECAST DIRECT
# =========================================================

def forecast_target(
    product: dict,
    forecast_days: int = DEFAULT_FORECAST_DAYS,
) -> dict:
    """
    Run forecasting directly on a product payload.

    Useful for frontend/chart development and testing
    independently from geographic analysis.
    """

    if not isinstance(
        product,
        dict,
    ):
        raise APIError(
            "Product forecast target is required.",
            422,
            "invalid_product",
        )

    forecast_days = max(
        7,
        min(
            int(
                forecast_days
            ),
            365,
        ),
    )

    try:

        return forecast_product(
            product,
            forecast_days,
        )

    except ValueError as exc:

        raise APIError(
            str(exc),
            422,
            "forecast_validation_error",
        )


# =========================================================
# DATASET STATUS
# =========================================================

def dataset_status() -> dict:
    """
    Return a health/availability summary for the local
    intelligence datasets.

    This is useful for administration and debugging.
    """

    datasets = {
        "areas": AREAS_FILE,
        "demographics": DEMOGRAPHICS_FILE,
        "economic_indicators": ECONOMIC_FILE,
        "market_signals": MARKET_SIGNALS_FILE,
    }

    result = {}

    for name, filepath in datasets.items():

        exists = os.path.exists(
            filepath
        )

        size = (
            os.path.getsize(
                filepath
            )
            if exists
            else 0
        )

        result[
            name
        ] = {
            "file": os.path.basename(
                filepath
            ),
            "available": exists,
            "size_bytes": size,
        }

    available_count = sum(
        1
        for item in result.values()
        if item[
            "available"
        ]
    )

    return {
        "data_version": DATA_VERSION,

        "datasets": result,

        "available_count": (
            available_count
        ),

        "total_count": len(
            result
        ),

        "ready": (
            available_count == len(
                result
            )
        ),

        "checked_at": now_utc().isoformat(),
    }


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "load_areas",
    "load_demographics",
    "load_economic_indicators",
    "load_market_signals",
    "resolve_location",
    "resolve_market_data",
    "resolve_economic_data",
    "infer_target_profile",
    "build_product_context",
    "analyze_product",
    "analyze_market",
    "list_market_areas",
    "get_market_area",
    "market_trends",
    "forecast_target",
    "dataset_status",
]
