"""
RevelaCode AI Gateway Context

Builds controlled, user-scoped ecosystem context for RevelaAI.

Design principles:
- Never expose MongoDB directly to RevelaAI.
- Reuse existing platform services.
- Keep context relevant to the user's request.
- Never return secrets, tokens, passwords, or OTPs.
- A missing optional service must not break the AI Gateway.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from backend.jumuiya.biashara import services as biashara_services
from backend.jumuiya.shamba import services as shamba_services
from backend.jumuiya.elimu import services as elimu_services
from backend.jumuiya.community import services as community_services


# =========================================================
# CONSTANTS
# =========================================================

MAX_FARMS = 5
MAX_CROPS_PER_FARM = 20
MAX_COMMUNITY_POSTS = 10

SENSITIVE_KEYS = {
    "password",
    "passwd",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "otp",
    "otp_code",
    "verification_code",
}


# =========================================================
# TIME
# =========================================================

def now_utc() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


# =========================================================
# SAFE SERIALIZATION
# =========================================================

def sanitize_value(value: Any) -> Any:
    """
    Recursively remove obvious sensitive fields before
    context is returned to RevelaAI.
    """

    if isinstance(value, dict):

        cleaned = {}

        for key, item in value.items():

            normalized_key = (
                str(key)
                .strip()
                .lower()
            )

            if normalized_key in SENSITIVE_KEYS:

                cleaned[key] = "[REDACTED]"
                continue

            cleaned[key] = sanitize_value(
                item
            )

        return cleaned

    if isinstance(value, list):

        return [
            sanitize_value(item)
            for item in value
        ]

    if hasattr(
        value,
        "isoformat",
    ):

        return value.isoformat()

    return value


# =========================================================
# SAFE SERVICE CALLS
# =========================================================

def safe_call(
    function: Callable,
    *args,
    **kwargs,
) -> tuple[Any, str | None]:
    """
    Execute an existing platform service safely.

    Returns:

        (result, None)

    or:

        (None, error_code)

    AI should not receive raw Python/database exceptions.
    """

    try:

        result = function(
            *args,
            **kwargs,
        )

        return (
            sanitize_value(result),
            None,
        )

    except Exception:

        return (
            None,
            "service_unavailable",
        )


def optional_service(
    module: Any,
    function_name: str,
    *args,
    **kwargs,
) -> tuple[Any, str | None]:
    """
    Call a service function only when it exists.

    This makes the gateway resilient while the ecosystem
    continues to evolve.
    """

    function = getattr(
        module,
        function_name,
        None,
    )

    if not callable(function):

        return (
            None,
            "not_available",
        )

    return safe_call(
        function,
        *args,
        **kwargs,
    )


# =========================================================
# REQUEST CLASSIFICATION HELPERS
# =========================================================

def text_contains(
    message: str,
    words: list[str],
) -> bool:
    """
    Determine whether the user's question is related
    to any of the supplied terms.
    """

    normalized = (
        str(message or "")
        .strip()
        .lower()
    )

    return any(
        word in normalized
        for word in words
    )


def needs_biashara_details(
    message: str,
) -> bool:

    return text_contains(
        message,
        [
            "sale",
            "sales",
            "revenue",
            "profit",
            "order",
            "orders",
            "customer",
            "customers",
            "product",
            "products",
            "stock",
            "inventory",
            "expense",
            "expenses",
            "business",
            "price",
            "pricing",
        ],
    )


def needs_shamba_details(
    message: str,
) -> bool:

    return text_contains(
        message,
        [
            "farm",
            "farmer",
            "crop",
            "crops",
            "maize",
            "beans",
            "soil",
            "harvest",
            "harvesting",
            "plant",
            "planting",
            "farming",
            "shamba",
            "agriculture",
        ],
    )


def needs_elimu_details(
    message: str,
) -> bool:

    return text_contains(
        message,
        [
            "school",
            "student",
            "students",
            "teacher",
            "teachers",
            "lesson",
            "lessons",
            "assignment",
            "assignments",
            "class",
            "cbc",
            "education",
            "elimu",
            "fees",
        ],
    )


def needs_community_details(
    message: str,
) -> bool:

    return text_contains(
        message,
        [
            "community",
            "post",
            "posts",
            "discussion",
            "discussions",
            "group",
            "groups",
            "people",
            "community feed",
        ],
    )


# =========================================================
# BIASHARA CONTEXT
# =========================================================

def get_biashara_context(
    user_id,
    message: str,
    include: dict,
) -> dict:

    context = {
        "domain": "biashara",
    }

    # -----------------------------------------------------
    # Business profile
    # -----------------------------------------------------

    business, _ = optional_service(
        biashara_services,
        "get_business_for_user",
        user_id,
    )

    if business is not None:
        context["business"] = business

    # -----------------------------------------------------
    # Main operating dashboard
    # -----------------------------------------------------

    dashboard, _ = optional_service(
        biashara_services,
        "dashboard",
        user_id,
    )

    if dashboard is not None:
        context["dashboard"] = dashboard

    # -----------------------------------------------------
    # Optional deeper operating data
    # -----------------------------------------------------

    detailed = (
        bool(include.get("products"))
        or bool(include.get("orders"))
        or bool(include.get("customers"))
        or bool(include.get("inventory"))
        or bool(include.get("sales"))
        or bool(include.get("expenses"))
        or needs_biashara_details(message)
    )

    if not detailed:
        return context

    # Products
    products, _ = optional_service(
        biashara_services,
        "list_products",
        user_id,
        None,
        None,
        None,
        50,
    )

    if products is not None:
        context["products"] = products

    # Orders
    orders, _ = optional_service(
        biashara_services,
        "list_orders",
        user_id,
        None,
        50,
    )

    if orders is not None:
        context["orders"] = orders

    # Customers
    customers, _ = optional_service(
        biashara_services,
        "list_customers",
        user_id,
        None,
        50,
    )

    if customers is not None:
        context["customers"] = customers

    # Low stock
    inventory, _ = optional_service(
        biashara_services,
        "low_stock",
        user_id,
        None,
    )

    if inventory is not None:
        context["low_stock"] = inventory

    # Expenses
    expenses, _ = optional_service(
        biashara_services,
        "list_expenses",
        user_id,
        50,
    )

    if expenses is not None:
        context["expenses"] = expenses

    return context


# =========================================================
# SHAMBA CONTEXT
# =========================================================

def get_shamba_context(
    user_id,
    message: str,
    include: dict,
) -> dict:

    context = {
        "domain": "shamba",
    }

    # -----------------------------------------------------
    # Farmer profile
    # -----------------------------------------------------

    farmer, _ = optional_service(
        shamba_services,
        "get_farmer",
        user_id,
    )

    if farmer is not None:
        context["farmer"] = farmer

    # -----------------------------------------------------
    # Shamba dashboard
    # -----------------------------------------------------

    dashboard, _ = optional_service(
        shamba_services,
        "dashboard",
        user_id,
    )

    if dashboard is not None:
        context["dashboard"] = dashboard

    # -----------------------------------------------------
    # Farms
    # -----------------------------------------------------

    farms, _ = optional_service(
        shamba_services,
        "list_farms",
        user_id,
    )

    if isinstance(
        farms,
        list,
    ):

        farms = farms[:MAX_FARMS]

        context["farms"] = farms

    # -----------------------------------------------------
    # Crops
    # -----------------------------------------------------

    detailed = (
        bool(include.get("crops"))
        or bool(include.get("farms"))
        or needs_shamba_details(message)
    )

    if detailed and isinstance(
        farms,
        list,
    ):

        crops_by_farm = {}

        for farm in farms:

            if not isinstance(
                farm,
                dict,
            ):
                continue

            farm_id = farm.get(
                "id"
            )

            if not farm_id:
                continue

            crops, _ = optional_service(
                shamba_services,
                "list_crops",
                user_id,
                farm_id,
                None,
            )

            if isinstance(
                crops,
                list,
            ):

                crops_by_farm[
                    str(farm_id)
                ] = crops[
                    :MAX_CROPS_PER_FARM
                ]

        if crops_by_farm:
            context["crops"] = crops_by_farm

    return context


# =========================================================
# ELIMU CONTEXT
# =========================================================

def get_elimu_context(
    user_id,
    message: str,
    include: dict,
) -> dict:

    context = {
        "domain": "elimu",
    }

    # -----------------------------------------------------
    # Education profile
    # -----------------------------------------------------

    profile, _ = optional_service(
        elimu_services,
        "get_profile",
        user_id,
    )

    if profile is not None:
        context["profile"] = profile

    # -----------------------------------------------------
    # School
    # -----------------------------------------------------

    school, _ = optional_service(
        elimu_services,
        "my_school",
        user_id,
    )

    if school is not None:
        context["school"] = school

    # -----------------------------------------------------
    # Dashboard
    # -----------------------------------------------------

    dashboard, _ = optional_service(
        elimu_services,
        "dashboard",
        user_id,
    )

    if dashboard is not None:
        context["dashboard"] = dashboard

    # -----------------------------------------------------
    # Optional education data
    # -----------------------------------------------------

    detailed = (
        bool(include.get("lessons"))
        or bool(include.get("assignments"))
        or bool(include.get("fees"))
        or bool(include.get("projects"))
        or needs_elimu_details(message)
    )

    if not detailed:
        return context

    lessons, _ = optional_service(
        elimu_services,
        "lessons",
        user_id,
        None,
    )

    if lessons is not None:
        context["lessons"] = lessons

    assignments, _ = optional_service(
        elimu_services,
        "assignments",
        user_id,
        None,
    )

    if assignments is not None:
        context["assignments"] = assignments

    fees, _ = optional_service(
        elimu_services,
        "student_fees",
        user_id,
    )

    if fees is not None:
        context["fees"] = fees

    projects, _ = optional_service(
        elimu_services,
        "student_projects",
        user_id,
    )

    if projects is not None:
        context["projects"] = projects

    return context


# =========================================================
# COMMUNITY CONTEXT
# =========================================================

def get_community_context(
    user_id,
    message: str,
    include: dict,
) -> dict:

    context = {
        "domain": "community",
    }

    should_load_feed = (
        bool(include.get("feed"))
        or needs_community_details(message)
    )

    if should_load_feed:

        feed, _ = optional_service(
            community_services,
            "feed",
            None,
            None,
            MAX_COMMUNITY_POSTS,
        )

        if isinstance(
            feed,
            list,
        ):

            context["feed"] = feed[
                :MAX_COMMUNITY_POSTS
            ]

    context["user_id"] = str(
        user_id
    )

    return context


# =========================================================
# GENERAL CONTEXT
# =========================================================

def get_general_context(
    user_id,
    message: str,
) -> dict:
    """
    General platform metadata.

    We deliberately do not dump the entire user's account
    or entire database into a general AI request.
    """

    return {
        "domain": "general",
        "ecosystem": {
            "platform": "RevelaCode",
            "architecture": "Jumuiya ecosystem",
            "hubs": [
                "biashara",
                "shamba",
                "elimu",
                "community",
            ],
        },
    }


# =========================================================
# DOMAIN DISPATCH
# =========================================================

def get_domain_context(
    user_id,
    domain: str,
    message: str,
    include: dict,
) -> dict:
    """
    Route context retrieval to the correct ecosystem domain.
    """

    domain = (
        str(domain or "general")
        .strip()
        .lower()
    )

    if domain == "biashara":

        return get_biashara_context(
            user_id,
            message,
            include,
        )

    if domain == "shamba":

        return get_shamba_context(
            user_id,
            message,
            include,
        )

    if domain == "elimu":

        return get_elimu_context(
            user_id,
            message,
            include,
        )

    if domain == "community":

        return get_community_context(
            user_id,
            message,
            include,
        )

    return get_general_context(
        user_id,
        message,
    )


# =========================================================
# PUBLIC CONTEXT BUILDER
# =========================================================

def get_ai_context(
    user_id,
    domain: str = "general",
    message: str = "",
    include: dict | None = None,
) -> dict:
    """
    Build the complete grounded context returned to RevelaAI.

    This function is intentionally retrieval-based.

    It does NOT:
        - expose MongoDB
        - dump the entire ecosystem
        - expose authentication secrets
        - perform LLM reasoning

    It DOES:
        - identify the requested ecosystem domain
        - reuse existing platform services
        - retrieve user-scoped data
        - sanitize the result
        - return structured grounding data
    """

    include = (
        include
        if isinstance(
            include,
            dict,
        )
        else {}
    )

    normalized_domain = (
        str(domain or "general")
        .strip()
        .lower()
    )

    context = get_domain_context(
        user_id=str(user_id),
        domain=normalized_domain,
        message=message,
        include=include,
    )

    return {
        "source": "revelacode_platform",
        "source_layer": "platform",
        "user_id": str(user_id),
        "domain": normalized_domain,
        "retrieved_at": now_utc(),
        "context": sanitize_value(
            context
        ),
    }