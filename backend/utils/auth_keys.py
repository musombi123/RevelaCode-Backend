"""Role resolution for privileged API routes.

Support/admin frontends authenticate with RevelaCode Bearer JWTs. Legacy
server-to-server integrations may still use the X-API-KEY header.
"""

from __future__ import annotations

import hmac
import logging
import os

import jwt

logger = logging.getLogger(__name__)


ADMIN_KEY = os.getenv("ADMIN_API_KEY")
SUPPORT_KEY = os.getenv("SUPPORT_API_KEY")
JWT_SECRET = os.getenv("JWT_SECRET")


def _matches_configured_key(provided: str | None, configured: str | None) -> bool:
    """Compare configured API keys without logging or leaking comparisons."""
    if not provided or not configured:
        return False

    return hmac.compare_digest(
        provided.encode("utf-8"),
        configured.encode("utf-8"),
    )


def _role_from_bearer(authorization: str) -> str | None:
    """Return a privileged role only from a valid signed JWT."""
    if not authorization:
        return None

    if not JWT_SECRET:
        logger.error("Privileged API JWT rejected: JWT_SECRET is not configured.")
        return None

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        logger.warning("Privileged API auth received an unsupported or empty Authorization scheme.")
        return None

    try:
        payload = jwt.decode(
            token.strip(),
            JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        logger.warning("Privileged API JWT rejected: token expired.")
        return None
    except jwt.InvalidTokenError as error:
        # Never log the JWT itself or the signing secret.
        logger.warning("Privileged API JWT rejected: %s.", type(error).__name__)
        return None

    # Normalize claim values because older accounts may store roles
    # with mixed casing or surrounding whitespace.
    candidates = [payload.get("role")]
    roles = payload.get("roles", [])
    if isinstance(roles, str):
        candidates.append(roles)
    elif isinstance(roles, (list, tuple, set)):
        candidates.extend(roles)

    for candidate in candidates:
        role = str(candidate or "").strip().lower()
        if role in {"admin", "support"}:
            return role

    logger.warning(
        "Privileged API JWT is valid but has no admin/support role claim "
        "(role_claim_present=%s, roles_claim_type=%s).",
        bool(payload.get("role")),
        type(roles).__name__,
    )
    return None


def get_role(req) -> str | None:
    """Resolve an admin/support role from a verified JWT or legacy API key.

    JWT authentication is preferred for browser sessions. API keys remain
    supported for existing trusted integrations; absent environment keys can
    never accidentally authenticate a request.
    """
    role = _role_from_bearer(
        req.headers.get("Authorization", "").strip()
    )
    if role:
        return role

    key = req.headers.get("X-API-KEY", "")

    if _matches_configured_key(key, ADMIN_KEY):
        return "admin"

    if _matches_configured_key(key, SUPPORT_KEY):
        return "support"

    logger.warning(
        "Privileged API authorization denied "
        "(authorization_header_present=%s, api_key_header_present=%s, jwt_secret_configured=%s).",
        bool(req.headers.get("Authorization")),
        bool(key),
        bool(JWT_SECRET),
    )
    return None
