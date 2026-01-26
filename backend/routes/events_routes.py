from flask import Blueprint, jsonify, current_app
from datetime import datetime, timedelta
import os, json
from backend.bible_decoder import BibleDecoder

events_bp = Blueprint("events", __name__)

EVENTS_FOLDER = os.path.join("backend", "events_decoded")
decoder = BibleDecoder()  # Use the same BibleDecoder as prophecy

def enrich_event_with_symbols(event):
    """
    Adds matched_symbols and matched_verses to an event based on its content
    """
    matched_symbols = []
    matched_verses = []

    text_to_check = " ".join([
        event.get("headline", ""),
        event.get("description", ""),
        event.get("content", "")
    ])

    decoded = decoder.decode_verse(text_to_check).get("decoded", [])

    for item in decoded:
        if "message" not in item:  # skip messages
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
    Returns events decoded for the past 7 days, latest first, enriched with symbols.
    """
    try:
        os.makedirs(EVENTS_FOLDER, exist_ok=True)
        events_list = []

        for i in range(7):
            day = datetime.now() - timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")
            event_path = os.path.join(EVENTS_FOLDER, f"events_{day_str}.json")

            if os.path.exists(event_path):
                try:
                    with open(event_path, "r", encoding="utf-8") as f:
                        day_events = json.load(f)
                        for ev in day_events:
                            ev["date"] = day_str
                            enriched = enrich_event_with_symbols(ev)
                            events_list.append(enriched)
                except Exception as e:
                    current_app.logger.warning(f"⚠️ Failed to load {event_path}: {e}")
                    continue

        if not events_list:
            return jsonify({
                "status": "ok",
                "message": "No events available in the past week.",
                "events": []
            }), 200

        events_list.sort(key=lambda x: x.get("date", ""), reverse=True)
        return jsonify({
            "status": "ok",
            "message": f"Returning {len(events_list)} events from the past week",
            "events": events_list
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error loading weekly events: {str(e)}")
        return jsonify({"status": "error", "message": str(e), "events": []}), 500
