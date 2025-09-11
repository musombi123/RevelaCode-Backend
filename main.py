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

# --- Docs (Privacy & Terms) ---
try:
    from backend.routes.docs_routes import docs_bp
    app.register_blueprint(docs_bp)
    app.logger.info("docs_bp registered")
except Exception as e:
    app.logger.warning(f"docs_bp not available: {e}")

# --- Decoder ---
try:
    from backend.routes.decoder_routes import decoder_bp
    app.register_blueprint(decoder_bp)
    app.logger.info("decoder_bp registered")
except Exception as e:
    app.logger.warning(f"decoder_bp not available: {e}")

# --- Events & Prophecies ---
try:
    from backend.events import events_bp
    app.register_blueprint(events_bp)
    app.logger.info("events_bp registered")
except Exception as e:
    app.logger.warning(f"events_bp not available: {e}")

# ---------- ROUTES ----------
@app.route("/", methods=["GET"])
def index():
    return jsonify({"message": "RevelaCode Backend is live"}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200

# ---------- START ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
