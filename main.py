# backend/main.py

import os
import logging
import threading
import time
from datetime import datetime

from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from backend.study.import_sda_q3_2026 import import_q3


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("main")


if os.getenv("FLASK_ENV") != "production":
    logger.info(
        f"MONGO_URI loaded: {bool(os.getenv('MONGO_URI'))}"
    )


# =========================================================
# APP
# =========================================================

app = Flask(__name__)


# =========================================================
# CORS
# =========================================================

CORS(
    app,
    resources={
        r"/*": {
            "origins": [
                "https://revelacode-frontend.onrender.com",
                "https://www.revelacode-frontend.onrender.com",
                "https://localhost",
                "http://localhost",
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
    methods=[
        "GET",
        "POST",
        "PUT",
        "DELETE",
        "OPTIONS",
    ],
)


# =========================================================
# DATABASE INIT
# =========================================================

try:
    from backend.db import db

    logger.info(
        "MongoDB initialized successfully"
    )

except Exception as e:

    logger.warning(
        f"MongoDB not available, running without DB: {e}"
    )

    db = None


# =========================================================
# STUDY BLUEPRINT
# =========================================================

try:

    from backend.routes.study_routes import study_bp

    app.register_blueprint(
        study_bp
    )

    logger.info(
        "study_bp registered"
    )

except Exception as e:

    logger.exception(
        f"study_bp registration failed: {e}"
    )




# =========================================================
# BLUEPRINT REGISTRATION HELPER
# =========================================================

def register_bp(
    import_path: str,
    bp_name: str,
):
    try:

        module = __import__(
            import_path,
            fromlist=[bp_name],
        )

        bp = getattr(
            module,
            bp_name,
        )

        app.register_blueprint(
            bp
        )

        logger.info(
            f"{bp_name} registered ({import_path})"
        )

    except Exception as e:

        logger.warning(
            f"{bp_name} not available "
            f"from {import_path}: {e}"
        )


# =========================================================
# AUTH & USER MODULES
# =========================================================

register_bp(
    "backend.auth_gate",
    "auth_bp",
)

register_bp(
    "backend.user_data",
    "user_bp",
)

register_bp(
    "backend.account_management",
    "accounts_bp",
)

register_bp(
    "backend.history_bp",
    "history_bp",
)

# =========================================================
# JUMUIYA PLATFORM
# =========================================================

try:
    from backend.jumuiya.integration.register import register_jumuiya

    register_jumuiya(app)

    logger.info(
        "✅ Jumuiya platform registered"
    )

except Exception as e:

    logger.exception(
        "❌ Jumuiya registration failed: %s",
        e,
    )

# =========================================================
# APPLICATION ROUTES
# =========================================================

register_bp(
    "backend.routes.events_routes",
    "events_bp",
)

register_bp(
    "backend.routes.docs_routes",
    "docs_bp",
)

register_bp(
    "backend.routes.prophecy_routes",
    "prophecy_bp",
)

register_bp(
    "backend.routes.domain_routes",
    "domain_bp",
)

register_bp(
    "backend.routes.notifications_routes",
    "notifications_bp",
)

register_bp(
    "backend.guest_decode_limiter",
    "guest_bp",
)


# =========================================================
# ADMIN / SUPPORT / PUBLIC
# =========================================================

try:

    from backend.routes.admin_routes import admin_bp

    app.register_blueprint(
        admin_bp,
        url_prefix="/api",
    )

    logger.info(
        "admin_bp registered with /api prefix"
    )

except Exception as e:

    logger.warning(
        f"admin_bp registration failed: {e}"
    )


try:

    from backend.routes.support_routes import support_bp

    app.register_blueprint(
        support_bp,
        url_prefix="/api/support",
    )

    logger.info(
        "support_bp registered with /api/support prefix"
    )

except Exception as e:

    logger.warning(
        f"support_bp registration failed: {e}"
    )


register_bp(
    "backend.routes.public_routes",
    "public_bp",
)


# =========================================================
# HEALTH ENDPOINTS
# =========================================================

@app.route(
    "/",
    methods=["GET"],
)
def index():

    return jsonify({
        "message": "RevelaCode Backend is live",
        "status": "ok",
    }), 200


@app.route(
    "/health",
    methods=["GET"],
)
def health():

    return jsonify({
        "ok": True,
        "mongo_connected": db is not None,
        "mongo_uri_set": bool(
            os.getenv("MONGO_URI")
        ),
    }), 200


# =========================================================
# SDA Q3 2026 IMPORT
# =========================================================

def maybe_import_sda_q3_2026():
    """
    Import SDA Q3 2026 lessons when explicitly enabled.

    Render environment variable:

        IMPORT_SDA_Q3_2026=true

    Once the import succeeds, set the environment
    variable to false/remove it.
    """

    enabled = os.getenv(
        "IMPORT_SDA_Q3_2026",
        "false",
    ).strip().lower()

    if enabled != "true":

        logger.info(
            "ℹ SDA Q3 2026 importer disabled."
        )

        return

    if db is None:

        logger.error(
            "❌ SDA importer cannot run because "
            "MongoDB is not initialized."
        )

        return

    logger.info(
        "🚀 Starting SDA Q3 2026 importer..."
    )

    try:

        result = import_q3()

        logger.info(
            "✅ SDA Q3 2026 import finished | "
            "requested=%s | successful=%s | failed=%s",
            result.get(
                "lessons_requested",
                0,
            ),
            result.get(
                "successful",
                0,
            ),
            result.get(
                "failed",
                0,
            ),
        )

        if result.get(
            "failed",
            0,
        ) > 0:

            logger.warning(
                "⚠ SDA Q3 2026 import completed "
                "with failures."
            )

        else:

            logger.info(
                "🎉 SDA Q3 2026 imported successfully."
            )

    except Exception:

        logger.exception(
            "❌ SDA Q3 2026 importer failed."
        )


# =========================================================
# SDA STARTUP THREAD
# =========================================================

def start_sda_importer():

    """
    Run the SDA import outside Flask's main thread.

    This allows Render to bind the web port while
    the importer is working.
    """

    thread = threading.Thread(
        target=maybe_import_sda_q3_2026,
        name="SDA-Q3-2026-Importer",
        daemon=True,
    )

    thread.start()

    logger.info(
        "🧵 SDA Q3 2026 importer thread started."
    )


# =========================================================
# DAILY RUNNER
# =========================================================

def daily_runner_loop():

    last_run_date = None

    backend_dir = os.path.abspath(
        os.path.dirname(__file__)
    )

    while True:

        today = datetime.now().date()

        if last_run_date != today:

            try:

                from backend.daily_runner import (
                    run_pipeline
                )

                logger.info(
                    "⏰ Running daily_runner pipeline"
                )

                current_dir = os.getcwd()

                os.chdir(
                    backend_dir
                )

                try:

                    run_pipeline()

                finally:

                    os.chdir(
                        current_dir
                    )

                last_run_date = today

            except Exception as e:

                logger.exception(
                    f"Daily runner failed: {e}"
                )

        time.sleep(
            3600
        )


# =========================================================
# SERVER START
# =========================================================

if __name__ == "__main__":

    # -----------------------------------------------------
    # SDA ONE-TIME IMPORT
    # -----------------------------------------------------

    start_sda_importer()

    # -----------------------------------------------------
    # DAILY RUNNER
    # -----------------------------------------------------

    threading.Thread(
        target=daily_runner_loop,
        name="Daily-Runner",
        daemon=True,
    ).start()

    # -----------------------------------------------------
    # PORT
    # -----------------------------------------------------

    port = int(
        os.environ.get(
            "PORT",
            5000,
        )
    )

    logger.info(
        f"Starting server on port {port}"
    )

    # -----------------------------------------------------
    # FLASK
    # -----------------------------------------------------

    app.run(
        host="0.0.0.0",
        port=port,
        debug=(
            os.getenv(
                "FLASK_ENV"
            ) != "production"
        ),
        use_reloader=False,
    )
