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
# ENRICHMENT LAYER (clean + safe)
# ======================================================

def enrich_event(event: dict) -> dict:
    text = " ".join([
        event.get("headline") or "",
        event.get("description") or "",
        event.get("content") or ""
    ])

    decoded = decoder.decode_verse(text).get("decoded", [])

    symbols = []
    verses = []

    for item in decoded:
        if not isinstance(item, dict) or "message" in item:
            continue

        symbol = list(item.keys())[0]
        symbols.append(symbol)

        ref = item[symbol].get("reference")
        if ref:
            verses.append(ref)

    event["matched_symbols"] = list(set(symbols))
    event["matched_verses"] = list(set(verses))

    # ensure category fallback
    event["categories"] = event.get("categories") or symbols or ["general"]

    return event


# ======================================================
# MAIN ROUTE
# ======================================================

@events_bp.route("/api/events", methods=["GET"])
def get_week_events():
    try:
        os.makedirs(EVENTS_FOLDER, exist_ok=True)

        cutoff = datetime.utcnow() - timedelta(days=7)

        events = []
        files_scanned = 0
        files_loaded = 0

        current_app.logger.info(f"📂 Scanning folder: {EVENTS_FOLDER}")

        for fname in os.listdir(EVENTS_FOLDER):
            if not fname.endswith(".json"):
                continue

            files_scanned += 1

            match = DATE_RE.search(fname)
            if not match:
                current_app.logger.warning(f"⚠️ Invalid filename skipped: {fname}")
                continue

            try:
                file_date = datetime.strptime(match.group(1), "%Y-%m-%d")
            except Exception:
                current_app.logger.warning(f"⚠️ Date parse failed: {fname}")
                continue

            if file_date < cutoff:
                current_app.logger.info(f"⏭️ Old file skipped: {fname}")
                continue

            path = os.path.join(EVENTS_FOLDER, fname)

            try:
                with open(path, "r", encoding="utf-8") as f:
                    day_events = json.load(f)

                if not isinstance(day_events, list):
                    current_app.logger.warning(f"⚠️ Invalid JSON structure: {fname}")
                    continue

                files_loaded += 1

                for ev in day_events:
                    ev["date"] = match.group(1)
                    ev = enrich_event(ev)

                    # safe defaults
                    ev.setdefault("headline", "")
                    ev.setdefault("description", "")
                    ev.setdefault("content", "")
                    ev.setdefault("author", "")
                    ev.setdefault("url", "")
                    ev.setdefault("urlToImage", "")
                    ev.setdefault("publishedAt", "")
                    ev.setdefault("source", "")
                    ev.setdefault("source_id", None)
                    ev.setdefault("location", {})

                    events.append(ev)

            except Exception as e:
                current_app.logger.error(f"❌ Failed loading {fname}: {e}")

        # ======================================================
        # RESPONSE HANDLING
        # ======================================================

        if not events:
            return jsonify({
                "status": "ok",
                "message": "No events available in the past week.",
                "debug": {
                    "files_scanned": files_scanned,
                    "files_loaded": files_loaded
                },
                "events": []
            }), 200

        events.sort(
            key=lambda x: x.get("publishedAt") or x.get("date"),
            reverse=True
        )

        return jsonify({
            "status": "ok",
            "message": f"Returning {len(events)} events",
            "debug": {
                "files_scanned": files_scanned,
                "files_loaded": files_loaded
            },
            "events": events
        }), 200

    except Exception as e:
        current_app.logger.error(f"❌ EVENTS API CRASH: {e}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "events": []
        }), 500