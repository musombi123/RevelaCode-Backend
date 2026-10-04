# backend/jumuiya/community/services.py

from __future__ import annotations

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

from backend.jumuiya.notifications import services as notification_services


# =========================================================
# COLLECTIONS
# =========================================================

POSTS = "jumuiya_community_posts"
COMMENTS = "jumuiya_community_comments"
REACTIONS = "jumuiya_community_reactions"
PROFILES = "jumuiya_profiles"


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_FEED_LIMIT = 30
MAX_FEED_LIMIT = 100

DEFAULT_COMMENT_LIMIT = 100
MAX_COMMENT_LIMIT = 200

MAX_SEARCH_LENGTH = 100

DEFAULT_AUTHOR_NAME = "Community member"


# =========================================================
# TIME
# =========================================================

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# =========================================================
# IDS
# =========================================================

def normalize_user_id(user_id: Any) -> str:
    """
    Normalize the authenticated user identifier.

    Community stores user references as strings because the same
    identity bridge is used across Jumuiya.
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
    Convert an incoming resource ID to ObjectId.
    """
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError, ValueError):
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
    Recursively serialize Mongo/BSON values so nested structures
    such as source/action/author are also API-safe.
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


def serialize(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doc:
        return None

    output = dict(doc)

    if "_id" in output:
        output["id"] = str(output.pop("_id"))

    return _serialize_value(output)


def serialize_many(
    docs: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        serialized
        for serialized in (
            serialize(doc)
            for doc in docs
        )
        if serialized is not None
    ]


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
    except (TypeError, ValueError):
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

    if max_length is not None and len(value) > max_length:
        raise APIError(
            f"{field} is too long.",
            422,
            "validation_error",
        )

    return value


def _normalize_hub(value: Any) -> str:
    value = _normalize_text(
        value,
        "hub",
        required=True,
        max_length=40,
    )

    value = value.lower()

    if value not in COMMUNITY_HUBS:
        raise APIError(
            "Invalid community hub.",
            422,
            "invalid_hub",
        )

    return value


def _normalize_post_type(value: Any) -> str:
    value = _normalize_text(
        value,
        "type",
        required=True,
        max_length=50,
    )

    value = value.lower()

    if value not in POST_TYPES:
        raise APIError(
            "Invalid community post type.",
            422,
            "invalid_post_type",
        )

    return value


def _normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []

    if not isinstance(value, (list, tuple)):
        raise APIError(
            "tags must be an array.",
            422,
            "validation_error",
        )

    output: list[str] = []

    for item in value:
        if not isinstance(item, str):
            continue

        tag = item.strip().lower()

        if not tag:
            continue

        if len(tag) > 40:
            continue

        if tag not in output:
            output.append(tag)

        if len(output) >= 10:
            break

    return output


# =========================================================
# PUBLIC AUTHOR PROFILE
# =========================================================

def _fallback_author(user_id: str) -> dict[str, Any]:
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
    """
    Batch-load public Jumuiya identity profiles.

    Private identity information such as phone/email is deliberately
    excluded from Community responses.
    """

    normalized_ids = {
        str(user_id).strip()
        for user_id in user_ids
        if user_id is not None and str(user_id).strip()
    }

    if not normalized_ids:
        return {}

    documents = list(
        collection(PROFILES).find(
            {
                "user_id": {
                    "$in": list(normalized_ids)
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

    output: dict[str, dict[str, Any]] = {
        user_id: _fallback_author(user_id)
        for user_id in normalized_ids
    }

    for profile in documents:
        user_id = str(
            profile.get("user_id", "")
        ).strip()

        if not user_id:
            continue

        full_name = (
            profile.get("full_name")
            or DEFAULT_AUTHOR_NAME
        )

        output[user_id] = {
            "id": user_id,
            "name": str(full_name).strip(),
            "avatar_url": profile.get("avatar_url"),
            "bio": profile.get("bio"),
            "county": profile.get("county"),
            "town": profile.get("town"),
        }

    return output


def _attach_authors(
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not documents:
        return documents

    author_ids = [
        str(doc.get("author_user_id"))
        for doc in documents
        if doc.get("author_user_id") is not None
    ]

    authors = _load_authors(author_ids)

    output: list[dict[str, Any]] = []

    for document in documents:
        item = dict(document)

        author_id = str(
            item.get("author_user_id", "")
        ).strip()

        item["author"] = authors.get(
            author_id,
            _fallback_author(author_id),
        )

        output.append(item)

    return output


# =========================================================
# POST HELPERS
# =========================================================

def _post_query(
    *,
    post_id: ObjectId,
    user_id: str | None = None,
) -> dict[str, Any] | None:
    query: dict[str, Any] = {
        "_id": post_id,
        "status": "published",
    }

    if user_id is not None:
        query["author_user_id"] = user_id

    return collection(POSTS).find_one(query)


def _ensure_post_type(
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Keep backward compatibility with older clients that only send
    category.

    Example:
        category=question -> type=question
        category=opportunity -> type=opportunity
    """

    payload = dict(data)

    if not payload.get("type"):
        category = str(
            payload.get("category", "general")
        ).strip().lower()

        if category in POST_TYPES:
            payload["type"] = category
        else:
            payload["type"] = "discussion"

    return payload


def _validate_search(value: Any) -> str | None:
    if value is None:
        return None

    search = str(value).strip()

    if not search:
        return None

    return search[:MAX_SEARCH_LENGTH]


# =========================================================
# CREATE POST
# =========================================================

def create_post(
    user_id: Any,
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a Community post.

    Supports:
        - title
        - body
        - category
        - hub
        - type
        - tags
        - location
        - visibility
        - source
        - action

    Validation remains centralized in community.models.
    """

    user_id = normalize_user_id(user_id)

    if not isinstance(data, dict):
        raise APIError(
            "Post data must be an object.",
            422,
            "validation_error",
        )

    payload = _ensure_post_type(data)

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

    result = collection(POSTS).insert_one(
        document
    )

    document["_id"] = result.inserted_id

    log_action(
        user_id,
        "community.post.created",
        "community_post",
        result.inserted_id,
        {
            "hub": document.get("hub"),
            "category": document.get("category"),
            "type": document.get("type"),
        },
    )

    hydrated = _attach_authors(
        [document]
    )[0]

    return serialize(hydrated)  # type: ignore[return-value]


# =========================================================
# GET SINGLE POST
# =========================================================

def get_post(
    user_id: Any,
    post_id: Any,
) -> dict[str, Any]:
    """
    Return a single published Community post.
    """

    user_id = normalize_user_id(user_id)

    document = _post_query(
        post_id=cid(post_id)
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

    reactions = collection(
        REACTIONS
    ).find_one(
        {
            "post_id": str(document["_id"]),
            "user_id": user_id,
        }
    )

    hydrated["liked_by_me"] = bool(
        reactions
    )

    return serialize(hydrated)  # type: ignore[return-value]


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
    """
    Return the published Community feed.

    The return value intentionally remains a flat list.

    This preserves compatibility with:
        - Web CommunityFeed
        - CommunityDashboard
        - Android clients
        - Existing /feed API consumers
    """

    normalized_user_id = (
        normalize_user_id(user_id)
        if user_id is not None
        else None
    )

    limit = _normalize_limit(
        limit,
        DEFAULT_FEED_LIMIT,
        MAX_FEED_LIMIT,
    )

    query: dict[str, Any] = {
        "status": "published"
    }

    if category:
        query["category"] = str(
            category
        ).strip().lower()

    if hub:
        hub = str(
            hub
        ).strip().lower()

        if hub not in COMMUNITY_HUBS:
            raise APIError(
                "Invalid community hub.",
                422,
                "invalid_hub",
            )

        query["hub"] = hub

    if post_type:
        post_type = str(
            post_type
        ).strip().lower()

        if post_type not in POST_TYPES:
            raise APIError(
                "Invalid community post type.",
                422,
                "invalid_post_type",
            )

        query["type"] = post_type

    normalized_search = _validate_search(
        search
    )

    if normalized_search:
        escaped = (
            __import__("re")
            .escape(normalized_search)
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

    documents = _attach_authors(
        documents
    )

    # -----------------------------------------------------
    # PERSONAL REACTION STATE
    # -----------------------------------------------------

    liked_post_ids: set[str] = set()

    if normalized_user_id:
        post_ids = [
            str(doc["_id"])
            for doc in documents
        ]

        reaction_documents = collection(
            REACTIONS
        ).find(
            {
                "post_id": {
                    "$in": post_ids
                },
                "user_id": normalized_user_id,
            },
            {
                "post_id": 1
            },
        )

        liked_post_ids = {
            str(reaction["post_id"])
            for reaction in reaction_documents
        }

    # -----------------------------------------------------
    # FINAL API SHAPE
    # -----------------------------------------------------

    output: list[dict[str, Any]] = []

    for document in documents:
        item = dict(document)

        item["liked_by_me"] = (
            str(item["_id"])
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
    limit: int = DEFAULT_FEED_LIMIT,
) -> list[dict[str, Any]]:
    """
    Dedicated Community search endpoint/service.

    Internally reuses the same feed engine so ranking and response
    shape remain consistent.
    """

    normalized_query = _validate_search(
        query
    )

    if not normalized_query:
        raise APIError(
            "Search query is required.",
            422,
            "validation_error",
        )

    return feed(
        user_id=user_id,
        category=category,
        hub=hub,
        post_type=post_type,
        search=normalized_query,
        limit=limit,
    )


# =========================================================
# UPDATE POST
# =========================================================

def update_post(
    user_id: Any,
    post_id: Any,
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Update an owned Community post.

    Only public/editable post fields are accepted.
    System fields such as counters, author, status and timestamps
    are protected.
    """

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

    allowed = {
        "title",
        "body",
        "category",
        "hub",
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
        if key in allowed
    }

    if not update_payload:
        raise APIError(
            "No valid fields were provided.",
            422,
            "validation_error",
        )

    # -----------------------------------------------------
    # Merge old + new content and validate through model
    # -----------------------------------------------------

    merged = {
        "title": existing.get(
            "title",
            ""
        ),
        "body": existing.get(
            "body",
            ""
        ),
        "category": existing.get(
            "category",
            "general",
        ),
        "hub": existing.get(
            "hub",
            "community",
        ),
        "type": existing.get(
            "type",
            existing.get(
                "category",
                "discussion",
            ),
        ),
        "tags": existing.get(
            "tags",
            [],
        ),
        "location": existing.get(
            "location"
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

    # Only use validated content fields.
    content_fields = {
        "title",
        "body",
        "category",
        "hub",
        "type",
        "tags",
        "location",
        "visibility",
        "source",
        "action",
    }

    safe_update = {
        field: validated.get(field)
        for field in content_fields
        if field in update_payload or (
            field == "type"
            and "category" in update_payload
        )
    }

    # Explicitly retain type when callers update both category/type.
    if "type" in update_payload:
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

    return serialize(hydrated)  # type: ignore[return-value]


# =========================================================
# DELETE POST
# =========================================================

def delete_post(
    user_id: Any,
    post_id: Any,
) -> dict[str, Any]:
    """
    Soft-delete the post instead of physically removing it.

    Moderation/audit history remains available.
    """

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
        "id": str(post_object_id),
    }


# =========================================================
# NOTIFICATION HELPERS
# =========================================================

def _notify(
    recipient_user_id: Any,
    data: dict[str, Any],
) -> None:
    """
    Notifications are secondary to the Community operation.

    A notification failure must never cause a successful comment
    or reaction to become a 500 response.
    """

    try:
        notification_services.notify(
            str(recipient_user_id),
            data,
        )
    except Exception:
        # Notification infrastructure must not break Community.
        pass


def _notify_post_author(
    *,
    actor_user_id: str,
    post: dict[str, Any],
    notification_type: str,
    title: str,
    message: str,
) -> None:
    author_user_id = str(
        post.get("author_user_id", "")
    ).strip()

    if not author_user_id:
        return

    # Never notify someone about their own activity.
    if author_user_id == actor_user_id:
        return

    _notify(
        author_user_id,
        {
            "type": notification_type,
            "title": title,
            "message": message,
            "actor_user_id": actor_user_id,
            "post_id": str(
                post.get("_id")
            ),
            "hub": post.get("hub"),
            "category": "community",
            "link": (
                f"/community/post/"
                f"{post.get('_id')}"
            ),
            "read": False,
            "created_at": now_utc(),
        },
    )


# =========================================================
# ADD COMMENT
# =========================================================

def add_comment(
    user_id: Any,
    post_id: Any,
    body: str,
) -> dict[str, Any]:
    """
    Add a comment to a published post.
    """

    user_id = normalize_user_id(
        user_id
    )

    body = _normalize_text(
        body,
        "Comment body",
        required=True,
        max_length=5000,
    )

    post_object_id = cid(
        post_id
    )

    post = collection(
        POSTS
    ).find_one(
        {
            "_id": post_object_id,
            "status": "published",
        }
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

    # -----------------------------------------------------
    # Update denormalized counter
    # -----------------------------------------------------

    counter_update = collection(
        POSTS
    ).update_one(
        {
            "_id": post_object_id,
            "status": "published",
        },
        {
            "$inc": {
                "comments_count": 1
            },
            "$set": {
                "updated_at": timestamp
            },
        },
    )

    # If the post became unavailable between the initial read
    # and the counter update, roll back the inserted comment.
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

    # -----------------------------------------------------
    # Notify post author
    # -----------------------------------------------------

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

    return serialize(hydrated)  # type: ignore[return-value]


# =========================================================
# COMMENTS
# =========================================================

def comments(
    post_id: Any,
    limit: int = DEFAULT_COMMENT_LIMIT,
) -> list[dict[str, Any]]:
    """
    Return published comments oldest-first.
    """

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
    """
    Toggle a user's like on a post.

    Important:
    - The reaction collection must have a unique compound index
      on post_id + user_id.
    - likes_count is changed only after a confirmed insert/delete.
    - DuplicateKeyError is handled specifically rather than catching
      every exception.
    """

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

    post = posts.find_one(
        {
            "_id": post_object_id,
            "status": "published",
        }
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

    # =====================================================
    # UNLIKE
    # =====================================================

    if existing:
        deletion = reactions.delete_one(
            {
                "_id": existing["_id"]
            }
        )

        # Only decrement if this request actually removed
        # the reaction.
        if deletion.deleted_count == 1:
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

            # Increment only after a successful insert.
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
            # Another concurrent request already inserted
            # this user's reaction.
            liked = True

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

    likes_count = (
        max(
            0,
            int(
                updated_post.get(
                    "likes_count",
                    0,
                )
            ),
        )
        if updated_post
        else 0
    )

    # Notify only when the user actually liked the post.
    if liked and existing is None and updated_post:
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

    elif not liked and existing:
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
    Lightweight aggregate Community statistics.

    Intended for dashboard/admin insight without exposing private
    user information.
    """

    posts_collection = collection(
        POSTS
    )

    comments_collection = collection(
        COMMENTS
    )

    published_posts = posts_collection.count_documents(
        {
            "status": "published"
        }
    )

    published_comments = comments_collection.count_documents(
        {
            "status": "published"
        }
    )

    hub_counts: dict[str, int] = {}

    for hub in COMMUNITY_HUBS:
        hub_counts[hub] = posts_collection.count_documents(
            {
                "status": "published",
                "hub": hub,
            }
        )

    return {
        "posts": published_posts,
        "comments": published_comments,
        "hubs": hub_counts,
    }
