from __future__ import annotations

from datetime import datetime, timezone


def now_utc():
    return datetime.now(timezone.utc)


def farmer_document(user_id, data):
    now = now_utc()

    return {
        "user_id": str(user_id),
        "farm_name": data.get("farm_name", ""),
        "farmer_name": data["farmer_name"],
        "phone": data.get("phone", ""),
        "county": data.get("county", ""),
        "town": data.get("town", ""),
        "location": data.get("location", ""),
        "farm_size": float(data.get("farm_size", 0)),
        "farm_size_unit": data.get("farm_size_unit", "acres"),
        "farming_type": data.get("farming_type", "mixed"),
        "description": data.get("description", ""),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }


def farm_document(user_id, data):
    now = now_utc()

    return {
        "owner_user_id": str(user_id),
        "name": data["name"],
        "county": data.get("county", ""),
        "town": data.get("town", ""),
        "location": data.get("location", ""),
        "size": float(data.get("size", 0)),
        "size_unit": data.get("size_unit", "acres"),
        "soil_type": data.get("soil_type", ""),
        "irrigation": data.get("irrigation", False),
        "description": data.get("description", ""),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }


def crop_document(user_id, farm_id, data):
    now = now_utc()

    return {
        "owner_user_id": str(user_id),
        "farm_id": str(farm_id),
        "name": data["name"],
        "variety": data.get("variety", ""),
        "season": data.get("season", ""),
        "area": float(data.get("area", 0)),
        "area_unit": data.get("area_unit", "acres"),
        "planting_date": data.get("planting_date"),
        "expected_harvest_date": data.get(
            "expected_harvest_date"
        ),
        "status": data.get("status", "growing"),
        "notes": data.get("notes", ""),
        "created_at": now,
        "updated_at": now,
    }


def farm_activity_document(user_id, farm_id, data):
    now = now_utc()

    return {
        "owner_user_id": str(user_id),
        "farm_id": str(farm_id),
        "type": data["type"],
        "description": data.get("description", ""),
        "cost": float(data.get("cost", 0)),
        "currency": data.get("currency", "KES"),
        "activity_date": data.get("activity_date"),
        "created_at": now,
    }


def harvest_document(user_id, farm_id, data):
    now = now_utc()

    return {
        "owner_user_id": str(user_id),
        "farm_id": str(farm_id),
        "crop_id": data.get("crop_id"),
        "crop_name": data["crop_name"],
        "quantity": float(data["quantity"]),
        "unit": data.get("unit", "kg"),
        "quality": data.get("quality", ""),
        "harvest_date": data.get("harvest_date"),
        "market_status": "available",
        "notes": data.get("notes", ""),
        "created_at": now,
        "updated_at": now,
    }