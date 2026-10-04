from __future__ import annotations

from datetime import datetime, timezone


def now_utc():
    return datetime.now(timezone.utc)


def _float(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value, default=False):
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    return str(value).lower() in {"true", "1", "yes", "on"}


def farmer_document(user_id, data):
    now = now_utc()

    return {
        # ---------------------------------------------------------
        # IDENTITY
        # ---------------------------------------------------------
        "user_id": str(user_id),
        "farmer_name": data["farmer_name"],
        "phone": data.get("phone", ""),

        # ---------------------------------------------------------
        # FARM PROFILE
        # ---------------------------------------------------------
        "farm_name": data.get("farm_name", ""),
        "farm_count": int(data.get("farm_count", 1)),
        "farming_type": data.get("farming_type", "mixed"),
        "experience_years": int(data.get("experience_years", 0)),

        # ---------------------------------------------------------
        # LOCATION
        # ---------------------------------------------------------
        "county": data.get("county", ""),
        "town": data.get("town", ""),
        "location": data.get("location", ""),

        # Optional GPS intelligence
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "location_accuracy": data.get("location_accuracy"),
        "location_source": data.get("location_source", "manual"),

        # ---------------------------------------------------------
        # FARM SIZE
        # ---------------------------------------------------------
        "farm_size": _float(data.get("farm_size")),
        "farm_size_unit": data.get("farm_size_unit", "acres"),

        # ---------------------------------------------------------
        # AGRICULTURAL PROFILE
        # ---------------------------------------------------------
        "primary_crops": data.get("primary_crops", []),
        "livestock": data.get("livestock", []),
        "soil_type": data.get("soil_type", ""),
        "water_source": data.get("water_source", ""),
        "irrigation_available": _bool(
            data.get("irrigation_available")
        ),

        # ---------------------------------------------------------
        # FARM OBJECTIVES
        # ---------------------------------------------------------
        "primary_goal": data.get(
            "primary_goal",
            "food_and_income",
        ),

        # Examples:
        # food_and_income
        # commercial
        # subsistence
        # livestock
        # export
        # agribusiness

        "target_market": data.get("target_market", ""),
        "description": data.get("description", ""),

        # ---------------------------------------------------------
        # INTELLIGENCE PROFILE
        # ---------------------------------------------------------
        "profile_completed": bool(
            data.get("profile_completed", False)
        ),

        "last_ai_analysis": None,
        "last_weather_sync": None,
        "last_market_sync": None,

        # ---------------------------------------------------------
        # STATUS
        # ---------------------------------------------------------
        "status": "active",

        "created_at": now,
        "updated_at": now,
    }
