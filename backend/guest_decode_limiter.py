from flask import Flask, request, jsonify
import json
import os
from datetime import datetime

app = Flask(__name__)
GUEST_FILE = "./backend/user_data/guest_decode.json"

MAX_GUEST_DECODES_PER_DAY = 5

def load_guest_counts():
    if os.path.exists(GUEST_FILE):
        with open(GUEST_FILE, "r") as f:
            return json.load(f)
    return {}

def save_guest_counts(counts):
    with open(GUEST_FILE, "w") as f:
        json.dump(counts, f, indent=2)

@app.route('/guest/decode', methods=['POST'])
def guest_decode():
    counts = load_guest_counts()
    today = datetime.now().strftime("%Y-%m-%d")

    today_count = counts.get(today, 0)

    if today_count >= MAX_GUEST_DECODES_PER_DAY:
        return jsonify({"message": "⚠️ Guest decode limit reached. Come back tomorrow."}), 429

    # process dummy decode (or real decode)
    counts[today] = today_count + 1
    save_guest_counts(counts)

    return jsonify({
        "message": "✅ Decoded as guest.",
        "remaining": MAX_GUEST_DECODES_PER_DAY - counts[today]
    })

if __name__ == "__main__":
    app.run(debug=True)
