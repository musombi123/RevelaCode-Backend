# backend/study/rootword_service.py

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from backend.db import get_db


# =========================================================
# LOGGING
# =========================================================

logger = logging.getLogger(
    "revelacode.study.rootword_service"
)


# =========================================================
# CONSTANTS
# =========================================================

COLLECTION_NAME = "rootwords"

DEFAULT_SEARCH_LIMIT = 25
MAX_SEARCH_LIMIT = 100


# =========================================================
# HELPERS
# =========================================================

def utc_now() -> datetime:
    """
    Return the current timezone-aware UTC datetime.
    """

    return datetime.now(
        timezone.utc
    )


def utc_now_iso() -> str:
    """
    Return the current UTC time as ISO text.
    """

    return utc_now().isoformat()


def clean_string(
    value: Any,
) -> str:
    """
    Normalize arbitrary input to a trimmed string.
    """

    if value is None:
        return ""

    return str(
        value
    ).strip()


def normalize_lookup(
    value: Any,
) -> str:
    """
    Normalize a value for case-insensitive lookup.
    """

    return clean_string(
        value
    ).casefold()


def normalize_list(
    value: Any,
) -> list[str]:
    """
    Normalize scripture/note lists.

    Accepts:

        ["John 1:1", "John 3:16"]

    or:

        "John 1:1, John 3:16"
    """

    if value is None:
        return []

    if isinstance(
        value,
        str,
    ):

        value = [
            item.strip()
            for item in value.split(",")
        ]

    if not isinstance(
        value,
        (list, tuple, set),
    ):

        return []

    result = []
    seen = set()

    for item in value:

        text = clean_string(
            item
        )

        if not text:
            continue

        key = text.casefold()

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            text
        )

    return result


def serialize_value(
    value: Any,
) -> Any:
    """
    Convert Mongo/Python values into JSON-safe values.
    """

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
        list,
    ):

        return [
            serialize_value(
                item
            )
            for item in value
        ]

    if isinstance(
        value,
        tuple,
    ):

        return [
            serialize_value(
                item
            )
            for item in value
        ]

    # Mongo ObjectId support without importing bson directly.
    if (
        value is not None
        and value.__class__.__name__ == "ObjectId"
    ):

        return str(
            value
        )

    if isinstance(
        value,
        datetime,
    ):

        return value.isoformat()

    return value


def normalize_limit(
    value: Any,
) -> int:
    """
    Normalize search result limit.
    """

    try:

        limit = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return DEFAULT_SEARCH_LIMIT

    return max(
        1,
        min(
            limit,
            MAX_SEARCH_LIMIT,
        ),
    )


# =========================================================
# ROOT WORD SERVICE
# =========================================================

class RootWordService:

    # =====================================================
    # DUPLICATE QUERY
    # =====================================================

    @staticmethod
    def _find_duplicate(
        db,
        *,
        word: str,
        strong_number: Optional[str],
    ):
        """
        Find a duplicate root word.

        Word matching is case-insensitive.

        Strong number is checked only when a real value was
        supplied; None must never cause unrelated records
        with missing strong numbers to collide.
        """

        word_regex = {
            "$regex": (
                "^"
                + re.escape(
                    word
                )
                + "$"
            ),
            "$options": "i",
        }

        conditions = [
            {
                "word": word_regex,
            }
        ]

        if strong_number:

            conditions.append(
                {
                    "strong_number": {
                        "$regex": (
                            "^"
                            + re.escape(
                                strong_number
                            )
                            + "$"
                        ),
                        "$options": "i",
                    }
                }
            )

        return db[
            COLLECTION_NAME
        ].find_one(
            {
                "$or": conditions
            }
        )

    # =====================================================
    # NORMALIZE ROOTWORD DATA
    # =====================================================

    @staticmethod
    def _build_document(
        *,
        word: str,
        language: Optional[str],
        strong_number: Optional[str],
        transliteration: Optional[str],
        meaning: Optional[str],
        scriptures: Any,
        notes: Any,
    ) -> dict:
        """
        Build a canonical root-word document.
        """

        now = utc_now_iso()

        return {
            "word": clean_string(
                word
            ),

            "language": (
                clean_string(
                    language
                )
                or None
            ),

            "strong_number": (
                clean_string(
                    strong_number
                )
                or None
            ),

            "transliteration": (
                clean_string(
                    transliteration
                )
                or None
            ),

            "meaning": (
                clean_string(
                    meaning
                )
                or None
            ),

            "scriptures": normalize_list(
                scriptures
            ),

            "notes": normalize_list(
                notes
            ),

            "created_at": now,
            "updated_at": now,
        }

    # =====================================================
    # ADD ROOTWORD
    # =====================================================

    @staticmethod
    def add_rootword(
        word,
        language=None,
        strong_number=None,
        transliteration=None,
        meaning=None,
        scriptures=None,
        notes=None,
    ):
        """
        Create a new Biblical/Hebrew/Greek root-word record.

        Returns a stable response shape:

            {
                success: bool,
                message: str,
                data: {...}
            }
        """

        word = clean_string(
            word
        )

        language = clean_string(
            language
        ) or None

        strong_number = clean_string(
            strong_number
        ) or None

        transliteration = clean_string(
            transliteration
        ) or None

        meaning = clean_string(
            meaning
        ) or None

        scriptures = normalize_list(
            scriptures
        )

        notes = normalize_list(
            notes
        )

        # -------------------------------------------------
        # Validation
        # -------------------------------------------------

        if not word:

            return {
                "success": False,
                "message": (
                    "Root word is required."
                ),
                "data": None,
            }

        db = get_db()

        # -------------------------------------------------
        # Duplicate detection
        # -------------------------------------------------

        existing = (
            RootWordService._find_duplicate(
                db,
                word=word,
                strong_number=strong_number,
            )
        )

        if existing:

            existing = serialize_value(
                existing
            )

            return {
                "success": False,
                "duplicate": True,
                "message": (
                    "Root word already exists."
                ),
                "data": existing,
            }

        # -------------------------------------------------
        # Create document
        # -------------------------------------------------

        data = (
            RootWordService._build_document(
                word=word,
                language=language,
                strong_number=strong_number,
                transliteration=transliteration,
                meaning=meaning,
                scriptures=scriptures,
                notes=notes,
            )
        )

        try:

            result = db[
                COLLECTION_NAME
            ].insert_one(
                data
            )

        except Exception as exc:

            logger.exception(
                "Failed to create root word: %s",
                word,
            )

            return {
                "success": False,
                "message": (
                    "Failed to save root word."
                ),
                "data": None,
                "error": str(
                    exc
                ),
            }

        data["_id"] = str(
            result.inserted_id
        )

        logger.info(
            "Root word created: %s",
            word,
        )

        return {
            "success": True,
            "duplicate": False,
            "message": (
                "Root word created successfully."
            ),
            "data": serialize_value(
                data
            ),
        }

    # =====================================================
    # SEARCH
    # =====================================================

    @staticmethod
    def search(
        word: str,
        *,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ):
        """
        Search root words across:

            word
            meaning
            transliteration
            strong_number
            language
            scriptures
            notes

        Matching is case-insensitive.

        The search term is regex-escaped so user input cannot
        accidentally become a Mongo regular expression.
        """

        query = clean_string(
            word
        )

        if not query:

            return {
                "success": False,
                "message": (
                    "word is required."
                ),
                "query": "",
                "count": 0,
                "results": [],
                "data": [],
            }

        limit = normalize_limit(
            limit
        )

        escaped = re.escape(
            query
        )

        regex = {
            "$regex": escaped,
            "$options": "i",
        }

        mongo_query = {
            "$or": [
                {
                    "word": regex,
                },
                {
                    "meaning": regex,
                },
                {
                    "transliteration": regex,
                },
                {
                    "strong_number": regex,
                },
                {
                    "language": regex,
                },
                {
                    "scriptures": regex,
                },
                {
                    "notes": regex,
                },
            ]
        }

        try:

            db = get_db()

            cursor = (
                db[
                    COLLECTION_NAME
                ]
                .find(
                    mongo_query
                )
                .sort(
                    [
                        (
                            "word",
                            1,
                        )
                    ]
                )
                .limit(
                    limit
                )
            )

            results = [
                serialize_value(
                    item
                )
                for item in cursor
            ]

            logger.info(
                "Root word search query=%s results=%d",
                query,
                len(
                    results
                ),
            )

            return {
                "success": True,
                "message": (
                    "Root word search completed."
                ),
                "query": query,
                "count": len(
                    results
                ),
                "results": results,
                "data": results,
            }

        except Exception as exc:

            logger.exception(
                "Root word search failed for query=%s",
                query,
            )

            return {
                "success": False,
                "message": (
                    "Failed to search root words."
                ),
                "query": query,
                "count": 0,
                "results": [],
                "data": [],
                "error": str(
                    exc
                ),
            }

    # =====================================================
    # GET ONE BY WORD
    # =====================================================

    @staticmethod
    def get_by_word(
        word: str,
    ):
        """
        Retrieve one root word by exact case-insensitive word.
        """

        word = clean_string(
            word
        )

        if not word:
            return None

        db = get_db()

        result = db[
            COLLECTION_NAME
        ].find_one(
            {
                "word": {
                    "$regex": (
                        "^"
                        + re.escape(
                            word
                        )
                        + "$"
                    ),
                    "$options": "i",
                }
            }
        )

        return (
            serialize_value(
                result
            )
            if result
            else None
        )

    # =====================================================
    # GET BY STRONG NUMBER
    # =====================================================

    @staticmethod
    def get_by_strong_number(
        strong_number: str,
    ):
        """
        Retrieve one root word by exact Strong's number.
        """

        strong_number = clean_string(
            strong_number
        )

        if not strong_number:
            return None

        db = get_db()

        result = db[
            COLLECTION_NAME
        ].find_one(
            {
                "strong_number": {
                    "$regex": (
                        "^"
                        + re.escape(
                            strong_number
                        )
                        + "$"
                    ),
                    "$options": "i",
                }
            }
        )

        return (
            serialize_value(
                result
            )
            if result
            else None
        )

    # =====================================================
    # UPDATE
    # =====================================================

    @staticmethod
    def update_rootword(
        word: str,
        *,
        language=None,
        strong_number=None,
        transliteration=None,
        meaning=None,
        scriptures=None,
        notes=None,
    ):
        """
        Update an existing root word.

        The original word is used as the stable lookup key.
        """

        word = clean_string(
            word
        )

        if not word:

            return {
                "success": False,
                "message": (
                    "Root word is required."
                ),
                "data": None,
            }

        updates = {}

        if language is not None:
            updates["language"] = (
                clean_string(
                    language
                )
                or None
            )

        if strong_number is not None:
            updates["strong_number"] = (
                clean_string(
                    strong_number
                )
                or None
            )

        if transliteration is not None:
            updates["transliteration"] = (
                clean_string(
                    transliteration
                )
                or None
            )

        if meaning is not None:
            updates["meaning"] = (
                clean_string(
                    meaning
                )
                or None
            )

        if scriptures is not None:
            updates["scriptures"] = (
                normalize_list(
                    scriptures
                )
            )

        if notes is not None:
            updates["notes"] = (
                normalize_list(
                    notes
                )
            )

        if not updates:

            return {
                "success": False,
                "message": (
                    "No fields were provided for update."
                ),
                "data": None,
            }

        updates["updated_at"] = (
            utc_now_iso()
        )

        db = get_db()

        try:

            result = db[
                COLLECTION_NAME
            ].find_one_and_update(
                {
                    "word": {
                        "$regex": (
                            "^"
                            + re.escape(
                                word
                            )
                            + "$"
                        ),
                        "$options": "i",
                    }
                },
                {
                    "$set": updates
                },
                return_document=True,
            )

        except TypeError:

            # Compatibility fallback for PyMongo versions
            # where return_document is not accepted in the
            # current invocation style.
            from pymongo import ReturnDocument

            result = db[
                COLLECTION_NAME
            ].find_one_and_update(
                {
                    "word": {
                        "$regex": (
                            "^"
                            + re.escape(
                                word
                            )
                            + "$"
                        ),
                        "$options": "i",
                    }
                },
                {
                    "$set": updates
                },
                return_document=ReturnDocument.AFTER,
            )

        except Exception as exc:

            logger.exception(
                "Failed to update root word: %s",
                word,
            )

            return {
                "success": False,
                "message": (
                    "Failed to update root word."
                ),
                "data": None,
                "error": str(
                    exc
                ),
            }

        if not result:

            return {
                "success": False,
                "message": (
                    "Root word was not found."
                ),
                "data": None,
            }

        return {
            "success": True,
            "message": (
                "Root word updated successfully."
            ),
            "data": serialize_value(
                result
            ),
        }