
# backend/jumuiya/platform_admin_routes.py

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from bson import ObjectId
from flask import Blueprint, request

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import (
    require_authenticated,
    require_roles,
)
from backend.jumuiya.core.responses import ok


# =========================================================
# BLUEPRINT
# =========================================================

platform_admin_bp = Blueprint(
    "jumuiya_platform_admin",
    __name__,
)

PLATFORM_ADMIN_ROLES = (
    "admin",
    "platform_admin",
    "super_admin",
    "revelacode_admin",
)

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
MAX_SEARCH_LENGTH = 120

FARMERS = "jumuiya_farmers"
BUSINESSES = "jumuiya_businesses"
SCHOOLS = "jumuiya_schools"


# =========================================================
# COMMON HELPERS
# =========================================================

def json_safe(value: Any) -> Any:
    """Convert MongoDB/Python values to JSON-safe values."""

    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            ("id" if key == "_id" else str(key)): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]

    return value


def required_roles(fn):
    """Require an authenticated, authorized platform administrator."""

    return require_authenticated(
        require_roles(*PLATFORM_ADMIN_ROLES)(fn)
    )


def pagination():
    """Validate page and limit query parameters."""

    try:
        page = int(request.args.get("page", "1"))
        limit = int(request.args.get("limit", str(DEFAULT_LIMIT)))
    except (TypeError, ValueError):
        raise APIError(
            "page and limit must be whole numbers.",
            422,
            "invalid_pagination",
        )

    if page < 1:
        raise APIError(
            "page must be at least 1.",
            422,
            "invalid_pagination",
        )

    if limit < 1 or limit > MAX_LIMIT:
        raise APIError(
            f"limit must be between 1 and {MAX_LIMIT}.",
            422,
            "invalid_pagination",
        )

    return page, limit


def search_text():
    """Read a bounded search phrase."""

    value = request.args.get("search", "").strip()

    if len(value) > MAX_SEARCH_LENGTH:
        raise APIError(
            f"search must not exceed {MAX_SEARCH_LENGTH} characters.",
            422,
            "invalid_search",
        )

    return value


def escaped_search_query(search, fields):
    """
    Build a literal, case-insensitive search.

    Escaping prevents user-entered search text from becoming
    an uncontrolled regular expression.
    """

    if not search:
        return None

    pattern = re.escape(search)

    return {
        "$or": [
            {
                field: {
                    "$regex": pattern,
                    "$options": "i",
                }
            }
            for field in fields
        ]
    }


def combine_queries(*queries):
    """Combine optional MongoDB query fragments with AND."""

    parts = [query for query in queries if query]

    if not parts:
        return {}

    if len(parts) == 1:
        return parts[0]

    return {"$and": parts}


def status_query(status):
    """Build an exact status filter for profile collections."""

    status = (status or "").strip().lower()

    if not status or status == "all":
        return None

    if len(status) > 40:
        raise APIError(
            "status is too long.",
            422,
            "invalid_status",
        )

    return {"status": status}


def serialize_profile(document, fields):
    """
    Return only explicitly selected profile fields.

    Never return the entire MongoDB document, tokens, or
    unreviewed internal application data by default.
    """

    if not document:
        return None

    result = {
        "id": str(document["_id"]),
    }

    for field in fields:
        if field in document:
            result[field] = json_safe(document[field])

    return result


def paginated_collection(
    *,
    collection_name,
    query,
    projection,
    fields,
    page,
    limit,
    resource_name,
):
    """Execute a paginated, read-only administrative listing."""

    documents = collection(collection_name)

    total = documents.count_documents(query)

    cursor = (
        documents
        .find(query, projection)
        .sort([
            ("created_at", -1),
            ("_id", -1),
        ])
        .skip((page - 1) * limit)
        .limit(limit)
    )

    items = [
        serialize_profile(document, fields)
        for document in cursor
    ]

    total_pages = math.ceil(total / limit) if total else 0

    return ok(
        {
            "items": items,
            "count": len(items),
            "resource": resource_name,
        },
        meta={
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        },
    )


# =========================================================
# SCHOOL STATUS FILTERS
# =========================================================

SCHOOL_STATUS_OPTIONS = {
    "all",
    "pending",
    "verified",
    "needs_information",
    "rejected",
    "suspended",
    "demo",
    "active",
}


def school_status_query(status):
    """
    Filter schools using the existing Elimu verification schema.

    Legacy active records without verification_status are
    included in the pending review category.
    """

    status = (status or "all").strip().lower()
    status = status.replace("-", "_")

    if status not in SCHOOL_STATUS_OPTIONS:
        raise APIError(
            "Unsupported school status filter.",
            422,
            "invalid_school_status",
        )

    if status == "all":
        return {}

    if status == "pending":
        return {
            "$or": [
                {"verification_status": "pending"},
                {"status": "pending_verification"},
                {"status": "pending"},
                {
                    "status": "active",
                    "verification_status": {"$exists": False},
                },
            ]
        }

    if status == "verified":
        return {
            "verification_status": "verified",
            "is_demo": {"$ne": True},
        }

    if status == "needs_information":
        return {
            "verification_status": "needs_information",
            "is_demo": {"$ne": True},
        }

    if status == "rejected":
        return {
            "$and": [
                {
                    "$or": [
                        {"verification_status": "rejected"},
                        {"status": "rejected"},
                    ]
                },
                {"is_demo": {"$ne": True}},
            ]
        }

    if status == "suspended":
        return {
            "status": "suspended",
            "is_demo": {"$ne": True},
        }

    if status == "demo":
        return {
            "$or": [
                {"is_demo": True},
                {"verification_status": "demo"},
            ]
        }

    return {
        "status": "active",
        "is_demo": {"$ne": True},
    }


# =========================================================
# ADMIN OVERVIEW
# =========================================================

@platform_admin_bp.get("/overview")
@required_roles
def get_platform_overview():
    """Return high-level profile counts across Jumuiya hubs."""

    farmer_collection = collection(FARMERS)
    business_collection = collection(BUSINESSES)
    school_collection = collection(SCHOOLS)

    total_schools = school_collection.count_documents({})
    real_schools = school_collection.count_documents({
        "is_demo": {"$ne": True},
    })

    verified_schools = school_collection.count_documents({
        "verification_status": "verified",
        "is_demo": {"$ne": True},
    })

    pending_schools = school_collection.count_documents(
        school_status_query("pending")
    )

    needs_information = school_collection.count_documents(
        school_status_query("needs_information")
    )

    rejected_schools = school_collection.count_documents(
        school_status_query("rejected")
    )

    return ok({
        "shamba_profiles": farmer_collection.count_documents({}),
        "biashara_profiles": business_collection.count_documents({}),
        "schools": total_schools,
        "real_schools": real_schools,
        "verified_schools": verified_schools,
        "pending_schools": pending_schools,
        "schools_needing_information": needs_information,
        "rejected_schools": rejected_schools,
    })


# =========================================================
# SHAMBA — ALL FARMER PROFILES
# =========================================================

SHAMBA_FIELDS = (
    "owner_user_id",
    "user_id",
    "farmer_name",
    "phone",
    "farm_name",
    "farm_count",
    "farming_type",
    "experience_years",
    "county",
    "town",
    "location",
    "farm_size",
    "farm_size_unit",
    "primary_crops",
    "livestock",
    "soil_type",
    "water_source",
    "irrigation_available",
    "primary_goal",
    "target_market",
    "description",
    "profile_completed",
    "status",
    "created_at",
    "updated_at",
)

SHAMBA_PROJECTION = {
    "_id": 1,
    **{field: 1 for field in SHAMBA_FIELDS},
}


@platform_admin_bp.get("/shamba-profiles")
@required_roles
def list_shamba_profiles():
    """
    List all Shamba farmer profiles.

    Query parameters:
        page=1
        limit=25
        search=farmer name, location, phone, or owner ID
        status=active
    """

    page, limit = pagination()
    search = search_text()

    status = status_query(request.args.get("status"))

    query = combine_queries(
        status,
        escaped_search_query(
            search,
            (
                "farmer_name",
                "phone",
                "farm_name",
                "county",
                "town",
                "location",
                "owner_user_id",
                "user_id",
            ),
        ),
    )

    return paginated_collection(
        collection_name=FARMERS,
        query=query,
        projection=SHAMBA_PROJECTION,
        fields=SHAMBA_FIELDS,
        page=page,
        limit=limit,
        resource_name="shamba_profiles",
    )


# =========================================================
# BIASHARA — ALL BUSINESS PROFILES
# =========================================================

BIASHARA_FIELDS = (
    "owner_user_id",
    "name",
    "slug",
    "description",
    "business_type",
    "category",
    "phone",
    "email",
    "location",
    "county",
    "logo_url",
    "currency",
    "payment_methods",
    "opening_hours",
    "status",
    "profile_complete",
    "created_at",
    "updated_at",
)

BIASHARA_PROJECTION = {
    "_id": 1,
    **{field: 1 for field in BIASHARA_FIELDS},
}


@platform_admin_bp.get("/businesses")
@required_roles
def list_business_profiles():
    """
    List all Biashara business profiles.

    Query parameters:
        page=1
        limit=25
        search=business name, category, email, county, or owner ID
        status=active
    """

    page, limit = pagination()
    search = search_text()

    status = status_query(request.args.get("status"))

    query = combine_queries(
        status,
        escaped_search_query(
            search,
            (
                "name",
                "slug",
                "description",
                "business_type",
                "category",
                "phone",
                "email",
                "location",
                "county",
                "owner_user_id",
            ),
        ),
    )

    return paginated_collection(
        collection_name=BUSINESSES,
        query=query,
        projection=BIASHARA_PROJECTION,
        fields=BIASHARA_FIELDS,
        page=page,
        limit=limit,
        resource_name="biashara_businesses",
    )


# =========================================================
# ELIMU — ALL SCHOOLS
# =========================================================

SCHOOL_FIELDS = (
    "owner_user_id",
    "name",
    "code",
    "registration_number",
    "registration_number_normalized",
    "registration_evidence_url",
    "description",
    "school_type",
    "motto",
    "principal_name",
    "administrator_name",
    "phone",
    "email",
    "website",
    "postal_address",
    "location",
    "county",
    "town",
    "country",
    "status",
    "verification_status",
    "is_demo",
    "review_notes",
    "submitted_at",
    "reviewed_at",
    "verified_at",
    "verified_by_user_id",
    "rejected_at",
    "rejected_by_user_id",
    "created_at",
    "updated_at",
)

SCHOOL_PROJECTION = {
    "_id": 1,
    **{field: 1 for field in SCHOOL_FIELDS},
}


@platform_admin_bp.get("/schools")
@required_roles
def list_all_schools():
    """
    List all Elimu schools, not only pending applications.

    Query parameters:
        page=1
        limit=25
        search=school name, registration number, county, or owner ID
        status=all|pending|verified|needs_information|rejected|
               suspended|demo|active
    """

    page, limit = pagination()
    search = search_text()

    school_status = school_status_query(
        request.args.get("status")
    )

    search_query = escaped_search_query(
        search,
        (
            "name",
            "code",
            "registration_number",
            "principal_name",
            "administrator_name",
            "phone",
            "email",
            "location",
            "county",
            "town",
            "owner_user_id",
        ),
    )

    query = combine_queries(
        school_status,
        search_query,
    )

    return paginated_collection(
        collection_name=SCHOOLS,
        query=query,
        projection=SCHOOL_PROJECTION,
        fields=SCHOOL_FIELDS,
        page=page,
        limit=limit,
        resource_name="schools",
    )