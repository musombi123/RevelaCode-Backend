from flask import Flask, jsonify
import os
import json
from datetime import datetime

app = Flask(__name__)  # Make sure this line exists
# ... CORS setup, logging, and other routes

@app.route('/api/events', methods=['GET'])
def get_today_events():
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        event_path = os.path.join('events', f'events_{today}.json')

        if not os.path.exists(event_path):
            return jsonify([])  # No events today

        with open(event_path, 'r', encoding='utf-8') as f:
            events = json.load(f)

        return jsonify(events), 200

    except Exception as e:
        app.logger.error(f"Error loading events: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
