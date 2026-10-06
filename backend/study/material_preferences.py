# backend/study/material_preferences.py

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from backend.db import get_db


# =========================================================
# LOGGING
# =========================================================

logger = logging.getLogger(
    "revelacode.study.material_preferences"
)


# =========================================================
# CONSTANTS
# =========================================================

PREFERENCES_COLLECTION = "study_preferences"
MATERIALS_COLLECTION = "study_materials"

MAX_PREFERENCES = 30
MAX_PREFERENCE_LENGTH = 100

DEFAULT_RECOMMENDATION_LIMIT = 50
MAX_RECOMMENDATION_LIMIT = 200


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


def normalize_preference(
    value: Any,
) -> str:
    """
    Canonical representation used for matching.

    Preferences remain human-readable, but matching is
    case-insensitive.
    """

    return clean_string(
        value
    ).casefold()


def normalize_preferences(
    preferences: Any,
) -> list[str]:
    """
    Normalize a preference collection.

    Supports:

        ["Faith", "SDA", "Bible"]

    and:

        "Faith,SDA,Bible"
    """

    if preferences is None:
        return []

    if isinstance(
        preferences,
        str,
    ):

        preferences = (
            preferences.split(",")
        )

    if not isinstance(
        preferences,
        Iterable,
    ):

        return []

    result = []
    seen = set()

    for preference in preferences:

        value = clean_string(
            preference
        )

        if not value:
            continue

        if len(value) > MAX_PREFERENCE_LENGTH:

            value = value[
                :MAX_PREFERENCE_LENGTH
            ].strip()

        normalized = (
            normalize_preference(
                value
            )
        )

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        result.append(
            value
        )

        if len(result) >= MAX_PREFERENCES:
            break

    return result


def serialize_value(
    value: Any,
) -> Any:
    """
    Convert Mongo/Python values into JSON-safe values.
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

    if value.__class__.__name__ == "ObjectId":

        return str(
            value
        )

    return value


def normalize_limit(
    value: Any,
) -> int:
    """
    Normalize recommendation result count.
    """

    try:

        limit = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return DEFAULT_RECOMMENDATION_LIMIT

    return min(
        max(
            limit,
            1,
        ),
        MAX_RECOMMENDATION_LIMIT,
    )


def value_matches(
    value: Any,
    preference_keys: set[str],
) -> bool:
    """
    Determine whether a scalar or collection value matches
    one of the user's normalized preferences.
    """

    if value is None:
        return False

    if isinstance(
        value,
        (list, tuple, set),
    ):

        for item in value:

            if normalize_preference(
                item
            ) in preference_keys:

                return True

        return False

    return (
        normalize_preference(
            value
        )
        in preference_keys
    )


# =========================================================
# MATERIAL PREFERENCE SERVICE
# =========================================================

class MaterialPreferences:

    COLLECTION = PREFERENCES_COLLECTION

    # =====================================================
    # INDEX
    # =====================================================

    @staticmethod
    def ensure_indexes() -> None:
        """
        Ensure one preference document exists per user.
        """

        try:

            db = get_db()

            db[
                PREFERENCES_COLLECTION
            ].create_index(
                "user_id",
                unique=True,
                name="study_preferences_user_unique",
            )

        except Exception as exc:

            logger.warning(
                "Could not ensure Study preference index: %s",
                exc,
            )

    # =====================================================
    # VALIDATE USER
    # =====================================================

    @staticmethod
    def normalize_user_id(
        user_id: Any,
    ) -> str:
        """
        Normalize a user identifier.
        """

        return clean_string(
            user_id
        )

    # =====================================================
    # SAVE PREFERENCES
    # =====================================================

    @classmethod
    def save_preferences(
        cls,
        user_id,
        preferences,
    ):
        """
        Save a user's Study preferences.

        The method intentionally returns the same simple
        response style used by the existing Study route.
        """

        user_id = cls.normalize_user_id(
            user_id
        )

        if not user_id:

            return {
                "success": False,
                "message": (
                    "user_id is required."
                ),
            }

        cleaned_preferences = (
            normalize_preferences(
                preferences
            )
        )

        cls.ensure_indexes()

        db = get_db()

        now = utc_now_iso()

        try:

            db[
                PREFERENCES_COLLECTION
            ].update_one(
                {
                    "user_id":
                        user_id
                },
                {
                    "$set": {
                        "preferences":
                            cleaned_preferences,
                        "updated_at":
                            now,
                    },
                    "$setOnInsert": {
                        "user_id":
                            user_id,
                        "created_at":
                            now,
                    },
                },
                upsert=True,
            )

            return {
                "success": True,
                "message": (
                    "Preferences saved successfully."
                ),
                "user_id": user_id,
                "preferences":
                    cleaned_preferences,
                "count": len(
                    cleaned_preferences
                ),
            }

        except Exception as exc:

            logger.exception(
                "Failed to save Study preferences for user=%s",
                user_id,
            )

            return {
                "success": False,
                "message": (
                    "Failed to save Study preferences."
                ),
            }

    # =====================================================
    # GET PREFERENCES
    # =====================================================

    @classmethod
    def get_preferences(
        cls,
        user_id,
    ):
        """
        Retrieve a user's preferences.

        Returns a list for compatibility with existing routes.
        """

        user_id = cls.normalize_user_id(
            user_id
        )

        if not user_id:
            return []

        try:

            db = get_db()

            data = db[
                PREFERENCES_COLLECTION
            ].find_one(
                {
                    "user_id":
                        user_id
                }
            )

            if not data:
                return []

            return normalize_preferences(
                data.get(
                    "preferences",
                    [],
                )
            )

        except Exception as exc:

            logger.exception(
                "Failed to load Study preferences for user=%s",
                user_id,
            )

            return []

    # =====================================================
    # GET PREFERENCE DOCUMENT
    # =====================================================

    @classmethod
    def get_preferences_document(
        cls,
        user_id,
    ) -> Optional[dict]:
        """
        Retrieve the complete preference document.

        Useful for admin/diagnostic views while keeping
        get_preferences() backward-compatible.
        """

        user_id = cls.normalize_user_id(
            user_id
        )

        if not user_id:
            return None

        try:

            db = get_db()

            data = db[
                PREFERENCES_COLLECTION
            ].find_one(
                {
                    "user_id":
                        user_id
                }
            )

            return (
                serialize_value(
                    data
                )
                if data
                else None
            )

        except Exception as exc:

            logger.exception(
                "Failed to load preference document for user=%s",
                user_id,
            )

            return None

    # =====================================================
    # BUILD SEARCH QUERY
    # =====================================================

    @classmethod
    def _build_material_query(
        cls,
        preferences: list[str],
    ) -> dict:
        """
        Build a case-insensitive MongoDB candidate query.

        Ranking is still performed in Python so different
        preference matches can receive different weights.
        """

        regex_conditions = []

        for preference in preferences:

            pattern = re.escape(
                preference
            )

            regex = {
                "$regex":
                    pattern,
                "$options":
                    "i",
            }

            regex_conditions.extend(
                [
                    {
                        "category":
                            regex
                    },
                    {
                        "subcategory":
                            regex
                    },
                    {
                        "material_type":
                            regex
                    },
                    {
                        "file_type":
                            regex
                    },
                    {
                        "tags":
                            regex
                    },
                    {
                        "title":
                            regex
                    },
                ]
            )

        if not regex_conditions:

            return {}

        return {
            "$or":
                regex_conditions
        }

    # =====================================================
    # SCORE MATERIAL
    # =====================================================

    @classmethod
    def _score_material(
        cls,
        material: dict,
        preference_keys: set[str],
    ) -> tuple[int, list[str]]:
        """
        Calculate a recommendation score.

        Weighting:

            category       +6
            subcategory    +5
            material_type  +3
            tags           +4 each
            title          +3
            author         +1
            metadata       +1
        """

        score = 0
        reasons = []

        category = material.get(
            "category"
        )

        if value_matches(
            category,
            preference_keys,
        ):

            score += 6
            reasons.append(
                "category"
            )

        subcategory = material.get(
            "subcategory"
        )

        if value_matches(
            subcategory,
            preference_keys,
        ):

            score += 5
            reasons.append(
                "subcategory"
            )

        material_type = (
            material.get(
                "material_type"
            )
            or material.get(
                "file_type"
            )
        )

        if value_matches(
            material_type,
            preference_keys,
        ):

            score += 3
            reasons.append(
                "material type"
            )

        tags = material.get(
            "tags",
            [],
        )

        if not isinstance(
            tags,
            list,
        ):

            tags = []

        matched_tags = []

        for tag in tags:

            normalized_tag = (
                normalize_preference(
                    tag
                )
            )

            if (
                normalized_tag
                in preference_keys
            ):

                matched_tags.append(
                    clean_string(
                        tag
                    )
                )

        if matched_tags:

            score += (
                4
                * len(
                    set(
                        normalize_preference(
                            tag
                        )
                        for tag in matched_tags
                    )
                )
            )

            reasons.append(
                "tags"
            )

        title = clean_string(
            material.get(
                "title"
            )
        )

        if title:

            normalized_title = (
                normalize_preference(
                    title
                )
            )

            title_match = any(
                pref in normalized_title
                for pref in preference_keys
            )

            if title_match:

                score += 3
                reasons.append(
                    "title"
                )

        author = material.get(
            "author"
        )

        if value_matches(
            author,
            preference_keys,
        ):

            score += 1
            reasons.append(
                "author"
            )

        metadata = material.get(
            "metadata",
            {},
        )

        if isinstance(
            metadata,
            dict,
        ):

            metadata_text = " ".join(
                clean_string(
                    value
                )
                for value in metadata.values()
                if isinstance(
                    value,
                    (
                        str,
                        int,
                        float,
                    ),
                )
            ).casefold()

            metadata_match = any(
                preference in metadata_text
                for preference in preference_keys
            )

            if metadata_match:

                score += 1
                reasons.append(
                    "metadata"
                )

        # Remove duplicate reasons while keeping order.
        reasons = list(
            dict.fromkeys(
                reasons
            )
        )

        return (
            score,
            reasons,
        )

    # =====================================================
    # RECOMMENDATIONS
    # =====================================================

    @classmethod
    def get_recommended_materials(
        cls,
        user_id,
        *,
        limit: int = DEFAULT_RECOMMENDATION_LIMIT,
    ):
        """
        Return personalized Study recommendations.

        Returns [] when the user has no preferences, preserving
        the existing route behavior.

        Each recommended material receives:

            recommendation_score
            recommendation_reasons
        """

        user_id = cls.normalize_user_id(
            user_id
        )

        if not user_id:
            return []

        preferences = cls.get_preferences(
            user_id
        )

        if not preferences:
            return []

        safe_limit = normalize_limit(
            limit
        )

        preference_keys = {
            normalize_preference(
                preference
            )
            for preference in preferences
            if normalize_preference(
                preference
            )
        }

        if not preference_keys:
            return []

        try:

            db = get_db()

            query = (
                cls._build_material_query(
                    preferences
                )
            )

            if not query:
                return []

            # -------------------------------------------------
            # Fetch a larger candidate pool than the final
            # response so ranking can work effectively.
            # -------------------------------------------------

            candidate_limit = min(
                safe_limit * 4,
                MAX_RECOMMENDATION_LIMIT,
            )

            materials = list(
                db[
                    MATERIALS_COLLECTION
                ]
                .find(
                    query
                )
                .sort(
                    [
                        (
                            "updated_at",
                            -1,
                        ),
                        (
                            "created_at",
                            -1,
                        ),
                    ]
                )
                .limit(
                    candidate_limit
                )
            )

            ranked = []

            for material in materials:

                score, reasons = (
                    cls._score_material(
                        material,
                        preference_keys,
                    )
                )

                if score <= 0:
                    continue

                material[
                    "_id"
                ] = str(
                    material[
                        "_id"
                    ]
                )

                material[
                    "recommendation_score"
                ] = score

                material[
                    "recommendation_reasons"
                ] = reasons

                ranked.append(
                    material
                )

            # -------------------------------------------------
            # Highest score first.
            #
            # Updated materials win ties.
            # -------------------------------------------------

            def rank_key(
                item: dict,
            ):
                return (
                    int(
                        item.get(
                            "recommendation_score",
                            0,
                        )
                    ),
                    clean_string(
                        item.get(
                            "updated_at"
                        )
                    ),
                    clean_string(
                        item.get(
                            "created_at"
                        )
                    ),
                )

            ranked.sort(
                key=rank_key,
                reverse=True,
            )

            return [
                serialize_value(
                    item
                )
                for item in ranked[
                    :safe_limit
                ]
            ]

        except Exception as exc:

            logger.exception(
                "Failed to generate Study recommendations for user=%s",
                user_id,
            )

            return []

    # =====================================================
    # RECOMMENDATION SUMMARY
    # =====================================================

    @classmethod
    def get_recommendation_summary(
        cls,
        user_id,
    ):
        """
        Return recommendation information useful for a
        dashboard without exposing the entire material list.
        """

        user_id = cls.normalize_user_id(
            user_id
        )

        preferences = cls.get_preferences(
            user_id
        )

        recommendations = (
            cls.get_recommended_materials(
                user_id,
                limit=10,
            )
        )

        return {
            "success": True,
            "user_id": user_id,
            "preferences":
                preferences,
            "preference_count":
                len(
                    preferences
                ),
            "recommendation_count":
                len(
                    recommendations
                ),
            "materials":
                recommendations,
        }