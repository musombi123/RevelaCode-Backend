# backend/routes/study_routes.py

from flask import Blueprint
from flask import request
from flask import jsonify

from backend.study.study_service import StudyService
from backend.study.lesson_processor import LessonProcessor
from backend.study.material_preferences import (
    MaterialPreferences
)

study_bp = Blueprint(
    "study",
    __name__,
    url_prefix="/study"
)


@study_bp.route(
    "/materials",
    methods=["GET"]
)
def get_materials():

    category=request.args.get(
        "category"
    )

    materials=StudyService.get_materials(
        category
    )

    return jsonify({
        "success":True,
        "count":len(materials),
        "materials":materials
    })

# ======================
# Save preferences
# ======================

@study_bp.route(
    "/preferences",
    methods=["POST"]
)
def save_preferences():

    data = request.json

    user_id = data.get(
        "user_id"
    )

    preferences = data.get(
        "preferences",
        []
    )

    result = (
        MaterialPreferences
        .save_preferences(
            user_id,
            preferences
        )
    )

    return jsonify(
        result
    )


# ======================
# Recommended materials
# ======================

@study_bp.route(
    "/recommend/<user_id>",
    methods=["GET"]
)
def recommended_materials(
    user_id
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
        "materials": materials

    })

@study_bp.route(
    "/upload",
    methods=["POST"]
)
def upload_material():

    data=request.json

    result=LessonProcessor.process_text_material(
        title=data.get("title"),
        category=data.get("category"),
        subcategory=data.get("subcategory"),
        content=data.get("content"),
        year=data.get("year"),
        tags=data.get("tags",[])
    )

    return jsonify(result)


@study_bp.route(
    "/material/<material_id>",
    methods=["GET"]
)
def get_material(material_id):

    material=StudyService.get_material_by_id(
        material_id
    )

    if not material:

        return jsonify({
            "success":False,
            "message":"Material not found"
        }),404

    return jsonify({
        "success":True,
        "material":material
    })


@study_bp.route(
    "/search",
    methods=["GET"]
)
def search_materials():

    query=request.args.get(
        "q",""
    )

    results=StudyService.search_materials(
        query
    )

    return jsonify({
        "success":True,
        "count":len(results),
        "results":results
    })