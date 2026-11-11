from __future__ import annotations

import calendar
import hashlib
import html
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests
from flask import Blueprint, request

from backend.jumuiya.core.responses import ok

world_events_bp = Blueprint("jumuiya_world_events", __name__)
logger = logging.getLogger("revelacode.world_events")

# News is NEVER persisted. This bounded in-process cache is discarded on
# worker restart, replaced on refresh, and age-pruned on every response.
CACHE_TTL_SECONDS = 8 * 60
MAX_EVENT_AGE_HOURS = 48
MAX_CACHED_EVENTS = 160
MAX_ITEMS_PER_SOURCE = 22
REQUEST_TIMEOUT_SECONDS = 10
MAX_WORKERS = 8
USER_AGENT = "RevelaCodeWorldDesk/1.0 (+https://revelacode.co.ke)"

PUBLISHER = {
    "id": "revelacode:official-world-desk",
    "name": "RevelaCode",
    "label": "Official World Desk",
    "kind": "platform_editorial",
}

SOURCE_REGISTRY = [
    {"id": "standard_kenya", "name": "The Standard — Kenya", "url": "https://www.standardmedia.co.ke/rss/kenya.php", "region": "kenya", "kind": "rss", "media_type": "article"},
    {"id": "standard_world", "name": "The Standard — World", "url": "https://www.standardmedia.co.ke/rss/world.php", "region": "world", "kind": "rss", "media_type": "article"},
    {"id": "standard_politics", "name": "The Standard — Politics", "url": "https://www.standardmedia.co.ke/rss/politics.php", "region": "kenya", "kind": "rss", "media_type": "article"},
    {"id": "standard_business", "name": "The Standard — Business", "url": "https://www.standardmedia.co.ke/rss/business.php", "region": "kenya", "kind": "rss", "media_type": "article"},
    {"id": "standard_agriculture", "name": "The Standard — Agriculture", "url": "https://www.standardmedia.co.ke/rss/agriculture.php", "region": "kenya", "kind": "rss", "media_type": "article"},
    {"id": "standard_ktn_videos", "name": "KTN Videos", "url": "https://www.standardmedia.co.ke/rss/ktnvideos.php", "region": "kenya", "kind": "rss", "media_type": "video"},
    {"id": "allafrica", "name": "AllAfrica", "url": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf", "region": "africa", "kind": "rss", "media_type": "article"},
    {"id": "bbc_world", "name": "BBC News — World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "region": "world", "kind": "rss", "media_type": "article"},
    {"id": "aljazeera_world", "name": "Al Jazeera English", "url": "https://www.aljazeera.com/xml/rss/all.xml", "region": "world", "kind": "rss", "media_type": "article"},
    {"id": "dw_world", "name": "DW — World", "url": "https://rss.dw.com/xml/rss-en-all", "region": "world", "kind": "rss", "media_type": "article"},
    {"id": "france24_world", "name": "France 24", "url": "https://www.france24.com/en/rss", "region": "world", "kind": "rss", "media_type": "article"},
    {"id": "guardian_world", "name": "The Guardian — World", "url": "https://www.theguardian.com/world/rss", "region": "world", "kind": "rss", "media_type": "article"},
    {"id": "youtube_bbc_news", "name": "BBC News — YouTube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC16niRr50-MSBwiO3YDb3RA", "region": "world", "kind": "youtube_atom", "media_type": "video"},
    {"id": "youtube_aljazeera_english", "name": "Al Jazeera English — YouTube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCNye-wNBqNL5ZzHSJj3l8Bg", "region": "world", "kind": "youtube_atom", "media_type": "video"},
    {"id": "youtube_ajplus", "name": "AJ+ — YouTube", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCV3Nm3T-XAgVhKH9jT0ViRg", "region": "world", "kind": "youtube_atom", "media_type": "video"},
]

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "politics": ("election", "president", "parliament", "government", "minister", "court", "senate", "policy", "governance", "political"),
    "economy": ("economy", "inflation", "cost of living", "jobs", "employment", "interest rate", "currency", "trade", "business", "budget", "tax", "market"),
    "education": ("school", "university", "education", "student", "teacher", "learning", "exam", "curriculum", "scholarship"),
    "agriculture": ("agriculture", "farmer", "farming", "crop", "harvest", "livestock", "food security", "fertilizer", "drought"),
    "health": ("health", "hospital", "patient", "disease", "outbreak", "vaccine", "medicine", "medical", "public health"),
    "technology": ("technology", "artificial intelligence", "software", "cyber", "digital", "internet", "startup", "innovation", "robot"),
    "science": ("science", "research", "scientist", "space", "discovery", "study finds"),
    "climate": ("climate", "flood", "flooding", "drought", "heatwave", "wildfire", "storm", "rainfall", "weather"),
    "environment": ("environment", "conservation", "wildlife", "forest", "pollution", "biodiversity", "ocean"),
    "humanitarian": ("humanitarian", "displaced", "refugee", "aid", "relief", "volunteer", "donation"),
    "security": ("security", "conflict", "war ", "attack", "terror", "violence", "military", "ceasefire", "peace talks"),
    "faith_society": ("religious liberty", "church", "faith community", "religion", "interfaith", "worship", "religious"),
    "sports": ("football", "soccer", "athletics", "sports", "olympic", "tournament", "rugby", "cricket"),
    "culture": ("culture", "music", "film", "arts", "heritage", "festival", "literature"),
    "public_safety": ("road accident", "accident", "fire", "emergency", "rescue", "public safety"),
}
KENYA_HINTS = ("kenya", "nairobi", "mombasa", "kisumu", "nakuru", "eldoret", "nyeri", "machakos", "garissa", "kakamega", "kilifi", "kwale", "bungoma", "busia", "siaya", "homabay", "migori", "kitui", "meru", "embu", "lamu", "taita taveta", "turkana", "mandera", "wajir", "marsabit", "isiolo")
AFRICA_HINTS = ("africa", "uganda", "tanzania", "rwanda", "burundi", "somalia", "ethiopia", "sudan", "south sudan", "eritrea", "djibouti", "nigeria", "ghana", "south africa", "senegal", "zambia", "zimbabwe", "malawi", "mozambique", "botswana", "namibia", "cameroon", "chad", "niger", "mali", "democratic republic of the congo", "dr congo", "ivory coast", "liberia", "sierra leone")

LESSONS = {
    "politics": ("Public decisions affect real lives. Read beyond campaign language, compare credible reporting, and judge decisions by evidence, accountability and their effect on people.", "What evidence supports the claims, who is affected, and what lawful civic action is available?"),
    "economy": ("Economic headlines become household realities through prices, jobs and access to services. Verify the figures before reacting, and plan using reliable information.", "How could this development affect household costs, livelihoods or local businesses?"),
    "education": ("Education news shapes opportunity for learners, families and future workers. Check official guidance before making school or career decisions, and share verified information.", "Which learners or communities may be affected, and what practical support would help?"),
    "agriculture": ("Agriculture connects food security, household income and climate resilience. Local conditions matter, so compare national reports with county guidance before changing farm decisions.", "What could farmers, consumers or local institutions do with this information?"),
    "health": ("Health information can influence urgent personal decisions. Use recognised health authorities and qualified professionals; a headline is not a diagnosis or treatment instruction.", "Which official health guidance should people check before acting?"),
    "technology": ("Technology changes work, privacy, education and access to services. Progress is most valuable when people understand its benefits, risks and responsibilities.", "Who benefits, what risks should be managed, and what skills will people need?"),
    "science": ("Scientific findings are strongest when methods, evidence and limitations are examined. Distinguish a peer-reviewed result from an early claim or exaggerated headline.", "What does the evidence actually show, and what remains uncertain?"),
    "climate": ("Weather and climate events can affect homes, farms, transport and public services. Preparedness works best when communities follow local alerts and help vulnerable neighbours.", "What practical preparation or community support is useful in the affected area?"),
    "environment": ("Environmental decisions influence public health, livelihoods and future generations. Consider both ecological evidence and the communities whose lives depend on the affected land or water.", "What can residents, businesses or institutions do to reduce harm?"),
    "humanitarian": ("Humanitarian crises involve people, not just statistics. Reliable information, dignity and accountable aid matter; verify relief channels before donating or sharing requests.", "What safe, verified way exists to support affected people?"),
    "security": ("Security developments carry serious consequences and misinformation risk. Separate confirmed reporting from speculation, avoid unverified images, and prioritise credible safety guidance.", "What is confirmed, what is still uncertain, and which official safety updates matter?"),
    "faith_society": ("Faith and society stories invite careful listening across communities. Respect people, distinguish reported facts from belief or opinion, and let convictions be expressed through service and integrity.", "How can people of different backgrounds respond with dignity, fairness and compassion?"),
    "sports": ("Sport can reveal discipline, teamwork, leadership and shared identity. Celebrate achievement while respecting the people and communities behind the result.", "What can this achievement teach about preparation, teamwork or resilience?"),
    "culture": ("Culture preserves identity and creates space for people to understand one another. Approach traditions and creative work with curiosity, context and respect.", "Whose story is being told, and what can the wider community learn from it?"),
    "public_safety": ("Public-safety stories may require timely, practical decisions. Confirm advice with relevant authorities, protect affected people's privacy and avoid unverified details.", "What verified action could reduce risk or help people nearby?"),
    "general": ("A single report is a starting point, not the whole story. Check the original source, compare independent reporting and consider how the development affects people locally.", "What is confirmed, what is missing, and what constructive response is possible?"),
}

_CACHE_LOCK = threading.RLock()
_CACHE: dict[str, Any] = {"refreshed_at": 0.0, "events": [], "sources": {}, "refreshing": False}


def _clean(value: Any, limit: int = 560) -> str:
    raw = html.unescape(str(value or ""))
    raw = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw if len(raw) <= limit else raw[: limit - 1].rsplit(" ", 1)[0].rstrip() + "…"


def _safe_url(value: Any) -> str:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    return raw if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _published(entry: Any) -> datetime:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key) if hasattr(entry, "get") else None
        if value:
            try:
                return datetime.fromtimestamp(calendar.timegm(value), timezone.utc)
            except (TypeError, ValueError, OverflowError):
                pass
    return datetime.now(timezone.utc)


def _topics(text: str) -> list[str]:
    lowered = text.lower()
    found = [topic for topic, words in TOPIC_KEYWORDS.items() if any(word in lowered for word in words)]
    return found[:5] or ["general"]


def _region(text: str, source_region: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in KENYA_HINTS):
        return "kenya"
    if any(word in lowered for word in AFRICA_HINTS):
        return "africa"
    return source_region if source_region in {"kenya", "africa"} else "world"


def _youtube_id(entry: Any, url: str) -> str:
    candidate = str(entry.get("yt_videoid") or "").strip()
    if candidate and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", candidate):
        return candidate
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,20})", url)
    return match.group(1) if match else ""


def _image(entry: Any, video_id: str) -> str:
    for field in ("media_thumbnail", "media_content"):
        values = entry.get(field, []) if hasattr(entry, "get") else []
        if isinstance(values, dict):
            values = [values]
        for item in values or []:
            candidate = _safe_url(item.get("url"))
            if candidate:
                return candidate
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else ""


def _editorial(categories: list[str]) -> tuple[str, str, str, str]:
    category = next((item for item in categories if item in LESSONS), "general")
    lesson, question = LESSONS[category]
    why = {
        "politics": "Governance, public accountability and rights can shape everyday life far beyond the political arena.",
        "economy": "Changes in markets, prices and policy can affect household budgets, employment and the cost of running a business.",
        "education": "Education policy and school developments influence access, quality, learner wellbeing and future opportunity.",
        "agriculture": "Food systems link farmers, markets, climate conditions and the cost of living.",
        "health": "Public-health developments can affect families, health services and community preparedness.",
        "technology": "Technology decisions can change how people work, learn, communicate and protect personal information.",
        "science": "Scientific developments can influence future technologies, public decisions and how society understands the world.",
        "climate": "Climate and weather developments can affect safety, infrastructure, farming and livelihoods.",
        "environment": "Environmental change can affect natural resources, public health and long-term economic resilience.",
        "humanitarian": "Humanitarian developments concern people's safety, dignity, basic needs and ability to recover.",
        "security": "Security developments can affect civilian safety, stability, services and regional relationships.",
        "faith_society": "Faith and social developments influence community relationships, freedom of belief, identity and public life.",
        "sports": "Sport reaches beyond results: it can influence national identity, youth opportunity and community morale.",
        "culture": "Cultural developments shape identity, heritage, creative expression and how communities understand one another.",
        "public_safety": "Public-safety developments can affect immediate risks, emergency response and community resilience.",
    }.get(category, "The event may have consequences for people, institutions or communities beyond the immediate headline.")
    faith = "Optional SDA reflection: consider justice, mercy and humility (Micah 6:8), and serving neighbours (Matthew 5:16). This reflection is not a claim that the event fulfils prophecy."
    return why, lesson, question, faith


def _normalize_entry(entry: Any, source: dict[str, Any]) -> dict[str, Any] | None:
    title = _clean(entry.get("title"), 300)
    url = _safe_url(entry.get("link"))
    if not title or not url:
        return None
    video_id = _youtube_id(entry, url) if source["kind"] == "youtube_atom" else ""
    if video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"
    published = _published(entry)
    summary = _clean(entry.get("summary") or entry.get("description") or "")
    categories = _topics(f"{title} {summary}")
    region = _region(f"{title} {summary}", source["region"])
    why, lesson, question, faith = _editorial(categories)
    media_type = "video" if video_id or source["media_type"] == "video" else "article"
    event_id = hashlib.sha256(url.rstrip("/").lower().encode("utf-8")).hexdigest()[:32]
    return {
        "id": event_id, "headline": title, "title": title,
        "description": summary or "Open the original publisher report for the full details.",
        "url": url, "urlToImage": _image(entry, video_id),
        "publishedAt": published.isoformat(), "source": source["name"],
        "source_id": source["id"], "source_domain": urlparse(url).netloc.lower(),
        "region": region, "categories": categories, "media_type": media_type,
        "video_url": url if media_type == "video" else "",
        "youtube_video_id": video_id, "why_it_matters": why,
        "life_lesson": lesson, "reflection_question": question,
        "faith_reflection": faith,
    }


def _fetch_one(source: dict[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    checked = datetime.now(timezone.utc)
    try:
        response = requests.get(
            source["url"],
            headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml, */*"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        entries = list(parsed.entries or [])[:MAX_ITEMS_PER_SOURCE]
        if getattr(parsed, "bozo", False) and not entries:
            raise ValueError("Feed could not be parsed")
        events = [item for item in (_normalize_entry(entry, source) for entry in entries) if item]
        return source["id"], events, {
            "id": source["id"], "name": source["name"], "region": source["region"],
            "kind": source["kind"], "media_type": source["media_type"],
            "status": "healthy" if not getattr(parsed, "bozo", False) else "degraded",
            "last_checked_at": checked.isoformat(), "items_last_check": len(events), "error": "",
        }
    except Exception as exc:
        logger.warning("World Events feed %s unavailable (%s)", source["id"], type(exc).__name__)
        return source["id"], [], {
            "id": source["id"], "name": source["name"], "region": source["region"],
            "kind": source["kind"], "media_type": source["media_type"],
            "status": "unavailable", "last_checked_at": checked.isoformat(),
            "items_last_check": 0, "error": type(exc).__name__,
        }


def _prune(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_EVENT_AGE_HOURS)
    kept = []
    for event in events:
        try:
            published = datetime.fromisoformat(str(event.get("publishedAt") or "").replace("Z", "+00:00"))
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if published >= cutoff:
            kept.append(event)
    kept.sort(key=lambda item: item.get("publishedAt") or "", reverse=True)
    return kept[:MAX_CACHED_EVENTS]


def refresh_cache(force: bool = False) -> None:
    now = time.monotonic()
    with _CACHE_LOCK:
        if not force and now - float(_CACHE["refreshed_at"] or 0) < CACHE_TTL_SECONDS:
            return
        if _CACHE["refreshing"]:
            return
        _CACHE["refreshing"] = True
    try:
        events_by_id: dict[str, dict[str, Any]] = {}
        statuses: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(_fetch_one, source) for source in SOURCE_REGISTRY]
            for future in as_completed(futures):
                source_id, events, status = future.result()
                statuses[source_id] = status
                for event in events:
                    events_by_id[event["id"]] = event
        fresh = _prune(list(events_by_id.values()))
        with _CACHE_LOCK:
            # Replace, rather than append: removed/expired publisher items disappear.
            if fresh or not _CACHE["events"]:
                _CACHE["events"] = fresh
            else:
                _CACHE["events"] = _prune(_CACHE["events"])
            _CACHE["sources"] = statuses
            _CACHE["refreshed_at"] = time.monotonic()
    finally:
        with _CACHE_LOCK:
            _CACHE["refreshing"] = False


def _rank(events: list[dict[str, Any]], topics: set[str], regions: set[str], limit: int) -> list[dict[str, Any]]:
    ranked = []
    for event in _prune(events):
        region = str(event.get("region") or "world").lower()
        if region not in regions:
            continue
        matches = len(topics.intersection(event.get("categories") or []))
        try:
            published = datetime.fromisoformat(str(event.get("publishedAt") or "").replace("Z", "+00:00"))
            age_hours = max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600)
        except (TypeError, ValueError):
            age_hours = 72
        score = 12 + matches * 18 + max(0, 8 - age_hours / 8)
        ranked.append((score, event))
    ranked.sort(key=lambda pair: (pair[0], pair[1].get("publishedAt") or ""), reverse=True)

    by_region: dict[str, list[dict[str, Any]]] = {"kenya": [], "africa": [], "world": []}
    for _, event in ranked:
        by_region.setdefault(str(event.get("region") or "world"), []).append(event)
    result = []
    for region in ("kenya", "africa", "world"):
        if region in regions and by_region.get(region):
            result.append(by_region[region].pop(0))
    seen = {event["id"] for event in result}
    for _, event in ranked:
        if len(result) >= limit:
            break
        if event["id"] not in seen:
            result.append(event)
            seen.add(event["id"])
    return result[:limit]


@world_events_bp.get("/feed")
def get_world_events_feed():
    refresh_cache()
    limit = request.args.get("limit", "18")
    try:
        limit = max(1, min(int(limit), 40))
    except (TypeError, ValueError):
        limit = 18
    raw_regions = request.args.getlist("region") or ["kenya", "africa", "world"]
    regions = {value.strip().lower() for value in raw_regions if value.strip()} & {"kenya", "africa", "world"}
    regions = regions or {"kenya", "africa", "world"}
    topics = {value.strip().lower() for value in request.args.getlist("topic") if value.strip()} & set(TOPIC_KEYWORDS)
    with _CACHE_LOCK:
        events = list(_CACHE["events"])
        sources = list(_CACHE["sources"].values())
        refreshed_at = float(_CACHE["refreshed_at"] or 0)
    return ok({
        "publisher": PUBLISHER,
        "data": _rank(events, topics, regions, limit),
        "sources": sources,
        "updated_at": datetime.now(timezone.utc).isoformat() if refreshed_at else None,
        "meta": {"count": len(events), "regions": ["kenya", "africa", "world"], "personalized": bool(topics)},
        "storage": "ephemeral_memory_only",
        "retention_hours": MAX_EVENT_AGE_HOURS,
    })


@world_events_bp.get("/sources")
def get_world_event_sources():
    refresh_cache()
    with _CACHE_LOCK:
        sources = dict(_CACHE["sources"])
    return ok({
        "publisher": PUBLISHER,
        "sources": [sources.get(source["id"], {
            "id": source["id"], "name": source["name"], "region": source["region"],
            "kind": source["kind"], "media_type": source["media_type"],
            "status": "pending_first_check", "items_last_check": 0,
        }) for source in SOURCE_REGISTRY],
        "storage": "ephemeral_memory_only",
    })


@world_events_bp.get("/health")
def world_events_health():
    with _CACHE_LOCK:
        source_rows = list(_CACHE["sources"].values())
        count = len(_prune(_CACHE["events"]))
    healthy = sum(1 for item in source_rows if item.get("status") == "healthy")
    return ok({
        "status": "ok",
        "storage": "ephemeral_memory_only",
        "cached_items": count,
        "sources_checked": len(source_rows),
        "sources_healthy": healthy,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "automatic_expiry_hours": MAX_EVENT_AGE_HOURS,
    })
