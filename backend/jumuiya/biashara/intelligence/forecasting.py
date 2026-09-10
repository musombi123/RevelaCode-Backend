# backend/jumuiya/biashara/intelligence/forecasting.py

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_FORECAST_DAYS = 30

MIN_FORECAST_DAYS = 7

MAX_FORECAST_DAYS = 365

MIN_HISTORY_POINTS = 2

DEFAULT_BASELINE_VALUE = 0.0

MAX_GROWTH_RATE = 5.0

MIN_GROWTH_RATE = -0.95


# =========================================================
# HELPERS
# =========================================================

def as_float(
    value: Any,
    default: float = 0.0,
) -> float:
    """
    Safely convert a value to float.
    """

    try:
        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def clamp(
    value: Any,
    minimum: float,
    maximum: float,
) -> float:
    """
    Clamp a number into a range.
    """

    value = as_float(
        value,
        minimum,
    )

    return max(
        minimum,
        min(
            value,
            maximum,
        ),
    )


def normalize_growth(
    value: Any,
) -> float:
    """
    Normalize a growth rate to a safe decimal range.

    Examples:

        0.15  -> 15%
        15    -> 15%

    The returned value is decimal form.
    """

    growth = as_float(
        value,
        0.0,
    )

    # Support percentages such as 15 instead of 0.15.
    if abs(growth) > 1:
        growth = growth / 100.0

    return clamp(
        growth,
        MIN_GROWTH_RATE,
        MAX_GROWTH_RATE,
    )


def normalize_index(
    value: Any,
    default: float = 1.0,
) -> float:
    """
    Normalize a multiplier/index.

    1.0 means neutral.

    1.20 means +20%.

    0.80 means -20%.
    """

    value = as_float(
        value,
        default,
    )

    if value < 0:
        return 0.0

    return value


# =========================================================
# TIME SERIES CLEANING
# =========================================================

def clean_time_series(
    history: list[Any] | None,
) -> list[dict]:
    """
    Normalize historical observations.

    Supported input formats include:

        {
            "date": "2026-08-01",
            "value": 100
        }

    or:

        {
            "period": "2026-08-01",
            "sales": 100
        }

    or:

        {
            "timestamp": "...",
            "demand": 100
        }

    Invalid observations are ignored.
    """

    if not isinstance(
        history,
        list,
    ):
        return []

    cleaned = []

    for item in history:

        if not isinstance(
            item,
            dict,
        ):
            continue

        date_value = (
            item.get("date")
            or item.get("period")
            or item.get("timestamp")
        )

        value = (
            item.get("value")
            if item.get("value") is not None
            else item.get("sales")
        )

        if value is None:
            value = item.get(
                "demand"
            )

        if date_value is None:
            continue

        numeric_value = as_float(
            value,
            None,
        )

        if numeric_value is None:
            continue

        cleaned.append({
            "date": str(
                date_value
            ),
            "value": max(
                0.0,
                numeric_value,
            ),
        })

    cleaned.sort(
        key=lambda item: item[
            "date"
        ]
    )

    return cleaned


# =========================================================
# SIMPLE STATISTICS
# =========================================================

def mean(
    values: list[float],
) -> float:
    if not values:
        return 0.0

    return (
        sum(values)
        / len(values)
    )


def weighted_mean(
    values: list[float],
) -> float:
    """
    Give more importance to recent observations.

    Example:

        oldest -> weight 1
        newest -> highest weight
    """

    if not values:
        return 0.0

    weights = list(
        range(
            1,
            len(values) + 1,
        )
    )

    denominator = sum(
        weights
    )

    if denominator == 0:
        return 0.0

    numerator = sum(
        value * weight
        for value, weight
        in zip(
            values,
            weights,
        )
    )

    return (
        numerator
        / denominator
    )


def linear_growth_rate(
    values: list[float],
) -> float:
    """
    Estimate a simple growth rate from the beginning
    and end of a time series.

    The output is decimal form.

    Example:

        100 -> 120

        returns approximately 0.20.
    """

    if len(values) < 2:
        return 0.0

    start = as_float(
        values[0],
        0.0,
    )

    end = as_float(
        values[-1],
        0.0,
    )

    if start <= 0:

        if end > 0:
            return 0.20

        return 0.0

    growth = (
        end - start
    ) / start

    return normalize_growth(
        growth
    )


def recent_growth_rate(
    values: list[float],
    window: int = 4,
) -> float:
    """
    Estimate recent growth using the first and last
    values of the selected recent window.
    """

    if len(values) < 2:
        return 0.0

    window = max(
        2,
        int(window),
    )

    recent = values[
        -window:
    ]

    return linear_growth_rate(
        recent
    )


def volatility_score(
    values: list[float],
) -> float:
    """
    Return a simple 0-100 volatility score.

    0   = very stable
    100 = highly volatile

    This is deliberately lightweight for the MVP.
    """

    if len(values) < 2:
        return 0.0

    average = mean(
        values
    )

    if average <= 0:
        return 0.0

    deviations = [
        abs(
            value - average
        )
        / average
        for value in values
    ]

    average_deviation = mean(
        deviations
    )

    return round(
        clamp(
            average_deviation * 100,
            0,
            100,
        ),
        2,
    )


# =========================================================
# BASELINE FORECAST
# =========================================================

def baseline_forecast(
    history: list[Any] | None,
    forecast_days: int = DEFAULT_FORECAST_DAYS,
) -> dict:
    """
    Produce a baseline demand forecast using a
    recency-weighted historical mean and recent growth.

    This is an explainable MVP forecasting method.
    """

    forecast_days = int(
        clamp(
            forecast_days,
            MIN_FORECAST_DAYS,
            MAX_FORECAST_DAYS,
        )
    )

    cleaned = clean_time_series(
        history
    )

    values = [
        item["value"]
        for item in cleaned
    ]

    if not values:

        return {
            "method": "baseline",
            "forecast_days": forecast_days,
            "baseline": 0.0,
            "growth_rate": 0.0,
            "volatility": 0.0,
            "forecast": [],
            "data_points": 0,
            "confidence": 0.0,
        }

    baseline = weighted_mean(
        values
    )

    growth = recent_growth_rate(
        values,
        min(
            6,
            len(values),
        ),
    )

    volatility = volatility_score(
        values
    )

    # Prevent extreme extrapolation.
    daily_growth = clamp(
        growth
        / max(
            len(values),
            1,
        ),
        -0.05,
        0.05,
    )

    forecast = []

    last_date = None

    if cleaned:

        last_raw_date = cleaned[-1][
            "date"
        ]

        try:

            last_date = datetime.fromisoformat(
                last_raw_date.replace(
                    "Z",
                    "+00:00",
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            last_date = None

    for day in range(
        1,
        forecast_days + 1,
    ):

        projected = baseline * (
            (1 + daily_growth)
            ** day
        )

        projected = max(
            0.0,
            projected,
        )

        if last_date:

            forecast_date = (
                last_date
                + timedelta(
                    days=day
                )
            ).date().isoformat()

        else:

            forecast_date = None

        forecast.append({
            "day": day,
            "date": forecast_date,
            "value": round(
                projected,
                2,
            ),
        })

    confidence = forecast_confidence(
        data_points=len(values),
        volatility=volatility,
    )

    return {
        "method": "baseline",
        "forecast_days": forecast_days,
        "baseline": round(
            baseline,
            2,
        ),
        "growth_rate": round(
            growth,
            4,
        ),
        "volatility": volatility,
        "forecast": forecast,
        "data_points": len(values),
        "confidence": confidence,
    }


# =========================================================
# SEASONAL ADJUSTMENT
# =========================================================

def apply_seasonality(
    forecast: dict,
    seasonal_index: Any = 1.0,
) -> dict:
    """
    Apply a seasonal multiplier to a baseline forecast.

    Examples:

        1.00 = neutral
        1.15 = expected +15%
        0.85 = expected -15%
    """

    if not isinstance(
        forecast,
        dict,
    ):
        return {}

    multiplier = normalize_index(
        seasonal_index,
        1.0,
    )

    updated = dict(
        forecast
    )

    projections = []

    for item in forecast.get(
        "forecast",
        [],
    ):

        if not isinstance(
            item,
            dict,
        ):
            continue

        value = (
            as_float(
                item.get(
                    "value"
                )
            )
            * multiplier
        )

        projections.append({
            **item,
            "value": round(
                max(
                    0.0,
                    value,
                ),
                2,
            ),
        })

    updated[
        "forecast"
    ] = projections

    updated[
        "seasonal_index"
    ] = round(
        multiplier,
        4,
    )

    return updated


# =========================================================
# MACRO ADJUSTMENT
# =========================================================

def macro_demand_adjustment(
    inflation: Any = 0.0,
    transport_inflation: Any = 0.0,
    supply_pressure: Any = 0.0,
    demand_sensitivity: Any = 0.5,
) -> float:
    """
    Estimate the directional effect of macro pressure
    on expected demand.

    This is not a claim that inflation directly causes
    a fixed amount of demand change. It is an explicit
    modelling assumption intended for the MVP.

    Returns a multiplier.

        1.00 = neutral
        <1  = negative pressure
        >1  = positive support
    """

    inflation = max(
        0.0,
        as_float(
            inflation
        ),
    )

    transport = max(
        0.0,
        as_float(
            transport_inflation
        ),
    )

    supply = max(
        0.0,
        as_float(
            supply_pressure
        ),
    )

    sensitivity = clamp(
        demand_sensitivity,
        0,
        1,
    )

    pressure = (
        inflation * 0.55
        +
        transport * 0.25
        +
        supply * 0.20
    )

    # Keep macro impact conservative.
    reduction = (
        pressure
        / 100
        * sensitivity
        * 0.50
    )

    return round(
        clamp(
            1 - reduction,
            0.50,
            1.15,
        ),
        4,
    )


def apply_macro_adjustment(
    forecast: dict,
    multiplier: Any,
) -> dict:
    """
    Apply a macro-economic multiplier to a forecast.
    """

    if not isinstance(
        forecast,
        dict,
    ):
        return {}

    multiplier = normalize_index(
        multiplier,
        1.0,
    )

    updated = dict(
        forecast
    )

    projections = []

    for item in forecast.get(
        "forecast",
        [],
    ):

        if not isinstance(
            item,
            dict,
        ):
            continue

        value = (
            as_float(
                item.get(
                    "value"
                )
            )
            * multiplier
        )

        projections.append({
            **item,
            "value": round(
                max(
                    0.0,
                    value,
                ),
                2,
            ),
        })

    updated[
        "forecast"
    ] = projections

    updated[
        "macro_multiplier"
    ] = round(
        multiplier,
        4,
    )

    return updated


# =========================================================
# COMBINED FORECAST
# =========================================================

def demand_forecast(
    history: list[Any] | None,
    forecast_days: int = DEFAULT_FORECAST_DAYS,
    seasonal_index: Any = 1.0,
    macro_multiplier: Any = 1.0,
) -> dict:
    """
    Generate a demand forecast with optional seasonal
    and macro-economic adjustments.

    Returns both the baseline assumptions and the
    adjusted projections so the frontend can explain
    how the result was produced.
    """

    baseline = baseline_forecast(
        history,
        forecast_days,
    )

    adjusted = apply_seasonality(
        baseline,
        seasonal_index,
    )

    adjusted = apply_macro_adjustment(
        adjusted,
        macro_multiplier,
    )

    # -----------------------------------------------------
    # Forecast summary
    # -----------------------------------------------------

    values = [
        as_float(
            item.get(
                "value"
            )
        )
        for item in adjusted.get(
            "forecast",
            []
        )
        if isinstance(
            item,
            dict,
        )
    ]

    average_forecast = mean(
        values
    )

    ending_forecast = (
        values[-1]
        if values
        else 0.0
    )

    growth_direction = (
        "rising"
        if ending_forecast
        > baseline.get(
            "baseline",
            0,
        ) * 1.05
        else
        "falling"
        if ending_forecast
        < baseline.get(
            "baseline",
            0,
        ) * 0.95
        else
        "stable"
    )

    adjusted[
        "summary"
    ] = {
        "average_forecast": round(
            average_forecast,
            2,
        ),

        "ending_forecast": round(
            ending_forecast,
            2,
        ),

        "direction": growth_direction,
    }

    adjusted[
        "confidence"
    ] = forecast_confidence(
        data_points=baseline.get(
            "data_points",
            0,
        ),
        volatility=baseline.get(
            "volatility",
            0,
        ),
    )

    return adjusted


# =========================================================
# CONFIDENCE
# =========================================================

def forecast_confidence(
    data_points: Any,
    volatility: Any = 0.0,
) -> float:
    """
    Estimate forecast confidence from historical depth
    and volatility.

    Returned as 0-1.
    """

    try:
        data_points = int(
            data_points
        )

    except (
        TypeError,
        ValueError,
    ):
        data_points = 0

    volatility = clamp(
        volatility,
        0,
        100,
    )

    # More observations increase confidence.
    history_factor = min(
        1.0,
        data_points / 30.0,
    )

    # Volatility reduces confidence.
    volatility_factor = max(
        0.0,
        1.0
        - (
            volatility / 120.0
        ),
    )

    # Very short datasets should remain explicitly
    # low-confidence.
    confidence = (
        history_factor * 0.60
        +
        volatility_factor * 0.40
    )

    if data_points < MIN_HISTORY_POINTS:
        confidence *= 0.35

    return round(
        clamp(
            confidence,
            0,
            1,
        ),
        3,
    )


# =========================================================
# FORECAST CATEGORY
# =========================================================

def forecast_label(
    direction: Any,
    growth_rate: Any = 0.0,
) -> str:
    """
    Convert directional forecast information into a
    business-friendly label.
    """

    direction = str(
        direction or ""
    ).strip().lower()

    growth = normalize_growth(
        growth_rate
    )

    if direction == "rising":

        if growth >= 0.20:
            return "strong_growth"

        return "rising"

    if direction == "falling":

        if growth <= -0.20:
            return "strong_decline"

        return "falling"

    return "stable"


# =========================================================
# FORECAST CHANGE
# =========================================================

def compare_forecasts(
    baseline: dict | None,
    adjusted: dict | None,
) -> dict:
    """
    Compare baseline and adjusted forecast averages.
    """

    baseline = (
        baseline
        if isinstance(
            baseline,
            dict,
        )
        else {}
    )

    adjusted = (
        adjusted
        if isinstance(
            adjusted,
            dict,
        )
        else {}
    )

    baseline_values = [
        as_float(
            item.get(
                "value"
            )
        )
        for item in baseline.get(
            "forecast",
            []
        )
        if isinstance(
            item,
            dict,
        )
    ]

    adjusted_values = [
        as_float(
            item.get(
                "value"
            )
        )
        for item in adjusted.get(
            "forecast",
            []
        )
        if isinstance(
            item,
            dict,
        )
    ]

    baseline_average = mean(
        baseline_values
    )

    adjusted_average = mean(
        adjusted_values
    )

    if baseline_average <= 0:

        change = 0.0

    else:

        change = (
            adjusted_average
            - baseline_average
        ) / baseline_average

    return {
        "baseline_average": round(
            baseline_average,
            2,
        ),

        "adjusted_average": round(
            adjusted_average,
            2,
        ),

        "change": round(
            change,
            4,
        ),

        "change_percent": round(
            change * 100,
            2,
        ),
    }


# =========================================================
# PRODUCT FORECAST
# =========================================================

def forecast_product(
    product: dict,
    forecast_days: int = DEFAULT_FORECAST_DAYS,
) -> dict:
    """
    Forecast a single product/service.

    Supported history fields:

        sales_history
        demand_history
        history
    """

    if not isinstance(
        product,
        dict,
    ):
        raise ValueError(
            "product must be an object."
        )

    history = (
        product.get(
            "sales_history"
        )
        or product.get(
            "demand_history"
        )
        or product.get(
            "history"
        )
        or []
    )

    seasonal_index = normalize_index(
        product.get(
            "seasonal_index",
            1.0,
        ),
        1.0,
    )

    macro_multiplier = normalize_index(
        product.get(
            "macro_multiplier",
            1.0,
        ),
        1.0,
    )

    forecast = demand_forecast(
        history=history,
        forecast_days=forecast_days,
        seasonal_index=seasonal_index,
        macro_multiplier=macro_multiplier,
    )

    baseline = baseline_forecast(
        history=history,
        forecast_days=forecast_days,
    )

    comparison = compare_forecasts(
        baseline,
        forecast,
    )

    direction = forecast.get(
        "summary",
        {},
    ).get(
        "direction",
        "stable",
    )

    growth_rate = forecast.get(
        "growth_rate",
        0.0,
    )

    return {
        "name": product.get(
            "name",
            "",
        ),

        "category": product.get(
            "category",
            "",
        ),

        "forecast": forecast,

        "label": forecast_label(
            direction,
            growth_rate,
        ),

        "comparison": comparison,

        "confidence": forecast.get(
            "confidence",
            0.0,
        ),
    }


# =========================================================
# MULTI-PRODUCT FORECAST
# =========================================================

def forecast_products(
    products: list[dict],
    forecast_days: int = DEFAULT_FORECAST_DAYS,
) -> list[dict]:
    """
    Forecast multiple products/services independently.
    """

    if not isinstance(
        products,
        list,
    ):
        return []

    results = []

    for product in products:

        try:

            result = forecast_product(
                product,
                forecast_days,
            )

            results.append(
                result
            )

        except ValueError:

            continue

    return results


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "clean_time_series",
    "mean",
    "weighted_mean",
    "linear_growth_rate",
    "recent_growth_rate",
    "volatility_score",
    "baseline_forecast",
    "apply_seasonality",
    "macro_demand_adjustment",
    "apply_macro_adjustment",
    "demand_forecast",
    "forecast_confidence",
    "forecast_label",
    "compare_forecasts",
    "forecast_product",
    "forecast_products",
]
