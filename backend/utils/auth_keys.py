"""Role resolution for privileged API routes.

Support/admin frontends authenticate with RevelaCode Bearer JWTs. Legacy
server-to-server integrations may still use the X-API-KEY header.
"""

from __future__ import annotations

import hmac
import os

import jwt


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
    if not JWT_SECRET or not authorization:
        return None

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        return None

    try:
        payload = jwt.decode(
            token.strip(),
            JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["exp"]},
        )
    except jwt.InvalidTokenError:
        return None

    role = payload.get("role")
    if role in {"admin", "support"}:
        return role

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

    return None
