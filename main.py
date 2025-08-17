from flask import Flask, request, jsonify
from flask_cors import CORS
import os, logging, json, hashlib
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ---------- INIT ----------
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ---------- BLUEPRINTS ----------
from backend.docs_routes import docs_bp   # /api/legal/privacy + /api/legal/terms
from backend.bible_decoder import decode_verse
app.register_blueprint(docs_bp)

USERS_FILE = os.path.join("backend", "user_data", "users.json")

# ---------- UTILS ----------
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ---------- ROUTES ----------
@app.route("/", methods=["GET"])
def index():
    return jsonify({"message": "RevelaCode Backend is live"}), 200

# --- Prophecy Decoding ---
@app.route("/decode", methods=["POST"])
def decode():
    try:
        data = request.get_json(force=True)
        verse = data.get("verse", "").strip()

        if not verse:
            return jsonify({"status": "error", "message": "Verse is required"}), 400

        app.logger.info(f"Decoding verse: {verse}")
        try:
            result = decode_verse(verse)
        except Exception as e:
            app.logger.error(f"Decoder failed: {str(e)}")
            result = [{"symbol": verse, "meaning": "No interpretation found"}]

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

# --- Events (Today’s File) ---
@app.route("/api/events", methods=["GET"])
def get_today_events():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        event_path = os.path.join("backend", "events_decoded", f"events_{today}.json")

        if not os.path.exists(event_path):
            return jsonify([{
                "title": "No events today",
                "time": "",
                "location": "",
                "details": "Check back tomorrow for updates."
            }]), 200

        with open(event_path, "r", encoding="utf-8") as f:
            events = json.load(f)

        return jsonify(events), 200
    except Exception as e:
        app.logger.error(f"Error loading events: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Latest Prophecies ---
@app.route("/api/prophecies", methods=["GET"])
def get_latest_prophecies():
    try:
        folder = os.path.join("backend", "events_decoded")
        prophecy_files = [f for f in os.listdir(folder) if f.startswith("events_prophecy_")]

        if not prophecy_files:
            return jsonify([]), 200

        latest_file = max(prophecy_files, key=lambda f: f.split("_")[-1].replace(".json", ""))
        file_path = os.path.join(folder, latest_file)

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return jsonify(data), 200
    except Exception as e:
        app.logger.error(f"Error loading prophecies: {str(e)}")
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
        app.logger.error(f"Error in register: {str(e)}")
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
        app.logger.error(f"Error in login: {str(e)}")
        return jsonify({"message": str(e)}), 500

# ---------- START ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
