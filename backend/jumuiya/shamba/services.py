from __future__ import annotations

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


# =========================================================
# HELPERS
# =========================================================

def clean_id(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return value


def serialise(doc):
    if not doc:
        return None

    out = dict(doc)

    if "_id" in out:
        out["id"] = str(out.pop("_id"))

    for key, value in list(out.items()):
        if isinstance(value, ObjectId):
            out[key] = str(value)
        elif hasattr(value, "isoformat"):
            out[key] = value.isoformat()

    return out


def serialise_many(docs):
    return [serialise(doc) for doc in docs]


# =========================================================
# FARMER PROFILE
# =========================================================

def get_farmer(user_id):
    doc = collection("jumuiya_farmers").find_one(
        {"user_id": str(user_id)}
    )

    return serialise(doc)


def create_or_update_farmer(user_id, data):
    user_id = str(user_id)

    collection_ref = collection("jumuiya_farmers")

    existing = collection_ref.find_one(
        {"user_id": user_id}
    )

    if existing:
        from datetime import datetime, timezone

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
            key: data.get(key, existing.get(key, ""))
            for key in allowed
        }

        update["updated_at"] = datetime.now(
            timezone.utc
        )

        doc = collection_ref.find_one_and_update(
            {"_id": existing["_id"]},
            {"$set": update},
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
    doc = farm_document(
        user_id,
        data,
    )

    result = collection(
        "jumuiya_farms"
    ).insert_one(doc)

    doc["_id"] = result.inserted_id

    log_action(
        user_id,
        "farm.created",
        "farm",
        result.inserted_id,
    )

    return serialise(doc)


def list_farms(user_id):
    docs = collection(
        "jumuiya_farms"
    ).find(
        {
            "owner_user_id": str(user_id),
            "status": {"$ne": "deleted"},
        }
    ).sort(
        "created_at",
        -1,
    )

    return serialise_many(docs)


def get_farm(user_id, farm_id):
    doc = collection(
        "jumuiya_farms"
    ).find_one(
        {
            "_id": clean_id(farm_id),
            "owner_user_id": str(user_id),
            "status": {"$ne": "deleted"},
        }
    )

    if not doc:
        raise APIError(
            "Farm not found.",
            404,
            "farm_not_found",
        )

    return serialise(doc)


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

    from datetime import datetime, timezone

    update["updated_at"] = datetime.now(
        timezone.utc
    )

    doc = collection(
        "jumuiya_farms"
    ).find_one_and_update(
        {
            "_id": clean_id(farm_id),
            "owner_user_id": str(user_id),
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
    result = collection(
        "jumuiya_farms"
    ).update_one(
        {
            "_id": clean_id(farm_id),
            "owner_user_id": str(user_id),
        },
        {
            "$set": {
                "status": "deleted"
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
# CROPS
# =========================================================

def create_crop(user_id, farm_id, data):
    farm = get_farm(
        user_id,
        farm_id,
    )

    doc = crop_document(
        user_id,
        farm["id"],
        data,
    )

    result = collection(
        "jumuiya_crops"
    ).insert_one(doc)

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
    get_farm(
        user_id,
        farm_id,
    )

    query = {
        "owner_user_id": str(user_id),
        "farm_id": str(farm_id),
    }

    if status:
        query["status"] = status

    docs = collection(
        "jumuiya_crops"
    ).find(query).sort(
        "created_at",
        -1,
    )

    return serialise_many(docs)


# =========================================================
# FARM ACTIVITIES
# =========================================================

def create_activity(user_id, farm_id, data):
    farm = get_farm(
        user_id,
        farm_id,
    )

    doc = farm_activity_document(
        user_id,
        farm["id"],
        data,
    )

    result = collection(
        "jumuiya_farm_activities"
    ).insert_one(doc)

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
    farm = get_farm(
        user_id,
        farm_id,
    )

    docs = collection(
        "jumuiya_farm_activities"
    ).find(
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
    farm = get_farm(
        user_id,
        farm_id,
    )

    doc = harvest_document(
        user_id,
        farm["id"],
        data,
    )

    result = collection(
        "jumuiya_harvests"
    ).insert_one(doc)

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
    farm = get_farm(
        user_id,
        farm_id,
    )

    docs = collection(
        "jumuiya_harvests"
    ).find(
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
# SHAMBA DASHBOARD
# =========================================================

def dashboard(user_id):
    user_id = str(user_id)

    farms = collection(
        "jumuiya_farms"
    )

    crops = collection(
        "jumuiya_crops"
    )

    activities = collection(
        "jumuiya_farm_activities"
    )

    harvests = collection(
        "jumuiya_harvests"
    )

    farmer = get_farmer(user_id)

    farm_count = farms.count_documents(
        {
            "owner_user_id": user_id,
            "status": {"$ne": "deleted"},
        }
    )

    crop_count = crops.count_documents(
        {
            "owner_user_id": user_id,
            "status": {
                "$nin": [
                    "harvested",
                    "deleted",
                ]
            },
        }
    )

    harvest_count = harvests.count_documents(
        {
            "owner_user_id": user_id
        }
    )

    activity_count = activities.count_documents(
        {
            "owner_user_id": user_id
        }
    )

    activity_cost = list(
        activities.aggregate(
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
                            "$sum": "$cost"
                        },
                    }
                },
            ]
        )
    )

    total_cost = (
        float(activity_cost[0]["total"])
        if activity_cost
        else 0.0
    )

    return {
        "farmer": farmer,
        "metrics": {
            "farms": farm_count,
            "active_crops": crop_count,
            "harvests": harvest_count,
            "farm_activities": activity_count,
            "total_activity_cost": total_cost,
        },
    }
