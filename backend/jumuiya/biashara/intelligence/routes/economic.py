"""
Jumuiya / Biashara - Live Economic Intelligence Routes

Exposes the live economic-data service to the Biashara frontend.

Endpoints:
    GET  /health
    GET  /indicators
    GET  /status
    POST /refresh

The route layer deliberately contains no source-specific scraping logic.

All fetching, validation, normalization, caching, and source handling
belongs in:

    services/economic_data_service.py
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import (
    require_authenticated,
)
from backend.jumuiya.core.responses import ok

from backend.jumuiya.biashara.intelligence.services import (
    economic_data_service,
)


# =========================================================
# BLUEPRINT
# =========================================================

economic_bp = Blueprint(
    "jumuiya_biashara_economic",
    __name__,
)


# =========================================================
# CONSTANTS
# =========================================================

TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "on",
}

FALSE_VALUES = {
    "0",
    "false",
    "no",
    "off",
}


# =========================================================
# HELPERS
# =========================================================

def _truthy(
    value: Any,
) -> bool:
    """
    Convert a query-string boolean into a real boolean.

    Accepted true values:
        1
        true
        yes
        on

    Accepted false values:
        0
        false
        no
        off
    """

    if isinstance(
        value,
        bool,
    ):
        return value

    normalized = (
        str(value)
        .strip()
        .lower()
    )

    if normalized in TRUE_VALUES:
        return True

    if normalized in FALSE_VALUES:
        return False

    raise APIError(
        "Boolean value expected.",
        422,
        "invalid_boolean",
    )


def _call_service(
    name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Resolve and execute an economic service function safely.

    This keeps the route layer independent from source-specific
    implementation details.
    """

    function = getattr(
        economic_data_service,
        name,
        None,
    )

    if not callable(
        function
    ):

        raise APIError(
            f"Economic data service is missing {name}().",
            500,
            "economic_service_unavailable",
        )

    try:

        return function(
            *args,
            **kwargs,
        )

    except APIError:

        raise

    except Exception as exc:

        raise APIError(
            f"Economic data service failed: {exc}",
            502,
            "economic_data_unavailable",
        )


# =========================================================
# HEALTH
# =========================================================

@economic_bp.get(
    "/health"
)
def health():
    """
    Return economic-provider and cache health.

    This remains public so monitoring systems can check
    the economic service without authentication.
    """

    return ok(
        _call_service(
            "economic_data_health"
        )
    )


# =========================================================
# CURRENT INDICATORS
# =========================================================

@economic_bp.get(
    "/indicators"
)
@require_authenticated
def indicators():
    """
    Return the latest economic indicators.

    Query parameters:

        refresh=true
            Force live source refresh.

        refresh=false
            Return the latest validated cache.

    Examples:

        GET /api/jumuiya/biashara/economic/indicators

        GET /api/jumuiya/biashara/economic/indicators?refresh=true
    """

    raw_refresh = request.args.get(
        "refresh",
        "false",
    )

    force_refresh = _truthy(
        raw_refresh
    )

    return ok(
        _call_service(
            "get_economic_indicators",
            refresh=force_refresh,
        )
    )


# =========================================================
# FORCE REFRESH
# =========================================================

@economic_bp.post(
    "/refresh"
)
@require_authenticated
def refresh():
    """
    Force an immediate refresh of economic data.

    The service:

        1. Fetches configured live sources.
        2. Validates the responses.
        3. Writes a new cache snapshot.
        4. Reports partial failures explicitly.
    """

    result = _call_service(
        "refresh_economic_indicators"
    )

    return ok(
        result
    )


# =========================================================
# STATUS
# =========================================================

@economic_bp.get(
    "/status"
)
@require_authenticated
def status():
    """
    Return the current economic-service status.
    """

    return ok(
        _call_service(
            "economic_data_health"
        )
    )
