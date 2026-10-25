# backend/jumuiya/community/group_services.py

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError


GROUPS = "jumuiya_community_groups"

GROUP_CATEGORIES = {
    "community",
    "biashara",
    "shamba",
    "elimu",
}

MAX_GROUP_NAME = 100
MAX_GROUP_DESCRIPTION = 1500
MAX_GROUP_LOCATION = 120
MAX_GROUP_SEARCH = 100


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_user_id(user_id: Any) -> str:
    if user_id is None:
        raise APIError(
            "Authentication is required.",
            401,
            "authentication_required",
        )

    value = str(user_id).strip()

    if not value:
        raise APIError(
            "Authentication is required.",
            401,
            "authentication_required",
        )

    return value


def parse_group_id(group_id: Any) -> ObjectId:
    try:
        return ObjectId(str(group_id))
    except (InvalidId, TypeError, ValueError):
        raise APIError(
            "Invalid group ID.",
            400,
            "invalid_group_id",
        )


def normalize_text(
    value: Any,
    field: str,
    *,
    required: bool = False,
    maximum: int = 500,
) -> str:
    if value is None:
        value = ""

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

    if len(value) > maximum:
        raise APIError(
            f"{field} must not exceed {maximum} characters.",
            422,
            "validation_error",
        )

    return value


def serialize_group(
    document: dict | None,
    user_id: str,
) -> dict | None:
    if not document:
        return None

    member_ids = document.get(
        "member_user_ids",
        [],
    )

    if not isinstance(member_ids, list):
        member_ids = []

    member_ids = [
        str(member_id)
        for member_id in member_ids
    ]

    created_at = document.get("created_at")
    updated_at = document.get("updated_at")

    return {
        "id": str(document["_id"]),
        "name": document.get("name", ""),
        "description": document.get("description", ""),
        "category": document.get("category", "community"),
        "location": document.get("location") or "Online",
        "members": len(member_ids),
        "member_count": len(member_ids),
        "posts": int(document.get("posts_count", 0) or 0),
        "activeToday": int(document.get("active_today", 0) or 0),
        "featured": bool(document.get("featured", False)),
        "joined": str(user_id) in member_ids,
        "createdAt": (
            created_at.isoformat()
            if isinstance(created_at, datetime)
            else None
        ),
        "updatedAt": (
            updated_at.isoformat()
            if isinstance(updated_at, datetime)
            else None
        ),
    }


def _active_group(group_id: Any) -> dict:
    document = collection(GROUPS).find_one({
        "_id": parse_group_id(group_id),
        "status": "active",
    })

    if not document:
        raise APIError(
            "Community group not found.",
            404,
            "group_not_found",
        )

    return document


def list_groups(
    user_id: Any,
    *,
    category: str | None = None,
    search: str | None = None,
    mine: bool = False,
    limit: int = 100,
) -> dict:
    user_id = normalize_user_id(user_id)

    query: dict[str, Any] = {
        "status": "active",
    }

    category = (category or "").strip().lower()

    if category and category != "all":
        if category not in GROUP_CATEGORIES:
            raise APIError(
                "Invalid group category.",
                422,
                "invalid_group_category",
            )

        query["category"] = category

    if mine:
        query["member_user_ids"] = user_id

    search = (search or "").strip()[:MAX_GROUP_SEARCH]

    if search:
        safe_pattern = re.escape(search)

        query["$or"] = [
            {"name": {"$regex": safe_pattern, "$options": "i"}},
            {"description": {"$regex": safe_pattern, "$options": "i"}},
            {"location": {"$regex": safe_pattern, "$options": "i"}},
            {"category": {"$regex": safe_pattern, "$options": "i"}},
        ]

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 100

    limit = max(1, min(limit, 100))

    groups_collection = collection(GROUPS)

    documents = list(
        groups_collection.find(query)
        .sort([
            ("featured", -1),
            ("created_at", -1),
        ])
        .limit(limit)
    )

    return {
        "groups": [
            serialize_group(document, user_id)
            for document in documents
        ],
        "total": groups_collection.count_documents(query),
    }


def get_group(
    user_id: Any,
    group_id: Any,
) -> dict:
    user_id = normalize_user_id(user_id)

    document = _active_group(group_id)

    return serialize_group(
        document,
        user_id,
    )


def create_group(
    user_id: Any,
    payload: dict,
) -> dict:
    user_id = normalize_user_id(user_id)

    if not isinstance(payload, dict):
        raise APIError(
            "A JSON request body is required.",
            400,
            "invalid_json",
        )

    name = normalize_text(
        payload.get("name"),
        "name",
        required=True,
        maximum=MAX_GROUP_NAME,
    )

    description = normalize_text(
        payload.get("description"),
        "description",
        required=True,
        maximum=MAX_GROUP_DESCRIPTION,
    )

    category = normalize_text(
        payload.get("category", "community"),
        "category",
        required=True,
        maximum=30,
    ).lower()

    if category not in GROUP_CATEGORIES:
        raise APIError(
            "Select a valid group category.",
            422,
            "invalid_group_category",
        )

    location = normalize_text(
        payload.get("location", ""),
        "location",
        maximum=MAX_GROUP_LOCATION,
    )

    timestamp = now_utc()

    document = {
        "name": name,
        "description": description,
        "category": category,
        "location": location or "Online",
        "created_by_user_id": user_id,
        "member_user_ids": [user_id],
        "posts_count": 0,
        "active_today": 0,
        "featured": False,
        "status": "active",
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    result = collection(GROUPS).insert_one(document)
    document["_id"] = result.inserted_id

    log_action(
        user_id,
        "community_group_created",
        resource="community_group",
        resource_id=result.inserted_id,
        metadata={
            "category": category,
        },
    )

    return serialize_group(
        document,
        user_id,
    )


def join_group(
    user_id: Any,
    group_id: Any,
) -> dict:
    user_id = normalize_user_id(user_id)
    document = _active_group(group_id)

    group_object_id = document["_id"]
    member_ids = document.get("member_user_ids", [])

    already_joined = (
        isinstance(member_ids, list)
        and user_id in [str(value) for value in member_ids]
    )

    if not already_joined:
        collection(GROUPS).update_one(
            {
                "_id": group_object_id,
                "status": "active",
                "member_user_ids": {"$ne": user_id},
            },
            {
                "$addToSet": {
                    "member_user_ids": user_id,
                },
                "$set": {
                    "updated_at": now_utc(),
                },
            },
        )

        log_action(
            user_id,
            "community_group_joined",
            resource="community_group",
            resource_id=group_object_id,
        )

    updated = _active_group(group_object_id)

    return serialize_group(
        updated,
        user_id,
    )


def leave_group(
    user_id: Any,
    group_id: Any,
) -> dict:
    user_id = normalize_user_id(user_id)

    document = _active_group(group_id)
    group_object_id = document["_id"]

    member_ids = document.get("member_user_ids", [])

    is_member = (
        isinstance(member_ids, list)
        and user_id in [str(value) for value in member_ids]
    )

    if is_member:
        collection(GROUPS).update_one(
            {
                "_id": group_object_id,
                "member_user_ids": user_id,
            },
            {
                "$pull": {
                    "member_user_ids": user_id,
                },
                "$set": {
                    "updated_at": now_utc(),
                },
            },
        )

        log_action(
            user_id,
            "community_group_left",
            resource="community_group",
            resource_id=group_object_id,
        )

    updated = _active_group(group_object_id)

    return serialize_group(
        updated,
        user_id,
    )


# ============================================================
# GROUP SHARED FILES
# ============================================================

GROUP_FILES = "jumuiya_community_group_files"
COMMUNITY_MEDIA = "jumuiya_community_media"


def _require_group_member(document: dict, user_id: str) -> None:
    members = document.get("member_user_ids", [])
    member_ids = [str(value) for value in members] if isinstance(members, list) else []
    if user_id not in member_ids:
        raise APIError(
            "Join this group before viewing or sharing its files.",
            403,
            "group_membership_required",
        )


def _serialize_group_file(document: dict) -> dict:
    created_at = document.get("created_at")
    return {
        "id": str(document.get("_id") or ""),
        "group_id": str(document.get("group_id") or ""),
        "file_name": str(document.get("file_name") or "Community document"),
        "url": str(document.get("url") or ""),
        "mime_type": str(document.get("mime_type") or "application/pdf"),
        "size_bytes": int(document.get("size_bytes", 0) or 0),
        "caption": str(document.get("caption") or ""),
        "shared_by_user_id": str(document.get("shared_by_user_id") or ""),
        "kind": "document",
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else None,
    }


def list_group_files(
    user_id: Any,
    group_id: Any,
    *,
    limit: int = 50,
) -> dict:
    user_id = normalize_user_id(user_id)
    group = _active_group(group_id)
    _require_group_member(group, user_id)

    safe_limit = max(1, min(int(limit or 50), 100))
    query = {"group_id": str(group["_id"])}
    rows = list(
        collection(GROUP_FILES)
        .find(query)
        .sort([("created_at", -1), ("_id", -1)])
        .limit(safe_limit)
    )
    return {
        "files": [_serialize_group_file(row) for row in rows],
        "total": collection(GROUP_FILES).count_documents(query),
    }


def share_group_file(
    user_id: Any,
    group_id: Any,
    payload: dict,
) -> dict:
    user_id = normalize_user_id(user_id)
    group = _active_group(group_id)
    _require_group_member(group, user_id)

    if not isinstance(payload, dict):
        raise APIError("A JSON request body is required.", 400, "invalid_json")

    media_id = payload.get("media_id") or payload.get("id")
    if not isinstance(media_id, str) or not media_id.strip() or len(media_id.strip()) > 100:
        raise APIError("A valid uploaded PDF is required.", 422, "invalid_media_id")

    try:
        media_object_id = ObjectId(media_id.strip())
    except (InvalidId, TypeError, ValueError):
        raise APIError("Invalid uploaded media ID.", 400, "invalid_media_id")

    media = collection(COMMUNITY_MEDIA).find_one({
        "_id": media_object_id,
        "uploaded_by_user_id": user_id,
    })
    if not media:
        raise APIError(
            "The uploaded PDF was not found or was not uploaded by your account.",
            403,
            "media_attachment_access_denied",
        )
    if str(media.get("kind") or "").lower() != "document" or str(media.get("format") or "").lower() != "pdf":
        raise APIError("Only validated PDF documents can be shared to a group.", 422, "pdf_required")

    url = str(media.get("secure_url") or "")
    if not url.startswith("https://"):
        raise APIError("The PDF URL is invalid.", 422, "invalid_media_url")

    caption = normalize_text(payload.get("caption", ""), "caption", maximum=500)
    timestamp = now_utc()
    document = {
        "group_id": str(group["_id"]),
        "media_id": str(media["_id"]),
        "file_name": str(media.get("file_name") or "Community document"),
        "url": url,
        "mime_type": str(media.get("mime_type") or "application/pdf"),
        "size_bytes": int(media.get("size_bytes", 0) or 0),
        "caption": caption,
        "shared_by_user_id": user_id,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    result = collection(GROUP_FILES).insert_one(document)
    document["_id"] = result.inserted_id

    log_action(
        user_id,
        "community_group_file_shared",
        resource="community_group_file",
        resource_id=result.inserted_id,
        metadata={"group_id": str(group["_id"]), "file_name": document["file_name"]},
    )
    collection(GROUPS).update_one(
        {"_id": group["_id"], "status": "active"},
        {"$set": {"updated_at": timestamp}},
    )
    return _serialize_group_file(document)
