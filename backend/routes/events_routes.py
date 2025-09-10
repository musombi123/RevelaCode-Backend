import os, json
from flask import Blueprint, request, jsonify
from datetime import datetime

events_bp = Blueprint("events", __name__, url_prefix="/api/events")

# folder for prophecy events JSON
EVENTS_FILE = os.path.join("backend", "events.json")
if not os.path.exists(EVENTS_FILE):
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)


def load_events():
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_events(events):
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)


@events_bp.route("/", methods=["GET"])
def get_all_events():
    """Fetch all prophecy news events"""
    return jsonify(load_events()), 200


@events_bp.route("/latest", methods=["GET"])
def get_latest_event():
    """Fetch the latest prophecy news event"""
    events = load_events()
    return jsonify(events[-1] if events else {}), 200


@events_bp.route("/add", methods=["POST"])
def add_event():
    """
    Add a new prophecy news event
    Expected JSON:
    {
      "headline": "...",
      "description": "...",
      "content": "...",
      "author": "...",
      "url": "...",
      "urlToImage": "...",
      "publishedAt": "...",
      "source": "...",
      "categories": ["general"],
      "matched_symbols": ["technology_and_image_of_the_beast"],
      "matched_verses": ["Revelation 13:14-15"]
    }
    """
    data = request.get_json(force=True) or {}
    events = load_events()

    # add timestamp if missing
    if "publishedAt" not in data:
        data["publishedAt"] = datetime.utcnow().isoformat()

    events.append(data)
    save_events(events)
    return jsonify({"message": "✅ Prophecy event added", "event": data}), 201
