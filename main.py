# main.py

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, request
from flask_cors import CORS


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

logger = logging.getLogger("revelacode.main")


# =========================================================
# APP
# =========================================================

app = Flask(__name__)


# =========================================================
# CORS CONFIGURATION
# =========================================================

DEFAULT_FRONTEND_ORIGINS = {
    "https://revelacode-frontend.onrender.com",
    "https://www.revelacode-frontend.onrender.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost",
    "https://localhost",
}


def configured_frontend_origins() -> set[str]:
    """
    Return explicitly approved frontend origins.

    Optional Render environment variable:
        FRONTEND_ORIGINS=https://example.com,https://another.example
    """

    origins = set(DEFAULT_FRONTEND_ORIGINS)

    configured = os.getenv("FRONTEND_ORIGINS", "")

    for item in configured.split(","):
        origin = item.strip().rstrip("/")

        if origin.startswith(("https://", "http://")):
            origins.add(origin)

    return origins


FRONTEND_ORIGINS = configured_frontend_origins()

CORS_ALLOWED_METHODS = (
    "GET, POST, PUT, PATCH, DELETE, OPTIONS"
)

CORS_ALLOWED_METHODS_SET = {
    method.strip().upper()
    for method in CORS_ALLOWED_METHODS.split(",")
}

CORS_ALLOWED_HEADERS = (
    "Accept, Content-Type, Authorization, "
    "X-ADMIN-KEY, X-ADMIN-API-KEY, x-api-key"
)

CORS_ALLOWED_HEADERS_SET = {
    header.strip().lower()
    for header in CORS_ALLOWED_HEADERS.split(",")
}


CORS(
    app,
    resources={
        r"/*": {
            "origins": sorted(FRONTEND_ORIGINS),
        }
    },
    supports_credentials=True,
    allow_headers=[
        "Accept",
        "Content-Type",
        "Authorization",
        "X-ADMIN-KEY",
        "X-ADMIN-API-KEY",
        "x-api-key",
    ],
    methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
    max_age=600,
)


# =========================================================
# EXPLICIT CORS PREFLIGHT
# =========================================================

@app.before_request
def handle_cors_preflight():
    """
    Handle browser OPTIONS preflight requests before normal
    authentication and route-specific processing.

    This does not bypass authentication for actual API calls.
    """

    if request.method != "OPTIONS":
        return None

    origin = request.headers.get("Origin", "").strip().rstrip("/")

    if origin not in FRONTEND_ORIGINS:
        logger.warning(
            "Rejected CORS preflight from origin: %s",
            origin or "<missing>",
        )

        return jsonify({
            "success": False,
            "error": {
                "code": "cors_origin_not_allowed",
                "message": "This origin is not permitted.",
            },
        }), 403

    requested_method = (
        request.headers.get(
            "Access-Control-Request-Method",
            "",
        )
        .strip()
        .upper()
    )

    if (
        requested_method
        and requested_method not in CORS_ALLOWED_METHODS_SET
    ):
        return jsonify({
            "success": False,
            "error": {
                "code": "cors_method_not_allowed",
                "message": "This request method is not permitted.",
            },
        }), 403

    requested_headers = {
        header.strip().lower()
        for header in request.headers.get(
            "Access-Control-Request-Headers",
            "",
        ).split(",")
        if header.strip()
    }

    unsupported_headers = (
        requested_headers - CORS_ALLOWED_HEADERS_SET
    )

    if unsupported_headers:
        logger.warning(
            "Rejected CORS preflight with unsupported headers: %s",
            ", ".join(sorted(unsupported_headers)),
        )

        return jsonify({
            "success": False,
            "error": {
                "code": "cors_header_not_allowed",
                "message": "The request contains an unapproved header.",
                "details": {
                    "headers": sorted(unsupported_headers),
                },
            },
        }), 403

    # A successful preflight has no response body.
    return make_response("", 204)


# =========================================================
# ENSURE CORS RESPONSE HEADERS
# =========================================================

@app.after_request
def ensure_cors_response_headers(response):
    """
    Attach CORS headers to responses sent to approved origins,
    including HTTP errors returned by the application.
    """

    origin = request.headers.get("Origin", "").strip().rstrip("/")

    if origin not in FRONTEND_ORIGINS:
        return response

    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = (
        CORS_ALLOWED_METHODS
    )
    response.headers["Access-Control-Allow-Headers"] = (
        CORS_ALLOWED_HEADERS
    )
    response.headers["Vary"] = "Origin"

    if request.method == "OPTIONS":
        response.headers["Access-Control-Max-Age"] = "600"

    return response


# =========================================================
# DATABASE
# =========================================================

try:
    from backend.db import db

    logger.info("MongoDB initialized successfully")

except Exception:
    db = None

    logger.exception("MongoDB initialization failed")


# =========================================================
# ROUTE REGISTRATION HELPER
# =========================================================

def register_bp(import_path: str, bp_name: str):
    """
    Register an existing, non-critical Flask blueprint.
    Failed registrations are logged rather than hidden.
    """

    try:
        module = __import__(
            import_path,
            fromlist=[bp_name],
        )

        blueprint = getattr(module, bp_name)

        app.register_blueprint(blueprint)

        logger.info(
            "%s registered from %s",
            bp_name,
            import_path,
        )

        return True

    except Exception:
        logger.exception(
            "Registration failed: %s from %s",
            bp_name,
            import_path,
        )

        return False


# =========================================================
# EXISTING REVELACODE AUTH AND USER MODULES
# =========================================================

register_bp("backend.auth_gate", "auth_bp")
register_bp("backend.user_data", "user_bp")
register_bp("backend.account_management", "accounts_bp")
register_bp("backend.history_bp", "history_bp")


# =========================================================
# JUMUIYA PLATFORM
# =========================================================

try:
    from backend.jumuiya.integration.register import register_jumuiya

    register_jumuiya(app)

    logger.info("Jumuiya platform registered")

except Exception:
    logger.exception("Jumuiya registration failed")


# =========================================================
# REVELAAI AI GATEWAY
# =========================================================

try:
    from backend.ai_gateway import register_ai_gateway

    register_ai_gateway(app)

    logger.info("RevelaAI AI Gateway registered")

except Exception:
    logger.exception("RevelaAI AI Gateway registration failed")


# =========================================================
# STUDY PLATFORM
# =========================================================

try:
    from backend.routes.study_routes import study_bp

except Exception:
    logger.exception("CRITICAL: Study blueprint import failed")
    raise


try:
    app.register_blueprint(
        study_bp,
        url_prefix="/api/study",
    )

except Exception:
    logger.exception("CRITICAL: Study blueprint registration failed")
    raise


logger.info("Study blueprint registered with /api prefix")


# =========================================================
# ROUTE DIAGNOSTICS HELPERS
# =========================================================

def get_registered_routes(prefix: str | None = None):
    routes = []

    for rule in app.url_map.iter_rules():
        if prefix is not None and not rule.rule.startswith(prefix):
            continue

        methods = sorted(
            method
            for method in rule.methods
            if method not in {"HEAD", "OPTIONS"}
        )

        routes.append({
            "rule": rule.rule,
            "endpoint": rule.endpoint,
            "methods": methods,
        })

    return sorted(routes, key=lambda item: item["rule"])


def study_route_exists(route: str) -> bool:
    return any(
        rule.rule == route
        for rule in app.url_map.iter_rules()
    )


# =========================================================
# STUDY ROUTE VERIFICATION
# =========================================================

STUDY_MATERIALS_ROUTE = "/api/study/materials"
STUDY_HEALTH_ROUTE = "/api/study/health"

logger.info(
    "Study materials route registered: %s",
    study_route_exists(STUDY_MATERIALS_ROUTE),
)

logger.info(
    "Study health route registered: %s",
    study_route_exists(STUDY_HEALTH_ROUTE),
)

for route in get_registered_routes("/api/study"):
    logger.info(
        "Study route: %s %s",
        ",".join(route["methods"]),
        route["rule"],
    )


# =========================================================
# OTHER APPLICATION ROUTES
# =========================================================

register_bp("backend.routes.events_routes", "events_bp")
register_bp("backend.routes.docs_routes", "docs_bp")
register_bp("backend.routes.prophecy_routes", "prophecy_bp")
register_bp("backend.routes.domain_routes", "domain_bp")
register_bp("backend.routes.notifications_routes", "notifications_bp")
register_bp("backend.guest_decode_limiter", "guest_bp")


# =========================================================
# ADMIN
# =========================================================

try:
    from backend.routes.admin_routes import admin_bp

    app.register_blueprint(
        admin_bp,
        url_prefix="/api",
    )

    logger.info("Admin blueprint registered")

except Exception:
    logger.exception("Admin blueprint registration failed")


# =========================================================
# SUPPORT
# =========================================================

try:
    from backend.routes.support_routes import support_bp

    app.register_blueprint(
        support_bp,
        url_prefix="/api/support",
    )

    logger.info("Support blueprint registered")

except Exception:
    logger.exception("Support blueprint registration failed")


# =========================================================
# PUBLIC ROUTES
# =========================================================

register_bp("backend.routes.public_routes", "public_bp")


# =========================================================
# ROOT
# =========================================================

@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "message": "RevelaCode Backend is live",
        "status": "ok",
    }), 200


# =========================================================
# HEALTH
# =========================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "mongo_connected": db is not None,
        "mongo_uri_set": bool(os.getenv("MONGO_URI")),
        "jumuiya": True,
        "cors": {
            "configured": True,
            "origins": sorted(FRONTEND_ORIGINS),
            "preflight_handler": True,
        },
        "study": {
            "registered": study_route_exists(
                STUDY_MATERIALS_ROUTE
            ),
            "health_route": study_route_exists(
                STUDY_HEALTH_ROUTE
            ),
            "materials_route": study_route_exists(
                STUDY_MATERIALS_ROUTE
            ),
        },
    }), 200


# =========================================================
# ROUTE DIAGNOSTICS
# =========================================================

@app.route("/api/diagnostics/routes", methods=["GET"])
def diagnostics_routes():
    return jsonify({
        "success": True,
        "study": {
            "registered": study_route_exists(
                STUDY_MATERIALS_ROUTE
            ),
            "health": study_route_exists(
                STUDY_HEALTH_ROUTE
            ),
            "materials": study_route_exists(
                STUDY_MATERIALS_ROUTE
            ),
            "routes": get_registered_routes("/api/study"),
        },
        "all_routes": get_registered_routes(),
    }), 200


# =========================================================
# SDA Q3 2026 IMPORT
# =========================================================

try:
    from backend.study.import_sda_q3_2026 import import_q3

except Exception:
    logger.exception("SDA importer import failed")
    import_q3 = None


def maybe_import_sda_q3_2026():
    enabled = os.getenv(
        "IMPORT_SDA_Q3_2026",
        "false",
    ).strip().lower()

    if enabled != "true":
        logger.info("SDA Q3 2026 importer disabled")
        return

    if db is None:
        logger.error(
            "SDA importer cannot run because MongoDB is unavailable"
        )
        return

    if import_q3 is None:
        logger.error("SDA importer could not be loaded")
        return

    logger.info("Starting SDA Q3 2026 importer")

    try:
        result = import_q3()

        requested = result.get("lessons_requested", 0)
        successful = result.get("successful", 0)
        failed = result.get("failed", 0)

        logger.info(
            "SDA import finished: requested=%s successful=%s failed=%s",
            requested,
            successful,
            failed,
        )

        if failed:
            logger.warning("SDA import completed with failures")
        else:
            logger.info("SDA Q3 2026 imported successfully")

    except Exception:
        logger.exception("SDA Q3 2026 importer failed")


# =========================================================
# SDA STARTUP THREAD
# =========================================================

def start_sda_importer():
    thread = threading.Thread(
        target=maybe_import_sda_q3_2026,
        name="SDA-Q3-2026-Importer",
        daemon=True,
    )

    thread.start()

    logger.info("SDA importer thread started")


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
                from backend.daily_runner import run_pipeline

                logger.info("Running daily_runner pipeline")

                current_dir = os.getcwd()

                try:
                    os.chdir(backend_dir)
                    run_pipeline()
                    last_run_date = today

                finally:
                    os.chdir(current_dir)

            except Exception:
                logger.exception("Daily runner failed")

        time.sleep(3600)


# =========================================================
# BACKGROUND JOB CONTROL
# =========================================================

_background_jobs_started = False
_background_jobs_lock = threading.Lock()


def start_background_jobs():
    global _background_jobs_started

    with _background_jobs_lock:
        if _background_jobs_started:
            logger.info("Background jobs already started")
            return

        _background_jobs_started = True

    start_sda_importer()

    daily_thread = threading.Thread(
        target=daily_runner_loop,
        name="Daily-Runner",
        daemon=True,
    )

    daily_thread.start()

    logger.info("Daily runner thread started")


# =========================================================
# START BACKGROUND JOBS
# =========================================================

start_background_jobs()


# =========================================================
# MANUAL SERVER START
# =========================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    logger.info("Starting server on port %s", port)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=os.getenv("FLASK_ENV") != "production",
        use_reloader=False,
    )