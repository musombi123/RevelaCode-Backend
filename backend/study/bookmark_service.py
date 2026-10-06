# backend/study/bookmark_service.py

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo.errors import DuplicateKeyError

from backend.db import get_db
from backend.study.study_service import StudyService


# =========================================================
# LOGGING
# =========================================================

logger = logging.getLogger(
    "revelacode.study.bookmark_service"
)


# =========================================================
# CONSTANTS
# =========================================================

COLLECTION_NAME = "study_bookmarks"

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


# =========================================================
# HELPERS
# =========================================================

def clean_string(
    value: Any,
) -> str:
    """
    Normalize an arbitrary value into a trimmed string.
    """

    if value is None:
        return ""

    return str(
        value
    ).strip()


def utc_now_iso() -> str:
    """
    Return a timezone-aware UTC timestamp.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


def serialize_value(
    value: Any,
) -> Any:
    """
    Convert Mongo/Python values to JSON-safe values.
    """

    if value is None:
        return None

    if isinstance(
        value,
        dict,
    ):

        return {
            str(key): serialize_value(
                item
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):

        return [
            serialize_value(
                item
            )
            for item in value
        ]

    if isinstance(
        value,
        datetime,
    ):

        return value.isoformat()

    # Avoid importing bson.ObjectId solely for serialization.
    if value.__class__.__name__ == "ObjectId":

        return str(
            value
        )

    return value


def normalize_limit(
    value: Any,
) -> int:
    """
    Normalize bookmark query limits.
    """

    try:

        limit = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return DEFAULT_LIMIT

    return min(
        max(
            limit,
            1,
        ),
        MAX_LIMIT,
    )


# =========================================================
# BOOKMARK SERVICE
# =========================================================

class BookmarkService:

    COLLECTION = COLLECTION_NAME

    # =====================================================
    # COLLECTION
    # =====================================================

    @classmethod
    def get_collection(
        cls,
    ):
        """
        Return the canonical bookmark collection.
        """

        db = get_db()

        return db[
            cls.COLLECTION
        ]

    # =====================================================
    # INDEX
    # =====================================================

    @classmethod
    def ensure_indexes(
        cls,
    ) -> None:
        """
        Ensure one user cannot bookmark the same material
        multiple times.

        Existing legacy duplicate records can cause MongoDB
        to reject index creation; in that case we log the
        issue and continue using application-level checking.
        """

        try:

            collection = (
                cls.get_collection()
            )

            collection.create_index(
                [
                    (
                        "user_id",
                        1,
                    ),
                    (
                        "material_id",
                        1,
                    ),
                ],
                unique=True,
                name="study_bookmarks_user_material_unique",
            )

        except Exception as exc:

            logger.warning(
                "Could not ensure Study bookmark unique index: %s",
                exc,
            )

    # =====================================================
    # VALIDATE IDENTIFIERS
    # =====================================================

    @classmethod
    def validate_identifiers(
        cls,
        user_id: Any,
        material_id: Any,
    ) -> tuple[str, str, Optional[dict]]:
        """
        Normalize and validate bookmark identifiers.

        Returns:

            user_id,
            material_id,
            error_response
        """

        normalized_user_id = clean_string(
            user_id
        )

        normalized_material_id = clean_string(
            material_id
        )

        if not normalized_user_id:

            return (
                "",
                "",
                {
                    "success": False,
                    "message": (
                        "user_id is required."
                    ),
                },
            )

        if not normalized_material_id:

            return (
                normalized_user_id,
                "",
                {
                    "success": False,
                    "message": (
                        "material_id is required."
                    ),
                },
            )

        return (
            normalized_user_id,
            normalized_material_id,
            None,
        )

    # =====================================================
    # FIND BOOKMARK
    # =====================================================

    @classmethod
    def find_bookmark(
        cls,
        user_id: Any,
        material_id: Any,
    ) -> Optional[dict]:
        """
        Find one bookmark belonging to one user/material pair.
        """

        user_id, material_id, error = (
            cls.validate_identifiers(
                user_id,
                material_id,
            )
        )

        if error:
            return None

        collection = cls.get_collection()

        bookmark = collection.find_one(
            {
                "user_id": user_id,
                "material_id": material_id,
            }
        )

        return (
            serialize_value(
                bookmark
            )
            if bookmark
            else None
        )

    # =====================================================
    # SAVE BOOKMARK
    # =====================================================

    @classmethod
    def add_bookmark(
        cls,
        user_id,
        material_id,
    ):
        """
        Create a bookmark for a user.

        The service verifies the referenced Study material
        before writing the bookmark.
        """

        user_id, material_id, error = (
            cls.validate_identifiers(
                user_id,
                material_id,
            )
        )

        if error:
            return error

        # -------------------------------------------------
        # Verify material exists.
        #
        # The route already performs this check, but keeping
        # it here protects callers that use the service
        # directly.
        # -------------------------------------------------

        try:

            material = (
                StudyService
                .get_material_by_id(
                    material_id
                )
            )

        except Exception as exc:

            logger.exception(
                "Failed to verify Study material for bookmark: %s",
                material_id,
            )

            return {
                "success": False,
                "message": (
                    "Unable to verify study material."
                ),
            }

        if not material:

            return {
                "success": False,
                "message": (
                    "Study material not found."
                ),
            }

        collection = (
            cls.get_collection()
        )

        # Best effort database-level uniqueness.
        cls.ensure_indexes()

        # -------------------------------------------------
        # Existing bookmark.
        # -------------------------------------------------

        existing = collection.find_one(
            {
                "user_id": user_id,
                "material_id": material_id,
            }
        )

        if existing:

            existing_id = existing.get(
                "_id"
            )

            return {
                "success": True,
                "already_bookmarked": True,
                "message": (
                    "Material is already bookmarked."
                ),
                "bookmark": {
                    "id": (
                        str(
                            existing_id
                        )
                        if existing_id is not None
                        else None
                    ),
                    "user_id": user_id,
                    "material_id": material_id,
                    "created_at": (
                        existing.get(
                            "created_at"
                        )
                    ),
                    "updated_at": (
                        existing.get(
                            "updated_at"
                        )
                    ),
                },
            }

        # -------------------------------------------------
        # Create bookmark.
        # -------------------------------------------------

        now = utc_now_iso()

        document = {
            "user_id": user_id,
            "material_id": material_id,
            "created_at": now,
            "updated_at": now,
        }

        try:

            result = (
                collection.insert_one(
                    document
                )
            )

        except DuplicateKeyError:

            # Another request may have inserted the same
            # bookmark between our find_one() and insert_one().
            existing = collection.find_one(
                {
                    "user_id": user_id,
                    "material_id": material_id,
                }
            )

            return {
                "success": True,
                "already_bookmarked": True,
                "message": (
                    "Material is already bookmarked."
                ),
                "bookmark": {
                    "id": (
                        str(
                            existing.get(
                                "_id"
                            )
                        )
                        if existing
                        else None
                    ),
                    "user_id": user_id,
                    "material_id": material_id,
                    "created_at": (
                        existing.get(
                            "created_at"
                        )
                        if existing
                        else now
                    ),
                    "updated_at": (
                        existing.get(
                            "updated_at"
                        )
                        if existing
                        else now
                    ),
                },
            }

        except Exception as exc:

            logger.exception(
                "Failed to save bookmark user=%s material=%s",
                user_id,
                material_id,
            )

            return {
                "success": False,
                "message": (
                    "Failed to save study bookmark."
                ),
            }

        return {
            "success": True,
            "already_bookmarked": False,
            "message": (
                "Material bookmarked successfully."
            ),
            "bookmark": {
                "id": str(
                    result.inserted_id
                ),
                "user_id": user_id,
                "material_id": material_id,
                "created_at": now,
                "updated_at": now,
            },
        }

    # =====================================================
    # GET USER BOOKMARKS
    # =====================================================

    @classmethod
    def get_bookmarks(
        cls,
        user_id,
        *,
        limit: int = DEFAULT_LIMIT,
    ):
        """
        Return a user's bookmarks ordered newest-first.

        The public route can then resolve the material IDs into
        full Study material objects.
        """

        user_id = clean_string(
            user_id
        )

        if not user_id:
            return []

        safe_limit = normalize_limit(
            limit
        )

        try:

            collection = (
                cls.get_collection()
            )

            cursor = (
                collection
                .find(
                    {
                        "user_id":
                            user_id,
                    }
                )
                .sort(
                    [
                        (
                            "created_at",
                            -1,
                        ),
                        (
                            "_id",
                            -1,
                        ),
                    ]
                )
                .limit(
                    safe_limit
                )
            )

            return [
                serialize_value(
                    bookmark
                )
                for bookmark in cursor
            ]

        except Exception as exc:

            logger.exception(
                "Failed to load Study bookmarks for user=%s",
                user_id,
            )

            return []

    # =====================================================
    # CHECK BOOKMARK
    # =====================================================

    @classmethod
    def is_bookmarked(
        cls,
        user_id,
        material_id,
    ) -> bool:
        """
        Check whether a user has bookmarked a material.
        """

        user_id, material_id, error = (
            cls.validate_identifiers(
                user_id,
                material_id,
            )
        )

        if error:
            return False

        try:

            collection = (
                cls.get_collection()
            )

            bookmark = collection.find_one(
                {
                    "user_id": user_id,
                    "material_id": material_id,
                },
                {
                    "_id": 1,
                },
            )

            return bookmark is not None

        except Exception as exc:

            logger.warning(
                "Bookmark check failed user=%s material=%s: %s",
                user_id,
                material_id,
                exc,
            )

            return False

    # =====================================================
    # GET ONE BOOKMARK
    # =====================================================

    @classmethod
    def get_bookmark(
        cls,
        user_id,
        material_id,
    ) -> Optional[dict]:
        """
        Return one bookmark or None.
        """

        return cls.find_bookmark(
            user_id,
            material_id,
        )

    # =====================================================
    # REMOVE BOOKMARK
    # =====================================================

    @classmethod
    def remove_bookmark(
        cls,
        user_id,
        material_id,
    ):
        """
        Remove a user's bookmark.

        Removing a non-existent bookmark is treated as
        successful/idempotent.
        """

        user_id, material_id, error = (
            cls.validate_identifiers(
                user_id,
                material_id,
            )
        )

        if error:
            return error

        try:

            collection = (
                cls.get_collection()
            )

            result = collection.delete_one(
                {
                    "user_id": user_id,
                    "material_id": material_id,
                }
            )

            if result.deleted_count:

                return {
                    "success": True,
                    "removed": True,
                    "message": (
                        "Bookmark removed successfully."
                    ),
                    "user_id": user_id,
                    "material_id": material_id,
                }

            return {
                "success": True,
                "removed": False,
                "message": (
                    "Bookmark was not present."
                ),
                "user_id": user_id,
                "material_id": material_id,
            }

        except Exception as exc:

            logger.exception(
                "Failed to remove bookmark user=%s material=%s",
                user_id,
                material_id,
            )

            return {
                "success": False,
                "message": (
                    "Failed to remove study bookmark."
                ),
            }

    # =====================================================
    # COUNT USER BOOKMARKS
    # =====================================================

    @classmethod
    def count_bookmarks(
        cls,
        user_id,
    ) -> int:
        """
        Return the number of bookmarks owned by a user.
        """

        user_id = clean_string(
            user_id
        )

        if not user_id:
            return 0

        try:

            return (
                cls
                .get_collection()
                .count_documents(
                    {
                        "user_id":
                            user_id,
                    }
                )
            )

        except Exception as exc:

            logger.warning(
                "Bookmark count failed for user=%s: %s",
                user_id,
                exc,
            )

            return 0