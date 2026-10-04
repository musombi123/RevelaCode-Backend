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
    Read and validate a required JSON request body.
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


def optional_json_body():
    """
    Read an optional JSON request body.
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


def text_value(
    data: dict,
    key: str,
    required: bool = False,
    maximum: int = 300,
) -> str:
    """
    Validate a simple text field used by intelligence
    endpoints.
    """

    value = data.get(key, "")

    if value is None:
        value = ""

    if not isinstance(value, str):
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

    if len(value) > maximum:
        raise APIError(
            f"{key} is too long.",
            422,
            "validation_error",
        )

    return value


def number_value(
    data: dict,
    key: str,
    required: bool = False,
    minimum: float | None = None,
) -> float | None:
    """
    Validate numeric values for GPS/location payloads.
    """

    value = data.get(key)

    if value in (None, ""):
        if required:
            raise APIError(
                f"{key} is required.",
                422,
                "validation_error",
            )

        return None

    try:
        value = float(value)
    except (TypeError, ValueError):
        raise APIError(
            f"{key} must be a number.",
            422,
            "validation_error",
        )

    if minimum is not None and value < minimum:
        raise APIError(
            f"{key} must be at least {minimum}.",
            422,
            "validation_error",
        )

    return value


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
        "intelligence": "enabled",
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
# FARM LOCATION
# ============================================================

@shamba_bp.put(
    "/farms/<farm_id>/location"
)
@require_authenticated
def update_farm_location(farm_id):
    """
    Save the farmer's best available GPS coordinate.

    Expected body:

    {
        "latitude": -4.0435,
        "longitude": 39.6682,
        "accuracy": 8.4,
        "source": "browser_gps",
        "county": "Mombasa",
        "town": "Mombasa",
        "location": "Mombasa"
    }
    """

    data = body()

    latitude = number_value(
        data,
        "latitude",
        required=True,
    )

    longitude = number_value(
        data,
        "longitude",
        required=True,
    )

    accuracy = number_value(
        data,
        "accuracy",
        required=False,
        minimum=0,
    )

    source = text_value(
        data,
        "source",
        required=False,
        maximum=60,
    ) or "browser_gps"

    county = text_value(
        data,
        "county",
        required=False,
        maximum=100,
    )

    town = text_value(
        data,
        "town",
        required=False,
        maximum=100,
    )

    location = text_value(
        data,
        "location",
        required=False,
        maximum=200,
    )

    return ok(
        services.update_farm_location(
            current_user_id(),
            farm_id,
            latitude=latitude,
            longitude=longitude,
            accuracy=accuracy,
            source=source,
            county=county or None,
            town=town or None,
            location=location or None,
        ),
        "Farm location updated.",
    )


# ============================================================
# CROPS
# ============================================================

@shamba_bp.get(
    "/farms/<farm_id>/crops"
)
@require_authenticated
def get_crops(farm_id):
    return ok(
        services.list_crops(
            current_user_id(),
            farm_id,
            request.args.get("status"),
        )
    )


@shamba_bp.post(
    "/farms/<farm_id>/crops"
)
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

@shamba_bp.get(
    "/farms/<farm_id>/activities"
)
@require_authenticated
def get_activities(farm_id):
    return ok(
        services.list_activities(
            current_user_id(),
            farm_id,
        )
    )


@shamba_bp.post(
    "/farms/<farm_id>/activities"
)
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

@shamba_bp.get(
    "/farms/<farm_id>/harvests"
)
@require_authenticated
def get_harvests(farm_id):
    return ok(
        services.list_harvests(
            current_user_id(),
            farm_id,
        )
    )


@shamba_bp.post(
    "/farms/<farm_id>/harvests"
)
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

@shamba_bp.get(
    "/farms/<farm_id>/insights"
)
@require_authenticated
def get_farm_insights(farm_id):
    """
    Return the current farm intelligence snapshot.

    This generates a fresh snapshot and persists it.
    """

    return ok(
        services.generate_farm_insight(
            current_user_id(),
            farm_id,
            persist=True,
        )
    )


@shamba_bp.post(
    "/farms/<farm_id>/insights/refresh"
)
@require_authenticated
def refresh_farm_insights(farm_id):
    """
    Explicitly refresh farm intelligence.

    Useful after:
        - adding crops
        - changing farm data
        - recording activities
        - recording harvests
        - syncing weather
        - syncing market data
    """

    return ok(
        services.refresh_farm_intelligence(
            current_user_id(),
            farm_id,
        ),
        "Farm intelligence refreshed.",
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
    Return active recommendations.
    """

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
    Create a manual recommendation.

    Expected body:

    {
        "title": "Review irrigation",
        "recommendation": "Inspect the irrigation system.",
        "category": "water",
        "priority": "high",
        "confidence": 90,
        "crop_id": "optional"
    }
    """

    data = body()

    title = text_value(
        data,
        "title",
        required=True,
        maximum=200,
    )

    recommendation = text_value(
        data,
        "recommendation",
        required=True,
        maximum=2000,
    )

    category = text_value(
        data,
        "category",
        maximum=80,
    ) or "general"

    priority = text_value(
        data,
        "priority",
        maximum=30,
    ) or "normal"

    confidence = number_value(
        data,
        "confidence",
        minimum=0,
    )

    if confidence is None:
        confidence = 50

    if confidence > 100:
        raise APIError(
            "confidence cannot exceed 100.",
            422,
            "validation_error",
        )

    crop_id = data.get("crop_id")

    if crop_id is not None:
        crop_id = str(crop_id).strip()

        if not crop_id:
            crop_id = None

    return created(
        services.create_recommendation(
            current_user_id(),
            farm_id,
            title=title,
            recommendation=recommendation,
            category=category,
            priority=priority,
            confidence=confidence,
            crop_id=crop_id,
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
    """

    return ok(
        services.list_alerts(
            current_user_id(),
            farm_id,
        )
    )


@shamba_bp.get(
    "/farms/<farm_id>/alerts/summary"
)
@require_authenticated
def get_alert_summary(farm_id):
    """
    Return active alerts plus unread count.
    """

    return ok(
        services.alerts_snapshot(
            current_user_id(),
            farm_id,
        )
    )


@shamba_bp.put(
    "/farms/<farm_id>/alerts/<alert_id>/read"
)
@require_authenticated
def mark_alert_read(
    farm_id,
    alert_id,
):
    """
    Mark one farm alert as read.
    """

    return ok(
        services.mark_alert_read(
            current_user_id(),
            farm_id,
            alert_id,
        ),
        "Alert marked as read.",
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
    Return the weather snapshot associated with the farm.

    Actual external weather synchronization can be connected
    later without changing the frontend contract.
    """

    return ok(
        services.get_weather(
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
    Return market intelligence associated with the farm.
    """

    return ok(
        services.get_market(
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
    Return crop-specific intelligence:

        - crop profile
        - crop risk
        - yield analysis
        - financial analysis
    """

    return ok(
        services.analyze_crop(
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
    Return structured Shamba context for RevelaAI.

    This endpoint does not generate an AI answer.

    It supplies structured:
        - farmer data
        - farm data
        - crops
        - activities
        - harvests
        - weather
        - market
        - intelligence
    """

    return ok(
        services.get_ai_context(
            current_user_id(),
            farm_id,
        )
    )


# ============================================================
# FARM COMMAND CENTER
# ============================================================

@shamba_bp.get(
    "/farms/<farm_id>/command-center"
)
@require_authenticated
def get_command_center(farm_id):
    """
    Complete Farm Operating System payload.

    Intended for the professional Shamba Command Center.
    """

    return ok(
        services.farm_command_center(
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
    Main Shamba Farm Command Center.

    The frontend can use this as the primary dashboard
    bootstrap endpoint.
    """

    return ok(
        services.dashboard(
            current_user_id()
        )
    )