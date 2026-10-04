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

from backend.jumuiya.shamba import (
    schemas,
    services,
)


shamba_bp = Blueprint(
    "jumuiya_shamba",
    __name__,
)


# ============================================================
# HELPERS
# ============================================================

def body():
    """
    Read and validate the JSON request body.
    """

    data = request.get_json(
        silent=True
    )

    if not isinstance(data, dict):
        raise APIError(
            "JSON request body is required.",
            400,
            "invalid_json",
        )

    return data


def validate(fn, data):
    """
    Run a Shamba schema validator and convert validation
    errors into the application's standard API error.
    """

    try:
        return fn(data)

    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "validation_error",
        )


def optional_json_body():
    """
    Read an optional JSON body.

    Useful for intelligence endpoints where filters or
    parameters may optionally be supplied.
    """

    data = request.get_json(
        silent=True
    )

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise APIError(
            "JSON request body must be an object.",
            400,
            "invalid_json",
        )

    return data


# ============================================================
# HEALTH
# ============================================================

@shamba_bp.get("/health")
def health():
    """
    Shamba service health check.
    """

    return ok({
        "hub": "shamba",
        "status": "online",
        "version": "2.0",
    })


# ============================================================
# FARMER PROFILE
# ============================================================

@shamba_bp.get("/farmer")
@require_authenticated
def get_farmer():
    return ok(
        services.get_farmer(
            current_user_id()
        )
    )


@shamba_bp.post("/farmer")
@require_authenticated
def save_farmer():
    payload = validate(
        schemas.farmer_payload,
        body(),
    )

    return ok(
        services.create_or_update_farmer(
            current_user_id(),
            payload,
        ),
        "Farmer profile saved.",
    )


# ============================================================
# FARMS
# ============================================================

@shamba_bp.get("/farms")
@require_authenticated
def get_farms():
    return ok(
        services.list_farms(
            current_user_id()
        )
    )


@shamba_bp.post("/farms")
@require_authenticated
def add_farm():
    payload = validate(
        schemas.farm_payload,
        body(),
    )

    return created(
        services.create_farm(
            current_user_id(),
            payload,
        ),
        "Farm created.",
    )


@shamba_bp.get("/farms/<farm_id>")
@require_authenticated
def get_farm(farm_id):
    return ok(
        services.get_farm(
            current_user_id(),
            farm_id,
        )
    )


@shamba_bp.put("/farms/<farm_id>")
@require_authenticated
def edit_farm(farm_id):
    payload = validate(
        schemas.farm_payload,
        body(),
    )

    return ok(
        services.update_farm(
            current_user_id(),
            farm_id,
            payload,
        ),
        "Farm updated.",
    )


@shamba_bp.delete("/farms/<farm_id>")
@require_authenticated
def remove_farm(farm_id):
    return ok(
        services.delete_farm(
            current_user_id(),
            farm_id,
        ),
        "Farm removed.",
    )


# ============================================================
# CROPS
# ============================================================

@shamba_bp.get("/farms/<farm_id>/crops")
@require_authenticated
def get_crops(farm_id):
    return ok(
        services.list_crops(
            current_user_id(),
            farm_id,
            request.args.get("status"),
        )
    )


@shamba_bp.post("/farms/<farm_id>/crops")
@require_authenticated
def add_crop(farm_id):
    payload = validate(
        schemas.crop_payload,
        body(),
    )

    return created(
        services.create_crop(
            current_user_id(),
            farm_id,
            payload,
        ),
        "Crop added.",
    )


# ============================================================
# FARM ACTIVITIES
# ============================================================

@shamba_bp.get("/farms/<farm_id>/activities")
@require_authenticated
def get_activities(farm_id):
    return ok(
        services.list_activities(
            current_user_id(),
            farm_id,
        )
    )


@shamba_bp.post("/farms/<farm_id>/activities")
@require_authenticated
def add_activity(farm_id):
    payload = validate(
        schemas.activity_payload,
        body(),
    )

    return created(
        services.create_activity(
            current_user_id(),
            farm_id,
            payload,
        ),
        "Farm activity recorded.",
    )


# ============================================================
# HARVESTS
# ============================================================

@shamba_bp.get("/farms/<farm_id>/harvests")
@require_authenticated
def get_harvests(farm_id):
    return ok(
        services.list_harvests(
            current_user_id(),
            farm_id,
        )
    )


@shamba_bp.post("/farms/<farm_id>/harvests")
@require_authenticated
def add_harvest(farm_id):
    payload = validate(
        schemas.harvest_payload,
        body(),
    )

    return created(
        services.create_harvest(
            current_user_id(),
            farm_id,
            payload,
        ),
        "Harvest recorded.",
    )


# ============================================================
# FARM INTELLIGENCE
# ============================================================

@shamba_bp.get("/farms/<farm_id>/insights")
@require_authenticated
def get_farm_insights(farm_id):
    """
    Return the latest intelligence snapshot for a farm.

    Intended for the Shamba Farm Command Center.
    """

    if not hasattr(
        services,
        "farm_insights",
    ):
        raise APIError(
            "Farm intelligence service is not available.",
            503,
            "intelligence_unavailable",
        )

    return ok(
        services.farm_insights(
            current_user_id(),
            farm_id,
        )
    )


# ============================================================
# FARM RECOMMENDATIONS
# ============================================================

@shamba_bp.get(
    "/farms/<farm_id>/recommendations"
)
@require_authenticated
def get_recommendations(farm_id):
    """
    Return active recommendations for a farm.
    """

    if not hasattr(
        services,
        "list_recommendations",
    ):
        raise APIError(
            "Farm recommendation service is not available.",
            503,
            "recommendations_unavailable",
        )

    return ok(
        services.list_recommendations(
            current_user_id(),
            farm_id,
        )
    )


@shamba_bp.post(
    "/farms/<farm_id>/recommendations"
)
@require_authenticated
def create_recommendation(farm_id):
    """
    Create a farm recommendation.

    Normally this will eventually be called by the
    Shamba intelligence engine or RevelaAI.
    """

    payload = optional_json_body()

    if not hasattr(
        services,
        "create_recommendation",
    ):
        raise APIError(
            "Farm recommendation service is not available.",
            503,
            "recommendations_unavailable",
        )

    return created(
        services.create_recommendation(
            current_user_id(),
            farm_id,
            payload,
        ),
        "Farm recommendation created.",
    )


# ============================================================
# FARM ALERTS
# ============================================================

@shamba_bp.get(
    "/farms/<farm_id>/alerts"
)
@require_authenticated
def get_farm_alerts(farm_id):
    """
    Return active agricultural alerts.

    Examples:
        - heavy rainfall
        - drought risk
        - pest risk
        - disease risk
        - harvest window
        - market opportunity
    """

    if not hasattr(
        services,
        "list_alerts",
    ):
        raise APIError(
            "Farm alert service is not available.",
            503,
            "alerts_unavailable",
        )

    return ok(
        services.list_alerts(
            current_user_id(),
            farm_id,
        )
    )


# ============================================================
# WEATHER
# ============================================================

@shamba_bp.get(
    "/farms/<farm_id>/weather"
)
@require_authenticated
def get_farm_weather(farm_id):
    """
    Return weather intelligence for a farm.

    Farm coordinates should be used when available.
    """

    if not hasattr(
        services,
        "farm_weather",
    ):
        raise APIError(
            "Farm weather service is not available.",
            503,
            "weather_unavailable",
        )

    return ok(
        services.farm_weather(
            current_user_id(),
            farm_id,
        )
    )


# ============================================================
# MARKET INTELLIGENCE
# ============================================================

@shamba_bp.get(
    "/farms/<farm_id>/market"
)
@require_authenticated
def get_farm_market(farm_id):
    """
    Return market intelligence relevant to the farmer's
    crops and harvests.
    """

    if not hasattr(
        services,
        "farm_market",
    ):
        raise APIError(
            "Farm market service is not available.",
            503,
            "market_unavailable",
        )

    return ok(
        services.farm_market(
            current_user_id(),
            farm_id,
        )
    )


# ============================================================
# CROP INTELLIGENCE
# ============================================================

@shamba_bp.get(
    "/farms/<farm_id>/crops/<crop_id>/analysis"
)
@require_authenticated
def get_crop_analysis(
    farm_id,
    crop_id,
):
    """
    Return crop-specific intelligence.

    Intended to combine:
        crop profile
        crop health
        yield
        weather
        disease risk
        pest risk
        market conditions
        profitability
    """

    if not hasattr(
        services,
        "crop_analysis",
    ):
        raise APIError(
            "Crop intelligence service is not available.",
            503,
            "crop_analysis_unavailable",
        )

    return ok(
        services.crop_analysis(
            current_user_id(),
            farm_id,
            crop_id,
        )
    )


# ============================================================
# REVELAAI CONTEXT
# ============================================================

@shamba_bp.get(
    "/farms/<farm_id>/ai-context"
)
@require_authenticated
def get_ai_context(farm_id):
    """
    Return structured agricultural context for RevelaAI.

    This endpoint should NOT directly generate an AI answer.

    Its job is to collect the farmer's:
        - farm
        - crops
        - activities
        - harvests
        - weather
        - market
        - intelligence

    The RevelaAI orchestrator can then decide how to use
    that context.
    """

    if not hasattr(
        services,
        "build_ai_context",
    ):
        raise APIError(
            "RevelaAI farm context service is not available.",
            503,
            "ai_context_unavailable",
        )

    return ok(
        services.build_ai_context(
            current_user_id(),
            farm_id,
        )
    )


# ============================================================
# DASHBOARD
# ============================================================

@shamba_bp.get("/dashboard")
@require_authenticated
def get_dashboard():
    """
    Shamba Farm Command Center.

    This should remain the primary endpoint used by the
    frontend dashboard.
    """

    return ok(
        services.dashboard(
            current_user_id()
        )
    )
