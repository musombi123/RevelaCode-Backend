# backend/routes/study_routes.py

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from backend.db import get_db
from backend.utils.decorators import require_role

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