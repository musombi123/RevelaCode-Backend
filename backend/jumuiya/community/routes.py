# backend/jumuiya/community/routes.py

from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import (
    require_authenticated,
    current_user_id,
)
from backend.jumuiya.core.responses import (
    ok,
    created,
)

from backend.jumuiya.community import services


# =========================================================
# BLUEPRINT
# =========================================================

community_bp = Blueprint(
    "jumuiya_community",
    __name__,
)


# =========================================================
# REQUEST HELPERS
# =========================================================

def body():
    data = request.get_json(
        silent=True
    )

    if not isinstance(data, dict):
        raise APIError(
            "JSON request body is required.",
            400,
            "invalid_json",
        )

    return data


def text(
    data,
    key,
    required=False,
    max_len=5000,
):
    value = data.get(
        key,
        "",
    )

    if value is None:
        value = ""

    if not isinstance(value, str):
        raise APIError(
            f"{key} must be text.",
            422,
            "validation_error",
        )

    value = value.strip()

    if required and not value:
        raise APIError(
            f"{key} is required.",
            422,
            "validation_error",
        )

    if len(value) > max_len:
        raise APIError(
            f"{key} is too long.",
            422,
            "validation_error",
        )

    return value


def parse_limit(
    default=30,
    maximum=100,
):
    try:
        value = int(
            request.args.get(
                "limit",
                default,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        value = default

    return max(
        1,
        min(
            value,
            maximum,
        ),
    )


# =========================================================
# HEALTH
# =========================================================

@community_bp.get("/health")
def health():
    return ok({
        "hub": "community",
        "status": "online",
    })


# =========================================================
# FEED
# =========================================================

@community_bp.get("/feed")
@require_authenticated
def get_feed():
    return ok(
        services.feed(
            category=request.args.get(
                "category"
            ),
            hub=request.args.get(
                "hub"
            ),
            limit=parse_limit(
                default=30,
                maximum=100,
            ),
        )
    )


# =========================================================
# CREATE POST
# =========================================================

@community_bp.post("/posts")
@require_authenticated
def create_post():

    data = body()

    hub = (
        text(
            data,
            "hub",
            required=False,
            max_len=60,
        )
        or "community"
    ).lower()

    category = (
        text(
            data,
            "category",
            required=False,
            max_len=60,
        )
        or "general"
    ).lower()

    allowed_hubs = {
        "community",
        "biashara",
        "shamba",
        "elimu",
    }

    if hub not in allowed_hubs:
        raise APIError(
            "Invalid community hub.",
            422,
            "invalid_hub",
        )

    payload = {
        "title": text(
            data,
            "title",
            required=True,
            max_len=180,
        ),

        "body": text(
            data,
            "body",
            required=True,
            max_len=10000,
        ),

        "category": category,

        "hub": hub,

        "location": text(
            data,
            "location",
            required=False,
            max_len=160,
        ),
    }

    return created(
        services.create_post(
            current_user_id(),
            payload,
        ),
        "Community post published.",
    )


# =========================================================
# UPDATE POST
# =========================================================

@community_bp.put(
    "/posts/<post_id>"
)
@require_authenticated
def edit_post(post_id):

    return ok(
        services.update_post(
            current_user_id(),
            post_id,
            body(),
        ),
        "Post updated.",
    )


# =========================================================
# DELETE POST
# =========================================================

@community_bp.delete(
    "/posts/<post_id>"
)
@require_authenticated
def remove_post(post_id):

    return ok(
        services.delete_post(
            current_user_id(),
            post_id,
        ),
        "Post deleted.",
    )


# =========================================================
# COMMENTS
# =========================================================

@community_bp.get(
    "/posts/<post_id>/comments"
)
@require_authenticated
def get_comments(post_id):

    return ok(
        services.comments(
            post_id,
            limit=parse_limit(
                default=100,
                maximum=200,
            ),
        )
    )


@community_bp.post(
    "/posts/<post_id>/comments"
)
@require_authenticated
def add_comment(post_id):

    data = body()

    comment_body = text(
        data,
        "body",
        required=True,
        max_len=3000,
    )

    return created(
        services.add_comment(
            current_user_id(),
            post_id,
            comment_body,
        ),
        "Comment added.",
    )


# =========================================================
# REACTION
# =========================================================

@community_bp.post(
    "/posts/<post_id>/react"
)
@require_authenticated
def react(post_id):

    return ok(
        services.react(
            current_user_id(),
            post_id,
        )
    )
