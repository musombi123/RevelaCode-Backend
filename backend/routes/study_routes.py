# backend/study/lesson_processor.py

import os
import json

from uuid import uuid4
from datetime import datetime

from backend.models.StudyMaterial import StudyMaterial
from backend.db import get_db


BASE_DIR = os.path.dirname(
    os.path.dirname(__file__)
)

STUDY_STORAGE = os.path.join(
    BASE_DIR,
    "user_data",
    "study_materials"
)


class LessonProcessor:

    @staticmethod
    def ensure_path(path):

        if not os.path.exists(path):
            os.makedirs(path)

    @staticmethod
    def process_text_material(
        title,
        category,
        subcategory,
        content,
        year=None,
        tags=None
    ):

        material = StudyMaterial(
            title=title,
            category=category,
            subcategory=subcategory,
            content=content,
            year=year,
            tags=tags
        )

        material_data = material.to_dict()

        save_path = os.path.join(
            STUDY_STORAGE,
            category,
            subcategory,
            str(year or "general")
        )

        LessonProcessor.ensure_path(
            save_path
        )

        filename = f"{uuid4()}.json"

        full_path = os.path.join(
            save_path,
            filename
        )

        with open(
            full_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                material_data,
                f,
                indent=4,
                ensure_ascii=False
            )

        try:

            db = get_db()

            material_data["file_backup"] = filename
            material_data["created_at"] = str(
                datetime.utcnow()
            )

            result = db[
                "study_materials"
            ].insert_one(
                material_data
            )

            material_data["_id"] = str(
                result.inserted_id
            )

        except Exception as e:

            print(
                "Mongo Error:",
                str(e)
            )

        return {
            "success": True,
            "message": "Study material created",
            "file": filename,
            "material": material_data
        }

    @staticmethod
    def process_uploaded_file(file):

        try:

            filename = file.filename

            content = file.read()

            text = content.decode(
                "utf-8",
                errors="ignore"
            )

            return {
                "success": True,
                "content": text,
                "filename": filename
            }

        except Exception as e:

            return {
                "success": False,
                "error": str(e)
            }