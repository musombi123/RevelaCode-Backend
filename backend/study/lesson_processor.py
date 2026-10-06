# backend/study/lesson_processor.py

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from backend.db import get_db
from backend.models.StudyMaterial import StudyMaterial
from backend.study.file_extractors import FileExtractors
from backend.study.upload_service import UploadService


# =========================================================
# LOGGING
# =========================================================

logger = logging.getLogger(
    "revelacode.study.lesson_processor"
)


# =========================================================
# PATHS
# =========================================================

# backend/study/lesson_processor.py
#        ↑
# backend/
BASE_DIR = os.path.dirname(
    os.path.dirname(__file__)
)

STUDY_STORAGE = os.path.join(
    BASE_DIR,
    "user_data",
    "study_materials",
)


# =========================================================
# SUPPORTED FILE TYPES
# =========================================================

SUPPORTED_FILE_TYPES = {
    "pdf",
    "docx",
    "txt",
}


# =========================================================
# LIMITS
# =========================================================

# Prevent unexpectedly huge extracted documents from being
# inserted into MongoDB or passed into downstream AI systems.
MAX_EXTRACTED_CHARACTERS = 5_000_000


# =========================================================
# HELPERS
# =========================================================

def utc_now_iso() -> str:
    """
    Return a timezone-aware UTC timestamp.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


def normalize_scalar(
    value: Any,
) -> str:
    """
    Convert a value into a clean string.
    """

    if value is None:
        return ""

    return str(
        value
    ).strip()


def safe_year(
    value: Any,
) -> Optional[int]:
    """
    Normalize year input.

    Returns:
        int or None
    """

    if value is None:
        return None

    if isinstance(
        value,
        bool,
    ):
        return None

    try:

        year = int(
            str(value).strip()
        )

    except (
        TypeError,
        ValueError,
    ):

        return None

    # Reasonable study-content year range.
    if year < 1900 or year > 2100:
        return None

    return year


def content_hash(
    content: str,
) -> str:
    """
    Generate a stable SHA-256 hash for extracted content.

    This is useful for diagnostics and future duplicate
    detection without changing the current database schema.
    """

    return hashlib.sha256(
        content.encode(
            "utf-8"
        )
    ).hexdigest()


# =========================================================
# LESSON PROCESSOR
# =========================================================

class LessonProcessor:

    # =====================================================
    # PATH
    # =====================================================

    @staticmethod
    def ensure_path(
        path: str,
    ):
        """
        Create a directory when it does not exist.
        """

        if not path:
            raise ValueError(
                "Storage path is required."
            )

        os.makedirs(
            path,
            exist_ok=True,
        )

    # =====================================================
    # FILE CLEANUP
    # =====================================================

    @staticmethod
    def remove_file(
        path: Optional[str],
    ) -> None:
        """
        Safely remove a file.

        Failure to remove a temporary/orphaned upload should
        never replace the original processing result.
        """

        if not path:
            return

        try:

            if os.path.isfile(
                path
            ):
                os.remove(
                    path
                )

        except Exception as exc:

            logger.warning(
                "Unable to remove study upload %s: %s",
                path,
                exc,
            )

    # =====================================================
    # TAG NORMALIZATION
    # =====================================================

    @staticmethod
    def normalize_tags(
        tags: Any,
    ) -> list[str]:
        """
        Normalize tags from either:

            "faith,sda,bible"

        or:

            ["faith", "sda", "bible"]
        """

        if tags is None:
            return []

        if isinstance(
            tags,
            str,
        ):

            tags = [
                item.strip()
                for item in tags.split(",")
            ]

        if not isinstance(
            tags,
            (list, tuple, set),
        ):

            return []

        cleaned = []
        seen = set()

        for item in tags:

            if not isinstance(
                item,
                str,
            ):
                continue

            value = item.strip()

            if not value:
                continue

            key = value.casefold()

            if key in seen:
                continue

            seen.add(key)
            cleaned.append(
                value
            )

        return cleaned

    # =====================================================
    # DUPLICATE CHECK
    # =====================================================

    @staticmethod
    def find_duplicate(
        db,
        title: str,
        category: str,
        subcategory: str,
    ):
        """
        Find an existing material by normalized title,
        category and subcategory.

        Case-insensitive matching prevents duplicates such as:

            "Faith"
            "faith"
            "FAITH"
        """

        title = normalize_scalar(
            title
        )

        category = normalize_scalar(
            category
        )

        subcategory = normalize_scalar(
            subcategory
        )

        if not title:
            return None

        return db[
            "study_materials"
        ].find_one(
            {
                "title": {
                    "$regex": (
                        "^"
                        + __import__("re").escape(
                            title
                        )
                        + "$"
                    ),
                    "$options": "i",
                },
                "category": {
                    "$regex": (
                        "^"
                        + __import__("re").escape(
                            category
                        )
                        + "$"
                    ),
                    "$options": "i",
                },
                "subcategory": {
                    "$regex": (
                        "^"
                        + __import__("re").escape(
                            subcategory
                        )
                        + "$"
                    ),
                    "$options": "i",
                },
            }
        )

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
        author="RevelaCode Admin",
        ai_enabled=True,
        metadata=None,
    ):
        """
        Validate and persist a study material.

        This method is intentionally compatible with existing
        Study routes and SDA import services.
        """

        title = normalize_scalar(
            title
        )

        category = normalize_scalar(
            category
        )

        subcategory = normalize_scalar(
            subcategory
        )

        content = normalize_scalar(
            content
        )

        material_type = normalize_scalar(
            material_type
        ).lower() or "lesson"

        author = normalize_scalar(
            author
        ) or "RevelaCode Admin"

        year = safe_year(
            year
        )

        normalized_tags = (
            LessonProcessor.normalize_tags(
                tags
            )
        )

        # -------------------------------------------------
        # Validation
        # -------------------------------------------------

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

        if len(content) > MAX_EXTRACTED_CHARACTERS:

            raise ValueError(
                "Study material is too large after extraction."
            )

        # -------------------------------------------------
        # Database
        # -------------------------------------------------

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
                "duplicate": True,
                "message": (
                    "A study material with the "
                    "same title, category and "
                    "subcategory already exists."
                ),
                "material": existing,
            }

        # -------------------------------------------------
        # Metadata
        # -------------------------------------------------

        material_metadata = {}

        if isinstance(
            metadata,
            dict,
        ):

            material_metadata.update(
                metadata
            )

        material_metadata.update(
            {
                "content_length": len(
                    content
                ),
                "content_hash": content_hash(
                    content
                ),
                "processed_at": utc_now_iso(),
            }
        )

        if source_filename:

            material_metadata[
                "source_filename"
            ] = normalize_scalar(
                source_filename
            )

        # -------------------------------------------------
        # Build model
        # -------------------------------------------------

        material = StudyMaterial(
            title=title,
            category=category,
            subcategory=subcategory,
            content=content,
            material_type=material_type,
            file_path=file_path,
            year=year,
            author=author,
            tags=normalized_tags,
            metadata=material_metadata,
            ai_enabled=bool(
                ai_enabled
            ),
        )

        material_data = (
            material.to_dict()
        )

        # -------------------------------------------------
        # Insert
        # -------------------------------------------------

        result = db[
            "study_materials"
        ].insert_one(
            material_data
        )

        material_data["_id"] = str(
            result.inserted_id
        )

        logger.info(
            "Study material created: id=%s title=%s category=%s subcategory=%s",
            material_data.get("id"),
            title,
            category,
            subcategory,
        )

        return {
            "success": True,
            "duplicate": False,
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
        """
        Process a material supplied directly as text.
        """

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
    # FILE EXTENSION
    # =====================================================

    @staticmethod
    def detect_extension(
        filename: str,
    ) -> str:
        """
        Return a normalized file extension.
        """

        filename = normalize_scalar(
            filename
        )

        if "." not in filename:
            return ""

        return (
            filename
            .rsplit(
                ".",
                1,
            )[-1]
            .strip()
            .lower()
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
        """
        Process an uploaded PDF, DOCX or TXT document.

        Pipeline:

            validate
              ↓
            save upload
              ↓
            extract content
              ↓
            validate extracted content
              ↓
            save study material
              ↓
            cleanup orphan upload when necessary
        """

        # -------------------------------------------------
        # Basic file validation
        # -------------------------------------------------

        if file is None:

            return {
                "success": False,
                "message": (
                    "No file was provided."
                ),
            }

        raw_filename = normalize_scalar(
            getattr(
                file,
                "filename",
                "",
            )
        )

        if not raw_filename:

            return {
                "success": False,
                "message": (
                    "No file was selected."
                ),
            }

        # Avoid storing client-provided directory paths.
        filename = os.path.basename(
            raw_filename
        )

        extension = (
            LessonProcessor.detect_extension(
                filename
            )
        )

        if extension not in SUPPORTED_FILE_TYPES:

            return {
                "success": False,
                "message": (
                    f".{extension or 'file'} is not supported. "
                    "Supported formats are PDF, DOCX and TXT."
                ),
                "filename": filename,
                "file_type": extension,
            }

        # -------------------------------------------------
        # Validate metadata before touching disk
        # -------------------------------------------------

        title = (
            normalize_scalar(
                title
            )
            or os.path.splitext(
                filename
            )[0]
        )

        category = normalize_scalar(
            category
        )

        subcategory = normalize_scalar(
            subcategory
        )

        if not category:

            return {
                "success": False,
                "message": (
                    "Study material category is required."
                ),
                "filename": filename,
                "file_type": extension,
            }

        if not subcategory:

            return {
                "success": False,
                "message": (
                    "Study material subcategory is required."
                ),
                "filename": filename,
                "file_type": extension,
            }

        year = safe_year(
            year
        )

        normalized_tags = (
            LessonProcessor.normalize_tags(
                tags
            )
        )

        saved_path = None

        try:

            # -------------------------------------------------
            # Save source file
            # -------------------------------------------------

            saved_path = UploadService.save(
                file
            )

            if not saved_path:

                raise RuntimeError(
                    "Upload service did not return a file path."
                )

            if not os.path.isfile(
                saved_path
            ):

                raise FileNotFoundError(
                    "Uploaded file could not be found after saving."
                )

            # -------------------------------------------------
            # Extract document
            # -------------------------------------------------

            content = FileExtractors.extract(
                saved_path,
                extension,
            )

            content = normalize_scalar(
                content
            )

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

            if len(content) > MAX_EXTRACTED_CHARACTERS:

                return {
                    "success": False,
                    "message": (
                        "The file contains too much extracted "
                        "text to be processed safely."
                    ),
                    "filename": filename,
                    "file_type": extension,
                    "extracted_characters": len(
                        content
                    ),
                }

            # -------------------------------------------------
            # Store source path relative to backend
            # -------------------------------------------------

            relative_path = os.path.relpath(
                saved_path,
                BASE_DIR,
            )

            # Always use forward slashes for a portable
            # database representation.
            relative_path = (
                relative_path.replace(
                    os.sep,
                    "/",
                )
            )

            # -------------------------------------------------
            # Persist material
            # -------------------------------------------------

            result = LessonProcessor.save_material(
                title=title,
                category=category,
                subcategory=subcategory,
                content=content,
                year=year,
                tags=normalized_tags,
                material_type=extension,
                file_path=relative_path,
                source_filename=filename,
            )

            # -------------------------------------------------
            # Duplicate cleanup
            # -------------------------------------------------
            #
            # The source file is not needed as a second copy
            # when the material already exists.
            # -------------------------------------------------

            if not result.get(
                "success",
                False,
            ):

                LessonProcessor.remove_file(
                    saved_path
                )

                saved_path = None

            return {
                **result,
                "filename": filename,
                "file_type": extension,
                "extracted_characters": len(
                    content
                ),
            }

        except Exception as exc:

            logger.exception(
                "Study document processing failed for %s",
                filename,
            )

            # -------------------------------------------------
            # Remove orphan upload on failure
            # -------------------------------------------------

            LessonProcessor.remove_file(
                saved_path
            )

            return {
                "success": False,
                "message": (
                    "Study document processing failed."
                ),
                "filename": filename,
                "file_type": extension,
            }
