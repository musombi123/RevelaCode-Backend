"""
RevelaCode AI Gateway - Biashara Intelligence

Controlled bridge from RevelaAI to the existing Biashara
Market Intelligence engine.

RevelaAI does not implement or duplicate Biashara forecasting.

The RevelaCode backend remains the source of truth and performs:

    - market analysis
    - product forecasting
    - market trend analysis
    - economic intelligence
    - recommendations
"""

from __future__ import annotations

from typing import Any

from backend.jumuiya.core.errors import APIError

from backend.jumuiya.biashara.intelligence import (
    schemas,
    service,
)

from backend.jumuiya.biashara.intelligence.services import (
    economic_data_service,
)


SUPPORTED_OPERATIONS = {
    "market_analysis",
    "market_forecast",
    "product_forecast",
    "market_trends",
    "economic_indicators",
}


OPERATION_ALIASES = {
    "forecast": "market_forecast",
    "forecast_market": "market_forecast",
    "next_week": "market_forecast",
    "next_week_forecast": "market_forecast",
    "product_prediction": "product_forecast",
    "trend": "market_trends",
    "trends": "market_trends",
    "economics": "economic_indicators",
}


def _normalize_operation(
    operation: str | None,
) -> str:
    value = str(
        operation or ""
    ).strip().lower()

    if not value:
        raise APIError(
            "Biashara intelligence operation is required.",
            422,
            "missing_operation",
        )

    value = OPERATION_ALIASES.get(
        value,
        value,
    )

    if value not in SUPPORTED_OPERATIONS:
        raise APIError(
            (
                f"Unsupported Biashara intelligence operation: "
                f"{value}."
            ),
            422,
            "unsupported_operation",
        )

    return value


def _dict_payload(
    payload: Any,
) -> dict:
    if payload is None:
        return {}

    if not isinstance(
        payload,
        dict,
    ):
        raise APIError(
            "Biashara intelligence payload must be a JSON object.",
            422,
            "invalid_payload",
        )

    return dict(payload)


def _forecast_days(
    value: Any,
    default: int = 7,
) -> int:
    try:
        days = int(
            value
            if value is not None
            else default
        )
    except (
        TypeError,
        ValueError,
    ):
        raise APIError(
            "forecast_days must be a valid integer.",
            422,
            "invalid_forecast_days",
        )

    if days < 7:
        raise APIError(
            "forecast_days must be at least 7.",
            422,
            "invalid_forecast_days",
        )

    return min(
        days,
        365,
    )


def _market_analysis(
    user_id: str,
    payload: dict,
    force_next_week: bool = False,
) -> dict:
    """
    Execute the existing backend Market Intelligence engine.

    For next-week forecasting, the forecast horizon is fixed
    to 7 days unless explicitly supplied.
    """

    request_payload = dict(
        payload
    )

    options = request_payload.get(
        "options"
    )

    if not isinstance(
        options,
        dict,
    ):
        options = {}

    options = dict(
        options
    )

    if force_next_week:
        options[
            "forecast_horizon"
        ] = "short_term"

        options[
            "forecast_days"
        ] = 7

    else:
        options[
            "forecast_days"
        ] = _forecast_days(
            options.get(
                "forecast_days",
                30,
            ),
            default=30,
        )

        options.setdefault(
            "forecast_horizon",
            "short_term",
        )

    request_payload[
        "options"
    ] = options

    try:

        validated = (
            schemas.market_analysis_payload(
                request_payload
            )
        )

    except ValueError as exc:

        raise APIError(
            str(exc),
            422,
            "validation_error",
        )

    result = service.analyze_market(
        user_id,
        validated,
    )

    return {
        "operation": (
            "market_forecast"
            if force_next_week
            else "market_analysis"
        ),
        "forecast": {
            "enabled": True,
            "horizon_days": options[
                "forecast_days"
            ],
            "period": (
                "next_7_days"
                if force_next_week
                else options.get(
                    "forecast_horizon",
                    "short_term",
                )
            ),
        },
        "result": result,
    }


def _product_forecast(
    payload: dict,
) -> dict:
    """
    Execute the existing backend product forecasting engine.
    """

    request_payload = dict(
        payload
    )

    forecast_days = _forecast_days(
        request_payload.pop(
            "forecast_days",
            7,
        ),
        default=7,
    )

    if not request_payload.get(
        "name"
    ):
        raise APIError(
            "Product name is required for product forecasting.",
            422,
            "missing_product_name",
        )

    try:

        result = service.forecast_target(
            request_payload,
            forecast_days,
        )

    except APIError:
        raise

    except Exception as exc:

        raise APIError(
            f"Product forecasting failed: {exc}",
            502,
            "product_forecast_failed",
        )

    return {
        "operation": "product_forecast",
        "forecast": {
            "enabled": True,
            "horizon_days": forecast_days,
        },
        "result": result,
    }


def _market_trends(
    payload: dict,
) -> dict:
    """
    Retrieve the backend's existing market/economic trend data.

    Important:
        This is trend retrieval.
        It is not itself a future prediction.
    """

    area_id = str(
        payload.get(
            "area_id",
            "",
        )
        or ""
    ).strip()

    category = str(
        payload.get(
            "category",
            "",
        )
        or ""
    ).strip()

    indicator = str(
        payload.get(
            "indicator",
            "",
        )
        or ""
    ).strip()

    try:
        days = int(
            payload.get(
                "days",
                30,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        raise APIError(
            "days must be a valid integer.",
            422,
            "invalid_days",
        )

    if days < 1:
        raise APIError(
            "days must be at least 1.",
            422,
            "invalid_days",
        )

    days = min(
        days,
        3650,
    )

    try:

        result = service.market_trends(
            area_id=area_id,
            category=category,
            indicator=indicator,
            days=days,
        )

    except APIError:
        raise

    except Exception as exc:

        raise APIError(
            f"Market trend retrieval failed: {exc}",
            502,
            "market_trends_failed",
        )

    return {
        "operation": "market_trends",
        "historical_window_days": days,
        "forecast": {
            "enabled": False,
        },
        "result": result,
    }


def _economic_indicators(
    payload: dict,
) -> dict:
    """
    Retrieve the backend's economic intelligence service.
    """

    refresh = payload.get(
        "refresh",
        False,
    )

    if isinstance(
        refresh,
        str,
    ):
        refresh = (
            refresh.strip().lower()
            in {
                "1",
                "true",
                "yes",
                "on",
            }
        )

    try:

        result = (
            economic_data_service
            .get_economic_indicators(
                refresh=bool(
                    refresh
                )
            )
        )

    except APIError:
        raise

    except Exception as exc:

        raise APIError(
            f"Economic intelligence failed: {exc}",
            502,
            "economic_intelligence_failed",
        )

    return {
        "operation": "economic_indicators",
        "forecast": {
            "enabled": False,
        },
        "result": result,
    }


def run_biashara_operation(
    *,
    user_id: str,
    operation: str,
    payload: dict | None = None,
) -> dict:
    """
    Public gateway dispatcher for RevelaAI.
    """

    if not user_id:
        raise APIError(
            "Authenticated user ID is required.",
            401,
            "missing_user_id",
        )

    normalized_operation = (
        _normalize_operation(
            operation
        )
    )

    normalized_payload = (
        _dict_payload(
            payload
        )
    )

    if normalized_operation == "market_analysis":

        return _market_analysis(
            user_id,
            normalized_payload,
            force_next_week=False,
        )

    if normalized_operation == "market_forecast":

        return _market_analysis(
            user_id,
            normalized_payload,
            force_next_week=True,
        )

    if normalized_operation == "product_forecast":

        return _product_forecast(
            normalized_payload
        )

    if normalized_operation == "market_trends":

        return _market_trends(
            normalized_payload
        )

    if normalized_operation == "economic_indicators":

        return _economic_indicators(
            normalized_payload
        )

    raise APIError(
        "Biashara intelligence operation could not be dispatched.",
        500,
        "operation_dispatch_failed",
    )


__all__ = [
    "run_biashara_operation",
    "SUPPORTED_OPERATIONS",
]