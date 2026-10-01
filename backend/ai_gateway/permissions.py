"""
RevelaCode AI Gateway Permissions

Security layer for the internal RevelaCode <-> RevelaAI bridge.

The gateway is intended for service-to-service communication.

Expected header:

    X-REVELAAI-SERVICE-KEY: <shared-secret>

The shared secret must be configured in the RevelaCode backend
environment as:

    REVELAAI_SERVICE_KEY

Important:
- Never expose this key to the frontend.
- Never log the key.
- Never accept a user JWT as a replacement for the service key.
- User data remains scoped by the supplied user_id.
"""

from __future__ import annotations

import hmac
import os
from typing import Any


# =========================================================
# CONFIGURATION
# =========================================================

SERVICE_KEY_ENV = "REVELAAI_SERVICE_KEY"

SERVICE_KEY_HEADER = "X-REVELAAI-SERVICE-KEY"


# =========================================================
# CONFIG HELPERS
# =========================================================

def get_configured_service_key() -> str:
    """
    Return the configured RevelaAI service key.

    An empty string means the key has not been configured.
    """

    return (
        os.getenv(
            SERVICE_KEY_ENV,
            "",
        )
        .strip()
    )


# =========================================================
# HEADER HELPERS
# =========================================================

def get_presented_service_key(
    request: Any,
) -> str:
    """
    Read the service key supplied by the caller.
    """

    if request is None:
        return ""

    value = request.headers.get(
        SERVICE_KEY_HEADER,
        "",
    )

    if not isinstance(
        value,
        str,
    ):
        return ""

    return value.strip()


# =========================================================
# SERVICE AUTHENTICATION
# =========================================================

def verify_service_key(
    request: Any,
) -> bool:
    """
    Verify that the incoming request contains the correct
    RevelaAI service credential.

    Uses hmac.compare_digest() to avoid ordinary string
    comparison for secret verification.
    """

    configured_key = (
        get_configured_service_key()
    )

    presented_key = (
        get_presented_service_key(
            request
        )
    )

    # Security-first behavior:
    # a missing server-side secret means the gateway
    # must not authenticate any service request.
    if not configured_key:
        return False

    if not presented_key:
        return False

    return hmac.compare_digest(
        presented_key,
        configured_key,
    )


# =========================================================
# USER ID VALIDATION
# =========================================================

def validate_user_id(
    user_id: Any,
) -> tuple[bool, str | None]:
    """
    Validate the user identifier supplied by RevelaAI.

    The gateway does not invent a user ID.

    Returns:

        (True, None)

    or:

        (False, "error_code")
    """

    if user_id is None:
        return (
            False,
            "missing_user_id",
        )

    if isinstance(
        user_id,
        bool,
    ):
        return (
            False,
            "invalid_user_id",
        )

    value = str(
        user_id
    ).strip()

    if not value:
        return (
            False,
            "invalid_user_id",
        )

    # Keep the identifier bounded so malformed payloads
    # cannot create unnecessarily large request values.
    if len(value) > 128:
        return (
            False,
            "invalid_user_id",
        )

    return (
        True,
        None,
    )


# =========================================================
# INTERNAL REQUEST AUTHORIZATION
# =========================================================

def authorize_ai_request(
    request: Any,
    user_id: Any = None,
) -> tuple[bool, str | None]:
    """
    Authorize an internal RevelaAI request.

    Authorization requires BOTH:

        1. A valid REVELAAI_SERVICE_KEY
        2. A usable user_id

    The service key proves:

        "This request is coming from an authorized
         RevelaAI service."

    The user_id determines:

        "Which RevelaCode account's data may be retrieved."

    Returns:

        (True, None)

    on success.

    Returns:

        (False, "error_code")

    on failure.
    """

    # -----------------------------------------------------
    # Service authentication
    # -----------------------------------------------------

    if not verify_service_key(
        request
    ):
        return (
            False,
            "invalid_service_credentials",
        )

    # -----------------------------------------------------
    # User scope
    # -----------------------------------------------------

    valid_user, user_error = (
        validate_user_id(
            user_id
        )
    )

    if not valid_user:

        return (
            False,
            user_error or "invalid_user_id",
        )

    return (
        True,
        None,
    )


# =========================================================
# OPTIONAL FLASK DECORATOR
# =========================================================

def require_ai_service(fn):
    """
    Optional decorator for future AI Gateway routes.

    Example:

        @require_ai_service
        def some_internal_route():
            ...

    This decorator performs service authentication only.

    Routes that accept user_id should still validate and scope
    that identifier explicitly.
    """

    from functools import wraps
    from flask import request

    @wraps(fn)
    def wrapper(
        *args,
        **kwargs,
    ):

        if not verify_service_key(
            request
        ):

            return {
                "status": "error",
                "message": "Unauthorized AI service request.",
            }, 401

        return fn(
            *args,
            **kwargs,
        )

    return wrapper


# =========================================================
# CONFIGURATION STATUS
# =========================================================

def service_key_configured() -> bool:
    """
    Return whether the server has a RevelaAI service key.

    This is useful for diagnostics and tests.

    Do NOT return the actual secret.
    """

    return bool(
        get_configured_service_key()
    )