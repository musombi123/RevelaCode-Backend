"""Current-role resolution for privileged API routes.

Browser JWTs establish identity only; the current RevelaCode user record
establishes role and account status. Configured API keys remain supported
only for existing trusted server-to-server integrations.
"""
from __future__ import annotations

import hmac
import logging
import os

from backend.utils.current_role_auth import (
    PLATFORM_ADMIN_ROLES,
    SUPPORT_ROLES,
    resolve_current_actor,
)

logger = logging.getLogger(__name__)

ADMIN_KEY = os.getenv("ADMIN_API_KEY")
SUPPORT_KEY = os.getenv("SUPPORT_API_KEY")


def _matches_configured_key(provided: str | None, configured: str | None) -> bool:
    if not provided or not configured:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), configured.encode("utf-8"))


def get_role(req) -> str | None:
    """Resolve the caller's current stored privileged role or trusted API key."""
    authorization = str(req.headers.get("Authorization") or "").strip()
    if authorization:
        actor, error, _status = resolve_current_actor(req)
        if actor and not error:
            roles = set(actor.get("roles") or [])
            roles.add(str(actor.get("role") or "").strip().casefold())
            if roles.intersection(PLATFORM_ADMIN_ROLES):
                # Preserve the legacy decorator's canonical admin label.
                return "admin"
            if "support_admin" in roles:
                return "support_admin"
            if "support" in roles:
                return "support"
        # A supplied browser JWT must not gain access from a role claim alone.
        # Do not log tokens or claim values.

    key = str(req.headers.get("X-API-KEY") or "")
    if _matches_configured_key(key, ADMIN_KEY):
        return "admin"
    if _matches_configured_key(key, SUPPORT_KEY):
        return "support"

    logger.warning(
        "Privileged API authorization denied "
        "(authorization_header_present=%s, api_key_header_present=%s).",
        bool(authorization),
        bool(key),
    )
    return None
