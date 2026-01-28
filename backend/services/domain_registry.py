from flask import Blueprint, request, jsonify, g
import importlib
import pkgutil
from backend import domains  # domains folder inside backend

domain_bp = Blueprint("domains", __name__)

# ---------------- DOMAIN REGISTRY ----------------
DOMAIN_REGISTRY = {}

def register_domain(name, handler):
    DOMAIN_REGISTRY[name] = handler

def get_domain(name):
    return DOMAIN_REGISTRY.get(name)

def list_domains():
    return list(DOMAIN_REGISTRY.keys())

def auto_load_domains():
    """
    Dynamically load all domains with service.py
    """
    for _, module_name, _ in pkgutil.iter_modules(domains.__path__):
        importlib.import_module(f"backend.domains.{module_name}.service")
        print(f"Loaded domain: {module_name}")

# Load all domains when blueprint is imported
auto_load_domains()

# ---------------- ROUTES ----------------
@domain_bp.route("/domains", methods=["GET"])
def domains_route():
    return jsonify({"available_domains": list_domains()})

@domain_bp.route("/domains/<domain_name>", methods=["POST"])
def handle_domain(domain_name):
    handler = get_domain(domain_name)
    if not handler:
        return jsonify({"error": "Domain not found"}), 404

    data = request.json
    query = data.get("query")
    user = getattr(g, "user", {"id": "guest", "is_premium": False})

    # Optional: enforce billing / audit logic
    # enforce_domain_policy(domain_name, user)
    # log_domain_event(user_id=user.get("id"), domain=domain_name, query=query, status="success")

    try:
        result = handler(query, user_context=user)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
