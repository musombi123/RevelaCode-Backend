# backend/routes/notifications_routes.py
from flask import Blueprint, request, jsonify
import os
import json
from datetime import datetime
from threading import Lock

notifications_bp = Blueprint("notifications", __name__)

# ---------------------------
# File storage (safe path)
# ---------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTIFICATIONS_FILE = os.path.join(BASE_DIR, "notifications.json")

file_lock = Lock()

# ---------------------------
# Helpers
# ---------------------------
def load_notifications():
    if not os.path.exists(NOTIFICATIONS_FILE):
        return []

    with file_lock:
        with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []

def save_notifications(data):
    with file_lock:
        with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

def _next_id(data):
    return max((n["id"] for n in data), default=0) + 1

def push_notification(text, extra=None):
    """Internal helper for system/user events."""
    data = load_notifications()

    new_item = {
        "id": _next_id(data),
        "text": text,
        "read": False,
        "timestamp": datetime.utcnow().isoformat()
    }

    if extra:
        for k, v in extra.items():
            if k not in new_item:
                new_item[k] = v

    data.append(new_item)
    save_notifications(data)
    return new_item

# ---------------------------
# Routes
# ---------------------------

@notifications_bp.route("/api/notifications", methods=["GET"])
def get_notifications():
    data = load_notifications()
    return jsonify({
        "total": len(data),
        "notifications": data
    }), 200


@notifications_bp.route("/api/notifications", methods=["POST"])
def add_notification():
    data = request.get_json(silent=True)
    if not data or not data.get("text"):
        return jsonify({"error": "Text is required"}), 400

    note = push_notification(data["text"], extra=data)
    return jsonify(note), 201


@notifications_bp.route("/api/notifications/read-all", methods=["PUT"])
def mark_all_read():
    data = load_notifications()
    for n in data:
        n["read"] = True
    save_notifications(data)

    return jsonify({"message": "All notifications marked as read"}), 200


@notifications_bp.route("/api/notifications/<int:note_id>", methods=["PUT"])
def mark_single_read(note_id):
    data = load_notifications()

    for n in data:
        if n["id"] == note_id:
            n["read"] = True
            save_notifications(data)
            return jsonify({
                "message": f"Notification {note_id} marked as read"
            }), 200

    return jsonify({"error": f"Notification {note_id} not found"}), 404


@notifications_bp.route("/api/notifications/<int:note_id>", methods=["DELETE"])
def delete_notification(note_id):
    data = load_notifications()
    new_data = [n for n in data if n["id"] != note_id]

    if len(new_data) == len(data):
        return jsonify({"error": f"Notification {note_id} not found"}), 404

    save_notifications(new_data)
    return jsonify({
        "message": f"Notification {note_id} deleted"
    }), 200


@notifications_bp.route("/api/notifications", methods=["DELETE"])
def clear_notifications():
    save_notifications([])
    return jsonify({"message": "All notifications cleared"}), 200
