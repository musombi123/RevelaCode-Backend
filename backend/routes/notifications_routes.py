from flask import Blueprint, request, jsonify
import os, json
from datetime import datetime

notifications_bp = Blueprint("notifications", __name__)

NOTIFICATIONS_FILE = os.path.join("backend", "notifications.json")

# ---------------------------
# Helpers
# ---------------------------
def load_notifications():
    if os.path.exists(NOTIFICATIONS_FILE):
        with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_notifications(data):
    with open(NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def push_notification(text, extra=None):
    """Internal helper for system/user events (not just API)."""
    data = load_notifications()
    new_item = {
        "id": len(data) + 1,
        "text": text,
        "read": False,
        "timestamp": datetime.now().isoformat()
    }
    if extra:
        new_item.update(extra)  # can add url, type, user_id, etc.
    data.append(new_item)
    save_notifications(data)
    return new_item

# ---------------------------
# Routes
# ---------------------------

# --- Get all notifications ---
@notifications_bp.route("/api/notifications", methods=["GET"])
def get_notifications():
    try:
        data = load_notifications()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Add notification (API) ---
@notifications_bp.route("/api/notifications", methods=["POST"])
def add_notification():
    try:
        new_note = request.get_json(force=True)
        if not new_note.get("text"):
            return jsonify({"error": "Text is required"}), 400

        note = push_notification(new_note["text"], extra=new_note)
        return jsonify(note), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Mark all as read ---
@notifications_bp.route("/api/notifications/read-all", methods=["PUT"])
def mark_all_read():
    try:
        data = load_notifications()
        for n in data:
            n["read"] = True
        save_notifications(data)
        return jsonify({"message": "All notifications marked as read"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Mark single notification as read ---
@notifications_bp.route("/api/notifications/<int:note_id>", methods=["PUT"])
def mark_single_read(note_id):
    try:
        data = load_notifications()
        found = False
        for n in data:
            if n["id"] == note_id:
                n["read"] = True
                found = True
        save_notifications(data)

        if not found:
            return jsonify({"error": f"Notification {note_id} not found"}), 404
        return jsonify({"message": f"Notification {note_id} marked as read"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Delete single notification ---
@notifications_bp.route("/api/notifications/<int:note_id>", methods=["DELETE"])
def delete_notification(note_id):
    try:
        data = load_notifications()
        new_data = [n for n in data if n["id"] != note_id]
        if len(new_data) == len(data):
            return jsonify({"error": f"Notification {note_id} not found"}), 404
        save_notifications(new_data)
        return jsonify({"message": f"Notification {note_id} deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Clear all notifications ---
@notifications_bp.route("/api/notifications", methods=["DELETE"])
def clear_notifications():
    try:
        save_notifications([])
        return jsonify({"message": "All notifications cleared"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
