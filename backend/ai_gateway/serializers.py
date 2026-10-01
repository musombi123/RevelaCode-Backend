"""
RevelaCode AI Gateway Serializers

Normalizes platform data before it is sent to RevelaAI.

Responsibilities:
- Convert database-native values into JSON-safe values.
- Remove MongoDB implementation details.
- Keep AI context structured and predictable.
- Prevent oversized/uncontrolled payloads.
- Preserve useful ecosystem information without exposing internals.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

try:
    from bson import ObjectId
except ImportError:
    ObjectId = None


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_MAX_STRING_LENGTH = 5000
DEFAULT_MAX_LIST_ITEMS = 100
DEFAULT_MAX_DICT_ITEMS = 100


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
    "cookie",
    "session_token",
    "otp",
    "otp_code",
    "verification_code",
}


# =========================================================
# BASIC VALUE SERIALIZATION
# =========================================================

def serialize_value(
    value: Any,
    *,
    max_string_length: int = DEFAULT_MAX_STRING_LENGTH,
    max_list_items: int = DEFAULT_MAX_LIST_ITEMS,
    max_dict_items: int = DEFAULT_MAX_DICT_ITEMS,
    key: str | None = None,
) -> Any:
    """
    Convert a Python/database value into a JSON-safe value.

    Supported:
        - dict
        - list
        - tuple
        - ObjectId
        - datetime
        - date
        - Decimal
        - primitive values
    """

    normalized_key = (
        str(key or "")
        .strip()
        .lower()
    )

    # -----------------------------------------------------
    # Sensitive fields
    # -----------------------------------------------------

    if normalized_key in SENSITIVE_KEYS:

        return "[REDACTED]"

    # -----------------------------------------------------
    # None / primitives
    # -----------------------------------------------------

    if value is None:
        return None

    if isinstance(
        value,
        (str, int, float, bool),
    ):

        if isinstance(
            value,
            str,
        ):

            return value[
                :max_string_length
            ]

        return value

    # -----------------------------------------------------
    # ObjectId
    # -----------------------------------------------------

    if (
        ObjectId is not None
        and isinstance(
            value,
            ObjectId,
        )
    ):

        return str(
            value
        )

    # -----------------------------------------------------
    # Dates
    # -----------------------------------------------------

    if isinstance(
        value,
        (
            datetime,
            date,
        ),
    ):

        return value.isoformat()

    # -----------------------------------------------------
    # Decimal
    # -----------------------------------------------------

    if isinstance(
        value,
        Decimal,
    ):

        return float(
            value
        )

    # -----------------------------------------------------
    # Dictionaries
    # -----------------------------------------------------

    if isinstance(
        value,
        dict,
    ):

        result = {}

        for index, (
            item_key,
            item_value,
        ) in enumerate(
            value.items()
        ):

            if index >= max_dict_items:
                break

            result[str(
                item_key
            )] = serialize_value(
                item_value,
                max_string_length=max_string_length,
                max_list_items=max_list_items,
                max_dict_items=max_dict_items,
                key=str(item_key),
            )

        return result

    # -----------------------------------------------------
    # Lists / tuples
    # -----------------------------------------------------

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):

        return [
            serialize_value(
                item,
                max_string_length=max_string_length,
                max_list_items=max_list_items,
                max_dict_items=max_dict_items,
            )
            for item in list(value)[
                :max_list_items
            ]
        ]

    # -----------------------------------------------------
    # Generic objects with isoformat()
    # -----------------------------------------------------

    isoformat = getattr(
        value,
        "isoformat",
        None,
    )

    if callable(
        isoformat
    ):

        try:
            return isoformat()
        except Exception:
            pass

    # -----------------------------------------------------
    # Last-resort conversion
    # -----------------------------------------------------

    return str(
        value
    )[
        :max_string_length
    ]


# =========================================================
# DOCUMENT SERIALIZATION
# =========================================================

def serialize_document(
    document: Any,
) -> dict:
    """
    Serialize a single platform document.

    MongoDB `_id` is normalized into `id`.
    """

    if not isinstance(
        document,
        dict,
    ):
        return {}

    output = {}

    for key, value in document.items():

        normalized_key = str(
            key
        )

        # MongoDB implementation detail:
        # AI should use the public `id` field.
        if normalized_key == "_id":

            output["id"] = serialize_value(
                value,
                key="id",
            )

            continue

        output[
            normalized_key
        ] = serialize_value(
            value,
            key=normalized_key,
        )

    return output


# =========================================================
# MANY DOCUMENTS
# =========================================================

def serialize_documents(
    documents: Any,
    *,
    limit: int = DEFAULT_MAX_LIST_ITEMS,
) -> list[dict]:
    """
    Serialize a collection of platform documents.
    """

    if not isinstance(
        documents,
        (
            list,
            tuple,
        ),
    ):

        return []

    result = []

    for document in list(
        documents
    )[:limit]:

        serialized = (
            serialize_document(
                document
            )
        )

        if serialized:
            result.append(
                serialized
            )

    return result


# =========================================================
# BUSINESS CONTEXT
# =========================================================

def serialize_biashara_context(
    context: Any,
) -> dict:
    """
    Normalize Biashara data for RevelaAI.
    """

    if not isinstance(
        context,
        dict,
    ):
        return {
            "domain": "biashara",
        }

    output = {
        "domain": "biashara",
    }

    business = context.get(
        "business"
    )

    if isinstance(
        business,
        dict,
    ):

        output["business"] = (
            serialize_document(
                business
            )
        )

    dashboard = context.get(
        "dashboard"
    )

    if isinstance(
        dashboard,
        dict,
    ):

        output["dashboard"] = (
            serialize_document(
                dashboard
            )
        )

    products = context.get(
        "products"
    )

    if products is not None:

        output["products"] = (
            serialize_documents(
                products,
                limit=50,
            )
        )

    orders = context.get(
        "orders"
    )

    if orders is not None:

        output["orders"] = (
            serialize_documents(
                orders,
                limit=50,
            )
        )

    customers = context.get(
        "customers"
    )

    if customers is not None:

        output["customers"] = (
            serialize_documents(
                customers,
                limit=50,
            )
        )

    low_stock = context.get(
        "low_stock"
    )

    if low_stock is not None:

        output["low_stock"] = (
            serialize_value(
                low_stock,
                max_list_items=50,
            )
        )

    expenses = context.get(
        "expenses"
    )

    if expenses is not None:

        output["expenses"] = (
            serialize_documents(
                expenses,
                limit=50,
            )
        )

    return output


# =========================================================
# SHAMBA CONTEXT
# =========================================================

def serialize_shamba_context(
    context: Any,
) -> dict:
    """
    Normalize Shamba data for RevelaAI.
    """

    if not isinstance(
        context,
        dict,
    ):
        return {
            "domain": "shamba",
        }

    output = {
        "domain": "shamba",
    }

    farmer = context.get(
        "farmer"
    )

    if isinstance(
        farmer,
        dict,
    ):

        output["farmer"] = (
            serialize_document(
                farmer
            )
        )

    dashboard = context.get(
        "dashboard"
    )

    if isinstance(
        dashboard,
        dict,
    ):

        output["dashboard"] = (
            serialize_document(
                dashboard
            )
        )

    farms = context.get(
        "farms"
    )

    if farms is not None:

        output["farms"] = (
            serialize_documents(
                farms,
                limit=10,
            )
        )

    crops = context.get(
        "crops"
    )

    if crops is not None:

        output["crops"] = serialize_value(
            crops,
            max_list_items=20,
            max_dict_items=20,
        )

    return output


# =========================================================
# ELIMU CONTEXT
# =========================================================

def serialize_elimu_context(
    context: Any,
) -> dict:
    """
    Normalize Elimu data for RevelaAI.
    """

    if not isinstance(
        context,
        dict,
    ):
        return {
            "domain": "elimu",
        }

    output = {
        "domain": "elimu",
    }

    profile = context.get(
        "profile"
    )

    if isinstance(
        profile,
        dict,
    ):

        output["profile"] = (
            serialize_document(
                profile
            )
        )

    school = context.get(
        "school"
    )

    if isinstance(
        school,
        dict,
    ):

        output["school"] = (
            serialize_document(
                school
            )
        )

    dashboard = context.get(
        "dashboard"
    )

    if isinstance(
        dashboard,
        dict,
    ):

        output["dashboard"] = (
            serialize_document(
                dashboard
            )
        )

    for field, limit in (
        ("lessons", 50),
        ("assignments", 50),
        ("fees", 50),
        ("projects", 50),
    ):

        value = context.get(
            field
        )

        if value is not None:

            output[field] = (
                serialize_documents(
                    value,
                    limit=limit,
                )
            )

    return output


# =========================================================
# COMMUNITY CONTEXT
# =========================================================

def serialize_community_context(
    context: Any,
) -> dict:
    """
    Normalize Community data for RevelaAI.
    """

    if not isinstance(
        context,
        dict,
    ):
        return {
            "domain": "community",
        }

    output = {
        "domain": "community",
    }

    feed = context.get(
        "feed"
    )

    if feed is not None:

        output["feed"] = (
            serialize_documents(
                feed,
                limit=20,
            )
        )

    return output


# =========================================================
# DOMAIN-AWARE CONTEXT
# =========================================================

def serialize_domain_context(
    domain: str,
    context: Any,
) -> dict:
    """
    Serialize context according to the ecosystem domain.
    """

    normalized_domain = (
        str(domain or "general")
        .strip()
        .lower()
    )

    if normalized_domain == "biashara":

        return serialize_biashara_context(
            context
        )

    if normalized_domain == "shamba":

        return serialize_shamba_context(
            context
        )

    if normalized_domain == "elimu":

        return serialize_elimu_context(
            context
        )

    if normalized_domain == "community":

        return serialize_community_context(
            context
        )

    return serialize_value(
        context,
        max_list_items=100,
        max_dict_items=100,
    )


# =========================================================
# COMPLETE AI PAYLOAD
# =========================================================

def serialize_ai_context(
    *,
    user_id: Any,
    domain: str,
    context: Any,
    message: str = "",
    retrieved_at: str | None = None,
) -> dict:
    """
    Produce the final JSON-safe payload consumed by RevelaAI.

    Structure:

        {
            "source": "revelacode_platform",
            "user_id": "...",
            "domain": "...",
            "message": "...",
            "retrieved_at": "...",
            "context": {...}
        }
    """

    normalized_domain = (
        str(domain or "general")
        .strip()
        .lower()
    )

    return {
        "source": "revelacode_platform",

        "source_layer": "platform",

        "user_id": str(
            user_id
        ),

        "domain": normalized_domain,

        "message": str(
            message or ""
        )[
            :DEFAULT_MAX_STRING_LENGTH
        ],

        "retrieved_at": (
            retrieved_at
            or datetime.utcnow().isoformat()
            + "Z"
        ),

        "context": serialize_domain_context(
            normalized_domain,
            context,
        ),
    }