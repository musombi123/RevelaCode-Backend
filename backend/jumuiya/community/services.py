# backend/jumuiya/community/services.py

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError

from backend.jumuiya.community.models import (
    COMMUNITY_HUBS,
    POST_TYPES,
    post_document,
)

from backend.jumuiya.notifications import (
    services as notification_services,
)


# =========================================================
# COLLECTIONS
# =========================================================

POSTS = "jumuiya_community_posts"
COMMENTS = "jumuiya_community_comments"
REACTIONS = "jumuiya_community_reactions"
PROFILES = "jumuiya_profiles"

BUSINESSES = "jumuiya_businesses"
FARMERS = "jumuiya_farmers"
FARMS = "jumuiya_farms"
EDUCATION_PROFILES = "jumuiya_education_profiles"
SCHOOLS = "jumuiya_schools"
MARKETPLACE_LISTINGS = "jumuiya_marketplace_listings"


# =========================================================
# LIMITS
# =========================================================

DEFAULT_FEED_LIMIT = 30
MAX_FEED_LIMIT = 100

DEFAULT_COMMENT_LIMIT = 100
MAX_COMMENT_LIMIT = 200

DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 50

MAX_SEARCH_LENGTH = 100

DEFAULT_AUTHOR_NAME = "Community member"


# =========================================================
# TIME
# =========================================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# =========================================================
# IDS / USER
# =========================================================

def normalize_user_id(user_id: Any) -> str:
    """
    Normalize the authenticated RevelaCode/Jumuiya user ID.
    """

    if user_id is None:
        raise APIError(
            "Authenticated user is required.",
            401,
            "authentication_required",
        )

    value = str(user_id).strip()

    if not value:
        raise APIError(
            "Authenticated user is required.",
            401,
            "authentication_required",
        )

    return value


def cid(value: Any) -> ObjectId:
    """
    Convert an incoming Mongo resource ID to ObjectId.
    """

    try:
        return ObjectId(str(value))
    except (
        InvalidId,
        TypeError,
        ValueError,
    ):
        raise APIError(
            "Invalid resource ID.",
            400,
            "invalid_id",
        )


# =========================================================
# SERIALIZATION
# =========================================================

def _serialize_value(value: Any) -> Any:
    """
    Recursively serialize Mongo/BSON values.
    """

    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): _serialize_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            _serialize_value(item)
            for item in value
        ]

    return value


def serialize(
    doc: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not doc:
        return None

    output = dict(doc)

    if "_id" in output:
        output["id"] = str(
            output.pop("_id")
        )

    return _serialize_value(output)


def serialize_many(
    docs: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    output = []

    for doc in docs:
        serialized = serialize(doc)

        if serialized is not None:
            output.append(serialized)

    return output


# =========================================================
# NORMALIZATION
# =========================================================

def _normalize_limit(
    value: Any,
    default: int,
    maximum: int,
) -> int:
    try:
        value = int(value)
    except (
        TypeError,
        ValueError,
    ):
        value = default

    return max(
        1,
        min(value, maximum),
    )


def _normalize_text(
    value: Any,
    field: str,
    *,
    required: bool = False,
    max_length: int | None = None,
) -> str | None:

    if value is None:
        if required:
            raise APIError(
                f"{field} is required.",
                422,
                "validation_error",
            )

        return None

    if not isinstance(value, str):
        raise APIError(
            f"{field} must be text.",
            422,
            "validation_error",
        )

    value = value.strip()

    if required and not value:
        raise APIError(
            f"{field} is required.",
            422,
            "validation_error",
        )

    if (
        max_length is not None
        and len(value) > max_length
    ):
        raise APIError(
            f"{field} is too long.",
            422,
            "validation_error",
        )

    return value


def _normalize_search(
    value: Any,
) -> str | None:

    if value is None:
        return None

    search = str(value).strip()

    if not search:
        return None

    return search[:MAX_SEARCH_LENGTH]


def _normalize_hub(
    value: Any,
) -> str:

    hub = _normalize_text(
        value,
        "hub",
        required=True,
        max_length=30,
    )

    if hub is None:
        raise APIError(
            "hub is required.",
            422,
            "validation_error",
        )

    hub = hub.lower()

    if hub not in COMMUNITY_HUBS:
        raise APIError(
            "Invalid community hub.",
            422,
            "invalid_hub",
        )

    return hub


def _normalize_post_type(
    value: Any,
) -> str:

    post_type = _normalize_text(
        value,
        "type",
        required=True,
        max_length=40,
    )

    if post_type is None:
        raise APIError(
            "type is required.",
            422,
            "validation_error",
        )

    post_type = post_type.lower()

    if post_type not in POST_TYPES:
        raise APIError(
            "Invalid community post type.",
            422,
            "invalid_post_type",
        )

    return post_type


# =========================================================
# HUB AUTHORIZATION
# =========================================================

def _ensure_hub_access(
    user_id: str,
    hub: str,
) -> None:
    """
    Ensure a user is actually entitled to publish into a
    hub-specific Community stream.

    Community itself is available to every authenticated user.

    Hub-specific streams require the matching profile:

        biashara -> business
        shamba   -> farmer/farm
        elimu    -> education profile

    This prevents false hub identity.
    """

    if hub == "community":
        return

    if hub == "biashara":
        business = collection(
            BUSINESSES
        ).find_one(
            {
                "owner_user_id": user_id,
                "status": "active",
            },
            {
                "_id": 1,
            },
        )

        if not business:
            raise APIError(
                "You need an active Biashara business profile "
                "to publish in the Biashara community.",
                403,
                "hub_access_denied",
            )

        return

    if hub == "shamba":
        farmer = collection(
            FARMERS
        ).find_one(
            {
                "user_id": user_id,
                "status": "active",
            },
            {
                "_id": 1,
            },
        )

        farm = collection(
            FARMS
        ).find_one(
            {
                "owner_user_id": user_id,
                "status": "active",
            },
            {
                "_id": 1,
            },
        )

        if not farmer and not farm:
            raise APIError(
                "You need an active Shamba farmer or farm profile "
                "to publish in the Shamba community.",
                403,
                "hub_access_denied",
            )

        return

    if hub == "elimu":
        education_profile = collection(
            EDUCATION_PROFILES
        ).find_one(
            {
                "user_id": user_id,
                "status": "active",
            },
            {
                "_id": 1,
            },
        )

        school = collection(
            SCHOOLS
        ).find_one(
            {
                "owner_user_id": user_id,
                "status": "active",
            },
            {
                "_id": 1,
            },
        )

        if not education_profile and not school:
            raise APIError(
                "You need an active Elimu profile or school account "
                "to publish in the Elimu community.",
                403,
                "hub_access_denied",
            )

        return

    raise APIError(
        "Invalid community hub.",
        422,
        "invalid_hub",
    )


# =========================================================
# SOURCE ENTITY AUTHORIZATION
# =========================================================

def _find_source_entity(
    source_hub: str,
    entity_type: str,
    entity_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    """
    Resolve an ecosystem source entity and verify ownership.

    Supported source mappings:

        biashara
            business
            product

        shamba
            farmer
            farm
            crop
            harvest

        elimu
            education_profile
            school
            lesson
            assignment
            cbc_project

        community
            community_post

        marketplace
            listing
    """

    if not entity_id:
        return None

    # -----------------------------------------------------
    # BIASHARA
    # -----------------------------------------------------

    if source_hub == "biashara":

        if entity_type == "business":
            return collection(
                BUSINESSES
            ).find_one(
                {
                    "_id": cid(entity_id),
                    "owner_user_id": user_id,
                }
            )

        if entity_type == "product":
            product = collection(
                "jumuiya_products"
            ).find_one(
                {
                    "_id": cid(entity_id),
                }
            )

            if not product:
                return None

            business = collection(
                BUSINESSES
            ).find_one(
                {
                    "_id": cid(
                        product.get(
                            "business_id"
                        )
                    ),
                    "owner_user_id": user_id,
                },
                {
                    "_id": 1,
                },
            )

            return product if business else None

    # -----------------------------------------------------
    # SHAMBA
    # -----------------------------------------------------

    if source_hub == "shamba":

        if entity_type == "farmer":
            return collection(
                FARMERS
            ).find_one(
                {
                    "_id": cid(entity_id),
                    "user_id": user_id,
                }
            )

        if entity_type == "farm":
            return collection(
                FARMS
            ).find_one(
                {
                    "_id": cid(entity_id),
                    "owner_user_id": user_id,
                }
            )

        if entity_type == "crop":
            return collection(
                "jumuiya_crops"
            ).find_one(
                {
                    "_id": cid(entity_id),
                    "owner_user_id": user_id,
                }
            )

        if entity_type == "harvest":
            return collection(
                "jumuiya_harvests"
            ).find_one(
                {
                    "_id": cid(entity_id),
                    "owner_user_id": user_id,
                }
            )

    # -----------------------------------------------------
    # ELIMU
    # -----------------------------------------------------

    if source_hub == "elimu":

        if entity_type == "education_profile":
            return collection(
                EDUCATION_PROFILES
            ).find_one(
                {
                    "_id": cid(entity_id),
                    "user_id": user_id,
                }
            )

        if entity_type == "school":
            return collection(
                SCHOOLS
            ).find_one(
                {
                    "_id": cid(entity_id),
                    "owner_user_id": user_id,
                }
            )

        if entity_type == "lesson":
            return collection(
                "jumuiya_lessons"
            ).find_one(
                {
                    "_id": cid(entity_id),
                    "author_user_id": user_id,
                }
            )

        if entity_type == "assignment":
            return collection(
                "jumuiya_assignments"
            ).find_one(
                {
                    "_id": cid(entity_id),
                    "teacher_user_id": user_id,
                }
            )

        if entity_type == "cbc_project":
            return collection(
                "jumuiya_cbc_projects"
            ).find_one(
                {
                    "_id": cid(entity_id),
                    "teacher_user_id": user_id,
                }
            )

    # -----------------------------------------------------
    # COMMUNITY
    # -----------------------------------------------------

    if source_hub == "community":

        if entity_type == "community_post":
            return collection(
                POSTS
            ).find_one(
                {
                    "_id": cid(entity_id),
                    "author_user_id": user_id,
                }
            )

    # -----------------------------------------------------
    # MARKETPLACE
    # -----------------------------------------------------

    if source_hub == "marketplace":

        if entity_type == "listing":
            return collection(
                MARKETPLACE_LISTINGS
            ).find_one(
                {
                    "_id": cid(entity_id),
                    "seller_user_id": user_id,
                }
            )

    return None


def _validate_source(
    user_id: str,
    source: Any,
) -> dict[str, Any]:

    if source is None:
        return {}

    if not isinstance(source, dict):
        raise APIError(
            "source must be an object.",
            422,
            "validation_error",
        )

    source_hub = str(
        source.get(
            "hub",
            "",
        )
        or ""
    ).strip().lower()

    entity_type = str(
        source.get(
            "entity_type",
            "",
        )
        or ""
    ).strip().lower()

    entity_id = str(
        source.get(
            "entity_id",
            "",
        )
        or ""
    ).strip()

    if not (
        source_hub
        or entity_type
        or entity_id
    ):
        return {}

    if source_hub not in {
        "community",
        "biashara",
        "shamba",
        "elimu",
        "marketplace",
    }:
        raise APIError(
            "Invalid source hub.",
            422,
            "invalid_source",
        )

    if not entity_type:
        raise APIError(
            "source.entity_type is required.",
            422,
            "invalid_source",
        )

    if not entity_id:
        raise APIError(
            "source.entity_id is required.",
            422,
            "invalid_source",
        )

    try:
        entity = _find_source_entity(
            source_hub,
            entity_type,
            entity_id,
            user_id,
        )
    except APIError:
        raise
    except (
        InvalidId,
        TypeError,
        ValueError,
    ):
        raise APIError(
            "Invalid source entity ID.",
            422,
            "invalid_source",
        )

    if not entity:
        raise APIError(
            "The referenced source entity was not found "
            "or does not belong to you.",
            403,
            "source_access_denied",
        )

    return {
        "hub": source_hub,
        "entity_type": entity_type,
        "entity_id": entity_id,
    }


# =========================================================
# CTA / ACTION VALIDATION
# =========================================================

def _validate_action(
    action: Any,
) -> dict[str, Any]:

    if action is None:
        return {}

    if not isinstance(action, dict):
        raise APIError(
            "action must be an object.",
            422,
            "validation_error",
        )

    action_type = str(
        action.get(
            "type",
            "",
        )
        or ""
    ).strip().lower()

    action_label = str(
        action.get(
            "label",
            "",
        )
        or ""
    ).strip()

    action_target = str(
        action.get(
            "target",
            "",
        )
        or ""
    ).strip()

    if not (
        action_type
        or action_label
        or action_target
    ):
        return {}

    if len(action_type) > 50:
        raise APIError(
            "action.type is too long.",
            422,
            "validation_error",
        )

    if len(action_label) > 80:
        raise APIError(
            "action.label is too long.",
            422,
            "validation_error",
        )

    if len(action_target) > 300:
        raise APIError(
            "action.target is too long.",
            422,
            "validation_error",
        )

    return {
        "type": action_type,
        "label": action_label,
        "target": action_target,
    }


# =========================================================
# PUBLIC AUTHOR PROFILE
# =========================================================

def _fallback_author(
    user_id: str,
) -> dict[str, Any]:

    return {
        "id": user_id,
        "name": DEFAULT_AUTHOR_NAME,
        "avatar_url": None,
        "bio": None,
        "county": None,
        "town": None,
    }


def _load_authors(
    user_ids: Iterable[str],
) -> dict[str, dict[str, Any]]:

    normalized_ids = {
        str(user_id).strip()
        for user_id in user_ids
        if (
            user_id is not None
            and str(user_id).strip()
        )
    }

    if not normalized_ids:
        return {}

    profiles = list(
        collection(PROFILES).find(
            {
                "user_id": {
                    "$in": list(
                        normalized_ids
                    )
                }
            },
            {
                "_id": 0,
                "user_id": 1,
                "full_name": 1,
                "avatar_url": 1,
                "bio": 1,
                "county": 1,
                "town": 1,
            },
        )
    )

    authors = {
        user_id: _fallback_author(
            user_id
        )
        for user_id in normalized_ids
    }

    for profile in profiles:

        user_id = str(
            profile.get(
                "user_id",
                "",
            )
        ).strip()

        if not user_id:
            continue

        full_name = (
            profile.get(
                "full_name"
            )
            or DEFAULT_AUTHOR_NAME
        )

        authors[user_id] = {
            "id": user_id,
            "name": str(
                full_name
            ).strip(),
            "avatar_url": profile.get(
                "avatar_url"
            ),
            "bio": profile.get(
                "bio"
            ),
            "county": profile.get(
                "county"
            ),
            "town": profile.get(
                "town"
            ),
        }

    return authors


def _attach_authors(
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    if not documents:
        return documents

    author_ids = [
        str(
            document.get(
                "author_user_id"
            )
        )
        for document in documents
        if document.get(
            "author_user_id"
        ) is not None
    ]

    authors = _load_authors(
        author_ids
    )

    output = []

    for document in documents:

        item = dict(document)

        author_id = str(
            item.get(
                "author_user_id",
                "",
            )
        ).strip()

        item["author"] = authors.get(
            author_id,
            _fallback_author(
                author_id
            ),
        )

        output.append(
            item
        )

    return output


# =========================================================
# POST HELPERS
# =========================================================

def _ensure_post_type(
    data: dict[str, Any],
) -> dict[str, Any]:

    payload = dict(data)

    if not payload.get("type"):

        category = str(
            payload.get(
                "category",
                "discussion",
            )
            or "discussion"
        ).strip().lower()

        if category in POST_TYPES:
            payload["type"] = category
        else:
            payload["type"] = "discussion"

    return payload


def _published_post(
    post_id: ObjectId,
) -> dict[str, Any] | None:

    return collection(
        POSTS
    ).find_one(
        {
            "_id": post_id,
            "status": "published",
        }
    )


# =========================================================
# CREATE POST
# =========================================================

def create_post(
    user_id: Any,
    data: dict[str, Any],
) -> dict[str, Any]:

    user_id = normalize_user_id(
        user_id
    )

    if not isinstance(data, dict):
        raise APIError(
            "Post data must be an object.",
            422,
            "validation_error",
        )

    payload = _ensure_post_type(
        data
    )

    hub = str(
        payload.get(
            "hub",
            "community",
        )
        or "community"
    ).strip().lower()

    hub = _normalize_hub(
        hub
    )

    _ensure_hub_access(
        user_id,
        hub,
    )

    # -----------------------------------------------------
    # Source reference
    # -----------------------------------------------------

    if payload.get("source"):
        payload["source"] = _validate_source(
            user_id,
            payload.get("source"),
        )

    # -----------------------------------------------------
    # Action / CTA
    # -----------------------------------------------------

    if payload.get("action"):
        payload["action"] = _validate_action(
            payload.get("action")
        )

    payload["hub"] = hub

    try:
        document = post_document(
            user_id,
            payload,
        )

    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "validation_error",
        )

    result = collection(
        POSTS
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    log_action(
        user_id,
        "community.post.created",
        "community_post",
        result.inserted_id,
        {
            "hub": document.get(
                "hub"
            ),
            "category": document.get(
                "category"
            ),
            "type": document.get(
                "type"
            ),
            "has_source": bool(
                document.get(
                    "source"
                )
            ),
            "has_action": bool(
                document.get(
                    "action"
                )
            ),
        },
    )

    hydrated = _attach_authors(
        [document]
    )[0]

    return serialize(
        hydrated
    )  # type: ignore[return-value]


# =========================================================
# GET SINGLE POST
# =========================================================

def get_post(
    user_id: Any,
    post_id: Any,
) -> dict[str, Any]:

    user_id = normalize_user_id(
        user_id
    )

    post_object_id = cid(
        post_id
    )

    document = _published_post(
        post_object_id
    )

    if not document:
        raise APIError(
            "Post not found.",
            404,
            "post_not_found",
        )

    hydrated = _attach_authors(
        [document]
    )[0]

    reaction = collection(
        REACTIONS
    ).find_one(
        {
            "post_id": str(
                post_object_id
            ),
            "user_id": user_id,
        },
        {
            "_id": 1,
        },
    )

    hydrated["liked_by_me"] = bool(
        reaction
    )

    return serialize(
        hydrated
    )  # type: ignore[return-value]


# =========================================================
# COMMUNITY FEED
# =========================================================

def feed(
    user_id: Any = None,
    category: str | None = None,
    hub: str | None = None,
    post_type: str | None = None,
    search: str | None = None,
    limit: int = DEFAULT_FEED_LIMIT,
) -> list[dict[str, Any]]:

    normalized_user_id = (
        normalize_user_id(
            user_id
        )
        if user_id is not None
        else None
    )

    limit = _normalize_limit(
        limit,
        DEFAULT_FEED_LIMIT,
        MAX_FEED_LIMIT,
    )

    query: dict[str, Any] = {
        "status": "published",
        "visibility": {
            "$in": [
                "public",
                "community",
            ]
        },
    }

    # -----------------------------------------------------
    # CATEGORY
    # -----------------------------------------------------

    if category:
        normalized_category = str(
            category
        ).strip().lower()

        if normalized_category:
            query["category"] = (
                normalized_category
            )

    # -----------------------------------------------------
    # HUB
    # -----------------------------------------------------

    if hub:
        query["hub"] = _normalize_hub(
            hub
        )

    # -----------------------------------------------------
    # TYPE
    # -----------------------------------------------------

    if post_type:
        query["type"] = _normalize_post_type(
            post_type
        )

    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    normalized_search = _normalize_search(
        search
    )

    if normalized_search:

        escaped = re.escape(
            normalized_search
        )

        query["$or"] = [
            {
                "title": {
                    "$regex": escaped,
                    "$options": "i",
                }
            },
            {
                "body": {
                    "$regex": escaped,
                    "$options": "i",
                }
            },
            {
                "location": {
                    "$regex": escaped,
                    "$options": "i",
                }
            },
            {
                "tags": {
                    "$regex": escaped,
                    "$options": "i",
                }
            },
        ]

    # -----------------------------------------------------
    # FETCH
    # -----------------------------------------------------

    documents = list(
        collection(POSTS)
        .find(query)
        .sort(
            [
                ("created_at", -1),
                ("_id", -1),
            ]
        )
        .limit(limit)
    )

    if not documents:
        return []

    # -----------------------------------------------------
    # AUTHORS
    # -----------------------------------------------------

    documents = _attach_authors(
        documents
    )

    # -----------------------------------------------------
    # PERSONAL REACTIONS
    # -----------------------------------------------------

    liked_post_ids: set[str] = set()

    if normalized_user_id:

        post_ids = [
            str(
                document["_id"]
            )
            for document in documents
        ]

        reaction_documents = (
            collection(
                REACTIONS
            )
            .find(
                {
                    "post_id": {
                        "$in": post_ids
                    },
                    "user_id": normalized_user_id,
                },
                {
                    "_id": 0,
                    "post_id": 1,
                },
            )
        )

        liked_post_ids = {
            str(
                reaction["post_id"]
            )
            for reaction in reaction_documents
        }

    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    output = []

    for document in documents:

        item = dict(document)

        item["liked_by_me"] = (
            str(
                item["_id"]
            )
            in liked_post_ids
        )

        output.append(
            item
        )

    return serialize_many(
        output
    )


# =========================================================
# SEARCH
# =========================================================

def search(
    user_id: Any,
    query: str,
    *,
    hub: str | None = None,
    category: str | None = None,
    post_type: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> list[dict[str, Any]]:

    normalized_query = _normalize_search(
        query
    )

    if not normalized_query:
        raise APIError(
            "Search query is required.",
            422,
            "search_query_required",
        )

    return feed(
        user_id=user_id,
        category=category,
        hub=hub,
        post_type=post_type,
        search=normalized_query,
        limit=_normalize_limit(
            limit,
            DEFAULT_SEARCH_LIMIT,
            MAX_SEARCH_LIMIT,
        ),
    )


# =========================================================
# UPDATE POST
# =========================================================

def update_post(
    user_id: Any,
    post_id: Any,
    data: dict[str, Any],
) -> dict[str, Any]:

    user_id = normalize_user_id(
        user_id
    )

    if not isinstance(data, dict):
        raise APIError(
            "Post data must be an object.",
            422,
            "validation_error",
        )

    post_object_id = cid(
        post_id
    )

    existing = collection(
        POSTS
    ).find_one(
        {
            "_id": post_object_id,
            "author_user_id": user_id,
            "status": {
                "$ne": "deleted"
            },
        }
    )

    if not existing:
        raise APIError(
            "Post not found or not owned by you.",
            404,
            "post_not_found",
        )

    allowed_fields = {
        "title",
        "body",
        "hub",
        "category",
        "type",
        "tags",
        "location",
        "visibility",
        "source",
        "action",
    }

    update_payload = {
        key: value
        for key, value in data.items()
        if key in allowed_fields
    }

    if not update_payload:
        raise APIError(
            "No valid fields were provided.",
            422,
            "validation_error",
        )

    # -----------------------------------------------------
    # Hub authorization
    # -----------------------------------------------------

    target_hub = str(
        update_payload.get(
            "hub",
            existing.get(
                "hub",
                "community",
            ),
        )
        or "community"
    ).strip().lower()

    target_hub = _normalize_hub(
        target_hub
    )

    _ensure_hub_access(
        user_id,
        target_hub,
    )

    update_payload["hub"] = target_hub

    # -----------------------------------------------------
    # Build complete candidate
    # -----------------------------------------------------

    merged = {
        "title": existing.get(
            "title",
            "",
        ),
        "body": existing.get(
            "body",
            "",
        ),
        "hub": existing.get(
            "hub",
            "community",
        ),
        "category": existing.get(
            "category",
            "general",
        ),
        "type": existing.get(
            "type",
            "discussion",
        ),
        "tags": existing.get(
            "tags",
            [],
        ),
        "location": existing.get(
            "location",
            "",
        ),
        "visibility": existing.get(
            "visibility",
            "public",
        ),
        "source": existing.get(
            "source",
            {},
        ),
        "action": existing.get(
            "action",
            {},
        ),
    }

    merged.update(
        update_payload
    )

    merged = _ensure_post_type(
        merged
    )

    # -----------------------------------------------------
    # Validate source if changed
    # -----------------------------------------------------

    if "source" in update_payload:

        merged["source"] = _validate_source(
            user_id,
            update_payload.get(
                "source"
            ),
        )

    # -----------------------------------------------------
    # Validate action if changed
    # -----------------------------------------------------

    if "action" in update_payload:

        merged["action"] = _validate_action(
            update_payload.get(
                "action"
            )
        )

    # -----------------------------------------------------
    # Model validation
    # -----------------------------------------------------

    try:
        validated = post_document(
            user_id,
            merged,
        )

    except ValueError as exc:
        raise APIError(
            str(exc),
            422,
            "validation_error",
        )

    # -----------------------------------------------------
    # Keep only requested fields
    # -----------------------------------------------------

    safe_update = {}

    for field in update_payload:
        safe_update[field] = validated.get(
            field
        )

    if (
        "type" not in safe_update
        and not existing.get("type")
    ):
        safe_update["type"] = validated.get(
            "type"
        )

    if not safe_update:
        raise APIError(
            "No valid fields were provided.",
            422,
            "validation_error",
        )

    safe_update["updated_at"] = now_utc()

    document = collection(
        POSTS
    ).find_one_and_update(
        {
            "_id": post_object_id,
            "author_user_id": user_id,
            "status": {
                "$ne": "deleted"
            },
        },
        {
            "$set": safe_update
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        raise APIError(
            "Post not found or not owned by you.",
            404,
            "post_not_found",
        )

    log_action(
        user_id,
        "community.post.updated",
        "community_post",
        post_object_id,
        {
            "fields": sorted(
                safe_update.keys()
            )
        },
    )

    hydrated = _attach_authors(
        [document]
    )[0]

    return serialize(
        hydrated
    )  # type: ignore[return-value]


# =========================================================
# DELETE POST
# =========================================================

def delete_post(
    user_id: Any,
    post_id: Any,
) -> dict[str, Any]:

    user_id = normalize_user_id(
        user_id
    )

    post_object_id = cid(
        post_id
    )

    document = collection(
        POSTS
    ).find_one_and_update(
        {
            "_id": post_object_id,
            "author_user_id": user_id,
            "status": {
                "$ne": "deleted"
            },
        },
        {
            "$set": {
                "status": "deleted",
                "updated_at": now_utc(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if not document:
        raise APIError(
            "Post not found or not owned by you.",
            404,
            "post_not_found",
        )

    log_action(
        user_id,
        "community.post.deleted",
        "community_post",
        post_object_id,
    )

    return {
        "deleted": True,
        "id": str(
            post_object_id
        ),
    }


# =========================================================
# NOTIFICATIONS
# =========================================================

def _notify(
    recipient_user_id: Any,
    *,
    title: str,
    message: str,
    notification_type: str,
    data: dict[str, Any] | None = None,
) -> None:
    """
    Current Jumuiya notification model stores metadata
    inside `data`.
    """

    try:
        notification_services.notify(
            str(recipient_user_id),
            {
                "title": title,
                "message": message,
                "type": notification_type,
                "data": data or {},
            },
        )
    except Exception:
        # Notification infrastructure must never turn a successful
        # Community action into a server error.
        pass


def _notify_post_author(
    *,
    actor_user_id: str,
    post: dict[str, Any],
    notification_type: str,
    title: str,
    message: str,
    extra_data: dict[str, Any] | None = None,
) -> None:

    author_user_id = str(
        post.get(
            "author_user_id",
            "",
        )
    ).strip()

    if not author_user_id:
        return

    if author_user_id == actor_user_id:
        return

    payload = {
        "actor_user_id": actor_user_id,
        "post_id": str(
            post.get("_id")
        ),
        "hub": post.get(
            "hub"
        ),
        "category": "community",
        "link": (
            f"/community/post/"
            f"{post.get('_id')}"
        ),
    }

    if extra_data:
        payload.update(
            extra_data
        )

    _notify(
        author_user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        data=payload,
    )


# =========================================================
# ADD COMMENT
# =========================================================

def add_comment(
    user_id: Any,
    post_id: Any,
    body: str,
) -> dict[str, Any]:

    user_id = normalize_user_id(
        user_id
    )

    body = _normalize_text(
        body,
        "Comment body",
        required=True,
        max_length=5000,
    )

    if body is None:
        raise APIError(
            "Comment cannot be empty.",
            422,
            "validation_error",
        )

    post_object_id = cid(
        post_id
    )

    post = _published_post(
        post_object_id
    )

    if not post:
        raise APIError(
            "Post not found.",
            404,
            "post_not_found",
        )

    timestamp = now_utc()

    document = {
        "post_id": str(
            post["_id"]
        ),
        "author_user_id": user_id,
        "body": body,
        "status": "published",
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    result = collection(
        COMMENTS
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    counter_update = collection(
        POSTS
    ).update_one(
        {
            "_id": post_object_id,
            "status": "published",
        },
        {
            "$inc": {
                "comments_count": 1,
            },
            "$set": {
                "updated_at": timestamp,
            },
        },
    )

    if counter_update.matched_count != 1:

        collection(
            COMMENTS
        ).delete_one(
            {
                "_id": result.inserted_id
            }
        )

        raise APIError(
            "Post is no longer available.",
            409,
            "post_unavailable",
        )

    log_action(
        user_id,
        "community.comment.created",
        "community_comment",
        result.inserted_id,
        {
            "post_id": str(
                post["_id"]
            )
        },
    )

    _notify_post_author(
        actor_user_id=user_id,
        post=post,
        notification_type="community_comment",
        title="New comment",
        message=(
            "Someone commented on your "
            "Community post."
        ),
    )

    hydrated = _attach_authors(
        [document]
    )[0]

    return serialize(
        hydrated
    )  # type: ignore[return-value]


# =========================================================
# COMMENTS
# =========================================================

def comments(
    post_id: Any,
    limit: int = DEFAULT_COMMENT_LIMIT,
) -> list[dict[str, Any]]:

    post_object_id = cid(
        post_id
    )

    limit = _normalize_limit(
        limit,
        DEFAULT_COMMENT_LIMIT,
        MAX_COMMENT_LIMIT,
    )

    documents = list(
        collection(COMMENTS)
        .find(
            {
                "post_id": str(
                    post_object_id
                ),
                "status": "published",
            }
        )
        .sort(
            [
                ("created_at", 1),
                ("_id", 1),
            ]
        )
        .limit(limit)
    )

    if not documents:
        return []

    documents = _attach_authors(
        documents
    )

    return serialize_many(
        documents
    )


# =========================================================
# REACT / UNREACT
# =========================================================

def react(
    user_id: Any,
    post_id: Any,
) -> dict[str, Any]:

    user_id = normalize_user_id(
        user_id
    )

    post_object_id = cid(
        post_id
    )

    posts = collection(
        POSTS
    )

    reactions = collection(
        REACTIONS
    )

    post = _published_post(
        post_object_id
    )

    if not post:
        raise APIError(
            "Post not found.",
            404,
            "post_not_found",
        )

    reaction_filter = {
        "post_id": str(
            post_object_id
        ),
        "user_id": user_id,
    }

    existing = reactions.find_one(
        reaction_filter
    )

    reaction_created = False
    reaction_deleted = False

    # =====================================================
    # UNLIKE
    # =====================================================

    if existing:

        deletion = reactions.delete_one(
            {
                "_id": existing["_id"]
            }
        )

        if deletion.deleted_count == 1:

            reaction_deleted = True

            posts.update_one(
                {
                    "_id": post_object_id,
                    "likes_count": {
                        "$gt": 0
                    },
                },
                {
                    "$inc": {
                        "likes_count": -1
                    },
                    "$set": {
                        "updated_at": now_utc()
                    },
                },
            )

        liked = False

    # =====================================================
    # LIKE
    # =====================================================

    else:

        reaction_document = {
            "post_id": str(
                post_object_id
            ),
            "user_id": user_id,
            "created_at": now_utc(),
        }

        try:

            reactions.insert_one(
                reaction_document
            )

            reaction_created = True

            posts.update_one(
                {
                    "_id": post_object_id
                },
                {
                    "$inc": {
                        "likes_count": 1
                    },
                    "$set": {
                        "updated_at": now_utc()
                    },
                },
            )

            liked = True

        except DuplicateKeyError:

            # Another request already created the reaction.
            concurrent_reaction = reactions.find_one(
                reaction_filter,
                {
                    "_id": 1,
                },
            )

            if not concurrent_reaction:
                raise

            liked = True

    # =====================================================
    # CURRENT COUNTER
    # =====================================================

    updated_post = posts.find_one(
        {
            "_id": post_object_id
        },
        {
            "likes_count": 1,
            "author_user_id": 1,
            "hub": 1,
        },
    )

    likes_count = 0

    if updated_post:

        try:

            likes_count = max(
                0,
                int(
                    updated_post.get(
                        "likes_count",
                        0,
                    )
                ),
            )

        except (
            TypeError,
            ValueError,
        ):

            likes_count = 0

    # =====================================================
    # NOTIFICATION
    # =====================================================

    if (
        liked
        and reaction_created
        and updated_post
    ):

        _notify_post_author(
            actor_user_id=user_id,
            post={
                "_id": post_object_id,
                "author_user_id": updated_post.get(
                    "author_user_id"
                ),
                "hub": updated_post.get(
                    "hub"
                ),
            },
            notification_type="community_reaction",
            title="New reaction",
            message=(
                "Someone liked your "
                "Community post."
            ),
        )

        log_action(
            user_id,
            "community.post.reacted",
            "community_post",
            post_object_id,
            {
                "reaction": "like",
            },
        )

    elif reaction_deleted:

        log_action(
            user_id,
            "community.post.unreacted",
            "community_post",
            post_object_id,
            {
                "reaction": "like",
            },
        )

    return {
        "post_id": str(
            post_object_id
        ),
        "liked": liked,
        "likes_count": likes_count,
    }


# =========================================================
# COMMUNITY STATISTICS
# =========================================================

def stats() -> dict[str, Any]:
    """
    Lightweight Community statistics.
    """

    posts_collection = collection(
        POSTS
    )

    comments_collection = collection(
        COMMENTS
    )

    published_posts = (
        posts_collection.count_documents(
            {
                "status": "published"
            }
        )
    )

    published_comments = (
        comments_collection.count_documents(
            {
                "status": "published"
            }
        )
    )

    hub_counts = {}

    for hub in COMMUNITY_HUBS:

        hub_counts[hub] = (
            posts_collection.count_documents(
                {
                    "status": "published",
                    "hub": hub,
                }
            )
        )

    return {
        "posts": published_posts,
        "comments": published_comments,
        "hubs": hub_counts,
    }
