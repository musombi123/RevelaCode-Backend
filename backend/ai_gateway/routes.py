"""
RevelaCode AI Gateway Routes

Internal API bridge used by RevelaAI to retrieve controlled,
user-scoped context from the RevelaCode platform.

Important:
- This gateway does NOT expose MongoDB directly.
- It delegates data retrieval to existing platform services.
- Requests must be authenticated as coming from RevelaAI.
- User context is scoped to the authenticated user.
"""

from flask import Blueprint, jsonify, request

from .context import get_ai_context
from .permissions import authorize_ai_request

ai_gateway_bp = Blueprint(
    "ai_gateway",
    __name__,
)


def _get_request_payload():
    """
    Safely parse JSON request payload.
    """
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        payload = {}

    return payload


@ai_gateway_bp.route("/health", methods=["GET"])
def ai_gateway_health():
    """
    Lightweight health endpoint.

    This endpoint intentionally does not expose platform data.
    """
    return jsonify(
        {
            "status": "success",
            "service": "revelacode-ai-gateway",
            "layer": "platform",
            "message": "AI Gateway is operational",
        }
    ), 200


@ai_gateway_bp.route("/context", methods=["POST"])
def ai_context():
    """
    Main internal context endpoint.

    Expected payload:

    {
        "user_id": "...",
        "domain": "biashara",
        "message": "Why are my sales dropping?",
        "include": {
            "business": true,
            "performance": true,
            "products": true,
            "orders": true,
            "inventory": true,
            "market": true,
            "economic": true
        }
    }
    """

    payload = _get_request_payload()

    user_id = (
        payload.get("user_id")
        or payload.get("userId")
        or payload.get("user")
    )

    domain = (
        payload.get("domain")
        or payload.get("intent")
        or "general"
    )

    message = (
        payload.get("message")
        or payload.get("query")
        or ""
    ).strip()

    if not user_id:
        return jsonify(
            {
                "status": "error",
                "message": "user_id is required",
            }
        ), 400

    # ------------------------------------------------------------------
    # Service-to-service authentication
    # ------------------------------------------------------------------
    authorized, auth_error = authorize_ai_request(
        request=request,
        user_id=str(user_id),
    )

    if not authorized:
        return jsonify(
            {
                "status": "error",
                "message": auth_error or "Unauthorized",
            }
        ), 401

    # ------------------------------------------------------------------
    # Validate domain
    # ------------------------------------------------------------------
    domain = str(domain).strip().lower()

    allowed_domains = {
        "general",
        "biashara",
        "shamba",
        "elimu",
        "community",
        "study",
        "scripture",
        "technology",
        "programming",
    }

    if domain not in allowed_domains:
        domain = "general"

    # ------------------------------------------------------------------
    # Context request
    # ------------------------------------------------------------------
    include = payload.get("include")

    if not isinstance(include, dict):
        include = {}

    try:
        context = get_ai_context(
            user_id=str(user_id),
            domain=domain,
            message=message,
            include=include,
        )
    except Exception:
        # Do not expose internal implementation/database errors to AI.
        return jsonify(
            {
                "status": "error",
                "message": "Unable to retrieve ecosystem context",
            }
        ), 500

    return jsonify(
        {
            "status": "success",
            "data": context,
        }
    ), 200


@ai_gateway_bp.route("/<domain>", methods=["POST"])
def domain_context(domain):
    """
    Convenience endpoint for domain-specific context.

    Example:

        POST /api/ai/biashara

    Payload:

    {
        "user_id": "...",
        "message": "Why are my sales dropping?"
    }

    This eventually lets RevelaAI use:

        /api/ai/biashara
        /api/ai/shamba
        /api/ai/elimu
        /api/ai/community

    while all requests still pass through the same authorization
    and context layer.
    """

    payload = _get_request_payload()

    user_id = (
        payload.get("user_id")
        or payload.get("userId")
        or payload.get("user")
    )

    message = (
        payload.get("message")
        or payload.get("query")
        or ""
    ).strip()

    if not user_id:
        return jsonify(
            {
                "status": "error",
                "message": "user_id is required",
            }
        ), 400

    authorized, auth_error = authorize_ai_request(
        request=request,
        user_id=str(user_id),
    )

    if not authorized:
        return jsonify(
            {
                "status": "error",
                "message": auth_error or "Unauthorized",
            }
        ), 401

    include = payload.get("include")

    if not isinstance(include, dict):
        include = {}

    normalized_domain = str(domain).strip().lower()

    allowed_domains = {
        "general",
        "biashara",
        "shamba",
        "elimu",
        "community",
        "study",
        "scripture",
        "technology",
        "programming",
    }

    if normalized_domain not in allowed_domains:
        return jsonify(
            {
                "status": "error",
                "message": f"Unsupported AI domain: {normalized_domain}",
            }
        ), 400

    try:
        context = get_ai_context(
            user_id=str(user_id),
            domain=normalized_domain,
            message=message,
            include=include,
        )
    except Exception:
        return jsonify(
            {
                "status": "error",
                "message": "Unable to retrieve ecosystem context",
            }
        ), 500

    return jsonify(
        {
            "status": "success",
            "data": context,
        }
    ), 200