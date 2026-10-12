# backend/jumuiya/community/models.py

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# =========================================================
# CONSTANTS
# =========================================================

COMMUNITY_HUBS = {
    "community",
    "biashara",
    "shamba",
    "elimu",
}

POST_TYPES = {
    "discussion",
    "question",
    "announcement",
    "opportunity",
    "job",
    "event",
    "market",
    "help",
    "knowledge",
    "alert",
    "request",
    "service_offer",
    "service_needed",
}

POST_STATUSES = {
    "published",
    "hidden",
    "deleted",
}

VISIBILITIES = {
    "public",
    "community",
}

DEFAULT_POST_TYPE = "discussion"
DEFAULT_CATEGORY = "general"
DEFAULT_HUB = "community"
DEFAULT_VISIBILITY = "public"


# =========================================================
# TIME
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


# =========================================================
# HELPERS
# =========================================================

def _text(
    value: Any,
    *,
    default: str = "",
    max_len: int | None = None,
) -> str:
    if value is None:
        value = default

    if not isinstance(value, str):
        raise ValueError("Value must be text.")

    value = value.strip()

    if max_len is not None and len(value) > max_len:
        raise ValueError(
            f"Value must not exceed {max_len} characters."
        )

    return value


def _string_list(
    value: Any,
    *,
    max_items: int = 20,
    item_max_len: int = 80,
) -> list[str]:
    if value is None:
        return []

    if not isinstance(value, list):
        raise ValueError("Value must be a list.")

    if len(value) > max_items:
        raise ValueError(
            f"Value cannot contain more than {max_items} items."
        )

    result = []

    for item in value:
        if not isinstance(item, str):
            raise ValueError(
                "Every list item must be text."
            )

        item = item.strip()

        if not item:
            continue

        if len(item) > item_max_len:
            raise ValueError(
                f"List items must not exceed {item_max_len} characters."
            )

        result.append(item)

    return list(dict.fromkeys(result))


# =========================================================
# COMMUNITY POST
# =========================================================

def post_document(
    user_id,
    data,
):
    """
    Create a canonical Jumuiya Community post.

    Community acts as the connection layer between:

        Biashara
        Shamba
        Elimu
        Community

    Posts can optionally reference an actual ecosystem
    entity such as:

        harvest
        business
        product
        school
        lesson
        marketplace listing
    """

    if user_id is None:
        raise ValueError(
            "author user ID is required."
        )

    if not isinstance(data, dict):
        raise ValueError(
            "Post data must be a dictionary."
        )

    # -----------------------------------------------------
    # CONTENT
    # -----------------------------------------------------

    title = _text(
        data.get("title"),
        max_len=200,
    )

    body = _text(
        data.get("body"),
        max_len=10000,
    )

    if not title:
        raise ValueError(
            "Post title is required."
        )

    if not body:
        raise ValueError(
            "Post body is required."
        )

    # -----------------------------------------------------
    # HUB
    # -----------------------------------------------------

    hub = _text(
        data.get(
            "hub",
            DEFAULT_HUB,
        ),
        default=DEFAULT_HUB,
        max_len=30,
    ).lower()

    if hub not in COMMUNITY_HUBS:
        raise ValueError(
            "Invalid community hub."
        )

    # -----------------------------------------------------
    # TYPE
    # -----------------------------------------------------

    post_type = _text(
        data.get(
            "type",
            "",
        ),
        default="",
        max_len=40,
    ).lower()

    if not post_type:
        post_type = (
            str(
                data.get(
                    "category",
                    DEFAULT_POST_TYPE,
                )
                or DEFAULT_POST_TYPE
            )
            .strip()
            .lower()
        )

    if post_type not in POST_TYPES:
        raise ValueError(
            "Invalid community post type."
        )

    # -----------------------------------------------------
    # CATEGORY
    # -----------------------------------------------------

    category = _text(
        data.get(
            "category",
            DEFAULT_CATEGORY,
        ),
        default=DEFAULT_CATEGORY,
        max_len=60,
    ).lower()

    if not category:
        category = DEFAULT_CATEGORY

    # -----------------------------------------------------
    # TAGS
    # -----------------------------------------------------

    tags = _string_list(
        data.get("tags"),
        max_items=10,
        item_max_len=40,
    )

    tags = [
        tag.lower()
        for tag in tags
    ]

    # -----------------------------------------------------
    # LOCATION
    # -----------------------------------------------------

    location = _text(
        data.get(
            "location",
            "",
        ),
        max_len=200,
    )

    # -----------------------------------------------------
    # VISIBILITY
    # -----------------------------------------------------

    visibility = _text(
        data.get(
            "visibility",
            DEFAULT_VISIBILITY,
        ),
        default=DEFAULT_VISIBILITY,
        max_len=30,
    ).lower()

    if visibility not in VISIBILITIES:
        raise ValueError(
            "Invalid post visibility."
        )

    # -----------------------------------------------------
    # SOURCE ENTITY
    # -----------------------------------------------------
    #
    # Example:
    #
    # {
    #   "hub": "shamba",
    #   "entity_type": "harvest",
    #   "entity_id": "..."
    # }
    #

    source = data.get("source")

    if source is None:
        source = {}

    if not isinstance(source, dict):
        raise ValueError(
            "source must be an object."
        )

    source_hub = _text(
        source.get("hub"),
        max_len=30,
    ).lower()

    if source_hub and source_hub not in COMMUNITY_HUBS:
        raise ValueError(
            "Invalid source hub."
        )

    source_entity_type = _text(
        source.get("entity_type"),
        max_len=60,
    ).lower()

    source_entity_id = _text(
        source.get("entity_id"),
        max_len=120,
    )

    source_document = {}

    if (
        source_hub
        or source_entity_type
        or source_entity_id
    ):
        source_document = {
            "hub": source_hub,
            "entity_type": source_entity_type,
            "entity_id": source_entity_id,
        }

    # -----------------------------------------------------
    # ACTION / CTA
    # -----------------------------------------------------

    action = data.get("action")

    if action is None:
        action = {}

    if not isinstance(action, dict):
        raise ValueError(
            "action must be an object."
        )

    action_type = _text(
        action.get("type"),
        max_len=50,
    ).lower()

    action_label = _text(
        action.get("label"),
        max_len=80,
    )

    action_target = _text(
        action.get("target"),
        max_len=300,
    )

    action_document = {}

    if action_type or action_label or action_target:
        action_document = {
            "type": action_type,
            "label": action_label,
            "target": action_target,
        }

    # -----------------------------------------------------
    # TIME
    # -----------------------------------------------------

    now = now_utc()

    # -----------------------------------------------------
    # DOCUMENT
    # -----------------------------------------------------

    return {
        "author_user_id": str(
            user_id
        ),

        "title": title,

        "body": body,

        "hub": hub,

        "category": category,

        "type": post_type,

        "tags": tags,

        "location": location,

        "visibility": visibility,

        "source": source_document,

        "action": action_document,

        "status": "published",

        # Engagement counters.
        "likes_count": 0,

        "comments_count": 0,

        "bookmarks_count": 0,

        "shares_count": 0,

        "reports_count": 0,

        "created_at": now,

        "updated_at": now,
    }
