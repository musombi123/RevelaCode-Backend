# backend/routes/study_routes.py

from flask import Blueprint, request, jsonify

from backend.db import get_db

from backend.study.study_service import StudyService
from backend.study.lesson_processor import LessonProcessor
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


# =========================================================
# BLUEPRINT
# =========================================================

study_bp = Blueprint(
    "study",
    __name__,
    url_prefix="/study",
)


# =========================================================
# MATERIALS
# =========================================================

@study_bp.route(
    "/materials",
    methods=["GET"],
)
def get_materials():

    category = request.args.get(
        "category"
    )

    materials = StudyService.get_materials(
        category
    )

    return jsonify({
        "success": True,
        "count": len(materials),
        "materials": materials,
    }), 200


# =========================================================
# PREFERENCES
# =========================================================

@study_bp.route(
    "/preferences",
    methods=["POST"],
)
def save_preferences():

    data = request.get_json(
        silent=True
    ) or {}

    user_id = data.get(
        "user_id"
    )

    preferences = data.get(
        "preferences",
        [],
    )

    if not user_id:
        return jsonify({
            "success": False,
            "message": "user_id is required.",
        }), 400

    if not isinstance(
        preferences,
        list,
    ):
        return jsonify({
            "success": False,
            "message": "preferences must be a list.",
        }), 400

    result = (
        MaterialPreferences
        .save_preferences(
            user_id,
            preferences,
        )
    )

    return jsonify(
        result
    ), 200


# =========================================================
# RECOMMENDED MATERIALS
# =========================================================

@study_bp.route(
    "/recommend/<user_id>",
    methods=["GET"],
)
def recommended_materials(
    user_id,
):

    materials = (
        MaterialPreferences
        .get_recommended_materials(
            user_id
        )
    )

    return jsonify({
        "success": True,
        "count": len(materials),
        "materials": materials,
    }), 200


# =========================================================
# UPLOAD / CREATE MATERIAL
# =========================================================

@study_bp.route(
    "/upload",
    methods=["POST"],
)
def upload_material():

    # -----------------------------------------------------
    # FILE UPLOAD
    # -----------------------------------------------------

    if "file" in request.files:

        file = request.files["file"]

        if not file.filename:
            return jsonify({
                "success": False,
                "message": "No file selected.",
            }), 400

        extracted = (
            LessonProcessor
            .process_uploaded_file(
                file
            )
        )

        return jsonify(
            extracted
        ), 200

    # -----------------------------------------------------
    # TEXT MATERIAL
    # -----------------------------------------------------

    data = request.get_json(
        silent=True
    ) or {}

    title = data.get(
        "title"
    )

    content = data.get(
        "content"
    )

    if not title:
        return jsonify({
            "success": False,
            "message": "title is required.",
        }), 400

    if not content:
        return jsonify({
            "success": False,
            "message": "content is required.",
        }), 400

    tags = data.get(
        "tags",
        [],
    )

    if not isinstance(
        tags,
        list,
    ):
        tags = []

    result = (
        LessonProcessor
        .process_text_material(
            title=title,
            category=data.get(
                "category"
            ),
            subcategory=data.get(
                "subcategory"
            ),
            content=content,
            year=data.get(
                "year"
            ),
            tags=tags,
        )
    )

    return jsonify(
        result
    ), 200


# =========================================================
# SEARCH
# =========================================================

@study_bp.route(
    "/search",
    methods=["GET"],
)
def search_materials():

    query = request.args.get(
        "q",
        "",
    ).strip()

    if not query:
        return jsonify({
            "success": True,
            "count": 0,
            "results": [],
        }), 200

    results = StudyService.search_materials(
        query
    )

    return jsonify({
        "success": True,
        "count": len(results),
        "results": results,
    }), 200


# =========================================================
# ROOTWORD SEARCH
# =========================================================

@study_bp.route(
    "/rootword",
    methods=["GET"],
)
def search_rootword():

    word = request.args.get(
        "word",
        "",
    ).strip()

    if not word:
        return jsonify({
            "success": False,
            "message": "word is required.",
        }), 400

    result = RootWordService.search(
        word
    )

    return jsonify(
        result
    ), 200


# =========================================================
# ADD ROOTWORD
# =========================================================

@study_bp.route(
    "/rootword",
    methods=["POST"],
)
def add_rootword():

    data = request.get_json(
        silent=True
    ) or {}

    if not data.get("word"):
        return jsonify({
            "success": False,
            "message": "word is required.",
        }), 400

    result = (
        RootWordService
        .add_rootword(
            word=data.get(
                "word"
            ),
            language=data.get(
                "language"
            ),
            strong_number=data.get(
                "strong_number"
            ),
            transliteration=data.get(
                "transliteration"
            ),
            meaning=data.get(
                "meaning"
            ),
            scriptures=data.get(
                "scriptures",
                [],
            ),
            notes=data.get(
                "notes",
                [],
            ),
        )
    )

    return jsonify(
        result
    ), 200


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

    material = StudyService.get_material_by_id(
        material_id
    )

    if not material:
        return jsonify({
            "success": False,
            "message": "Material not found.",
        }), 404

    return jsonify({
        "success": True,
        "material": material,
    }), 200


# =========================================================
# BOOKMARK
# =========================================================

@study_bp.route(
    "/bookmark",
    methods=["POST"],
)
def save_bookmark():

    data = request.get_json(
        silent=True
    ) or {}

    user_id = data.get(
        "user_id"
    )

    material_id = data.get(
        "material_id"
    )

    if not user_id:
        return jsonify({
            "success": False,
            "message": "user_id is required.",
        }), 400

    if not material_id:
        return jsonify({
            "success": False,
            "message": "material_id is required.",
        }), 400

    result = (
        BookmarkService
        .add_bookmark(
            user_id,
            str(material_id),
        )
    )

    return jsonify(
        result
    ), 200


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

    db = get_db()

    bookmarks = list(
        db["study_bookmarks"].find({
            "user_id": user_id,
        })
    )

    materials = []

    for bookmark in bookmarks:

        material_id = bookmark.get(
            "material_id"
        )

        if not material_id:
            continue

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

    return jsonify({
        "success": True,
        "count": len(materials),
        "bookmarks": materials,
    }), 200


# =========================================================
# SDA QUARTERLY
# =========================================================

@study_bp.route(
    "/sda/today",
    methods=["GET"],
)
def sda_today():

    material = (
        SDAQuarterlyService
        .get_today()
    )

    if not material:
        return jsonify({
            "success": False,
            "message": (
                "No SDA quarterly lesson "
                "is available for today."
            ),
        }), 404

    return jsonify({
        "success": True,
        "material": material,
    }), 200


# =========================================================
# SDA CURRENT WEEK
# =========================================================

@study_bp.route(
    "/sda/week",
    methods=["GET"],
)
def sda_current_week():

    materials = (
        SDAQuarterlyService
        .get_current_week()
    )

    return jsonify({
        "success": True,
        "count": len(materials),
        "materials": materials,
    }), 200


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

    parsed = (
        SDAQuarterlyService
        .parse_date(
            lesson_date
        )
    )

    if not parsed:
        return jsonify({
            "success": False,
            "message": (
                "Date must use YYYY-MM-DD."
            ),
        }), 400

    material = (
        SDAQuarterlyService
        .get_by_date(
            parsed
        )
    )

    if not material:
        return jsonify({
            "success": False,
            "message": "Lesson not found.",
        }), 404

    return jsonify({
        "success": True,
        "material": material,
    }), 200


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

    if quarter not in (
        1,
        2,
        3,
        4,
    ):
        return jsonify({
            "success": False,
            "message": (
                "Quarter must be between 1 and 4."
            ),
        }), 400

    materials = (
        SDAQuarterlyService
        .get_quarter(
            year,
            quarter,
        )
    )

    return jsonify({
        "success": True,
        "year": year,
        "quarter": quarter,
        "count": len(materials),
        "materials": materials,
    }), 200


# =========================================================
# SDA IMPORT
# =========================================================

@study_bp.route(
    "/sda/import",
    methods=["POST"],
)
def import_sda_quarter():

    data = request.get_json(
        silent=True
    ) or {}

    if not data:
        return jsonify({
            "success": False,
            "message": (
                "Quarter payload is required."
            ),
        }), 400

    try:
        result = (
            SDAQuarterlyService
            .import_quarter(
                data
            )
        )

        return jsonify(
            result
        ), 200

    except ValueError as exc:

        return jsonify({
            "success": False,
            "message": str(exc),
        }), 400

    except Exception as exc:

        print(
            "❌ SDA import failed:",
            exc,
        )

        return jsonify({
            "success": False,
            "message": (
                "Failed to import SDA quarterly lessons."
            ),
            "error": str(exc),
        }), 500
