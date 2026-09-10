# backend/jumuiya/biashara/intelligence/scoring.py

from __future__ import annotations

from typing import Any


# =========================================================
# SCORING CONSTANTS
# =========================================================
#
# All individual signals are normalized to 0 - 100.
# The final opportunity score is also 0 - 100.
#
# These weights are intentionally explicit and explainable.
# They can later be replaced/tuned using historical data.
# =========================================================

WEIGHTS = {
    "demographic_fit": 0.25,
    "demand_signal": 0.25,
    "price_environment": 0.15,
    "competition": 0.15,
    "seasonality": 0.10,
    "business_performance": 0.10,
}


# =========================================================
# LABELS
# =========================================================

SCORE_LABELS = (
    (80, "excellent"),
    (65, "strong"),
    (50, "moderate"),
    (35, "risky"),
    (0, "weak"),
)


LEVELS = {
    "very_low": 20,
    "low": 40,
    "medium": 60,
    "high": 80,
}


# =========================================================
# GENERAL HELPERS
# =========================================================

def clamp(
    value: Any,
    minimum: float = 0.0,
    maximum: float = 100.0,
) -> float:
    """
    Clamp a numeric value into a defined range.
    """

    try:
        value = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        value = minimum

    return round(
        max(
            minimum,
            min(
                value,
                maximum,
            ),
        ),
        2,
    )


def as_number(
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


def weighted_average(
    signals: dict[str, Any],
    weights: dict[str, float],
) -> float:
    """
    Calculate a weighted average.

    Missing signals are excluded and the remaining weights
    are normalized so incomplete datasets do not
    automatically produce a zero score.
    """

    numerator = 0.0
    denominator = 0.0

    for key, weight in weights.items():

        if key not in signals:
            continue

        value = signals.get(
            key
        )

        if value is None:
            continue

        value = clamp(
            value
        )

        weight = as_number(
            weight,
            0.0,
        )

        if weight <= 0:
            continue

        numerator += (
            value * weight
        )

        denominator += weight

    if denominator <= 0:
        return 0.0

    return round(
        numerator / denominator,
        2,
    )


def score_label(
    score: Any,
) -> str:
    """
    Convert a 0-100 score into a human-readable label.
    """

    score = clamp(
        score
    )

    for minimum, label in SCORE_LABELS:

        if score >= minimum:
            return label

    return "weak"


def score_level(
    score: Any,
) -> str:
    """
    Convert a 0-100 score into a simpler level.
    """

    score = clamp(
        score
    )

    if score < LEVELS["very_low"]:
        return "very_low"

    if score < LEVELS["low"]:
        return "low"

    if score < LEVELS["medium"]:
        return "medium"

    if score < LEVELS["high"]:
        return "high"

    return "very_high"


# =========================================================
# DIRECTION HELPERS
# =========================================================

def direction_score(
    value: Any,
    neutral: float = 0.0,
    scale: float = 1.0,
    invert: bool = False,
) -> float:
    """
    Convert a directional numeric signal into 0-100.

    Example:

        value = +0.2
        neutral = 0
        scale = 0.2

    produces a strong positive score.

    When invert=True, higher source values become
    lower opportunity scores.
    """

    value = as_number(
        value,
        neutral,
    )

    scale = abs(
        as_number(
            scale,
            1.0,
        )
    )

    if scale == 0:
        scale = 1.0

    normalized = (
        50
        + (
            (value - neutral)
            / scale
        ) * 50
    )

    score = clamp(
        normalized
    )

    if invert:
        score = 100 - score

    return round(
        score,
        2,
    )


# =========================================================
# DEMOGRAPHIC FIT
# =========================================================

def demographic_fit_score(
    demographic_data: dict | None,
    target_profile: dict | None = None,
) -> float:
    """
    Estimate product/business fit against available
    aggregate demographic indicators.

    Supported optional values include:

        youth_index
        working_age_index
        senior_index
        household_index
        population_density_index

    A target profile may provide desired weights such as:

        {
            "youth": 0.8,
            "working_age": 0.7,
            "density": 0.9
        }

    No individual-level profiling is performed.
    """

    demographic_data = (
        demographic_data
        if isinstance(
            demographic_data,
            dict,
        )
        else {}
    )

    target_profile = (
        target_profile
        if isinstance(
            target_profile,
            dict,
        )
        else {}
    )

    signals = []

    # -----------------------------------------------------
    # Direct normalized indexes
    # -----------------------------------------------------

    direct_fields = [
        (
            "youth_index",
            "youth",
        ),
        (
            "working_age_index",
            "working_age",
        ),
        (
            "senior_index",
            "senior",
        ),
        (
            "household_index",
            "households",
        ),
        (
            "population_density_index",
            "density",
        ),
    ]

    for field, target_key in direct_fields:

        value = demographic_data.get(
            field
        )

        if value is None:
            continue

        importance = as_number(
            target_profile.get(
                target_key,
                1.0,
            ),
            1.0,
        )

        signals.append(
            (
                clamp(
                    value
                ),
                max(
                    0.1,
                    importance,
                ),
            )
        )

    # -----------------------------------------------------
    # Percentage-style age groups
    # -----------------------------------------------------

    age_groups = demographic_data.get(
        "age_groups"
    )

    if isinstance(
        age_groups,
        dict,
    ):

        age_values = []

        for key, value in age_groups.items():

            numeric = as_number(
                value,
                -1,
            )

            if 0 <= numeric <= 100:
                age_values.append(
                    numeric
                )

        if age_values:

            average_age_signal = (
                sum(age_values)
                / len(age_values)
            )

            # Presence of valid demographic data
            # contributes to confidence without
            # claiming direct product suitability.
            signals.append(
                (
                    clamp(
                        average_age_signal
                    ),
                    0.25,
                )
            )

    if not signals:
        return 50.0

    numerator = sum(
        value * weight
        for value, weight
        in signals
    )

    denominator = sum(
        weight
        for _, weight
        in signals
    )

    if denominator <= 0:
        return 50.0

    return round(
        clamp(
            numerator / denominator
        ),
        2,
    )


# =========================================================
# DEMAND SIGNAL
# =========================================================

def demand_signal_score(
    market_data: dict | None,
) -> float:
    """
    Convert available demand indicators into 0-100.

    Supported fields may include:

        demand_index
        demand_growth
        search_interest
        sales_growth
        stock_turnover
        demand_rating
    """

    market_data = (
        market_data
        if isinstance(
            market_data,
            dict,
        )
        else {}
    )

    scores = []

    # -----------------------------------------------------
    # Explicit demand index
    # -----------------------------------------------------

    if market_data.get(
        "demand_index"
    ) is not None:

        scores.append(
            clamp(
                market_data[
                    "demand_index"
                ]
            )
        )

    # -----------------------------------------------------
    # Demand growth
    # -----------------------------------------------------

    if market_data.get(
        "demand_growth"
    ) is not None:

        scores.append(
            direction_score(
                market_data[
                    "demand_growth"
                ],
                neutral=0,
                scale=0.25,
            )
        )

    # -----------------------------------------------------
    # Search interest
    # -----------------------------------------------------

    if market_data.get(
        "search_interest"
    ) is not None:

        scores.append(
            clamp(
                market_data[
                    "search_interest"
                ]
            )
        )

    # -----------------------------------------------------
    # Business sales growth
    # -----------------------------------------------------

    if market_data.get(
        "sales_growth"
    ) is not None:

        scores.append(
            direction_score(
                market_data[
                    "sales_growth"
                ],
                neutral=0,
                scale=0.30,
            )
        )

    # -----------------------------------------------------
    # Rating
    # -----------------------------------------------------

    rating = str(
        market_data.get(
            "demand_rating",
            "",
        )
    ).strip().lower()

    rating_scores = {
        "very_low": 15,
        "low": 30,
        "medium": 55,
        "moderate": 55,
        "high": 80,
        "very_high": 95,
        "rising": 85,
        "stable": 60,
        "falling": 30,
        "declining": 25,
    }

    if rating in rating_scores:

        scores.append(
            rating_scores[
                rating
            ]
        )

    if not scores:
        return 50.0

    return round(
        clamp(
            sum(scores)
            / len(scores)
        ),
        2,
    )


# =========================================================
# PRICE ENVIRONMENT
# =========================================================

def price_environment_score(
    economic_data: dict | None,
    business_data: dict | None = None,
) -> float:
    """
    Estimate how favorable the current price environment
    is for a business.

    Important:

        Higher inflation does not automatically mean
        an opportunity is bad.

    The score therefore considers whether the business
    can absorb or respond to the pressure.
    """

    economic_data = (
        economic_data
        if isinstance(
            economic_data,
            dict,
        )
        else {}
    )

    business_data = (
        business_data
        if isinstance(
            business_data,
            dict,
        )
        else {}
    )

    inflation = as_number(
        economic_data.get(
            "inflation"
        ),
        0.0,
    )

    food_inflation = as_number(
        economic_data.get(
            "food_inflation"
        ),
        inflation,
    )

    transport_inflation = as_number(
        economic_data.get(
            "transport_inflation"
        ),
        inflation,
    )

    supply_pressure = as_number(
        economic_data.get(
            "supply_pressure"
        ),
        0.0,
    )

    # -----------------------------------------------------
    # Pressure index
    # -----------------------------------------------------

    pressure = (
        max(
            inflation,
            0.0,
        ) * 0.40
        +
        max(
            food_inflation,
            0.0,
        ) * 0.25
        +
        max(
            transport_inflation,
            0.0,
        ) * 0.20
        +
        max(
            supply_pressure,
            0.0,
        ) * 0.15
    )

    # Around 0% pressure = 100
    # Around 10% pressure = 60
    # Around 20%+ pressure = very challenging
    score = (
        100
        - (
            pressure * 2.5
        )
    )

    # Businesses with higher gross margin
    # can absorb some cost pressure.
    gross_margin = as_number(
        business_data.get(
            "gross_margin"
        ),
        0.0,
    )

    if gross_margin > 0:

        margin_boost = min(
            gross_margin * 0.25,
            15,
        )

        score += margin_boost

    return round(
        clamp(
            score
        ),
        2,
    )


# =========================================================
# COMPETITION
# =========================================================

def competition_score(
    competition_data: dict | None,
) -> float:
    """
    Convert competition intensity into an opportunity score.

    Lower competition = higher opportunity.

    Supported fields:

        competition_index 0-100
        competitor_count
        competition_rating
    """

    competition_data = (
        competition_data
        if isinstance(
            competition_data,
            dict,
        )
        else {}
    )

    if competition_data.get(
        "competition_index"
    ) is not None:

        index = clamp(
            competition_data[
                "competition_index"
            ]
        )

        return round(
            100 - index,
            2,
        )

    rating = str(
        competition_data.get(
            "competition_rating",
            "",
        )
    ).strip().lower()

    rating_scores = {
        "very_low": 95,
        "low": 80,
        "medium": 60,
        "moderate": 60,
        "high": 35,
        "very_high": 15,
    }

    if rating in rating_scores:

        return float(
            rating_scores[
                rating
            ]
        )

    competitor_count = competition_data.get(
        "competitor_count"
    )

    if competitor_count is not None:

        count = max(
            0,
            as_number(
                competitor_count
            ),
        )

        # This is a conservative baseline.
        # Real datasets should provide a normalized
        # competition index.
        return round(
            clamp(
                100
                - (
                    min(
                        count,
                        100,
                    )
                    * 0.8
                )
            ),
            2,
        )

    return 50.0


# =========================================================
# SEASONALITY
# =========================================================

def seasonality_score(
    seasonal_data: dict | None,
) -> float:
    """
    Estimate opportunity from seasonal conditions.

    Supported:

        seasonal_index
        demand_multiplier
        seasonal_direction
        peak_period
    """

    seasonal_data = (
        seasonal_data
        if isinstance(
            seasonal_data,
            dict,
        )
        else {}
    )

    if seasonal_data.get(
        "seasonal_index"
    ) is not None:

        return clamp(
            seasonal_data[
                "seasonal_index"
            ]
        )

    if seasonal_data.get(
        "demand_multiplier"
    ) is not None:

        multiplier = as_number(
            seasonal_data[
                "demand_multiplier"
            ],
            1.0,
        )

        return round(
            clamp(
                50
                + (
                    multiplier
                    - 1
                )
                * 100
            ),
            2,
        )

    direction = str(
        seasonal_data.get(
            "seasonal_direction",
            "",
        )
    ).strip().lower()

    direction_scores = {
        "falling": 25,
        "declining": 25,
        "stable": 55,
        "normal": 55,
        "rising": 80,
        "peak": 95,
        "high": 85,
        "low": 25,
    }

    if direction in direction_scores:

        return float(
            direction_scores[
                direction
            ]
        )

    return 50.0


# =========================================================
# BUSINESS PERFORMANCE
# =========================================================

def business_performance_score(
    business_data: dict | None,
) -> float:
    """
    Convert existing business performance into a signal.

    Supported:

        sales_growth
        conversion_rate
        repeat_customer_rate
        stock_turnover
        gross_margin
    """

    business_data = (
        business_data
        if isinstance(
            business_data,
            dict,
        )
        else {}
    )

    scores = []

    if business_data.get(
        "sales_growth"
    ) is not None:

        scores.append(
            direction_score(
                business_data[
                    "sales_growth"
                ],
                neutral=0,
                scale=0.30,
            )
        )

    if business_data.get(
        "conversion_rate"
    ) is not None:

        conversion = as_number(
            business_data[
                "conversion_rate"
            ],
            0,
        )

        # 0%-10% → approximately 0-100.
        scores.append(
            clamp(
                conversion * 10
                if conversion <= 10
                else conversion
            )
        )

    if business_data.get(
        "repeat_customer_rate"
    ) is not None:

        repeat_rate = as_number(
            business_data[
                "repeat_customer_rate"
            ],
            0,
        )

        scores.append(
            clamp(
                repeat_rate * 100
                if repeat_rate <= 1
                else repeat_rate
            )
        )

    if business_data.get(
        "stock_turnover"
    ) is not None:

        turnover = as_number(
            business_data[
                "stock_turnover"
            ],
            0,
        )

        scores.append(
            clamp(
                turnover * 20
            )
        )

    if business_data.get(
        "gross_margin"
    ) is not None:

        margin = as_number(
            business_data[
                "gross_margin"
            ],
            0,
        )

        scores.append(
            clamp(
                margin * 100
                if margin <= 1
                else margin
            )
        )

    if not scores:
        return 50.0

    return round(
        clamp(
            sum(scores)
            / len(scores)
        ),
        2,
    )


# =========================================================
# FULL OPPORTUNITY SCORE
# =========================================================

def calculate_opportunity_score(
    *,
    demographic_fit: Any = None,
    demand_signal: Any = None,
    price_environment: Any = None,
    competition: Any = None,
    seasonality: Any = None,
    business_performance: Any = None,
) -> dict:
    """
    Calculate the final market opportunity score.

    All six dimensions are normalized to 0-100 first,
    then combined using WEIGHTS.
    """

    signals = {
        "demographic_fit": (
            50
            if demographic_fit is None
            else clamp(
                demographic_fit
            )
        ),

        "demand_signal": (
            50
            if demand_signal is None
            else clamp(
                demand_signal
            )
        ),

        "price_environment": (
            50
            if price_environment is None
            else clamp(
                price_environment
            )
        ),

        "competition": (
            50
            if competition is None
            else clamp(
                competition
            )
        ),

        "seasonality": (
            50
            if seasonality is None
            else clamp(
                seasonality
            )
        ),

        "business_performance": (
            50
            if business_performance is None
            else clamp(
                business_performance
            )
        ),
    }

    score = weighted_average(
        signals,
        WEIGHTS,
    )

    return {
        "score": score,

        "label": score_label(
            score
        ),

        "level": score_level(
            score
        ),

        "signals": signals,

        "weights": WEIGHTS.copy(),
    }


# =========================================================
# CATEGORY SCORE
# =========================================================

def category_market_score(
    *,
    demographics: dict | None = None,
    market: dict | None = None,
    economics: dict | None = None,
    competition: dict | None = None,
    seasonality: dict | None = None,
    business: dict | None = None,
    target_profile: dict | None = None,
) -> dict:
    """
    Calculate a complete category/location market score.
    """

    demographic_score = (
        demographic_fit_score(
            demographics,
            target_profile,
        )
    )

    demand_score = (
        demand_signal_score(
            market
        )
    )

    price_score = (
        price_environment_score(
            economics,
            business,
        )
    )

    competition_score_value = (
        globals()["competition_score"](
            competition
        )
    )

    seasonality_score_value = (
        globals()["seasonality_score"](
            seasonality
        )
    )

    business_score = (
        business_performance_score(
            business
        )
    )

    return calculate_opportunity_score(
        demographic_fit=demographic_score,
        demand_signal=demand_score,
        price_environment=price_score,
        competition=competition_score_value,
        seasonality=seasonality_score_value,
        business_performance=business_score,
    )


# =========================================================
# SIGNAL COMPARISON
# =========================================================

def compare_scores(
    current_score: Any,
    previous_score: Any,
) -> dict:
    """
    Compare two opportunity scores and return
    direction and magnitude.
    """

    current = clamp(
        current_score
    )

    previous = clamp(
        previous_score
    )

    change = round(
        current - previous,
        2,
    )

    if change >= 5:
        direction = "improving"

    elif change <= -5:
        direction = "declining"

    else:
        direction = "stable"

    return {
        "current": current,
        "previous": previous,
        "change": change,
        "direction": direction,
    }


# =========================================================
# CONFIDENCE
# =========================================================

def calculate_confidence(
    available_sources: int,
    total_expected_sources: int,
    data_freshness_score: Any = 100,
    consistency_score: Any = 100,
) -> float:
    """
    Calculate an explainable confidence score.

    Confidence is separate from opportunity.

    A market can have:
        high opportunity + low confidence
    or:
        low opportunity + high confidence.
    """

    try:

        available_sources = int(
            available_sources
        )

    except (
        TypeError,
        ValueError,
    ):
        available_sources = 0

    try:

        total_expected_sources = int(
            total_expected_sources
        )

    except (
        TypeError,
        ValueError,
    ):
        total_expected_sources = 0

    if total_expected_sources <= 0:

        source_coverage = 0.0

    else:

        source_coverage = clamp(
            (
                available_sources
                / total_expected_sources
            )
            * 100
        )

    freshness = clamp(
        data_freshness_score
    )

    consistency = clamp(
        consistency_score
    )

    confidence = (
        source_coverage * 0.40
        +
        freshness * 0.30
        +
        consistency * 0.30
    )

    return round(
        clamp(
            confidence
        )
        / 100,
        3,
    )


# =========================================================
# RANK MARKETS
# =========================================================

def rank_market_scores(
    markets: list[dict],
) -> list[dict]:
    """
    Sort analyzed market areas by opportunity score.
    """

    if not isinstance(
        markets,
        list,
    ):
        return []

    normalized = []

    for market in markets:

        if not isinstance(
            market,
            dict,
        ):
            continue

        score = clamp(
            market.get(
                "score",
                0,
            )
        )

        normalized.append({
            **market,
            "score": score,
            "label": score_label(
                score
            ),
        })

    normalized.sort(
        key=lambda item: item[
            "score"
        ],
        reverse=True,
    )

    return normalized


# =========================================================
# EXPLANATION
# =========================================================

def explain_score(
    result: dict,
) -> list[str]:
    """
    Generate concise human-readable explanations
    from the scored dimensions.
    """

    if not isinstance(
        result,
        dict,
    ):
        return []

    signals = result.get(
        "signals",
        {},
    )

    explanations = []

    labels = {
        "demographic_fit": (
            "Target-market demographic fit"
        ),
        "demand_signal": (
            "Current demand signals"
        ),
        "price_environment": (
            "Market price environment"
        ),
        "competition": (
            "Competitive environment"
        ),
        "seasonality": (
            "Seasonal demand conditions"
        ),
        "business_performance": (
            "Business performance"
        ),
    }

    ordered = sorted(
        signals.items(),
        key=lambda item: (
            abs(
                clamp(
                    item[1]
                ) - 50
            )
        ),
        reverse=True,
    )

    for key, value in ordered:

        score = clamp(
            value
        )

        label = labels.get(
            key,
            key,
        )

        if score >= 80:

            explanations.append(
                f"{label} are strongly favorable "
                f"({score}/100)."
            )

        elif score >= 65:

            explanations.append(
                f"{label} are favorable "
                f"({score}/100)."
            )

        elif score >= 50:

            explanations.append(
                f"{label} are relatively balanced "
                f"({score}/100)."
            )

        elif score >= 35:

            explanations.append(
                f"{label} show some pressure "
                f"({score}/100)."
            )

        else:

            explanations.append(
                f"{label} are unfavorable "
                f"({score}/100)."
            )

    return explanations[:6]


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "WEIGHTS",
    "clamp",
    "as_number",
    "weighted_average",
    "score_label",
    "score_level",
    "direction_score",
    "demographic_fit_score",
    "demand_signal_score",
    "price_environment_score",
    "competition_score",
    "seasonality_score",
    "business_performance_score",
    "calculate_opportunity_score",
    "category_market_score",
    "compare_scores",
    "calculate_confidence",
    "rank_market_scores",
    "explain_score",
]
