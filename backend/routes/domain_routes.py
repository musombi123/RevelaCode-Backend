import pkgutil
import importlib

from flask import Blueprint, request, jsonify, g
from backend import domains
from backend.services.audit_logger import log_domain_event
from backend.services.billing_guard import enforce_domain_policy
from backend.services.ai_router import ask_ai

# ---------------- BLUEPRINT ----------------
domain_bp = Blueprint("domains", __name__)

# ---------------- DOMAIN REGISTRY ----------------
DOMAIN_REGISTRY = {}

def register_domain(name, handler, use_ai=False):
    """
    Register a domain with optional AI usage.
    use_ai: True if the domain should call AI for queries
    """
    DOMAIN_REGISTRY[name] = {"handler": handler, "use_ai": use_ai}

def get_domain(name):
    return DOMAIN_REGISTRY.get(name)

def list_domains():
    return list(DOMAIN_REGISTRY.keys())

def auto_load_domains():
    """
    Dynamically load all domains with service.py inside backend/domains/
    """
    for _, module_name, _ in pkgutil.iter_modules(domains.__path__):
        importlib.import_module(f"backend.domains.{module_name}.service")
        print(f"Loaded domain: {module_name}")

# Auto-load all domains when blueprint is imported
auto_load_domains()

# ---------------- ROUTES ----------------
@domain_bp.route("/domains", methods=["GET"])
def domains_route():
    """List all available domains"""
    return jsonify({"available_domains": list_domains()})

@domain_bp.route("/domains/<domain_name>", methods=["POST"])
def handle_domain(domain_name):
    """Handle a POST query to a specific domain"""
    domain_info = get_domain(domain_name)
    if not domain_info:
        return jsonify({"error": "Domain not found"}), 404

    data = request.json or {}
    query = data.get("query")

    # Default user context
    user = getattr(g, "user", {"id": "guest", "is_premium": False})

    # Enforce billing / usage rules
    enforce_domain_policy(domain_name, user)

    try:
        # Use AI only if the domain is flagged to use AI
        if domain_info.get("use_ai"):
            result = ask_ai(prompt=query, domain=domain_name, context=user)
        else:
            result = domain_info["handler"](query, user_context=user)

        # Log successful event
        log_domain_event(
            user_id=user.get("id"),
            domain=domain_name,
            query=query,
            status="success"
        )

        return jsonify(result)

    except Exception as e:
        # Log failed event
        log_domain_event(
            user_id=user.get("id"),
            domain=domain_name,
            query=query,
            status="error",
            metadata={"error": str(e)}
        )
        return jsonify({"error": str(e)}), 500
