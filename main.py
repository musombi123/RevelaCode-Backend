# backend/main.py
from flask import Flask, jsonify
from flask_cors import CORS
import os
import logging
from dotenv import load_dotenv
import threading
import time
from datetime import datetime


# ---------- ENV ----------
load_dotenv()

# ---------- LOGGING ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

# ✅ SILENT IN PRODUCTION, SAFE IN DEV
if os.getenv("FLASK_ENV") != "production":
    logger.info(f"MONGO_URI loaded: {bool(os.getenv('MONGO_URI'))}")

# ---------- APP ----------
app = Flask(__name__)

CORS(
    app,
    supports_credentials=True,
    resources={
        r"/*": {
            "origins": [
                "https://revelacode-frontend.onrender.com",
                "https://www.revelacode-frontend.onrender.com"
            ],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-ADMIN-KEY"]
        }
    }
)


# ---------- DB INIT (OPTIONAL / SAFE) ----------
try:
    from backend.db import db
    logger.info("MongoDB initialized successfully")
except Exception as e:
    logger.warning(f"MongoDB not available, running without DB: {e}")
    db = None

# ---------- BLUEPRINT REGISTRATION HELPER ----------
def register_bp(import_path: str, bp_name: str):
    try:
        module = __import__(import_path, fromlist=[bp_name])
        bp = getattr(module, bp_name)
        app.register_blueprint(bp)
        logger.info(f"{bp_name} registered ({import_path})")
    except Exception as e:
        logger.warning(f"{bp_name} not available from {import_path}: {e}")

# ---------- AUTH & USERS ----------
register_bp("backend.auth_gate", "auth_bp")
register_bp("backend.user_data", "user_bp")  # ✅ Corrected

# ---------- ROUTES (backend/routes/) ----------
register_bp("backend.routes.events_routes", "events_bp")
register_bp("backend.routes.docs_routes", "docs_bp")
register_bp("backend.routes.prophecy_routes", "prophecy_bp")

# ---------- OPTIONAL / FUTURE ----------
register_bp("backend.guest_decode_limiter", "guest_bp")
register_bp("backend.routes.notifications_routes", "notifications_bp")

# ---------- ADMIN / SUPPORT / PUBLIC ----------
register_bp("backend.routes.admin_routes", "admin_bp")
register_bp("backend.routes.support_routes", "support_bp")
register_bp("backend.routes.public_routes", "public_bp")

# ---------- HEALTH ----------
@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "message": "RevelaCode Backend is live",
        "status": "ok"
    }), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "mongo_connected": db is not None,
        "mongo_uri_set": bool(os.getenv("MONGO_URI"))
    }), 200

# ---------- DAILY RUNNER (BACKGROUND) ----------
def daily_runner_loop():
    last_run_date = None

    while True:
        now = datetime.now().date()

        if last_run_date != now:
            try:
                from backend.daily_runner import run_pipeline
                logger.info("⏰ Running daily_runner pipeline")
                run_pipeline()
                last_run_date = now
            except Exception as e:
                logger.error(f"Daily runner failed: {e}")

        time.sleep(3600)  # check once per hour

# ---------- START ----------
if __name__ == "__main__":
    threading.Thread(target=daily_runner_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
