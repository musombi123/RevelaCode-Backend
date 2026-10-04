# backend/study/lesson_processor.py

from __future__ import annotations

import os
from datetime import datetime

from backend.db import get_db
from backend.models.StudyMaterial import StudyMaterial
from backend.study.upload_service import UploadService
from backend.study.file_extractors import FileExtractors


BASE_DIR = os.path.dirname(
    os.path.dirname(__file__)
)

STUDY_STORAGE = os.path.join(
    BASE_DIR,
    "user_data",
    "study_materials"
)

SUPPORTED_FILE_TYPES = {
    "pdf",
    "docx",
    "txt",
}


class LessonProcessor:

    # =====================================================
    # PATH
    # =====================================================

    @staticmethod
    def ensure_path(path: str):
        os.makedirs(
            path,
            exist_ok=True
        )

    # =====================================================
    # TAG NORMALIZATION
    # =====================================================

    @staticmethod
    def normalize_tags(tags):
        if tags is None:
            return []

        if isinstance(tags, str):
            tags = [
                item.strip()
                for item in tags.split(",")
            ]

        if not isinstance(tags, list):
            return []

        cleaned = []

        for item in tags:
            if not isinstance(item, str):
                continue

            value = item.strip()

            if value:
                cleaned.append(value)

        return list(dict.fromkeys(cleaned))

    # =====================================================
    # DUPLICATE CHECK
    # =====================================================

    @staticmethod
    def find_duplicate(
        db,
        title,
        category,
        subcategory,
    ):
        return db[
            "study_materials"
        ].find_one({
            "title": title,
            "category": category,
            "subcategory": subcategory,
        })

    # =====================================================
    # SAVE MATERIAL
    # =====================================================

    @staticmethod
    def save_material(
        *,
        title,
        category,
        subcategory,
        content,
        year=None,
        tags=None,
        material_type="lesson",
        file_path=None,
        source_filename=None,
    ):
        title = str(
            title or ""
        ).strip()

        category = str(
            category or ""
        ).strip()

        subcategory = str(
            subcategory or ""
        ).strip()

        content = str(
            content or ""
        ).strip()

        if not title:
            raise ValueError(
                "Study material title is required."
            )

        if not category:
            raise ValueError(
                "Study material category is required."
            )

        if not subcategory:
            raise ValueError(
                "Study material subcategory is required."
            )

        if not content:
            raise ValueError(
                "Study material content could not be extracted."
            )

        db = get_db()

        existing = (
            LessonProcessor.find_duplicate(
                db,
                title,
                category,
                subcategory,
            )
        )

        if existing:
            existing["_id"] = str(
                existing["_id"]
            )

            return {
                "success": False,
                "message": (
                    "A study material with the "
                    "same title, category and "
                    "subcategory already exists."
                ),
                "material": existing,
            }

        material = StudyMaterial(
            title=title,
            category=category,
            subcategory=subcategory,
            content=content,
            material_type=material_type,
            file_path=file_path,
            year=year,
            author="RevelaCode Admin",
            tags=LessonProcessor.normalize_tags(
                tags
            ),
            metadata={
                "source_filename":
                    source_filename,
                "content_length":
                    len(content),
                "processed_at":
                    datetime.utcnow().isoformat(),
            },
            ai_enabled=True,
        )

        material_data = (
            material.to_dict()
        )

        result = db[
            "study_materials"
        ].insert_one(
            material_data
        )

        material_data["_id"] = str(
            result.inserted_id
        )

        return {
            "success": True,
            "message": (
                "Study material created successfully."
            ),
            "material": material_data,
        }

    # =====================================================
    # TEXT MATERIAL
    # =====================================================

    @staticmethod
    def process_text_material(
        *,
        title,
        category,
        subcategory,
        content,
        year=None,
        tags=None,
    ):
        return LessonProcessor.save_material(
            title=title,
            category=category,
            subcategory=subcategory,
            content=content,
            year=year,
            tags=tags,
            material_type="lesson",
        )

    # =====================================================
    # FILE EXTRACTION
    # =====================================================

    @staticmethod
    def process_uploaded_file(
        file,
        *,
        title=None,
        category=None,
        subcategory=None,
        year=None,
        tags=None,
    ):
        if file is None:
            return {
                "success": False,
                "message": "No file was provided.",
            }

        filename = (
            str(
                file.filename or ""
            ).strip()
        )

        if not filename:
            return {
                "success": False,
                "message": "No file was selected.",
            }

        extension = (
            filename.rsplit(
                ".",
                1
            )[-1].lower()
            if "." in filename
            else ""
        )

        if extension not in SUPPORTED_FILE_TYPES:
            return {
                "success": False,
                "message": (
                    f".{extension or 'file'} is not supported. "
                    "Supported formats are PDF, DOCX and TXT."
                ),
            }

        if not title:
            title = os.path.splitext(
                filename
            )[0]

        try:
            # -------------------------------------------------
            # Save uploaded source file
            # -------------------------------------------------

            saved_path = (
                UploadService.save(
                    file
                )
            )

            # -------------------------------------------------
            # Select correct extractor
            # -------------------------------------------------

            extractors = {
                "pdf":
                    FileExtractors.extract_pdf,

                "docx":
                    FileExtractors.extract_docx,

                "txt":
                    FileExtractors.extract_txt,
            }

            extractor = extractors[
                extension
            ]

            # -------------------------------------------------
            # Extract actual document text
            # -------------------------------------------------

            content = extractor(
                saved_path
            )

            content = str(
                content or ""
            ).strip()

            if not content:
                return {
                    "success": False,
                    "message": (
                        "The file was uploaded, but "
                        "no readable text could be extracted."
                    ),
                    "filename": filename,
                    "file_type": extension,
                }

            # -------------------------------------------------
            # Store relative source path
            # -------------------------------------------------

            relative_path = os.path.relpath(
                saved_path,
                BASE_DIR,
            )

            # -------------------------------------------------
            # Save extracted material
            # -------------------------------------------------

            result = (
                LessonProcessor.save_material(
                    title=title,
                    category=category,
                    subcategory=subcategory,
                    content=content,
                    year=year,
                    tags=tags,
                    material_type=extension,
                    file_path=relative_path,
                    source_filename=filename,
                )
            )

            return {
                **result,
                "filename": filename,
                "file_type": extension,
                "extracted_characters":
                    len(content),
            }

        except Exception as exc:
            return {
                "success": False,
                "message": (
                    "Study document processing failed."
                ),
                "error": str(exc),
                "filename": filename,
                "file_type": extension,
            }
