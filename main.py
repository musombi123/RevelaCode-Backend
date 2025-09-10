# backend/main.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import os, logging, json, hashlib
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ---------- INIT ----------
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)

# ---------- BLUEPRINTS ----------
# --- Auth & Users ---
try:
    from backend.registry import registry_bp
    app.register_blueprint(registry_bp)
    app.logger.info("registry_bp registered")
except Exception as e:
    app.logger.warning(f"registry_bp not available: {e}")

try:
    from backend.login import login_bp
    app.register_blueprint(login_bp)
    app.logger.info("login_bp registered")
except Exception as e:
    app.logger.warning(f"login_bp not available: {e}")

try:
    from backend.verify import verify_bp
    app.register_blueprint(verify_bp)
    app.logger.info("verify_bp registered")
except Exception as e:
    app.logger.warning(f"verify_bp not available: {e}")

try:
    from backend.reset_password import reset_bp
    app.register_blueprint(reset_bp)
    app.logger.info("reset_bp registered")
except Exception as e:
    app.logger.warning(f"reset_bp not available: {e}")

# --- Notifications ---
try:
    from backend.notifications_routes import notifications_bp
    app.register_blueprint(notifications_bp)
    app.logger.info("notifications_bp registered")
except Exception as e:
    app.logger.warning(f"notifications_bp not available: {e}")

try:
    from backend.routes.docs_routes import docs_bp  # /api/legal/privacy + /api/legal/terms
    app.register_blueprint(docs_bp)
    app.logger.info("docs_bp registered")
except Exception as e:
    app.logger.warning(f"docs_bp not available: {e}")

try:
    from backend.routes.decoder_routes import decoder_bp  # exposes /decode
    app.register_blueprint(decoder_bp)
    app.logger.info("decoder_bp registered")
except Exception as e:
    app.logger.warning(f"decoder_bp not available: {e}")

# ---------- STORAGE PATHS ----------
USERS_FILE = os.path.join("backend", "user_data", "users.json")
SYMBOLS_FILE = os.path.join("backend", "symbols_data.json")
EVENTS_FOLDER = os.path.join("backend", "events_decoded")

# ---------- UTILS ----------
def ensure_user_dir():
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)

def load_users():
    ensure_user_dir()
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users):
    ensure_user_dir()
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ---------- ROUTES ----------
@app.route("/", methods=["GET"])
def index():
    return jsonify({"message": "RevelaCode Backend is live"}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200

# --- Symbols ---
@app.route("/symbols", methods=["GET"])
def get_symbols():
    try:
        if not os.path.exists(SYMBOLS_FILE):
            return jsonify({"symbols": []}), 200
        with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data), 200
    except Exception as e:
        app.logger.error(f"Error loading symbols data: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Events (Today’s File) ---
@app.route("/api/events", methods=["GET"])
def get_today_events():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(EVENTS_FOLDER, exist_ok=True)
        event_path = os.path.join(EVENTS_FOLDER, f"events_{today}.json")

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
        app.logger.error(f"Error loading events: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Latest Prophecies ---
@app.route("/api/prophecies", methods=["GET"])
def get_latest_prophecies():
    try:
        os.makedirs(EVENTS_FOLDER, exist_ok=True)
        files = [
            f for f in os.listdir(EVENTS_FOLDER)
            if f.startswith("events_prophecy_") and f.endswith(".json")
        ]
        if not files:
            return jsonify([]), 200

        latest = max(files, key=lambda f: f.split("_")[-1].replace(".json", ""))
        file_path = os.path.join(EVENTS_FOLDER, latest)
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data), 200
    except Exception as e:
        app.logger.error(f"Error loading prophecies: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Registration ---
@app.route("/api/register", methods=["POST"])
def register():
    try:
        data = request.get_json(force=True) or {}
        full_name = str(data.get("full_name", "")).strip()
        contact = str(data.get("contact", data.get("username", ""))).strip()
        password = str(data.get("password", "")).strip()
        confirm_password = str(data.get("confirm_password", "")).strip()

        if not full_name or not contact or not password:
            return jsonify({"message": "All fields are required"}), 400

        if confirm_password and (password != confirm_password):
            return jsonify({"message": "Passwords do not match"}), 400

        users = load_users()
        if contact in users:
            return jsonify({"message": "⚠ Account already exists with this contact"}), 400

        users[contact] = {
            "full_name": full_name,
            "contact": contact,
            "password": hash_password(password),
            "role": "normal"
        }
        save_users(users)

        return jsonify({"message": "✅ Registration successful", "user": full_name}), 201
    except Exception as e:
        app.logger.error(f"Error in register: {e}")
        return jsonify({"message": str(e)}), 500

# --- Login ---
@app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.get_json(force=True) or {}
        contact = str(data.get("contact", data.get("username", ""))).strip()
        password = str(data.get("password", "")).strip()

        users = load_users()
        if contact not in users:
            return jsonify({"message": "❌ Invalid contact or password"}), 401

        if users[contact]["password"] != hash_password(password):
            return jsonify({"message": "❌ Invalid contact or password"}), 401

        return jsonify({
            "message": "✅ Login successful",
            "user": {
                "contact": contact,
                "full_name": users[contact]["full_name"],
                "role": users[contact]["role"]
            }
        }), 200
    except Exception as e:
        app.logger.error(f"Error in login: {e}")
        return jsonify({"message": str(e)}), 500

# ---------- START ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
