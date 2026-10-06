# backend/study/ai_context_service.py

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from backend.services.ai_router import ask_ai
from backend.study.study_service import StudyService


# =========================================================
# LOGGING
# =========================================================

logger = logging.getLogger(
    "revelacode.study.ai_context"
)


# =========================================================
# CONSTANTS
# =========================================================

DEFAULT_MAX_CONTEXT_CHARACTERS = 60_000

try:
    MAX_CONTEXT_CHARACTERS = max(
        5_000,
        int(
            os.getenv(
                "STUDY_AI_MAX_CONTEXT_CHARS",
                str(
                    DEFAULT_MAX_CONTEXT_CHARACTERS
                ),
            )
        ),
    )
except (
    TypeError,
    ValueError,
):
    MAX_CONTEXT_CHARACTERS = (
        DEFAULT_MAX_CONTEXT_CHARACTERS
    )


# =========================================================
# HELPERS
# =========================================================

def clean_string(
    value: Any,
) -> str:
    """
    Normalize arbitrary values into clean strings.
    """

    if value is None:
        return ""

    return str(
        value
    ).strip()


def extract_ai_answer(
    value: Any,
) -> str:
    """
    Normalize different RevelaAI response shapes into one
    answer string.

    Supported examples:

        "answer text"

        {
            "answer": "..."
        }

        {
            "response": "..."
        }

        {
            "data": {
                "answer": "..."
            }
        }

        {
            "result": {
                "text": "..."
            }
        }
    """

    if value is None:
        return ""

    if isinstance(
        value,
        str,
    ):
        return value.strip()

    if isinstance(
        value,
        dict,
    ):

        # -------------------------------------------------
        # Common direct response fields.
        # -------------------------------------------------

        for key in (
            "answer",
            "response",
            "content",
            "text",
            "output",
            "message",
        ):

            candidate = value.get(
                key
            )

            if isinstance(
                candidate,
                str,
            ) and candidate.strip():

                return candidate.strip()

        # -------------------------------------------------
        # Common nested response containers.
        # -------------------------------------------------

        for key in (
            "data",
            "result",
            "response",
        ):

            nested = value.get(
                key
            )

            if isinstance(
                nested,
                (
                    dict,
                    list,
                    str,
                ),
            ):

                answer = extract_ai_answer(
                    nested
                )

                if answer:
                    return answer

        return ""

    if isinstance(
        value,
        list,
    ):

        for item in value:

            answer = extract_ai_answer(
                item
            )

            if answer:
                return answer

    return clean_string(
        value
    )


def build_study_excerpt(
    content: str,
) -> tuple[str, bool]:
    """
    Protect the AI request from an excessively large lesson.

    Returns:

        excerpt
        truncated
    """

    content = clean_string(
        content
    )

    if not content:
        return (
            "",
            False,
        )

    if len(content) <= MAX_CONTEXT_CHARACTERS:

        return (
            content,
            False,
        )

    return (
        content[
            :MAX_CONTEXT_CHARACTERS
        ].rstrip()
        + "\n\n[Study material truncated for AI context length.]",
        True,
    )


def build_ai_context(
    material: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the canonical context sent to RevelaAI.

    Includes the Study material metadata and the material
    content itself.
    """

    raw_content = clean_string(
        material.get(
            "content",
            "",
        )
    )

    content, truncated = (
        build_study_excerpt(
            raw_content
        )
    )

    metadata = material.get(
        "metadata",
        {},
    )

    if not isinstance(
        metadata,
        dict,
    ):
        metadata = {}

    return {
        "title": clean_string(
            material.get(
                "title"
            )
        ),

        "category": clean_string(
            material.get(
                "category"
            )
        ),

        "subcategory": clean_string(
            material.get(
                "subcategory"
            )
        ),

        "material_type": clean_string(
            material.get(
                "material_type"
            )
            or material.get(
                "file_type"
            )
        ),

        "year": material.get(
            "year"
        ),

        "author": clean_string(
            material.get(
                "author"
            )
        ),

        "tags": material.get(
            "tags",
            [],
        ),

        "metadata": metadata,

        "content": content,

        "content_truncated": truncated,

        "original_content_length": len(
            raw_content
        ),
    }


def fallback_answer(
    material: Dict[str, Any],
    ai_response: Any,
) -> str:
    """
    Provide a transparent degraded-mode answer when the AI
    service is unavailable.

    This does NOT pretend that an AI answer was generated.
    """

    title = (
        clean_string(
            material.get(
                "title"
            )
        )
        or "this study material"
    )

    message = ""

    if isinstance(
        ai_response,
        dict,
    ):

        message = clean_string(
            ai_response.get(
                "message"
            )
        )

    excerpt = clean_string(
        material.get(
            "content",
            "",
        )
    )

    if excerpt:

        excerpt = excerpt[
            :500
        ].strip()

    if message:

        opening = (
            f"RevelaAI is temporarily unavailable: "
            f"{message}"
        )

    else:

        opening = (
            "RevelaAI is temporarily unavailable right now."
        )

    if excerpt:

        return (
            f"{opening}\n\n"
            f"Relevant content from {title}:\n"
            f"{excerpt}"
        )

    return opening


# =========================================================
# AI CONTEXT SERVICE
# =========================================================

class AIContextService:

    # =====================================================
    # ASK ABOUT MATERIAL
    # =====================================================

    @staticmethod
    def ask_material_ai(
        material_id: Any,
        user_question: Any,
    ) -> Dict[str, Any]:
        """
        Ask RevelaAI a question about one Study material.

        Returns a stable response shape suitable for the
        Study API and frontend.

        Example:

            {
                "success": True,
                "material_id": "...",
                "material_title": "...",
                "question": "...",
                "answer": "..."
            }
        """

        material_id = clean_string(
            material_id
        )

        question = clean_string(
            user_question
        )

        # -------------------------------------------------
        # Validate request
        # -------------------------------------------------

        if not material_id:

            return {
                "success": False,
                "message": (
                    "Study material ID is required."
                ),
            }

        if not question:

            return {
                "success": False,
                "message": (
                    "Study question is required."
                ),
            }

        # -------------------------------------------------
        # Load material
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
                "Failed to load Study material for AI: %s",
                material_id,
            )

            return {
                "success": False,
                "message": (
                    "Unable to load study material."
                ),
            }

        if not material:

            return {
                "success": False,
                "message": (
                    "Study material not found."
                ),
            }

        if not isinstance(
            material,
            dict,
        ):

            logger.error(
                "Unexpected Study material type for %s: %s",
                material_id,
                type(material).__name__,
            )

            return {
                "success": False,
                "message": (
                    "Study material has an invalid format."
                ),
            }

        # -------------------------------------------------
        # Validate lesson content
        # -------------------------------------------------

        lesson_content = clean_string(
            material.get(
                "content",
                "",
            )
        )

        if not lesson_content:

            return {
                "success": False,
                "message": (
                    "This study material does not contain "
                    "readable content for AI assistance."
                ),
                "material_id": material_id,
                "material_title": clean_string(
                    material.get(
                        "title"
                    )
                ),
                "question": question,
            }

        # -------------------------------------------------
        # Build context
        # -------------------------------------------------

        context = build_ai_context(
            material
        )

        # -------------------------------------------------
        # AI request
        # -------------------------------------------------

        try:

            ai_response = ask_ai(
                prompt=question,
                domain="study",
                context=context,
            )

        except Exception as exc:

            logger.exception(
                "Study AI request failed for material=%s",
                material_id,
            )

            return {
                "success": False,
                "message": (
                    "Study AI request could not be completed."
                ),
                "material_id": material_id,
                "material_title": clean_string(
                    material.get(
                        "title"
                    )
                ),
                "question": question,
            }

        # -------------------------------------------------
        # Detect degraded/fallback AI response
        # -------------------------------------------------

        is_fallback = (
            isinstance(
                ai_response,
                dict,
            )
            and bool(
                ai_response.get(
                    "fallback",
                    False,
                )
            )
        )

        if is_fallback:

            answer = fallback_answer(
                material,
                ai_response,
            )

            return {
                "success": True,
                "degraded": True,
                "ai_available": False,
                "fallback": True,
                "material_id": material_id,
                "material_title": clean_string(
                    material.get(
                        "title"
                    )
                ),
                "question": question,
                "answer": answer,
            }

        # -------------------------------------------------
        # Normalize actual AI answer
        # -------------------------------------------------

        answer = extract_ai_answer(
            ai_response
        )

        if not answer:

            logger.warning(
                "RevelaAI returned no usable answer for material=%s",
                material_id,
            )

            return {
                "success": False,
                "message": (
                    "RevelaAI returned an empty response."
                ),
                "material_id": material_id,
                "material_title": clean_string(
                    material.get(
                        "title"
                    )
                ),
                "question": question,
            }

        # -------------------------------------------------
        # Successful response
        # -------------------------------------------------

        return {
            "success": True,
            "degraded": False,
            "ai_available": True,
            "fallback": False,
            "material_id": material_id,
            "material_title": clean_string(
                material.get(
                    "title"
                )
            ),
            "category": clean_string(
                material.get(
                    "category"
                )
            ),
            "subcategory": clean_string(
                material.get(
                    "subcategory"
                )
            ),
            "question": question,
            "answer": answer,
        }