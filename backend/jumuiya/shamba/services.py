from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.audit import log_action

from backend.jumuiya.shamba.models import (
    farmer_document,
    farm_document,
    crop_document,
    farm_activity_document,
    harvest_document,
)

from backend.jumuiya.shamba.farm_insights import (
    calculate_farm_health,
    calculate_crop_risk,
    calculate_yield_analysis,
    calculate_crop_financials,
    weather_snapshot,
    market_snapshot,
    recommendation_document,
    alert_document,
    farm_insight_document,
    build_ai_farm_context,
    build_dashboard_summary,
)


# =========================================================
# CONSTANTS
# =========================================================

FARMERS = "jumuiya_farmers"
FARMS = "jumuiya_farms"
CROPS = "jumuiya_crops"
ACTIVITIES = "jumuiya_farm_activities"
HARVESTS = "jumuiya_harvests"
INSIGHTS = "jumuiya_farm_insights"
RECOMMENDATIONS = "jumuiya_farm_recommendations"
ALERTS = "jumuiya_farm_alerts"

ACTIVE_FARM_STATUSES = {
    "active",
    "operational",
    "growing",
    "planned",
}

DELETED_STATUS = "deleted"


# =========================================================
# HELPERS
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


def clean_id(value):
    """
    Convert a MongoDB id string into ObjectId when possible.

    Invalid ids are returned unchanged so Mongo queries can safely
    fail without crashing the application.
    """
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return value


def serialise(doc):
    """
    Convert MongoDB documents into JSON-safe dictionaries.
    """

    if not doc:
        return None

    out = dict(doc)

    if "_id" in out:
        out["id"] = str(out.pop("_id"))

    for key, value in list(out.items()):
        if isinstance(value, ObjectId):
            out[key] = str(value)

        elif isinstance(value, datetime):
            out[key] = value.isoformat()

        elif hasattr(value, "isoformat"):
            try:
                out[key] = value.isoformat()
            except Exception:
                pass

    return out


def serialise_many(docs):
    return [serialise(doc) for doc in docs]


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    try:
        if value is None:
            return default

        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_list(value):
    if isinstance(value, list):
        return value

    if value is None:
        return []

    return [value]


def _percentage(value):
    return round(_safe_float(value), 2)


def _normalise_id(value):
    if value is None:
        return None

    return str(value)


def _get_farm_raw(user_id, farm_id):
    """
    Internal farm lookup.

    Unlike get_farm(), this returns the raw MongoDB document.
    """

    return collection(FARMS).find_one(
        {
            "_id": clean_id(farm_id),
            "owner_user_id": str(user_id),
            "status": {"$ne": DELETED_STATUS},
        }
    )


def _require_farm(user_id, farm_id):
    """
    Return a serialised farm or raise a consistent API error.
    """

    doc = _get_farm_raw(user_id, farm_id)

    if not doc:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    return serialise(doc)


def _farm_exists(user_id, farm_id):
    return _get_farm_raw(user_id, farm_id) is not None


def _get_farm_crops(user_id, farm_id):
    docs = collection(CROPS).find(
        {
            "owner_user_id": str(user_id),
            "farm_id": str(farm_id),
            "status": {"$ne": DELETED_STATUS},
        }
    ).sort(
        "created_at",
        -1,
    )

    return list(docs)


def _get_farm_activities(user_id, farm_id):
    docs = collection(ACTIVITIES).find(
        {
            "owner_user_id": str(user_id),
            "farm_id": str(farm_id),
        }
    ).sort(
        "activity_date",
        -1,
    )

    return list(docs)


def _get_farm_harvests(user_id, farm_id):
    docs = collection(HARVESTS).find(
        {
            "owner_user_id": str(user_id),
            "farm_id": str(farm_id),
        }
    ).sort(
        "harvest_date",
        -1,
    )

    return list(docs)


def _get_weather_document(farm):
    """
    Weather data is intentionally read from the farm record first.

    A future weather integration can populate:
        weather
        weather_snapshot
        current_weather

    without changing this service contract.
    """

    return (
        farm.get("weather_snapshot")
        or farm.get("weather")
        or farm.get("current_weather")
        or {}
    )


def _get_market_document(farm):
    """
    Market data can be populated by a future market integration.
    """

    return (
        farm.get("market_snapshot")
        or farm.get("market")
        or {}
    )


def _build_farm_intelligence_payload(
    user_id,
    farm_id,
):
    """
    Collect the complete farm intelligence dataset.
    """

    farm = _require_farm(
        user_id,
        farm_id,
    )

    farmer = get_farmer(user_id)

    raw_crops = _get_farm_crops(
        user_id,
        farm_id,
    )

    raw_activities = _get_farm_activities(
        user_id,
        farm_id,
    )

    raw_harvests = _get_farm_harvests(
        user_id,
        farm_id,
    )

    crops = serialise_many(raw_crops)
    activities = serialise_many(raw_activities)
    harvests = serialise_many(raw_harvests)

    weather = weather_snapshot(
        _get_weather_document(farm)
    )

    market = market_snapshot(
        _get_market_document(farm)
    )

    return {
        "farmer": farmer,
        "farm": farm,
        "crops": crops,
        "activities": activities,
        "harvests": harvests,
        "weather": weather,
        "market": market,
    }


# =========================================================
# FARMER PROFILE
# =========================================================

def get_farmer(user_id):
    doc = collection(FARMERS).find_one(
        {
            "user_id": str(user_id)
        }
    )

    return serialise(doc)


def create_or_update_farmer(user_id, data):
    user_id = str(user_id)

    collection_ref = collection(FARMERS)

    existing = collection_ref.find_one(
        {
            "user_id": user_id
        }
    )

    if existing:
        allowed = [
            "farm_name",
            "farmer_name",
            "phone",
            "county",
            "town",
            "location",
            "farm_size",
            "farm_size_unit",
            "farming_type",
            "description",
        ]

        update = {
            key: data.get(
                key,
                existing.get(key, ""),
            )
            for key in allowed
        }

        update["updated_at"] = now_utc()

        doc = collection_ref.find_one_and_update(
            {
                "_id": existing["_id"]
            },
            {
                "$set": update
            },
            return_document=ReturnDocument.AFTER,
        )

        log_action(
            user_id,
            "farmer.profile.updated",
            "farmer",
            doc["_id"],
        )

        return serialise(doc)

    doc = farmer_document(
        user_id,
        data,
    )

    result = collection_ref.insert_one(doc)

    doc["_id"] = result.inserted_id

    log_action(
        user_id,
        "farmer.profile.created",
        "farmer",
        result.inserted_id,
    )

    return serialise(doc)


# =========================================================
# FARM
# =========================================================

def create_farm(user_id, data):
    user_id = str(user_id)

    doc = farm_document(
        user_id,
        data,
    )

    result = collection(FARMS).insert_one(doc)

    doc["_id"] = result.inserted_id

    log_action(
        user_id,
        "farm.created",
        "farm",
        result.inserted_id,
    )

    return serialise(doc)


def list_farms(user_id):
    docs = collection(FARMS).find(
        {
            "owner_user_id": str(user_id),
            "status": {
                "$ne": DELETED_STATUS
            },
        }
    ).sort(
        "created_at",
        -1,
    )

    return serialise_many(docs)


def get_farm(user_id, farm_id):
    return _require_farm(
        user_id,
        farm_id,
    )


def update_farm(user_id, farm_id, data):
    allowed = [
        "name",
        "county",
        "town",
        "location",
        "size",
        "size_unit",
        "soil_type",
        "irrigation",
        "description",
    ]

    update = {
        key: data[key]
        for key in allowed
        if key in data
    }

    update["updated_at"] = now_utc()

    doc = collection(FARMS).find_one_and_update(
        {
            "_id": clean_id(farm_id),
            "owner_user_id": str(user_id),
            "status": {
                "$ne": DELETED_STATUS
            },
        },
        {
            "$set": update
        },
        return_document=ReturnDocument.AFTER,
    )

    if not doc:
        raise APIError(
            "Farm not found or not owned by you.",
            404,
            "farm_not_found",
        )

    log_action(
        user_id,
        "farm.updated",
        "farm",
        doc["_id"],
    )

    return serialise(doc)


def delete_farm(user_id, farm_id):
    result = collection(FARMS).update_one(
        {
            "_id": clean_id(farm_id),
            "owner_user_id": str(user_id),
            "status": {
                "$ne": DELETED_STATUS
            },
        },
        {
            "$set": {
                "status": DELETED_STATUS,
                "updated_at": now_utc(),
            }
        },
    )

    if result.modified_count != 1:
        raise APIError(
            "Farm not found or not owned by you.",
            404,
            "farm_not_found",
        )

    log_action(
        user_id,
        "farm.deleted",
        "farm",
        farm_id,
    )

    return {
        "deleted": True,
        "id": str(farm_id),
    }


# =========================================================
# FARM LOCATION
# =========================================================

def update_farm_location(
    user_id,
    farm_id,
    latitude,
    longitude,
    accuracy=None,
    source="gps",
    county=None,
    town=None,
    location=None,
):
    """
    Persist the best available farm GPS location.

    This is intentionally separate from farm_payload() so the
    existing frontend does not have to change immediately.
    """

    latitude = _safe_float(latitude)
    longitude = _safe_float(longitude)

    if not -90 <= latitude <= 90:
        raise APIError(
            "Invalid latitude.",
            422,
            "invalid_latitude",
        )

    if not -180 <= longitude <= 180:
        raise APIError(
            "Invalid longitude.",
            422,
            "invalid_longitude",
        )

    update = {
        "latitude": latitude,
        "longitude": longitude,
        "location_source": source or "gps",
        "updated_at": now_utc(),
    }

    if accuracy is not None:
        update["location_accuracy"] = _safe_float(
            accuracy
        )

    if county:
        update["county"] = str(county).strip()

    if town:
        update["town"] = str(town).strip()

    if location:
        update["location"] = str(location).strip()

    doc = collection(FARMS).find_one_and_update(
        {
            "_id": clean_id(farm_id),
            "owner_user_id": str(user_id),
            "status": {
                "$ne": DELETED_STATUS
            },
        },
        {
            "$set": update
        },
        return_document=ReturnDocument.AFTER,
    )

    if not doc:
        raise APIError(
            "Farm not found or not owned by you.",
            404,
            "farm_not_found",
        )

    log_action(
        user_id,
        "farm.location.updated",
        "farm",
        doc["_id"],
        {
            "source": source or "gps"
        },
    )

    return serialise(doc)


# =========================================================
# CROPS
# =========================================================

def create_crop(user_id, farm_id, data):
    farm = _require_farm(
        user_id,
        farm_id,
    )

    doc = crop_document(
        str(user_id),
        farm["id"],
        data,
    )

    result = collection(CROPS).insert_one(doc)

    doc["_id"] = result.inserted_id

    log_action(
        user_id,
        "crop.created",
        "crop",
        result.inserted_id,
        {
            "farm_id": farm["id"]
        },
    )

    return serialise(doc)


def list_crops(user_id, farm_id, status=None):
    _require_farm(
        user_id,
        farm_id,
    )

    query = {
        "owner_user_id": str(user_id),
        "farm_id": str(farm_id),
        "status": {
            "$ne": DELETED_STATUS
        },
    }

    if status:
        query["status"] = status

    docs = collection(CROPS).find(
        query
    ).sort(
        "created_at",
        -1,
    )

    return serialise_many(docs)


def get_crop(user_id, farm_id, crop_id):
    _require_farm(
        user_id,
        farm_id,
    )

    doc = collection(CROPS).find_one(
        {
            "_id": clean_id(crop_id),
            "owner_user_id": str(user_id),
            "farm_id": str(farm_id),
            "status": {
                "$ne": DELETED_STATUS
            },
        }
    )

    if not doc:
        raise APIError(
            "Crop not found.",
            404,
            "crop_not_found",
        )

    return serialise(doc)


# =========================================================
# CROP ANALYSIS
# =========================================================

def crop_analysis(
    user_id,
    farm_id,
    crop_id,
):
    farm = _require_farm(
        user_id,
        farm_id,
    )

    crop = get_crop(
        user_id,
        farm_id,
        crop_id,
    )

    raw_activities = _get_farm_activities(
        user_id,
        farm_id,
    )

    raw_harvests = _get_farm_harvests(
        user_id,
        farm_id,
    )

    crop_harvests = [
        item
        for item in raw_harvests
        if (
            not crop.get("id")
            or str(item.get("crop_id")) == str(crop["id"])
        )
    ]

    yield_analysis = calculate_yield_analysis(
        crop,
        crop_harvests,
    )

    financials = calculate_crop_financials(
        crop,
        raw_activities,
        crop_harvests,
    )

    risk = calculate_crop_risk(
        crop,
        farm,
        weather_snapshot(
            _get_weather_document(farm)
        ),
        market_snapshot(
            _get_market_document(farm)
        ),
    )

    return {
        "farm": farm,
        "crop": crop,
        "yield": yield_analysis,
        "financial": financials,
        "risk": risk,
        "generated_at": now_utc().isoformat(),
    }


# =========================================================
# FARM ACTIVITIES
# =========================================================

def create_activity(user_id, farm_id, data):
    farm = _require_farm(
        user_id,
        farm_id,
    )

    doc = farm_activity_document(
        str(user_id),
        farm["id"],
        data,
    )

    result = collection(ACTIVITIES).insert_one(doc)

    doc["_id"] = result.inserted_id

    log_action(
        user_id,
        "farm.activity.created",
        "farm_activity",
        result.inserted_id,
        {
            "farm_id": farm["id"]
        },
    )

    return serialise(doc)


def list_activities(user_id, farm_id):
    farm = _require_farm(
        user_id,
        farm_id,
    )

    docs = collection(ACTIVITIES).find(
        {
            "owner_user_id": str(user_id),
            "farm_id": farm["id"],
        }
    ).sort(
        "created_at",
        -1,
    )

    return serialise_many(docs)


# =========================================================
# HARVESTS
# =========================================================

def create_harvest(user_id, farm_id, data):
    farm = _require_farm(
        user_id,
        farm_id,
    )

    doc = harvest_document(
        str(user_id),
        farm["id"],
        data,
    )

    result = collection(HARVESTS).insert_one(doc)

    doc["_id"] = result.inserted_id

    log_action(
        user_id,
        "harvest.created",
        "harvest",
        result.inserted_id,
        {
            "farm_id": farm["id"]
        },
    )

    return serialise(doc)


def list_harvests(user_id, farm_id):
    farm = _require_farm(
        user_id,
        farm_id,
    )

    docs = collection(HARVESTS).find(
        {
            "owner_user_id": str(user_id),
            "farm_id": farm["id"],
        }
    ).sort(
        "created_at",
        -1,
    )

    return serialise_many(docs)


# =========================================================
# FARM HEALTH
# =========================================================

def farm_health(
    user_id,
    farm_id,
):
    payload = _build_farm_intelligence_payload(
        user_id,
        farm_id,
    )

    result = calculate_farm_health(
        payload["farm"],
        payload["crops"],
        payload["activities"],
        payload["harvests"],
        payload["weather"],
        payload["market"],
    )

    return {
        "farm_id": str(farm_id),
        "health": result,
        "generated_at": now_utc().isoformat(),
    }


# =========================================================
# FARM INSIGHTS
# =========================================================

def farm_insights(
    user_id,
    farm_id,
):
    payload = _build_farm_intelligence_payload(
        user_id,
        farm_id,
    )

    health = calculate_farm_health(
        payload["farm"],
        payload["crops"],
        payload["activities"],
        payload["harvests"],
        payload["weather"],
        payload["market"],
    )

    crop_analysis_items = []

    for crop in payload["crops"]:
        crop_harvests = [
            harvest
            for harvest in payload["harvests"]
            if str(
                harvest.get("crop_id")
            ) == str(
                crop.get("id")
            )
        ]

        crop_risk = calculate_crop_risk(
            crop,
            payload["farm"],
            payload["weather"],
            payload["market"],
        )

        crop_yield = calculate_yield_analysis(
            crop,
            crop_harvests,
        )

        crop_financials = calculate_crop_financials(
            crop,
            payload["activities"],
            crop_harvests,
        )

        crop_analysis_items.append(
            {
                "crop": crop,
                "risk": crop_risk,
                "yield": crop_yield,
                "financial": crop_financials,
            }
        )

    recommendations = _generate_recommendations(
        payload,
        health,
        crop_analysis_items,
    )

    alerts = _generate_alerts(
        payload,
        health,
        crop_analysis_items,
    )

    insight = farm_insight_document(
        user_id=str(user_id),
        farm=payload["farm"],
        health=health,
        crops=crop_analysis_items,
        recommendations=recommendations,
        alerts=alerts,
    )

    insight["generated_at"] = now_utc()

    collection(INSIGHTS).update_one(
        {
            "owner_user_id": str(user_id),
            "farm_id": str(farm_id),
        },
        {
            "$set": insight
        },
        upsert=True,
    )

    stored = collection(INSIGHTS).find_one(
        {
            "owner_user_id": str(user_id),
            "farm_id": str(farm_id),
        }
    )

    return serialise(stored)


# =========================================================
# RECOMMENDATIONS
# =========================================================

def _generate_recommendations(
    payload,
    health,
    crop_analysis_items,
):
    recommendations = []

    farm = payload["farm"]
    weather = payload["weather"]
    market = payload["market"]

    health_score = _safe_float(
        health.get("score")
    )

    if health_score < 50:
        recommendations.append(
            recommendation_document(
                category="farm_health",
                priority="high",
                title="Improve overall farm health",
                message=(
                    "Your farm health score indicates that "
                    "one or more production factors need attention."
                ),
                action=(
                    "Review soil, water availability, crop condition "
                    "and recent farm activities before increasing production."
                ),
                confidence=0.82,
                source="shamba_intelligence",
            )
        )

    elif health_score >= 80:
        recommendations.append(
            recommendation_document(
                category="farm_health",
                priority="low",
                title="Maintain current farm performance",
                message=(
                    "Your farm is currently showing strong operational indicators."
                ),
                action=(
                    "Maintain your current practices and continue monitoring "
                    "soil, water, crops and market conditions."
                ),
                confidence=0.84,
                source="shamba_intelligence",
            )
        )

    if not farm.get("irrigation"):
        recommendations.append(
            recommendation_document(
                category="water",
                priority="medium",
                title="Strengthen water planning",
                message=(
                    "The farm does not currently indicate an irrigation system."
                ),
                action=(
                    "Track rainfall and plan water availability before "
                    "starting water-sensitive crops."
                ),
                confidence=0.78,
                source="farm_profile",
            )
        )

    rainfall = _safe_float(
        weather.get("rainfall")
        or weather.get("rainfall_mm")
    )

    if rainfall > 0:
        recommendations.append(
            recommendation_document(
                category="weather",
                priority="medium",
                title="Monitor rainfall conditions",
                message=(
                    f"Recent rainfall data indicates approximately "
                    f"{rainfall:.1f} mm."
                ),
                action=(
                    "Adjust irrigation and field activities according "
                    "to actual soil moisture and crop requirements."
                ),
                confidence=0.72,
                source="weather_snapshot",
            )
        )

    for item in crop_analysis_items:
        crop = item.get("crop", {})
        risk = item.get("risk", {})

        risk_score = _safe_float(
            risk.get("score")
        )

        crop_name = crop.get(
            "name",
            "Crop",
        )

        if risk_score >= 70:
            recommendations.append(
                recommendation_document(
                    category="crop_risk",
                    priority="high",
                    title=f"Inspect {crop_name}",
                    message=(
                        f"{crop_name} is showing elevated production risk."
                    ),
                    action=(
                        "Inspect the crop for pest, disease, water or "
                        "weather stress and record the observation."
                    ),
                    confidence=0.80,
                    source="crop_intelligence",
                    crop_id=crop.get("id"),
                )
            )

        yield_data = item.get(
            "yield",
            {},
        )

        performance = _safe_float(
            yield_data.get("performance")
        )

        if performance and performance < 70:
            recommendations.append(
                recommendation_document(
                    category="yield",
                    priority="medium",
                    title=f"Review {crop_name} productivity",
                    message=(
                        f"{crop_name} is currently performing below "
                        "its expected yield."
                    ),
                    action=(
                        "Review planting conditions, soil fertility, "
                        "water, pests, disease and farm activities."
                    ),
                    confidence=0.76,
                    source="yield_analysis",
                    crop_id=crop.get("id"),
                )
            )

    market_change = _safe_float(
        market.get("change_percent")
    )

    if market_change >= 10:
        recommendations.append(
            recommendation_document(
                category="market",
                priority="high",
                title="Market opportunity detected",
                message=(
                    "The available market data indicates a positive "
                    "price movement."
                ),
                action=(
                    "Compare current prices with nearby buyers before "
                    "committing harvested produce."
                ),
                confidence=0.70,
                source="market_snapshot",
            )
        )

    return recommendations


# =========================================================
# ALERTS
# =========================================================

def _generate_alerts(
    payload,
    health,
    crop_analysis_items,
):
    alerts = []

    farm = payload["farm"]
    weather = payload["weather"]

    health_score = _safe_float(
        health.get("score")
    )

    if health_score < 40:
        alerts.append(
            alert_document(
                category="farm_health",
                severity="critical",
                title="Farm health requires attention",
                message=(
                    "Several farm indicators are currently weak."
                ),
                action=(
                    "Review soil, water, crop and financial conditions "
                    "before making major production decisions."
                ),
                source="shamba_intelligence",
            )
        )

    elif health_score < 60:
        alerts.append(
            alert_document(
                category="farm_health",
                severity="warning",
                title="Farm health needs monitoring",
                message=(
                    "Your farm health score is below the preferred range."
                ),
                action=(
                    "Review the health recommendations and address "
                    "the weakest indicators."
                ),
                source="shamba_intelligence",
            )
        )

    if not farm.get("water_source") and not farm.get("irrigation"):
        alerts.append(
            alert_document(
                category="water",
                severity="warning",
                title="Water source not recorded",
                message=(
                    "No reliable farm water source is currently recorded."
                ),
                action=(
                    "Add your water source and plan water availability "
                    "before the next production cycle."
                ),
                source="farm_profile",
            )
        )

    temperature = _safe_float(
        weather.get("temperature")
    )

    if temperature >= 35:
        alerts.append(
            alert_document(
                category="weather",
                severity="warning",
                title="High temperature conditions",
                message=(
                    f"Recorded temperature is approximately "
                    f"{temperature:.1f}°C."
                ),
                action=(
                    "Monitor crops for heat stress and review water "
                    "availability."
                ),
                source="weather_snapshot",
            )
        )

    for item in crop_analysis_items:
        crop = item.get(
            "crop",
            {},
        )

        risk = item.get(
            "risk",
            {},
        )

        score = _safe_float(
            risk.get("score")
        )

        if score >= 80:
            alerts.append(
                alert_document(
                    category="crop_risk",
                    severity="critical",
                    title=(
                        f"{crop.get('name', 'Crop')} "
                        "has critical risk"
                    ),
                    message=(
                        "The crop intelligence engine has detected "
                        "a high-risk condition."
                    ),
                    action=(
                        "Inspect the crop immediately and record "
                        "any visible symptoms."
                    ),
                    source="crop_intelligence",
                    crop_id=crop.get("id"),
                )
            )

        elif score >= 65:
            alerts.append(
                alert_document(
                    category="crop_risk",
                    severity="warning",
                    title=(
                        f"{crop.get('name', 'Crop')} "
                        "needs monitoring"
                    ),
                    message=(
                        "The crop currently has elevated production risk."
                    ),
                    action=(
                        "Inspect the crop and monitor environmental conditions."
                    ),
                    source="crop_intelligence",
                    crop_id=crop.get("id"),
                )
            )

    return alerts


def list_recommendations(
    user_id,
    farm_id,
):
    _require_farm(
        user_id,
        farm_id,
    )

    docs = collection(RECOMMENDATIONS).find(
        {
            "owner_user_id": str(user_id),
            "farm_id": str(farm_id),
            "status": {
                "$ne": DELETED_STATUS
            },
        }
    ).sort(
        "created_at",
        -1,
    ).limit(50)

    return serialise_many(docs)


def create_recommendation(
    user_id,
    farm_id,
    data,
):
    _require_farm(
        user_id,
        farm_id,
    )

    if not isinstance(data, dict):
        raise APIError(
            "Recommendation data must be an object.",
            422,
            "invalid_recommendation",
        )

    document = recommendation_document(
        category=data.get(
            "category",
            "general",
        ),
        priority=data.get(
            "priority",
            "medium",
        ),
        title=data.get(
            "title",
            "Farm recommendation",
        ),
        message=data.get(
            "message",
            "",
        ),
        action=data.get(
            "action",
            "",
        ),
        confidence=_safe_float(
            data.get(
                "confidence",
                0.5,
            )
        ),
        source=data.get(
            "source",
            "manual",
        ),
        crop_id=data.get(
            "crop_id"
        ),
    )

    document["owner_user_id"] = str(user_id)
    document["farm_id"] = str(farm_id)
    document["created_at"] = now_utc()
    document["updated_at"] = now_utc()
    document["status"] = "active"

    result = collection(
        RECOMMENDATIONS
    ).insert_one(document)

    document["_id"] = result.inserted_id

    log_action(
        user_id,
        "farm.recommendation.created",
        "farm_recommendation",
        result.inserted_id,
        {
            "farm_id": str(farm_id)
        },
    )

    return serialise(document)


# =========================================================
# ALERTS
# =========================================================

def list_alerts(
    user_id,
    farm_id,
):
    _require_farm(
        user_id,
        farm_id,
    )

    docs = collection(ALERTS).find(
        {
            "owner_user_id": str(user_id),
            "farm_id": str(farm_id),
            "status": {
                "$ne": "resolved"
            },
        }
    ).sort(
        "created_at",
        -1,
    ).limit(50)

    return serialise_many(docs)


def create_alert(
    user_id,
    farm_id,
    data,
):
    _require_farm(
        user_id,
        farm_id,
    )

    if not isinstance(data, dict):
        raise APIError(
            "Alert data must be an object.",
            422,
            "invalid_alert",
        )

    document = alert_document(
        category=data.get(
            "category",
            "general",
        ),
        severity=data.get(
            "severity",
            "info",
        ),
        title=data.get(
            "title",
            "Farm alert",
        ),
        message=data.get(
            "message",
            "",
        ),
        action=data.get(
            "action",
            "",
        ),
        source=data.get(
            "source",
            "manual",
        ),
        crop_id=data.get(
            "crop_id"
        ),
    )

    document["owner_user_id"] = str(user_id)
    document["farm_id"] = str(farm_id)
    document["created_at"] = now_utc()
    document["updated_at"] = now_utc()
    document["status"] = "active"

    result = collection(ALERTS).insert_one(
        document
    )

    document["_id"] = result.inserted_id

    log_action(
        user_id,
        "farm.alert.created",
        "farm_alert",
        result.inserted_id,
        {
            "farm_id": str(farm_id)
        },
    )

    return serialise(document)


# =========================================================
# WEATHER
# =========================================================

def farm_weather(
    user_id,
    farm_id,
):
    farm = _require_farm(
        user_id,
        farm_id,
    )

    snapshot = weather_snapshot(
        _get_weather_document(farm)
    )

    return {
        "farm_id": str(farm_id),
        "location": {
            "latitude": farm.get("latitude"),
            "longitude": farm.get("longitude"),
            "accuracy": farm.get(
                "location_accuracy"
            ),
            "county": farm.get(
                "county"
            ),
            "town": farm.get(
                "town"
            ),
        },
        "weather": snapshot,
        "available": bool(snapshot),
        "generated_at": now_utc().isoformat(),
    }


# =========================================================
# MARKET
# =========================================================

def farm_market(
    user_id,
    farm_id,
):
    farm = _require_farm(
        user_id,
        farm_id,
    )

    snapshot = market_snapshot(
        _get_market_document(farm)
    )

    return {
        "farm_id": str(farm_id),
        "market": snapshot,
        "available": bool(snapshot),
        "generated_at": now_utc().isoformat(),
    }


# =========================================================
# AI CONTEXT
# =========================================================

def build_ai_context(
    user_id,
    farm_id=None,
):
    """
    Build structured context for RevelaAI.

    This does NOT generate the AI response.

    The RevelaAI orchestrator should consume this structure and
    decide what agricultural intelligence, weather, market or
    general reasoning is required.
    """

    user_id = str(user_id)

    if farm_id:
        payload = _build_farm_intelligence_payload(
            user_id,
            farm_id,
        )

        health = calculate_farm_health(
            payload["farm"],
            payload["crops"],
            payload["activities"],
            payload["harvests"],
            payload["weather"],
            payload["market"],
        )

        intelligence = {
            "health": health,
        }

        return build_ai_farm_context(
            farmer=payload["farmer"],
            farm=payload["farm"],
            crops=payload["crops"],
            activities=payload["activities"],
            harvests=payload["harvests"],
            weather=payload["weather"],
            market=payload["market"],
            intelligence=intelligence,
        )

    farmer = get_farmer(user_id)

    farms = list_farms(user_id)

    all_context = []

    for farm in farms:
        current_farm_id = farm.get("id")

        if not current_farm_id:
            continue

        payload = _build_farm_intelligence_payload(
            user_id,
            current_farm_id,
        )

        health = calculate_farm_health(
            payload["farm"],
            payload["crops"],
            payload["activities"],
            payload["harvests"],
            payload["weather"],
            payload["market"],
        )

        all_context.append(
            {
                "farm": payload["farm"],
                "crops": payload["crops"],
                "activities": payload["activities"],
                "harvests": payload["harvests"],
                "weather": payload["weather"],
                "market": payload["market"],
                "health": health,
            }
        )

    return {
        "domain": "shamba",
        "farmer": farmer,
        "farms": all_context,
        "farm_count": len(all_context),
        "generated_at": now_utc().isoformat(),
    }


# =========================================================
# DASHBOARD
# =========================================================

def dashboard(user_id):
    """
    Shamba Farm Command Center.

    Keeps the original dashboard contract while adding intelligence.
    """

    user_id = str(user_id)

    farms_collection = collection(FARMS)
    crops_collection = collection(CROPS)
    activities_collection = collection(ACTIVITIES)
    harvests_collection = collection(HARVESTS)

    farmer = get_farmer(user_id)

    farm_count = farms_collection.count_documents(
        {
            "owner_user_id": user_id,
            "status": {
                "$ne": DELETED_STATUS
            },
        }
    )

    crop_count = crops_collection.count_documents(
        {
            "owner_user_id": user_id,
            "status": {
                "$nin": [
                    "harvested",
                    DELETED_STATUS,
                ]
            },
        }
    )

    harvest_count = harvests_collection.count_documents(
        {
            "owner_user_id": user_id
        }
    )

    activity_count = activities_collection.count_documents(
        {
            "owner_user_id": user_id
        }
    )

    activity_cost = list(
        activities_collection.aggregate(
            [
                {
                    "$match": {
                        "owner_user_id": user_id
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total": {
                            "$sum": {
                                "$ifNull": [
                                    "$cost",
                                    0,
                                ]
                            }
                        },
                    }
                },
            ]
        )
    )

    total_cost = (
        _safe_float(
            activity_cost[0]["total"]
        )
        if activity_cost
        else 0.0
    )

    farms = list_farms(user_id)

    farm_summaries = []

    for farm in farms:
        farm_id = farm.get("id")

        if not farm_id:
            continue

        try:
            payload = _build_farm_intelligence_payload(
                user_id,
                farm_id,
            )

            health = calculate_farm_health(
                payload["farm"],
                payload["crops"],
                payload["activities"],
                payload["harvests"],
                payload["weather"],
                payload["market"],
            )

            farm_summaries.append(
                {
                    "farm": farm,
                    "health": health,
                    "weather": payload["weather"],
                    "market": payload["market"],
                    "active_crops": len(
                        [
                            crop
                            for crop in payload["crops"]
                            if crop.get("status")
                            not in {
                                "harvested",
                                "deleted",
                            }
                        ]
                    ),
                }
            )

        except Exception:
            # Dashboard intelligence must never make the
            # basic Shamba dashboard unavailable.
            continue

    overall_health_scores = [
        _safe_float(
            item.get("health", {}).get("score")
        )
        for item in farm_summaries
        if item.get("health")
    ]

    overall_health = (
        round(
            sum(overall_health_scores)
            / len(overall_health_scores),
            2,
        )
        if overall_health_scores
        else 0.0
    )

    base_dashboard = {
        "farmer": farmer,
        "metrics": {
            "farms": farm_count,
            "active_crops": crop_count,
            "harvests": harvest_count,
            "farm_activities": activity_count,
            "total_activity_cost": total_cost,
        },
    }

    intelligence_dashboard = {
        "overall_health": overall_health,
        "farm_summaries": farm_summaries,
        "generated_at": now_utc().isoformat(),
    }

    return {
        **base_dashboard,
        "intelligence": intelligence_dashboard,
    }


# =========================================================
# FARM COMMAND CENTER
# =========================================================

def farm_command_center(
    user_id,
    farm_id,
):
    """
    Rich single-farm dashboard payload for the Shamba frontend.
    """

    payload = _build_farm_intelligence_payload(
        user_id,
        farm_id,
    )

    health = calculate_farm_health(
        payload["farm"],
        payload["crops"],
        payload["activities"],
        payload["harvests"],
        payload["weather"],
        payload["market"],
    )

    crop_items = []

    for crop in payload["crops"]:
        crop_harvests = [
            harvest
            for harvest in payload["harvests"]
            if str(
                harvest.get("crop_id")
            ) == str(
                crop.get("id")
            )
        ]

        crop_items.append(
            {
                "crop": crop,
                "risk": calculate_crop_risk(
                    crop,
                    payload["farm"],
                    payload["weather"],
                    payload["market"],
                ),
                "yield": calculate_yield_analysis(
                    crop,
                    crop_harvests,
                ),
                "financial": calculate_crop_financials(
                    crop,
                    payload["activities"],
                    crop_harvests,
                ),
            }
        )

    recommendations = _generate_recommendations(
        payload,
        health,
        crop_items,
    )

    alerts = _generate_alerts(
        payload,
        health,
        crop_items,
    )

    summary = build_dashboard_summary(
        farm=payload["farm"],
        crops=payload["crops"],
        activities=payload["activities"],
        harvests=payload["harvests"],
        weather=payload["weather"],
        market=payload["market"],
        health=health,
        recommendations=recommendations,
        alerts=alerts,
    )

    return {
        "farm": payload["farm"],
        "farmer": payload["farmer"],
        "summary": summary,
        "health": health,
        "crops": crop_items,
        "weather": payload["weather"],
        "market": payload["market"],
        "recommendations": recommendations,
        "alerts": alerts,
        "generated_at": now_utc().isoformat(),
    }


# =========================================================
# INSIGHT REFRESH
# =========================================================

def refresh_farm_intelligence(
    user_id,
    farm_id,
):
    """
    Explicitly regenerate and persist the farm intelligence snapshot.
    """

    result = farm_insights(
        user_id,
        farm_id,
    )

    collection(FARMS).update_one(
        {
            "_id": clean_id(farm_id),
            "owner_user_id": str(user_id),
        },
        {
            "$set": {
                "last_ai_analysis": now_utc(),
                "updated_at": now_utc(),
            }
        },
    )

    log_action(
        user_id,
        "farm.intelligence.refreshed",
        "farm",
        farm_id,
    )

    return result
