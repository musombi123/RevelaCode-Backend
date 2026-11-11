from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from flask import Blueprint, g, request

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import ok
from backend.jumuiya.core.errors import APIError


world_events_bp = Blueprint("jumuiya_world_events", __name__)

EVENTS = "jumuiya_world_events"
SOURCES = "jumuiya_world_event_sources"
PREFERENCES = "jumuiya_world_event_preferences"
ACTIVITY = "jumuiya_world_event_activity"

PUBLISHER = {
    "id": "revelacode:official-world-desk",
    "name": "RevelaCode",
    "label": "Official World Desk",
    "kind": "platform_editorial",
}

ALLOWED_TOPICS = {
    "politics", "economy", "education", "agriculture", "health",
    "technology", "science", "climate", "environment", "humanitarian",
    "security", "faith_society", "sports", "culture", "public_safety",
}
ALLOWED_REGIONS = {"kenya", "africa", "world"}

# Publisher feeds are public feeds. They are polled by the scheduled worker;
# user requests never trigger upstream fetches.
SOURCE_REGISTRY = [
    {
        "id": "standard_kenya",
        "name": "The Standard — Kenya",
        "url": "https://www.standardmedia.co.ke/rss/kenya.php",
        "region": "kenya",
        "kind": "rss",
        "media_type": "article",
    },
    {
        "id": "standard_world",
        "name": "The Standard — World",
        "url": "https://www.standardmedia.co.ke/rss/world.php",
        "region": "world",
        "kind": "rss",
        "media_type": "article",
    },
    {
        "id": "standard_ktn_videos",
        "name": "KTN Videos",
        "url": "https://www.standardmedia.co.ke/rss/ktnvideos.php",
        "region": "kenya",
        "kind": "rss",
        "media_type": "video",
    },
    {
        "id": "allafrica",
        "name": "AllAfrica",
        "url": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
        "region": "africa",
        "kind": "rss",
        "media_type": "article",
    },
    {
        "id": "bbc_world",
        "name": "BBC News — World",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "region": "world",
        "kind": "rss",
        "media_type": "article",
    },
    {
        "id": "aljazeera_world",
        "name": "Al Jazeera English",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "region": "world",
        "kind": "rss",
        "media_type": "article",
    },
    {
        "id": "dw_world",
        "name": "DW — World",
        "url": "https://www.dw.com/en/top-stories/rss",
        "region": "world",
        "kind": "rss",
        "media_type": "article",
    },
    {
        "id": "france24_world",
        "name": "France 24 — World",
        "url": "https://www.france24.com/en/rss",
        "region": "world",
        "kind": "rss",
        "media_type": "article",
    },
    {
        "id": "guardian_world",
        "name": "The Guardian — World",
        "url": "https://www.theguardian.com/world/rss",
        "region": "world",
        "kind": "rss",
        "media_type": "article",
    },
    {
        "id": "youtube_bbc_news",
        "name": "BBC News — YouTube",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC16niRr50-MSBwiO3YDb3RA",
        "region": "world",
        "kind": "youtube_atom",
        "media_type": "video",
    },
    {
        "id": "youtube_aljazeera_english",
        "name": "Al Jazeera English — YouTube",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCNye-wNBqNL5ZzHSJj3l8Bg",
        "region": "world",
        "kind": "youtube_atom",
        "media_type": "video",
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public_source(source: dict[str, Any], status: dict[str, Any] | None = None) -> dict[str, Any]:
    status = status or {}
    return {
        "id": source["id"],
        "name": source["name"],
        "region": source["region"],
        "kind": source["kind"],
        "media_type": source["media_type"],
        "status": status.get("status", "pending_first_check"),
        "last_checked_at": _iso(status.get("last_checked_at")),
        "last_success_at": _iso(status.get("last_success_at")),
        "last_item_at": _iso(status.get("last_item_at")),
        "items_last_run": int(status.get("items_last_run") or 0),
        "last_error": status.get("last_error") or "",
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _preference_for(user_id: str) -> dict[str, Any]:
    stored = collection(PREFERENCES).find_one({"user_id": user_id}) or {}
    topics = [value for value in stored.get("topics", []) if value in ALLOWED_TOPICS]
    regions = [value for value in stored.get("regions", []) if value in ALLOWED_REGIONS]
    return {
        "topics": topics,
        "regions": regions or ["kenya", "africa", "world"],
        "updated_at": _iso(stored.get("updated_at")),
        "is_personalized": bool(topics or stored.get("has_activity")),
    }


def _event_card(document: dict[str, Any]) -> dict[str, Any]:
    event = dict(document)
    event_id = str(event.get("event_id") or event.get("_id") or "")
    event.pop("_id", None)
    event["id"] = event_id
    event["publisher"] = PUBLISHER
    event["publishedAt"] = _iso(event.get("publishedAt") or event.get("published_at"))
    event["fetched_at"] = _iso(event.get("fetched_at"))
    event["source_checked_at"] = _iso(event.get("source_checked_at"))
    event["categories"] = event.get("categories") if isinstance(event.get("categories"), list) else ["general"]
    event["why_it_matters"] = str(event.get("why_it_matters") or "")
    event["life_lesson"] = str(event.get("life_lesson") or "")
    event["reflection_question"] = str(event.get("reflection_question") or "")
    event["faith_reflection"] = str(event.get("faith_reflection") or "")
    event["media_type"] = str(event.get("media_type") or "article")
    return event


def _rank_events(documents: list[dict[str, Any]], preference: dict[str, Any], activities: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    topic_set = set(preference.get("topics") or [])
    region_set = set(preference.get("regions") or ALLOWED_REGIONS)
    activity_by_id = {str(item.get("event_id")): item for item in activities}
    now = _now()
    ranked: list[tuple[float, dict[str, Any]]] = []

    for document in documents:
        event_id = str(document.get("event_id") or document.get("_id") or "")
        activity = activity_by_id.get(event_id, {})
        if activity.get("hidden") or activity.get("not_interested"):
            continue

        region = str(document.get("region") or "world").lower()
        if region not in region_set:
            continue

        categories = {
            str(value).lower()
            for value in (document.get("categories") or [])
            if value
        }
        score = 10.0
        if topic_set:
            score += 16.0 * len(categories.intersection(topic_set))
        score += min(8.0, float(activity.get("view_count") or 0) * 0.5)
        if activity.get("saved"):
            score += 8.0
        if region == "kenya":
            score += 3.0
        published = document.get("publishedAt")
        if isinstance(published, datetime):
            published_dt = published
        else:
            try:
                published_dt = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
                if published_dt.tzinfo is None:
                    published_dt = published_dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                published_dt = now - timedelta(days=14)
        age_hours = max(0.0, (now - published_dt).total_seconds() / 3600)
        score += max(0.0, 8.0 - age_hours / 12.0)
        ranked.append((score, document))

    ranked.sort(key=lambda pair: (pair[0], str(pair[1].get("publishedAt") or "")), reverse=True)

    # Preserve a useful Kenya / Africa / World mix so a high-volume publisher
    # cannot occupy the entire first screen.
    buckets: dict[str, list[dict[str, Any]]] = {"kenya": [], "africa": [], "world": []}
    for _, document in ranked:
        region = str(document.get("region") or "world").lower()
        buckets.setdefault(region, []).append(document)

    ordered: list[dict[str, Any]] = []
    active_regions = [region for region in ("kenya", "africa", "world") if region in region_set]
    while len(ordered) < limit and any(buckets.get(region) for region in active_regions):
        for region in active_regions:
            if buckets.get(region) and len(ordered) < limit:
                ordered.append(buckets[region].pop(0))

    if len(ordered) < limit:
        used = {str(item.get("event_id") or item.get("_id")) for item in ordered}
        for _, document in ranked:
            key = str(document.get("event_id") or document.get("_id"))
            if key not in used:
                ordered.append(document)
                used.add(key)
                if len(ordered) >= limit:
                    break

    return [_event_card(document) for document in ordered]


@world_events_bp.get("/feed")
def get_world_events_feed():
    limit = request.args.get("limit", "18")
    try:
        limit = max(1, min(int(limit), 40))
    except (TypeError, ValueError):
        limit = 18

    user = getattr(g, "jumuiya_user", None)
    user_id = str((user or {}).get("id") or (user or {}).get("_id") or (user or {}).get("user_id") or "")
    preference = _preference_for(user_id) if user_id else {"topics": [], "regions": ["kenya", "africa", "world"], "is_personalized": False}
    activities = []
    if user_id:
        activities = list(collection(ACTIVITY).find({"user_id": user_id}, {"_id": 0}).sort("updated_at", -1).limit(200))

    now = _now()
    documents = list(
        collection(EVENTS)
        .find({"status": "published", "$or": [{"expires_at": {"$exists": False}}, {"expires_at": {"$gte": now}}]})
        .sort("publishedAt", -1)
        .limit(250)
    )
    events = _rank_events(documents, preference, activities, limit)

    source_status = {
        item.get("source_id"): item
        for item in collection(SOURCES).find({}, {"_id": 0})
    }
    sources = [_public_source(source, source_status.get(source["id"])) for source in SOURCE_REGISTRY]

    last_updated = max(
        (item.get("fetched_at") for item in documents if isinstance(item.get("fetched_at"), datetime)),
        default=None,
    )

    return ok({
        "publisher": PUBLISHER,
        "data": events,
        "sources": sources,
        "updated_at": _iso(last_updated),
        "preferences": preference,
        "meta": {
            "count": len(events),
            "regions": ["kenya", "africa", "world"],
            "personalized": preference.get("is_personalized", False),
        },
    })


@world_events_bp.get("/sources")
def get_world_event_sources():
    stored = {
        item.get("source_id"): item
        for item in collection(SOURCES).find({}, {"_id": 0})
    }
    return ok({
        "publisher": PUBLISHER,
        "sources": [_public_source(source, stored.get(source["id"])) for source in SOURCE_REGISTRY],
        "checked_at": _iso(max(
            (item.get("last_checked_at") for item in stored.values() if isinstance(item.get("last_checked_at"), datetime)),
            default=None,
        )),
    })


@world_events_bp.get("/preferences")
@require_authenticated
def get_world_event_preferences():
    return ok({"preferences": _preference_for(str(current_user_id()))})


@world_events_bp.put("/preferences")
@require_authenticated
def put_world_event_preferences():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise APIError("A JSON preferences object is required.", 400, "invalid_payload")

    topics = payload.get("topics", [])
    regions = payload.get("regions", ["kenya", "africa", "world"])
    if not isinstance(topics, list) or not isinstance(regions, list):
        raise APIError("topics and regions must be arrays.", 422, "invalid_preferences")

    normalized_topics = list(dict.fromkeys(str(value).strip().lower() for value in topics if str(value).strip()))
    normalized_regions = list(dict.fromkeys(str(value).strip().lower() for value in regions if str(value).strip()))
    if any(value not in ALLOWED_TOPICS for value in normalized_topics):
        raise APIError("One or more selected topics are not supported.", 422, "invalid_topic")
    if any(value not in ALLOWED_REGIONS for value in normalized_regions):
        raise APIError("One or more selected regions are not supported.", 422, "invalid_region")
    if not normalized_regions:
        normalized_regions = ["kenya", "africa", "world"]

    user_id = str(current_user_id())
    now = _now()
    collection(PREFERENCES).update_one(
        {"user_id": user_id},
        {
            "$set": {"topics": normalized_topics, "regions": normalized_regions, "updated_at": now},
            "$setOnInsert": {"user_id": user_id, "created_at": now},
        },
        upsert=True,
    )
    return ok({"preferences": _preference_for(user_id), "message": "World Events interests saved."})


@world_events_bp.post("/interactions")
@require_authenticated
def record_world_event_interaction():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise APIError("A JSON interaction object is required.", 400, "invalid_payload")

    event_id = str(payload.get("event_id") or "").strip()
    action = str(payload.get("action") or "").strip().lower()
    if not event_id or len(event_id) > 128:
        raise APIError("A valid event_id is required.", 422, "invalid_event_id")
    if action not in {"open", "save", "unsave", "hide", "not_interested"}:
        raise APIError("Unsupported World Events interaction.", 422, "invalid_action")

    user_id = str(current_user_id())
    event = collection(EVENTS).find_one({"event_id": event_id}, {"_id": 0, "event_id": 1, "categories": 1, "region": 1})
    if not event:
        raise APIError("This event is no longer available.", 404, "event_not_found")

    now = _now()
    update: dict[str, Any] = {
        "$set": {
            "user_id": user_id,
            "event_id": event_id,
            "categories": event.get("categories") or [],
            "region": event.get("region") or "world",
            "updated_at": now,
        },
        "$setOnInsert": {"created_at": now},
    }
    if action == "open":
        update["$inc"] = {"view_count": 1}
        update["$set"]["last_opened_at"] = now
    elif action == "save":
        update["$set"]["saved"] = True
        update["$set"]["hidden"] = False
    elif action == "unsave":
        update["$set"]["saved"] = False
    elif action == "hide":
        update["$set"]["hidden"] = True
    elif action == "not_interested":
        update["$set"]["not_interested"] = True

    collection(ACTIVITY).update_one(
        {"user_id": user_id, "event_id": event_id},
        update,
        upsert=True,
    )
    collection(PREFERENCES).update_one(
        {"user_id": user_id},
        {"$set": {"has_activity": True, "updated_at": now}, "$setOnInsert": {"user_id": user_id, "created_at": now}},
        upsert=True,
    )
    return ok({"event_id": event_id, "action": action, "saved": action == "save"})
