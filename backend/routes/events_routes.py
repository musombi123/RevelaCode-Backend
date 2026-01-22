from flask import Blueprint, jsonify, current_app
from datetime import datetime, timedelta
import os, json

events_bp = Blueprint("events", __name__)

EVENTS_FOLDER = os.path.join("backend", "events_decoded")

@events_bp.route("/api/events", methods=["GET"])
def get_week_events():
    """
    Returns events decoded for the past 7 days, latest first.
    If no events are found for a day, that day is skipped.
    """
    try:
        os.makedirs(EVENTS_FOLDER, exist_ok=True)
        events_list = []

        for i in range(7):
            day = datetime.now() - timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")
            event_path = os.path.join(EVENTS_FOLDER, f"events_{day_str}.json")

            if os.path.exists(event_path):
                with open(event_path, "r", encoding="utf-8") as f:
                    day_events = json.load(f)
                    for ev in day_events:
                        ev["date"] = day_str  # tag each event with its date
                    events_list.extend(day_events)

        if not events_list:
            return jsonify({
                "status": "ok",
                "message": "No events available in the past week.",
                "events": []
            }), 200

        # Sort so latest events appear first
        events_list.sort(key=lambda x: x.get("date", ""), reverse=True)

        return jsonify({
            "status": "ok",
            "message": f"Returning {len(events_list)} events from the past week",
            "events": events_list
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error loading weekly events: {str(e)}")
        return jsonify({"status": "error", "message": str(e), "events": []}), 500


@events_bp.route("/api/prophecies", methods=["GET"])
def get_latest_prophecies():
    """
    Returns the latest prophecy file (events_prophecy_*.json)
    """
    try:
        os.makedirs(EVENTS_FOLDER, exist_ok=True)
        prophecy_files = [f for f in os.listdir(EVENTS_FOLDER) if f.startswith("events_prophecy_")]

        if not prophecy_files:
            return jsonify({
                "status": "ok",
                "message": "No prophecies available.",
                "prophecies": []
            }), 200

        latest_file = max(prophecy_files, key=lambda f: f.split("_")[-1].replace(".json", ""))
        file_path = os.path.join(EVENTS_FOLDER, latest_file)

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return jsonify({
            "status": "ok",
            "message": f"Latest prophecy file: {latest_file}",
            "prophecies": data
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error loading prophecies: {str(e)}")
        return jsonify({"status": "error", "message": str(e), "prophecies": []}), 500
