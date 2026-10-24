"""Stable compatibility aliases for the authenticated Elimu learning API.

The existing /api/study/elimu routes remain canonical implementation endpoints.
These aliases preserve older /api/elimu and /api/certificates links without
duplicating storage or weakening the original authentication/signature checks.
"""
from __future__ import annotations

from flask import Blueprint

from backend.routes import study_routes

elimu_compat_bp = Blueprint("elimu_compat_bp", __name__)


@elimu_compat_bp.get("/api/elimu/hubs")
def compat_elimu_list_hubs():
    return study_routes.elimu_learning_list_hubs()


@elimu_compat_bp.get("/api/elimu/hubs/<hub_id>")
def compat_elimu_get_hub(hub_id: str):
    return study_routes.elimu_learning_get_hub(hub_id)


@elimu_compat_bp.get("/api/elimu/progress")
def compat_elimu_get_progress():
    return study_routes.elimu_learning_get_progress()


@elimu_compat_bp.post("/api/elimu/progress")
def compat_elimu_save_progress():
    return study_routes.elimu_learning_save_progress()


@elimu_compat_bp.post("/api/elimu/certificates/generate")
@elimu_compat_bp.post("/api/certificates/generate")
def compat_elimu_generate_certificate():
    return study_routes.elimu_learning_generate_certificate()


@elimu_compat_bp.get("/api/elimu/certificates/<certificate_id>")
@elimu_compat_bp.get("/api/certificates/<certificate_id>")
def compat_elimu_download_certificate(certificate_id: str):
    return study_routes.elimu_learning_download_certificate(certificate_id)


@elimu_compat_bp.get("/api/elimu/certificates/verify/<certificate_id>")
@elimu_compat_bp.get("/api/certificates/verify/<certificate_id>")
def compat_elimu_verify_certificate(certificate_id: str):
    return study_routes.elimu_learning_verify_certificate(certificate_id)
