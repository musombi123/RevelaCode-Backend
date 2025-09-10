# backend/decoder_routes.py
from flask import Blueprint, request, jsonify
from backend.bible_decoder import BibleDecoder

# Init blueprint
decoder_bp = Blueprint("decoder", __name__)

# Init decoder class
decoder = BibleDecoder()

@decoder_bp.route("/api/decode", methods=["POST"])
def decode():
    try:
        data = request.get_json()
        verse = data.get("verse", "")

        if not verse.strip():
            return jsonify({"status": "error", "message": "Verse is required"}), 400

        result = decoder.decode_verse(verse)
        return jsonify({"status": "success", "result": result}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
