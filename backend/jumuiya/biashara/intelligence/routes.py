# backend/jumuiya/biashara/intelligence/routes.py

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

from backend.jumuiya.biashara.intelligence import (
    schemas,
    service,
)


# =========================================================
# BLUEPRINT
# =========================================================

intelligence_bp = Blueprint(
    "jumuiya_biashara_intelligence",
    __name__,
)


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_LIMIT = 50

MAX_LIMIT = 100

DEFAULT_FORECAST_DAYS = 30

MAX_FORECAST_DAYS = 365


# =========================================================
# HELPERS
# =========================================================

def body():
    """
    Safely read a JSON request body.
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
    Convert schema ValueError exceptions into
    the standard APIError format.
    """

    try:
        return fn(
            data
        )

    except ValueError as exc:

        raise APIError(
            str(exc),
            422,
            "validation_error",
        )


def user_id():
    """
    Return the current authenticated user ID.
    """

    return current_user_id()


def query_limit(
    default=DEFAULT_LIMIT,
):
    """
    Safely parse a request limit.
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
        MAX_LIMIT,
    )


def forecast_days():
    """
    Parse forecast horizon from query parameters.
    """

    raw = request.args.get(
        "forecast_days",
        DEFAULT_FORECAST_DAYS,
    )

    try:
        value = int(
            raw
        )

    except (
        TypeError,
        ValueError,
    ):

        raise APIError(
            "forecast_days must be a valid integer.",
            422,
            "invalid_forecast_days",
        )

    if value < 7:

        raise APIError(
            "forecast_days must be at least 7.",
            422,
            "invalid_forecast_days",
        )

    return min(
        value,
        MAX_FORECAST_DAYS,
    )


# =========================================================
# HEALTH
# =========================================================

@intelligence_bp.get(
    "/health"
)
def health():
    """
    Public health endpoint for the Biashara
    Market Intelligence engine.
    """

    return ok({
        "module": "biashara_market_intelligence",
        "status": "online",
        "version": "1.0",
        "datasets": service.dataset_status(),
    })


# =========================================================
# DATASET STATUS
# =========================================================

@intelligence_bp.get(
    "/datasets/status"
)
@require_authenticated
def get_dataset_status():
    """
    Return the availability of local intelligence datasets.

    Useful for administrative monitoring and debugging.
    """

    return ok(
        service.dataset_status()
    )


# =========================================================
# MARKET AREAS
# =========================================================

@intelligence_bp.get(
    "/areas"
)
@require_authenticated
def get_market_areas():
    """
    List configured geographic market areas.

    Supports:

        ?search=Nyali
    """

    search = (
        request.args.get(
            "search",
            "",
        )
        .strip()
    )

    return ok(
        service.list_market_areas(
            search
        )
    )


@intelligence_bp.get(
    "/areas/<area_id>"
)
@require_authenticated
def get_market_area(
    area_id,
):
    """
    Return detailed information for one configured
    market area.
    """

    if not area_id.strip():

        raise APIError(
            "area_id is required.",
            422,
            "invalid_area",
        )

    return ok(
        service.get_market_area(
            area_id
        )
    )


# =========================================================
# MARKET TRENDS
# =========================================================

@intelligence_bp.get(
    "/trends"
)
@require_authenticated
def get_market_trends():
    """
    Return currently available market/economic trend data.

    Supported:

        ?area_id=nyali
        ?category=electronics
        ?indicator=inflation
        ?days=365
    """

    area_id = (
        request.args.get(
            "area_id",
            "",
        )
        .strip()
    )

    category = (
        request.args.get(
            "category",
            "",
        )
        .strip()
    )

    indicator = (
        request.args.get(
            "indicator",
            "",
        )
        .strip()
    )

    raw_days = request.args.get(
        "days",
        "365",
    )

    try:

        days = int(
            raw_days
        )

    except (
        TypeError,
        ValueError,
    ):

        raise APIError(
            "days must be a valid integer.",
            422,
            "invalid_days",
        )

    if days < 1:

        raise APIError(
            "days must be at least 1.",
            422,
            "invalid_days",
        )

    days = min(
        days,
        3650,
    )

    return ok(
        service.market_trends(
            area_id=area_id,
            category=category,
            indicator=indicator,
            days=days,
        )
    )


# =========================================================
# DIRECT PRODUCT FORECAST
# =========================================================

@intelligence_bp.post(
    "/forecast"
)
@require_authenticated
def forecast():
    """
    Run a direct product/service forecast.

    This endpoint is useful for testing and for frontend
    chart interactions without running the full market
    feasibility analysis.

    Example:

        {
            "name": "Smartphone",
            "category": "Electronics",
            "sales_history": [
                {
                    "date": "2026-08-01",
                    "value": 12
                },
                {
                    "date": "2026-08-02",
                    "value": 15
                }
            ]
        }
    """

    data = body()

    # Accept forecast_days either in the body
    # or use the query parameter.
    requested_days = data.get(
        "forecast_days"
    )

    if requested_days is None:

        requested_days = request.args.get(
            "forecast_days",
            DEFAULT_FORECAST_DAYS,
        )

    try:

        requested_days = int(
            requested_days
        )

    except (
        TypeError,
        ValueError,
    ):

        raise APIError(
            "forecast_days must be a valid integer.",
            422,
            "invalid_forecast_days",
        )

    if requested_days < 7:

        raise APIError(
            "forecast_days must be at least 7.",
            422,
            "invalid_forecast_days",
        )

    requested_days = min(
        requested_days,
        MAX_FORECAST_DAYS,
    )

    product = dict(
        data
    )

    product.pop(
        "forecast_days",
        None,
    )

    return ok(
        service.forecast_target(
            product,
            requested_days,
        )
    )


# =========================================================
# FULL MARKET ANALYSIS
# =========================================================

@intelligence_bp.post(
    "/analyze"
)
@require_authenticated
def analyze_market():
    """
    Run the complete Biashara Market Intelligence
    analysis.

    The endpoint combines:

        geographic context
        demographic data
        market signals
        macro-economic indicators
        existing business performance
        product information
        demand forecasting
        recommendations

    Example:

        {
            "location": {
                "area_id": "nyali"
            },

            "products": [
                {
                    "name": "Smartphone",
                    "category": "Electronics",
                    "price": 25000,
                    "cost_price": 19000
                }
            ],

            "business": {
                "business_category": "Electronics",
                "business_type": "Retail"
            },

            "options": {
                "analysis_mode": "full",
                "forecast_horizon": "short_term",
                "forecast_days": 30
            }
        }
    """

    payload = validate(
        schemas.market_analysis_payload,
        body(),
    )

    return created(
        service.analyze_market(
            user_id(),
            payload,
        ),
        "Market analysis completed.",
    )


# =========================================================
# AUTHENTICATED USER MARKET ANALYSIS
# =========================================================
#
# Alias route for clients that prefer the explicit
# /me/analyze naming convention.
# =========================================================

@intelligence_bp.post(
    "/me/analyze"
)
@require_authenticated
def analyze_my_market():
    """
    Run Market Intelligence using the authenticated
    Biashara context.
    """

    payload = validate(
        schemas.market_analysis_payload,
        body(),
    )

    return created(
        service.analyze_market(
            user_id(),
            payload,
        ),
        "Market analysis completed.",
    )


# =========================================================
# QUICK AREA ANALYSIS
# =========================================================

@intelligence_bp.post(
    "/quick-analysis"
)
@require_authenticated
def quick_analysis():
    """
    Convenience endpoint for simple frontend requests.

    Example:

        {
            "area_id": "nyali",
            "category": "electronics",
            "product": {
                "name": "Smartphone",
                "price": 25000
            }
        }

    The endpoint converts the simplified request into the
    full Market Intelligence request structure.
    """

    data = body()

    area_id = data.get(
        "area_id"
    )

    category = data.get(
        "category",
        "",
    )

    product = data.get(
        "product"
    )

    if not isinstance(
        area_id,
        str,
    ) or not area_id.strip():

        raise APIError(
            "area_id is required.",
            422,
            "invalid_area",
        )

    if not isinstance(
        product,
        dict,
    ):

        raise APIError(
            "product object is required.",
            422,
            "invalid_product",
        )

    normalized_product = {
        **product,
        "category": (
            product.get(
                "category"
            )
            or category
        ),
    }

    request_payload = {
        "location": {
            "area_id": area_id.strip()
        },

        "products": [
            normalized_product
        ],

        "business": {},

        "options": {
            "analysis_mode": "full",
            "forecast_horizon": "short_term",
            "forecast_days": forecast_days(),
        },
    }

    validated = validate(
        schemas.market_analysis_payload,
        request_payload,
    )

    return created(
        service.analyze_market(
            user_id(),
            validated,
        ),
        "Market analysis completed.",
    )


# =========================================================
# BUSINESS-CENTRIC ANALYSIS
# =========================================================

@intelligence_bp.post(
    "/business-analysis"
)
@require_authenticated
def business_analysis():
    """
    Analyze the authenticated business against a selected
    location and one or more products.

    The current business profile and business performance
    are automatically incorporated by the service layer.
    """

    data = body()

    location = data.get(
        "location"
    )

    if location is None:

        location = {
            "area_id": data.get(
                "area_id"
            )
        }

    products = data.get(
        "products"
    )

    if products is None:

        product = data.get(
            "product"
        )

        if isinstance(
            product,
            dict,
        ):

            products = [
                product
            ]

    request_payload = {
        "location": location,

        "products": products or [],

        "business": data.get(
            "business",
            {},
        ),

        "options": data.get(
            "options",
            {},
        ),

        "notes": data.get(
            "notes",
            "",
        ),
    }

    validated = validate(
        schemas.market_analysis_payload,
        request_payload,
    )

    return created(
        service.analyze_market(
            user_id(),
            validated,
        ),
        "Business market analysis completed.",
    )


# =========================================================
# PRODUCT-SPECIFIC ANALYSIS
# =========================================================

@intelligence_bp.post(
    "/product-analysis"
)
@require_authenticated
def product_analysis():
    """
    Analyze one product/service in a selected market.

    This is useful for a product-detail screen where the
    user wants to ask:

        "Should I sell this here?"
    """

    data = body()

    location = data.get(
        "location"
    )

    if location is None:

        location = {
            "area_id": data.get(
                "area_id"
            )
        }

    product = data.get(
        "product"
    )

    if not isinstance(
        product,
        dict,
    ):

        raise APIError(
            "product object is required.",
            422,
            "invalid_product",
        )

    request_payload = {
        "location": location,

        "products": [
            product
        ],

        "business": data.get(
            "business",
            {},
        ),

        "options": data.get(
            "options",
            {},
        ),

        "notes": data.get(
            "notes",
            "",
        ),
    }

    validated = validate(
        schemas.market_analysis_payload,
        request_payload,
    )

    result = service.analyze_market(
        user_id(),
        validated,
    )

    # The normal service response already contains
    # one-product analysis.
    return created(
        result,
        "Product market analysis completed.",
    )


# =========================================================
# API INFORMATION
# =========================================================

@intelligence_bp.get(
    "/info"
)
def info():
    """
    Public informational endpoint describing the current
    Market Intelligence service capabilities.
    """

    return ok({
        "module": "Biashara Market Intelligence",

        "version": "1.0",

        "capabilities": [
            "geographic_market_selection",
            "demographic_context",
            "market_demand_signals",
            "macro_economic_context",
            "demand_forecasting",
            "market_opportunity_scoring",
            "business_recommendations",
        ],

        "location_support": [
            "configured_market_area",
            "map_center_point",
            "drawn_bounds",
        ],

        "analysis_modes": [
            "feasibility",
            "demand",
            "pricing",
            "full",
        ],

        "default_currency": "KES",
    })


# =========================================================
# EXPORT
# =========================================================

__all__ = [
    "intelligence_bp",
]
