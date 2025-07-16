from flask import Flask, request, jsonify
from flask_cors import CORS
from backend.bible_decoder import decode_verse
import os
import logging
import json  # <-- You were missing this import

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

@app.route('/', methods=['GET'])
def index():
    return jsonify({"message": "RevelaCode Backend is live"}), 200

@app.route('/decode', methods=['POST'])
def decode():
    try:
        data = request.get_json(force=True)
        verse = data.get('verse', '').strip()

        if not verse:
            return jsonify({'status': 'error', 'message': 'Verse is required'}), 400

        app.logger.info(f"Decoding verse: {verse}")
        result = decode_verse(verse)

        return jsonify({'status': 'success', 'decoded': result}), 200

    except Exception as e:
        app.logger.error(f"Error decoding verse: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/symbols', methods=['GET'])
def get_symbols():
    try:
        file_path = os.path.join('backend', 'symbols_data.json')
        with open(file_path, 'r') as f:
            data = json.load(f)
        return jsonify(data), 200

    except Exception as e:
        app.logger.error(f"Error loading symbols data: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
