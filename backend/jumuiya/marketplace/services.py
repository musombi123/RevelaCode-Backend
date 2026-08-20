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

    try:
        document = listing_document(
            user_id,
            data,
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