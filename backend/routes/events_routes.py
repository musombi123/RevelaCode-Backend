from flask import Blueprint, jsonify
from datetime import datetime, timedelta
import os
import json
import re

events_bp = Blueprint("events", __name__)

# ======================================================
# CONFIG
# ======================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

EVENTS_FOLDER = os.path.join(BASE_DIR, "events_decoded")

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


# ======================================================
# NORMALIZE EVENT
# ======================================================

def normalize_event(event, date):

    event["date"] = date

    event.setdefault("headline", "")
    event.setdefault("description", "")
    event.setdefault("content", "")
    event.setdefault("author", "")

    event.setdefault("url", "")
    event.setdefault("publishedAt", "")

    event.setdefault("source", "")
    event.setdefault("source_id", "")

    event.setdefault("region", "global")
    event.setdefault("location", {})

    event.setdefault("categories", ["general"])

    event.setdefault("matched_symbols", [])
    event.setdefault("matched_verses", [])

    event.setdefault("media_type", "article")

    event.setdefault("urlToImage", "")
    event.setdefault("video_url", "")

    event.setdefault("media", {})
    event["media"].setdefault("images", [])
    event["media"].setdefault("videos", [])

    # Backward compatibility
    if (
        not event["urlToImage"]
        and event["media"]["images"]
    ):
        event["urlToImage"] = event["media"]["images"][0]

    if (
        not event["video_url"]
        and event["media"]["videos"]
    ):
        event["video_url"] = event["media"]["videos"][0]
        event["media_type"] = "video"

    event["has_image"] = bool(event["urlToImage"])
    event["has_video"] = bool(event["video_url"])

    return event


# ======================================================
# API
# ======================================================

@events_bp.route("/api/events", methods=["GET"])
def get_week_events():

    try:

        os.makedirs(EVENTS_FOLDER, exist_ok=True)

        cutoff = datetime.utcnow() - timedelta(days=7)

        events = []

        for filename in os.listdir(EVENTS_FOLDER):

            if not filename.endswith(".json"):
                continue

            match = DATE_RE.search(filename)

            if not match:
                continue

            file_date = datetime.strptime(
                match.group(1),
                "%Y-%m-%d"
            )

            if file_date < cutoff:
                continue

            filepath = os.path.join(
                EVENTS_FOLDER,
                filename
            )

            with open(filepath, "r", encoding="utf-8") as f:
                day_events = json.load(f)

            for event in day_events:

                events.append(
                    normalize_event(
                        event,
                        match.group(1)
                    )
                )

        events.sort(
            key=lambda e: (
                e.get("publishedAt")
                or e.get("date")
            ),
            reverse=True
        )

        return jsonify({
            "status": "ok",
            "count": len(events),
            "events": events
        }), 200

    except Exception as exc:

        return jsonify({
            "status": "error",
            "message": str(exc),
            "events": []
        }), 500