from flask import Flask, jsonify
import os
import json
from datetime import datetime

app = Flask(__name__)

@app.route("/api/events", methods=["GET"])
def get_latest_events():
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"./events_decoded/events_{today}.json"

    if not os.path.exists(filename):
        return jsonify({"error": "No events found"}), 404

    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"Failed to load events: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
