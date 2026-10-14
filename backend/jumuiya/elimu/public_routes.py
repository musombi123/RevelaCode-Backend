
from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, redirect, request

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import (
    current_user_id,
    require_authenticated,
)
from backend.jumuiya.core.responses import ok
from backend.jumuiya.elimu import school_verification


# Register this blueprint beneath elimu_bp.
#
# Public:
# GET   /public/schools
# GET   /public/school
# GET   /public/events
# GET   /public/calendar
# GET   /public/cbc/projects
# GET   /public/documents
# GET   /public/documents/<document_id>/download
#
# Authenticated school owner:
# PATCH /school/publication
# PATCH /cbc/projects/<project_id>/publication
# GET   /documents/manage
# POST  /documents/manage
# PATCH /documents/manage/<document_id>
# DELETE /documents/manage/<document_id>


public_bp = Blueprint(
    "jumuiya_elimu_public",
    __name__,
)

SCHOOLS = "jumuiya_schools"
EVENTS = "jumuiya_school_events"
CBC = "jumuiya_cbc_projects"
DOCUMENTS = "jumuiya_elimu_public_documents"

VERIFIED = "verified"
PUBLISHED = "published"

MAX_LIMIT = 100
DEFAULT_LIMIT = 30

DOCUMENT_CATEGORIES = {
    "fees",
    "forms",
    "calendar",
    "handbook",
    "admissions",
    "notices",
    "other",
}

DOCUMENT_STATUSES = {
    "draft",
    "published",
    "archived",
}


# ============================================================
# HELPERS
# ============================================================

def _text(value, default=""):
    if value is None:
        return default

    if not isinstance(value, str):
        return default

    return value.strip()


def _serialize(value):
    if isinstance(value, ObjectId):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        result = {}

        for key, item in value.items():
            if key == "_id":
                result["id"] = _serialize(item)
            else:
                result[str(key)] = _serialize(item)

        return result

    if isinstance(value, list):
        return [_serialize(item) for item in value]

    return value


def _limit():
    raw = request.args.get("limit", str(DEFAULT_LIMIT))

    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise APIError(
            "limit must be a whole number.",
            422,
            "validation_error",
        ) from exc

    if not 1 <= value <= MAX_LIMIT:
        raise APIError(
            f"limit must be between 1 and {MAX_LIMIT}.",
            422,
            "validation_error",
        )

    return value


def _json_body():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        raise APIError(
            "A JSON object request body is required.",
            400,
            "invalid_json",
        )

    return payload


def _object_id(value, label="resource"):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError, ValueError) as exc:
        raise APIError(
            f"Invalid {label} ID.",
            400,
            "invalid_id",
        ) from exc


def _verified_school_query():
    return {
        "status": "active",
        "verification_status": VERIFIED,
        "is_demo": {"$ne": True},
        "public_profile_enabled": True,
    }


def _public_school_summary(school):
    """Return only fields suitable for a public school directory."""
    return {
        "id": str(school["_id"]),
        "code": school.get("code", ""),
        "public_slug": school.get("public_slug", ""),
        "name": school.get("name", ""),
        "school_type": school.get("school_type", ""),
        "description": school.get("description", ""),
        "logo_url": school.get("logo_url", ""),
        "county": school.get("county", ""),
        "town": school.get("town", ""),
        "website": school.get("website", ""),
    }


def _public_school_profile(school):
    """
    Explicit public allowlist.

    Never return the full MongoDB school document here. In particular,
    omit owner_user_id, verification evidence, reviewer records, and
    internal verification history.
    """
    allowed_fields = (
        "code",
        "public_slug",
        "name",
        "school_type",
        "description",
        "public_description",
        "about",
        "about_school",
        "homepage_title",
        "cover_image_url",
        "curriculum",
        "established_year",
        "address",
        "motto",
        "mission",
        "vision",
        "principal_name",
        "phone",
        "email",
        "website",
        "postal_address",
        "location",
        "county",
        "town",
        "country",
        "logo_url",
        "academic_year",
        "current_term",
        "calendar_year",
        "courses",
        "departments",
        "co_curricular_activities",
        "teacher_services",
    )

    result = {
        "id": str(school["_id"]),
    }

    for field in allowed_fields:
        if field in {"courses", "departments", "co_curricular_activities", "teacher_services"}:
            value = school.get(field, [])
            result[field] = value if isinstance(value, list) else []
        else:
            result[field] = school.get(field, "")

    # Public website design settings are an allowlisted, validated projection.
    result["website_theme"] = _public_website_theme(school.get("website_theme"))
    result["public"] = True

    return _serialize(result)


def _resolve_public_school():
    """
    Resolve an explicitly published, verified school.

    Supported query selectors:
        ?school_id=<Mongo ObjectId>
        ?school_code=<school code>
        ?school_code=<public slug>

    When no selector is supplied, a default is accepted only if exactly
    one public school exists. Multi-school deployments must identify
    the intended school to avoid displaying the wrong school's data.
    """
    base_query = _verified_school_query()

    school_id = _text(request.args.get("school_id"))
    school_code = (
        _text(request.args.get("school_code"))
        or _text(request.args.get("code"))
    )

    if school_id:
        try:
            school_oid = ObjectId(school_id)
        except (InvalidId, TypeError, ValueError):
            # Allow non-ObjectId IDs only if the deployed schema supports them.
            matches = [
                {"school_id": school_id},
            ]
        else:
            matches = [
                {"_id": school_oid},
                {"school_id": school_id},
            ]

        query = {
            **base_query,
            "$or": matches,
        }

        school = collection(SCHOOLS).find_one(query)

        if not school:
            raise APIError(
                "The requested public school was not found.",
                404,
                "public_school_not_found",
            )

        return school

    if school_code:
        school = collection(SCHOOLS).find_one({
            **base_query,
            "$or": [
                {"code": school_code},
                {"public_slug": school_code},
            ],
        })

        if not school:
            raise APIError(
                "The requested public school was not found.",
                404,
                "public_school_not_found",
            )

        return school

    matches = list(
        collection(SCHOOLS)
        .find(base_query)
        .sort("name", 1)
        .limit(2)
    )

    if not matches:
        raise APIError(
            "No school has published its verified public profile yet.",
            404,
            "public_school_unavailable",
        )

    if len(matches) > 1:
        raise APIError(
            (
                "Specify school_id or school_code when requesting "
                "content for a particular school."
            ),
            400,
            "school_selector_required",
        )

    return matches[0]


def _verified_school_by_id(school_id):
    try:
        school_oid = ObjectId(str(school_id))
    except (InvalidId, TypeError, ValueError):
        return None

    return collection(SCHOOLS).find_one({
        "_id": school_oid,
        **_verified_school_query(),
    })


def _current_school_document_context():
    """Resolve the current verified school and whether the requester owns it."""
    user_id = str(current_user_id() or "").strip()
    if not user_id:
        raise APIError(
            "Authentication is required.",
            401,
            "authentication_required",
        )

    school = school_verification.require_accessible_school(user_id)
    if (
        not school
        or school.get("status") != "active"
        or school.get("verification_status") != VERIFIED
        or school.get("is_demo") is True
    ):
        raise APIError(
            "A verified, active school account is required for document submissions.",
            403,
            "verified_school_required",
        )

    is_owner = str(school.get("owner_user_id", "")) == user_id
    return school, is_owner


def _current_owner_school():
    """
    Require an authenticated owner of a verified real school.

    Ordinary school membership does not grant public publishing rights.
    Platform-admin permissions alone are also not treated as school
    ownership by this helper.
    """
    user_id = str(current_user_id() or "").strip()

    if not user_id:
        raise APIError(
            "Authentication is required.",
            401,
            "authentication_required",
        )

    school = school_verification.require_accessible_school(user_id)

    if not school or school.get("is_demo") is True:
        raise APIError(
            "A verified real school is required for public publishing.",
            403,
            "verified_school_required",
        )

    if school.get("verification_status") != VERIFIED:
        raise APIError(
            "The school must be verified before public publishing.",
            403,
            "school_verification_required",
        )

    if str(school.get("owner_user_id", "")) != user_id:
        raise APIError(
            "Only the school owner can change public publishing settings.",
            403,
            "school_owner_required",
        )

    return school


def _school_id(school):
    return str(school["_id"])


def _school_document_is_public(school_id):
    school = _verified_school_by_id(school_id)

    if not school:
        return None

    return school if school.get("public_profile_enabled") is True else None


def _public_event_projection(document):
    """Strip internal event fields before returning a public response."""
    return {
        "id": str(document["_id"]),
        "title": document.get("title", ""),
        "event_type": document.get("event_type", "school"),
        "description": document.get("description", ""),
        "start_date": document.get("start_date", ""),
        "end_date": document.get("end_date", ""),
        "location": document.get("location", ""),
        "organizer": document.get("organizer", ""),
        "academic_year": document.get("academic_year", ""),
        "term": document.get("term", ""),
        "is_annual": bool(document.get("is_annual", False)),
        "all_day": bool(document.get("all_day", False)),
        "calendar_year": document.get("calendar_year", ""),
        "status": document.get("status", ""),
    }


def _public_events(school, year=None, limit=None):
    visibility_query = {
        "school_id": _school_id(school),
        "status": {"$ne": "cancelled"},
        "visibility": {"$in": ["public", "community"]},
    }

    if year:
        year = _text(year)

        if not year or len(year) > 30:
            raise APIError(
                "year is invalid.",
                422,
                "validation_error",
            )

        visibility_query["$or"] = [
            {"calendar_year": year},
            {"start_date": {"$regex": f"^{year}"}},
        ]

    cursor = (
        collection(EVENTS)
        .find(visibility_query)
        .sort([
            ("start_date", 1),
            ("created_at", -1),
        ])
    )

    if limit is not None:
        cursor = cursor.limit(limit)

    return [
        _public_event_projection(document)
        for document in cursor
    ]


def _public_project_projection(document):
    """
    Deliberately omit student IDs, admission numbers, student names,
    teacher IDs, remarks, and school-internal metadata.
    """
    return {
        "id": str(document["_id"]),
        "title": document.get("title", ""),
        "description": document.get("description", ""),
        "category": document.get("category", ""),
        "skills": document.get("skills", []),
        "status": document.get("status", ""),
        "created_at": _serialize(document.get("created_at")),
        "updated_at": _serialize(document.get("updated_at")),
    }


def _document_host_allowlist():
    configured = os.getenv("ELIMU_PUBLIC_DOCUMENT_HOSTS", "")

    hosts = {
        item.strip().lower()
        for item in configured.split(",")
        if item.strip()
    }

    # Same-host files can be used without adding the backend hostname
    # separately. Cloudinary is trusted because Elimu uploads documents there.
    request_host = (request.host or "").split(":", 1)[0].strip().lower()

    if request_host:
        hosts.add(request_host)

    hosts.add("res.cloudinary.com")
    return hosts


def _validated_download_url(value):
    url = _text(value)

    if not url:
        raise APIError(
            "A hosted document URL is required.",
            422,
            "document_url_required",
        )

    parsed = urlparse(url)

    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise APIError(
            "Document URLs must be valid HTTPS URLs without embedded credentials.",
            422,
            "invalid_document_url",
        )

    allowed_hosts = _document_host_allowlist()

    if parsed.hostname.lower() not in allowed_hosts:
        raise APIError(
            (
                "This document host is not approved. Configure "
                "ELIMU_PUBLIC_DOCUMENT_HOSTS with the trusted storage host."
            ),
            422,
            "document_host_not_allowed",
        )

    return url


def _document_metadata(document):
    """Public-safe metadata; never return the backing storage URL."""
    return {
        "id": str(document["_id"]),
        "title": document.get("title", ""),
        "description": document.get("description", ""),
        "category": document.get("category", "other"),
        "filename": document.get("filename", ""),
        "file_type": document.get("file_type", ""),
        "file_size": document.get("file_size"),
        "published_at": _serialize(document.get("published_at")),
        "updated_at": _serialize(document.get("updated_at")),
        "status": document.get("status", ""),
        "is_public": bool(document.get("is_public", False)),
    }


def _document_payload(payload, *, existing=None):
    existing = existing or {}

    result = {}

    text_fields = {
        "title": 200,
        "description": 2000,
        "filename": 255,
        "file_type": 30,
    }

    for field, max_length in text_fields.items():
        if field in payload:
            value = payload[field]

            if not isinstance(value, str):
                raise APIError(
                    f"{field} must be text.",
                    422,
                    "validation_error",
                )

            value = value.strip()

            if len(value) > max_length:
                raise APIError(
                    f"{field} must not exceed {max_length} characters.",
                    422,
                    "validation_error",
                )

            if field == "title" and not value:
                raise APIError(
                    "title is required.",
                    422,
                    "validation_error",
                )

            result[field] = value

    if "category" in payload:
        category = _text(payload.get("category")).lower()

        if category not in DOCUMENT_CATEGORIES:
            raise APIError(
                "category is not supported.",
                422,
                "validation_error",
            )

        result["category"] = category

    if "file_size" in payload:
        value = payload["file_size"]

        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            or value > 200 * 1024 * 1024
        ):
            raise APIError(
                "file_size must be a whole number from 0 to 209715200 bytes.",
                422,
                "validation_error",
            )

        result["file_size"] = value

    if "download_url" in payload:
        result["download_url"] = _validated_download_url(
            payload["download_url"]
        )

    if "is_public" in payload:
        if not isinstance(payload["is_public"], bool):
            raise APIError(
                "is_public must be a boolean.",
                422,
                "validation_error",
            )

        result["is_public"] = payload["is_public"]

    if "status" in payload:
        status = _text(payload.get("status")).lower()

        if status not in DOCUMENT_STATUSES:
            raise APIError(
                "status must be draft, published, or archived.",
                422,
                "validation_error",
            )

        result["status"] = status

    # Validate the merged resulting record before saving.
    merged = {**existing, **result}

    if not merged.get("title"):
        raise APIError(
            "title is required.",
            422,
            "validation_error",
        )

    if not merged.get("download_url"):
        raise APIError(
            "download_url is required.",
            422,
            "document_url_required",
        )

    return result


def _owned_document(document_id, school):
    oid = _object_id(document_id, "document")

    document = collection(DOCUMENTS).find_one({
        "_id": oid,
        "school_id": _school_id(school),
    })

    if not document:
        raise APIError(
            "Document not found.",
            404,
            "document_not_found",
        )

    return document


# ============================================================
# PUBLIC SCHOOL DIRECTORY AND PROFILE
# ============================================================

@public_bp.get("/public/schools")
def list_public_schools():
    limit = _limit()

    schools = list(
        collection(SCHOOLS)
        .find(_verified_school_query())
        .sort("name", 1)
        .limit(limit)
    )

    return ok({
        "schools": [
            _public_school_summary(school)
            for school in schools
        ],
        "count": len(schools),
        "limit": limit,
    })


@public_bp.get("/public/school")
def get_public_school():
    school = _resolve_public_school()

    return ok({
        "school": _public_school_profile(school),
    })


@public_bp.get("/public/status")
def get_public_school_status():
    school = _resolve_public_school()
    school_id = _school_id(school)

    events_count = collection(EVENTS).count_documents({
        "school_id": school_id,
        "status": {"$ne": "cancelled"},
        "visibility": {"$in": ["public", "community"]},
    })

    projects_count = collection(CBC).count_documents({
        "school_id": school_id,
        "status": {"$in": ["active", "completed"]},
        "$or": [
            {"is_public": True},
            {"visibility": "public"},
        ],
    })

    documents_count = collection(DOCUMENTS).count_documents({
        "school_id": school_id,
        "is_public": True,
        "status": PUBLISHED,
    })

    return ok({
        "public": True,
        "school": {
            "id": school_id,
            "name": school.get("name", ""),
            "code": school.get("code", ""),
        },
        "counts": {
            "events": events_count,
            "cbc_projects": projects_count,
            "documents": documents_count,
        },
    })


# ============================================================
# PUBLIC EVENTS AND CALENDAR
# ============================================================

@public_bp.get("/public/events")
def get_public_events():
    school = _resolve_public_school()
    year = _text(request.args.get("year")) or None
    limit = _limit()

    events = _public_events(
        school,
        year=year,
        limit=limit,
    )

    return ok({
        "events": events,
        "count": len(events),
        "year": year,
    })


@public_bp.get("/public/calendar")
def get_public_calendar():
    school = _resolve_public_school()
    year = _text(request.args.get("year")) or None
    limit = _limit()

    events = _public_events(
        school,
        year=year,
        limit=limit,
    )

    return ok({
        "school": {
            "id": str(school["_id"]),
            "name": school.get("name", ""),
        },
        "year": year,
        "events": events,
        "count": len(events),
    })


# ============================================================
# PUBLIC CBC PROJECTS
# ============================================================

@public_bp.get("/public/cbc/projects")
def get_public_cbc_projects():
    school = _resolve_public_school()
    school_id = _school_id(school)
    limit = _limit()

    query = {
        "school_id": school_id,
        "status": {"$in": ["active", "completed"]},
        "$or": [
            {"is_public": True},
            {"visibility": "public"},
        ],
    }

    projects = list(
        collection(CBC)
        .find(query)
        .sort("created_at", -1)
        .limit(limit)
    )

    return ok({
        "projects": [
            _public_project_projection(project)
            for project in projects
        ],
        "count": len(projects),
        "limit": limit,
    })


@public_bp.patch("/cbc/projects/<project_id>/publication")
@require_authenticated
def update_project_publication(project_id):
    """
    Let only the verified school owner publish or unpublish a CBC project.
    The public-read endpoint still returns only a safe projection.
    """
    school = _current_owner_school()
    payload = _json_body()

    is_public = payload.get("is_public")

    if not isinstance(is_public, bool):
        raise APIError(
            "is_public must be a boolean.",
            422,
            "validation_error",
        )

    project_oid = _object_id(project_id, "project")

    project = collection(CBC).find_one({
        "_id": project_oid,
        "school_id": _school_id(school),
    })

    if not project:
        raise APIError(
            "CBC project not found in this school.",
            404,
            "cbc_project_not_found",
        )

    now = datetime.now(timezone.utc)

    update = {
        "is_public": is_public,
        "visibility": "public" if is_public else "school",
        "updated_at": now,
        "publicly_published_by": (
            str(current_user_id()) if is_public else None
        ),
    }

    if is_public:
        update["publicly_published_at"] = now
    else:
        update["publicly_published_at"] = None

    result = collection(CBC).find_one_and_update(
        {
            "_id": project_oid,
            "school_id": _school_id(school),
        },
        {"$set": update},
        return_document=True,
    )

    return ok({
        "project": _public_project_projection(result),
        "is_public": is_public,
    }, "CBC project publication updated.")


# ============================================================
# PUBLIC DOCUMENT LISTING AND DOWNLOAD
# ============================================================

@public_bp.get("/public/documents")
def get_public_documents():
    school = _resolve_public_school()
    school_id = _school_id(school)
    limit = _limit()

    query = {
        "school_id": school_id,
        "is_public": True,
        "status": PUBLISHED,
    }

    category = _text(request.args.get("category")).lower()

    if category:
        if category not in DOCUMENT_CATEGORIES:
            raise APIError(
                "category is not supported.",
                422,
                "validation_error",
            )

        query["category"] = category

    documents = list(
        collection(DOCUMENTS)
        .find(query)
        .sort([
            ("published_at", -1),
            ("updated_at", -1),
        ])
        .limit(limit)
    )

    return ok({
        "documents": [
            _document_metadata(document)
            for document in documents
        ],
        "count": len(documents),
        "limit": limit,
    })


@public_bp.get("/public/documents/<document_id>/download")
def download_public_document(document_id):
    document_oid = _object_id(document_id, "document")

    document = collection(DOCUMENTS).find_one({
        "_id": document_oid,
        "is_public": True,
        "status": PUBLISHED,
    })

    if not document:
        raise APIError(
            "Public document not found.",
            404,
            "public_document_not_found",
        )

    school = _school_document_is_public(
        document.get("school_id")
    )

    if not school:
        raise APIError(
            "Public document not found.",
            404,
            "public_document_not_found",
        )

    download_url = _validated_download_url(
        document.get("download_url")
    )

    response = redirect(download_url, code=302)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"

    return response


# ============================================================
# SCHOOL OWNER: PUBLIC PROFILE SETTING
# ============================================================

@public_bp.patch("/school/publication")
@require_authenticated
def update_public_profile_setting():
    school = _current_owner_school()
    payload = _json_body()

    enabled = payload.get("enabled")

    if not isinstance(enabled, bool):
        raise APIError(
            "enabled must be a boolean.",
            422,
            "validation_error",
        )

    result = collection(SCHOOLS).find_one_and_update(
        {
            "_id": school["_id"],
            "owner_user_id": str(current_user_id()),
            "status": "active",
            "verification_status": VERIFIED,
            "is_demo": {"$ne": True},
        },
        {
            "$set": {
                "public_profile_enabled": enabled,
                "public_profile_updated_at": datetime.now(timezone.utc),
            }
        },
        return_document=True,
    )

    if not result:
        raise APIError(
            "The verified school could not be updated.",
            409,
            "school_publication_update_failed",
        )

    return ok({
        "enabled": enabled,
        "school": {
            "id": str(result["_id"]),
            "name": result.get("name", ""),
        },
    }, "Public school profile setting updated.")


# ============================================================
# SCHOOL OWNER: PUBLIC WEBSITE SETTINGS
# ============================================================

# Website themes are data, never arbitrary CSS or executable content.
_WEBSITE_THEME_DEFAULTS = {
    "primary": "#047857",
    "secondary": "#064e3b",
    "accent": "#d4af37",
    "background": "#f8fafc",
    "surface": "#ffffff",
    "heading": "#0f172a",
    "body": "#475569",
    "header": "#ffffff",
    "footer": "#ffffff",
    "font_style": "modern",
    "button_style": "solid",
}
_WEBSITE_THEME_COLOR_FIELDS = tuple(
    field for field in _WEBSITE_THEME_DEFAULTS if field not in {"font_style", "button_style"}
)
_WEBSITE_THEME_OPTIONS = {
    "font_style": {"modern", "classic", "humanist"},
    "button_style": {"solid", "outline", "soft"},
}
_WEBSITE_THEME_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _public_website_theme(value):
    """Return a safe public theme, falling back field-by-field to defaults."""
    result = dict(_WEBSITE_THEME_DEFAULTS)
    if not isinstance(value, dict):
        return result
    for field in _WEBSITE_THEME_COLOR_FIELDS:
        candidate = value.get(field)
        if isinstance(candidate, str) and _WEBSITE_THEME_COLOR_RE.fullmatch(candidate.strip()):
            result[field] = candidate.strip().lower()
    for field, choices in _WEBSITE_THEME_OPTIONS.items():
        candidate = value.get(field)
        if isinstance(candidate, str) and candidate in choices:
            result[field] = candidate
    return result


def _validated_website_theme(value, base=None):
    """Validate a school theme and persist only supported colours and options."""
    if not isinstance(value, dict):
        raise APIError(
            "website_theme_draft must be an object of supported theme settings.",
            422,
            "validation_error",
        )
    unknown = set(value) - set(_WEBSITE_THEME_DEFAULTS)
    if unknown:
        raise APIError(
            "Unsupported website theme fields: " + ", ".join(sorted(unknown)),
            422,
            "validation_error",
        )
    result = _public_website_theme(base)
    for field in _WEBSITE_THEME_COLOR_FIELDS:
        if field not in value:
            continue
        candidate = value[field]
        if not isinstance(candidate, str) or not _WEBSITE_THEME_COLOR_RE.fullmatch(candidate.strip()):
            raise APIError(
                f"{field} must be a six-digit hexadecimal colour such as #0A74DA.",
                422,
                "validation_error",
            )
        result[field] = candidate.strip().lower()
    for field, choices in _WEBSITE_THEME_OPTIONS.items():
        if field not in value:
            continue
        candidate = value[field]
        if not isinstance(candidate, str) or candidate not in choices:
            raise APIError(
                f"{field} must be one of: {', '.join(sorted(choices))}.",
                422,
                "validation_error",
            )
        result[field] = candidate
    return result


_WEBSITE_TEXT_LIMITS = {
    "public_slug": 80,
    "description": 3000,
    "public_description": 3000,
    "about": 4000,
    "about_school": 4000,
    "homepage_title": 180,
    "motto": 300,
    "mission": 2000,
    "vision": 2000,
    "principal_name": 160,
    "phone": 50,
    "email": 254,
    "website": 500,
    "postal_address": 300,
    "location": 200,
    "county": 100,
    "town": 100,
    "country": 100,
    "logo_url": 1000,
    "cover_image_url": 1000,
    "curriculum": 160,
    "academic_year": 50,
    "current_term": 50,
    "calendar_year": 20,
    "established_year": 20,
    "address": 300,
}

_WEBSITE_URL_FIELDS = {"website", "logo_url", "cover_image_url"}

# These are curated public-facing offerings managed by the verified school owner.
# Only allowlisted fields are stored/returned; student records and internal staff
# membership documents are never used as a public directory.
_WEBSITE_LIST_SCHEMAS = {
    "courses": {
        "name": 180,
        "description": 1500,
        "duration": 120,
        "requirements": 500,
        "level": 100,
    },
    "departments": {
        "name": 180,
        "description": 1500,
        "subjects": 500,
    },
    "co_curricular_activities": {
        "name": 180,
        "category": 100,
        "description": 1500,
        "schedule": 180,
    },
    "teacher_services": {
        "teacher_name": 180,
        "subject": 180,
        "service": 180,
        "description": 1500,
        "availability": 180,
    },
}
_WEBSITE_LIST_REQUIRED = {
    "courses": ("name",),
    "departments": ("name",),
    "co_curricular_activities": ("name",),
    "teacher_services": ("teacher_name", "service"),
}
_MAX_WEBSITE_LIST_ENTRIES = 100


def _validated_website_entries(field, value):
    schema = _WEBSITE_LIST_SCHEMAS[field]
    if not isinstance(value, list):
        raise APIError(
            f"{field} must be a list of records.",
            422,
            "validation_error",
        )
    if len(value) > _MAX_WEBSITE_LIST_ENTRIES:
        raise APIError(
            f"{field} cannot contain more than {_MAX_WEBSITE_LIST_ENTRIES} records.",
            422,
            "validation_error",
        )

    result = []
    required = _WEBSITE_LIST_REQUIRED[field]
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise APIError(
                f"{field} record {index} must be an object.",
                422,
                "validation_error",
            )
        record = {}
        for key, maximum in schema.items():
            raw = item.get(key, "")
            if raw is None:
                raw = ""
            if not isinstance(raw, str):
                raise APIError(
                    f"{field} record {index} field {key} must be text.",
                    422,
                    "validation_error",
                )
            value_text = raw.strip()
            if len(value_text) > maximum:
                raise APIError(
                    f"{field} record {index} field {key} must be {maximum} characters or fewer.",
                    422,
                    "validation_error",
                )
            record[key] = value_text
        missing = [key for key in required if not record.get(key)]
        if missing:
            raise APIError(
                f"{field} record {index} requires: {', '.join(missing)}.",
                422,
                "validation_error",
            )
        result.append(record)
    return result


def _website_slug(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug[:80].strip("-")


def _owner_website_projection(school):
    fields = tuple(_WEBSITE_TEXT_LIMITS.keys())
    result = {
        "id": str(school["_id"]),
        "name": school.get("name", ""),
        "school_type": school.get("school_type", ""),
        "code": school.get("code", ""),
        "verification_status": school.get("verification_status", ""),
        "public_profile_enabled": school.get("public_profile_enabled") is True,
    }
    for field in fields:
        result[field] = school.get(field, "")
    for field in _WEBSITE_LIST_SCHEMAS:
        value = school.get(field, [])
        result[field] = value if isinstance(value, list) else []
    result["website_theme"] = _public_website_theme(school.get("website_theme"))
    result["website_theme_draft"] = _public_website_theme(
        school.get("website_theme_draft") or school.get("website_theme")
    )
    result["public_slug"] = result.get("public_slug") or _website_slug(school.get("name"))
    return result


@public_bp.get("/school/website-settings")
@require_authenticated
def get_owner_website_settings():
    school = _current_owner_school()
    return ok({"school": _owner_website_projection(school)})


@public_bp.patch("/school/website-settings")
@require_authenticated
def save_owner_website_settings():
    school = _current_owner_school()
    payload = _json_body()
    updates = {}

    for field, maximum in _WEBSITE_TEXT_LIMITS.items():
        if field not in payload:
            continue
        value = payload.get(field)
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise APIError(
                f"{field} must be text.",
                422,
                "validation_error",
            )
        value = value.strip()
        if len(value) > maximum:
            raise APIError(
                f"{field} must be {maximum} characters or fewer.",
                422,
                "validation_error",
            )
        updates[field] = value

    for field in _WEBSITE_LIST_SCHEMAS:
        if field in payload:
            updates[field] = _validated_website_entries(field, payload[field])

    if "website_theme_draft" in payload:
        updates["website_theme_draft"] = _validated_website_theme(
            payload["website_theme_draft"],
            base=school.get("website_theme_draft") or school.get("website_theme"),
        )

    publish_theme = payload.get("publish_website_theme", False)
    if not isinstance(publish_theme, bool):
        raise APIError(
            "publish_website_theme must be a boolean.",
            422,
            "validation_error",
        )
    if publish_theme:
        theme_candidate = payload.get(
            "website_theme_draft",
            school.get("website_theme_draft") or school.get("website_theme") or _WEBSITE_THEME_DEFAULTS,
        )
        published_theme = _validated_website_theme(
            theme_candidate,
            base=school.get("website_theme_draft") or school.get("website_theme"),
        )
        updates["website_theme"] = published_theme
        updates["website_theme_draft"] = published_theme

    requested_slug = updates.get("public_slug")
    slug_source = requested_slug or school.get("public_slug") or school.get("name")
    slug = _website_slug(slug_source)
    if not slug:
        raise APIError(
            "A public website slug could not be generated. Add the school name first.",
            422,
            "website_slug_required",
        )

    collision = collection(SCHOOLS).find_one({
        "public_slug": slug,
        "_id": {"$ne": school["_id"]},
    })
    if collision:
        raise APIError(
            "That public website address is already used by another school. Choose a different slug.",
            409,
            "website_slug_taken",
        )

    for field in _WEBSITE_URL_FIELDS:
        value = updates.get(field, school.get(field, ""))
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise APIError(
                f"{field} must be a valid HTTP or HTTPS URL.",
                422,
                "validation_error",
            )

    publish = payload.get(
        "publish",
        school.get("public_profile_enabled") is True,
    )
    if not isinstance(publish, bool):
        raise APIError(
            "publish must be a boolean.",
            422,
            "validation_error",
        )

    updates["public_slug"] = slug
    updates["public_profile_enabled"] = publish
    updates["public_profile_updated_at"] = datetime.now(timezone.utc)
    updates["public_website_updated_at"] = datetime.now(timezone.utc)

    result = collection(SCHOOLS).find_one_and_update(
        {
            "_id": school["_id"],
            "owner_user_id": str(current_user_id()),
            "status": "active",
            "verification_status": VERIFIED,
            "is_demo": {"$ne": True},
        },
        {"$set": updates},
        return_document=True,
    )

    if not result:
        raise APIError(
            "The verified school website settings could not be saved.",
            409,
            "website_settings_update_failed",
        )

    return ok(
        {"school": _owner_website_projection(result)},
        "School website settings saved.",
    )

# ============================================================
# SCHOOL OWNER: DOCUMENT MANAGEMENT
# ============================================================

@public_bp.get("/documents/manage")
@require_authenticated
def list_managed_documents():
    school, _is_owner = _current_school_document_context()

    documents = list(
        collection(DOCUMENTS)
        .find({"school_id": _school_id(school)})
        .sort("updated_at", -1)
        .limit(MAX_LIMIT)
    )

    return ok({
        "documents": [
            _document_metadata(document)
            for document in documents
        ],
        "count": len(documents),
    })


@public_bp.post("/documents/manage")
@require_authenticated
def create_managed_document():
    """Register an HTTPS-hosted document as a draft for school review."""
    school, is_owner = _current_school_document_context()
    payload = _json_body()
    now = datetime.now(timezone.utc)

    data = _document_payload(payload)

    if "download_url" not in data:
        data["download_url"] = _validated_download_url(
            payload.get("download_url")
        )

    data.setdefault("category", "other")
    data.setdefault("description", "")
    data.setdefault("filename", "")
    data.setdefault("file_type", "")
    data.setdefault("file_size", None)
    data.setdefault("is_public", False)
    data.setdefault("status", "draft")

    # Staff may submit resources, but only the owner can decide to publish them.
    if not is_owner:
        data["is_public"] = False
        data["status"] = "draft"

    if data["status"] == PUBLISHED and not data["is_public"]:
        raise APIError(
            "A published public document must set is_public to true.",
            422,
            "document_publication_invalid",
        )

    document = {
        **data,
        "school_id": _school_id(school),
        "created_by_user_id": str(current_user_id()),
        "created_at": now,
        "updated_at": now,
        "published_at": now if data["status"] == PUBLISHED else None,
    }

    result = collection(DOCUMENTS).insert_one(document)
    document["_id"] = result.inserted_id

    return ok({
        "document": _document_metadata(document),
    }, "School document registered for review.")


@public_bp.patch("/documents/manage/<document_id>")
@require_authenticated
def update_managed_document(document_id):
    school = _current_owner_school()
    existing = _owned_document(document_id, school)
    payload = _json_body()

    data = _document_payload(payload, existing=existing)

    if not data:
        raise APIError(
            "No supported document fields were supplied.",
            422,
            "validation_error",
        )

    effective_public = data.get(
        "is_public",
        existing.get("is_public", False),
    )
    effective_status = data.get(
        "status",
        existing.get("status", "draft"),
    )

    if effective_status == PUBLISHED and not effective_public:
        raise APIError(
            "A published public document must set is_public to true.",
            422,
            "document_publication_invalid",
        )

    now = datetime.now(timezone.utc)
    data["updated_at"] = now

    if effective_status == PUBLISHED and existing.get("status") != PUBLISHED:
        data["published_at"] = now

    if effective_status != PUBLISHED:
        data["published_at"] = None

    result = collection(DOCUMENTS).find_one_and_update(
        {
            "_id": existing["_id"],
            "school_id": _school_id(school),
        },
        {"$set": data},
        return_document=True,
    )

    return ok({
        "document": _document_metadata(result),
    }, "School document updated.")


@public_bp.delete("/documents/manage/<document_id>")
@require_authenticated
def delete_managed_document(document_id):
    school = _current_owner_school()
    existing = _owned_document(document_id, school)

    collection(DOCUMENTS).delete_one({
        "_id": existing["_id"],
        "school_id": _school_id(school),
    })

    # This deletes the MongoDB metadata record only. It does not delete
    # the file from the external storage provider.
    return ok({
        "deleted": True,
        "id": str(existing["_id"]),
    }, "School document removed from the library.")