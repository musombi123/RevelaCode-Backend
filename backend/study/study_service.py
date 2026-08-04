# backend/study/study_service.py

import os
import json

from bson import ObjectId
from bson.errors import InvalidId

from backend.db import get_db


BASE_DIR = os.path.dirname(
    os.path.dirname(__file__)
)

STUDY_PATH = os.path.join(
    BASE_DIR,
    "user_data",
    "study_materials"
)


class StudyService:

    @staticmethod
    def get_categories():
        return [
            "faith",
            "education"
        ]

    @staticmethod
    def get_materials(
        category=None,
        subcategory=None,
        file_type=None
    ):

        db = get_db()

        query = {}

        if category:
            query["category"] = category

        if subcategory:
            query["subcategory"] = subcategory

        if file_type:
            query["file_type"] = file_type

        try:

            materials = list(
                db["study_materials"].find(query)
            )

            for material in materials:
                material["_id"] = str(material["_id"])

            return materials

        except Exception as e:

            print(f"Database error: {e}")

            return StudyService.load_local(
                category
            )

    @staticmethod
    def load_local(category=None):

        materials = []

        if not os.path.exists(STUDY_PATH):
            return materials

        for root, dirs, files in os.walk(STUDY_PATH):

            for file in files:

                if not file.endswith(".json"):
                    continue

                try:

                    path = os.path.join(
                        root,
                        file
                    )

                    with open(
                        path,
                        "r",
                        encoding="utf-8"
                    ) as f:

                        data = json.load(f)

                    if (
                        category and
                        data.get("category") != category
                    ):
                        continue

                    materials.append(data)

                except Exception as e:

                    print(f"Read error: {e}")

        return materials

    @staticmethod
    def get_material_by_id(material_id):

        db = get_db()

        # --------------------------------------
        # 1. Try MongoDB ObjectId
        # --------------------------------------
        try:

            material = db["study_materials"].find_one({
                "_id": ObjectId(material_id)
            })

            if material:
                material["_id"] = str(material["_id"])
                return material

        except (InvalidId, TypeError):
            pass

        except Exception as e:

            print(
                f"MongoDB ObjectId lookup error: {e}"
            )

        # --------------------------------------
        # 2. Try custom UUID field
        # --------------------------------------
        try:

            material = db["study_materials"].find_one({
                "id": material_id
            })

            if material:
                material["_id"] = str(material["_id"])
                return material

        except Exception as e:

            print(
                f"UUID lookup error: {e}"
            )

        # --------------------------------------
        # 3. Fallback to local JSON
        # --------------------------------------
        try:

            materials = StudyService.load_local()

            for material in materials:

                if (
                    material.get("_id") == material_id
                    or material.get("id") == material_id
                    or material.get("material_id") == material_id
                ):
                    return material

        except Exception as e:

            print(
                f"Local lookup error: {e}"
            )

        return None

    @staticmethod
    def search_materials(query):

        db = get_db()

        try:

            results = list(

                db["study_materials"].find({

                    "$or": [

                        {
                            "title": {
                                "$regex": query,
                                "$options": "i"
                            }
                        },

                        {
                            "content": {
                                "$regex": query,
                                "$options": "i"
                            }
                        },

                        {
                            "tags": {
                                "$regex": query,
                                "$options": "i"
                            }
                        }

                    ]

                })

            )

            for material in results:
                material["_id"] = str(material["_id"])

            return results

        except Exception as e:

            print(f"Search error: {e}")

            return []
