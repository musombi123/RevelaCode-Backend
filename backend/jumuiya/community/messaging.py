# backend/jumuiya/community/messaging.py
"""
Persistent, participant-scoped Community matters and direct messages.

This module deliberately uses the existing Jumuiya database and authenticated
RevelaCode user IDs. A matter and its messages are visible only to the
participants recorded on that matter. No demo threads are generated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError


MATTERS = "jumuiya_community_matters"
MESSAGES = "jumuiya_community_matter_messages"
PROFILES = "jumuiya_profiles"
POSTS = "jumuiya_community_posts"

ALLOWED_STATUSES = {"open", "agreed", "done"}
MAX_MESSAGE_LENGTH = 3000
MAX_TITLE_LENGTH = 200


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user_id(value: Any) -> str:
    if value is None or not str(value).strip():
        raise APIError("Authentication is required.", 401, "authentication_required")
    return str(value).strip()


def _id(value: Any) -> ObjectId:
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError, ValueError):
        raise APIError("Invalid matter ID.", 400, "invalid_matter_id")


def _serialize_value(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    return value


def _serialize(doc: dict | None) -> dict | None:
    if not doc:
        return None
    result = dict(doc)
    if "_id" in result:
        result["id"] = str(result.pop("_id"))
    return _serialize_value(result)


def _profile(user_id: str) -> dict:
    profile = collection(PROFILES).find_one({"user_id": user_id}) or {}
    name = (
        profile.get("full_name")
        or profile.get("name")
        or profile.get("username")
        or "Community member"
    )
    avatar = profile.get("avatar_url") or profile.get("avatar") or None
    return {
        "user_id": user_id,
        "id": user_id,
        "name": str(name).strip() or "Community member",
        "avatar_url": avatar if isinstance(avatar, str) and avatar.strip() else None,
    }


def _require_recipient(user_id: str, recipient_id: str) -> dict:
    if not recipient_id:
        raise APIError("participant_user_id is required.", 422, "validation_error")
    if recipient_id == user_id:
        raise APIError("You cannot start a conversation with yourself.", 422, "invalid_recipient")
    profile = collection(PROFILES).find_one({"user_id": recipient_id})
    # Feed authors may predate a profile record. A published Community post is
    # accepted as proof that this ID belongs to a real Community participant.
    if not profile:
        post = collection(POSTS).find_one({
            "author_user_id": recipient_id,
            "status": "published",
            "visibility": {"$in": ["public", "community"]},
        })
        if not post:
            raise APIError(
                "The selected participant is not available in Community.",
                404,
                "community_member_not_found",
            )
    return _profile(recipient_id)


def _matter_for_participant(user_id: str, matter_id: Any) -> dict:
    matter = collection(MATTERS).find_one({
        "_id": _id(matter_id),
        "participant_ids": user_id,
    })
    if not matter:
        # Do not disclose whether a matter ID exists for somebody else.
        raise APIError("Matter not found.", 404, "matter_not_found")
    return matter


def _format_matter(doc: dict, user_id: str) -> dict:
    result = _serialize(doc) or {}
    other_ids = [
        str(value)
        for value in doc.get("participant_ids", [])
        if str(value) != user_id
    ]
    counterparty = _profile(other_ids[0]) if other_ids else None
    result["counterparty"] = counterparty
    result["other_participant"] = counterparty
    result["title"] = (
        str(doc.get("title") or "").strip()
        or (
            f"Conversation with {counterparty['name']}"
            if counterparty
            else "Community conversation"
        )
    )
    if doc.get("linked_post"):
        result["linked_post"] = _serialize_value(doc["linked_post"])
    return result


def list_matters(user_id: Any, *, limit: int = 30) -> dict:
    uid = _user_id(user_id)
    try:
        count = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        count = 30
    docs = list(
        collection(MATTERS)
        .find({"participant_ids": uid})
        .sort([("updated_at", -1), ("_id", -1)])
        .limit(count)
    )
    return {
        "matters": [_format_matter(doc, uid) for doc in docs],
        "count": len(docs),
    }


def create_matter(user_id: Any, payload: Any) -> dict:
    uid = _user_id(user_id)
    if not isinstance(payload, dict):
        raise APIError("A JSON object is required.", 400, "invalid_json")

    recipient_id = str(payload.get("participant_user_id") or "").strip()
    recipient = _require_recipient(uid, recipient_id)
    title = str(payload.get("title") or "").strip()
    if len(title) > MAX_TITLE_LENGTH:
        raise APIError("Matter title must be 200 characters or fewer.", 422, "validation_error")

    linked_post_id = str(
        payload.get("linked_post_id") or payload.get("related_post_id") or ""
    ).strip()
    linked_post = None
    if linked_post_id:
        try:
            post_oid = ObjectId(linked_post_id)
        except (InvalidId, TypeError, ValueError):
            raise APIError("Invalid linked Community post ID.", 400, "invalid_post_id")
        post = collection(POSTS).find_one({
            "_id": post_oid,
            "author_user_id": recipient_id,
            "status": {"$nin": ["deleted", "hidden"]},
            "visibility": {"$in": ["public", "community"]},
        })
        if not post:
            raise APIError(
                "The linked post must be a visible Community post authored by the selected participant.",
                404,
                "linked_post_not_found",
            )
        linked_post = {
            "id": str(post["_id"]),
            "post_id": str(post["_id"]),
            "title": str(post.get("title") or "Community post"),
            "location": post.get("location") or post.get("place") or post.get("area") or "",
            "hub": post.get("hub") or "community",
            "type": post.get("type") or post.get("post_type") or "discussion",
        }
        if not title:
            title = linked_post["title"][:MAX_TITLE_LENGTH]

    participants = sorted({uid, recipient_id})
    # One conversation per participant pair, with separate threads when the
    # user explicitly starts a conversation about a specific post.
    conversation_key = "|".join(participants) + "|post:" + (linked_post_id or "direct")
    matters = collection(MATTERS)
    existing = matters.find_one({"conversation_key": conversation_key})
    if existing:
        return _format_matter(existing, uid)

    now = _now()
    document = {
        "participant_ids": participants,
        "participant_user_ids": participants,
        "conversation_key": conversation_key,
        "title": title or f"Conversation with {recipient['name']}",
        "status": "open",
        "linked_post_id": linked_post_id or None,
        "linked_post": linked_post,
        "last_message": "",
        "last_message_at": None,
        "created_by_user_id": uid,
        "created_at": now,
        "updated_at": now,
    }
    inserted = matters.insert_one(document)
    document["_id"] = inserted.inserted_id
    try:
        log_action(uid, "community.matter.created", "community_matter", inserted.inserted_id, {
            "participant_ids": participants,
            "linked_post_id": linked_post_id or None,
        })
    except Exception:
        pass
    return _format_matter(document, uid)


def list_messages(user_id: Any, matter_id: Any, *, limit: int = 100) -> dict:
    uid = _user_id(user_id)
    matter = _matter_for_participant(uid, matter_id)
    try:
        count = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        count = 100
    # Fetch the newest bounded page, then reverse it into chronological order
    # for rendering a normal chat thread.
    docs = list(
        collection(MESSAGES)
        .find({
            "matter_id": str(matter["_id"]),
            "participant_ids": uid,
        })
        .sort([("created_at", -1), ("_id", -1)])
        .limit(count)
    )
    docs.reverse()
    return {
        "matter_id": str(matter["_id"]),
        "messages": [_serialize(doc) for doc in docs],
        "count": len(docs),
    }


def send_message(user_id: Any, matter_id: Any, payload: Any) -> dict:
    uid = _user_id(user_id)
    if not isinstance(payload, dict):
        raise APIError("A JSON object is required.", 400, "invalid_json")
    text = payload.get("body", payload.get("text", payload.get("content", "")))
    if not isinstance(text, str):
        raise APIError("Message body must be text.", 422, "validation_error")
    text = text.strip()
    if not text:
        raise APIError("Message body cannot be empty.", 422, "validation_error")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise APIError("Messages must be 3000 characters or fewer.", 422, "validation_error")

    matter = _matter_for_participant(uid, matter_id)
    now = _now()
    message = {
        "matter_id": str(matter["_id"]),
        "participant_ids": list(matter.get("participant_ids") or []),
        "sender_user_id": uid,
        "author_user_id": uid,
        "body": text,
        "created_at": now,
        "edited_at": None,
    }
    inserted = collection(MESSAGES).insert_one(message)
    message["_id"] = inserted.inserted_id
    collection(MATTERS).update_one(
        {"_id": matter["_id"], "participant_ids": uid},
        {"$set": {
            "last_message": text[:240],
            "last_message_at": now,
            "updated_at": now,
        }},
    )
    try:
        log_action(uid, "community.matter.message_sent", "community_matter", matter["_id"], {
            "message_id": str(inserted.inserted_id),
        })
    except Exception:
        pass
    return _serialize(message)


def update_status(user_id: Any, matter_id: Any, payload: Any) -> dict:
    uid = _user_id(user_id)
    if not isinstance(payload, dict):
        raise APIError("A JSON object is required.", 400, "invalid_json")
    status = str(payload.get("status") or "").strip().lower()
    if status not in ALLOWED_STATUSES:
        raise APIError("Status must be open, agreed, or done.", 422, "invalid_matter_status")
    matter = _matter_for_participant(uid, matter_id)
    now = _now()
    collection(MATTERS).update_one(
        {"_id": matter["_id"], "participant_ids": uid},
        {"$set": {
            "status": status,
            "updated_at": now,
            "status_updated_by_user_id": uid,
            "status_updated_at": now,
        }},
    )
    updated = collection(MATTERS).find_one({"_id": matter["_id"], "participant_ids": uid})
    try:
        log_action(uid, "community.matter.status_updated", "community_matter", matter["_id"], {
            "status": status,
        })
    except Exception:
        pass
    return _format_matter(updated, uid)
