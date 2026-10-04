# backend/jumuiya/community/schemas.py

from __future__ import annotations

from backend.jumuiya.community.models import (
    COMMUNITY_HUBS,
    POST_TYPES,
    VISIBILITIES,
)


# =========================================================
# HELPERS
# =========================================================

def _object(data):
    if not isinstance(data, dict):
        raise ValueError(
            "JSON object required."
        )


def _text(
    data,
    key,
    *,
    required=False,
    max_len=500,
):
    value = data.get(key, "")

    if value is None:
        value = ""

    if not isinstance(value, str):
        raise ValueError(
            f"{key} must be text."
        )

    value = value.strip()

    if required and not value:
        raise ValueError(
            f"{key} is required."
        )

    if len(value) > max_len:
        raise ValueError(
            f"{key} must not exceed {max_len} characters."
        )

    return value


def _choice(
    data,
    key,
    allowed,
    *,
    default=None,
    required=False,
):
    value = data.get(key)

    if value is None or value == "":
        if required:
            raise ValueError(
                f"{key} is required."
            )

        return default

    if not isinstance(value, str):
        raise ValueError(
            f"{key} must be text."
        )

    value = value.strip().lower()

    if value not in allowed:
        raise ValueError(
            f"{key} is invalid."
        )

    return value


def _list(
    data,
    key,
    *,
    max_items=10,
    item_max_len=40,
):
    value = data.get(key)

    if value is None:
        return []

    if not isinstance(value, list):
        raise ValueError(
            f"{key} must be a list."
        )

    if len(value) > max_items:
        raise ValueError(
            f"{key} cannot contain more than {max_items} items."
        )

    cleaned = []

    for item in value:

        if not isinstance(item, str):
            raise ValueError(
                f"Each {key} item must be text."
            )

        item = item.strip()

        if not item:
            continue

        if len(item) > item_max_len:
            raise ValueError(
                f"{key} items must not exceed {item_max_len} characters."
            )

        cleaned.append(
            item.lower()
        )

    return list(
        dict.fromkeys(cleaned)
    )


# =========================================================
# CREATE POST
# =========================================================

def create_post_payload(data):
    _object(data)

    source = data.get("source")

    if source is None:
        source = {}

    if not isinstance(source, dict):
        raise ValueError(
            "source must be an object."
        )

    action = data.get("action")

    if action is None:
        action = {}

    if not isinstance(action, dict):
        raise ValueError(
            "action must be an object."
        )

    return {
        "title": _text(
            data,
            "title",
            required=True,
            max_len=200,
        ),

        "body": _text(
            data,
            "body",
            required=True,
            max_len=10000,
        ),

        "hub": _choice(
            data,
            "hub",
            COMMUNITY_HUBS,
            default="community",
        ),

        "category": (
            _text(
                data,
                "category",
                max_len=60,
            )
            or "general"
        ).lower(),

        "type": _choice(
            data,
            "type",
            POST_TYPES,
            default=None,
        ),

        "tags": _list(
            data,
            "tags",
            max_items=10,
            item_max_len=40,
        ),

        "location": _text(
            data,
            "location",
            max_len=200,
        ),

        "visibility": _choice(
            data,
            "visibility",
            VISIBILITIES,
            default="public",
        ),

        "source": source,

        "action": action,
    }


# =========================================================
# UPDATE POST
# =========================================================

def update_post_payload(data):
    _object(data)

    allowed = {
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

    unknown = set(data.keys()) - allowed

    # Silently ignore unknown fields so future frontend
    # clients don't unnecessarily break the endpoint.
    payload = {}

    if "title" in data:
        payload["title"] = _text(
            data,
            "title",
            required=True,
            max_len=200,
        )

    if "body" in data:
        payload["body"] = _text(
            data,
            "body",
            required=True,
            max_len=10000,
        )

    if "hub" in data:
        payload["hub"] = _choice(
            data,
            "hub",
            COMMUNITY_HUBS,
            required=True,
        )

    if "category" in data:
        payload["category"] = (
            _text(
                data,
                "category",
                max_len=60,
            )
            or "general"
        ).lower()

    if "type" in data:
        payload["type"] = _choice(
            data,
            "type",
            POST_TYPES,
            required=True,
        )

    if "tags" in data:
        payload["tags"] = _list(
            data,
            "tags",
            max_items=10,
            item_max_len=40,
        )

    if "location" in data:
        payload["location"] = _text(
            data,
            "location",
            max_len=200,
        )

    if "visibility" in data:
        payload["visibility"] = _choice(
            data,
            "visibility",
            VISIBILITIES,
            required=True,
        )

    if "source" in data:
        if not isinstance(
            data["source"],
            dict,
        ):
            raise ValueError(
                "source must be an object."
            )

        payload["source"] = data["source"]

    if "action" in data:
        if not isinstance(
            data["action"],
            dict,
        ):
            raise ValueError(
                "action must be an object."
            )

        payload["action"] = data["action"]

    if not payload:
        raise ValueError(
            "No valid post fields were provided."
        )

    return payload
