# backend/routes/study_routes.py

from __future__ import annotations

import json
import logging
import re
from html import escape as html_escape
import secrets
import os
import io
import hmac
import hashlib
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request, send_file
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from backend.db import get_db
from backend.utils.decorators import require_role
from backend.utils.current_role_auth import require_current_roles, PLATFORM_ADMIN_ROLES
from backend.jumuiya.core.permissions import current_user_id, require_authenticated

from backend.study.study_service import (
    StudyService,
)

from backend.study.lesson_processor import (
    LessonProcessor,
)

from backend.study.material_preferences import (
    MaterialPreferences,
)

from backend.study.rootword_service import (
    RootWordService,
)

from backend.study.bookmark_service import (
    BookmarkService,
)

from backend.study.sda_quarterly_service import (
    SDAQuarterlyService,
)

from backend.study.ai_context_service import (
    AIContextService,
)


# =========================================================
# LOGGING
# =========================================================

logger = logging.getLogger(
    "revelacode.study"
)


# =========================================================
# BLUEPRINT
# =========================================================
#
# main.py registers this blueprint with:
#
#     url_prefix="/api"
#
# Therefore:
#
#     /api/study/...
#
# =========================================================

study_bp = Blueprint(
    "study",
    __name__,
    url_prefix="/study",
)


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_PAGE = 1
DEFAULT_LIMIT = 50
MAX_LIMIT = 100

DEFAULT_SEARCH_LIMIT = 50
MAX_SEARCH_LIMIT = 100

DEFAULT_RECOMMENDATION_LIMIT = 20
MAX_RECOMMENDATION_LIMIT = 100


# =========================================================
# HELPERS
# =========================================================

def _json_body() -> Dict[str, Any]:
    """
    Safely return a JSON object from the request.
    """

    data = request.get_json(
        silent=True
    )

    return (
        data
        if isinstance(
            data,
            dict,
        )
        else {}
    )


def _clean_string(
    value: Any,
) -> str:
    """
    Normalize an arbitrary value into a trimmed string.
    """

    if value is None:
        return ""

    return str(
        value
    ).strip()


def _parse_int(
    value: Any,
    default: Optional[int] = None,
    *,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> Optional[int]:
    """
    Safely parse an integer value.
    """

    if value is None:
        return default

    text = _clean_string(
        value
    )

    if not text:
        return default

    try:

        number = int(
            text
        )

    except (
        TypeError,
        ValueError,
    ):

        return default

    if (
        minimum is not None
        and number < minimum
    ):
        return default

    if (
        maximum is not None
        and number > maximum
    ):
        return default

    return number


def _normalize_tags(
    value: Any,
) -> List[str]:
    """
    Accept tags as:

        ["faith", "SDA"]

    or:

        "faith,SDA"

    or:

        "[\"faith\", \"SDA\"]"
    """

    if value is None:
        return []

    if isinstance(
        value,
        str,
    ):

        text = value.strip()

        if not text:
            return []

        if (
            text.startswith("[")
            and text.endswith("]")
        ):

            try:

                parsed = json.loads(
                    text
                )

                if isinstance(
                    parsed,
                    list,
                ):

                    value = parsed

                else:

                    value = text.split(",")

            except (
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):

                value = text.split(",")

        else:

            value = text.split(",")

    if not isinstance(
        value,
        (list, tuple, set),
    ):

        return []

    tags = []
    seen = set()

    for item in value:

        tag = _clean_string(
            item
        )

        if not tag:
            continue

        normalized = tag.casefold()

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        tags.append(
            tag
        )

    return tags


def _normalize_preferences(
    value: Any,
) -> List[str]:
    """
    Normalize user study preferences.
    """

    return _normalize_tags(
        value
    )


def _serialize_value(
    value: Any,
) -> Any:
    """
    Convert MongoDB/Python values into JSON-safe values.
    """

    if value is None:
        return None

    if isinstance(
        value,
        dict,
    ):

        return {
            str(key):
            _serialize_value(
                item
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):

        return [
            _serialize_value(
                item
            )
            for item in value
        ]

    if isinstance(
        value,
        (
            datetime,
            date,
        ),
    ):

        return value.isoformat()

    if value.__class__.__name__ == "ObjectId":

        return str(
            value
        )

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):

        return value

    return str(
        value
    )


def _error_response(
    message: str,
    status_code: int = 500,
    *,
    error: Any = None,
):
    """
    Return a consistent Study API error response.

    Internal exception details are logged, not exposed to
    the client.
    """

    payload = {
        "success": False,
        "message": message,
    }

    if error is not None:

        logger.error(
            "Study API error: %s",
            error,
            exc_info=True,
        )

    return jsonify(
        payload
    ), status_code


def _extract_ai_answer(
    value: Any,
) -> str:
    """
    Normalize different RevelaAI response shapes.
    """

    if value is None:
        return ""

    if isinstance(
        value,
        str,
    ):

        return value.strip()

    if isinstance(
        value,
        dict,
    ):

        for key in (
            "answer",
            "response",
            "content",
            "text",
            "output",
            "message",
        ):

            candidate = value.get(
                key
            )

            if isinstance(
                candidate,
                str,
            ) and candidate.strip():

                return candidate.strip()

        for key in (
            "data",
            "result",
        ):

            nested = value.get(
                key
            )

            if nested is not None:

                answer = (
                    _extract_ai_answer(
                        nested
                    )
                )

                if answer:
                    return answer

        return ""

    if isinstance(
        value,
        list,
    ):

        for item in value:

            answer = (
                _extract_ai_answer(
                    item
                )
            )

            if answer:
                return answer

        return ""

    return str(
        value
    ).strip()


def _paginate(
    items: List[Any],
    page: int,
    limit: int,
):
    """
    Apply API-level pagination while preserving the existing
    StudyService list contract.
    """

    total = len(
        items
    )

    start = (
        (page - 1)
        * limit
    )

    end = (
        start
        + limit
    )

    paged = items[
        start:end
    ]

    total_pages = (
        (
            total
            + limit
            - 1
        )
        // limit
        if total
        else 0
    )

    return (
        paged,
        {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
            "has_next": (
                page < total_pages
            ),
            "has_previous": (
                page > 1
            ),
        },
    )


# =========================================================
# STUDY HEALTH
# =========================================================

@study_bp.route(
    "/health",
    methods=["GET"],
)
def study_health():
    """
    Lightweight Study API diagnostic.

    Public endpoint:

        GET /api/study/health
    """

    return jsonify({
        "success": True,
        "study": True,
        "service": "study",
        "status": "ok",
        "routes": {
            "materials":
                "/api/study/materials",

            "material":
                "/api/study/material/<material_id>",

            "search":
                "/api/study/search",

            "upload":
                "/api/study/upload",

            "ask_ai":
                "/api/study/ask-ai",

            "preferences":
                "/api/study/preferences",

            "recommend":
                "/api/study/recommend/<user_id>",

            "rootword":
                "/api/study/rootword",

            "bookmark":
                "/api/study/bookmark",

            "bookmarks":
                "/api/study/bookmarks/<user_id>",

            "sda_today":
                "/api/study/sda/today",

            "sda_week":
                "/api/study/sda/week",

            "sda_date":
                "/api/study/sda/date/<lesson_date>",

            "sda_quarter":
                "/api/study/sda/quarter/<year>/<quarter>",

            "sda_import":
                "/api/study/sda/import",
        },
    }), 200


# =========================================================
# CURATED FAITH CATALOGUE
# =========================================================

@study_bp.route(
    "/seed-faith-catalog",
    methods=["POST"],
)
@require_current_roles(*PLATFORM_ADMIN_ROLES, "support_admin")
def seed_faith_catalog_route():
    """Publish/update the reviewed starter Faith lessons (admin-only)."""
    try:
        from backend.study.faith_curated_catalog import publish_faith_catalog

        result = publish_faith_catalog()
        status = 200 if result.get("success") else 500
        return jsonify(_serialize_value(result)), status
    except Exception as exc:
        return _error_response(
            "Failed to publish the curated Faith catalogue.",
            500,
            error=exc,
        )


# =========================================================
# MATERIALS
# =========================================================

@study_bp.route(
    "/materials",
    methods=["GET"],
)
def get_materials():
    """
    Get Study materials.

    Examples:

        GET /api/study/materials

        GET /api/study/materials?category=faith

        GET /api/study/materials?subcategory=sda_quarterly

        GET /api/study/materials?material_type=lesson

        GET /api/study/materials?page=1&limit=20
    """

    try:

        category = (
            _clean_string(
                request.args.get(
                    "category"
                )
            )
            or None
        )

        subcategory = (
            _clean_string(
                request.args.get(
                    "subcategory"
                )
            )
            or None
        )

        material_type = (
            _clean_string(
                request.args.get(
                    "material_type"
                )
            )
            or None
        )

        # -------------------------------------------------
        # Preserve legacy file_type requests.
        # -------------------------------------------------

        file_type = (
            _clean_string(
                request.args.get(
                    "file_type"
                )
            )
            or None
        )

        resolved_type = (
            material_type
            or file_type
            or None
        )

        materials = (
            StudyService
            .get_materials(
                category=category,
                subcategory=subcategory,
                material_type=resolved_type,
            )
        )

        if not isinstance(
            materials,
            list,
        ):

            materials = []

        page_requested = (
            request.args.get(
                "page"
            )
            is not None
        )

        limit_requested = (
            request.args.get(
                "limit"
            )
            is not None
        )

        page = _parse_int(
            request.args.get(
                "page"
            ),
            default=DEFAULT_PAGE,
            minimum=1,
        )

        limit = _parse_int(
            request.args.get(
                "limit"
            ),
            default=DEFAULT_LIMIT,
            minimum=1,
            maximum=MAX_LIMIT,
        )

        pagination = None

        if (
            page_requested
            or limit_requested
        ):

            response_materials, pagination = (
                _paginate(
                    materials,
                    page,
                    limit,
                )
            )

        else:

            response_materials = (
                materials
            )

        safe_materials = [
            _serialize_value(
                item
            )
            for item in response_materials
        ]

        response = {
            "success": True,
            "count": len(
                safe_materials
            ),
            "total": len(
                materials
            ),
            "materials": safe_materials,
        }

        if pagination is not None:

            response[
                "pagination"
            ] = pagination

        return jsonify(
            response
        ), 200

    except Exception as exc:

        return _error_response(
            "Failed to load study materials.",
            500,
            error=exc,
        )


# =========================================================
# SINGLE MATERIAL
# =========================================================

@study_bp.route(
    "/material/<material_id>",
    methods=["GET"],
)
def get_material(
    material_id,
):
    """
    Retrieve one Study material.
    """

    material_id = _clean_string(
        material_id
    )

    if not material_id:

        return _error_response(
            "material_id is required.",
            400,
        )

    try:

        material = (
            StudyService
            .get_material_by_id(
                material_id
            )
        )

        if not material:

            return _error_response(
                "Material not found.",
                404,
            )

        return jsonify({
            "success": True,
            "material":
                _serialize_value(
                    material
                ),
        }), 200

    except Exception as exc:

        return _error_response(
            "Failed to load study material.",
            500,
            error=exc,
        )


# =========================================================
# PREFERENCES
# =========================================================

@study_bp.route(
    "/preferences",
    methods=["POST"],
)
def save_preferences():
    """
    Save Study preferences.

    Expected:

        {
            "user_id": "...",
            "preferences": [
                "faith",
                "SDA",
                "Bible"
            ]
        }
    """

    data = _json_body()

    user_id = _clean_string(
        data.get(
            "user_id"
        )
    )

    preferences = data.get(
        "preferences",
        [],
    )

    if not user_id:

        return _error_response(
            "user_id is required.",
            400,
        )

    if not isinstance(
        preferences,
        list,
    ):

        return _error_response(
            "preferences must be a list.",
            400,
        )

    cleaned_preferences = (
        _normalize_preferences(
            preferences
        )
    )

    try:

        result = (
            MaterialPreferences
            .save_preferences(
                user_id,
                cleaned_preferences,
            )
        )

        status_code = (
            200
            if result.get(
                "success",
                False,
            )
            else 400
        )

        return jsonify(
            _serialize_value(
                result
            )
        ), status_code

    except Exception as exc:

        return _error_response(
            "Failed to save study preferences.",
            500,
            error=exc,
        )


# =========================================================
# GET PREFERENCES
# =========================================================

@study_bp.route(
    "/preferences/<user_id>",
    methods=["GET"],
)
def get_preferences(
    user_id,
):
    """
    Get saved Study preferences.
    """

    user_id = _clean_string(
        user_id
    )

    if not user_id:

        return _error_response(
            "user_id is required.",
            400,
        )

    try:

        preferences = (
            MaterialPreferences
            .get_preferences(
                user_id
            )
        )

        if not isinstance(
            preferences,
            list,
        ):

            preferences = []

        return jsonify({
            "success": True,
            "user_id": user_id,
            "preferences":
                _serialize_value(
                    preferences
                ),
            "count": len(
                preferences
            ),
        }), 200

    except Exception as exc:

        return _error_response(
            "Failed to load study preferences.",
            500,
            error=exc,
        )


# =========================================================
# RECOMMENDATIONS
# =========================================================

@study_bp.route(
    "/recommend/<user_id>",
    methods=["GET"],
)
def recommended_materials(
    user_id,
):
    """
    Get personalized Study recommendations.

    Optional:

        ?limit=20
    """

    user_id = _clean_string(
        user_id
    )

    if not user_id:

        return _error_response(
            "user_id is required.",
            400,
        )

    limit = _parse_int(
        request.args.get(
            "limit"
        ),
        default=DEFAULT_RECOMMENDATION_LIMIT,
        minimum=1,
        maximum=MAX_RECOMMENDATION_LIMIT,
    )

    try:

        materials = (
            MaterialPreferences
            .get_recommended_materials(
                user_id,
                limit=limit,
            )
        )

        if not isinstance(
            materials,
            list,
        ):

            materials = []

        safe_materials = [
            _serialize_value(
                item
            )
            for item in materials
        ]

        return jsonify({
            "success": True,
            "user_id": user_id,
            "count": len(
                safe_materials
            ),
            "materials":
                safe_materials,
        }), 200

    except Exception as exc:

        return _error_response(
            "Failed to load study recommendations.",
            500,
            error=exc,
        )


# =========================================================
# STUDY STATS
# =========================================================

@study_bp.route(
    "/stats",
    methods=["GET"],
)
def study_stats():
    """
    Return Study library statistics.
    """

    try:

        result = (
            StudyService
            .get_stats()
        )

        return jsonify(
            _serialize_value(
                result
            )
        ), 200

    except Exception as exc:

        return _error_response(
            "Failed to load study statistics.",
            500,
            error=exc,
        )


# =========================================================
# UPLOAD / CREATE MATERIAL
# =========================================================
#
# Administrative operation.
#
# Existing admin authentication is reused through:
#
#     @require_role("admin")
#
# =========================================================

@study_bp.route(
    "/upload",
    methods=["POST"],
)
@require_role("admin")
def upload_material():
    """
    Create a Study material from:

        1. uploaded PDF/DOCX/TXT
        2. JSON text content
    """

    try:

        # =================================================
        # FILE UPLOAD
        # =================================================

        if "file" in request.files:

            file = request.files[
                "file"
            ]

            if not file.filename:

                return _error_response(
                    "No file selected.",
                    400,
                )

            title = (
                _clean_string(
                    request.form.get(
                        "title"
                    )
                )
                or None
            )

            category = (
                _clean_string(
                    request.form.get(
                        "category"
                    )
                )
                or None
            )

            subcategory = (
                _clean_string(
                    request.form.get(
                        "subcategory"
                    )
                )
                or None
            )

            year = _parse_int(
                request.form.get(
                    "year"
                ),
                default=None,
                minimum=1900,
                maximum=2100,
            )

            tags = _normalize_tags(
                request.form.get(
                    "tags"
                )
            )

            result = (
                LessonProcessor
                .process_uploaded_file(
                    file,
                    title=title,
                    category=category,
                    subcategory=subcategory,
                    year=year,
                    tags=tags,
                )
            )

            status_code = (
                200
                if result.get(
                    "success",
                    False,
                )
                else 400
            )

            return jsonify(
                _serialize_value(
                    result
                )
            ), status_code

        # =================================================
        # TEXT MATERIAL
        # =================================================

        data = _json_body()

        title = _clean_string(
            data.get(
                "title"
            )
        )

        category = _clean_string(
            data.get(
                "category"
            )
        )

        subcategory = _clean_string(
            data.get(
                "subcategory"
            )
        )

        content = _clean_string(
            data.get(
                "content"
            )
        )

        if not title:

            return _error_response(
                "title is required.",
                400,
            )

        if not category:

            return _error_response(
                "category is required.",
                400,
            )

        if not subcategory:

            return _error_response(
                "subcategory is required.",
                400,
            )

        if not content:

            return _error_response(
                "content is required.",
                400,
            )

        year = _parse_int(
            data.get(
                "year"
            ),
            default=None,
            minimum=1900,
            maximum=2100,
        )

        tags = _normalize_tags(
            data.get(
                "tags",
                [],
            )
        )

        result = (
            LessonProcessor
            .process_text_material(
                title=title,
                category=category,
                subcategory=subcategory,
                content=content,
                year=year,
                tags=tags,
            )
        )

        status_code = (
            200
            if result.get(
                "success",
                False,
            )
            else 400
        )

        return jsonify(
            _serialize_value(
                result
            )
        ), status_code

    except ValueError as exc:

        return _error_response(
            str(exc),
            400,
        )

    except Exception as exc:

        return _error_response(
            "Study material upload failed.",
            500,
            error=exc,
        )


# =========================================================
# SEARCH
# =========================================================

@study_bp.route(
    "/search",
    methods=["GET"],
)
def search_materials():
    """
    Search Study materials.

    Example:

        GET /api/study/search?q=faith&limit=20
    """

    query = _clean_string(
        request.args.get(
            "q",
            "",
        )
    )

    if not query:

        return jsonify({
            "success": True,
            "count": 0,
            "query": "",
            "results": [],
        }), 200

    limit = _parse_int(
        request.args.get(
            "limit"
        ),
        default=DEFAULT_SEARCH_LIMIT,
        minimum=1,
        maximum=MAX_SEARCH_LIMIT,
    )

    try:

        results = (
            StudyService
            .search_materials(
                query,
                limit=limit,
            )
        )

        if not isinstance(
            results,
            list,
        ):

            results = []

        safe_results = [
            _serialize_value(
                item
            )
            for item in results
        ]

        return jsonify({
            "success": True,
            "count": len(
                safe_results
            ),
            "query": query,
            "results":
                safe_results,
        }), 200

    except Exception as exc:

        return _error_response(
            "Failed to search study materials.",
            500,
            error=exc,
        )


# =========================================================
# AI STUDY ASSISTANT
# =========================================================

@study_bp.route(
    "/ask-ai",
    methods=["POST"],
)
def ask_study_ai():
    """
    Ask RevelaAI about a specific Study material.

    Expected:

        {
            "material_id": "...",
            "question": "Explain this lesson."
        }
    """

    data = _json_body()

    material_id = _clean_string(
        data.get(
            "material_id"
        )
    )

    question = (
        _clean_string(
            data.get(
                "question"
            )
        )
        or
        _clean_string(
            data.get(
                "user_question"
            )
        )
    )

    if not material_id:

        return _error_response(
            "material_id is required.",
            400,
        )

    if not question:

        return _error_response(
            "question is required.",
            400,
        )

    try:

        # -------------------------------------------------
        # Verify material and AI availability.
        # -------------------------------------------------

        material = (
            StudyService
            .get_material_by_id(
                material_id
            )
        )

        if not material:

            return _error_response(
                "Study material not found.",
                404,
            )

        if (
            isinstance(
                material,
                dict,
            )
            and material.get(
                "ai_enabled",
                True,
            )
            is False
        ):

            return _error_response(
                "AI assistance is disabled for this material.",
                403,
            )

        result = (
            AIContextService
            .ask_material_ai(
                material_id,
                question,
            )
        )

        if not isinstance(
            result,
            dict,
        ):

            answer = (
                _extract_ai_answer(
                    result
                )
            )

            return jsonify({
                "success": bool(
                    answer
                ),
                "material_id":
                    material_id,
                "question":
                    question,
                "answer":
                    answer,
            }), 200

        result = _serialize_value(
            result
        )

        raw_answer = result.get(
            "answer"
        )

        normalized_answer = (
            _extract_ai_answer(
                raw_answer
            )
        )

        if normalized_answer:

            result[
                "answer"
            ] = normalized_answer

        return jsonify(
            result
        ), 200

    except Exception as exc:

        return _error_response(
            "Study AI request failed.",
            500,
            error=exc,
        )


# =========================================================
# ROOTWORD SEARCH
# =========================================================

@study_bp.route(
    "/rootword",
    methods=["GET"],
)
def search_rootword():
    """
    Search Biblical/Hebrew/Greek root words.

    Example:

        GET /api/study/rootword?word=logos
    """

    word = _clean_string(
        request.args.get(
            "word",
            "",
        )
    )

    if not word:

        return _error_response(
            "word is required.",
            400,
        )

    limit = _parse_int(
        request.args.get(
            "limit"
        ),
        default=25,
        minimum=1,
        maximum=100,
    )

    try:

        result = (
            RootWordService
            .search(
                word,
                limit=limit,
            )
        )

        return jsonify(
            _serialize_value(
                result
            )
        ), (
            200
            if result.get(
                "success",
                False,
            )
            else 400
        )

    except Exception as exc:

        return _error_response(
            "Failed to search root words.",
            500,
            error=exc,
        )


# =========================================================
# ADD ROOTWORD
# =========================================================

@study_bp.route(
    "/rootword",
    methods=["POST"],
)
@require_role("admin")
def add_rootword():
    """
    Create a Biblical/Hebrew/Greek root-word record.

    Administrative operation.
    """

    data = _json_body()

    word = _clean_string(
        data.get(
            "word"
        )
    )

    if not word:

        return _error_response(
            "word is required.",
            400,
        )

    try:

        result = (
            RootWordService
            .add_rootword(
                word=word,

                language=_clean_string(
                    data.get(
                        "language"
                    )
                )
                or None,

                strong_number=_clean_string(
                    data.get(
                        "strong_number"
                    )
                )
                or None,

                transliteration=_clean_string(
                    data.get(
                        "transliteration"
                    )
                )
                or None,

                meaning=_clean_string(
                    data.get(
                        "meaning"
                    )
                )
                or None,

                scriptures=(
                    data.get(
                        "scriptures",
                        [],
                    )
                    if isinstance(
                        data.get(
                            "scriptures",
                            [],
                        ),
                        list,
                    )
                    else []
                ),

                notes=(
                    data.get(
                        "notes",
                        [],
                    )
                    if isinstance(
                        data.get(
                            "notes",
                            [],
                        ),
                        list,
                    )
                    else []
                ),
            )
        )

        if not isinstance(
            result,
            dict,
        ):

            return _error_response(
                "Invalid root word service response.",
                500,
            )

        status_code = (
            200
            if result.get(
                "success",
                False,
            )
            else 400
        )

        return jsonify(
            _serialize_value(
                result
            )
        ), status_code

    except Exception as exc:

        return _error_response(
            "Failed to create root word.",
            500,
            error=exc,
        )


# =========================================================
# ADD BOOKMARK
# =========================================================

@study_bp.route(
    "/bookmark",
    methods=["POST"],
)
def save_bookmark():
    """
    Save a Study bookmark.
    """

    data = _json_body()

    user_id = _clean_string(
        data.get(
            "user_id"
        )
    )

    material_id = _clean_string(
        data.get(
            "material_id"
        )
    )

    if not user_id:

        return _error_response(
            "user_id is required.",
            400,
        )

    if not material_id:

        return _error_response(
            "material_id is required.",
            400,
        )

    try:

        result = (
            BookmarkService
            .add_bookmark(
                user_id,
                material_id,
            )
        )

        if not isinstance(
            result,
            dict,
        ):

            return _error_response(
                "Invalid bookmark service response.",
                500,
            )

        if result.get(
            "success",
            False,
        ):

            return jsonify(
                _serialize_value(
                    result
                )
            ), 200

        message = (
            result.get(
                "message"
            )
            or "Failed to save study bookmark."
        )

        if (
            "not found"
            in message.lower()
        ):

            status_code = 404

        else:

            status_code = 400

        return jsonify(
            _serialize_value(
                result
            )
        ), status_code

    except Exception as exc:

        return _error_response(
            "Failed to save study bookmark.",
            500,
            error=exc,
        )


# =========================================================
# REMOVE BOOKMARK
# =========================================================

@study_bp.route(
    "/bookmark",
    methods=["DELETE"],
)
def remove_bookmark():
    """
    Remove a Study bookmark.

    Expected:

        {
            "user_id": "...",
            "material_id": "..."
        }
    """

    data = _json_body()

    user_id = _clean_string(
        data.get(
            "user_id"
        )
    )

    material_id = _clean_string(
        data.get(
            "material_id"
        )
    )

    if not user_id:

        return _error_response(
            "user_id is required.",
            400,
        )

    if not material_id:

        return _error_response(
            "material_id is required.",
            400,
        )

    try:

        result = (
            BookmarkService
            .remove_bookmark(
                user_id,
                material_id,
            )
        )

        status_code = (
            200
            if result.get(
                "success",
                False,
            )
            else 400
        )

        return jsonify(
            _serialize_value(
                result
            )
        ), status_code

    except Exception as exc:

        return _error_response(
            "Failed to remove study bookmark.",
            500,
            error=exc,
        )


# =========================================================
# CHECK BOOKMARK
# =========================================================

@study_bp.route(
    "/bookmark/check",
    methods=["GET"],
)
def check_bookmark():
    """
    Check bookmark state.

    Example:

        GET /api/study/bookmark/check
            ?user_id=...
            &material_id=...
    """

    user_id = _clean_string(
        request.args.get(
            "user_id"
        )
    )

    material_id = _clean_string(
        request.args.get(
            "material_id"
        )
    )

    if not user_id:

        return _error_response(
            "user_id is required.",
            400,
        )

    if not material_id:

        return _error_response(
            "material_id is required.",
            400,
        )

    try:

        bookmarked = (
            BookmarkService
            .is_bookmarked(
                user_id,
                material_id,
            )
        )

        return jsonify({
            "success": True,
            "user_id": user_id,
            "material_id": material_id,
            "bookmarked": bool(
                bookmarked
            ),
        }), 200

    except Exception as exc:

        return _error_response(
            "Failed to check study bookmark.",
            500,
            error=exc,
        )


# =========================================================
# GET BOOKMARKS
# =========================================================

@study_bp.route(
    "/bookmarks/<user_id>",
    methods=["GET"],
)
def get_bookmarks(
    user_id,
):
    """
    Get a user's bookmarked Study materials.
    """

    user_id = _clean_string(
        user_id
    )

    if not user_id:

        return _error_response(
            "user_id is required.",
            400,
        )

    limit = _parse_int(
        request.args.get(
            "limit"
        ),
        default=DEFAULT_LIMIT,
        minimum=1,
        maximum=MAX_LIMIT,
    )

    try:

        bookmarks = (
            BookmarkService
            .get_bookmarks(
                user_id,
                limit=limit,
            )
        )

        if not isinstance(
            bookmarks,
            list,
        ):

            bookmarks = []

        materials = []
        bookmark_records = []

        for bookmark in bookmarks:

            if not isinstance(
                bookmark,
                dict,
            ):
                continue

            material_id = _clean_string(
                bookmark.get(
                    "material_id"
                )
            )

            if not material_id:
                continue

            bookmark_records.append(
                bookmark
            )

            material = (
                StudyService
                .get_material_by_id(
                    material_id
                )
            )

            if material:

                materials.append(
                    material
                )

        safe_materials = [
            _serialize_value(
                material
            )
            for material in materials
        ]

        return jsonify({
            "success": True,
            "user_id": user_id,
            "count": len(
                safe_materials
            ),
            "bookmarks":
                safe_materials,
            "bookmark_records":
                _serialize_value(
                    bookmark_records
                ),
        }), 200

    except Exception as exc:

        return _error_response(
            "Failed to load study bookmarks.",
            500,
            error=exc,
        )


# =========================================================
# SDA TODAY
# =========================================================

@study_bp.route(
    "/sda/today",
    methods=["GET"],
)
def sda_today():
    """
    Get today's SDA quarterly lesson using Kenya time.
    """

    try:

        target = (
            SDAQuarterlyService
            .today_date()
        )

        material = (
            SDAQuarterlyService
            .get_today(
                target
            )
        )

        if not material:

            return jsonify({
                "success": False,
                "message": (
                    "No SDA quarterly lesson "
                    "is available for today."
                ),
                "date":
                    target.isoformat(),
            }), 404

        return jsonify({
            "success": True,
            "date":
                target.isoformat(),
            "material":
                _serialize_value(
                    material
                ),
        }), 200

    except Exception as exc:

        return _error_response(
            "Failed to load today's SDA lesson.",
            500,
            error=exc,
        )


# =========================================================
# SDA CURRENT WEEK
# =========================================================

@study_bp.route(
    "/sda/week",
    methods=["GET"],
)
def sda_current_week():
    """
    Get the current Saturday-Friday SDA lesson week.
    """

    try:

        target = (
            SDAQuarterlyService
            .today_date()
        )

        materials = (
            SDAQuarterlyService
            .get_current_week(
                target
            )
        )

        if not isinstance(
            materials,
            list,
        ):

            materials = []

        safe_materials = [
            _serialize_value(
                material
            )
            for material in materials
        ]

        return jsonify({
            "success": True,
            "count": len(
                safe_materials
            ),
            "materials":
                safe_materials,
        }), 200

    except Exception as exc:

        return _error_response(
            "Failed to load the current SDA week.",
            500,
            error=exc,
        )


# =========================================================
# SDA BY DATE
# =========================================================

@study_bp.route(
    "/sda/date/<lesson_date>",
    methods=["GET"],
)
def sda_by_date(
    lesson_date,
):
    """
    Get an SDA lesson by date.

    Canonical format:

        YYYY-MM-DD
    """

    lesson_date = _clean_string(
        lesson_date
    )

    if not lesson_date:

        return _error_response(
            "lesson_date is required.",
            400,
        )

    parsed = (
        SDAQuarterlyService
        .parse_date(
            lesson_date
        )
    )

    if not parsed:

        return _error_response(
            "Date must use YYYY-MM-DD.",
            400,
        )

    try:

        material = (
            SDAQuarterlyService
            .get_by_date(
                parsed
            )
        )

        if not material:

            return _error_response(
                "Lesson not found.",
                404,
            )

        return jsonify({
            "success": True,
            "date":
                parsed.isoformat(),
            "material":
                _serialize_value(
                    material
                ),
        }), 200

    except Exception as exc:

        return _error_response(
            "Failed to load the SDA lesson.",
            500,
            error=exc,
        )


# =========================================================
# SDA QUARTER
# =========================================================

@study_bp.route(
    "/sda/quarter/<int:year>/<int:quarter>",
    methods=["GET"],
)
def sda_quarter(
    year,
    quarter,
):
    """
    Get all daily lessons in an SDA quarter.
    """

    if quarter not in (
        1,
        2,
        3,
        4,
    ):

        return _error_response(
            "Quarter must be between 1 and 4.",
            400,
        )

    if year < 1900 or year > 3000:

        return _error_response(
            "Invalid year.",
            400,
        )

    try:

        materials = (
            SDAQuarterlyService
            .get_quarter(
                year,
                quarter,
            )
        )

        if not isinstance(
            materials,
            list,
        ):

            materials = []

        page_requested = (
            request.args.get(
                "page"
            )
            is not None
        )

        limit_requested = (
            request.args.get(
                "limit"
            )
            is not None
        )

        page = _parse_int(
            request.args.get(
                "page"
            ),
            default=1,
            minimum=1,
        )

        limit = _parse_int(
            request.args.get(
                "limit"
            ),
            default=DEFAULT_LIMIT,
            minimum=1,
            maximum=MAX_LIMIT,
        )

        pagination = None

        if (
            page_requested
            or limit_requested
        ):

            response_materials, pagination = (
                _paginate(
                    materials,
                    page,
                    limit,
                )
            )

        else:

            response_materials = (
                materials
            )

        safe_materials = [
            _serialize_value(
                material
            )
            for material in response_materials
        ]

        response = {
            "success": True,
            "year": year,
            "quarter": quarter,
            "count": len(
                safe_materials
            ),
            "total": len(
                materials
            ),
            "materials":
                safe_materials,
        }

        if pagination is not None:

            response[
                "pagination"
            ] = pagination

        return jsonify(
            response
        ), 200

    except Exception as exc:

        return _error_response(
            "Failed to load SDA quarter.",
            500,
            error=exc,
        )


# =========================================================
# SDA IMPORT
# =========================================================
#
# Administrative operation.
#
# This endpoint is intentionally protected because importing
# an entire quarter can modify a large amount of Study data.
# =========================================================

@study_bp.route(
    "/sda/import",
    methods=["POST"],
)
@require_role("admin")
def import_sda_quarter():
    """
    Import a validated SDA quarter payload.

    Expected structure:

        {
            "year": 2026,
            "quarter": 3,
            "lessons": [...]
        }
    """

    data = _json_body()

    if not data:

        return _error_response(
            "Quarter payload is required.",
            400,
        )

    try:

        result = (
            SDAQuarterlyService
            .import_quarter(
                data
            )
        )

        status_code = (
            200
            if result.get(
                "success",
                False,
            )
            else 400
        )

        return jsonify(
            _serialize_value(
                result
            )
        ), status_code

    except ValueError as exc:

        return _error_response(
            str(exc),
            400,
        )

    except Exception as exc:

        return _error_response(
            "Failed to import SDA quarterly lessons.",
            500,
            error=exc,
        )

# REVELACODE_ELIMU_LEARNING_ROUTES_V1
# The course-learning API lives in the existing study blueprint and therefore
# uses the established database and authentication modules. This avoids a
# second, standalone Elimu blueprint and preserves the school's separate
# /api/jumuiya/elimu management surface.

_ELIMU_LEARNING_HUB_ID = "elimu-education"
_ELIMU_LEARNING_PROGRESS = "revelacode_elimu_learning_progress"
_ELIMU_LEARNING_CERTIFICATES = "revelacode_elimu_learning_certificates"


def _elimu_learning_now():
    return datetime.now(timezone.utc)


def _elimu_learning_text(value):
    return str(value or "").strip()


def _elimu_learning_slug(value):
    return re.sub(r"[^a-z0-9_-]+", "-", _elimu_learning_text(value).lower()).strip("-")[:100] or "general"


def _elimu_learning_materials():
    rows = list(
        get_db()["study_materials"]
        .find({"category": {"$in": ["education", "elimu"]}})
        .limit(2000)
    )
    result = []
    for row in rows:
        status = _elimu_learning_text(
            row.get("status") or row.get("publication_status") or "published"
        ).lower()
        if status not in {"published", "active", "available"}:
            continue
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        material_id = _elimu_learning_text(row.get("id") or row.get("_id"))
        title = _elimu_learning_text(row.get("title") or metadata.get("lesson_title"))
        if material_id and title:
            result.append((row, metadata, material_id, title))
    return result


def _elimu_learning_hub(user_id):
    materials = _elimu_learning_materials()
    if not materials:
        return None

    rows = list(
        get_db()[_ELIMU_LEARNING_PROGRESS].find({
            "user_id": user_id,
            "hub_id": _ELIMU_LEARNING_HUB_ID,
        })
    )
    completed_lessons = {
        str(item.get("lesson_id"))
        for item in rows
        if item.get("action") == "complete_lesson"
    }
    started = {
        str(item.get("course_id"))
        for item in rows
        if item.get("action") == "start"
    }
    completed_courses = {
        str(item.get("course_id"))
        for item in rows
        if item.get("action") == "complete_course"
    }

    groups = {}
    for row, metadata, material_id, title in materials:
        raw_key = (
            metadata.get("course_id")
            or metadata.get("course_title")
            or row.get("course_id")
            or row.get("course_title")
            or row.get("subcategory")
            or row.get("subject")
            or "General"
        )
        key = _elimu_learning_slug(raw_key)
        course = groups.setdefault(key, {
            "id": key,
            "course_id": key,
            "title": _elimu_learning_text(
                metadata.get("course_title")
                or row.get("course_title")
                or row.get("subcategory")
                or row.get("subject")
                or title
            ),
            "description": _elimu_learning_text(
                metadata.get("course_description") or row.get("course_description")
            ),
            "lessons": [],
        })
        course["lessons"].append({
            "id": material_id,
            "lesson_id": material_id,
            "title": title,
            "description": _elimu_learning_text(
                row.get("description") or metadata.get("description")
            ),
            "completed": material_id in completed_lessons,
        })

    courses = list(groups.values())
    for course in courses:
        course["lessons"].sort(key=lambda item: item["title"].casefold())
        course["status"] = (
            "completed"
            if course["id"] in completed_courses
            else (
                "in_progress"
                if course["id"] in started or any(item["completed"] for item in course["lessons"])
                else "not started"
            )
        )
    courses.sort(key=lambda item: item["title"].casefold())
    lessons = [lesson for course in courses for lesson in course["lessons"]]
    completed_count = sum(bool(item["completed"]) for item in lessons)
    completed_course_count = sum(course["status"] == "completed" for course in courses)
    return {
        "id": _ELIMU_LEARNING_HUB_ID,
        "name": "RevelaCode Education",
        "description": "Published education materials stored by RevelaCode.",
        "courses_count": len(courses),
        "courses": courses,
        "progress": {
            "completed_lessons": completed_count,
            "total_lessons": len(lessons),
            "completed_courses": completed_course_count,
            "total_courses": len(courses),
            "progress_percent": round(completed_count * 100 / len(lessons)) if lessons else 0,
            "hub_completed": bool(
                courses
                and lessons
                and completed_count == len(lessons)
                and completed_course_count == len(courses)
            ),
        },
    }


def _elimu_learning_key():
    secret = _elimu_learning_text(os.getenv("REVELACODE_CERTIFICATE_SIGNING_KEY"))
    if not secret:
        secret = _elimu_learning_text(os.getenv("JWT_SECRET"))
    if not secret:
        raise RuntimeError("Certificate signing secret is not configured")
    return hmac.new(
        secret.encode("utf-8"),
        b"revelacode-elimu-learning-certificate-v1",
        hashlib.sha256,
    ).digest()


def _elimu_learning_signature(claims):
    raw = json.dumps(
        claims,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hmac.new(_elimu_learning_key(), raw, hashlib.sha256).hexdigest()


def _elimu_learning_pdf(record):
    claims = record["claims"]
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=24 * mm,
        bottomMargin=22 * mm,
        title="RevelaCode Elimu Learning Certificate",
        author="RevelaCode",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="RevelaCodeElimuBrand",
        parent=styles["Title"],
        fontSize=25,
        textColor=colors.HexColor("#0A74DA"),
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="RevelaCodeElimuCertificate",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#2E8B57"),
        spaceAfter=16,
    ))
    story = [
        Paragraph("RevelaCode", styles["RevelaCodeElimuBrand"]),
        Paragraph("Elimu Learning Certificate", styles["RevelaCodeElimuCertificate"]),
    ]
    for label, value in [
        ("Issued to", claims.get("full_name")),
        ("Account ID", claims.get("user_id")),
        ("Learning hub", claims.get("hub_name")),
        ("Completed lessons", f'{claims.get("completed_lessons", 0)} / {claims.get("total_lessons", 0)}'),
        ("Roles recorded", ", ".join(claims.get("roles") or [])),
        ("Certificate ID", record.get("certificate_id")),
        ("Issued at (UTC)", claims.get("issued_at")),
        ("Verification URL", claims.get("verification_url")),
    ]:
        story.append(Paragraph(
            f"<b>{html_escape(str(label))}:</b> {html_escape(str(value or 'Not recorded'))}",
            styles["BodyText"],
        ))
        story.append(Spacer(1, 4 * mm))
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        "Issuer: RevelaCode. This certificate confirms only the learning completion recorded in RevelaCode; it is not a government qualification or external accreditation.",
        styles["Italic"],
    ))
    document.build(story)
    return output.getvalue()


def _elimu_learning_find_user(database, user_id):
    query_parts = [{"id": user_id}, {"user_id": user_id}]
    try:
        from bson import ObjectId
        if ObjectId.is_valid(user_id):
            query_parts.insert(0, {"_id": ObjectId(user_id)})
    except Exception:
        pass
    return database["users"].find_one({"$or": query_parts})


@study_bp.get("/elimu/hubs")
@require_authenticated
def elimu_learning_list_hubs():
    user_id = _elimu_learning_text(current_user_id())
    hub = _elimu_learning_hub(user_id)
    public_hubs = (
        [{key: hub[key] for key in ("id", "name", "description", "courses_count")}]
        if hub else []
    )
    return jsonify(success=True, hubs=public_hubs)


@study_bp.get("/elimu/hubs/<hub_id>")
@require_authenticated
def elimu_learning_get_hub(hub_id):
    if hub_id != _ELIMU_LEARNING_HUB_ID:
        return jsonify(success=False, error={
            "code": "hub_not_found",
            "message": "Learning hub not found.",
        }), 404
    hub = _elimu_learning_hub(_elimu_learning_text(current_user_id()))
    if not hub:
        return jsonify(success=False, error={
            "code": "learning_content_unavailable",
            "message": "No published education materials are available yet.",
        }), 404
    return jsonify(success=True, hub=hub)


@study_bp.get("/elimu/progress")
@require_authenticated
def elimu_learning_get_progress():
    requested_hub = _elimu_learning_text(request.args.get("hub_id")) or _ELIMU_LEARNING_HUB_ID
    if requested_hub != _ELIMU_LEARNING_HUB_ID:
        return jsonify(success=False, error={
            "code": "hub_not_found",
            "message": "Learning hub not found.",
        }), 404

    hub = _elimu_learning_hub(_elimu_learning_text(current_user_id()))
    if not hub:
        return jsonify(success=False, error={
            "code": "learning_content_unavailable",
            "message": "No published education materials are available yet.",
        }), 404
    return jsonify(success=True, hub_id=_ELIMU_LEARNING_HUB_ID, progress=hub["progress"], hub=hub), 200


@study_bp.post("/elimu/progress")
@require_authenticated
def elimu_learning_save_progress():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(success=False, error={
            "code": "invalid_json",
            "message": "A JSON object is required.",
        }), 400

    user_id = _elimu_learning_text(current_user_id())
    hub_id, course_id, action, lesson_id = map(
        _elimu_learning_text,
        (payload.get("hub_id"), payload.get("course_id"), payload.get("action"), payload.get("lesson_id")),
    )
    if (
        hub_id != _ELIMU_LEARNING_HUB_ID
        or action not in {"start", "complete_lesson", "complete_course"}
        or not course_id
    ):
        return jsonify(success=False, error={
            "code": "invalid_progress_request",
            "message": "Hub, course or action is invalid.",
        }), 422

    hub = _elimu_learning_hub(user_id)
    if not hub:
        return jsonify(success=False, error={
            "code": "learning_content_unavailable",
            "message": "No published education materials are available.",
        }), 409

    course = next((item for item in hub["courses"] if item["id"] == course_id), None)
    if not course:
        return jsonify(success=False, error={
            "code": "course_not_found",
            "message": "Course not found.",
        }), 404
    if action == "complete_lesson" and lesson_id not in {item["id"] for item in course["lessons"]}:
        return jsonify(success=False, error={
            "code": "lesson_not_found",
            "message": "Lesson does not belong to this course.",
        }), 404
    if action == "complete_course" and (
        not course["lessons"] or not all(item["completed"] for item in course["lessons"])
    ):
        return jsonify(success=False, error={
            "code": "course_incomplete",
            "message": "Complete every recorded lesson first.",
        }), 409

    now = _elimu_learning_now()
    query = {
        "user_id": user_id,
        "hub_id": _ELIMU_LEARNING_HUB_ID,
        "course_id": course_id,
        "action": action,
    }
    if action == "complete_lesson":
        query["lesson_id"] = lesson_id
    get_db()[_ELIMU_LEARNING_PROGRESS].update_one(
        query,
        {
            "$set": {
                "user_id": user_id,
                "hub_id": _ELIMU_LEARNING_HUB_ID,
                "course_id": course_id,
                "action": action,
                "lesson_id": lesson_id or None,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    updated = _elimu_learning_hub(user_id)
    return jsonify(success=True, progress=updated["progress"], hub=updated)


@study_bp.post("/elimu/certificates/generate")
@require_authenticated
def elimu_learning_generate_certificate():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or _elimu_learning_text(payload.get("hub_id")) != _ELIMU_LEARNING_HUB_ID:
        return jsonify(success=False, error={
            "code": "hub_not_found",
            "message": "Learning hub not found.",
        }), 404

    user_id = _elimu_learning_text(current_user_id())
    hub = _elimu_learning_hub(user_id)
    if not hub or not hub["progress"]["hub_completed"]:
        return jsonify(success=False, error={
            "code": "learning_incomplete",
            "message": "Complete all recorded courses and lessons before requesting a certificate.",
        }), 409

    database = get_db()
    certificates = database[_ELIMU_LEARNING_CERTIFICATES]
    existing = certificates.find_one({
        "user_id": user_id,
        "hub_id": _ELIMU_LEARNING_HUB_ID,
        "status": "active",
    })
    if existing:
        claims = existing.get("claims") or {}
        return jsonify(
            success=True,
            certificate_id=existing["certificate_id"],
            cert_id=existing["certificate_id"],
            already_issued=True,
            verification_url=claims.get("verification_url"),
            download_url=f"/api/study/elimu/certificates/{existing['certificate_id']}",
        )

    user = _elimu_learning_find_user(database, user_id)
    if not user:
        return jsonify(success=False, error={
            "code": "account_not_found",
            "message": "The authenticated account record could not be found.",
        }), 404
    raw_roles = user.get("roles") if isinstance(user.get("roles"), list) else []
    if user.get("role"):
        raw_roles = list(raw_roles) + [user["role"]]
    roles = list(dict.fromkeys(
        str(value).strip() for value in raw_roles if str(value).strip()
    )) or ["user"]

    certificate_id = "RC-EL-" + secrets.token_hex(8).upper()
    root = _elimu_learning_text(os.getenv("REVELACODE_PUBLIC_URL")) or "https://revelacode.co.ke"
    if not root.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        root = "https://revelacode.co.ke"
    claims = {
        "certificate_id": certificate_id,
        "user_id": user_id,
        "full_name": _elimu_learning_text(
            user.get("full_name") or user.get("fullName") or user.get("name") or user.get("username")
        ),
        "roles": roles,
        "hub_id": _ELIMU_LEARNING_HUB_ID,
        "hub_name": hub["name"],
        "completed_lessons": hub["progress"]["completed_lessons"],
        "total_lessons": hub["progress"]["total_lessons"],
        "issued_at": _elimu_learning_now().isoformat(),
        "issuer": "RevelaCode",
        "scope": "recorded_elimu_learning_completion",
        "verification_url": f"{root.rstrip('/')}/api/verify/certificate/{certificate_id}",
    }
    record = {
        "certificate_id": certificate_id,
        "user_id": user_id,
        "hub_id": _ELIMU_LEARNING_HUB_ID,
        "status": "active",
        "claims": claims,
        "signature": _elimu_learning_signature(claims),
        "signature_algorithm": "HMAC-SHA256",
        "created_at": _elimu_learning_now(),
    }
    certificates.insert_one(record)
    return jsonify(
        success=True,
        certificate_id=certificate_id,
        cert_id=certificate_id,
        already_issued=False,
        verification_url=claims["verification_url"],
        download_url=f"/api/study/elimu/certificates/{certificate_id}",
    ), 201


@study_bp.get("/elimu/certificates/<certificate_id>")
@require_authenticated
def elimu_learning_download_certificate(certificate_id):
    user_id = _elimu_learning_text(current_user_id())
    record = get_db()[_ELIMU_LEARNING_CERTIFICATES].find_one({
        "certificate_id": certificate_id,
        "user_id": user_id,
        "status": "active",
    })
    if not record:
        return jsonify(success=False, error={
            "code": "certificate_not_found",
            "message": "No active certificate belongs to this account.",
        }), 404
    if not hmac.compare_digest(
        str(record.get("signature") or ""),
        _elimu_learning_signature(record.get("claims") or {}),
    ):
        return jsonify(success=False, error={
            "code": "certificate_signature_invalid",
            "message": "Certificate integrity check failed.",
        }), 409
    response = send_file(
        io.BytesIO(_elimu_learning_pdf(record)),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{certificate_id}.pdf",
        max_age=0,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@study_bp.get("/elimu/certificates/verify/<certificate_id>")
def elimu_learning_verify_certificate(certificate_id):
    if not re.fullmatch(r"RC-EL-[A-F0-9]{16}", str(certificate_id or "")):
        return jsonify(valid=False, certificate_id=certificate_id, reason="certificate_not_found"), 404
    record = get_db()[_ELIMU_LEARNING_CERTIFICATES].find_one({"certificate_id": certificate_id})
    if not record:
        return jsonify(valid=False, certificate_id=certificate_id, reason="certificate_not_found"), 404
    if record.get("status") != "active":
        return jsonify(valid=False, certificate_id=certificate_id, reason="certificate_revoked"), 200
    claims = record.get("claims") or {}
    if not hmac.compare_digest(
        str(record.get("signature") or ""),
        _elimu_learning_signature(claims),
    ):
        return jsonify(valid=False, certificate_id=certificate_id, reason="signature_invalid"), 200
    return jsonify(
        valid=True,
        certified_by="RevelaCode",
        issuer_role="RevelaCode Certificate Issuer",
        certificate_id=certificate_id,
        user={"name": claims.get("full_name"), "roles": claims.get("roles") or []},
        hub={
            "name": claims.get("hub_name"),
            "completed_lessons": claims.get("completed_lessons"),
            "total_lessons": claims.get("total_lessons"),
        },
        roles=claims.get("roles") or [],
        issued_at=claims.get("issued_at"),
        verification_url=claims.get("verification_url"),
        signature_algorithm="HMAC-SHA256",
        certificate_scope="Recorded Elimu learning completion only; not a government qualification or external accreditation.",
    )


# =========================================================
# FAITH PREMIUM LEARNING, WORKSPACE, ASSESSMENTS & GROUPS
# =========================================================
# Reuses the current study collection, Mongo database, auth bridge,
# RevelaAI router, and shared Revenue Engine entitlement service.

import uuid as _faith_uuid
from pymongo import ASCENDING as _FAITH_ASCENDING, DESCENDING as _FAITH_DESCENDING
from pymongo.errors import DuplicateKeyError as _FaithDuplicateKeyError
from backend.revenue.subscriptions import (
    resolve_entitlement as _faith_resolve_entitlement,
    require_revenue_entitlement as _faith_require_entitlement,
)
from backend.study.faith_premium_curriculum import (
    COURSES as _FAITH_COURSES,
    get_course as _faith_get_course,
    get_lesson as _faith_get_lesson,
    public_course as _faith_public_course,
)

_FAITH_INDEXES_READY = False
_FAITH_PROGRESS = "jumuiya_faith_learning_progress"
_FAITH_NOTES = "jumuiya_faith_study_notes"
_FAITH_ASSESSMENTS = "jumuiya_faith_assessment_attempts"
_FAITH_GROUPS = "jumuiya_faith_study_groups"
_FAITH_GROUP_MEMBERS = "jumuiya_faith_study_group_members"
_FAITH_GROUP_ASSIGNMENTS = "jumuiya_faith_study_assignments"
_FAITH_ASSIGNMENT_PROGRESS = "jumuiya_faith_study_assignment_progress"


def _faith_now():
    return datetime.now(timezone.utc)


def _faith_db():
    return get_db()


def _faith_indexes():
    global _FAITH_INDEXES_READY
    if _FAITH_INDEXES_READY:
        return
    db = _faith_db()
    db[_FAITH_PROGRESS].create_index(
        [("user_id", _FAITH_ASCENDING), ("course_slug", _FAITH_ASCENDING), ("lesson_slug", _FAITH_ASCENDING)],
        unique=True, name="uq_faith_progress_user_course_lesson",
    )
    db[_FAITH_PROGRESS].create_index(
        [("user_id", _FAITH_ASCENDING), ("updated_at", _FAITH_DESCENDING)],
        name="ix_faith_progress_user_updated",
    )
    db[_FAITH_NOTES].create_index(
        [("user_id", _FAITH_ASCENDING), ("updated_at", _FAITH_DESCENDING)],
        name="ix_faith_notes_user_updated",
    )
    db[_FAITH_ASSESSMENTS].create_index(
        [("user_id", _FAITH_ASCENDING), ("created_at", _FAITH_DESCENDING)],
        name="ix_faith_assessments_user_created",
    )
    db[_FAITH_GROUPS].create_index(
        [("invite_code", _FAITH_ASCENDING)], unique=True, name="uq_faith_group_invite_code",
    )
    db[_FAITH_GROUP_MEMBERS].create_index(
        [("group_id", _FAITH_ASCENDING), ("user_id", _FAITH_ASCENDING)],
        unique=True, name="uq_faith_group_member",
    )
    db[_FAITH_GROUP_MEMBERS].create_index(
        [("user_id", _FAITH_ASCENDING), ("joined_at", _FAITH_DESCENDING)],
        name="ix_faith_group_member_user",
    )
    db[_FAITH_GROUP_ASSIGNMENTS].create_index(
        [("group_id", _FAITH_ASCENDING), ("created_at", _FAITH_DESCENDING)],
        name="ix_faith_group_assignment_group",
    )
    db[_FAITH_ASSIGNMENT_PROGRESS].create_index(
        [("assignment_id", _FAITH_ASCENDING), ("user_id", _FAITH_ASCENDING)],
        unique=True, name="uq_faith_assignment_progress_user",
    )
    _FAITH_INDEXES_READY = True


def _faith_clean(value, limit=500):
    return str(value or "").strip()[:limit]


def _faith_access(feature):
    try:
        user_id = current_user_id()
        entitlement = _faith_resolve_entitlement(user_id, "faith", feature)
        return user_id, entitlement, None
    except ValueError as exc:
        return None, None, _faith_error(str(exc), 400, "invalid_entitlement_request")
    except Exception as exc:
        logger.exception("Faith entitlement check failed: %s", exc)
        return None, None, _faith_error(
            "Faith access could not be verified right now. Please retry.",
            503, "faith_entitlement_unavailable",
        )


def _faith_error(message, status=400, code="invalid_request", extra=None):
    payload = {"success": False, "message": message, "code": code}
    if isinstance(extra, dict):
        payload.update(extra)
    return jsonify(payload), status


def _faith_locked(entitlement):
    return jsonify({
        "success": False,
        "code": "premium_entitlement_required",
        "message": "Start your one-time 30-day Faith trial or activate an eligible Faith plan to unlock this service.",
        "entitlement": entitlement,
    }), 402


def _faith_public_group(group, can_manage=False, member_count=0):
    output = {
        "id": str(group.get("group_id") or ""),
        "name": group.get("name") or "Faith Study Group",
        "organization": group.get("organization") or "",
        "description": group.get("description") or "",
        "owner_id": str(group.get("owner_id") or ""),
        "member_count": int(member_count),
        "created_at": _serialize_value(group.get("created_at")),
        "can_manage": bool(can_manage),
    }
    if can_manage:
        output["invite_code"] = group.get("invite_code") or ""
    return output


def _faith_member(group_id, user_id):
    _faith_indexes()
    return _faith_db()[_FAITH_GROUP_MEMBERS].find_one({
        "group_id": str(group_id), "user_id": str(user_id),
    })


def _faith_progress(user_id, course_slug, lesson_slug):
    _faith_indexes()
    return _faith_db()[_FAITH_PROGRESS].find_one({
        "user_id": str(user_id),
        "course_slug": course_slug,
        "lesson_slug": lesson_slug,
    })


@study_bp.get("/faith/courses")
@require_authenticated
def faith_list_learning_courses():
    user_id, entitlement, failure = _faith_access("faith_courses")
    if failure:
        return failure
    _faith_indexes()
    courses = []
    for course in _FAITH_COURSES:
        item = _faith_public_course(course, has_premium_access=bool(entitlement.get("allowed")), detail=False)
        item["completed_lessons"] = (
            _faith_db()[_FAITH_PROGRESS].count_documents({
                "user_id": user_id, "course_slug": course["slug"], "completed": True,
            }) if entitlement.get("allowed") else 0
        )
        courses.append(item)
    return jsonify({
        "success": True,
        "courses": courses,
        "entitlement": entitlement,
        "preview_note": "One lesson in Study Scripture with Context is free to preview. Full courses unlock during the Faith trial or through an eligible paid plan.",
    }), 200


@study_bp.get("/faith/courses/<course_slug>")
@require_authenticated
def faith_get_learning_course(course_slug):
    user_id, entitlement, failure = _faith_access("faith_courses")
    if failure:
        return failure
    course = _faith_get_course(course_slug)
    if not course:
        return _faith_error("Course not found.", 404, "course_not_found")
    payload = _faith_public_course(course, has_premium_access=bool(entitlement.get("allowed")), detail=True)
    for lesson in payload.get("lessons", []):
        row = _faith_progress(user_id, course["slug"], lesson["slug"])
        lesson["completed"] = bool(row and row.get("completed"))
        lesson["last_accessed_at"] = _serialize_value(row.get("updated_at")) if row else None
    payload["entitlement"] = entitlement
    return jsonify({"success": True, "course": payload}), 200


@study_bp.post("/faith/progress")
@require_authenticated
def faith_save_learning_progress():
    data = _json_body()
    course_slug = _faith_clean(data.get("course_slug"), 100).lower()
    lesson_slug = _faith_clean(data.get("lesson_slug"), 100).lower()
    completed = data.get("completed", True)
    if not isinstance(completed, bool):
        return _faith_error("'completed' must be a boolean.", 400, "invalid_progress")
    course, lesson = _faith_get_lesson(course_slug, lesson_slug)
    if not course or not lesson:
        return _faith_error("Course or lesson not found.", 404, "lesson_not_found")
    user_id, entitlement, failure = _faith_access("faith_courses")
    if failure:
        return failure
    if not entitlement.get("allowed") and not lesson.get("preview"):
        return _faith_locked(entitlement)

    _faith_indexes()
    now = _faith_now()
    try:
        last_position = max(0, min(int(data.get("last_position") or 0), 5_000_000))
    except (TypeError, ValueError):
        last_position = 0
    _faith_db()[_FAITH_PROGRESS].update_one(
        {"user_id": user_id, "course_slug": course_slug, "lesson_slug": lesson_slug},
        {"$set": {
            "completed": completed, "last_position": last_position,
            "updated_at": now, "completed_at": now if completed else None,
        }, "$setOnInsert": {
            "user_id": user_id, "course_slug": course_slug,
            "lesson_slug": lesson_slug, "created_at": now,
        }},
        upsert=True,
    )
    row = _faith_progress(user_id, course_slug, lesson_slug)
    return jsonify({"success": True, "progress": {
        "course_slug": course_slug, "lesson_slug": lesson_slug,
        "completed": bool(row.get("completed")),
        "last_position": int(row.get("last_position") or 0),
        "updated_at": _serialize_value(row.get("updated_at")),
    }}), 200


@study_bp.get("/faith/workspace")
@require_authenticated
@_faith_require_entitlement("faith", "faith_workspace")
def faith_get_personal_workspace():
    user_id = current_user_id()
    _faith_indexes()
    db = _faith_db()
    progress = list(db[_FAITH_PROGRESS].find({"user_id": user_id}).sort("updated_at", _FAITH_DESCENDING).limit(100))
    notes = list(db[_FAITH_NOTES].find({"user_id": user_id}).sort("updated_at", _FAITH_DESCENDING).limit(100))
    attempts = list(db[_FAITH_ASSESSMENTS].find({"user_id": user_id}).sort("created_at", _FAITH_DESCENDING).limit(20))
    public_notes = [{
        "id": str(row.get("note_id") or ""),
        "title": row.get("title") or "Study note",
        "content": row.get("content") or "",
        "course_slug": row.get("course_slug") or "",
        "lesson_slug": row.get("lesson_slug") or "",
        "material_id": row.get("material_id") or "",
        "created_at": _serialize_value(row.get("created_at")),
        "updated_at": _serialize_value(row.get("updated_at")),
    } for row in notes]
    public_progress = [{
        "course_slug": row.get("course_slug"),
        "lesson_slug": row.get("lesson_slug"),
        "completed": bool(row.get("completed")),
        "last_position": int(row.get("last_position") or 0),
        "updated_at": _serialize_value(row.get("updated_at")),
    } for row in progress]
    public_attempts = [{
        "id": str(row.get("attempt_id") or ""),
        "course_slug": row.get("course_slug"),
        "lesson_slug": row.get("lesson_slug"),
        "score_percent": int(row.get("score_percent") or 0),
        "passed": bool(row.get("passed")),
        "created_at": _serialize_value(row.get("created_at")),
    } for row in attempts]
    return jsonify({
        "success": True,
        "notes": public_notes,
        "progress": public_progress,
        "assessments": public_attempts,
        "summary": {
            "completed_lessons": sum(1 for row in public_progress if row["completed"]),
            "notes_count": len(public_notes),
            "assessment_attempts": len(public_attempts),
        },
    }), 200


@study_bp.post("/faith/notes")
@require_authenticated
@_faith_require_entitlement("faith", "faith_workspace")
def faith_save_note():
    data = _json_body()
    title = _faith_clean(data.get("title") or "Study note", 160)
    content = _faith_clean(data.get("content"), 8000)
    course_slug = _faith_clean(data.get("course_slug"), 100).lower()
    lesson_slug = _faith_clean(data.get("lesson_slug"), 100).lower()
    material_id = _faith_clean(data.get("material_id"), 128)
    if not content:
        return _faith_error("Write some note content before saving.", 400, "empty_note")
    if course_slug or lesson_slug:
        course, lesson = _faith_get_lesson(course_slug, lesson_slug)
        if not course or not lesson:
            return _faith_error("The linked course lesson does not exist.", 404, "lesson_not_found")
    if material_id:
        material = StudyService.get_material_by_id(material_id)
        if not material or str(material.get("category") or "").lower() != "faith":
            return _faith_error("The linked Faith study material was not found.", 404, "faith_material_not_found")
    user_id = current_user_id()
    _faith_indexes()
    now = _faith_now()
    note_id = _faith_clean(data.get("note_id"), 64) or _faith_uuid.uuid4().hex
    query = {"user_id": user_id, "note_id": note_id}
    rows = _faith_db()[_FAITH_NOTES]
    existing = rows.find_one(query)
    if existing:
        rows.update_one(query, {"$set": {
            "title": title, "content": content, "course_slug": course_slug,
            "lesson_slug": lesson_slug, "material_id": material_id, "updated_at": now,
        }})
    else:
        rows.insert_one({
            "note_id": note_id, "user_id": user_id, "title": title, "content": content,
            "course_slug": course_slug, "lesson_slug": lesson_slug, "material_id": material_id,
            "created_at": now, "updated_at": now,
        })
    return jsonify({"success": True, "note": {
        "id": note_id, "title": title, "content": content,
        "course_slug": course_slug, "lesson_slug": lesson_slug,
        "material_id": material_id, "updated_at": _serialize_value(now),
    }}), 200


@study_bp.delete("/faith/notes/<note_id>")
@require_authenticated
@_faith_require_entitlement("faith", "faith_workspace")
def faith_delete_note(note_id):
    user_id = current_user_id()
    _faith_indexes()
    result = _faith_db()[_FAITH_NOTES].delete_one({
        "user_id": user_id, "note_id": _faith_clean(note_id, 64),
    })
    if result.deleted_count < 1:
        return _faith_error("Study note not found.", 404, "note_not_found")
    return jsonify({"success": True, "deleted": True}), 200


@study_bp.post("/faith/assessments/submit")
@require_authenticated
def faith_submit_assessment():
    data = _json_body()
    course_slug = _faith_clean(data.get("course_slug"), 100).lower()
    lesson_slug = _faith_clean(data.get("lesson_slug"), 100).lower()
    answers = data.get("answers")
    if not isinstance(answers, dict):
        return _faith_error("Assessment answers must be an object.", 400, "invalid_answers")
    course, lesson = _faith_get_lesson(course_slug, lesson_slug)
    if not course or not lesson:
        return _faith_error("Course or lesson not found.", 404, "lesson_not_found")
    user_id, entitlement, failure = _faith_access("faith_courses")
    if failure:
        return failure
    if not entitlement.get("allowed") and not lesson.get("preview"):
        return _faith_locked(entitlement)
    quiz = lesson.get("quiz") or []
    if not quiz:
        return _faith_error("This lesson has no assessment configured.", 409, "assessment_unavailable")
    graded = []
    correct_count = 0
    for index, item in enumerate(quiz):
        raw_answer = answers.get(str(index), answers.get(index))
        try:
            selected = int(raw_answer)
        except (TypeError, ValueError):
            selected = -1
        is_correct = selected == int(item["answer_index"])
        if is_correct:
            correct_count += 1
        graded.append({
            "question": item["question"],
            "selected_index": selected if 0 <= selected < len(item["options"]) else None,
            "correct_index": int(item["answer_index"]),
            "correct": is_correct,
            "explanation": item.get("explanation") or "",
        })
    score = round(correct_count * 100 / len(quiz))
    passed = score >= 70
    attempt_id = _faith_uuid.uuid4().hex
    now = _faith_now()
    _faith_indexes()
    _faith_db()[_FAITH_ASSESSMENTS].insert_one({
        "attempt_id": attempt_id, "user_id": user_id,
        "course_slug": course_slug, "lesson_slug": lesson_slug,
        "answers": answers, "score_percent": score,
        "correct_count": correct_count, "question_count": len(quiz),
        "passed": passed, "created_at": now,
    })
    return jsonify({
        "success": True, "attempt_id": attempt_id, "score_percent": score,
        "correct_count": correct_count, "question_count": len(quiz), "passed": passed,
        "feedback": graded,
        "message": "Assessment passed." if passed else "Review the explanations and try again. A score of 70% is required to pass.",
    }), 200


@study_bp.post("/faith/companion")
@require_authenticated
@_faith_require_entitlement("faith", "faith_companion")
def faith_study_companion():
    data = _json_body()
    course_slug = _faith_clean(data.get("course_slug"), 100).lower()
    lesson_slug = _faith_clean(data.get("lesson_slug"), 100).lower()
    question = _faith_clean(data.get("question"), 4000)
    discussion_mode = _faith_clean(data.get("discussion_mode"), 30).lower() or "interpret"
    if discussion_mode not in {"interpret", "debate"}:
        return _faith_error(
            "discussion_mode must be 'interpret' or 'debate'.",
            400,
            "invalid_discussion_mode",
        )
    if not question:
        return _faith_error("Enter a question for the Faith Study Companion.", 400, "empty_question")
    course, lesson = _faith_get_lesson(course_slug, lesson_slug)
    if not course or not lesson:
        return _faith_error("Course or lesson not found.", 404, "lesson_not_found")

    shared_instructions = (
        "You are RevelaCode's Faith Study Companion. Use the supplied lesson and source lists as context, "
        "but do not assume the lesson settles every question. Distinguish primary-text wording, official denominational teaching, "
        "scholarly interpretation, personal application, historical fact, and inference. Never invent quotations, sources, or official positions. "
        "When you state a religious tradition's position, identify the tradition and ground the description in the provided sources; "
        "if the sources do not support a claim, say so and ask for or recommend a relevant primary source. "
        "Represent traditions as their informed adherents would recognize them, while noting internal diversity where it materially matters. "
        "Do not use slurs, dehumanize believers, label an entire religion or its members evil, or claim that any religion's adherents are more powerful, valuable, intelligent, or worthy than another's. "
        "Do not use fear to pressure religious decisions, assign apocalyptic labels to living people without evidence, or make sensational prophecy predictions or date-set Christ's return. "
        "Avoid forced equivalence: clearly name real doctrinal disagreements instead of pretending all traditions say the same thing. "
    )
    if discussion_mode == "debate":
        mode_instructions = (
            "DISCUSSION MODE: BALANCED DEBATE. Structure the answer with these headings: "
            "1) Question and scope; 2) Primary evidence and context; 3) Perspective A stated in its strongest fair form; "
            "4) Perspective B stated in its strongest fair form; 5) Best objections and replies from both sides; "
            "6) What is agreed, what genuinely conflicts, and what remains unresolved; 7) Sources and follow-up questions. "
            "Give each relevant perspective comparable analytical depth and apply the same evidential standards. "
            "For Adventist doctrine, explain the official Adventist reading and compare a credible alternative where relevant. "
            "For Catholic-Muslim questions, give Catholic and Muslim perspectives equal space, use sources from each tradition, "
            "and do not frame one as the default judge of the other. Do not announce a winner or rank the traditions' truth, power, or human worth. "
            "You may assess whether a specific argument follows from its stated premises and cited evidence; explain that assessment without treating it as a verdict on an entire religion. "
        )
    else:
        mode_instructions = (
            "DISCUSSION MODE: INTERPRETATION. Explain the question in context, state the lesson's main reading, "
            "identify relevant alternatives and the evidence each uses, and separate what the source explicitly says from inference. "
            "When the question crosses traditions, give each relevant perspective a fair, clearly labelled account and identify unresolved questions. "
        )
    prompt = (
        shared_instructions
        + mode_instructions
        + "\nCourse: " + course["title"]
        + "\nLesson: " + lesson["title"]
        + "\nLesson reference: " + str(lesson.get("reference") or "")
        + "\nUser question:\n" + question
    )
    context = {
        "title": course["title"] + " — " + lesson["title"],
        "category": "faith",
        "subcategory": course["slug"],
        "material_type": "structured_faith_lesson",
        "reference": lesson.get("reference") or "",
        "content": lesson.get("content") or "",
        "sources": lesson.get("sources") or [],
        "curriculum_sources": course.get("sources") or [],
        "discussion_mode": discussion_mode,
        "principles": {
            "fair_representation": True,
            "balanced_analytical_depth": True,
            "no_religious_superiority_or_human_worth_ranking": True,
            "sources_required_for_attributions": True,
            "acknowledge_real_disagreements": True,
        },
    }
    try:
        from backend.services.ai_router import ask_ai
        response = ask_ai(prompt=prompt, domain="study", context=context)
        answer = _extract_ai_answer(response)
        if not answer:
            return _faith_error("RevelaAI did not return a usable answer. Please retry.", 503, "study_ai_unavailable")
        return jsonify({
            "success": True, "course_slug": course_slug, "lesson_slug": lesson_slug,
            "discussion_mode": discussion_mode,
            "answer": answer, "sources": lesson.get("sources") or [],
            "ai_available": not bool(response.get("fallback")) if isinstance(response, dict) else True,
        }), 200
    except Exception as exc:
        logger.exception("Faith Study Companion request failed: %s", exc)
        return _faith_error("The Study Companion is temporarily unavailable. Your lesson and notes remain available.", 503, "study_ai_unavailable")


@study_bp.get("/faith/groups")
@require_authenticated
@_faith_require_entitlement("faith", "faith_group_tools")
def faith_list_groups():
    user_id = current_user_id()
    _faith_indexes()
    db = _faith_db()
    memberships = list(db[_FAITH_GROUP_MEMBERS].find({"user_id": user_id}).sort("joined_at", _FAITH_DESCENDING).limit(100))
    groups = []
    for membership in memberships:
        group = db[_FAITH_GROUPS].find_one({"group_id": membership.get("group_id")})
        if not group:
            continue
        count = db[_FAITH_GROUP_MEMBERS].count_documents({"group_id": group["group_id"]})
        owner = str(group.get("owner_id")) == user_id
        item = _faith_public_group(group, can_manage=owner, member_count=count)
        item["my_role"] = membership.get("role") or "member"
        groups.append(item)
    return jsonify({"success": True, "groups": groups}), 200


@study_bp.post("/faith/groups")
@require_authenticated
@_faith_require_entitlement("faith", "faith_group_tools")
def faith_create_group():
    data = _json_body()
    name = _faith_clean(data.get("name"), 120)
    organization = _faith_clean(data.get("organization"), 120)
    description = _faith_clean(data.get("description"), 500)
    if len(name) < 3:
        return _faith_error("Group name must contain at least 3 characters.", 400, "invalid_group_name")
    user_id = current_user_id()
    _faith_indexes()
    db = _faith_db()
    if db[_FAITH_GROUPS].count_documents({"owner_id": user_id}) >= 20:
        return _faith_error("This account has reached the group creation limit.", 409, "group_limit_reached")
    now = _faith_now()
    group_id = _faith_uuid.uuid4().hex
    group = None
    for _ in range(5):
        code = secrets.token_urlsafe(7).replace("-", "").replace("_", "").upper()[:10]
        candidate = {
            "group_id": group_id, "name": name, "organization": organization,
            "description": description, "owner_id": user_id, "invite_code": code,
            "created_at": now, "updated_at": now,
        }
        try:
            db[_FAITH_GROUPS].insert_one(candidate)
            group = candidate
            break
        except _FaithDuplicateKeyError:
            continue
    if not group:
        return _faith_error("A secure invite code could not be generated. Please retry.", 503, "invite_code_generation_failed")
    try:
        db[_FAITH_GROUP_MEMBERS].insert_one({
            "group_id": group_id, "user_id": user_id, "role": "owner", "joined_at": now,
        })
    except Exception:
        logger.exception("Faith group created but owner membership insert failed; attempting repair.")
        db[_FAITH_GROUP_MEMBERS].update_one(
            {"group_id": group_id, "user_id": user_id},
            {"$setOnInsert": {"role": "owner", "joined_at": now}}, upsert=True,
        )
    return jsonify({
        "success": True,
        "group": _faith_public_group(group, can_manage=True, member_count=1),
        "message": "Group created. Share its invite code with your church or study group.",
    }), 201


@study_bp.post("/faith/groups/join")
@require_authenticated
@_faith_require_entitlement("faith", "faith_group_tools")
def faith_join_group():
    invite_code = _faith_clean(_json_body().get("invite_code"), 32).upper()
    if not invite_code:
        return _faith_error("Enter a group invite code.", 400, "invite_code_required")
    user_id = current_user_id()
    _faith_indexes()
    db = _faith_db()
    group = db[_FAITH_GROUPS].find_one({"invite_code": invite_code})
    if not group:
        return _faith_error("That invite code was not found. Check it with the group leader.", 404, "invalid_invite_code")
    existing = db[_FAITH_GROUP_MEMBERS].find_one({"group_id": group["group_id"], "user_id": user_id})
    if not existing:
        try:
            db[_FAITH_GROUP_MEMBERS].insert_one({
                "group_id": group["group_id"], "user_id": user_id,
                "role": "member", "joined_at": _faith_now(),
            })
        except _FaithDuplicateKeyError:
            pass
    count = db[_FAITH_GROUP_MEMBERS].count_documents({"group_id": group["group_id"]})
    owner = str(group.get("owner_id")) == user_id
    return jsonify({
        "success": True,
        "group": _faith_public_group(group, can_manage=owner, member_count=count),
        "message": "You are a member of this study group.",
    }), 200


@study_bp.get("/faith/groups/<group_id>")
@require_authenticated
@_faith_require_entitlement("faith", "faith_group_tools")
def faith_get_group(group_id):
    user_id = current_user_id()
    group_id = _faith_clean(group_id, 64)
    _faith_indexes()
    db = _faith_db()
    group = db[_FAITH_GROUPS].find_one({"group_id": group_id})
    if not group:
        return _faith_error("Study group not found.", 404, "group_not_found")
    membership = _faith_member(group_id, user_id)
    if not membership:
        return _faith_error("Join this study group before viewing assignments.", 403, "group_membership_required")
    members = list(db[_FAITH_GROUP_MEMBERS].find({"group_id": group_id}).sort("joined_at", _FAITH_ASCENDING).limit(250))
    assignments = list(db[_FAITH_GROUP_ASSIGNMENTS].find({"group_id": group_id}).sort("created_at", _FAITH_DESCENDING).limit(100))
    public_assignments = []
    for assignment in assignments:
        mine = db[_FAITH_ASSIGNMENT_PROGRESS].find_one({
            "assignment_id": assignment["assignment_id"], "user_id": user_id, "completed": True,
        })
        public_assignments.append({
            "id": assignment.get("assignment_id"), "title": assignment.get("title") or "Study assignment",
            "course_slug": assignment.get("course_slug"), "lesson_slug": assignment.get("lesson_slug"),
            "due_date": assignment.get("due_date") or "", "created_at": _serialize_value(assignment.get("created_at")),
            "created_by": assignment.get("created_by"), "my_completed": bool(mine),
            "completed_count": db[_FAITH_ASSIGNMENT_PROGRESS].count_documents({
                "assignment_id": assignment["assignment_id"], "completed": True,
            }),
        })
    count = db[_FAITH_GROUP_MEMBERS].count_documents({"group_id": group_id})
    owner = str(group.get("owner_id")) == user_id
    output = _faith_public_group(group, can_manage=owner, member_count=count)
    output["my_role"] = membership.get("role") or "member"
    output["members"] = [{
        "user_id": row.get("user_id"), "role": row.get("role") or "member",
        "joined_at": _serialize_value(row.get("joined_at")),
    } for row in members]
    output["assignments"] = public_assignments
    return jsonify({"success": True, "group": output}), 200


@study_bp.post("/faith/groups/<group_id>/assignments")
@require_authenticated
@_faith_require_entitlement("faith", "faith_group_tools")
def faith_create_group_assignment(group_id):
    data = _json_body()
    title = _faith_clean(data.get("title") or "Group study assignment", 140)
    course_slug = _faith_clean(data.get("course_slug"), 100).lower()
    lesson_slug = _faith_clean(data.get("lesson_slug"), 100).lower()
    due_date = _faith_clean(data.get("due_date"), 10)
    course, lesson = _faith_get_lesson(course_slug, lesson_slug)
    if not course or not lesson:
        return _faith_error("Select a valid curriculum course and lesson.", 404, "lesson_not_found")
    if due_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_date):
        return _faith_error("Due date must use YYYY-MM-DD.", 400, "invalid_due_date")
    user_id = current_user_id()
    _faith_indexes()
    db = _faith_db()
    group = db[_FAITH_GROUPS].find_one({"group_id": _faith_clean(group_id, 64)})
    if not group:
        return _faith_error("Study group not found.", 404, "group_not_found")
    if not _faith_member(group["group_id"], user_id):
        return _faith_error("You are not a member of this study group.", 403, "group_membership_required")
    if str(group.get("owner_id")) != user_id:
        return _faith_error("Only the group leader can create assignments.", 403, "group_leader_required")
    now = _faith_now()
    assignment_id = _faith_uuid.uuid4().hex
    db[_FAITH_GROUP_ASSIGNMENTS].insert_one({
        "assignment_id": assignment_id, "group_id": group["group_id"], "title": title,
        "course_slug": course_slug, "lesson_slug": lesson_slug, "due_date": due_date,
        "created_by": user_id, "created_at": now, "updated_at": now,
    })
    return jsonify({"success": True, "assignment": {
        "id": assignment_id, "title": title, "course_slug": course_slug,
        "lesson_slug": lesson_slug, "due_date": due_date, "created_at": _serialize_value(now),
    }}), 201


@study_bp.post("/faith/groups/<group_id>/assignments/<assignment_id>/complete")
@require_authenticated
@_faith_require_entitlement("faith", "faith_group_tools")
def faith_complete_group_assignment(group_id, assignment_id):
    user_id = current_user_id()
    group_id = _faith_clean(group_id, 64)
    assignment_id = _faith_clean(assignment_id, 64)
    _faith_indexes()
    db = _faith_db()
    if not _faith_member(group_id, user_id):
        return _faith_error("You are not a member of this study group.", 403, "group_membership_required")
    assignment = db[_FAITH_GROUP_ASSIGNMENTS].find_one({"group_id": group_id, "assignment_id": assignment_id})
    if not assignment:
        return _faith_error("Assignment not found.", 404, "assignment_not_found")
    now = _faith_now()
    db[_FAITH_ASSIGNMENT_PROGRESS].update_one(
        {"assignment_id": assignment_id, "user_id": user_id},
        {"$set": {"completed": True, "completed_at": now, "updated_at": now},
         "$setOnInsert": {"group_id": group_id, "created_at": now}},
        upsert=True,
    )
    return jsonify({"success": True, "completed": True, "completed_at": _serialize_value(now)}), 200

