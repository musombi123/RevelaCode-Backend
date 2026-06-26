# backend/study/bookmark_service.py

import os
import json

from backend.models.Bookmark import Bookmark

BASE_DIR = os.path.dirname(
    os.path.dirname(__file__)
)

BOOKMARKS_FILE = os.path.join(
    BASE_DIR,
    "user_data",
    "bookmarks.json"
)


class BookmarkService:

    @staticmethod
    def load_bookmarks():

        if not os.path.exists(
            BOOKMARKS_FILE
        ):

            return []

        with open(
            BOOKMARKS_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)


    @staticmethod
    def save_bookmarks(data):

        with open(
            BOOKMARKS_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                indent=4
            )


    @staticmethod
    def add_bookmark(
        user_id,
        material_id
    ):

        bookmarks = (
            BookmarkService
            .load_bookmarks()
        )

        existing = next(

            (
                b for b in bookmarks
                if b["user_id"] == user_id
                and b["material_id"] == material_id
            ),

            None
        )

        if existing:

            return {
                "success": False,
                "message":
                "Already bookmarked"
            }

        bookmark = Bookmark(
            user_id,
            material_id
        )

        bookmarks.append(
            bookmark.to_dict()
        )

        BookmarkService.save_bookmarks(
            bookmarks
        )

        return {
            "success": True,
            "bookmark":
            bookmark.to_dict()
        }


    @staticmethod
    def get_user_bookmarks(
        user_id
    ):

        bookmarks = (
            BookmarkService
            .load_bookmarks()
        )

        return [

            b for b in bookmarks

            if b["user_id"]
            == user_id
        ]
