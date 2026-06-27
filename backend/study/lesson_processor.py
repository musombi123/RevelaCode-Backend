# backend/study/lesson_processor.py

import os
import json

from uuid import uuid4
from datetime import datetime

from backend.models.StudyMaterial import (
    StudyMaterial
)
from backend.study.upload_service import (
    UploadService
)

from backend.study.file_extractors import (
    FileExtractors
)

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
    def process_uploaded_file(file):

        try:

            filename = file.filename

            extension = (
                filename.split(
                    "."
                )[-1].lower()
            )

            # -----------------
            # Save physical file
            # -----------------

            path = (
                UploadService.save(
                    file
                )
            )

            # -----------------
            # File handlers
            # -----------------

            extractors = {

                "pdf":
                FileExtractors.extract_pdf,

                "docx":
                FileExtractors.extract_docx,

                "txt":
                FileExtractors.extract_txt
            }

            extractor = (
                extractors.get(
                    extension
                )
            )

            if not extractor:

                return {

                    "success": False,

                    "message":
                    f"{extension} not supported"
                }

            # -----------------
            # Extract text
            # -----------------

            content = (
                extractor(
                    path
                )
            )

            return {

                "success": True,

                "filename": filename,

                "file_type": extension,

                "content": content,

                "path": path
            }

        except Exception as e:

            return {

                "success": False,

                "error": str(e)
            }

        # -----------------
        # Save Mongo
        # -----------------

        try:

            db = get_db()

            material_data[
                "file_backup"
            ] = filename

            material_data[
                "created_at"
            ] = str(
                datetime.utcnow()
            )

            # Prevent duplicate uploads

            existing = db[
                "study_materials"
            ].find_one({

                "title": title,
                "category": category,
                "subcategory": subcategory

            })

            if existing:

                existing["_id"] = str(
                    existing["_id"]
                )

                return {

                    "success": False,

                    "message":
                    "Material already exists",

                    "material":
                    existing
                }


            result = db[
                "study_materials"
            ].insert_one(
                material_data
            )

            material_data[
                "_id"
            ] = str(
                result.inserted_id
            )


        except Exception as e:

            print(
                "Mongo Error:",
                str(e)
            )


        # -----------------
        # IMPORTANT
        # -----------------

        return {

            "success": True,

            "message":
            "Study material created",

            "file":
            filename,

            "material":
            material_data
        }



    @staticmethod
    def process_uploaded_file(
        file
    ):

        try:

            filename = (
                file.filename
            )

            content = (
                file.read()
            )

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