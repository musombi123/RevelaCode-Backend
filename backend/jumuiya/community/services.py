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


# =========================================================
# LIMITS
# =========================================================

DEFAULT_FEED_LIMIT = 30
MAX_FEED_LIMIT = 100

DEFAULT_COMMENT_LIMIT = 100
MAX_COMMENT_LIMIT = 200

DEFAULT_SEARCH_LIMIT = 20
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
    Recursively serialize BSON/Mongo values.

    This handles nested structures such as:

        author
        source
        action
        tags
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
    """
    Batch-load public Jumuiya profile information.

    Never exposes:
        phone
        email
        credentials
        private account fields
    """

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
            profile.get("full_name")
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

        output.append(item)

    return output


# =========================================================
# POST HELPERS
# =========================================================

def _ensure_post_type(
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Backward compatibility for older clients.

    Older clients may send:

        category=question

    without:

        type=question
    """

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

    return collection(POSTS).find_one(
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
    """
    Canonical Community feed.

    Return value intentionally remains:

        list[dict]

    so existing Web and Android clients remain compatible.
    """

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
        query["category"] = (
            str(category)
            .strip()
            .lower()
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
    # QUERY
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
    # AUTHOR HYDRATION
    # -----------------------------------------------------

    documents = _attach_authors(
        documents
    )

    # -----------------------------------------------------
    # PERSONAL REACTION STATE
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
    # FINAL RESPONSE
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
            50,
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
    # Build a complete candidate document and validate it
    # through the canonical Community model.
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
    # Only update fields the caller requested.
    # -----------------------------------------------------

    safe_update = {}

    for field in update_payload:
        safe_update[field] = validated.get(
            field
        )

    # If type is omitted but the existing document is a legacy
    # post without a type, ensure it receives the canonical value.
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
    Send a Jumuiya notification.

    IMPORTANT:
    The current notification model only persists:

        title
        message
        type
        read
        data
        created_at

    Therefore Community metadata must live inside `data`.
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
        # Community activity must not fail just because
        # notification infrastructure is temporarily unavailable.
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

    # Never notify a user about their own activity.
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

    # -----------------------------------------------------
    # Increment comment counter only while post is published.
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
                "comments_count": 1,
            },
            "$set": {
                "updated_at": timestamp,
            },
        },
    )

    if counter_update.matched_count != 1:

        # Roll the comment back because its parent post
        # is no longer available.
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
    # Notify post owner
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
    """
    Toggle a user's like.

    Requires the unique Mongo index:

        post_id + user_id

    on jumuiya_community_reactions.
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

    # Used to distinguish a real insert from
    # a concurrent duplicate request.
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

            # Another concurrent request already created
            # this exact user/post reaction.
            concurrent_reaction = (
                reactions.find_one(
                    reaction_filter
                )
            )

            if not concurrent_reaction:
                raise

            liked = True

    # =====================================================
    # LATEST COUNTER
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
    Lightweight aggregate statistics.

    This service is intentionally separate from the public feed.
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
