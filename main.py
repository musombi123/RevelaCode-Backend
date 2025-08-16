from flask import Flask, request, jsonify
from flask_cors import CORS
from backend.bible_decoder import decode_verse
import os, logging, json, hashlib
from datetime import datetime

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

USERS_FILE = os.path.join("backend", "users.json")

# ---------- UTILS ----------
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ---------- ROUTES ----------
@app.route("/", methods=["GET"])
def index():
    return jsonify({"message": "RevelaCode Backend is live"}), 200

# --- Prophecy decoding ---
@app.route("/decode", methods=["POST"])
def decode():
    try:
        data = request.get_json(force=True)
        verse = data.get("verse", "").strip()

        if not verse:
            return jsonify({"status": "error", "message": "Verse is required"}), 400

        app.logger.info(f"Decoding verse: {verse}")
        result = decode_verse(verse)

        return jsonify({"status": "success", "decoded": result}), 200
    except Exception as e:
        app.logger.error(f"Error decoding verse: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Symbols ---
@app.route("/symbols", methods=["GET"])
def get_symbols():
    try:
        file_path = os.path.join("backend", "symbols_data.json")
        with open(file_path, "r") as f:
            data = json.load(f)
        return jsonify(data), 200
    except Exception as e:
        app.logger.error(f"Error loading symbols data: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Events ---
@app.route("/api/events", methods=["GET"])
def get_today_events():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        event_path = os.path.join("events", f"events_{today}.json")

        if not os.path.exists(event_path):
            return jsonify([])

        with open(event_path, "r", encoding="utf-8") as f:
            events = json.load(f)

        return jsonify(events), 200
    except Exception as e:
        app.logger.error(f"Error loading events: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- User Registration ---
@app.route("/api/register", methods=["POST"])
def register():
    try:
        data = request.get_json(force=True)
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        full_name = data.get("full_name", "").strip()

        if not username or not password or not full_name:
            return jsonify({"message": "All fields are required"}), 400

        users = load_users()
        if username in users:
            return jsonify({"message": "⚠ Username already exists"}), 400

        users[username] = {
            "full_name": full_name,
            "password": hash_password(password),
            "role": "normal"
        }
        save_users(users)

        return jsonify({"message": "✅ Registration successful", "user": full_name}), 201
    except Exception as e:
        return jsonify({"message": str(e)}), 500

# --- User Login ---
@app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.get_json(force=True)
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()

        users = load_users()
        if username not in users:
            return jsonify({"message": "❌ Invalid username or password"}), 401

        hashed = hash_password(password)
        if users[username]["password"] != hashed:
            return jsonify({"message": "❌ Invalid username or password"}), 401

        return jsonify({
            "message": "✅ Login successful",
            "user": {
                "username": username,
                "full_name": users[username]["full_name"],
                "role": users[username]["role"]
            }
        }), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

# ---------- START ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
