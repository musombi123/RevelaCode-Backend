# backend/jumuiya/community/models.py

from __future__ import annotations

from datetime import datetime, timezone


# =========================================================
# TIME
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


# =========================================================
# COMMUNITY POST
# =========================================================

def post_document(user_id, data):
    """
    Create a Jumuiya Community post.

    Community is the shared social layer across:

        Biashara
        Shamba
        Elimu
        Community

    Every post belongs to an authenticated Jumuiya user.
    """

    if user_id is None:
        raise ValueError(
            "author user ID is required."
        )

    if not isinstance(data, dict):
        raise ValueError(
            "Post data must be a dictionary."
        )

    title = str(
        data.get("title", "")
        or ""
    ).strip()

    body = str(
        data.get("body", "")
        or ""
    ).strip()

    if not title:
        raise ValueError(
            "Post title is required."
        )

    if not body:
        raise ValueError(
            "Post body is required."
        )

    if len(title) > 200:
        raise ValueError(
            "Post title is too long."
        )

    if len(body) > 10000:
        raise ValueError(
            "Post body is too long."
        )

    category = str(
        data.get(
            "category",
            "general",
        )
        or "general"
    ).strip().lower()

    hub = str(
        data.get(
            "hub",
            "community",
        )
        or "community"
    ).strip().lower()

    allowed_hubs = {
        "community",
        "biashara",
        "shamba",
        "elimu",
    }

    if hub not in allowed_hubs:
        raise ValueError(
            "Invalid community hub."
        )

    location = str(
        data.get(
            "location",
            "",
        )
        or ""
    ).strip()

    now = now_utc()

    return {
        "author_user_id": str(
            user_id
        ),

        "title": title,

        "body": body,

        "category": category,

        "hub": hub,

        "location": location,

        "status": "published",

        "likes_count": 0,

        "comments_count": 0,

        "created_at": now,

        "updated_at": now,
    }