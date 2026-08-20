# backend/jumuiya/identity/services.py

from __future__ import annotations

from datetime import datetime, timezone

from pymongo import ReturnDocument

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.identity.models import profile_document


# =========================================================
# TIME
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


# =========================================================
# SERIALIZATION
# =========================================================

def _ser(doc):
    """
    Convert MongoDB profile document into a JSON-safe object.
    """

    if not doc:
        return None

    out = dict(doc)

    if "_id" in out:
        out["id"] = str(
            out.pop("_id")
        )

    elif "id" in out:
        out["id"] = str(
            out["id"]
        )

    for key, value in list(
        out.items()
    ):
        if hasattr(
            value,
            "isoformat",
        ):
            out[key] = value.isoformat()

    return out


# =========================================================
# GET / CREATE PROFILE
# =========================================================

def profile(user):
    """
    Return the Jumuiya profile for an authenticated
    RevelaCode user.

    If the user does not yet have a Jumuiya profile,
    create one automatically.
    """

    if not isinstance(
        user,
        dict,
    ):
        raise APIError(
            "Invalid user identity.",
            401,
            "invalid_identity",
        )

    user_id = (
        user.get("id")
        or user.get("_id")
        or user.get("user_id")
    )

    if user_id is None:
        raise APIError(
            "Authenticated user has no usable ID.",
            401,
            "invalid_identity",
        )

    user_id = str(
        user_id
    )

    collection_profiles = collection(
        "jumuiya_profiles"
    )

    existing = collection_profiles.find_one(
        {
            "user_id": user_id
        }
    )

    if existing:
        return _ser(
            existing
        )

    document = profile_document(
        {
            **user,
            "id": user_id,
        }
    )

    result = collection_profiles.insert_one(
        document
    )

    document["_id"] = result.inserted_id

    log_action(
        user_id,
        "identity.profile.created",
        "profile",
        result.inserted_id,
    )

    return _ser(
        document
    )


# =========================================================
# UPDATE PROFILE
# =========================================================

def update_profile(
    user_id,
    data,
):
    """
    Update the authenticated user's Jumuiya profile.

    Only profile-owned fields can be changed here.

    Authentication fields such as:
        user_id
        roles
        verified
        email
        authentication credentials

    are NOT editable through this endpoint.
    """

    if user_id is None:
        raise APIError(
            "Authenticated user ID is required.",
            401,
            "invalid_identity",
        )

    if not isinstance(
        data,
        dict,
    ):
        raise APIError(
            "Profile data must be a JSON object.",
            400,
            "invalid_profile_data",
        )

    user_id = str(
        user_id
    )

    allowed = {
        "full_name": 160,
        "bio": 1000,
        "avatar_url": 500,
        "county": 100,
        "town": 100,
    }

    update = {}

    for key, max_length in allowed.items():

        if key not in data:
            continue

        value = data[key]

        if not isinstance(
            value,
            str,
        ):
            raise APIError(
                f"{key} must be text.",
                422,
                "validation_error",
            )

        value = value.strip()

        if len(value) > max_length:
            raise APIError(
                f"{key} is too long.",
                422,
                "validation_error",
            )

        update[key] = value

    if not update:
        raise APIError(
            "No valid profile fields were supplied.",
            422,
            "validation_error",
        )

    update["updated_at"] = now_utc()

    profiles = collection(
        "jumuiya_profiles"
    )

    document = profiles.find_one_and_update(
        {
            "user_id": user_id
        },
        {
            "$set": update
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    log_action(
        user_id,
        "identity.profile.updated",
        "profile",
        document.get("_id"),
        metadata={
            "fields": list(
                update.keys()
            )
        },
    )

    return _ser(
        document
    )