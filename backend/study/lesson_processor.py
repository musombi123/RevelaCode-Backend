# backend/study/lesson_processor.py

import os
import json
from uuid import uuid4

from backend.models.StudyMaterial import StudyMaterial

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

        save_path = os.path.join(
            STUDY_STORAGE,
            category,
            subcategory,
            str(year if year else "general")
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
                material.to_dict(),
                f,
                indent=4,
                ensure_ascii=False
            )

        return {
            "success": True,
            "message": "Study material created",
            "file": filename,
            "material": material.to_dict()
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
