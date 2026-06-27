# backend/routes/study_routes.py

from flask import Blueprint
from flask import request
from flask import jsonify

from backend.db import get_db
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

# ======================
# Save bookmark
# ======================

@study_bp.route(
    "/bookmark",
    methods=["POST"]
)
def save_bookmark():

    data = request.json or {}

    user_id = data.get(
        "user_id"
    )

    material_id = data.get(
        "material_id"
    )

    if not user_id or not material_id:

        return jsonify({
            "success":False,
            "message":"user_id and material_id required"
        }),400


    db = get_db()

    existing = db[
        "study_bookmarks"
    ].find_one({

        "user_id":user_id,
        "material_id":material_id
    })


    if existing:

        return jsonify({

            "success":True,
            "message":"Already bookmarked"

        })


    db[
        "study_bookmarks"
    ].insert_one({

        "user_id":user_id,
        "material_id":material_id
    })


    return jsonify({

        "success":True,
        "message":"Bookmark saved"

    })


# ======================
# Get bookmarks
# ======================

@study_bp.route(
    "/bookmarks/<user_id>",
    methods=["GET"]
)
def get_bookmarks(user_id):

    from backend.db import get_db

    db = get_db()

    bookmarks = list(

        db[
            "study_bookmarks"
        ].find({

            "user_id":user_id
        })

    )

    materials=[]

    for bookmark in bookmarks:

        material = StudyService.get_material_by_id(

            bookmark.get(
                "material_id"
            )
        )

        if material:

            materials.append(
                material
            )


    return jsonify({

        "success":True,
        "bookmarks":materials,
        "count":len(materials)

    })