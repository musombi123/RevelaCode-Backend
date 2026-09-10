# backend/jumuiya/biashara/intelligence/recommendations.py

from __future__ import annotations

from typing import Any


# =========================================================
# CONSTANTS
# =========================================================

PRIORITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


DEFAULT_CONFIDENCE = 0.50


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
    minimum: float = 0.0,
    maximum: float = 100.0,
) -> float:
    """
    Clamp a numeric value into a range.
    """

    value = as_float(
        value,
        minimum,
    )

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


def normalize_confidence(
    value: Any,
) -> float:
    """
    Normalize confidence into 0-1.
    """

    value = as_float(
        value,
        DEFAULT_CONFIDENCE,
    )

    if value > 1:
        value /= 100.0

    return round(
        max(
            0.0,
            min(
                value,
                1.0,
            ),
        ),
        3,
    )


def normalize_text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(
        value
    ).strip()


def priority_rank(
    priority: str,
) -> int:
    return PRIORITY_ORDER.get(
        normalize_text(
            priority
        ).lower(),
        99,
    )


# =========================================================
# RECOMMENDATION FACTORY
# =========================================================

def recommendation(
    *,
    rec_type: str,
    priority: str,
    title: str,
    message: str,
    action: str,
    reason: str = "",
    confidence: Any = DEFAULT_CONFIDENCE,
    metric: Any = None,
    source: str = "market_intelligence",
) -> dict:
    """
    Create a standard recommendation object.

    The structure is deliberately frontend-friendly and
    can later be persisted or sent through notifications.
    """

    result = {
        "type": normalize_text(
            rec_type
        ) or "general",

        "priority": normalize_text(
            priority
        ).lower() or "medium",

        "title": normalize_text(
            title
        ),

        "message": normalize_text(
            message
        ),

        "action": normalize_text(
            action
        ),

        "reason": normalize_text(
            reason
        ),

        "confidence": normalize_confidence(
            confidence
        ),

        "source": normalize_text(
            source
        ) or "market_intelligence",
    }

    if metric is not None:
        result[
            "metric"
        ] = metric

    return result


# =========================================================
# DEMAND RECOMMENDATIONS
# =========================================================

def demand_recommendations(
    demand_score: Any,
    forecast: dict | None = None,
    confidence: Any = DEFAULT_CONFIDENCE,
) -> list[dict]:
    """
    Generate recommendations based on demand conditions.
    """

    score = clamp(
        demand_score
    )

    forecast = (
        forecast
        if isinstance(
            forecast,
            dict,
        )
        else {}
    )

    summary = forecast.get(
        "summary",
        {}
    )

    if not isinstance(
        summary,
        dict,
    ):
        summary = {}

    direction = normalize_text(
        summary.get(
            "direction"
        )
    ).lower()

    recommendations = []

    # -----------------------------------------------------
    # Strong demand
    # -----------------------------------------------------

    if score >= 80:

        recommendations.append(
            recommendation(
                rec_type="inventory",
                priority="high",
                title="Prepare for stronger demand",
                message=(
                    "Current demand signals are strongly favorable "
                    "for this market."
                ),
                action=(
                    "Increase availability of fast-moving products "
                    "while monitoring stock turnover."
                ),
                reason=(
                    f"Demand score is {score}/100."
                ),
                confidence=confidence,
                metric={
                    "demand_score": score,
                    "direction": direction or "strong",
                },
            )
        )

    # -----------------------------------------------------
    # Rising demand
    # -----------------------------------------------------

    if direction == "rising":

        recommendations.append(
            recommendation(
                rec_type="growth",
                priority="high",
                title="Demand is trending upward",
                message=(
                    "The available demand history indicates "
                    "an upward direction."
                ),
                action=(
                    "Prioritize high-performing products and "
                    "prepare additional stock before demand peaks."
                ),
                reason=(
                    "Forecast direction is rising."
                ),
                confidence=confidence,
                metric={
                    "direction": "rising",
                    "forecast": forecast.get(
                        "forecast",
                        [],
                    ),
                },
            )
        )

    # -----------------------------------------------------
    # Weak demand
    # -----------------------------------------------------

    if score < 35:

        recommendations.append(
            recommendation(
                rec_type="inventory",
                priority="high",
                title="Avoid overstocking",
                message=(
                    "Current demand signals are weak relative "
                    "to the available market indicators."
                ),
                action=(
                    "Reduce slow-moving stock exposure and test "
                    "demand with smaller inventory commitments."
                ),
                reason=(
                    f"Demand score is {score}/100."
                ),
                confidence=confidence,
                metric={
                    "demand_score": score,
                },
            )
        )

    # -----------------------------------------------------
    # Falling demand
    # -----------------------------------------------------

    if direction == "falling":

        recommendations.append(
            recommendation(
                rec_type="pricing",
                priority="medium",
                title="Review products facing declining demand",
                message=(
                    "The demand forecast is pointing downward."
                ),
                action=(
                    "Consider promotions, smaller stock purchases, "
                    "product repositioning, or alternative offerings."
                ),
                reason=(
                    "Forecast direction is falling."
                ),
                confidence=confidence,
                metric={
                    "direction": "falling",
                },
            )
        )

    return recommendations


# =========================================================
# PRICE RECOMMENDATIONS
# =========================================================

def price_recommendations(
    price_score: Any,
    economic_data: dict | None = None,
    product: dict | None = None,
    confidence: Any = DEFAULT_CONFIDENCE,
) -> list[dict]:
    """
    Generate recommendations based on the market price
    environment.
    """

    score = clamp(
        price_score
    )

    economic_data = (
        economic_data
        if isinstance(
            economic_data,
            dict,
        )
        else {}
    )

    product = (
        product
        if isinstance(
            product,
            dict,
        )
        else {}
    )

    inflation = as_float(
        economic_data.get(
            "inflation",
            0,
        )
    )

    transport_inflation = as_float(
        economic_data.get(
            "transport_inflation",
            0,
        )
    )

    recommendations = []

    # -----------------------------------------------------
    # High price pressure
    # -----------------------------------------------------

    if score < 40:

        recommendations.append(
            recommendation(
                rec_type="pricing",
                priority="high",
                title="Review pricing pressure",
                message=(
                    "Current macro-economic conditions may put "
                    "pressure on business operating costs."
                ),
                action=(
                    "Review supplier costs, transport expenses "
                    "and product pricing before margins compress."
                ),
                reason=(
                    "Price-environment score is below 40/100."
                ),
                confidence=confidence,
                metric={
                    "price_environment_score": score,
                    "inflation": inflation,
                    "transport_inflation": (
                        transport_inflation
                    ),
                },
            )
        )

    # -----------------------------------------------------
    # Moderate price pressure
    # -----------------------------------------------------

    elif score < 65:

        recommendations.append(
            recommendation(
                rec_type="pricing",
                priority="medium",
                title="Monitor your margins",
                message=(
                    "The market shows moderate cost pressure."
                ),
                action=(
                    "Review margins regularly and compare "
                    "supplier prices before restocking."
                ),
                reason=(
                    f"Price-environment score is {score}/100."
                ),
                confidence=confidence,
                metric={
                    "price_environment_score": score,
                },
            )
        )

    # -----------------------------------------------------
    # High inflation context
    # -----------------------------------------------------

    if inflation >= 10:

        recommendations.append(
            recommendation(
                rec_type="cost_control",
                priority="high",
                title="Protect against rising costs",
                message=(
                    "Inflation pressure is elevated in the "
                    "available economic data."
                ),
                action=(
                    "Review suppliers, operating costs and "
                    "lower-cost alternatives."
                ),
                reason=(
                    f"Reported inflation input is {inflation}%."
                ),
                confidence=confidence,
                metric={
                    "inflation": inflation,
                },
            )
        )

    # -----------------------------------------------------
    # Product margin
    # -----------------------------------------------------

    price = as_float(
        product.get(
            "price"
        )
    )

    cost_price = as_float(
        product.get(
            "cost_price"
        )
    )

    if price > 0:

        margin = (
            (
                price
                - cost_price
            )
            / price
        )

        if margin < 0.15:

            recommendations.append(
                recommendation(
                    rec_type="margin",
                    priority="high",
                    title="Low product margin detected",
                    message=(
                        "The current selling price leaves "
                        "limited room after product cost."
                    ),
                    action=(
                        "Review supplier pricing or evaluate "
                        "whether the selling price can be adjusted."
                    ),
                    reason=(
                        f"Estimated gross margin is "
                        f"{round(margin * 100, 2)}%."
                    ),
                    confidence=confidence,
                    metric={
                        "selling_price": price,
                        "cost_price": cost_price,
                        "gross_margin": round(
                            margin * 100,
                            2,
                        ),
                    },
                )
            )

    return recommendations


# =========================================================
# COMPETITION RECOMMENDATIONS
# =========================================================

def competition_recommendations(
    competition_score: Any,
    competition_data: dict | None = None,
    confidence: Any = DEFAULT_CONFIDENCE,
) -> list[dict]:
    """
    Generate recommendations based on competitive intensity.
    """

    score = clamp(
        competition_score
    )

    competition_data = (
        competition_data
        if isinstance(
            competition_data,
            dict,
        )
        else {}
    )

    recommendations = []

    # Remember:
    # competition score is an opportunity score:
    # higher = less competitive pressure.

    if score >= 80:

        recommendations.append(
            recommendation(
                rec_type="growth",
                priority="medium",
                title="Competitive pressure appears manageable",
                message=(
                    "Available competition indicators suggest "
                    "room to compete in this market."
                ),
                action=(
                    "Test differentiated products or services "
                    "and build early customer loyalty."
                ),
                reason=(
                    f"Competition opportunity score is {score}/100."
                ),
                confidence=confidence,
                metric={
                    "competition_score": score,
                },
            )
        )

    elif score <= 35:

        competitor_count = competition_data.get(
            "competitor_count"
        )

        recommendations.append(
            recommendation(
                rec_type="competition",
                priority="high",
                title="Differentiate before scaling",
                message=(
                    "The market appears to have relatively "
                    "high competitive pressure."
                ),
                action=(
                    "Differentiate through pricing, convenience, "
                    "quality, service or a focused niche."
                ),
                reason=(
                    f"Competition opportunity score is {score}/100."
                ),
                confidence=confidence,
                metric={
                    "competition_score": score,
                    "competitor_count": competitor_count,
                },
            )
        )

    return recommendations


# =========================================================
# SEASONAL RECOMMENDATIONS
# =========================================================

def seasonality_recommendations(
    seasonality_score: Any,
    seasonal_data: dict | None = None,
    confidence: Any = DEFAULT_CONFIDENCE,
) -> list[dict]:
    """
    Generate recommendations around seasonal demand.
    """

    score = clamp(
        seasonality_score
    )

    seasonal_data = (
        seasonal_data
        if isinstance(
            seasonal_data,
            dict,
        )
        else {}
    )

    direction = normalize_text(
        seasonal_data.get(
            "seasonal_direction"
        )
    ).lower()

    recommendations = []

    if score >= 80:

        recommendations.append(
            recommendation(
                rec_type="seasonality",
                priority="high",
                title="Prepare for seasonal demand",
                message=(
                    "Seasonal conditions appear favorable "
                    "for the target market."
                ),
                action=(
                    "Plan stock, staffing, promotions and "
                    "cash flow ahead of the expected peak."
                ),
                reason=(
                    f"Seasonality score is {score}/100."
                ),
                confidence=confidence,
                metric={
                    "seasonality_score": score,
                    "direction": direction,
                },
            )
        )

    elif score <= 30:

        recommendations.append(
            recommendation(
                rec_type="seasonality",
                priority="medium",
                title="Plan around weaker seasonal demand",
                message=(
                    "Seasonal demand may be below the normal "
                    "baseline."
                ),
                action=(
                    "Reduce unnecessary stock exposure and "
                    "focus on essential or evergreen offerings."
                ),
                reason=(
                    f"Seasonality score is {score}/100."
                ),
                confidence=confidence,
                metric={
                    "seasonality_score": score,
                },
            )
        )

    return recommendations


# =========================================================
# DEMOGRAPHIC RECOMMENDATIONS
# =========================================================

def demographic_recommendations(
    demographic_score: Any,
    demographics: dict | None = None,
    target_profile: dict | None = None,
    confidence: Any = DEFAULT_CONFIDENCE,
) -> list[dict]:
    """
    Generate recommendations using aggregate demographic
    market characteristics.

    Recommendations are market-level and do not infer
    anything about individual users.
    """

    score = clamp(
        demographic_score
    )

    demographics = (
        demographics
        if isinstance(
            demographics,
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

    recommendations = []

    age_groups = demographics.get(
        "age_groups",
        {}
    )

    if not isinstance(
        age_groups,
        dict,
    ):
        age_groups = {}

    # -----------------------------------------------------
    # Youth-oriented market
    # -----------------------------------------------------

    youth = as_float(
        age_groups.get(
            "15_24",
            age_groups.get(
                "18_24",
                0,
            ),
        )
    )

    if youth >= 30:

        recommendations.append(
            recommendation(
                rec_type="product_mix",
                priority="medium",
                title="Consider youth-oriented offerings",
                message=(
                    "The available aggregate demographic data "
                    "shows a substantial younger age segment."
                ),
                action=(
                    "Test affordable, convenient and "
                    "youth-relevant products or services."
                ),
                reason=(
                    f"Youth-segment input is {youth}%."
                ),
                confidence=confidence,
                metric={
                    "youth_share": youth,
                },
            )
        )

    # -----------------------------------------------------
    # Working-age market
    # -----------------------------------------------------

    working_age = (
        as_float(
            age_groups.get(
                "25_34",
                0,
            )
        )
        +
        as_float(
            age_groups.get(
                "35_64",
                0,
            )
        )
    )

    if working_age >= 40:

        recommendations.append(
            recommendation(
                rec_type="product_mix",
                priority="medium",
                title="Target working-age demand",
                message=(
                    "The market shows a substantial working-age "
                    "population segment in the available data."
                ),
                action=(
                    "Consider convenience, productivity, "
                    "household and service-oriented offerings."
                ),
                reason=(
                    f"Working-age segment input is {working_age}%."
                ),
                confidence=confidence,
                metric={
                    "working_age_share": working_age,
                },
            )
        )

    # -----------------------------------------------------
    # Weak overall fit
    # -----------------------------------------------------

    if score < 35:

        recommendations.append(
            recommendation(
                rec_type="market_fit",
                priority="medium",
                title="Recheck target-market fit",
                message=(
                    "Available demographic indicators do not "
                    "strongly align with the current target profile."
                ),
                action=(
                    "Compare alternative customer segments or "
                    "test a different product positioning."
                ),
                reason=(
                    f"Demographic fit score is {score}/100."
                ),
                confidence=confidence,
                metric={
                    "demographic_score": score,
                },
            )
        )

    return recommendations


# =========================================================
# INVENTORY RECOMMENDATIONS
# =========================================================

def inventory_recommendations(
    product: dict | None = None,
    low_stock: bool = False,
    stock_quantity: Any = 0,
    low_stock_threshold: Any = 5,
    forecast_direction: str = "",
    confidence: Any = DEFAULT_CONFIDENCE,
) -> list[dict]:
    """
    Generate direct inventory actions for a product.
    """

    product = (
        product
        if isinstance(
            product,
            dict,
        )
        else {}
    )

    stock_quantity = max(
        0.0,
        as_float(
            stock_quantity
        ),
    )

    low_stock_threshold = max(
        0.0,
        as_float(
            low_stock_threshold,
            5,
        ),
    )

    product_name = (
        normalize_text(
            product.get(
                "name"
            )
        )
        or "Product"
    )

    recommendations = []

    if low_stock:

        recommendations.append(
            recommendation(
                rec_type="inventory",
                priority="high",
                title=f"Restock {product_name}",
                message=(
                    f"{product_name} is at or below its "
                    "configured low-stock threshold."
                ),
                action=(
                    "Review available suppliers and replenish "
                    "before the product runs out."
                ),
                reason=(
                    f"Current stock is {stock_quantity} and "
                    f"the threshold is {low_stock_threshold}."
                ),
                confidence=confidence,
                metric={
                    "stock_quantity": stock_quantity,
                    "low_stock_threshold": (
                        low_stock_threshold
                    ),
                },
            )
        )

    if (
        forecast_direction == "rising"
        and stock_quantity
        <= low_stock_threshold * 2
    ):

        recommendations.append(
            recommendation(
                rec_type="inventory",
                priority="high",
                title=f"Prepare stock for {product_name}",
                message=(
                    "Demand is rising while current inventory "
                    "appears relatively limited."
                ),
                action=(
                    "Consider an earlier reorder to reduce the "
                    "risk of stock-outs."
                ),
                reason=(
                    "Forecast direction is rising and inventory "
                    "is close to the low-stock range."
                ),
                confidence=confidence,
                metric={
                    "stock_quantity": stock_quantity,
                    "forecast_direction": (
                        forecast_direction
                    ),
                },
            )
        )

    return recommendations


# =========================================================
# FULL RECOMMENDATION ENGINE
# =========================================================

def generate_recommendations(
    *,
    scores: dict | None = None,
    forecast: dict | None = None,
    demographics: dict | None = None,
    economics: dict | None = None,
    market: dict | None = None,
    competition: dict | None = None,
    seasonality: dict | None = None,
    business: dict | None = None,
    product: dict | None = None,
    confidence: Any = DEFAULT_CONFIDENCE,
) -> list[dict]:
    """
    Generate a complete recommendation set from the
    market-intelligence analysis.

    Expected score structure:

        {
            "demographic_fit": 75,
            "demand_signal": 82,
            "price_environment": 55,
            "competition": 68,
            "seasonality": 80,
            "business_performance": 60
        }
    """

    scores = (
        scores
        if isinstance(
            scores,
            dict,
        )
        else {}
    )

    forecast = (
        forecast
        if isinstance(
            forecast,
            dict,
        )
        else {}
    )

    demographics = (
        demographics
        if isinstance(
            demographics,
            dict,
        )
        else {}
    )

    economics = (
        economics
        if isinstance(
            economics,
            dict,
        )
        else {}
    )

    market = (
        market
        if isinstance(
            market,
            dict,
        )
        else {}
    )

    competition = (
        competition
        if isinstance(
            competition,
            dict,
        )
        else {}
    )

    seasonality = (
        seasonality
        if isinstance(
            seasonality,
            dict,
        )
        else {}
    )

    business = (
        business
        if isinstance(
            business,
            dict,
        )
        else {}
    )

    product = (
        product
        if isinstance(
            product,
            dict,
        )
        else {}
    )

    confidence = normalize_confidence(
        confidence
    )

    recommendations = []

    # -----------------------------------------------------
    # Demand
    # -----------------------------------------------------

    recommendations.extend(
        demand_recommendations(
            scores.get(
                "demand_signal",
                50,
            ),
            forecast,
            confidence,
        )
    )

    # -----------------------------------------------------
    # Price environment
    # -----------------------------------------------------

    recommendations.extend(
        price_recommendations(
            scores.get(
                "price_environment",
                50,
            ),
            economics,
            product,
            confidence,
        )
    )

    # -----------------------------------------------------
    # Competition
    # -----------------------------------------------------

    recommendations.extend(
        competition_recommendations(
            scores.get(
                "competition",
                50,
            ),
            competition,
            confidence,
        )
    )

    # -----------------------------------------------------
    # Seasonality
    # -----------------------------------------------------

    recommendations.extend(
        seasonality_recommendations(
            scores.get(
                "seasonality",
                50,
            ),
            seasonality,
            confidence,
        )
    )

    # -----------------------------------------------------
    # Demographics
    # -----------------------------------------------------

    recommendations.extend(
        demographic_recommendations(
            scores.get(
                "demographic_fit",
                50,
            ),
            demographics,
            None,
            confidence,
        )
    )

    # -----------------------------------------------------
    # Inventory
    # -----------------------------------------------------

    current_stock = as_float(
        product.get(
            "stock_quantity",
            0,
        )
    )

    stock_threshold = as_float(
        product.get(
            "low_stock_threshold",
            5,
        ),
        5,
    )

    low_stock = (
        current_stock
        <= stock_threshold
    )

    forecast_direction = normalize_text(
        forecast.get(
            "summary",
            {},
        ).get(
            "direction",
            "",
        )
        if isinstance(
            forecast.get(
                "summary",
                {},
            ),
            dict,
        )
        else ""
    ).lower()

    recommendations.extend(
        inventory_recommendations(
            product=product,
            low_stock=low_stock,
            stock_quantity=current_stock,
            low_stock_threshold=stock_threshold,
            forecast_direction=forecast_direction,
            confidence=confidence,
        )
    )

    # -----------------------------------------------------
    # Business performance
    # -----------------------------------------------------

    business_score = clamp(
        scores.get(
            "business_performance",
            50,
        )
    )

    sales_growth = as_float(
        business.get(
            "sales_growth",
            0,
        )
    )

    if sales_growth > 0.20:

        recommendations.append(
            recommendation(
                rec_type="growth",
                priority="medium",
                title="Build on current sales momentum",
                message=(
                    "Recent business performance shows positive "
                    "sales growth."
                ),
                action=(
                    "Identify the products and channels driving "
                    "that growth and prioritize them."
                ),
                reason=(
                    f"Sales growth input is "
                    f"{round(sales_growth * 100, 2)}%."
                ),
                confidence=confidence,
                metric={
                    "sales_growth": sales_growth,
                },
            )
        )

    elif sales_growth < -0.20:

        recommendations.append(
            recommendation(
                rec_type="growth",
                priority="high",
                title="Investigate declining sales",
                message=(
                    "Recent business performance shows a "
                    "negative sales direction."
                ),
                action=(
                    "Review product mix, pricing, stock availability "
                    "and customer demand before increasing spend."
                ),
                reason=(
                    f"Sales growth input is "
                    f"{round(sales_growth * 100, 2)}%."
                ),
                confidence=confidence,
                metric={
                    "sales_growth": sales_growth,
                },
            )
        )

    # -----------------------------------------------------
    # Weak business signal
    # -----------------------------------------------------

    if business_score < 35:

        recommendations.append(
            recommendation(
                rec_type="business_review",
                priority="medium",
                title="Review current business performance",
                message=(
                    "The current business-performance signal "
                    "is relatively weak."
                ),
                action=(
                    "Review sales, customer retention, margins "
                    "and inventory turnover."
                ),
                reason=(
                    f"Business-performance score is "
                    f"{business_score}/100."
                ),
                confidence=confidence,
                metric={
                    "business_performance": business_score,
                },
            )
        )

    return recommendations


# =========================================================
# DEDUPLICATION
# =========================================================

def deduplicate_recommendations(
    recommendations: list[dict],
) -> list[dict]:
    """
    Remove duplicate recommendations while preserving
    the strongest version of each recommendation.
    """

    if not isinstance(
        recommendations,
        list,
    ):
        return []

    seen = {}

    for item in recommendations:

        if not isinstance(
            item,
            dict,
        ):
            continue

        title = normalize_text(
            item.get(
                "title"
            )
        ).lower()

        if not title:
            continue

        existing = seen.get(
            title
        )

        if existing is None:

            seen[
                title
            ] = item

            continue

        current_confidence = (
            normalize_confidence(
                item.get(
                    "confidence",
                    0,
                )
            )
        )

        existing_confidence = (
            normalize_confidence(
                existing.get(
                    "confidence",
                    0,
                )
            )
        )

        current_priority = priority_rank(
            item.get(
                "priority",
                "medium",
            )
        )

        existing_priority = priority_rank(
            existing.get(
                "priority",
                "medium",
            )
        )

        if (
            current_priority
            < existing_priority
            or
            (
                current_priority
                == existing_priority
                and current_confidence
                > existing_confidence
            )
        ):

            seen[
                title
            ] = item

    return list(
        seen.values()
    )


# =========================================================
# SORTING
# =========================================================

def sort_recommendations(
    recommendations: list[dict],
) -> list[dict]:
    """
    Sort recommendations by priority and confidence.
    """

    if not isinstance(
        recommendations,
        list,
    ):
        return []

    return sorted(
        recommendations,
        key=lambda item: (
            priority_rank(
                item.get(
                    "priority",
                    "medium",
                )
            ),
            -normalize_confidence(
                item.get(
                    "confidence",
                    0,
                )
            ),
        ),
    )


# =========================================================
# TOP RECOMMENDATIONS
# =========================================================

def top_recommendations(
    recommendations: list[dict],
    limit: int = 5,
) -> list[dict]:
    """
    Return the most important recommendations.
    """

    try:

        limit = int(
            limit
        )

    except (
        TypeError,
        ValueError,
    ):

        limit = 5

    limit = max(
        1,
        min(
            limit,
            20,
        ),
    )

    cleaned = deduplicate_recommendations(
        recommendations
    )

    cleaned = sort_recommendations(
        cleaned
    )

    return cleaned[
        :limit
    ]


# =========================================================
# EXECUTIVE SUMMARY
# =========================================================

def recommendation_summary(
    recommendations: list[dict],
) -> dict:
    """
    Build summary counts for the dashboard.
    """

    recommendations = (
        recommendations
        if isinstance(
            recommendations,
            list,
        )
        else []
    )

    counts = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
    }

    for item in recommendations:

        if not isinstance(
            item,
            dict,
        ):
            continue

        priority = normalize_text(
            item.get(
                "priority",
                "medium",
            )
        ).lower()

        if priority not in counts:
            priority = "medium"

        counts[
            priority
        ] += 1

    ordered = top_recommendations(
        recommendations,
        5,
    )

    return {
        "total": len(
            recommendations
        ),

        "counts": counts,

        "top": ordered,

        "has_urgent_action": (
            counts["critical"] > 0
            or
            counts["high"] > 0
        ),
    }


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "recommendation",
    "demand_recommendations",
    "price_recommendations",
    "competition_recommendations",
    "seasonality_recommendations",
    "demographic_recommendations",
    "inventory_recommendations",
    "generate_recommendations",
    "deduplicate_recommendations",
    "sort_recommendations",
    "top_recommendations",
    "recommendation_summary",
]
