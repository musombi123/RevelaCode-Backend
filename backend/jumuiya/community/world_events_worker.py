from __future__ import annotations

import calendar
import hashlib
import html
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests

from backend.jumuiya.core.database import collection
from backend.jumuiya.community.world_events_routes import (
    EVENTS,
    SOURCES,
    SOURCE_REGISTRY,
)

logger = logging.getLogger("revelacode.world_events")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)

USER_AGENT = "RevelaCodeWorldDesk/1.0 (+https://revelacode.co.ke)"
REQUEST_TIMEOUT = 18
MAX_ITEMS_PER_SOURCE = 30
RETENTION_DAYS = 15
MAX_SUMMARY_CHARS = 560

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "politics": ("election", "president", "parliament", "government", "minister", "court", "senate", "policy", "governance", "political"),
    "economy": ("economy", "inflation", "cost of living", "jobs", "employment", "interest rate", "currency", "trade", "business", "budget", "tax", "market"),
    "education": ("school", "university", "education", "student", "teacher", "learning", "exam", "curriculum", "scholarship"),
    "agriculture": ("agriculture", "farmer", "farming", "crop", "harvest", "livestock", "food security", "fertilizer", "drought"),
    "health": ("health", "hospital", "patient", "disease", "outbreak", "vaccine", "medicine", "medical", "public health"),
    "technology": ("technology", "artificial intelligence", "ai ", "software", "cyber", "digital", "internet", "startup", "innovation", "robot"),
    "science": ("science", "research", "scientist", "space", "discovery", "study finds", "climate model"),
    "climate": ("climate", "flood", "flooding", "drought", "heatwave", "wildfire", "storm", "rainfall", "weather"),
    "environment": ("environment", "conservation", "wildlife", "forest", "pollution", "biodiversity", "ocean"),
    "humanitarian": ("humanitarian", "displaced", "refugee", "aid", "relief", "food assistance", "volunteer", "donation"),
    "security": ("security", "conflict", "war ", "attack", "terror", "violence", "military", "ceasefire", "peace talks"),
    "faith_society": ("religious liberty", "church", "faith community", "religion", "interfaith", "worship", "religious"),
    "sports": ("football", "soccer", "athletics", "sports", "olympic", "tournament", "rugby", "cricket"),
    "culture": ("culture", "music", "film", "arts", "heritage", "festival", "literature"),
    "public_safety": ("road accident", "accident", "fire", "emergency", "rescue", "public safety", "missing persons"),
}

KENYA_HINTS = (
    "kenya", "nairobi", "mombasa", "kisumu", "nakuru", "eldoret",
    "nyeri", "machakos", "garissa", "kakamega", "kilifi", "kwale",
    "bungoma", "busia", "siaya", "homabay", "migori", "kitui",
    "meru", "embu", "tharaka", "lamu", "taita taveta", "turkana",
    "west pokot", "mandera", "wajir", "marsabit", "isiolo",
)
AFRICA_HINTS = (
    "africa", "uganda", "tanzania", "rwanda", "burundi", "somalia",
    "ethiopia", "sudan", "south sudan", "eritrea", "djibouti",
    "nigeria", "ghana", "south africa", "senegal", "zambia", "zimbabwe",
    "malawi", "mozambique", "botswana", "namibia", "cameroon", "chad",
    "niger", "mali", "democratic republic of the congo", "dr congo",
    "ivory coast", "côte d’ivoire", "liberia", "sierra leone",
)

LESSONS = {
    "politics": (
        "Public decisions affect real lives. Read beyond campaign language, compare credible reporting, and judge decisions by evidence, accountability and their effect on people.",
        "What evidence supports the claims, who is affected, and what lawful civic action is available?",
    ),
    "economy": (
        "Economic headlines become household realities through prices, jobs and access to services. Avoid reacting to one headline; verify the figures and plan with reliable information.",
        "How could this development affect household costs, livelihoods or local businesses?",
    ),
    "education": (
        "Education news shapes opportunity for learners, families and future workers. Check official guidance before making school or career decisions, and share verified information with others.",
        "Which learners or communities may be affected, and what practical support would help?",
    ),
    "agriculture": (
        "Agriculture connects food security, household income and climate resilience. Local conditions matter, so compare national reports with county guidance before changing farm decisions.",
        "What could farmers, consumers or local institutions do with this information?",
    ),
    "health": (
        "Health information can influence urgent personal decisions. Use recognised health authorities and qualified professionals; do not treat a headline as a diagnosis or treatment instruction.",
        "Which official health guidance should people check before acting?",
    ),
    "technology": (
        "Technology changes work, privacy, education and access to services. Progress is most valuable when people understand its benefits, risks and responsibilities.",
        "Who benefits, what risks should be managed, and what skills will people need?",
    ),
    "science": (
        "Scientific findings are strongest when methods, evidence and limitations are examined. Distinguish a peer-reviewed result from an early claim or an exaggerated headline.",
        "What does the evidence actually show, and what remains uncertain?",
    ),
    "climate": (
        "Weather and climate events can affect homes, farms, transport and public services. Preparedness works best when communities follow local alerts and help vulnerable neighbours.",
        "What practical preparation or community support is useful in the affected area?",
    ),
    "environment": (
        "Environmental decisions influence public health, livelihoods and future generations. Look at both ecological evidence and the communities whose lives depend on the affected land or water.",
        "What can residents, businesses or institutions do to reduce harm?",
    ),
    "humanitarian": (
        "Humanitarian crises involve people, not just statistics. Reliable information, dignity and accountable aid matter; verify relief channels before donating or sharing requests.",
        "What safe, verified way exists to support affected people?",
    ),
    "security": (
        "Security developments can carry serious consequences and misinformation risk. Separate confirmed reporting from speculation, avoid amplifying unverified images, and prioritise credible safety guidance.",
        "What is confirmed, what is still uncertain, and which official safety updates matter?",
    ),
    "faith_society": (
        "Faith and society stories invite careful listening across communities. Respect people, distinguish reported facts from belief or opinion, and let convictions be expressed through service and integrity.",
        "How can people of different backgrounds respond with dignity, fairness and compassion?",
    ),
    "sports": (
        "Sport can reveal discipline, teamwork, leadership and the power of shared identity. Celebrate achievement while respecting the people and communities behind the result.",
        "What can this achievement teach about preparation, teamwork or resilience?",
    ),
    "culture": (
        "Culture preserves identity and creates space for people to understand one another. Approach traditions and creative work with curiosity, context and respect.",
        "Whose story is being told, and what can the wider community learn from it?",
    ),
    "public_safety": (
        "Public safety stories may require timely, practical decisions. Confirm advice with relevant authorities, protect affected people's privacy and avoid spreading unverified details.",
        "What verified action could reduce risk or help people nearby?",
    ),
    "general": (
        "A single report is a starting point, not the whole story. Check the original source, compare independent reporting and consider how the development affects people locally.",
        "What is confirmed, what is missing, and what constructive response is possible?",
    ),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def clean_text(value: Any, limit: int = MAX_SUMMARY_CHARS) -> str:
    raw = html.unescape(str(value or ""))
    raw = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if len(raw) > limit:
        raw = raw[: limit - 1].rsplit(" ", 1)[0].rstrip() + "…"
    return raw


def safe_http_url(value: Any) -> str:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    return raw if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def event_published_at(entry: Any) -> datetime:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key) if hasattr(entry, "get") else None
        if value:
            try:
                return datetime.fromtimestamp(calendar.timegm(value), timezone.utc)
            except (TypeError, ValueError, OverflowError):
                pass
    return utc_now()


def event_image(entry: Any) -> str:
    for field in ("media_thumbnail", "media_content", "links"):
        values = entry.get(field, []) if hasattr(entry, "get") else []
        if isinstance(values, dict):
            values = [values]
        for value in values or []:
            candidate = safe_http_url(value.get("url") or value.get("href"))
            media_type = str(value.get("type") or "").lower()
            if candidate and (media_type.startswith("image/") or "thumbnail" in str(value.get("medium") or "").lower() or field != "links"):
                return candidate
    return ""


def get_youtube_video_id(entry: Any, url: str) -> str:
    value = str(entry.get("yt_videoid") or "").strip()
    if value and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", value):
        return value
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,20})", url)
    return match.group(1) if match else ""


def classify_topics(text: str) -> list[str]:
    lowered = text.lower()
    found = [topic for topic, keywords in TOPIC_KEYWORDS.items() if any(keyword in lowered for keyword in keywords)]
    return found[:5] or ["general"]


def classify_region(text: str, source_region: str) -> str:
    lowered = text.lower()
    if any(hint in lowered for hint in KENYA_HINTS):
        return "kenya"
    if any(hint in lowered for hint in AFRICA_HINTS):
        return "africa"
    if source_region in {"kenya", "africa"}:
        return source_region
    return "world"


def editorial_context(categories: list[str]) -> tuple[str, str, str, str]:
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
        "humanitarian": "Humanitarian developments concern people's safety, dignity, basic needs and the ability of communities to recover.",
        "security": "Security developments can affect civilian safety, stability, services and regional relationships.",
        "faith_society": "Faith and social developments influence community relationships, freedom of belief, identity and public life.",
        "sports": "Sport reaches beyond results: it can influence national identity, youth opportunity and community morale.",
        "culture": "Cultural developments shape identity, heritage, creative expression and how communities understand one another.",
        "public_safety": "Public-safety developments can affect immediate risks, emergency response and community resilience.",
        "general": "The event may have consequences for people, institutions or communities beyond the immediate headline.",
    }.get(category, "The event may have consequences for people, institutions or communities beyond the immediate headline.")
    faith = (
        "Optional SDA reflection: consider how a thoughtful response can uphold justice, mercy and humility (Micah 6:8) and serve neighbours (Matthew 5:16). "
        "This reflection is not a claim that the event fulfils a prophecy."
    )
    return why, lesson, question, faith


def normalize_entry(entry: Any, source: dict[str, Any], fetched_at: datetime) -> dict[str, Any] | None:
    title = clean_text(entry.get("title"), 300)
    url = safe_http_url(entry.get("link"))
    if not title or not url:
        return None

    video_id = get_youtube_video_id(entry, url) if source["kind"] == "youtube_atom" else ""
    if video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"

    published = event_published_at(entry)
    summary = clean_text(entry.get("summary") or entry.get("description") or "")
    if not summary:
        summary = "Open the original publisher report for the full details."

    media_type = "video" if video_id or source["media_type"] == "video" else "article"
    image = event_image(entry)
    if video_id and not image:
        image = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

    combined = f"{title} {summary}"
    categories = classify_topics(combined)
    region = classify_region(combined, source["region"])
    why, lesson, question, faith = editorial_context(categories)

    event_id = hashlib.sha256(url.rstrip("/").lower().encode("utf-8")).hexdigest()[:32]
    parsed_host = urlparse(url).netloc.lower()
    return {
        "event_id": event_id,
        "headline": title,
        "title": title,
        "description": summary,
        "summary": summary,
        "url": url,
        "urlToImage": image,
        "publishedAt": published,
        "source": source["name"],
        "source_id": source["id"],
        "source_domain": parsed_host,
        "source_url": source["url"],
        "region": region,
        "categories": categories,
        "media_type": media_type,
        "video_url": url if media_type == "video" else "",
        "youtube_video_id": video_id,
        "why_it_matters": why,
        "life_lesson": lesson,
        "reflection_question": question,
        "faith_reflection": faith,
        "status": "published",
        "fetched_at": fetched_at,
        "last_seen_at": fetched_at,
        "expires_at": fetched_at + timedelta(days=RETENTION_DAYS),
    }


def ensure_indexes() -> None:
    events = collection(EVENTS)
    sources = collection(SOURCES)
    activity = collection("jumuiya_world_event_activity")
    preferences = collection("jumuiya_world_event_preferences")

    events.create_index("event_id", unique=True, name="uq_world_events_event_id")
    events.create_index([("status", 1), ("publishedAt", -1)], name="ix_world_events_status_published")
    events.create_index([("region", 1), ("publishedAt", -1)], name="ix_world_events_region_published")
    events.create_index("expires_at", expireAfterSeconds=0, name="ttl_world_events_expiry")
    sources.create_index("source_id", unique=True, name="uq_world_event_source_id")
    activity.create_index([("user_id", 1), ("updated_at", -1)], name="ix_world_event_activity_user_updated")
    activity.create_index([("user_id", 1), ("event_id", 1)], unique=True, name="uq_world_event_activity_user_event")
    preferences.create_index("user_id", unique=True, name="uq_world_event_preferences_user")


def fetch_source(source: dict[str, Any], fetched_at: datetime) -> tuple[int, datetime | None, str]:
    response = requests.get(
        source["url"],
        headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml, */*"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    entries = list(parsed.entries or [])[:MAX_ITEMS_PER_SOURCE]
    if getattr(parsed, "bozo", False) and not entries:
        raise ValueError("Feed response could not be parsed.")

    rows = [normalize_entry(entry, source, fetched_at) for entry in entries]
    rows = [row for row in rows if row]
    if rows:
        collection(EVENTS).bulk_write(
            [
                __import__("pymongo").ReplaceOne(
                    {"event_id": row["event_id"]},
                    row,
                    upsert=True,
                )
                for row in rows
            ],
            ordered=False,
        )

    latest = max((row["publishedAt"] for row in rows), default=None)
    return len(rows), latest, "healthy" if response.status_code == 200 and not getattr(parsed, "bozo", False) else "degraded"


def run() -> int:
    ensure_indexes()
    checked_at = utc_now()
    successful = 0
    total_items = 0

    for source in SOURCE_REGISTRY:
        count = 0
        latest = None
        status = "error"
        error = ""
        last_success = None
        try:
            count, latest, status = fetch_source(source, checked_at)
            successful += 1
            total_items += count
            if status == "healthy":
                last_success = checked_at
            else:
                error = "Feed parsed with a warning; inspect the publisher response."
            logger.info(
                "source=%s status=%s items=%s latest=%s",
                source["id"], status, count, latest.isoformat() if latest else "none",
            )
        except requests.RequestException as exc:
            error = f"HTTP/network error: {type(exc).__name__}"
            logger.warning("source=%s failed: %s", source["id"], error)
        except Exception as exc:
            error = f"Feed processing error: {type(exc).__name__}"
            logger.exception("source=%s failed", source["id"])

        source_doc = {
            "source_id": source["id"],
            "name": source["name"],
            "region": source["region"],
            "kind": source["kind"],
            "media_type": source["media_type"],
            "status": status,
            "last_checked_at": checked_at,
            "last_success_at": last_success,
            "last_item_at": latest,
            "items_last_run": count,
            "last_error": error,
            "updated_at": checked_at,
        }
        collection(SOURCES).update_one(
            {"source_id": source["id"]},
            {"$set": source_doc, "$setOnInsert": {"created_at": checked_at}},
            upsert=True,
        )

    collection(EVENTS).update_many(
        {"expires_at": {"$lt": checked_at}, "status": "published"},
        {"$set": {"status": "expired"}},
    )

    logger.info(
        "World Events refresh complete: sources_ok=%s/%s items_seen=%s",
        successful, len(SOURCE_REGISTRY), total_items,
    )
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(run())
