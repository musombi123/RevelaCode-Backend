# backend/study/bookmark_service.py

from datetime import datetime

from backend.db import get_db


class BookmarkService:

    COLLECTION = "study_bookmarks"

    # =====================================================
    # SAVE BOOKMARK
    # =====================================================

    @classmethod
    def add_bookmark(
        cls,
        user_id,
        material_id,
    ):
        if not user_id:
            return {
                "success": False,
                "message": "user_id is required.",
            }

        if not material_id:
            return {
                "success": False,
                "message": "material_id is required.",
            }

        user_id = str(user_id).strip()
        material_id = str(material_id).strip()

        if not user_id:
            return {
                "success": False,
                "message": "user_id is required.",
            }

        if not material_id:
            return {
                "success": False,
                "message": "material_id is required.",
            }

        db = get_db()

        collection = db[
            cls.COLLECTION
        ]

        # -------------------------------------------------
        # Prevent duplicate bookmarks
        # -------------------------------------------------

        existing = collection.find_one({
            "user_id": user_id,
            "material_id": material_id,
        })

        if existing:
            return {
                "success": True,
                "already_bookmarked": True,
                "message": "Material is already bookmarked.",
                "bookmark": {
                    "id": str(
                        existing.get("_id")
                    ),
                    "user_id": user_id,
                    "material_id": material_id,
                },
            }

        # -------------------------------------------------
        # Create bookmark
        # -------------------------------------------------

        now = datetime.utcnow().isoformat()

        result = collection.insert_one({
            "user_id": user_id,
            "material_id": material_id,
            "created_at": now,
            "updated_at": now,
        })

        return {
            "success": True,
            "already_bookmarked": False,
            "message": "Material bookmarked successfully.",
            "bookmark": {
                "id": str(
                    result.inserted_id
                ),
                "user_id": user_id,
                "material_id": material_id,
                "created_at": now,
            },
        }

    # =====================================================
    # GET USER BOOKMARKS
    # =====================================================

    @classmethod
    def get_bookmarks(
        cls,
        user_id,
    ):
        if not user_id:
            return []

        db = get_db()

        bookmarks = list(
            db[
                cls.COLLECTION
            ].find({
                "user_id": str(user_id),
            })
        )

        for bookmark in bookmarks:
            if bookmark.get("_id"):
                bookmark["_id"] = str(
                    bookmark["_id"]
                )

        return bookmarks

    # =====================================================
    # CHECK BOOKMARK
    # =====================================================

    @classmethod
    def is_bookmarked(
        cls,
        user_id,
        material_id,
    ):
        if not user_id or not material_id:
            return False

        db = get_db()

        bookmark = db[
            cls.COLLECTION
        ].find_one({
            "user_id": str(user_id),
            "material_id": str(material_id),
        })

        return bookmark is not None
