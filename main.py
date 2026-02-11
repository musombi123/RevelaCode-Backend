# backend/main.py
import os
import logging
import threading
import time
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# ---------- ENV ----------
load_dotenv()

# ---------- LOGGING ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

if os.getenv("FLASK_ENV") != "production":
    logger.info(f"MONGO_URI loaded: {bool(os.getenv('MONGO_URI'))}")

# ---------- APP ----------
app = Flask(__name__)

CORS(
    app,
    resources={
        r"/*": {
            "origins": [
                "https://revelacode-frontend.onrender.com",
                "https://www.revelacode-frontend.onrender.com",
            ]
        }
    },
    supports_credentials=True,
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-ADMIN-KEY",
        "x-api-key",
        "X-ADMIN-API-KEY",
    ],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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

# ---------- AUTH & USER MODULES ----------
register_bp("backend.auth_gate", "auth_bp")
register_bp("backend.user_data", "user_bp")
register_bp("backend.account_management", "accounts_bp")
register_bp("backend.history_bp", "history_bp")


# ---------- ROUTES ----------
register_bp("backend.routes.events_routes", "events_bp")
register_bp("backend.routes.docs_routes", "docs_bp")
register_bp("backend.routes.prophecy_routes", "prophecy_bp")
register_bp("backend.routes.domain_routes", "domain_bp")
register_bp("backend.routes.notifications_routes", "notifications_bp")  # optional
register_bp("backend.guest_decode_limiter", "guest_bp")  # optional

# ---------- ADMIN / SUPPORT / PUBLIC ----------
try:
    from backend.routes.admin_routes import admin_bp
    app.register_blueprint(admin_bp, url_prefix="/api")
    logger.info("admin_bp registered with /api prefix")
except Exception as e:
    logger.warning(f"admin_bp registration failed: {e}")

register_bp("backend.routes.support_routes", "support_bp", url_prefix="/api/support")
register_bp("backend.routes.public_routes", "public_bp")

# ---------- HEALTH ENDPOINTS ----------
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
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__)))

    while True:
        today = datetime.now().date()
        if last_run_date != today:
            try:
                from backend.daily_runner import run_pipeline
                logger.info("⏰ Running daily_runner pipeline")

                # ensure working dir is backend
                current_dir = os.getcwd()
                os.chdir(backend_dir)
                try:
                    run_pipeline()
                finally:
                    os.chdir(current_dir)

                last_run_date = today

            except Exception as e:
                logger.error(f"Daily runner failed: {e}")

        time.sleep(3600)  # check once per hour

# ---------- START SERVER ----------
if __name__ == "__main__":
    # Start daily runner in background
    threading.Thread(target=daily_runner_loop, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting server on port {port}")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=os.getenv("FLASK_ENV") != "production",
        use_reloader=False
    )
