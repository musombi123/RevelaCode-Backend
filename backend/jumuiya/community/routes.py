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

from backend.jumuiya.community import (
    schemas,
    services,
)


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

    if not isinstance(
        data,
        dict,
    ):
        raise APIError(
            "JSON request body is required.",
            400,
            "invalid_json",
        )

    return data


def parse_limit(
    default=30,
    maximum=100,
):
    raw = request.args.get(
        "limit",
        default,
    )

    try:
        value = int(raw)
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
        "version": "2.0",
        "features": [
            "posts",
            "comments",
            "reactions",
            "ecosystem_context",
            "notifications",
        ],
    })


# =========================================================
# FEED
# =========================================================

@community_bp.get("/feed")
@require_authenticated
def get_feed():

    user_id = current_user_id()

    return ok(
        services.feed(
            user_id=user_id,
            category=request.args.get(
                "category"
            ),
            hub=request.args.get(
                "hub"
            ),
            post_type=request.args.get(
                "type"
            ),
            search=request.args.get(
                "search"
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

    payload = schemas.create_post_payload(
        body()
    )

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

    payload = schemas.update_post_payload(
        body()
    )

    return ok(
        services.update_post(
            current_user_id(),
            post_id,
            payload,
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

    comment_body = data.get(
        "body",
        "",
    )

    if not isinstance(
        comment_body,
        str,
    ):
        raise APIError(
            "body must be text.",
            422,
            "validation_error",
        )

    comment_body = comment_body.strip()

    if not comment_body:
        raise APIError(
            "Comment cannot be empty.",
            422,
            "validation_error",
        )

    if len(comment_body) > 3000:
        raise APIError(
            "Comment must not exceed 3000 characters.",
            422,
            "validation_error",
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


# =========================================================
# SEARCH
# =========================================================

@community_bp.get("/search")
@require_authenticated
def search():

    query = (
        request.args.get(
            "q",
            "",
        )
        .strip()
    )

    if not query:
        raise APIError(
            "Search query is required.",
            422,
            "search_query_required",
        )

    return ok(
        services.search(
            current_user_id(),
            query,
            limit=parse_limit(
                default=20,
                maximum=50,
            ),
        )
    )
