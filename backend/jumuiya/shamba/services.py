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


# ============================================================
# COLLECTIONS
# ============================================================

FARMERS = "jumuiya_farmers"
FARMS = "jumuiya_farms"
CROPS = "jumuiya_crops"
ACTIVITIES = "jumuiya_farm_activities"
HARVESTS = "jumuiya_harvests"

INSIGHTS = "jumuiya_farm_insights"
RECOMMENDATIONS = "jumuiya_farm_recommendations"
ALERTS = "jumuiya_farm_alerts"


# ============================================================
# GENERAL HELPERS
# ============================================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def clean_id(value: Any) -> str:
    """
    Safely convert Mongo/ObjectId values into strings.
    """
    if isinstance(value, ObjectId):
        return str(value)

    if value is None:
        return ""

    return str(value)


def object_id(value: Any) -> ObjectId:
    """
    Convert a value into ObjectId or raise a clean API error.
    """
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError, ValueError):
        raise APIError(
            "Invalid resource identifier.",
            400,
            "invalid_id",
        )


def serialise(document: dict | None) -> dict | None:
    """
    Convert Mongo document into frontend-safe JSON data.
    """
    if not document:
        return None

    result = dict(document)

    if "_id" in result:
        result["id"] = clean_id(result.pop("_id"))

    for key, value in list(result.items()):
        if isinstance(value, ObjectId):
            result[key] = str(value)

    return result


def serialise_many(documents: list[dict]) -> list[dict]:
    return [
        serialise(document)
        for document in documents
        if document
    ]


def _collection(name: str):
    return collection(name)


def _owner_filter(user_id: str) -> dict:
    return {
        "owner_user_id": str(user_id),
    }


def _farm_filter(user_id: str, farm_id: str) -> dict:
    return {
        "owner_user_id": str(user_id),
        "_id": object_id(farm_id),
        "status": {"$ne": "deleted"},
    }


def _crop_filter(
    user_id: str,
    farm_id: str,
    crop_id: str | None = None,
) -> dict:
    query = {
        "owner_user_id": str(user_id),
        "farm_id": str(farm_id),
    }

    if crop_id:
        query["_id"] = object_id(crop_id)

    return query


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
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


def _status_value(document: dict, default: str = "") -> str:
    value = document.get("status", default)

    if value is None:
        return default

    return str(value).strip().lower()


# ============================================================
# FARMER PROFILE
# ============================================================

def get_farmer(user_id: str) -> dict | None:
    document = _collection(FARMERS).find_one(
        {
            "owner_user_id": str(user_id),
            "status": {"$ne": "deleted"},
        }
    )

    return serialise(document)


def create_or_update_farmer(
    user_id: str,
    payload: dict,
) -> dict:
    """
    Create or update the farmer profile.
    """

    now = now_utc()

    existing = _collection(FARMERS).find_one(
        {
            "owner_user_id": str(user_id),
            "status": {"$ne": "deleted"},
        }
    )

    if existing:
        update = {
            **payload,
            "owner_user_id": str(user_id),
            "updated_at": now,
        }

        result = _collection(FARMERS).find_one_and_update(
            {
                "_id": existing["_id"],
                "owner_user_id": str(user_id),
            },
            {
                "$set": update,
            },
            return_document=ReturnDocument.AFTER,
        )

        log_action(
            user_id,
            "shamba_farmer_updated",
            {
                "farmer_id": clean_id(existing["_id"]),
            },
        )

        return serialise(result)

    document = farmer_document(
        owner_user_id=str(user_id),
        **payload,
    )

    document.setdefault("created_at", now)
    document.setdefault("updated_at", now)
    document.setdefault("status", "active")

    result = _collection(FARMERS).insert_one(document)

    created = _collection(FARMERS).find_one(
        {"_id": result.inserted_id}
    )

    log_action(
        user_id,
        "shamba_farmer_created",
        {
            "farmer_id": clean_id(result.inserted_id),
        },
    )

    return serialise(created)


# ============================================================
# FARMS
# ============================================================

def create_farm(
    user_id: str,
    payload: dict,
) -> dict:
    document = farm_document(
        owner_user_id=str(user_id),
        **payload,
    )

    now = now_utc()

    document.setdefault("created_at", now)
    document.setdefault("updated_at", now)
    document.setdefault("status", "active")

    result = _collection(FARMS).insert_one(document)

    farm = _collection(FARMS).find_one(
        {"_id": result.inserted_id}
    )

    log_action(
        user_id,
        "shamba_farm_created",
        {
            "farm_id": clean_id(result.inserted_id),
        },
    )

    return serialise(farm)


def list_farms(user_id: str) -> list[dict]:
    farms = list(
        _collection(FARMS)
        .find(
            {
                "owner_user_id": str(user_id),
                "status": {"$ne": "deleted"},
            }
        )
        .sort("created_at", -1)
    )

    return serialise_many(farms)


def get_farm(
    user_id: str,
    farm_id: str,
) -> dict:
    farm = _collection(FARMS).find_one(
        _farm_filter(user_id, farm_id)
    )

    if not farm:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    return serialise(farm)


def update_farm(
    user_id: str,
    farm_id: str,
    payload: dict,
) -> dict:
    farm = _collection(FARMS).find_one(
        _farm_filter(user_id, farm_id)
    )

    if not farm:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    update = {
        **payload,
        "updated_at": now_utc(),
    }

    result = _collection(FARMS).find_one_and_update(
        _farm_filter(user_id, farm_id),
        {
            "$set": update,
        },
        return_document=ReturnDocument.AFTER,
    )

    log_action(
        user_id,
        "shamba_farm_updated",
        {
            "farm_id": str(farm_id),
        },
    )

    return serialise(result)


def delete_farm(
    user_id: str,
    farm_id: str,
) -> dict:
    farm = _collection(FARMS).find_one(
        _farm_filter(user_id, farm_id)
    )

    if not farm:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    result = _collection(FARMS).find_one_and_update(
        _farm_filter(user_id, farm_id),
        {
            "$set": {
                "status": "deleted",
                "updated_at": now_utc(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    log_action(
        user_id,
        "shamba_farm_deleted",
        {
            "farm_id": str(farm_id),
        },
    )

    return serialise(result)


# ============================================================
# FARM LOCATION
# ============================================================

def update_farm_location(
    user_id: str,
    farm_id: str,
    *,
    latitude: Any,
    longitude: Any,
    accuracy: Any = None,
    source: str = "browser_gps",
    county: str | None = None,
    town: str | None = None,
    location: str | None = None,
) -> dict:
    """
    Persist the farmer's best available GPS position.

    This is a coordinate fix, not a farm-boundary measurement.
    """

    lat = _safe_float(latitude)
    lng = _safe_float(longitude)

    if lat < -90 or lat > 90:
        raise APIError(
            "Latitude must be between -90 and 90.",
            422,
            "invalid_latitude",
        )

    if lng < -180 or lng > 180:
        raise APIError(
            "Longitude must be between -180 and 180.",
            422,
            "invalid_longitude",
        )

    update = {
        "latitude": lat,
        "longitude": lng,
        "location_accuracy": (
            _safe_float(accuracy)
            if accuracy is not None
            else None
        ),
        "location_source": source or "browser_gps",
        "updated_at": now_utc(),
    }

    if county is not None:
        update["county"] = county

    if town is not None:
        update["town"] = town

    if location is not None:
        update["location"] = location

    result = _collection(FARMS).find_one_and_update(
        _farm_filter(user_id, farm_id),
        {
            "$set": update,
        },
        return_document=ReturnDocument.AFTER,
    )

    if not result:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    log_action(
        user_id,
        "shamba_farm_location_updated",
        {
            "farm_id": str(farm_id),
            "location_source": source,
        },
    )

    return serialise(result)


# ============================================================
# CROPS
# ============================================================

def create_crop(
    user_id: str,
    farm_id: str,
    payload: dict,
) -> dict:
    farm = _collection(FARMS).find_one(
        _farm_filter(user_id, farm_id)
    )

    if not farm:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    document = crop_document(
        owner_user_id=str(user_id),
        farm_id=str(farm_id),
        **payload,
    )

    now = now_utc()

    document.setdefault("created_at", now)
    document.setdefault("updated_at", now)
    document.setdefault("status", "growing")

    result = _collection(CROPS).insert_one(document)

    crop = _collection(CROPS).find_one(
        {"_id": result.inserted_id}
    )

    log_action(
        user_id,
        "shamba_crop_created",
        {
            "farm_id": str(farm_id),
            "crop_id": clean_id(result.inserted_id),
        },
    )

    return serialise(crop)


def list_crops(
    user_id: str,
    farm_id: str,
    status: str | None = None,
) -> list[dict]:
    query = _crop_filter(user_id, farm_id)

    if status:
        query["status"] = status

    crops = list(
        _collection(CROPS)
        .find(query)
        .sort("created_at", -1)
    )

    return serialise_many(crops)


def get_crop(
    user_id: str,
    farm_id: str,
    crop_id: str,
) -> dict:
    crop = _collection(CROPS).find_one(
        _crop_filter(
            user_id,
            farm_id,
            crop_id,
        )
    )

    if not crop:
        raise APIError(
            "Crop not found.",
            404,
            "crop_not_found",
        )

    return serialise(crop)


# ============================================================
# FARM ACTIVITIES
# ============================================================

def create_activity(
    user_id: str,
    farm_id: str,
    payload: dict,
) -> dict:
    farm = _collection(FARMS).find_one(
        _farm_filter(user_id, farm_id)
    )

    if not farm:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    document = farm_activity_document(
        owner_user_id=str(user_id),
        farm_id=str(farm_id),
        **payload,
    )

    now = now_utc()

    document.setdefault("created_at", now)
    document.setdefault("updated_at", now)

    result = _collection(ACTIVITIES).insert_one(document)

    activity = _collection(ACTIVITIES).find_one(
        {"_id": result.inserted_id}
    )

    log_action(
        user_id,
        "shamba_activity_created",
        {
            "farm_id": str(farm_id),
            "activity_id": clean_id(result.inserted_id),
        },
    )

    return serialise(activity)


def list_activities(
    user_id: str,
    farm_id: str,
) -> list[dict]:
    activities = list(
        _collection(ACTIVITIES)
        .find(
            {
                "owner_user_id": str(user_id),
                "farm_id": str(farm_id),
            }
        )
        .sort("activity_date", -1)
    )

    return serialise_many(activities)


# ============================================================
# HARVESTS
# ============================================================

def create_harvest(
    user_id: str,
    farm_id: str,
    payload: dict,
) -> dict:
    farm = _collection(FARMS).find_one(
        _farm_filter(user_id, farm_id)
    )

    if not farm:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    document = harvest_document(
        owner_user_id=str(user_id),
        farm_id=str(farm_id),
        **payload,
    )

    now = now_utc()

    document.setdefault("created_at", now)
    document.setdefault("updated_at", now)

    # Keep sold inventory internally consistent.
    quantity = _safe_float(document.get("quantity"))
    document.setdefault("sold_quantity", 0)
    document.setdefault(
        "remaining_quantity",
        quantity,
    )

    result = _collection(HARVESTS).insert_one(document)

    harvest = _collection(HARVESTS).find_one(
        {"_id": result.inserted_id}
    )

    log_action(
        user_id,
        "shamba_harvest_created",
        {
            "farm_id": str(farm_id),
            "harvest_id": clean_id(result.inserted_id),
        },
    )

    return serialise(harvest)


def list_harvests(
    user_id: str,
    farm_id: str,
) -> list[dict]:
    harvests = list(
        _collection(HARVESTS)
        .find(
            {
                "owner_user_id": str(user_id),
                "farm_id": str(farm_id),
            }
        )
        .sort("harvest_date", -1)
    )

    return serialise_many(harvests)


# ============================================================
# WEATHER
# ============================================================

def _normalise_weather(
    farm: dict,
) -> dict:
    raw = (
        farm.get("weather_snapshot")
        or farm.get("weather")
        or farm.get("current_weather")
        or {}
    )

    if not isinstance(raw, dict):
        raw = {}

    return weather_snapshot(
        temperature=raw.get("temperature"),
        humidity=raw.get("humidity"),
        rainfall=raw.get("rainfall"),
        rainfall_probability=raw.get(
            "rainfall_probability"
        ),
        wind_speed=raw.get("wind_speed"),
        condition=raw.get("condition", ""),
        forecast_date=raw.get("forecast_date"),
    )


def _weather_available(
    weather: dict,
) -> bool:
    fields = (
        "temperature",
        "humidity",
        "rainfall",
        "rainfall_probability",
        "wind_speed",
        "condition",
    )

    return any(
        weather.get(field) not in (None, "")
        for field in fields
    )


def get_weather(
    user_id: str,
    farm_id: str,
) -> dict:
    farm = _collection(FARMS).find_one(
        _farm_filter(user_id, farm_id)
    )

    if not farm:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    weather = _normalise_weather(farm)

    return {
        "farm_id": str(farm["_id"]),
        "location": {
            "county": farm.get("county", ""),
            "town": farm.get("town", ""),
            "location": farm.get("location", ""),
            "latitude": farm.get("latitude"),
            "longitude": farm.get("longitude"),
            "accuracy": farm.get("location_accuracy"),
        },
        "available": _weather_available(weather),
        "weather": serialise(weather),
        "last_synced": farm.get("last_weather_sync"),
    }


# ============================================================
# MARKET
# ============================================================

def _normalise_market(
    farm: dict,
) -> list[dict]:
    raw = (
        farm.get("market_snapshot")
        or farm.get("market")
        or []
    )

    if isinstance(raw, dict):
        raw = [raw]

    if not isinstance(raw, list):
        return []

    results = []

    for item in raw:
        if not isinstance(item, dict):
            continue

        crop_name = str(
            item.get("crop_name")
            or item.get("crop")
            or ""
        ).strip()

        if not crop_name:
            continue

        results.append(
            market_snapshot(
                crop_name=crop_name,
                price=item.get("price", 0),
                previous_price=item.get(
                    "previous_price",
                    0,
                ),
                unit=item.get("unit", "kg"),
                market=item.get("market", ""),
                currency=item.get(
                    "currency",
                    "KES",
                ),
                demand_score=item.get(
                    "demand_score",
                    50,
                ),
            )
        )

    return results


def get_market(
    user_id: str,
    farm_id: str,
) -> dict:
    farm = _collection(FARMS).find_one(
        _farm_filter(user_id, farm_id)
    )

    if not farm:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    market = _normalise_market(farm)

    return {
        "farm_id": str(farm["_id"]),
        "market": serialise_many(market),
        "available": bool(market),
        "last_synced": farm.get("last_market_sync"),
    }


# ============================================================
# FARM HEALTH SCORING
# ============================================================

def _soil_score(
    farm: dict,
) -> int:
    explicit = farm.get("soil_score")

    if explicit is not None:
        return max(
            0,
            min(
                100,
                _safe_int(explicit, 50),
            ),
        )

    fertility = str(
        farm.get("soil_fertility", "")
    ).lower()

    if fertility in {
        "excellent",
        "very_high",
    }:
        return 90

    if fertility in {
        "good",
        "high",
    }:
        return 75

    if fertility in {
        "poor",
        "low",
    }:
        return 35

    if farm.get("soil_type"):
        return 65

    return 50


def _water_score(
    farm: dict,
) -> int:
    explicit = farm.get("water_score")

    if explicit is not None:
        return max(
            0,
            min(
                100,
                _safe_int(explicit, 50),
            ),
        )

    irrigation = bool(
        farm.get("irrigation")
        or farm.get("irrigation_available")
    )

    water_source = bool(
        farm.get("water_source")
    )

    reliability = str(
        farm.get("water_reliability", "")
    ).lower()

    if irrigation and reliability in {
        "excellent",
        "reliable",
        "high",
    }:
        return 95

    if irrigation and water_source:
        return 85

    if water_source:
        return 65

    if irrigation:
        return 70

    return 35


def _crop_health_score(
    crops: list[dict],
) -> int:
    if not crops:
        return 50

    values = []

    mapping = {
        "excellent": 95,
        "healthy": 85,
        "good": 80,
        "moderate": 60,
        "stressed": 40,
        "poor": 30,
        "critical": 15,
        "diseased": 20,
    }

    for crop in crops:
        explicit = crop.get("health_score")

        if explicit is not None:
            values.append(
                max(
                    0,
                    min(
                        100,
                        _safe_int(
                            explicit,
                            50,
                        ),
                    ),
                )
            )
            continue

        status = str(
            crop.get("health_status", "")
        ).lower()

        values.append(
            mapping.get(status, 65)
        )

    return round(sum(values) / len(values))


def _productivity_score(
    farm: dict,
    crops: list[dict],
) -> int:
    explicit = farm.get("productivity_score")

    if explicit is not None:
        return max(
            0,
            min(
                100,
                _safe_int(explicit, 50),
            ),
        )

    performances = []

    for crop in crops:
        expected = _safe_float(
            crop.get("expected_yield")
        )

        actual = _safe_float(
            crop.get("actual_yield")
        )

        if expected > 0:
            performances.append(
                max(
                    0,
                    min(
                        100,
                        (actual / expected) * 100,
                    ),
                )
            )

    if performances:
        return round(
            sum(performances)
            / len(performances)
        )

    return 50


def _financial_score(
    farm: dict,
    crops: list[dict],
) -> int:
    explicit = farm.get("financial_score")

    if explicit is not None:
        return max(
            0,
            min(
                100,
                _safe_int(explicit, 50),
            ),
        )

    total_cost = 0.0
    total_revenue = 0.0

    for crop in crops:
        total_cost += _safe_float(
            crop.get("actual_cost")
            or crop.get("estimated_cost")
        )

        total_revenue += _safe_float(
            crop.get("actual_revenue")
            or crop.get("expected_revenue")
        )

    if total_revenue <= 0:
        return 50

    margin = (
        (total_revenue - total_cost)
        / total_revenue
    ) * 100

    return max(
        0,
        min(
            100,
            round(50 + margin),
        ),
    )


def _risk_score(
    farm: dict,
    crops: list[dict],
) -> int:
    explicit = farm.get("risk_score")

    if explicit is not None:
        return max(
            0,
            min(
                100,
                _safe_int(explicit, 50),
            ),
        )

    if not crops:
        return 20

    risks = []

    for crop in crops:
        analysis = calculate_crop_risk(
            pest_risk=crop.get(
                "pest_risk",
                0,
            ),
            disease_risk=crop.get(
                "disease_risk",
                0,
            ),
            water_stress=crop.get(
                "water_stress",
                0,
            ),
            weather_risk=crop.get(
                "weather_risk",
                0,
            ),
            market_risk=crop.get(
                "market_risk",
                0,
            ),
        )

        risks.append(
            analysis["score"]
        )

    return round(
        sum(risks) / len(risks)
    )


# ============================================================
# CROP INTELLIGENCE
# ============================================================

def analyze_crop(
    user_id: str,
    farm_id: str,
    crop_id: str,
) -> dict:
    crop = _collection(CROPS).find_one(
        _crop_filter(
            user_id,
            farm_id,
            crop_id,
        )
    )

    if not crop:
        raise APIError(
            "Crop not found.",
            404,
            "crop_not_found",
        )

    risk = calculate_crop_risk(
        pest_risk=crop.get(
            "pest_risk",
            0,
        ),
        disease_risk=crop.get(
            "disease_risk",
            0,
        ),
        water_stress=crop.get(
            "water_stress",
            0,
        ),
        weather_risk=crop.get(
            "weather_risk",
            0,
        ),
        market_risk=crop.get(
            "market_risk",
            0,
        ),
    )

    yield_analysis = calculate_yield_analysis(
        expected_yield=crop.get(
            "expected_yield",
            0,
        ),
        actual_yield=crop.get(
            "actual_yield",
            0,
        ),
        area=crop.get(
            "area",
            0,
        ),
        area_unit=crop.get(
            "area_unit",
            "acres",
        ),
        yield_unit=crop.get(
            "expected_yield_unit",
            "kg",
        ),
    )

    financials = calculate_crop_financials(
        estimated_cost=crop.get(
            "estimated_cost",
            0,
        ),
        actual_cost=crop.get(
            "actual_cost",
            0,
        ),
        expected_revenue=crop.get(
            "expected_revenue",
            0,
        ),
        actual_revenue=crop.get(
            "actual_revenue",
            0,
        ),
        currency=crop.get(
            "currency",
            "KES",
        ),
    )

    return {
        "crop": serialise(crop),
        "risk": risk,
        "yield": yield_analysis,
        "financials": financials,
        "generated_at": now_utc(),
    }


# ============================================================
# FARM INSIGHTS
# ============================================================

def _generate_farm_recommendations(
    *,
    user_id: str,
    farm: dict,
    crops: list[dict],
    health: dict,
) -> list[dict]:
    farm_id = clean_id(farm["_id"])

    recommendations = []

    if health["components"]["water"] < 50:
        recommendations.append(
            recommendation_document(
                owner_user_id=str(user_id),
                farm_id=farm_id,
                title="Improve water security",
                recommendation=(
                    "Your farm currently has limited water "
                    "security. Assess reliable water sources "
                    "and consider irrigation where practical."
                ),
                category="water",
                priority="high",
                confidence=88,
                source="shamba_intelligence",
            )
        )

    if health["components"]["soil"] < 50:
        recommendations.append(
            recommendation_document(
                owner_user_id=str(user_id),
                farm_id=farm_id,
                title="Improve soil management",
                recommendation=(
                    "Your soil profile indicates that soil "
                    "management deserves attention. Consider "
                    "soil testing and an appropriate fertility plan."
                ),
                category="soil",
                priority="high",
                confidence=82,
                source="shamba_intelligence",
            )
        )

    if not crops:
        recommendations.append(
            recommendation_document(
                owner_user_id=str(user_id),
                farm_id=farm_id,
                title="Add your first crop",
                recommendation=(
                    "Add the crops currently growing on this farm "
                    "so Shamba can calculate yield, risk, financial "
                    "and seasonal intelligence."
                ),
                category="farm_setup",
                priority="normal",
                confidence=98,
                source="shamba_intelligence",
            )
        )

    for crop in crops:
        risk = calculate_crop_risk(
            pest_risk=crop.get(
                "pest_risk",
                0,
            ),
            disease_risk=crop.get(
                "disease_risk",
                0,
            ),
            water_stress=crop.get(
                "water_stress",
                0,
            ),
            weather_risk=crop.get(
                "weather_risk",
                0,
            ),
            market_risk=crop.get(
                "market_risk",
                0,
            ),
        )

        if risk["score"] >= 60:
            recommendations.append(
                recommendation_document(
                    owner_user_id=str(user_id),
                    farm_id=farm_id,
                    crop_id=clean_id(
                        crop["_id"]
                    ),
                    title=(
                        f"Review {crop.get('name', 'crop')} risk"
                    ),
                    recommendation=(
                        f"{crop.get('name', 'This crop')} "
                        f"currently has a {risk['level']} risk "
                        "profile. Review water, pest, disease, "
                        "weather and market conditions before "
                        "the next major farm decision."
                    ),
                    category="crop_risk",
                    priority=(
                        "high"
                        if risk["score"] >= 80
                        else "normal"
                    ),
                    confidence=85,
                    source="crop_intelligence",
                )
            )

        expected = _safe_float(
            crop.get("expected_yield")
        )
        actual = _safe_float(
            crop.get("actual_yield")
        )

        if expected > 0 and actual > 0:
            performance = (
                actual / expected
            ) * 100

            if performance < 70:
                recommendations.append(
                    recommendation_document(
                        owner_user_id=str(user_id),
                        farm_id=farm_id,
                        crop_id=clean_id(
                            crop["_id"]
                        ),
                        title=(
                            f"Investigate {crop.get('name', 'crop')} yield"
                        ),
                        recommendation=(
                            f"{crop.get('name', 'This crop')} "
                            f"is currently performing at "
                            f"{performance:.0f}% of expected yield. "
                            "Review planting conditions, nutrition, "
                            "water availability, pests and disease."
                        ),
                        category="yield",
                        priority="high",
                        confidence=90,
                        source="yield_analysis",
                    )
                )

    return recommendations


def _generate_farm_alerts(
    *,
    user_id: str,
    farm: dict,
    crops: list[dict],
    health: dict,
) -> list[dict]:
    farm_id = clean_id(farm["_id"])

    alerts = []

    if health["score"] < 40:
        alerts.append(
            alert_document(
                owner_user_id=str(user_id),
                farm_id=farm_id,
                title="Farm health requires attention",
                message=(
                    "The current farm health score is low. "
                    "Review soil, water, crop health, "
                    "productivity and financial indicators."
                ),
                alert_type="farm_health",
                severity="critical",
                action="Open Farm Health",
                source="shamba_intelligence",
            )
        )

    elif health["score"] < 60:
        alerts.append(
            alert_document(
                owner_user_id=str(user_id),
                farm_id=farm_id,
                title="Farm health needs monitoring",
                message=(
                    "Your farm health is moderate. "
                    "Review the recommended actions before "
                    "the situation becomes more serious."
                ),
                alert_type="farm_health",
                severity="warning",
                action="Review recommendations",
                source="shamba_intelligence",
            )
        )

    for crop in crops:
        risk = calculate_crop_risk(
            pest_risk=crop.get(
                "pest_risk",
                0,
            ),
            disease_risk=crop.get(
                "disease_risk",
                0,
            ),
            water_stress=crop.get(
                "water_stress",
                0,
            ),
            weather_risk=crop.get(
                "weather_risk",
                0,
            ),
            market_risk=crop.get(
                "market_risk",
                0,
            ),
        )

        if risk["score"] >= 80:
            alerts.append(
                alert_document(
                    owner_user_id=str(user_id),
                    farm_id=farm_id,
                    crop_id=clean_id(
                        crop["_id"]
                    ),
                    title=(
                        f"Critical crop risk: "
                        f"{crop.get('name', 'Crop')}"
                    ),
                    message=(
                        f"{crop.get('name', 'This crop')} "
                        "has reached a critical risk level. "
                        "Immediate assessment is recommended."
                    ),
                    alert_type="crop_risk",
                    severity="critical",
                    action="Analyze crop",
                    source="crop_intelligence",
                )
            )

    return alerts


def _replace_generated_recommendations(
    user_id: str,
    farm_id: str,
    documents: list[dict],
) -> None:
    """
    Replace only automatically generated recommendations.

    Manual/user-created recommendations remain untouched.
    """

    query = {
        "owner_user_id": str(user_id),
        "farm_id": str(farm_id),
        "source": {
            "$in": [
                "shamba_intelligence",
                "crop_intelligence",
                "yield_analysis",
                "farm_profile",
            ]
        },
        "status": "active",
    }

    _collection(RECOMMENDATIONS).update_many(
        query,
        {
            "$set": {
                "status": "replaced",
                "updated_at": now_utc(),
            }
        },
    )

    if documents:
        _collection(RECOMMENDATIONS).insert_many(
            documents
        )


def _replace_generated_alerts(
    user_id: str,
    farm_id: str,
    documents: list[dict],
) -> None:
    query = {
        "owner_user_id": str(user_id),
        "farm_id": str(farm_id),
        "source": {
            "$in": [
                "shamba_intelligence",
                "crop_intelligence",
            ]
        },
        "status": "active",
    }

    _collection(ALERTS).update_many(
        query,
        {
            "$set": {
                "status": "replaced",
                "updated_at": now_utc(),
            }
        },
    )

    if documents:
        _collection(ALERTS).insert_many(
            documents
        )


def generate_farm_insight(
    user_id: str,
    farm_id: str,
    *,
    persist: bool = True,
) -> dict:
    """
    Generate the current farm intelligence snapshot.

    This function is the central Shamba intelligence engine.
    """

    farm = _collection(FARMS).find_one(
        _farm_filter(user_id, farm_id)
    )

    if not farm:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    farm_id_string = clean_id(
        farm["_id"]
    )

    crops_raw = list(
        _collection(CROPS)
        .find(
            {
                "owner_user_id": str(user_id),
                "farm_id": farm_id_string,
            }
        )
    )

    activities_raw = list(
        _collection(ACTIVITIES)
        .find(
            {
                "owner_user_id": str(user_id),
                "farm_id": farm_id_string,
            }
        )
        .sort(
            "activity_date",
            -1,
        )
        .limit(50)
    )

    harvests_raw = list(
        _collection(HARVESTS)
        .find(
            {
                "owner_user_id": str(user_id),
                "farm_id": farm_id_string,
            }
        )
        .sort(
            "harvest_date",
            -1,
        )
    )

    crops = serialise_many(crops_raw)
    activities = serialise_many(
        activities_raw
    )
    harvests = serialise_many(
        harvests_raw
    )

    soil_score = _soil_score(farm)
    water_score = _water_score(farm)
    crop_score = _crop_health_score(crops)
    productivity_score = _productivity_score(
        farm,
        crops,
    )
    financial_score = _financial_score(
        farm,
        crops,
    )
    risk_score = _risk_score(
        farm,
        crops,
    )

    health = calculate_farm_health(
        soil_score=soil_score,
        water_score=water_score,
        crop_score=crop_score,
        productivity_score=productivity_score,
        financial_score=financial_score,
        risk_score=risk_score,
    )

    recommendations = _generate_farm_recommendations(
        user_id=str(user_id),
        farm=farm,
        crops=crops_raw,
        health=health,
    )

    alerts = _generate_farm_alerts(
        user_id=str(user_id),
        farm=farm,
        crops=crops_raw,
        health=health,
    )

    recommendation_text = [
        item.get(
            "recommendation",
            "",
        )
        for item in recommendations
    ]

    risk_text = [
        item.get(
            "message",
            "",
        )
        for item in alerts
    ]

    strengths = []

    if soil_score >= 70:
        strengths.append(
            "Soil conditions are currently favorable."
        )

    if water_score >= 70:
        strengths.append(
            "Water availability is relatively strong."
        )

    if crop_score >= 70:
        strengths.append(
            "Current crop health is generally good."
        )

    if productivity_score >= 70:
        strengths.append(
            "Farm productivity is performing well."
        )

    if financial_score >= 70:
        strengths.append(
            "The farm has a positive financial outlook."
        )

    summary = (
        f"Farm health is {health['score']}/100 "
        f"({health['status']}). "
        f"Productivity is {productivity_score}/100 "
        f"and current operational risk is "
        f"{risk_score}/100."
    )

    insight_document = farm_insight_document(
        owner_user_id=str(user_id),
        farm_id=farm_id_string,
        health_score=health["score"],
        productivity_score=productivity_score,
        risk_score=risk_score,
        soil_score=soil_score,
        water_score=water_score,
        crop_score=crop_score,
        financial_score=financial_score,
        summary=summary,
        strengths=strengths,
        risks=risk_text,
        recommendations=recommendation_text,
        ai_summary="",
        model="",
    )

    if persist:
        _collection(INSIGHTS).update_one(
            {
                "owner_user_id": str(user_id),
                "farm_id": farm_id_string,
                "status": "active",
            },
            {
                "$set": insight_document,
            },
            upsert=True,
        )

        _replace_generated_recommendations(
            str(user_id),
            farm_id_string,
            recommendations,
        )

        _replace_generated_alerts(
            str(user_id),
            farm_id_string,
            alerts,
        )

        _collection(FARMS).update_one(
            {
                "_id": farm["_id"],
            },
            {
                "$set": {
                    "health_score": health["score"],
                    "productivity_score": productivity_score,
                    "risk_level": health["status"],
                    "last_ai_analysis": now_utc(),
                    "updated_at": now_utc(),
                }
            },
        )

    return {
        "farm": serialise(farm),
        "health": health,
        "insight": serialise(
            insight_document
        ),
        "recommendations": serialise_many(
            recommendations
        ),
        "alerts": serialise_many(
            alerts
        ),
        "generated_at": now_utc(),
    }


# ============================================================
# STORED INSIGHT
# ============================================================

def get_latest_insight(
    user_id: str,
    farm_id: str,
) -> dict | None:
    insight = _collection(INSIGHTS).find_one(
        {
            "owner_user_id": str(user_id),
            "farm_id": str(farm_id),
            "status": "active",
        },
        sort=[
            ("updated_at", -1),
            ("generated_at", -1),
        ],
    )

    return serialise(insight)


# ============================================================
# RECOMMENDATIONS
# ============================================================

def list_recommendations(
    user_id: str,
    farm_id: str,
) -> list[dict]:
    recommendations = list(
        _collection(RECOMMENDATIONS)
        .find(
            {
                "owner_user_id": str(user_id),
                "farm_id": str(farm_id),
                "status": "active",
            }
        )
        .sort(
            [
                ("priority", -1),
                ("created_at", -1),
            ]
        )
    )

    return serialise_many(
        recommendations
    )


def create_recommendation(
    user_id: str,
    farm_id: str,
    *,
    title: str,
    recommendation: str,
    category: str = "general",
    priority: str = "normal",
    confidence: Any = 50,
    crop_id: str | None = None,
) -> dict:
    farm = _collection(FARMS).find_one(
        _farm_filter(user_id, farm_id)
    )

    if not farm:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    document = recommendation_document(
        owner_user_id=str(user_id),
        farm_id=str(farm_id),
        title=title,
        recommendation=recommendation,
        category=category,
        priority=priority,
        confidence=confidence,
        source="manual",
        crop_id=crop_id,
    )

    result = _collection(
        RECOMMENDATIONS
    ).insert_one(document)

    created_document = (
        _collection(RECOMMENDATIONS).find_one(
            {
                "_id": result.inserted_id,
            }
        )
    )

    return serialise(
        created_document
    )


# ============================================================
# ALERTS
# ============================================================

def list_alerts(
    user_id: str,
    farm_id: str,
) -> list[dict]:
    alerts = list(
        _collection(ALERTS)
        .find(
            {
                "owner_user_id": str(user_id),
                "farm_id": str(farm_id),
                "status": "active",
            }
        )
        .sort(
            [
                ("read", 1),
                ("created_at", -1),
            ]
        )
    )

    return serialise_many(alerts)


def mark_alert_read(
    user_id: str,
    farm_id: str,
    alert_id: str,
) -> dict:
    result = _collection(
        ALERTS
    ).find_one_and_update(
        {
            "owner_user_id": str(user_id),
            "farm_id": str(farm_id),
            "_id": object_id(alert_id),
        },
        {
            "$set": {
                "read": True,
                "updated_at": now_utc(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not result:
        raise APIError(
            "Alert not found.",
            404,
            "alert_not_found",
        )

    return serialise(result)


# ============================================================
# AI CONTEXT
# ============================================================

def get_ai_context(
    user_id: str,
    farm_id: str,
) -> dict:
    """
    Build structured Shamba context for RevelaAI.

    No raw LTM text is generated here.
    """

    farm = _collection(FARMS).find_one(
        _farm_filter(user_id, farm_id)
    )

    if not farm:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    farmer = _collection(FARMERS).find_one(
        {
            "owner_user_id": str(user_id),
            "status": {"$ne": "deleted"},
        }
    )

    farm_id_string = clean_id(
        farm["_id"]
    )

    crops = serialise_many(
        list(
            _collection(CROPS).find(
                {
                    "owner_user_id": str(user_id),
                    "farm_id": farm_id_string,
                }
            )
        )
    )

    activities = serialise_many(
        list(
            _collection(ACTIVITIES)
            .find(
                {
                    "owner_user_id": str(user_id),
                    "farm_id": farm_id_string,
                }
            )
            .sort(
                "activity_date",
                -1,
            )
            .limit(50)
        )
    )

    harvests = serialise_many(
        list(
            _collection(HARVESTS)
            .find(
                {
                    "owner_user_id": str(user_id),
                    "farm_id": farm_id_string,
                }
            )
            .sort(
                "harvest_date",
                -1,
            )
        )
    )

    insight = get_latest_insight(
        str(user_id),
        farm_id_string,
    )

    if not insight:
        generated = generate_farm_insight(
            str(user_id),
            farm_id_string,
            persist=True,
        )

        insight = generated.get(
            "insight"
        ) or {}

    weather = _normalise_weather(
        farm
    )

    market = _normalise_market(
        farm
    )

    farmer_context = (
        serialise(farmer)
        if farmer
        else {}
    )

    farm_context = dict(farm)
    farm_context["_id"] = farm_id_string

    return build_ai_farm_context(
        farmer=farmer_context,
        farm=farm_context,
        crops=crops,
        activities=activities,
        harvests=harvests,
        weather=weather
        if _weather_available(weather)
        else {},
        market=market,
        insights=insight or {},
    )


# ============================================================
# FARM COMMAND CENTER
# ============================================================

def farm_command_center(
    user_id: str,
    farm_id: str,
) -> dict:
    """
    Full Farm Operating System command-center payload.
    """

    farm = _collection(FARMS).find_one(
        _farm_filter(user_id, farm_id)
    )

    if not farm:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    farm_id_string = clean_id(
        farm["_id"]
    )

    crops_raw = list(
        _collection(CROPS)
        .find(
            {
                "owner_user_id": str(user_id),
                "farm_id": farm_id_string,
            }
        )
    )

    activities_raw = list(
        _collection(ACTIVITIES)
        .find(
            {
                "owner_user_id": str(user_id),
                "farm_id": farm_id_string,
            }
        )
        .sort(
            "activity_date",
            -1,
        )
        .limit(20)
    )

    harvests_raw = list(
        _collection(HARVESTS)
        .find(
            {
                "owner_user_id": str(user_id),
                "farm_id": farm_id_string,
            }
        )
        .sort(
            "harvest_date",
            -1,
        )
    )

    insight = get_latest_insight(
        str(user_id),
        farm_id_string,
    )

    if not insight:
        generated = generate_farm_insight(
            str(user_id),
            farm_id_string,
            persist=True,
        )

        insight = generated.get(
            "insight"
        ) or {}

    crops = serialise_many(
        crops_raw
    )

    activities = serialise_many(
        activities_raw
    )

    harvests = serialise_many(
        harvests_raw
    )

    summary = build_dashboard_summary(
        farm=farm,
        crops=crops,
        activities=activities,
        harvests=harvests,
        insight=insight,
    )

    weather = _normalise_weather(
        farm
    )

    market = _normalise_market(
        farm
    )

    recommendations = list_recommendations(
        str(user_id),
        farm_id_string,
    )

    alerts = list_alerts(
        str(user_id),
        farm_id_string,
    )

    return {
        "summary": summary,
        "farm": serialise(farm),
        "health": {
            "score": insight.get(
                "health_score"
            ),
            "status": insight.get(
                "health_status"
            ),
            "risk_level": insight.get(
                "risk_level"
            ),
            "components": insight.get(
                "health_components",
                {},
            ),
        },
        "weather": (
            serialise(weather)
            if _weather_available(weather)
            else None
        ),
        "market": serialise_many(
            market
        ),
        "crops": crops,
        "recent_activities": activities,
        "harvests": harvests,
        "recommendations": recommendations,
        "alerts": alerts,
        "location": {
            "latitude": farm.get(
                "latitude"
            ),
            "longitude": farm.get(
                "longitude"
            ),
            "accuracy": farm.get(
                "location_accuracy"
            ),
            "source": farm.get(
                "location_source"
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
        },
        "generated_at": now_utc(),
    }


# ============================================================
# DASHBOARD
# ============================================================

def dashboard(
    user_id: str,
) -> dict:
    """
    Main Shamba dashboard.

    If the farmer has farms, the first active farm becomes
    the primary farm while all farms remain available.
    """

    farms = list_farms(
        str(user_id)
    )

    farmer = get_farmer(
        str(user_id)
    )

    if not farms:
        return {
            "farmer": farmer,
            "farms": [],
            "primary_farm": None,
            "summary": {
                "farm_count": 0,
                "crop_count": 0,
                "active_crop_count": 0,
                "harvest_count": 0,
                "health_score": None,
            },
            "needs_setup": True,
            "generated_at": now_utc(),
        }

    primary = farms[0]

    primary_id = primary.get(
        "id"
    )

    command_center = farm_command_center(
        str(user_id),
        primary_id,
    )

    total_crops = _collection(
        CROPS
    ).count_documents(
        {
            "owner_user_id": str(user_id),
        }
    )

    active_crops = _collection(
        CROPS
    ).count_documents(
        {
            "owner_user_id": str(user_id),
            "status": {
                "$nin": [
                    "harvested",
                    "completed",
                    "cancelled",
                ]
            },
        }
    )

    harvest_count = _collection(
        HARVESTS
    ).count_documents(
        {
            "owner_user_id": str(user_id),
        }
    )

    return {
        "farmer": farmer,
        "farms": farms,
        "primary_farm": command_center,
        "summary": {
            "farm_count": len(farms),
            "crop_count": total_crops,
            "active_crop_count": active_crops,
            "harvest_count": harvest_count,
            "health_score": command_center[
                "health"
            ].get("score"),
            "health_status": command_center[
                "health"
            ].get("status"),
            "risk_level": command_center[
                "health"
            ].get("risk_level"),
        },
        "needs_setup": False,
        "generated_at": now_utc(),
    }


# ============================================================
# REFRESH INTELLIGENCE
# ============================================================

def refresh_farm_intelligence(
    user_id: str,
    farm_id: str,
) -> dict:
    """
    Explicit intelligence refresh endpoint.

    This is useful after:
      - adding a crop
      - updating soil/water data
      - syncing weather
      - syncing market prices
      - completing farm activities
    """

    result = generate_farm_insight(
        str(user_id),
        str(farm_id),
        persist=True,
    )

    log_action(
        user_id,
        "shamba_intelligence_refreshed",
        {
            "farm_id": str(farm_id),
        },
    )

    return result


# ============================================================
# FARM RECOMMENDATIONS SNAPSHOT
# ============================================================

def recommendations_snapshot(
    user_id: str,
    farm_id: str,
) -> dict:
    insight = get_latest_insight(
        str(user_id),
        str(farm_id),
    )

    if not insight:
        insight_result = generate_farm_insight(
            str(user_id),
            str(farm_id),
            persist=True,
        )

        insight = (
            insight_result.get(
                "insight"
            )
            or {}
        )

    return {
        "farm_id": str(farm_id),
        "recommendations": list_recommendations(
            str(user_id),
            str(farm_id),
        ),
        "insight": insight,
        "updated_at": now_utc(),
    }


# ============================================================
# FARM ALERT SNAPSHOT
# ============================================================

def alerts_snapshot(
    user_id: str,
    farm_id: str,
) -> dict:
    return {
        "farm_id": str(farm_id),
        "alerts": list_alerts(
            str(user_id),
            str(farm_id),
        ),
        "unread_count": _collection(
            ALERTS
        ).count_documents(
            {
                "owner_user_id": str(user_id),
                "farm_id": str(farm_id),
                "status": "active",
                "read": False,
            }
        ),
        "updated_at": now_utc(),
    }
