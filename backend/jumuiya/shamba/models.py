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
    """Create a canonical Shamba farmer profile without trusting client review state."""
    now = now_utc()
    payload = dict(data or {})
    intent = str(payload.pop("intent", "submit") or "submit").strip().lower()
    required = ("farmer_name", "phone", "county", "town", "farming_type")
    profile_completed = all(str(payload.get(key, "")).strip() for key in required)
    submitted = intent == "submit"

    document = {
        "owner_user_id": str(user_id),
        # Retain the legacy alias; owner_user_id is canonical for new writes.
        "user_id": str(user_id),
        "farmer_name": payload.get("farmer_name", ""),
        "phone": payload.get("phone", ""),
        "preferred_contact_method": payload.get("preferred_contact_method", "phone"),
        "farm_name": payload.get("farm_name", ""),
        "farm_count": _int(payload.get("farm_count"), 1),
        "farming_type": payload.get("farming_type", "mixed"),
        "experience_years": _int(payload.get("experience_years"), 0),
        "county": payload.get("county", ""),
        "sub_county": payload.get("sub_county", ""),
        "town": payload.get("town", ""),
        "village": payload.get("village", ""),
        "location": payload.get("location", ""),
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "location_accuracy": payload.get("location_accuracy"),
        "location_source": payload.get("location_source", "manual"),
        "location_precision": payload.get("location_precision", "unspecified"),
        "gps_consent": _bool(payload.get("gps_consent")),
        "farm_size": _float(payload.get("farm_size")),
        "farm_size_unit": payload.get("farm_size_unit", "acres"),
        "primary_crops": _list(payload.get("primary_crops")),
        "livestock": _list(payload.get("livestock")),
        "soil_type": payload.get("soil_type", ""),
        "water_source": payload.get("water_source", ""),
        "irrigation_available": _bool(payload.get("irrigation_available")),
        "primary_goal": payload.get("primary_goal", "food_and_income"),
        "target_market": payload.get("target_market", ""),
        "description": payload.get("description", ""),
        "declaration": _bool(payload.get("declaration")),
        "privacy_consent": _bool(payload.get("privacy_consent")),
        "profile_completed": profile_completed,
        # The server owns review state; saving a draft grants no privileges.
        "verification_status": "pending" if submitted else "draft",
        "verification_submitted_at": now if submitted else None,
        "verification_review_notes": "",
        "verification_reviewer_user_id": None,
        "verification_reviewed_at": None,
        "verification_history": [],
        "last_ai_analysis": None,
        "last_weather_sync": None,
        "last_market_sync": None,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    return document


# ============================================================
# FARM
# ============================================================

def farm_document(user_id, data):
    """Create a Shamba farm; farm-rights verification remains a separate review."""
    now = now_utc()
    payload = dict(data or {})
    return {
        "owner_user_id": str(user_id),
        "name": payload["name"],
        "farm_code": payload.get("farm_code", ""),
        "county": payload.get("county", ""),
        "town": payload.get("town", ""),
        "location": payload.get("location", ""),
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "location_accuracy": payload.get("location_accuracy"),
        "location_source": payload.get("location_source", "manual"),
        "size": _float(payload.get("size")),
        "size_unit": payload.get("size_unit", "acres"),
        "soil_type": payload.get("soil_type", ""),
        "soil_ph": payload.get("soil_ph"),
        "soil_fertility": payload.get("soil_fertility", ""),
        "irrigation": _bool(payload.get("irrigation")),
        "water_source": payload.get("water_source", ""),
        "water_reliability": payload.get("water_reliability", ""),
        "farming_type": payload.get("farming_type", "mixed"),
        "production_system": payload.get("production_system", "conventional"),
        "productivity_score": payload.get("productivity_score"),
        "health_score": payload.get("health_score"),
        "climate_zone": payload.get("climate_zone", ""),
        "current_season": payload.get("current_season", ""),
        "risk_level": payload.get("risk_level", "unknown"),
        "last_weather_sync": None,
        "last_market_sync": None,
        "last_ai_analysis": None,
        "description": payload.get("description", ""),
        # A new farm must separately complete the existing rights-review flow.
        "legal_verification_status": "not_submitted",
        "publication_status": "pending_verification",
        "status": "active",
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
