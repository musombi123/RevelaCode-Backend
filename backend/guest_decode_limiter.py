from flask import Blueprint, request, jsonify, current_app
from datetime import datetime

guest_bp = Blueprint("guest", __name__)

@guest_bp.route("/api/guest/prophecy", methods=["POST"])
def guest_prophecy():
    try:
        data = request.get_json(silent=True) or {}
        query = (data.get("query") or "").strip()

        if not query:
            return jsonify({
                "success": False,
                "message": "❌ Please provide a prophecy query."
            }), 400

        # ----- REAL DECODING LOGIC GOES HERE -----
        # For now, a placeholder
        decoded = f"Prophecy decoded result for: {query}"

        return jsonify({
            "success": True,
            "mode": "guest",
            "message": "✅ Prophecy decoded successfully.",
            "data": {
                "query": query,
                "decoded": decoded,
                "timestamp": datetime.utcnow().isoformat()
            },
            "notice": "ℹ️ You're in Guest Mode. Log in to save prophecy history and access full features."
        }), 200

    except Exception as e:
        current_app.logger.error(f"Guest prophecy error: {e}")
        return jsonify({
            "success": False,
            "message": "❌ Something went wrong while decoding prophecy.",
            "error": str(e)
        }), 500
