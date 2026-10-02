"""
RevelaCode Platform Knowledge

Public, non-sensitive knowledge exposed to RevelaAI.

This module intentionally contains:
    - platform identity
    - public capabilities
    - public hubs
    - official public links
    - public legal-document metadata/content

It MUST NOT contain:
    - JWT secrets
    - service keys
    - API keys
    - passwords
    - private user records
    - database credentials
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


# =========================================================
# TIME
# =========================================================

def now_utc() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


# =========================================================
# PUBLIC URL HELPERS
# =========================================================

def public_url(
    env_name: str,
    fallback: str,
) -> str:
    return (
        os.getenv(
            env_name,
            fallback,
        )
        .strip()
        .rstrip("/")
    )


# =========================================================
# PLATFORM MANIFEST
# =========================================================

def get_platform_manifest() -> dict[str, Any]:
    """
    Return the canonical public RevelaCode platform manifest.

    This is platform knowledge, not user-specific context.
    """

    revelacode_url = public_url(
        "REVELACODE_PUBLIC_URL",
        "https://revelacode-frontend.onrender.com",
    )

    revelacode_backend_url = public_url(
        "REVELACODE_BACKEND_PUBLIC_URL",
        "https://revelacode-backend.onrender.com",
    )

    revelaai_url = public_url(
        "REVELAAI_PUBLIC_URL",
        "https://revelaai.onrender.com",
    )

    github_frontend = (
        os.getenv(
            "REVELACODE_GITHUB_FRONTEND",
            "https://github.com/musombi123/RevelaCode-Frontend",
        )
        .strip()
    )

    github_backend = (
        os.getenv(
            "REVELACODE_GITHUB_BACKEND",
            "https://github.com/musombi123/RevelaCode-Backend",
        )
        .strip()
    )

    github_ai = (
        os.getenv(
            "REVELAAI_GITHUB",
            "https://github.com/musombi123/RevelaAI",
        )
        .strip()
    )

    public_docs = (
        os.getenv(
            "REVELACODE_DOCS_URL",
            "https://musombiwilliam.github.io/",
        )
        .strip()
    )

    return {
        "source": "revelacode_platform",
        "source_layer": "platform_knowledge",
        "retrieved_at": now_utc(),

        "identity": {
            "platform": "RevelaCode",
            "ai": "RevelaAI",
            "ecosystem": "Jumuiya",
            "description": (
                "RevelaCode is a technology platform with "
                "RevelaAI as its intelligence layer and "
                "Jumuiya as its connected ecosystem."
            ),
        },

        "architecture": {
            "platform_layer": "RevelaCode Backend",
            "intelligence_layer": "RevelaAI",
            "ecosystem": "Jumuiya",
            "principle": (
                "One RevelaCode platform with connected "
                "ecosystem hubs and an integrated AI layer."
            ),
        },

        "hubs": {
            "biashara": {
                "name": "Biashara",
                "supported": True,
                "description": (
                    "Business operations, marketplace, "
                    "products, sales, customers, inventory, "
                    "expenses and business intelligence."
                ),
            },

            "shamba": {
                "name": "Shamba",
                "supported": True,
                "description": (
                    "Agricultural and farm intelligence "
                    "including crops, farm planning, "
                    "production and agricultural analysis."
                ),
            },

            "elimu": {
                "name": "Elimu",
                "supported": True,
                "description": (
                    "Education and learning support for "
                    "students, teachers and schools."
                ),
            },

            "community": {
                "name": "Community",
                "supported": True,
                "description": (
                    "Community communication, discussions, "
                    "groups and authorized social interaction."
                ),
            },
        },

        "capabilities": {
            "general_assistance": {
                "supported": True,
                "runtime_status": "available",
            },

            "programming": {
                "supported": True,
                "runtime_status": "available",
            },

            "education": {
                "supported": True,
                "runtime_status": "available",
            },

            "scripture_theology": {
                "supported": True,
                "runtime_status": "available",
            },

            "creative_work": {
                "supported": True,
                "runtime_status": "available",
            },

            "online_research": {
                "supported": True,
                "runtime_status": "connected",
                "description": (
                    "RevelaAI can use its online research "
                    "subsystem when a request requires current "
                    "or external information."
                ),
            },

            "image_generation": {
                "supported": True,
                "runtime_status": "available",
                "provider": "Hugging Face",
                "model": (
                    "black-forest-labs/FLUX.1-schnell"
                ),
                "endpoint": "/ai",
            },

            "pdf_processing": {
                "supported": True,
                "runtime_status": "available",
                "processor": "PyMuPDF",
                "endpoint": "/ai",
            },

            "voice": {
                "supported": True,
                "runtime_status": "available",
                "speech_recognition": {
                    "provider": "Hugging Face",
                    "model": "openai/whisper-large-v3",
                },
                "text_to_speech": {
                    "provider": "Hugging Face",
                    "model": "hexgrad/Kokoro-82M",
                },
                "endpoint": "/voice",
            },

            "biashara_intelligence": {
                "supported": True,
                "runtime_status": "integrated",
                "operations": [
                    "market_analysis",
                    "market_forecast",
                    "product_forecast",
                    "market_trends",
                    "economic_indicators",
                    "business_performance_analysis",
                    "market_recommendations",
                ],
                "authorization": (
                    "Personalized operations require an "
                    "authenticated RevelaCode user."
                ),
            },

            "shamba_intelligence": {
                "supported": True,
                "runtime_status": "integrated",
                "operations": [
                    "crop_suitability",
                    "production_planning",
                    "yield_analysis",
                    "farm_risk_analysis",
                    "seasonal_planning",
                ],
                "authorization": (
                    "Farm-specific intelligence requires "
                    "authenticated RevelaCode ecosystem context."
                ),
            },

            "platform_context": {
                "supported": True,
                "runtime_status": "connected",
                "authorization": (
                    "Personalized platform data requires an "
                    "authenticated RevelaCode user."
                ),
            },
        },

        "public_links": {
            "revelacode": revelacode_url,
            "revelacode_backend": revelacode_backend_url,
            "revelaai": revelaai_url,

            "github_frontend": github_frontend,
            "github_backend": github_backend,
            "github_revelaai": github_ai,

            "documentation": public_docs,

            "privacy_policy": (
                f"{revelacode_backend_url}"
                "/api/legal/privacy"
            ),

            "terms_of_service": (
                f"{revelacode_backend_url}"
                "/api/legal/terms"
            ),
        },

        "legal_documents": {
            "privacy": {
                "available": True,
                "url": (
                    f"{revelacode_backend_url}"
                    "/api/legal/privacy"
                ),
            },

            "terms": {
                "available": True,
                "url": (
                    f"{revelacode_backend_url}"
                    "/api/legal/terms"
                ),
            },
        },

        "knowledge_rules": [
            (
                "Platform capability support must not be "
                "confused with execution of a capability "
                "during the current request."
            ),
            (
                "A capability may be supported even when "
                "the current request did not invoke it."
            ),
            (
                "Personalized platform data requires "
                "authenticated user context."
            ),
            (
                "Public platform information may be shared "
                "when relevant to the user's request."
            ),
            (
                "Official RevelaCode links may be provided "
                "when the user asks about RevelaCode, "
                "RevelaAI, documentation or legal documents."
            ),
        ],
    }


# =========================================================
# LEGAL DOCUMENTS
# =========================================================

def get_public_legal_document(
    document_type: str,
) -> dict[str, Any]:

    normalized = (
        str(
            document_type or ""
        )
        .strip()
        .lower()
    )

    if normalized not in {
        "privacy",
        "terms",
    }:
        return {
            "available": False,
            "error": "unsupported_document_type",
        }

    try:
        from backend.db import get_db

        db = get_db()

        collection = db[
            "legaldocs"
        ]

        document = collection.find_one(
            {
                "type": normalized
            },
            {
                "_id": 0
            },
        )

        if not document:

            return {
                "available": False,
                "document_type": normalized,
                "error": "document_not_found",
            }

        return {
            "available": True,
            "source": "revelacode_platform",
            "document_type": normalized,
            "version": document.get(
                "version",
                "1.0",
            ),
            "content": str(
                document.get(
                    "content",
                    "",
                )
                or ""
            ),
            "updated_at": (
                document.get(
                    "updated_at"
                ).isoformat()
                if hasattr(
                    document.get(
                        "updated_at"
                    ),
                    "isoformat",
                )
                else document.get(
                    "updated_at"
                )
            ),
        }

    except Exception:

        return {
            "available": False,
            "document_type": normalized,
            "error": "legal_document_unavailable",
        }


__all__ = [
    "get_platform_manifest",
    "get_public_legal_document",
]
