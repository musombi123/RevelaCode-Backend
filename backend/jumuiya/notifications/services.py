from bson import ObjectId
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.notifications.models import notification_document


def notify(user_id, data):
    if user_id is None or not str(user_id).strip():
        return None
    payload = dict(data or {})
    payload["title"] = str(payload.get("title") or "Jumuiya update").strip()[:160]
    payload["message"] = str(payload.get("message") or payload.get("text") or "").strip()[:2000]
    payload["type"] = str(payload.get("type") or "info").strip()[:80]
    payload["data"] = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    doc = notification_document(user_id, payload)
    result = collection("jumuiya_notifications").insert_one(doc)
    doc["_id"] = result.inserted_id
    return _ser(doc)


def list_notifications(user_id, limit=30):
    try:
        limit = min(max(int(limit), 1), 100)
    except (TypeError, ValueError):
        limit = 30
    documents = (
        collection("jumuiya_notifications")
        .find({"user_id": str(user_id)})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [_ser(item) for item in documents]


def mark_read(user_id, notification_id):
    try:
        oid = ObjectId(notification_id)
    except Exception:
        oid = notification_id
    document = collection("jumuiya_notifications").find_one_and_update(
        {"_id": oid, "user_id": str(user_id)},
        {"$set": {"read": True}},
    )
    if not document:
        # Some drivers return the previous document, so confirm existence before
        # treating this as a successful user-scoped mutation.
        document = collection("jumuiya_notifications").find_one(
            {"_id": oid, "user_id": str(user_id)}
        )
    if not document:
        raise APIError("Notification not found.", 404, "notification_not_found")
    return {"id": str(document.get("_id") or notification_id), "read": True}


def mark_all_read(user_id):
    result = collection("jumuiya_notifications").update_many(
        {"user_id": str(user_id), "read": {"$ne": True}},
        {"$set": {"read": True}},
    )
    return {"updated": int(getattr(result, "modified_count", 0) or 0), "read": True}


def _ser(doc):
    out = dict(doc)
    out["id"] = str(out.pop("_id")) if "_id" in out else str(out.get("id") or "")
    for key, value in list(out.items()):
        if hasattr(value, "isoformat"):
            out[key] = value.isoformat()
    return out
