# backend/study/study_service.py

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId

from backend.db import get_db


# =========================================================
# LOGGING
# =========================================================

logger = logging.getLogger(
    "revelacode.study.service"
)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

STUDY_PATH = os.path.join(
    BASE_DIR,
    "user_data",
    "study_materials",
)


# =========================================================
# CONSTANTS
# =========================================================

COLLECTION = "study_materials"

DEFAULT_LIMIT = 100

MAX_LIMIT = 500

DEFAULT_CATEGORIES = (
    "faith",
    "education",
)


# =========================================================
# SERIALIZATION
# =========================================================

def serialize_value(
    value: Any,
) -> Any:
    """
    Convert MongoDB/Python values into JSON-safe values.

    Handles:

        ObjectId
        datetime
        date
        dict
        list
        tuple
        primitive values
    """

    if value is None:
        return None

    if isinstance(
        value,
        ObjectId,
    ):
        return str(value)

    if isinstance(
        value,
        (
            datetime,
            date,
        ),
    ):
        return value.isoformat()

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key):
            serialize_value(item)
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
            serialize_value(item)
            for item in value
        ]

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    return str(
        value
    )


# =========================================================
# STRING HELPERS
# =========================================================

def clean_string(
    value: Any,
) -> str:
    """
    Normalize arbitrary input into a trimmed string.
    """

    if value is None:
        return ""

    return str(
        value
    ).strip()


def normalize_category(
    value: Any,
) -> Optional[str]:
    value = clean_string(
        value
    )

    return (
        value.lower()
        if value
        else None
    )


def normalize_subcategory(
    value: Any,
) -> Optional[str]:
    value = clean_string(
        value
    )

    return (
        value.lower()
        if value
        else None
    )


def normalize_material_type(
    value: Any,
) -> Optional[str]:
    value = clean_string(
        value
    )

    return (
        value.lower()
        if value
        else None
    )


# =========================================================
# LOCAL JSON HELPERS
# =========================================================

def _load_json_file(
    path: str,
) -> Any:
    """
    Load one JSON study file safely.
    """

    try:

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(
                file
            )

    except Exception as exc:

        logger.warning(
            "Unable to read Study JSON file %s: %s",
            path,
            exc,
        )

        return None


def _flatten_local_data(
    data: Any,
) -> List[Dict[str, Any]]:
    """
    Normalize several possible local JSON structures.

    Supported:

        { ...material... }

        [ ...materials... ]

        {
            "materials": [...]
        }

        {
            "data": [...]
        }
    """

    if isinstance(
        data,
        list,
    ):

        return [
            item
            for item in data
            if isinstance(
                item,
                dict,
            )
        ]

    if not isinstance(
        data,
        dict,
    ):
        return []

    for key in (
        "materials",
        "data",
        "items",
        "lessons",
    ):

        nested = data.get(
            key
        )

        if isinstance(
            nested,
            list,
        ):

            return [
                item
                for item in nested
                if isinstance(
                    item,
                    dict,
                )
            ]

    return [
        data
    ]


def _local_material_matches(
    material: Dict[str, Any],
    *,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    material_type: Optional[str] = None,
) -> bool:
    """
    Apply the same filters used by MongoDB.
    """

    if category:

        stored_category = normalize_category(
            material.get(
                "category"
            )
        )

        if stored_category != category:
            return False

    if subcategory:

        stored_subcategory = normalize_subcategory(
            material.get(
                "subcategory"
            )
        )

        if stored_subcategory != subcategory:
            return False

    if material_type:

        stored_type = normalize_material_type(
            material.get(
                "material_type"
            )
            or material.get(
                "file_type"
            )
        )

        if stored_type != material_type:
            return False

    return True


# =========================================================
# SEARCH HELPERS
# =========================================================

def _material_search_text(
    material: Dict[str, Any],
) -> str:
    """
    Build a searchable text representation.

    Includes:

        title
        content
        category
        subcategory
        material_type
        tags
        metadata
    """

    values: List[str] = []

    for key in (
        "title",
        "content",
        "category",
        "subcategory",
        "material_type",
        "file_type",
        "author",
    ):

        value = material.get(
            key
        )

        if value is not None:

            values.append(
                clean_string(
                    value
                )
            )

    tags = material.get(
        "tags",
        [],
    )

    if isinstance(
        tags,
        list,
    ):

        values.extend(
            clean_string(
                tag
            )
            for tag in tags
            if clean_string(
                tag
            )
        )

    metadata = material.get(
        "metadata",
        {},
    )

    if isinstance(
        metadata,
        dict,
    ):

        for value in metadata.values():

            if isinstance(
                value,
                (
                    str,
                    int,
                    float,
                ),
            ):

                values.append(
                    clean_string(
                        value
                    )
                )

    return " ".join(
        value
        for value in values
        if value
    )


def _local_search(
    materials: List[Dict[str, Any]],
    query: str,
) -> List[Dict[str, Any]]:
    """
    Case-insensitive local fallback search.
    """

    query = clean_string(
        query
    ).lower()

    if not query:
        return []

    results = []

    for material in materials:

        searchable = (
            _material_search_text(
                material
            )
            .lower()
        )

        if query in searchable:
            results.append(
                material
            )

    return results


# =========================================================
# MAIN SERVICE
# =========================================================

class StudyService:

    # =====================================================
    # COLLECTION
    # =====================================================

    @staticmethod
    def get_collection():
        """
        Return the canonical Study collection.
        """

        db = get_db()

        return db[
            COLLECTION
        ]

    # =====================================================
    # CATEGORIES
    # =====================================================

    @staticmethod
    def get_categories():
        """
        Return known Study categories.

        Static categories remain available even when the
        database is empty.

        Database categories are merged when available.
        """

        categories = set(
            DEFAULT_CATEGORIES
        )

        try:

            collection = (
                StudyService
                .get_collection()
            )

            values = collection.distinct(
                "category"
            )

            for value in values:

                normalized = normalize_category(
                    value
                )

                if normalized:
                    categories.add(
                        normalized
                    )

        except Exception as exc:

            logger.warning(
                "Unable to load Study categories: %s",
                exc,
            )

        return sorted(
            categories
        )

    # =====================================================
    # MATERIALS
    # =====================================================

    @staticmethod
    def get_materials(
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        file_type: Optional[str] = None,
        material_type: Optional[str] = None,
        page: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve Study materials.

        Compatibility:

            file_type
            material_type

        are both accepted.

        The canonical database field is:

            material_type

        Legacy documents containing:

            file_type

        are also supported.

        By default this method returns a list, preserving the
        original StudyService contract.
        """

        category = normalize_category(
            category
        )

        subcategory = normalize_subcategory(
            subcategory
        )

        resolved_type = normalize_material_type(
            material_type
            or file_type
        )

        query: Dict[str, Any] = {}

        # -------------------------------------------------
        # Category
        # -------------------------------------------------

        if category:

            query[
                "category"
            ] = category

        # -------------------------------------------------
        # Subcategory
        # -------------------------------------------------

        if subcategory:

            query[
                "subcategory"
            ] = subcategory

        # -------------------------------------------------
        # Material type
        #
        # Support current material_type and legacy
        # file_type records.
        # -------------------------------------------------

        if resolved_type:

            query[
                "$or"
            ] = [
                {
                    "material_type":
                        resolved_type
                },
                {
                    "file_type":
                        resolved_type
                },
            ]

        try:

            collection = (
                StudyService
                .get_collection()
            )

            cursor = (
                collection
                .find(query)
                .sort(
                    [
                        (
                            "created_at",
                            -1,
                        ),
                        (
                            "updated_at",
                            -1,
                        ),
                    ]
                )
            )

            # -------------------------------------------------
            # Optional pagination at service level.
            #
            # Existing callers that do not provide page/limit
            # still receive all materials.
            # -------------------------------------------------

            if (
                page is not None
                or limit is not None
            ):

                safe_page = (
                    max(
                        int(
                            page
                            or 1
                        ),
                        1,
                    )
                )

                safe_limit = (
                    min(
                        max(
                            int(
                                limit
                                or DEFAULT_LIMIT
                            ),
                            1,
                        ),
                        MAX_LIMIT,
                    )
                )

                skip = (
                    (
                        safe_page
                        - 1
                    )
                    * safe_limit
                )

                cursor = (
                    cursor
                    .skip(skip)
                    .limit(
                        safe_limit
                    )
                )

            materials = list(
                cursor
            )

            return [
                serialize_value(
                    material
                )
                for material in materials
            ]

        except Exception as exc:

            logger.exception(
                "MongoDB Study material query failed: %s",
                exc,
            )

            # -------------------------------------------------
            # Local fallback.
            # -------------------------------------------------

            return StudyService.load_local(
                category=category,
                subcategory=subcategory,
                material_type=resolved_type,
                page=page,
                limit=limit,
            )

    # =====================================================
    # LOCAL MATERIALS
    # =====================================================

    @staticmethod
    def load_local(
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        material_type: Optional[str] = None,
        page: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Load Study materials from the local filesystem.

        This is a fallback only. MongoDB remains the primary
        source of Study materials.
        """

        category = normalize_category(
            category
        )

        subcategory = normalize_subcategory(
            subcategory
        )

        material_type = normalize_material_type(
            material_type
        )

        if not os.path.exists(
            STUDY_PATH
        ):

            return []

        materials: List[
            Dict[str, Any]
        ] = []

        for root, _, files in os.walk(
            STUDY_PATH
        ):

            for filename in files:

                if not filename.lower().endswith(
                    ".json"
                ):
                    continue

                path = os.path.join(
                    root,
                    filename,
                )

                data = _load_json_file(
                    path
                )

                for material in _flatten_local_data(
                    data
                ):

                    if not _local_material_matches(
                        material,
                        category=category,
                        subcategory=subcategory,
                        material_type=material_type,
                    ):
                        continue

                    # -------------------------------------------------
                    # Ensure an ID exists when possible.
                    # -------------------------------------------------

                    if not material.get(
                        "id"
                    ):

                        candidate = (
                            material.get(
                                "_id"
                            )
                            or material.get(
                                "material_id"
                            )
                        )

                        if candidate:
                            material[
                                "id"
                            ] = str(
                                candidate
                            )

                    materials.append(
                        serialize_value(
                            material
                        )
                    )

        # -----------------------------------------------------
        # Stable ordering.
        # -----------------------------------------------------

        materials.sort(
            key=lambda item:
                str(
                    item.get(
                        "updated_at"
                        )
                    or item.get(
                        "created_at"
                    )
                    or item.get(
                        "title",
                        ""
                    )
                ),
            reverse=True,
        )

        # -----------------------------------------------------
        # Optional pagination.
        # -----------------------------------------------------

        if (
            page is not None
            or limit is not None
        ):

            safe_page = max(
                int(
                    page
                    or 1
                ),
                1,
            )

            safe_limit = min(
                max(
                    int(
                        limit
                        or DEFAULT_LIMIT
                    ),
                    1,
                ),
                MAX_LIMIT,
            )

            start = (
                (
                    safe_page
                    - 1
                )
                * safe_limit
            )

            end = (
                start
                + safe_limit
            )

            materials = materials[
                start:end
            ]

        return materials

    # =====================================================
    # SINGLE MATERIAL
    # =====================================================

    @staticmethod
    def get_material_by_id(
        material_id: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Find a material by:

            Mongo ObjectId
            custom UUID `id`
            legacy `material_id`
            local JSON ID
        """

        material_id = clean_string(
            material_id
        )

        if not material_id:
            return None

        try:

            collection = (
                StudyService
                .get_collection()
            )

            # -------------------------------------------------
            # ObjectId lookup.
            # -------------------------------------------------

            try:

                object_id = ObjectId(
                    material_id
                )

                material = (
                    collection
                    .find_one({
                        "_id":
                            object_id
                    })
                )

                if material:

                    return serialize_value(
                        material
                    )

            except (
                InvalidId,
                TypeError,
            ):
                pass

            # -------------------------------------------------
            # Custom IDs.
            # -------------------------------------------------

            material = (
                collection
                .find_one({
                    "$or": [
                        {
                            "id":
                                material_id
                        },
                        {
                            "material_id":
                                material_id
                        },
                    ]
                })
            )

            if material:

                return serialize_value(
                    material
                )

        except Exception as exc:

            logger.exception(
                "MongoDB Study material lookup failed: %s",
                exc,
            )

        # -----------------------------------------------------
        # Local fallback.
        # -----------------------------------------------------

        try:

            materials = (
                StudyService
                .load_local()
            )

            for material in materials:

                identifiers = {
                    clean_string(
                        material.get(
                            "id"
                        )
                    ),
                    clean_string(
                        material.get(
                            "_id"
                        )
                    ),
                    clean_string(
                        material.get(
                            "material_id"
                        )
                    ),
                }

                if material_id in identifiers:

                    return serialize_value(
                        material
                    )

        except Exception as exc:

            logger.exception(
                "Local Study material lookup failed: %s",
                exc,
            )

        return None

    # =====================================================
    # SEARCH
    # =====================================================

    @staticmethod
    def search_materials(
        query: str,
        *,
        limit: int = MAX_LIMIT,
    ) -> List[Dict[str, Any]]:
        """
        Search Study materials safely.

        Searches:

            title
            content
            tags
            category
            subcategory
            author
            material_type
            metadata fields
        """

        query = clean_string(
            query
        )

        if not query:
            return []

        safe_limit = min(
            max(
                int(
                    limit
                ),
                1,
            ),
            MAX_LIMIT,
        )

        # -----------------------------------------------------
        # Escape regex metacharacters so user input cannot
        # accidentally become an expensive/malformed regex.
        # -----------------------------------------------------

        pattern = re.escape(
            query
        )

        mongo_query = {
            "$or": [
                {
                    "title": {
                        "$regex":
                            pattern,
                        "$options":
                            "i",
                    }
                },
                {
                    "content": {
                        "$regex":
                            pattern,
                        "$options":
                            "i",
                    }
                },
                {
                    "tags": {
                        "$regex":
                            pattern,
                        "$options":
                            "i",
                    }
                },
                {
                    "category": {
                        "$regex":
                            pattern,
                        "$options":
                            "i",
                    }
                },
                {
                    "subcategory": {
                        "$regex":
                            pattern,
                        "$options":
                            "i",
                    }
                },
                {
                    "material_type": {
                        "$regex":
                            pattern,
                        "$options":
                            "i",
                    }
                },
                {
                    "file_type": {
                        "$regex":
                            pattern,
                        "$options":
                            "i",
                    }
                },
                {
                    "author": {
                        "$regex":
                            pattern,
                        "$options":
                            "i",
                    }
                },
                {
                    "metadata.lesson_title": {
                        "$regex":
                            pattern,
                        "$options":
                            "i",
                    }
                },
                {
                    "metadata.memory_text": {
                        "$regex":
                            pattern,
                        "$options":
                            "i",
                    }
                },
                {
                    "metadata.day": {
                        "$regex":
                            pattern,
                        "$options":
                            "i",
                    }
                },
                {
                    "metadata.book_title": {
                        "$regex":
                            pattern,
                        "$options":
                            "i",
                    }
                },
            ]
        }

        try:

            collection = (
                StudyService
                .get_collection()
            )

            results = list(
                collection
                .find(
                    mongo_query
                )
                .sort(
                    [
                        (
                            "created_at",
                            -1,
                        ),
                        (
                            "updated_at",
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
                    item
                )
                for item in results
            ]

        except Exception as exc:

            logger.exception(
                "MongoDB Study search failed: %s",
                exc,
            )

            # -------------------------------------------------
            # Local fallback search.
            # -------------------------------------------------

            try:

                materials = (
                    StudyService
                    .load_local()
                )

                results = _local_search(
                    materials,
                    query,
                )

                return [
                    serialize_value(
                        item
                    )
                    for item in results[
                        :safe_limit
                    ]
                ]

            except Exception as fallback_exc:

                logger.exception(
                    "Local Study search failed: %s",
                    fallback_exc,
                )

                return []

    # =====================================================
    # EXISTS
    # =====================================================

    @staticmethod
    def material_exists(
        material_id: Any,
    ) -> bool:
        """
        Lightweight material existence check.
        """

        return (
            StudyService
            .get_material_by_id(
                material_id
            )
            is not None
        )

    # =====================================================
    # COUNTS / STATISTICS
    # =====================================================

    @staticmethod
    def get_stats() -> Dict[str, Any]:
        """
        Return basic Study library statistics.

        Useful for:

            Study dashboard
            Admin dashboard
            diagnostics
        """

        try:

            collection = (
                StudyService
                .get_collection()
            )

            total = collection.count_documents(
                {}
            )

            category_counts = {}

            for category in (
                collection
                .distinct(
                    "category"
                )
            ):

                normalized = normalize_category(
                    category
                )

                if not normalized:
                    continue

                category_counts[
                    normalized
                ] = collection.count_documents({
                    "category":
                        category
                })

            material_type_counts = {}

            for material_type in (
                collection
                .distinct(
                    "material_type"
                )
            ):

                normalized = normalize_material_type(
                    material_type
                )

                if not normalized:
                    continue

                material_type_counts[
                    normalized
                ] = collection.count_documents({
                    "material_type":
                        material_type
                })

            return {
                "success": True,
                "total_materials":
                    total,
                "categories":
                    category_counts,
                "material_types":
                    material_type_counts,
                "storage":
                    "mongodb",
            }

        except Exception as exc:

            logger.exception(
                "Unable to build Study statistics: %s",
                exc,
            )

            local_materials = (
                StudyService
                .load_local()
            )

            return {
                "success": True,
                "total_materials":
                    len(
                        local_materials
                    ),
                "categories": {},
                "material_types": {},
                "storage":
                    "local_fallback",
            }
