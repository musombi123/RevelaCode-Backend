from flask import Blueprint, jsonify, current_app
from datetime import datetime
import os, json

events_bp = Blueprint("events", __name__)

EVENTS_FOLDER = os.path.join("backend", "events_decoded")

@events_bp.route("/api/events", methods=["GET"])
def get_today_events():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(EVENTS_FOLDER, exist_ok=True)
        event_path = os.path.join(EVENTS_FOLDER, f"events_{today}.json")

        if not os.path.exists(event_path):
            return jsonify({
                "status": "ok",
                "message": "No events available today.",
                "events": []
            }), 200

        with open(event_path, "r", encoding="utf-8") as f:
            events = json.load(f)

        return jsonify({
            "status": "ok",
            "message": f"Found {len(events)} events for {today}",
            "events": events
        }), 200

    except Exception as e:
        current_app.logger.error(str(e))
        return jsonify({"status": "error", "message": str(e), "events": []}), 500


@events_bp.route("/api/prophecies", methods=["GET"])
def get_latest_prophecies():
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
        current_app.logger.error(str(e))
        return jsonify({"status": "error", "message": str(e), "prophecies": []}), 500
