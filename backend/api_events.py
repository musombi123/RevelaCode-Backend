# backend/events.py
from flask import Blueprint, jsonify, current_app
import os
import json
from datetime import datetime, timedelta

events_bp = Blueprint("events", __name__)

EVENTS_FOLDER = os.path.join("backend", "events_decoded")

def load_events_for_date(date_str):
    """Helper to load events for a given date string (YYYY-MM-DD)"""
    try:
        event_path = os.path.join(EVENTS_FOLDER, f"events_{date_str}.json")
        if os.path.exists(event_path):
            with open(event_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error loading events for {date_str}: {str(e)}")
    return []

@events_bp.route("/api/events", methods=["GET"])
def get_week_events():
    """
    Returns decoded prophecy events for the past 7 days, including today.
    Sorted with the latest (today) first.
    """
    try:
        os.makedirs(EVENTS_FOLDER, exist_ok=True)
        week_events = []
        for i in range(7):
            day = datetime.now() - timedelta(days=i)
            date_str = day.strftime("%Y-%m-%d")
            events = load_events_for_date(date_str)
            week_events.append({
                "date": date_str,
                "events": events
            })

        # Filter out days with no events
        week_events = [day for day in week_events if day["events"]]

        if not week_events:
            return jsonify({
                "status": "ok",
                "message": "No events available for the past week.",
                "events": []
            }), 200

        return jsonify({
            "status": "ok",
            "message": f"Events for the past {len(week_events)} days (latest first).",
            "events": week_events
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error loading week events: {str(e)}")
        return jsonify({"status": "error", "message": str(e), "events": []}), 500


@events_bp.route("/api/prophecies", methods=["GET"])
def get_latest_prophecies():
    """
    Returns the latest prophecy file (events_prophecy_*.json).
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

        # Pick latest by date in filename
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
