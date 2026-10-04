from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# ============================================================
# TIME
# ============================================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# SAFE HELPERS
# ============================================================

def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default

        return int(value)

    except (TypeError, ValueError):
        return default


def _list(value: Any) -> list:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    return [value]


# ============================================================
# SCORE HELPERS
# ============================================================

def clamp_score(value: Any, minimum: int = 0, maximum: int = 100) -> int:
    """
    Keep intelligence scores between 0 and 100.
    """

    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = minimum

    return max(
        minimum,
        min(score, maximum),
    )


def score_label(score: Any) -> str:
    """
    Convert a numeric score into a human-readable status.
    """

    score = clamp_score(score)

    if score >= 85:
        return "excellent"

    if score >= 70:
        return "good"

    if score >= 50:
        return "moderate"

    if score >= 30:
        return "poor"

    return "critical"


def risk_level(score: Any) -> str:
    """
    Convert a risk score into a standard Shamba risk level.

    Higher score = higher risk.
    """

    score = clamp_score(score)

    if score >= 80:
        return "critical"

    if score >= 60:
        return "high"

    if score >= 35:
        return "moderate"

    if score >= 15:
        return "low"

    return "minimal"


# ============================================================
# FARM HEALTH
# ============================================================

def calculate_farm_health(
    *,
    soil_score: Any = 50,
    water_score: Any = 50,
    crop_score: Any = 50,
    productivity_score: Any = 50,
    financial_score: Any = 50,
    risk_score: Any = 50,
) -> dict:
    """
    Calculate an overall Farm Health Score.

    This is intentionally deterministic.

    RevelaAI can later provide more sophisticated analysis,
    but the dashboard should always have a reliable baseline
    score even when AI services are unavailable.
    """

    soil = clamp_score(soil_score)
    water = clamp_score(water_score)
    crop = clamp_score(crop_score)
    productivity = clamp_score(productivity_score)
    financial = clamp_score(financial_score)

    # risk_score represents HEALTH RISK.
    # Therefore it is inverted when calculating health.
    risk = clamp_score(risk_score)

    risk_health = 100 - risk

    score = (
        (soil * 0.20)
        + (water * 0.20)
        + (crop * 0.20)
        + (productivity * 0.15)
        + (financial * 0.15)
        + (risk_health * 0.10)
    )

    score = clamp_score(score)

    return {
        "score": score,
        "status": score_label(score),
        "components": {
            "soil": soil,
            "water": water,
            "crop_health": crop,
            "productivity": productivity,
            "financial": financial,
            "risk_health": risk_health,
        },
    }


# ============================================================
# CROP RISK
# ============================================================

def calculate_crop_risk(
    *,
    pest_risk: Any = 0,
    disease_risk: Any = 0,
    water_stress: Any = 0,
    weather_risk: Any = 0,
    market_risk: Any = 0,
) -> dict:
    """
    Calculate the overall risk facing a crop.

    Inputs are expected to be 0-100.
    Higher means greater risk.
    """

    pest = clamp_score(pest_risk)
    disease = clamp_score(disease_risk)
    water = clamp_score(water_stress)
    weather = clamp_score(weather_risk)
    market = clamp_score(market_risk)

    score = (
        (pest * 0.25)
        + (disease * 0.25)
        + (water * 0.20)
        + (weather * 0.20)
        + (market * 0.10)
    )

    score = clamp_score(score)

    return {
        "score": score,
        "level": risk_level(score),
        "components": {
            "pest": pest,
            "disease": disease,
            "water": water,
            "weather": weather,
            "market": market,
        },
    }


# ============================================================
# YIELD ANALYSIS
# ============================================================

def calculate_yield_analysis(
    *,
    expected_yield: Any = 0,
    actual_yield: Any = 0,
    area: Any = 0,
    area_unit: str = "acres",
    yield_unit: str = "kg",
) -> dict:
    """
    Calculate crop yield performance.

    Returns both total yield information and yield per area.
    """

    expected = _float(expected_yield)
    actual = _float(actual_yield)
    farm_area = _float(area)

    variance = actual - expected

    if expected > 0:
        performance = (
            actual / expected
        ) * 100

    else:
        performance = 0

    if expected > 0:
        variance_percentage = (
            variance / expected
        ) * 100

    else:
        variance_percentage = 0

    if farm_area > 0:
        actual_per_area = (
            actual / farm_area
        )

        expected_per_area = (
            expected / farm_area
        )

    else:
        actual_per_area = 0

        expected_per_area = 0

    return {
        "expected_yield": expected,
        "actual_yield": actual,
        "yield_unit": yield_unit,
        "variance": round(
            variance,
            2,
        ),
        "variance_percentage": round(
            variance_percentage,
            2,
        ),
        "performance_percentage": round(
            performance,
            2,
        ),
        "area": farm_area,
        "area_unit": area_unit,
        "actual_yield_per_area": round(
            actual_per_area,
            2,
        ),
        "expected_yield_per_area": round(
            expected_per_area,
            2,
        ),
    }


# ============================================================
# CROP FINANCIAL ANALYSIS
# ============================================================

def calculate_crop_financials(
    *,
    estimated_cost: Any = 0,
    actual_cost: Any = 0,
    expected_revenue: Any = 0,
    actual_revenue: Any = 0,
    currency: str = "KES",
) -> dict:
    """
    Calculate crop profitability.
    """

    estimated = _float(
        estimated_cost
    )

    actual = _float(
        actual_cost
    )

    expected_revenue_value = _float(
        expected_revenue
    )

    actual_revenue_value = _float(
        actual_revenue
    )

    expected_profit = (
        expected_revenue_value
        - estimated
    )

    actual_profit = (
        actual_revenue_value
        - actual
    )

    if expected_revenue_value > 0:
        expected_margin = (
            expected_profit
            / expected_revenue_value
        ) * 100

    else:
        expected_margin = 0

    if actual_revenue_value > 0:
        actual_margin = (
            actual_profit
            / actual_revenue_value
        ) * 100

    else:
        actual_margin = 0

    return {
        "currency": currency,

        "estimated_cost": estimated,

        "actual_cost": actual,

        "expected_revenue": expected_revenue_value,

        "actual_revenue": actual_revenue_value,

        "expected_profit": round(
            expected_profit,
            2,
        ),

        "actual_profit": round(
            actual_profit,
            2,
        ),

        "expected_margin_percentage": round(
            expected_margin,
            2,
        ),

        "actual_margin_percentage": round(
            actual_margin,
            2,
        ),

        "profitable": (
            actual_profit > 0
            if actual_revenue_value > 0
            else expected_profit > 0
        ),
    }


# ============================================================
# WEATHER INTELLIGENCE
# ============================================================

def weather_snapshot(
    *,
    temperature: Any = None,
    humidity: Any = None,
    rainfall: Any = None,
    rainfall_probability: Any = None,
    wind_speed: Any = None,
    condition: str = "",
    forecast_date: Any = None,
) -> dict:
    """
    Normalize weather information before storing it.

    Weather providers can differ in their response format.
    Shamba should have one internal representation.
    """

    return {
        "temperature": (
            _float(temperature)
            if temperature is not None
            else None
        ),

        "humidity": (
            _float(humidity)
            if humidity is not None
            else None
        ),

        "rainfall": (
            _float(rainfall)
            if rainfall is not None
            else None
        ),

        "rainfall_probability": (
            clamp_score(
                rainfall_probability
            )
            if rainfall_probability is not None
            else None
        ),

        "wind_speed": (
            _float(wind_speed)
            if wind_speed is not None
            else None
        ),

        "condition": condition,

        "forecast_date": forecast_date,

        "captured_at": now_utc(),
    }


# ============================================================
# MARKET INTELLIGENCE
# ============================================================

def market_snapshot(
    *,
    crop_name: str,
    price: Any = 0,
    previous_price: Any = 0,
    unit: str = "kg",
    market: str = "",
    currency: str = "KES",
    demand_score: Any = 50,
) -> dict:
    """
    Normalize crop market information.

    This can later be populated from:
        - Jumuiya marketplace
        - Biashara
        - external market data
        - manually entered farmer data
    """

    current_price = _float(price)
    old_price = _float(previous_price)

    if old_price > 0:
        change_percentage = (
            (current_price - old_price)
            / old_price
        ) * 100

    else:
        change_percentage = 0

    demand = clamp_score(
        demand_score
    )

    if change_percentage > 10:
        trend = "strong_rise"

    elif change_percentage > 2:
        trend = "rising"

    elif change_percentage < -10:
        trend = "strong_fall"

    elif change_percentage < -2:
        trend = "falling"

    else:
        trend = "stable"

    return {
        "crop_name": crop_name,

        "price": current_price,

        "previous_price": old_price,

        "price_change_percentage": round(
            change_percentage,
            2,
        ),

        "trend": trend,

        "unit": unit,

        "market": market,

        "currency": currency,

        "demand_score": demand,

        "captured_at": now_utc(),
    }


# ============================================================
# FARM RECOMMENDATION
# ============================================================

def recommendation_document(
    *,
    owner_user_id: str,
    farm_id: str,
    title: str,
    recommendation: str,
    category: str = "general",
    priority: str = "normal",
    confidence: Any = 50,
    source: str = "shamba",
    crop_id: str | None = None,
    expires_at: Any = None,
) -> dict:
    """
    Create a standardized Shamba recommendation.

    Categories can include:
        crop
        weather
        irrigation
        soil
        pest
        disease
        market
        financial
        harvest
        general
    """

    return {
        "owner_user_id": str(
            owner_user_id
        ),

        "farm_id": str(
            farm_id
        ),

        "crop_id": (
            str(crop_id)
            if crop_id
            else None
        ),

        "title": title,

        "recommendation": recommendation,

        "category": category,

        "priority": priority,

        "confidence": clamp_score(
            confidence
        ),

        "source": source,

        "status": "active",

        "expires_at": expires_at,

        "created_at": now_utc(),

        "updated_at": now_utc(),
    }


# ============================================================
# FARM ALERT
# ============================================================

def alert_document(
    *,
    owner_user_id: str,
    farm_id: str,
    title: str,
    message: str,
    alert_type: str = "general",
    severity: str = "info",
    crop_id: str | None = None,
    action: str = "",
    source: str = "shamba",
    expires_at: Any = None,
) -> dict:
    """
    Create a farm alert.

    Alerts are intended for actionable events rather than
    generic notifications.
    """

    return {
        "owner_user_id": str(
            owner_user_id
        ),

        "farm_id": str(
            farm_id
        ),

        "crop_id": (
            str(crop_id)
            if crop_id
            else None
        ),

        "title": title,

        "message": message,

        "alert_type": alert_type,

        "severity": severity,

        "recommended_action": action,

        "source": source,

        "read": False,

        "status": "active",

        "expires_at": expires_at,

        "created_at": now_utc(),

        "updated_at": now_utc(),
    }


# ============================================================
# FARM INSIGHT DOCUMENT
# ============================================================

def farm_insight_document(
    *,
    owner_user_id: str,
    farm_id: str,
    health_score: Any = 50,
    productivity_score: Any = 50,
    risk_score: Any = 50,
    soil_score: Any = 50,
    water_score: Any = 50,
    crop_score: Any = 50,
    financial_score: Any = 50,
    summary: str = "",
    strengths: Any = None,
    risks: Any = None,
    recommendations: Any = None,
    ai_summary: str = "",
    model: str = "",
) -> dict:
    """
    Store the current intelligence snapshot for a farm.

    This document is intentionally separate from the farm
    itself because intelligence changes much more frequently
    than farm identity data.
    """

    health = calculate_farm_health(
        soil_score=soil_score,
        water_score=water_score,
        crop_score=crop_score,
        productivity_score=productivity_score,
        financial_score=financial_score,
        risk_score=risk_score,
    )

    risk = clamp_score(
        risk_score
    )

    return {
        # ----------------------------------------------------
        # OWNERSHIP
        # ----------------------------------------------------
        "owner_user_id": str(
            owner_user_id
        ),

        "farm_id": str(
            farm_id
        ),

        # ----------------------------------------------------
        # OVERALL HEALTH
        # ----------------------------------------------------
        "health_score": health["score"],

        "health_status": health["status"],

        "health_components": health[
            "components"
        ],

        # ----------------------------------------------------
        # PRODUCTIVITY
        # ----------------------------------------------------
        "productivity_score": clamp_score(
            productivity_score
        ),

        # ----------------------------------------------------
        # RISK
        # ----------------------------------------------------
        "risk_score": risk,

        "risk_level": risk_level(
            risk
        ),

        # ----------------------------------------------------
        # FARM COMPONENTS
        # ----------------------------------------------------
        "soil_score": clamp_score(
            soil_score
        ),

        "water_score": clamp_score(
            water_score
        ),

        "crop_score": clamp_score(
            crop_score
        ),

        "financial_score": clamp_score(
            financial_score
        ),

        # ----------------------------------------------------
        # HUMAN-READABLE INTELLIGENCE
        # ----------------------------------------------------
        "summary": summary,

        "strengths": _list(
            strengths
        ),

        "risks": _list(
            risks
        ),

        "recommendations": _list(
            recommendations
        ),

        # ----------------------------------------------------
        # AI
        # ----------------------------------------------------
        "ai_summary": ai_summary,

        "ai_model": model,

        "ai_generated": bool(
            ai_summary
        ),

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------
        "status": "active",

        # ----------------------------------------------------
        # TIMESTAMP
        # ----------------------------------------------------
        "generated_at": now_utc(),

        "updated_at": now_utc(),
    }


# ============================================================
# FARM AI CONTEXT
# ============================================================

def build_ai_farm_context(
    *,
    farmer: dict | None = None,
    farm: dict | None = None,
    crops: list[dict] | None = None,
    activities: list[dict] | None = None,
    harvests: list[dict] | None = None,
    weather: dict | None = None,
    market: list[dict] | None = None,
    insights: dict | None = None,
) -> dict:
    """
    Build a clean context object for RevelaAI.

    IMPORTANT:
    This is not an AI prompt.

    It is structured agricultural context that the
    RevelaAI orchestrator can transform into an appropriate
    prompt depending on the farmer's question.
    """

    farmer = farmer or {}
    farm = farm or {}
    crops = crops or []
    activities = activities or []
    harvests = harvests or []
    market = market or []
    insights = insights or {}

    return {
        "domain": "shamba",

        "farmer": {
            "name": farmer.get(
                "farmer_name",
                "",
            ),

            "experience_years": farmer.get(
                "experience_years",
                0,
            ),

            "farming_type": farmer.get(
                "farming_type",
                "",
            ),

            "primary_goal": farmer.get(
                "primary_goal",
                "",
            ),
        },

        "farm": {
            "id": farm.get(
                "_id"
            ),

            "name": farm.get(
                "name",
                "",
            ),

            "county": farm.get(
                "county",
                "",
            ),

            "town": farm.get(
                "town",
                "",
            ),

            "location": farm.get(
                "location",
                "",
            ),

            "latitude": farm.get(
                "latitude"
            ),

            "longitude": farm.get(
                "longitude"
            ),

            "location_accuracy": farm.get(
                "location_accuracy"
            ),

            "size": farm.get(
                "size",
                0,
            ),

            "size_unit": farm.get(
                "size_unit",
                "acres",
            ),

            "soil_type": farm.get(
                "soil_type",
                "",
            ),

            "soil_ph": farm.get(
                "soil_ph"
            ),

            "water_source": farm.get(
                "water_source",
                "",
            ),

            "irrigation": farm.get(
                "irrigation",
                False,
            ),

            "farming_type": farm.get(
                "farming_type",
                "",
            ),

            "production_system": farm.get(
                "production_system",
                "",
            ),

            "climate_zone": farm.get(
                "climate_zone",
                "",
            ),

            "current_season": farm.get(
                "current_season",
                "",
            ),
        },

        "crops": crops,

        "activities": activities,

        "harvests": harvests,

        "weather": weather or {},

        "market": market,

        "intelligence": {
            "health_score": insights.get(
                "health_score"
            ),

            "health_status": insights.get(
                "health_status"
            ),

            "productivity_score": insights.get(
                "productivity_score"
            ),

            "risk_score": insights.get(
                "risk_score"
            ),

            "risk_level": insights.get(
                "risk_level"
            ),

            "strengths": insights.get(
                "strengths",
                [],
            ),

            "risks": insights.get(
                "risks",
                [],
            ),

            "recommendations": insights.get(
                "recommendations",
                [],
            ),
        },

        "generated_at": now_utc(),
    }


# ============================================================
# SHAMBA DASHBOARD SUMMARY
# ============================================================

def build_dashboard_summary(
    *,
    farm: dict | None = None,
    crops: list[dict] | None = None,
    activities: list[dict] | None = None,
    harvests: list[dict] | None = None,
    insight: dict | None = None,
) -> dict:
    """
    Build a lightweight dashboard summary.

    This is designed for:
        GET /api/jumuiya/shamba/dashboard

    It avoids sending large agricultural datasets to the
    frontend when the dashboard only needs summary metrics.
    """

    farm = farm or {}
    crops = crops or []
    activities = activities or []
    harvests = harvests or []
    insight = insight or {}

    active_crops = [
        crop
        for crop in crops
        if crop.get(
            "status",
            "growing",
        )
        not in {
            "harvested",
            "completed",
            "cancelled",
        }
    ]

    total_area = sum(
        _float(
            crop.get("area")
        )
        for crop in active_crops
    )

    total_expected_yield = sum(
        _float(
            crop.get("expected_yield")
        )
        for crop in active_crops
    )

    total_actual_yield = sum(
        _float(
            crop.get("actual_yield")
        )
        for crop in active_crops
    )

    total_cost = sum(
        _float(
            crop.get("actual_cost")
        )
        for crop in crops
    )

    total_expected_revenue = sum(
        _float(
            crop.get("expected_revenue")
        )
        for crop in crops
    )

    total_harvested = sum(
        _float(
            harvest.get("quantity")
        )
        for harvest in harvests
    )

    total_sold = sum(
        _float(
            harvest.get("sold_quantity")
        )
        for harvest in harvests
    )

    total_revenue = sum(
        _float(
            harvest.get("revenue")
        )
        for harvest in harvests
    )

    return {
        # ----------------------------------------------------
        # FARM
        # ----------------------------------------------------
        "farm": {
            "id": farm.get(
                "_id"
            ),

            "name": farm.get(
                "name",
                "",
            ),

            "county": farm.get(
                "county",
                "",
            ),

            "town": farm.get(
                "town",
                "",
            ),

            "location": farm.get(
                "location",
                "",
            ),

            "latitude": farm.get(
                "latitude"
            ),

            "longitude": farm.get(
                "longitude"
            ),

            "location_accuracy": farm.get(
                "location_accuracy"
            ),

            "size": farm.get(
                "size",
                0,
            ),

            "size_unit": farm.get(
                "size_unit",
                "acres",
            ),
        },

        # ----------------------------------------------------
        # HEALTH
        # ----------------------------------------------------
        "health": {
            "score": insight.get(
                "health_score"
            ),

            "status": insight.get(
                "health_status",
                "unknown",
            ),

            "risk_level": insight.get(
                "risk_level",
                "unknown",
            ),
        },

        # ----------------------------------------------------
        # CROPS
        # ----------------------------------------------------
        "crops": {
            "total": len(crops),

            "active": len(
                active_crops
            ),

            "area": round(
                total_area,
                2,
            ),

            "expected_yield": round(
                total_expected_yield,
                2,
            ),

            "actual_yield": round(
                total_actual_yield,
                2,
            ),
        },

        # ----------------------------------------------------
        # FINANCIAL
        # ----------------------------------------------------
        "financial": {
            "total_cost": round(
                total_cost,
                2,
            ),

            "expected_revenue": round(
                total_expected_revenue,
                2,
            ),

            "expected_profit": round(
                total_expected_revenue
                - total_cost,
                2,
            ),

            "harvest_revenue": round(
                total_revenue,
                2,
            ),
        },

        # ----------------------------------------------------
        # HARVEST
        # ----------------------------------------------------
        "harvests": {
            "total": len(
                harvests
            ),

            "quantity": round(
                total_harvested,
                2,
            ),

            "sold_quantity": round(
                total_sold,
                2,
            ),

            "available_quantity": round(
                max(
                    total_harvested
                    - total_sold,
                    0,
                ),
                2,
            ),
        },

        # ----------------------------------------------------
        # OPERATIONS
        # ----------------------------------------------------
        "activities": {
            "total": len(
                activities
            ),
        },

        # ----------------------------------------------------
        # INTELLIGENCE
        # ----------------------------------------------------
        "recommendations": insight.get(
            "recommendations",
            [],
        ),

        "risks": insight.get(
            "risks",
            [],
        ),

        "updated_at": now_utc(),
    }
