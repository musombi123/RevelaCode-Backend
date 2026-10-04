from __future__ import annotations

from datetime import datetime, timezone


# ============================================================
# TIME
# ============================================================

def now_utc():
    return datetime.now(timezone.utc)


# ============================================================
# SAFE VALUE HELPERS
# ============================================================

def _float(value, default=0.0):
    """
    Safely convert a value to float.

    Prevents malformed frontend input from breaking
    document creation.
    """
    try:
        if value in (None, ""):
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def _int(value, default=0):
    """
    Safely convert a value to int.
    """
    try:
        if value in (None, ""):
            return default

        return int(value)

    except (TypeError, ValueError):
        return default


def _bool(value, default=False):
    """
    Safely normalize boolean-like frontend values.
    """
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    return str(value).strip().lower() in {
        "true",
        "1",
        "yes",
        "on",
    }


def _list(value, default=None):
    """
    Ensure list-based fields always remain lists.
    """
    if default is None:
        default = []

    if value is None:
        return default

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    return [value]


# ============================================================
# FARMER
# ============================================================

def farmer_document(user_id, data):
    """
    Create the canonical Shamba farmer profile.

    A farmer is more than an authenticated user. This document
    contains the agricultural profile required by Shamba and
    RevelaAI to understand the farmer's operating environment.
    """

    now = now_utc()

    return {
        # ----------------------------------------------------
        # IDENTITY
        # ----------------------------------------------------
        "user_id": str(user_id),

        "farmer_name": data["farmer_name"],

        "phone": data.get(
            "phone",
            "",
        ),

        # ----------------------------------------------------
        # FARM PROFILE
        # ----------------------------------------------------
        "farm_name": data.get(
            "farm_name",
            "",
        ),

        "farm_count": _int(
            data.get("farm_count"),
            1,
        ),

        "farming_type": data.get(
            "farming_type",
            "mixed",
        ),

        "experience_years": _int(
            data.get("experience_years"),
            0,
        ),

        # ----------------------------------------------------
        # LOCATION
        # ----------------------------------------------------
        "county": data.get(
            "county",
            "",
        ),

        "town": data.get(
            "town",
            "",
        ),

        "location": data.get(
            "location",
            "",
        ),

        # Optional precise farm coordinates.
        #
        # These should only be supplied when the farmer has
        # explicitly granted location permission or entered
        # the coordinates manually.
        "latitude": data.get(
            "latitude"
        ),

        "longitude": data.get(
            "longitude"
        ),

        "location_accuracy": data.get(
            "location_accuracy"
        ),

        "location_source": data.get(
            "location_source",
            "manual",
        ),

        # ----------------------------------------------------
        # FARM SIZE
        # ----------------------------------------------------
        "farm_size": _float(
            data.get("farm_size")
        ),

        "farm_size_unit": data.get(
            "farm_size_unit",
            "acres",
        ),

        # ----------------------------------------------------
        # AGRICULTURAL PROFILE
        # ----------------------------------------------------
        "primary_crops": _list(
            data.get("primary_crops")
        ),

        "livestock": _list(
            data.get("livestock")
        ),

        "soil_type": data.get(
            "soil_type",
            "",
        ),

        "water_source": data.get(
            "water_source",
            "",
        ),

        "irrigation_available": _bool(
            data.get("irrigation_available")
        ),

        # ----------------------------------------------------
        # FARM OBJECTIVES
        # ----------------------------------------------------
        "primary_goal": data.get(
            "primary_goal",
            "food_and_income",
        ),

        # Possible values:
        #
        # food_and_income
        # commercial
        # subsistence
        # livestock
        # export
        # agribusiness

        "target_market": data.get(
            "target_market",
            "",
        ),

        "description": data.get(
            "description",
            "",
        ),

        # ----------------------------------------------------
        # SHAMBA INTELLIGENCE STATE
        # ----------------------------------------------------
        "profile_completed": bool(
            data.get(
                "profile_completed",
                False,
            )
        ),

        "last_ai_analysis": None,

        "last_weather_sync": None,

        "last_market_sync": None,

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------
        "status": "active",

        # ----------------------------------------------------
        # AUDIT
        # ----------------------------------------------------
        "created_at": now,

        "updated_at": now,
    }


# ============================================================
# FARM
# ============================================================

def farm_document(user_id, data):
    """
    Create a Shamba farm.

    The farm is the central agricultural operating unit.
    Crops, activities, harvests, intelligence and future
    marketplace operations can all reference this farm.
    """

    now = now_utc()

    return {
        # ----------------------------------------------------
        # OWNERSHIP
        # ----------------------------------------------------
        "owner_user_id": str(user_id),

        # ----------------------------------------------------
        # FARM IDENTITY
        # ----------------------------------------------------
        "name": data["name"],

        "farm_code": data.get(
            "farm_code",
            "",
        ),

        # ----------------------------------------------------
        # LOCATION
        # ----------------------------------------------------
        "county": data.get(
            "county",
            "",
        ),

        "town": data.get(
            "town",
            "",
        ),

        "location": data.get(
            "location",
            "",
        ),

        # GPS intelligence.
        #
        # latitude / longitude:
        #   Farm coordinates.
        #
        # location_accuracy:
        #   Estimated GPS accuracy in metres.
        #
        # location_source:
        #   gps / manual / map / imported
        "latitude": data.get(
            "latitude"
        ),

        "longitude": data.get(
            "longitude"
        ),

        "location_accuracy": data.get(
            "location_accuracy"
        ),

        "location_source": data.get(
            "location_source",
            "manual",
        ),

        # ----------------------------------------------------
        # LAND
        # ----------------------------------------------------
        "size": _float(
            data.get("size")
        ),

        "size_unit": data.get(
            "size_unit",
            "acres",
        ),

        # ----------------------------------------------------
        # SOIL
        # ----------------------------------------------------
        "soil_type": data.get(
            "soil_type",
            "",
        ),

        "soil_ph": data.get(
            "soil_ph"
        ),

        "soil_fertility": data.get(
            "soil_fertility",
            "",
        ),

        # ----------------------------------------------------
        # WATER
        # ----------------------------------------------------
        "irrigation": _bool(
            data.get("irrigation")
        ),

        "water_source": data.get(
            "water_source",
            "",
        ),

        "water_reliability": data.get(
            "water_reliability",
            "",
        ),

        # ----------------------------------------------------
        # FARMING SYSTEM
        # ----------------------------------------------------
        "farming_type": data.get(
            "farming_type",
            "mixed",
        ),

        "production_system": data.get(
            "production_system",
            "conventional",
        ),

        # ----------------------------------------------------
        # PRODUCTIVITY
        # ----------------------------------------------------
        "productivity_score": data.get(
            "productivity_score"
        ),

        "health_score": data.get(
            "health_score"
        ),

        # ----------------------------------------------------
        # CLIMATE / SEASON
        # ----------------------------------------------------
        "climate_zone": data.get(
            "climate_zone",
            "",
        ),

        "current_season": data.get(
            "current_season",
            "",
        ),

        # ----------------------------------------------------
        # RISK
        # ----------------------------------------------------
        "risk_level": data.get(
            "risk_level",
            "unknown",
        ),

        # ----------------------------------------------------
        # INTELLIGENCE SYNC
        # ----------------------------------------------------
        "last_weather_sync": None,

        "last_market_sync": None,

        "last_ai_analysis": None,

        # ----------------------------------------------------
        # DESCRIPTION
        # ----------------------------------------------------
        "description": data.get(
            "description",
            "",
        ),

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------
        "status": "active",

        # ----------------------------------------------------
        # AUDIT
        # ----------------------------------------------------
        "created_at": now,

        "updated_at": now,
    }


# ============================================================
# CROP
# ============================================================

def crop_document(user_id, farm_id, data):
    """
    Create a crop record.

    Crops contain production, health, financial and market
    information so Shamba can eventually calculate yield,
    profitability and agricultural risk.
    """

    now = now_utc()

    return {
        # ----------------------------------------------------
        # OWNERSHIP
        # ----------------------------------------------------
        "owner_user_id": str(user_id),

        "farm_id": str(farm_id),

        # ----------------------------------------------------
        # CROP IDENTITY
        # ----------------------------------------------------
        "name": data["name"],

        "variety": data.get(
            "variety",
            "",
        ),

        "category": data.get(
            "category",
            "food_crop",
        ),

        # ----------------------------------------------------
        # SEASON
        # ----------------------------------------------------
        "season": data.get(
            "season",
            "",
        ),

        "planting_date": data.get(
            "planting_date"
        ),

        "expected_harvest_date": data.get(
            "expected_harvest_date"
        ),

        # ----------------------------------------------------
        # LAND ALLOCATION
        # ----------------------------------------------------
        "area": _float(
            data.get("area")
        ),

        "area_unit": data.get(
            "area_unit",
            "acres",
        ),

        # ----------------------------------------------------
        # PRODUCTION
        # ----------------------------------------------------
        "expected_yield": _float(
            data.get("expected_yield")
        ),

        "expected_yield_unit": data.get(
            "expected_yield_unit",
            "kg",
        ),

        "actual_yield": _float(
            data.get("actual_yield")
        ),

        # ----------------------------------------------------
        # INPUTS
        # ----------------------------------------------------
        "seed_source": data.get(
            "seed_source",
            "",
        ),

        "fertilizer_used": _list(
            data.get("fertilizer_used")
        ),

        "pesticides_used": _list(
            data.get("pesticides_used")
        ),

        # ----------------------------------------------------
        # CROP HEALTH
        # ----------------------------------------------------
        "health_status": data.get(
            "health_status",
            "unknown",
        ),

        "pest_risk": data.get(
            "pest_risk",
            "unknown",
        ),

        "disease_risk": data.get(
            "disease_risk",
            "unknown",
        ),

        # ----------------------------------------------------
        # FINANCIAL INTELLIGENCE
        # ----------------------------------------------------
        "estimated_cost": _float(
            data.get("estimated_cost")
        ),

        "actual_cost": _float(
            data.get("actual_cost")
        ),

        "expected_revenue": _float(
            data.get("expected_revenue")
        ),

        # ----------------------------------------------------
        # MARKET
        # ----------------------------------------------------
        "target_market": data.get(
            "target_market",
            "",
        ),

        "market_price": _float(
            data.get("market_price")
        ),

        "market_price_unit": data.get(
            "market_price_unit",
            "kg",
        ),

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------
        "status": data.get(
            "status",
            "growing",
        ),

        "notes": data.get(
            "notes",
            "",
        ),

        # ----------------------------------------------------
        # AUDIT
        # ----------------------------------------------------
        "created_at": now,

        "updated_at": now,
    }


# ============================================================
# FARM ACTIVITY
# ============================================================

def farm_activity_document(user_id, farm_id, data):
    """
    Create a farm activity.

    Activities become the operational and financial history
    of the farm.
    """

    now = now_utc()

    return {
        # ----------------------------------------------------
        # OWNERSHIP
        # ----------------------------------------------------
        "owner_user_id": str(user_id),

        "farm_id": str(farm_id),

        # ----------------------------------------------------
        # ACTIVITY
        # ----------------------------------------------------
        "type": data["type"],

        # Common types:
        #
        # planting
        # ploughing
        # weeding
        # fertilizer
        # spraying
        # irrigation
        # harvesting
        # transport
        # labour
        # livestock
        # maintenance
        # other

        "description": data.get(
            "description",
            "",
        ),

        "activity_date": data.get(
            "activity_date"
        ),

        # ----------------------------------------------------
        # FINANCIAL
        # ----------------------------------------------------
        "cost": _float(
            data.get("cost")
        ),

        "currency": data.get(
            "currency",
            "KES",
        ),

        "payment_status": data.get(
            "payment_status",
            "paid",
        ),

        # ----------------------------------------------------
        # RESOURCE USAGE
        # ----------------------------------------------------
        "quantity": _float(
            data.get("quantity")
        ),

        "quantity_unit": data.get(
            "quantity_unit",
            "",
        ),

        "provider": data.get(
            "provider",
            "",
        ),

        # ----------------------------------------------------
        # CROP LINK
        # ----------------------------------------------------
        "crop_id": data.get(
            "crop_id"
        ),

        # ----------------------------------------------------
        # NOTES
        # ----------------------------------------------------
        "notes": data.get(
            "notes",
            "",
        ),

        # ----------------------------------------------------
        # AUDIT
        # ----------------------------------------------------
        "created_at": now,

        "updated_at": now,
    }


# ============================================================
# HARVEST
# ============================================================

def harvest_document(user_id, farm_id, data):
    """
    Create a harvest record.

    Harvests form the bridge between farm production and
    the Jumuiya marketplace / Biashara ecosystem.
    """

    now = now_utc()

    quantity = _float(
        data.get("quantity")
    )

    sold_quantity = _float(
        data.get("sold_quantity")
    )

    # Prevent impossible negative inventory.
    remaining_quantity = max(
        quantity - sold_quantity,
        0,
    )

    return {
        # ----------------------------------------------------
        # OWNERSHIP
        # ----------------------------------------------------
        "owner_user_id": str(user_id),

        "farm_id": str(farm_id),

        # ----------------------------------------------------
        # CROP
        # ----------------------------------------------------
        "crop_id": data.get(
            "crop_id"
        ),

        "crop_name": data["crop_name"],

        # ----------------------------------------------------
        # PRODUCTION
        # ----------------------------------------------------
        "quantity": quantity,

        "unit": data.get(
            "unit",
            "kg",
        ),

        "quality": data.get(
            "quality",
            "",
        ),

        "harvest_date": data.get(
            "harvest_date"
        ),

        # ----------------------------------------------------
        # MARKET
        # ----------------------------------------------------
        "market_status": data.get(
            "market_status",
            "available",
        ),

        "asking_price": _float(
            data.get("asking_price")
        ),

        "price_unit": data.get(
            "price_unit",
            "kg",
        ),

        "target_market": data.get(
            "target_market",
            "",
        ),

        # ----------------------------------------------------
        # BUYER
        # ----------------------------------------------------
        "buyer_id": data.get(
            "buyer_id"
        ),

        "buyer_name": data.get(
            "buyer_name",
            "",
        ),

        # ----------------------------------------------------
        # SALES
        # ----------------------------------------------------
        "sold_quantity": sold_quantity,

        "remaining_quantity": remaining_quantity,

        "revenue": _float(
            data.get("revenue")
        ),

        "sold_at": data.get(
            "sold_at"
        ),

        # ----------------------------------------------------
        # NOTES
        # ----------------------------------------------------
        "notes": data.get(
            "notes",
            "",
        ),

        # ----------------------------------------------------
        # AUDIT
        # ----------------------------------------------------
        "created_at": now,

        "updated_at": now,
    }
