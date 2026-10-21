# backend/jumuiya/marketplace/services.py

from __future__ import annotations

from bson import ObjectId
from bson.errors import InvalidId

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.audit import log_action
from backend.jumuiya.marketplace.models import listing_document


# =========================================================
# OBJECT ID
# =========================================================

def clean_id(value):
    """
    Convert a MongoDB ObjectId string into ObjectId.

    If the value is not a valid ObjectId, return it as-is.
    """

    try:
        return ObjectId(value)

    except (
        InvalidId,
        TypeError,
    ):
        return value


# =========================================================
# SERIALIZATION
# =========================================================

def serialize(doc):
    """
    Convert MongoDB documents into JSON-safe dictionaries.
    """

    if not doc:
        return None

    output = dict(doc)

    if "_id" in output:
        output["id"] = str(
            output.pop("_id")
        )

    for key, value in list(
        output.items()
    ):

        if isinstance(
            value,
            ObjectId,
        ):
            output[key] = str(value)

        elif hasattr(
            value,
            "isoformat",
        ):
            output[key] = value.isoformat()

    return output


def serialize_many(docs):
    return [
        serialize(doc)
        for doc in docs
    ]


# =========================================================
# LISTINGS
# =========================================================

def listings(
    user_id=None,
    hub=None,
    category=None,
):
    """
    Return active marketplace listings.

    Marketplace is public within Jumuiya, so user_id is
    currently optional.

    Future filtering can include:

        county
        town
        seller
        price range
        distance
        search
    """

    query = {
        "status": "active"
    }

    if hub:
        query["hub"] = str(
            hub
        ).strip().lower()

    if category:
        query["category"] = str(
            category
        ).strip().lower()

    normalized_hub = str(hub or "").strip().lower()
    reviewed_owner_by_id = {}

    # Filter legacy/unreviewed Shamba listings even when the client requests
    # the all-hubs marketplace without passing ?hub=shamba.
    if normalized_hub in {"", "shamba"}:
        reviewed_farms = list(collection("jumuiya_farms").find(
            {
                "legal_verification_status": "verified",
                "status": {"$ne": "deleted"},
            },
            {"_id": 1, "owner_user_id": 1},
        ))
        reviewed_owner_by_id = {
            str(item.get("_id")): str(item.get("owner_user_id") or "")
            for item in reviewed_farms
        }
        reviewed_ids = list(reviewed_owner_by_id.keys())

        if normalized_hub == "shamba":
            if not reviewed_ids:
                return []
            query["farm_id"] = {"$in": reviewed_ids}
        elif reviewed_ids:
            query["$or"] = [
                {"hub": {"$ne": "shamba"}},
                {"hub": "shamba", "farm_id": {"$in": reviewed_ids}},
            ]
        else:
            query["hub"] = {"$ne": "shamba"}

    documents = (
        collection(
            "jumuiya_marketplace_listings"
        )
        .find(query)
        .sort(
            "created_at",
            -1,
        )
    )

    if normalized_hub == "shamba":
        # For Shamba-only requests, seller identity must match the reviewed farm owner.
        documents = [
            item for item in documents
            if reviewed_owner_by_id.get(str(item.get("farm_id"))) == str(item.get("seller_user_id") or "")
        ]
    elif not normalized_hub:
        # The general marketplace includes all hubs, but only reviewed and correctly
        # owner-linked Shamba listings are allowed into that result set.
        documents = [
            item for item in documents
            if str(item.get("hub") or "community").strip().lower() != "shamba"
            or reviewed_owner_by_id.get(str(item.get("farm_id"))) == str(item.get("seller_user_id") or "")
        ]

    return serialize_many(
        documents
    )


# =========================================================
# CREATE LISTING
# =========================================================

def create_listing(
    user_id,
    data,
):
    """
    Create a marketplace listing for the authenticated user.
    """

    if not user_id:
        raise APIError(
            "Authentication is required.",
            401,
            "authentication_required",
        )

    resolved_data = dict(data)
    if str(resolved_data.get("hub", "community")).strip().lower() == "shamba":
        # Seller status and individual farm-rights review are separate gates.
        farmer = collection("jumuiya_farmers").find_one({
            "$or": [
                {"owner_user_id": str(user_id)},
                {"user_id": str(user_id)},
            ],
            "verification_status": {"$in": ["approved", "verified"]},
            "status": {"$ne": "deleted"},
        })
        if not farmer:
            raise APIError(
                "Shamba listings require an administrator-verified farmer profile.",
                403,
                "farmer_verification_required",
            )

        requested_farm_id = str(resolved_data.get("farm_id") or "").strip()
        farm_query = {
            "owner_user_id": str(user_id),
            "legal_verification_status": "verified",
            "status": {"$ne": "deleted"},
        }
        if requested_farm_id:
            try:
                requested_oid = ObjectId(requested_farm_id)
                farm_query["_id"] = requested_oid
            except (InvalidId, TypeError, ValueError):
                raise APIError("Invalid farm identifier for this Shamba listing.", 422, "invalid_farm_id")
            farm = collection("jumuiya_farms").find_one(farm_query)
        else:
            farm = collection("jumuiya_farms").find_one(farm_query, sort=[("created_at", -1)])
        if not farm:
            raise APIError(
                "Shamba listings require a farm you own or are authorized to manage whose rights have been reviewed by RevelaCode.",
                403,
                "farm_verification_required",
            )
        resolved_data["farm_id"] = str(farm["_id"])

    try:
        document = listing_document(
            user_id,
            resolved_data,
        )

    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "validation_error",
        )

    result = collection(
        "jumuiya_marketplace_listings"
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    log_action(
        user_id,
        "marketplace.listing.created",
        "listing",
        result.inserted_id,
    )

    return serialize(
        document
    )


# =========================================================
# DELETE LISTING
# =========================================================

def delete_listing(
    user_id,
    listing_id,
):
    """
    Soft-delete a marketplace listing.

    We deliberately do not physically delete the document.
    This preserves the audit/history trail.
    """

    listing_object_id = clean_id(
        listing_id
    )

    result = collection(
        "jumuiya_marketplace_listings"
    ).update_one(
        {
            "_id": listing_object_id,
            "seller_user_id": str(
                user_id
            ),
            "status": "active",
        },
        {
            "$set": {
                "status": "deleted",
            }
        },
    )

    if result.modified_count != 1:
        raise APIError(
            "Listing not found or not owned by you.",
            404,
            "listing_not_found",
        )

    log_action(
        user_id,
        "marketplace.listing.deleted",
        "listing",
        listing_id,
    )

    return {
        "deleted": True,
        "id": str(
            listing_id
        ),
    }