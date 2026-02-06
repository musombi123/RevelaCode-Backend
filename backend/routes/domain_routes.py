# backend/routes/domain_routes.py
import pkgutil
import importlib
import logging

from flask import Blueprint, request, jsonify, g

from backend import domains
from backend.services.audit_logger import log_domain_event
from backend.services.billing_guard import enforce_domain_policy
from backend.services.ai_router import ask_ai

logger = logging.getLogger(__name__)

# ---------------- BLUEPRINT ----------------
domain_bp = Blueprint("domains", __name__)

# ---------------- DOMAIN REGISTRY ----------------
DOMAIN_REGISTRY = {}

def register_domain(name, handler, use_ai=False):
    """
    Register a domain with optional AI usage.
    """
    if not callable(handler):
        raise ValueError(f"Handler for domain '{name}' must be callable")

    DOMAIN_REGISTRY[name] = {
        "handler": handler,
        "use_ai": bool(use_ai)
    }

def get_domain(name):
    return DOMAIN_REGISTRY.get(name)

def list_domains():
    return sorted(DOMAIN_REGISTRY.keys())

# ---------------- AUTO LOADER ----------------
def auto_load_domains():
    """
    Dynamically load all backend/domains/*/service.py files
    without crashing the app on failure.
    """
    for _, module_name, is_pkg in pkgutil.iter_modules(domains.__path__):
        if not is_pkg:
            continue

        module_path = f"backend.domains.{module_name}.service"
        try:
            importlib.import_module(module_path)
            logger.info(f"✅ Loaded domain: {module_name}")
        except ModuleNotFoundError:
            logger.warning(f"⚠️ No service.py for domain '{module_name}'")
        except Exception as e:
            logger.error(f"❌ Failed to load domain '{module_name}': {e}")

# Load domains once at import time
auto_load_domains()

# ---------------- ROUTES ----------------
@domain_bp.route("/domains", methods=["GET"])
def domains_route():
    """List all available domains"""
    return jsonify({
        "available_domains": list_domains(),
        "count": len(DOMAIN_REGISTRY)
    })

@domain_bp.route("/domains/<domain_name>", methods=["POST"])
def handle_domain(domain_name):
    domain_info = get_domain(domain_name)
    if not domain_info:
        return jsonify({"error": "Domain not found"}), 404

    data = request.get_json(silent=True) or {}
    query = data.get("query")

    if not query:
        return jsonify({"error": "Missing 'query'"}), 400

    # User context (guest-safe)
    user = getattr(g, "user", None) or {
        "id": "guest",
        "is_premium": False
    }

    # Enforce billing / usage rules
    enforce_domain_policy(domain_name, user)

    try:
        if domain_info["use_ai"]:
            result = ask_ai(
                prompt=query,
                domain=domain_name,
                context=user
            )
        else:
            result = domain_info["handler"](
                query,
                user_context=user
            )

        log_domain_event(
            user_id=user["id"],
            domain=domain_name,
            query=query,
            status="success"
        )

        return jsonify(result), 200

    except Exception as e:
        logger.exception("Domain execution failed")

        log_domain_event(
            user_id=user["id"],
            domain=domain_name,
            query=query,
            status="error",
            metadata={"error": str(e)}
        )

        return jsonify({
            "error": "Domain execution failed",
            "details": str(e)
        }), 500
