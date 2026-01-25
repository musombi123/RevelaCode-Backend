from flask import Blueprint, request, jsonify
from backend.bible_decoder import BibleDecoder

prophecy_bp = Blueprint("prophecy", __name__, url_prefix="/api/prophecy")

# Initialize decoder
decoder = BibleDecoder()


@prophecy_bp.route("/decode", methods=["POST"])
def decode_prophecy():
    """
    Decode a verse or passage using the BibleDecoder.
    Returns a consistent structure for the frontend:
    {
        "original": "<input text>",
        "decoded": [ { "symbol": {...} }, ... ]
    }
    """
    try:
        data = request.get_json(force=True) or {}
        verse_text = str(data.get("verse", "")).strip()

        if not verse_text:
            return jsonify({"message": "❌ Verse text is required"}), 400

        # Decode using BibleDecoder
        decoded_result = decoder.decode_verse(verse_text)

        # Ensure `decoded` is always a list of objects
        decoded_list = decoded_result.get("decoded", [])
        if not isinstance(decoded_list, list):
            decoded_list = [{"message": "⚠️ Unexpected decode format"}]

        return jsonify({
            "original": verse_text,
            "decoded": decoded_list
        }), 200

    except Exception as e:
        return jsonify({
            "message": f"❌ Failed to decode prophecy: {str(e)}"
        }), 500
