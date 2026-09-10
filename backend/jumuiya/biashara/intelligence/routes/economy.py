"""
Jumuiya / Biashara - Live Economic Intelligence Routes

Exposes the live economic-data service to the Biashara frontend.

Endpoints:
    GET  /health
    GET  /indicators
    POST /refresh

The route layer deliberately contains no source-specific scraping logic.
All fetching, validation, normalization, caching, and source handling
belongs in services/economic_data_service.py.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import require_authenticated
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
# HELPERS
# =========================================================

def _truthy(value: Any) -> bool:
    """Convert a query-string boolean into a real boolean."""

    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _call_service(name: str, *args: Any, **kwargs: Any) -> Any:
    """
    Resolve a service function safely.

    Keeping this check here produces a useful API error instead of an
    obscure AttributeError when the service contract is incomplete.
    """

    function = getattr(
        economic_data_service,
        name,
        None,
    )

    if not callable(function):
        raise APIError(
            f"Economic data service is missing {name}().",
            500,
            "economic_service_unavailable",
        )

    try:
        return function(*args, **kwargs)
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

@economic_bp.get("/health")
def health():
    """
    Return live economic-provider/cache health.

    Kept public so deployment monitors can check the service without
    requiring an authenticated Biashara session.
    """

    return ok(
        _call_service(
            "economic_data_health"
        )
    )


# =========================================================
# CURRENT INDICATORS
# =========================================================

@economic_bp.get("/indicators")
@require_authenticated
def indicators():
    """
    Return the latest validated economic indicators.

    Query parameters:
        refresh=true   Force an upstream refresh before returning data.

    Examples:
        GET /api/jumuiya/biashara/economic/indicators
        GET /api/jumuiya/biashara/economic/indicators?refresh=true
    """

    force_refresh = _truthy(
        request.args.get(
            "refresh",
            "false",
        )
    )

    return ok(
        _call_service(
            "get_live_economic_indicators",
            force_refresh=force_refresh,
        )
    )


# =========================================================
# FORCE REFRESH
# =========================================================

@economic_bp.post("/refresh")
@require_authenticated
def refresh():
    """
    Force an immediate refresh of economic data.

    The service updates the local cache only after successful
    validation, allowing the previous snapshot to remain available
    when an upstream source fails.
    """

    result = _call_service(
        "refresh_economic_indicators"
    )

    return ok(
        result
    )


# =========================================================
# DATASET STATUS
# =========================================================

@economic_bp.get("/status")
@require_authenticated
def status():
    """
    Return the live economic data provider/cache status.
    """

    return ok(
        _call_service(
            "economic_data_health"
        )
    )
