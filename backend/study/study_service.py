# backend/study/study_service.py

import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

STUDY_PATH = os.path.join(
    BASE_DIR,
    "user_data",
    "study_materials"
)


class StudyService:

    @staticmethod
    def get_categories():
        return ["faith", "education"]


    @staticmethod
    def get_materials(category=None):
        materials = []

        if not os.path.exists(STUDY_PATH):
            return []

        for root, dirs, files in os.walk(STUDY_PATH):
            for file in files:

                if not file.endswith(".json"):
                    continue

                file_path = os.path.join(root, file)

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                        if category:
                            if data.get("category") != category:
                                continue

                        materials.append(data)

                except Exception as e:
                    print(
                        f"Error reading {file}: {e}"
                    )

        return materials


    @staticmethod
    def get_material_by_id(material_id):

        materials = StudyService.get_materials()

        for item in materials:
            if item.get("id") == material_id:
                return item

        return None


    @staticmethod
    def search_materials(query):

        results = []

        materials = StudyService.get_materials()

        query = query.lower()

        for item in materials:

            title = item.get(
                "title",
                ""
            ).lower()

            content = item.get(
                "content",
                ""
            ).lower()

            if (
                query in title or
                query in content
            ):
                results.append(item)

        return results
