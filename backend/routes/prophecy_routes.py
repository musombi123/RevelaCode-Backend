from flask import Blueprint, request, jsonify
from backend.bible_decoder import BibleDecoder

prophecy_bp = Blueprint("prophecy", __name__, url_prefix="/api/prophecy")

# init decoder instance
decoder = BibleDecoder()

@prophecy_bp.route("/decode", methods=["POST"])
def decode_prophecy():
    """
    Decode a verse or passage using the BibleDecoder
    """
    data = request.get_json(force=True) or {}
    verse_text = str(data.get("verse", "")).strip()

    if not verse_text:
        return jsonify({"message": "❌ Verse text is required"}), 400

    try:
        decoded = decoder.decode_verse(verse_text)
        return jsonify({
            "original": verse_text,
            "decoded": decoded
        }), 200
    except Exception as e:
        return jsonify({"message": f"❌ Failed to decode: {e}"}), 500


@prophecy_bp.route("/symbols", methods=["GET"])
def list_symbols():
    """
    Return all prophecy symbols loaded in BibleDecoder
    """
    return jsonify({
        "symbols": decoder.symbols
    }), 200


@prophecy_bp.route("/events", methods=["GET"])
def list_events():
    """
    Return prophecy-related events (stub for now)
    """
    # Later you can load from prophecy_events.json or db
    events = [
        {"id": 1, "title": "Daniel's Vision", "chapter": "Daniel 7"},
        {"id": 2, "title": "Revelation Beast", "chapter": "Revelation 13"},
    ]
    return jsonify(events), 200
