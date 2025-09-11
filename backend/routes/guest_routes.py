from flask import Blueprint, request, jsonify, current_app
import os, json
from datetime import datetime

guest_bp = Blueprint("guest", __name__)

GUEST_FILE = os.path.join("backend", "user_data", "guest_decode.json")
MAX_GUEST_DECODES_PER_DAY = 5


def load_guest_counts():
    if os.path.exists(GUEST_FILE):
        with open(GUEST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_guest_counts(counts):
    os.makedirs(os.path.dirname(GUEST_FILE), exist_ok=True)
    with open(GUEST_FILE, "w", encoding="utf-8") as f:
        json.dump(counts, f, indent=2)


@guest_bp.route("/guest/decode", methods=["POST"])
def guest_decode():
    try:
        counts = load_guest_counts()
        today = datetime.now().strftime("%Y-%m-%d")

        today_count = counts.get(today, 0)
        if today_count >= MAX_GUEST_DECODES_PER_DAY:
            return jsonify({
                "success": False,
                "message": "⚠️ Guest decode limit reached. Please register or come back tomorrow."
            }), 429

        # here you would normally run real decode logic
        # for now we just increment counter
        counts[today] = today_count + 1
        save_guest_counts(counts)

        return jsonify({
            "success": True,
            "message": "✅ Decoded as guest.",
            "remaining": MAX_GUEST_DECODES_PER_DAY - counts[today]
        }), 200

    except Exception as e:
        current_app.logger.error(f"Guest decode error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
