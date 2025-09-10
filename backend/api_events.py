from flask import Blueprint, jsonify, current_app
import os
import json
from datetime import datetime

events_bp = Blueprint("events", __name__)

@events_bp.route("/api/events", methods=["GET"])
def get_today_events():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        event_path = os.path.join("events", f"events_{today}.json")

        if not os.path.exists(event_path):
            return jsonify([]), 200  # No events today

        with open(event_path, "r", encoding="utf-8") as f:
            events = json.load(f)

        return jsonify(events), 200

    except Exception as e:
        current_app.logger.error(f"Error loading events: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
