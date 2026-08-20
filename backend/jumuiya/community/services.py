# backend/jumuiya/community/services.py

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.audit import log_action

from backend.jumuiya.community.models import post_document


# =========================================================
# TIME
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


# =========================================================
# IDS
# =========================================================

def cid(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise APIError(
            "Invalid resource ID.",
            400,
            "invalid_id",
        )


# =========================================================
# SERIALIZATION
# =========================================================

def serialize(doc):
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
# CREATE POST
# =========================================================

def create_post(
    user_id,
    data,
):
    try:
        document = post_document(
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
        "jumuiya_community_posts"
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
    )

    return serialize(
        document
    )


# =========================================================
# COMMUNITY FEED
# =========================================================

def feed(
    category=None,
    hub=None,
    limit=30,
):
    """
    Return published community posts.

    Community supports:

        community
        biashara
        shamba
        elimu
    """

    try:
        limit = int(limit)
    except (
        TypeError,
        ValueError,
    ):
        limit = 30

    limit = max(
        1,
        min(limit, 100),
    )

    query = {
        "status": "published"
    }

    if category:
        query["category"] = (
            str(category)
            .strip()
            .lower()
        )

    if hub:
        query["hub"] = (
            str(hub)
            .strip()
            .lower()
        )

    documents = (
        collection(
            "jumuiya_community_posts"
        )
        .find(query)
        .sort(
            "created_at",
            -1,
        )
        .limit(limit)
    )

    return serialize_many(
        documents
    )


# =========================================================
# UPDATE POST
# =========================================================

def update_post(
    user_id,
    post_id,
    data,
):
    if not isinstance(
        data,
        dict,
    ):
        raise APIError(
            "Post data must be an object.",
            422,
            "validation_error",
        )

    allowed = {
        "title",
        "body",
        "category",
        "hub",
        "location",
    }

    update = {
        key: value
        for key, value in data.items()
        if key in allowed
    }

    if not update:
        raise APIError(
            "No valid fields were provided.",
            422,
            "validation_error",
        )

    if "title" in update:
        if not isinstance(
            update["title"],
            str,
        ):
            raise APIError(
                "title must be text.",
                422,
                "validation_error",
            )

        update["title"] = (
            update["title"].strip()
        )

        if not update["title"]:
            raise APIError(
                "title is required.",
                422,
                "validation_error",
            )

    if "body" in update:
        if not isinstance(
            update["body"],
            str,
        ):
            raise APIError(
                "body must be text.",
                422,
                "validation_error",
            )

        update["body"] = (
            update["body"].strip()
        )

        if not update["body"]:
            raise APIError(
                "body is required.",
                422,
                "validation_error",
            )

    if "hub" in update:
        update["hub"] = (
            str(update["hub"])
            .strip()
            .lower()
        )

        if update["hub"] not in {
            "community",
            "biashara",
            "shamba",
            "elimu",
        }:
            raise APIError(
                "Invalid community hub.",
                422,
                "invalid_hub",
            )

    if "category" in update:
        update["category"] = (
            str(update["category"])
            .strip()
            .lower()
        )

    update["updated_at"] = now_utc()

    document = collection(
        "jumuiya_community_posts"
    ).find_one_and_update(
        {
            "_id": cid(post_id),
            "author_user_id": str(
                user_id
            ),
            "status": {
                "$ne": "deleted"
            },
        },
        {
            "$set": update
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
        post_id,
    )

    return serialize(
        document
    )


# =========================================================
# DELETE POST
# =========================================================

def delete_post(
    user_id,
    post_id,
):
    """
    Soft-delete the post instead of physically removing it.

    This preserves moderation and audit history.
    """

    result = collection(
        "jumuiya_community_posts"
    ).update_one(
        {
            "_id": cid(post_id),
            "author_user_id": str(
                user_id
            ),
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
    )

    if result.modified_count != 1:
        raise APIError(
            "Post not found or not owned by you.",
            404,
            "post_not_found",
        )

    log_action(
        user_id,
        "community.post.deleted",
        "community_post",
        post_id,
    )

    return {
        "deleted": True,
        "id": str(post_id),
    }


# =========================================================
# ADD COMMENT
# =========================================================

def add_comment(
    user_id,
    post_id,
    body,
):
    if not isinstance(
        body,
        str,
    ):
        raise APIError(
            "Comment body must be text.",
            422,
            "validation_error",
        )

    body = body.strip()

    if not body:
        raise APIError(
            "Comment cannot be empty.",
            422,
            "validation_error",
        )

    if len(body) > 5000:
        raise APIError(
            "Comment is too long.",
            422,
            "validation_error",
        )

    post_id = cid(
        post_id
    )

    post = collection(
        "jumuiya_community_posts"
    ).find_one(
        {
            "_id": post_id,
            "status": "published",
        }
    )

    if not post:
        raise APIError(
            "Post not found.",
            404,
            "post_not_found",
        )

    document = {
        "post_id": str(
            post["_id"]
        ),
        "author_user_id": str(
            user_id
        ),
        "body": body,
        "status": "published",
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }

    result = collection(
        "jumuiya_community_comments"
    ).insert_one(
        document
    )

    document["_id"] = (
        result.inserted_id
    )

    collection(
        "jumuiya_community_posts"
    ).update_one(
        {
            "_id": post_id
        },
        {
            "$inc": {
                "comments_count": 1
            }
        },
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

    return serialize(
        document
    )


# =========================================================
# COMMENTS
# =========================================================

def comments(
    post_id,
    limit=100,
):
    post_id = cid(
        post_id
    )

    try:
        limit = int(limit)
    except (
        TypeError,
        ValueError,
    ):
        limit = 100

    limit = max(
        1,
        min(limit, 200),
    )

    documents = (
        collection(
            "jumuiya_community_comments"
        )
        .find(
            {
                "post_id": str(
                    post_id
                ),
                "status": "published",
            }
        )
        .sort(
            "created_at",
            1,
        )
        .limit(limit)
    )

    return serialize_many(
        documents
    )


# =========================================================
# LIKE / UNLIKE
# =========================================================

def react(
    user_id,
    post_id,
):
    """
    Toggle a user's like on a post.

    One reaction per user per post.
    """

    post_id = cid(
        post_id
    )

    posts = collection(
        "jumuiya_community_posts"
    )

    reactions = collection(
        "jumuiya_community_reactions"
    )

    post = posts.find_one(
        {
            "_id": post_id,
            "status": "published",
        }
    )

    if not post:
        raise APIError(
            "Post not found.",
            404,
            "post_not_found",
        )

    user_id = str(
        user_id
    )

    existing = reactions.find_one(
        {
            "post_id": str(
                post_id
            ),
            "user_id": user_id,
        }
    )

    if existing:

        reactions.delete_one(
            {
                "_id": existing["_id"]
            }
        )

        posts.update_one(
            {
                "_id": post_id,
                "likes_count": {
                    "$gt": 0
                },
            },
            {
                "$inc": {
                    "likes_count": -1
                }
            },
        )

        liked = False

    else:

        try:

            reactions.insert_one(
                {
                    "post_id": str(
                        post_id
                    ),
                    "user_id": user_id,
                    "created_at": now_utc(),
                }
            )

        except Exception:
            # Handles duplicate reaction attempts
            # safely under concurrent requests.
            existing = reactions.find_one(
                {
                    "post_id": str(
                        post_id
                    ),
                    "user_id": user_id,
                }
            )

            if existing:
                liked = True

            else:
                raise

        posts.update_one(
            {
                "_id": post_id
            },
            {
                "$inc": {
                    "likes_count": 1
                }
            },
        )

        liked = True

    updated_post = posts.find_one(
        {
            "_id": post_id
        }
    )

    return {
        "liked": liked,
        "likes_count": (
            updated_post.get(
                "likes_count",
                0,
            )
            if updated_post
            else 0
        ),
    }