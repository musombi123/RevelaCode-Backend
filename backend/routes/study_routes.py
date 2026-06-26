# backend/routes/study_routes.py

from flask import Blueprint
from flask import request
from flask import jsonify

from backend.study.study_service import StudyService
from backend.study.lesson_processor import LessonProcessor
from backend.study.ai_context_service import (
AIContextService
)

from backend.study.bookmark_service import (
BookmarkService
)

study_bp = Blueprint(
    "study",
    __name__,
    url_prefix="/study"
)


# ==========================
# Get all study materials
# ==========================

@study_bp.route(
    "/materials",
    methods=["GET"]
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
        "materials": materials
    })


# ==========================
# Get one material
# ==========================

@study_bp.route(
    "/material/<material_id>",
    methods=["GET"]
)
def get_material(material_id):

    material = (
        StudyService.get_material_by_id(
            material_id
        )
    )

    if not material:

        return jsonify({
            "success": False,
            "message": "Material not found"
        }), 404

    return jsonify({
        "success": True,
        "material": material
    })


# ==========================
# Search study materials
# ==========================

@study_bp.route(
    "/search",
    methods=["GET"]
)
def search_materials():

    query = request.args.get(
        "q",
        ""
    )

    results = (
        StudyService.search_materials(
            query
        )
    )

    return jsonify({
        "success": True,
        "count": len(results),
        "results": results
    })


# ==========================
# Upload material
# ==========================

@study_bp.route(
    "/upload",
    methods=["POST"]
)
def upload_material():

    data = request.json

    title = data.get("title")
    category = data.get("category")
    subcategory = data.get(
        "subcategory"
    )
    content = data.get("content")

    year = data.get("year")
    tags = data.get("tags", [])

    result = (
        LessonProcessor
        .process_text_material(
            title=title,
            category=category,
            subcategory=subcategory,
            content=content,
            year=year,
            tags=tags
        )
    )

    return jsonify(result)
# ==========================
# Ask RevelaAI
# ==========================

@study_bp.route(
    "/ask-ai",
    methods=["POST"]
)
def ask_ai():

    data = request.json

    material_id = data.get(
        "material_id"
    )

    question = data.get(
        "question"
    )

    if not material_id:

        return jsonify({
            "success": False,
            "message":"material_id required"
        }),400

    if not question:

        return jsonify({
            "success": False,
            "message":"question required"
        }),400

    result = (
        AIContextService
        .ask_material_ai(
            material_id,
            question
        )
    )

    return jsonify(
        result
    )


# ==========================
# Bookmark material
# ==========================

@study_bp.route(
    "/bookmark",
    methods=["POST"]
)
def bookmark_material():

    data = request.json

    user_id = data.get(
        "user_id"
    )

    material_id = data.get(
        "material_id"
    )

    if not user_id:

        return jsonify({
            "success":False,
            "message":"user_id required"
        }),400

    if not material_id:

        return jsonify({
            "success":False,
            "message":"material_id required"
        }),400


    result = (
        BookmarkService
        .add_bookmark(
            user_id,
            material_id
        )
    )

    return jsonify(
        result
    )


# ==========================
# User bookmarks
# ==========================

@study_bp.route(
    "/bookmarks/<user_id>",
    methods=["GET"]
)
def get_bookmarks(
    user_id
):

    bookmarks = (
        BookmarkService
        .get_user_bookmarks(
            user_id
        )
    )

    return jsonify({

        "success":True,
        "count":len(
            bookmarks
        ),
        "bookmarks":bookmarks
    })
