from flask import Blueprint, request, jsonify
from backend.bible_decoder import BibleDecoder

decoder_bp = Blueprint("decoder", __name__)
decoder = BibleDecoder()

@decoder_bp.route("/api/decode", methods=["POST"])
def decode_text():
    data = request.get_json()

    if not data or "verse" not in data:
        return jsonify({"error": "Missing 'verse' field."}), 400

    verse = data["verse"]
    decoded = decoder.decode_verse(verse)

    return jsonify(decoded), 200
