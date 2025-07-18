from flask import Flask, request, jsonify
from flask_cors import CORS
from backend.bible_decoder import decode_verse
import os
import logging
import json
from datetime import datetime  # <-- Needed for today's date

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

@app.route('/api/events', methods=['GET'])
def get_today_events():
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        event_path = os.path.join('events', f'events_{today}.json')

        if not os.path.exists(event_path):
            return jsonify([])  # No events found

        with open(event_path, 'r', encoding='utf-8') as f:
            events = json.load(f)

        return jsonify(events), 200

    except Exception as e:
        app.logger.error(f"Error loading events: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
