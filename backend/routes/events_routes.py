from flask import Blueprint, jsonify, current_app
from datetime import datetime, timedelta
import os, json, re
from backend.bible_decoder import BibleDecoder

events_bp = Blueprint("events", __name__)

EVENTS_FOLDER = os.path.join("backend", "events_decoded")
decoder = BibleDecoder()

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

def enrich_event_with_symbols(event: dict) -> dict:
    matched_symbols = []
    matched_verses = []

    text_to_check = " ".join([
        event.get("headline", ""),
        event.get("description", ""),
        event.get("content", "")
    ])

    decoded = decoder.decode_verse(text_to_check).get("decoded", [])

    for item in decoded:
        if "message" in item:
            continue
        symbol = list(item.keys())[0]
        matched_symbols.append(symbol)
        verse = item[symbol].get("reference")
        if verse:
            matched_verses.append(verse)

    event["matched_symbols"] = matched_symbols
    event["matched_verses"] = matched_verses
    return event


@events_bp.route("/api/events", methods=["GET"])
def get_week_events():
    """
    Returns decoded events from the past 7 days (any prefix),
    enriched with symbols & verses.
    """
    try:
        os.makedirs(EVENTS_FOLDER, exist_ok=True)
        events_list = []
        cutoff = datetime.utcnow() - timedelta(days=7)

        for fname in os.listdir(EVENTS_FOLDER):
            if not fname.endswith(".json"):
                continue

            match = DATE_RE.search(fname)
            if not match:
                current_app.logger.warning(f"⚠️ Skipping invalid filename: {fname}")
                continue

            try:
                file_date = datetime.strptime(match.group(1), "%Y-%m-%d")
            except ValueError:
                continue

            if file_date < cutoff:
                continue

            path = os.path.join(EVENTS_FOLDER, fname)

            try:
                with open(path, "r", encoding="utf-8") as f:
                    day_events = json.load(f)

                for ev in day_events:
                    ev["date"] = match.group(1)
                    enriched = enrich_event_with_symbols(ev)

                    # Normalize fields for frontend safety
                    enriched.setdefault("headline", "")
                    enriched.setdefault("description", "")
                    enriched.setdefault("content", "")
                    enriched.setdefault("author", "")
                    enriched.setdefault("url", "")
                    enriched.setdefault("urlToImage", "")
                    enriched.setdefault("publishedAt", "")
                    enriched.setdefault("source", "")
                    enriched.setdefault("source_id", None)
                    enriched.setdefault("categories", enriched.get("matched_symbols", []))
                    enriched.setdefault("matched_symbols", [])
                    enriched.setdefault("matched_verses", [])
                    enriched.setdefault("location", {})

                    events_list.append(enriched)

            except Exception as e:
                current_app.logger.warning(f"⚠️ Failed to load {fname}: {e}")

        if not events_list:
            return jsonify({
                "status": "ok",
                "message": "No events available in the past week.",
                "events": []
            }), 200

        events_list.sort(
            key=lambda x: x.get("publishedAt") or x.get("date"),
            reverse=True
        )

        return jsonify({
            "status": "ok",
            "message": f"Returning {len(events_list)} events from the past week",
            "events": events_list
        }), 200

    except Exception as e:
        current_app.logger.error(f"❌ Error loading weekly events: {e}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "events": []
        }), 500
