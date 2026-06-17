from flask import Blueprint, jsonify, current_app
from datetime import datetime, timedelta
import os, json, re
from backend.bible_decoder import BibleDecoder

events_bp = Blueprint("events", __name__)

# ======================================================
# CONFIG
# ======================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

EVENTS_FOLDER = os.path.join(BASE_DIR, "events_decoded")

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

decoder = BibleDecoder()

# ======================================================
# MAIN ROUTE
# ======================================================
@events_bp.route("/api/events", methods=["GET"])
def get_week_events():
    try:
        os.makedirs(EVENTS_FOLDER, exist_ok=True)

        cutoff = datetime.utcnow() - timedelta(days=7)

        events = []

        for fname in os.listdir(EVENTS_FOLDER):
            if not fname.endswith(".json"):
                continue

            match = DATE_RE.search(fname)
            if not match:
                continue

            file_date = datetime.strptime(match.group(1), "%Y-%m-%d")

            if file_date < cutoff:
                continue

            path = os.path.join(EVENTS_FOLDER, fname)

            with open(path, "r", encoding="utf-8") as f:
                day_events = json.load(f)

            for ev in day_events:
                ev["date"] = match.group(1)

                # NO RE-ENRICHMENT HERE
                ev.setdefault("matched_symbols", [])
                ev.setdefault("matched_verses", [])
                ev.setdefault("categories", ev.get("categories", ["general"]))

                events.append(ev)

        events.sort(
            key=lambda x: x.get("publishedAt") or x.get("date"),
            reverse=True
        )

        return jsonify({
            "status": "ok",
            "message": f"Returning {len(events)} events",
            "events": events
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "events": []
        }), 500