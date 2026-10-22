"""Shamba trust, farm-rights review, soil preflight, and service-lead routes.

Important boundaries:
- A RevelaCode review is not a government title search or legal adjudication.
- Camera photos support surface/quality screening only. They cannot scan subsurface
  layers or measure soil chemistry. Laboratory results must come from a qualified lab.
- Raw images are processed in memory and are not persisted by this module.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import re
from functools import wraps
from datetime import datetime, timezone
from typing import Any

import requests
from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, request
from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import (
    current_user_id,
    require_authenticated,
    require_roles,
)
from backend.jumuiya.core.responses import created, ok
from backend.revenue.subscriptions import require_revenue_entitlement
from backend.services.ai_router import ask_ai

shamba_trust_bp = Blueprint("jumuiya_shamba_trust", __name__, url_prefix="/trust")

FARMS = "jumuiya_farms"
VERIFICATIONS = "jumuiya_farm_verification_cases"
SOIL_SCANS = "jumuiya_soil_scan_records"
SOIL_SERVICE_LEADS = "jumuiya_soil_service_leads"
SAFETY_REPORTS = "jumuiya_shamba_safety_reports"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
RIGHTS_BASES = {
    "registered_owner",
    "leaseholder",
    "authorized_manager",
    "community_land_user",
    "other_lawful_interest",
}
EVIDENCE_TYPES = {
    "land_register_reference",
    "lease_reference",
    "authority_letter_reference",
    "community_land_resolution_reference",
    "other_reference",
}
SERVICE_TYPES = {"laboratory_soil_test", "agronomy_consultation"}
REPORT_CATEGORIES = {
    "suspected_scam",
    "fake_or_misrepresented_product",
    "off_platform_payment_pressure",
    "land_or_farm_misrepresentation",
    "duplicate_or_stolen_media",
    "unsafe_agricultural_claim",
    "other",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any, name: str, maximum: int = 500, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise APIError(f"{name} must be text.", 422, "validation_error")
    value = value.strip()
    if required and not value:
        raise APIError(f"{name} is required.", 422, "validation_error")
    if len(value) > maximum:
        raise APIError(f"{name} is too long (maximum {maximum} characters).", 422, "validation_error")
    return value


def _farm_id(value: str) -> ObjectId:
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError, ValueError):
        raise APIError("Invalid farm identifier.", 400, "invalid_farm_id")


def _owned_farm(user_id: str, farm_id: str) -> dict:
    farm = collection(FARMS).find_one({
        "_id": _farm_id(farm_id),
        "owner_user_id": str(user_id),
        "status": {"$ne": "deleted"},
    })
    if not farm:
        raise APIError("Farm not found or you do not manage it.", 404, "farm_not_found")
    return farm


def _latest_case(farm_id: str, user_id: str | None = None) -> dict | None:
    query: dict[str, Any] = {"farm_id": str(farm_id)}
    if user_id is not None:
        query["owner_user_id"] = str(user_id)
    return collection(VERIFICATIONS).find_one(query, sort=[("created_at", -1)])


def ensure_farm_verified(user_id: str, farm_id: str) -> dict:
    """Fail closed for farm operations that require reviewed rights."""
    farm = _owned_farm(user_id, farm_id)
    state = str(farm.get("legal_verification_status") or "not_submitted").lower()
    if state != "verified":
        latest = _latest_case(str(farm.get("_id")), user_id)
        if latest and latest.get("status") == "verified":
            return farm
        raise APIError(
            "Farm rights must be reviewed by RevelaCode before this operation. Open Trust & Soil to submit the relevant ownership, lease, management or community-land reference.",
            403,
            "farm_verification_required",
            {"farm_id": str(farm.get("_id")), "verification_status": state},
        )
    return farm


def require_farm_rights_review(fn):
    """Route decorator: require this user's farm to have reviewed rights."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        farm_id = kwargs.get("farm_id")
        if not farm_id and args:
            farm_id = args[0]
        if not farm_id:
            raise APIError("Farm identifier is required.", 400, "farm_id_required")
        ensure_farm_verified(current_user_id(), str(farm_id))
        return fn(*args, **kwargs)
    return wrapper


def require_verified_farm_workspace(fn):
    """Route decorator for endpoints that summarize a whole farmer workspace."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = current_user_id()
        found = collection(FARMS).find_one({
            "owner_user_id": str(user_id),
            "status": {"$ne": "deleted"},
            "legal_verification_status": "verified",
        })
        if not found:
            raise APIError(
                "A farm with reviewed rights is required before using this Shamba operation.",
                403,
                "farm_verification_required",
            )
        return fn(*args, **kwargs)
    return wrapper


def _farm_summary(farm: dict, case: dict | None) -> dict:
    farm_id = str(farm.get("_id", ""))
    status = (case or {}).get("status") or farm.get("legal_verification_status") or "not_submitted"
    return {
        "id": farm_id,
        "name": farm.get("name") or "Unnamed farm",
        "county": farm.get("county") or "",
        "town": farm.get("town") or "",
        "location": farm.get("location") or "",
        "size": farm.get("size"),
        "size_unit": farm.get("size_unit") or "acres",
        "legal_verification_status": str(status).lower(),
        "rights_basis": (case or {}).get("rights_basis") or farm.get("rights_basis") or "",
        "verification_case_id": str((case or {}).get("_id", "")) or None,
        "verification_submitted_at": (case or {}).get("created_at").isoformat() if isinstance((case or {}).get("created_at"), datetime) else (case or {}).get("created_at"),
        "review_notes": (case or {}).get("review_notes") or "",
        "platform_review_only": True,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        result = {str(k): _json_safe(v) for k, v in value.items() if k != "_id"}
        if value.get("_id") is not None:
            result.setdefault("id", str(value["_id"]))
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _admin_roles(f):
    return require_authenticated(require_roles("admin", "super_admin")(f))


def _photo_preflight(raw: bytes) -> tuple[dict, bytes, str]:
    try:
        candidate = Image.open(io.BytesIO(raw))
        candidate.verify()
        image = Image.open(io.BytesIO(raw))
        # Check compressed-image dimensions before rotating or converting pixels.
        # This bounds memory use for malformed/decompression-bomb images.
        width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise APIError("That file is not a valid supported image. Choose a clear JPEG, PNG or WebP photo.", 422, "invalid_image")

    fmt = str(image.format or "").upper()
    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise APIError("Only JPEG, PNG and WebP photos are supported.", 415, "unsupported_image_format")
    if width < 320 or height < 240:
        raise APIError("Photo is too small. Use at least 320 × 240 pixels.", 422, "image_too_small")
    if width * height > MAX_IMAGE_PIXELS:
        raise APIError("Photo resolution is too large. Use a photo of 16 megapixels or less.", 413, "image_too_large")

    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size

    preview = image.copy()
    preview.thumbnail((96, 96))
    gray = ImageOps.grayscale(preview)
    luminance = float(ImageStat.Stat(gray).mean[0])
    contrast = float(ImageStat.Stat(gray).stddev[0])
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_strength = float(ImageStat.Stat(edges).mean[0])
    rgb = [round(x, 1) for x in ImageStat.Stat(preview).mean[:3]]

    issues = []
    if luminance < 20:
        issues.append("Photo appears too dark; use daylight or brighter shade.")
    elif luminance > 238:
        issues.append("Photo appears overexposed; reduce direct glare or sunlight.")
    if contrast < 8:
        issues.append("The photo has very little visible contrast; refocus and capture the soil surface clearly.")
    if edge_strength < 1.8:
        issues.append("Fine detail is hard to distinguish; clean the camera lens and retake the photo closer to the sample.")

    quality_score = 100
    if luminance < 20 or luminance > 238:
        quality_score -= 30
    if contrast < 8:
        quality_score -= 25
    if edge_strength < 1.8:
        quality_score -= 25
    quality_score = max(0, min(100, quality_score))

    # Strip EXIF/GPS metadata and normalize orientation before any optional vision call.
    clean_buffer = io.BytesIO()
    sanitized = image.copy()
    sanitized.thumbnail((2600, 2600))
    sanitized.save(clean_buffer, format="JPEG", quality=88, optimize=True)
    if clean_buffer.tell() > MAX_IMAGE_BYTES:
        clean_buffer = io.BytesIO()
        sanitized.save(clean_buffer, format="JPEG", quality=72, optimize=True)
    if clean_buffer.tell() > MAX_IMAGE_BYTES:
        raise APIError("Could not safely compress this photo to the supported size. Please capture a smaller photo.", 413, "sanitized_image_too_large")

    result = {
        "format": fmt,
        "width": width,
        "height": height,
        "file_size_bytes": len(raw),
        "photo_quality_score": quality_score,
        "mean_luminance_0_255": round(luminance, 2),
        "luminance_contrast": round(contrast, 2),
        "edge_detail_indicator": round(edge_strength, 2),
        "mean_rgb": rgb,
        "ready_for_ai_intake": not issues,
        "retake_tips": issues,
        "what_this_measures": "Photo quality and coarse pixel statistics only; not soil chemistry, subsurface layers or fertility.",
        "exif_metadata_removed_before_optional_vision_call": True,
    }
    return result, clean_buffer.getvalue(), "image/jpeg"


def _extract_answer(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("answer", "response", "content", "text", "output", "message"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for key in ("data", "result"):
            candidate = value.get(key)
            answer = _extract_answer(candidate)
            if answer:
                return answer
    if isinstance(value, list):
        for item in value:
            answer = _extract_answer(item)
            if answer:
                return answer
    return ""


def _call_revelaai(raw: bytes, mime: str, preflight: dict, observations: str, farm: dict) -> tuple[str, str, bool]:
    prompt = (
        "You support a Kenyan farmer with cautious soil-sampling guidance. Do not claim that a phone camera can see underground layers or measure pH, NPK, salinity, heavy metals, contamination or fertility. "
        "Separate directly measured photo-quality metrics from the farmer's own observations and from hypotheses. Never prescribe exact fertilizer quantities without lab results and crop/area context. "
        "Recommend representative physical soil sampling and a qualified laboratory where chemical values matter. Provide brief actionable next steps and uncertainty."
    )
    context = {
        "farm_context": {"county": farm.get("county") or "", "town": farm.get("town") or "", "crop_context": farm.get("current_crop") or ""},
        "farmer_observations": observations,
        "photo_preflight": preflight,
        "limitation": "If image-capable inference is not configured, only metadata and farmer observations are sent to text RevelaAI; raw image pixels are not interpreted by a text-only model.",
    }

    vision_url = os.getenv("REVELA_AI_VISION_URL", "").strip()
    if vision_url:
        payload = {
            "prompt": prompt,
            "domain": "shamba_soil_surface_screening",
            "image_base64": base64.b64encode(raw).decode("ascii"),
            "image_mime_type": mime,
            "context": context,
        }
        try:
            response = requests.post(vision_url, json=payload, timeout=45)
            response.raise_for_status()
            answer = _extract_answer(response.json())
            if answer:
                return answer[:6000], "vision_endpoint", True
            return "The image-capable service returned no usable advice. Retake or request a qualified soil test.", "vision_endpoint_empty", True
        except Exception as exc:  # keep the scan record even if the AI service is down
            return f"Image preflight passed, but the image-capable service is unavailable ({type(exc).__name__}). Retry later or request a laboratory test.", "vision_endpoint_unavailable", True

    context["explicit_warning"] = "The text AI has NOT received the image pixels. Only use the numeric photo quality metrics and farmer observations; do not describe the image's visible soil appearance as if seen."
    if not os.getenv("REVELA_AI_URL", "").strip():
        return (
            "Photo-quality checks passed, but RevelaAI is not configured on the backend. "
            "No AI request was sent. This is not a soil diagnosis; use a qualified lab for pH, nutrients or contaminants.",
            "metadata_only_text_triage_unavailable",
            False,
        )
    answer = _extract_answer(ask_ai(prompt, domain="shamba", context=context))
    if not answer:
        answer = "Photo-quality checks passed. Image-aware AI is not configured, so this is not a visual soil interpretation. Record the sample location and crop, then use a qualified lab for pH, nutrients or contaminants."
    return answer[:6000], "metadata_only_text_triage", True


@shamba_trust_bp.get("/overview")
@require_authenticated
def trust_overview():
    user_id = current_user_id()
    farms = list(collection(FARMS).find({"owner_user_id": str(user_id), "status": {"$ne": "deleted"}}).sort("created_at", -1))
    result = []
    for farm in farms:
        farm_id = str(farm.get("_id"))
        case = _latest_case(farm_id, user_id)
        result.append(_farm_summary(farm, case))
    verified = sum(1 for farm in result if farm["legal_verification_status"] == "verified")
    pending = sum(1 for farm in result if farm["legal_verification_status"] in {"pending", "more_info"})
    return ok({"farms": result, "farm_count": len(result), "verified_farm_count": verified, "pending_farm_count": pending, "platform_review_only": True})


@shamba_trust_bp.post("/farms/<farm_id>/verification")
@require_authenticated
def submit_farm_verification(farm_id: str):
    user_id = current_user_id()
    farm = _owned_farm(user_id, farm_id)
    data = request.get_json(silent=True) or {}
    rights_basis = _text(data.get("rights_basis"), "rights_basis", 50, True).lower()
    evidence_type = _text(data.get("evidence_type"), "evidence_type", 80, True).lower()
    evidence_reference = _text(data.get("evidence_reference"), "evidence_reference", 120, True)
    declaration = data.get("declaration") is True
    privacy_consent = data.get("privacy_consent") is True

    if rights_basis not in RIGHTS_BASES:
        raise APIError("Choose a supported lawful farm-rights basis.", 422, "invalid_rights_basis")
    if evidence_type not in EVIDENCE_TYPES:
        raise APIError("Choose a supported evidence-reference type.", 422, "invalid_evidence_type")
    if not declaration:
        raise APIError("Confirm that you are authorized to manage this farm and the information is accurate.", 422, "declaration_required")
    if not privacy_consent:
        raise APIError("Consent to process the submitted verification reference is required.", 422, "privacy_consent_required")
    if re.search(r"\b(?:national\s*id|id\s*number|passport\s*number)\s*[:#-]?\s*\w+", evidence_reference, re.I):
        raise APIError("Do not enter national ID or passport numbers. Enter a land, lease or authorization reference only.", 422, "sensitive_identifier_rejected")

    farm_key = str(farm.get("_id"))
    current = _latest_case(farm_key, user_id)
    if current and current.get("status") == "pending":
        raise APIError("A farm-rights review is already pending. Wait for the reviewer or respond to a request for more information.", 409, "verification_already_pending")

    fingerprint = hashlib.sha256(evidence_reference.casefold().encode("utf-8")).hexdigest()
    duplicate = collection(VERIFICATIONS).find_one({"evidence_reference_hash": fingerprint, "status": {"$in": ["pending", "verified"]}, "farm_id": {"$ne": farm_key}})
    if duplicate:
        raise APIError("This reference is already associated with another pending or verified farm record. Contact support if the same lawful reference covers multiple parcels.", 409, "duplicate_evidence_reference")

    now = _now()
    case = {
        "owner_user_id": str(user_id),
        "farm_id": farm_key,
        "farm_name_snapshot": farm.get("name") or "Unnamed farm",
        "county_snapshot": farm.get("county") or "",
        "town_snapshot": farm.get("town") or "",
        "rights_basis": rights_basis,
        "evidence_type": evidence_type,
        "evidence_reference": evidence_reference,
        "evidence_reference_hash": fingerprint,
        "status": "pending",
        "review_notes": "",
        "platform_review_only": True,
        "created_at": now,
        "updated_at": now,
    }
    inserted = collection(VERIFICATIONS).insert_one(case)
    collection(FARMS).update_one({"_id": farm["_id"], "owner_user_id": str(user_id)}, {"$set": {"legal_verification_status": "pending", "rights_basis": rights_basis, "verification_case_id": str(inserted.inserted_id), "updated_at": now}})
    return created({"case_id": str(inserted.inserted_id), "farm_id": farm_key, "status": "pending", "message": "Submitted for manual RevelaCode review. This is not a government title certification."}, "Farm-rights review submitted.")


@shamba_trust_bp.get("/verification-queue")
@require_authenticated
@require_roles("admin", "super_admin")
def verification_queue():
    cases = list(collection(VERIFICATIONS).find({"status": {"$in": ["pending", "more_info"]}}).sort("created_at", 1).limit(200))
    return ok({"items": [_json_safe(item) for item in cases], "count": len(cases)})


@shamba_trust_bp.post("/farms/<farm_id>/verification/review")
@require_authenticated
@require_roles("admin", "super_admin")
def review_farm_verification(farm_id: str):
    data = request.get_json(silent=True) or {}
    decision = _text(data.get("decision"), "decision", 30, True).lower()
    notes = _text(data.get("review_notes"), "review_notes", 800, True)
    if decision not in {"verified", "rejected", "more_info"}:
        raise APIError("Decision must be verified, rejected or more_info.", 422, "invalid_review_decision")
    case = collection(VERIFICATIONS).find_one({"farm_id": str(farm_id), "status": {"$in": ["pending", "more_info"]}}, sort=[("created_at", -1)])
    if not case:
        raise APIError("No pending review exists for this farm.", 404, "verification_case_not_found")
    farm = collection(FARMS).find_one({"_id": _farm_id(farm_id), "owner_user_id": str(case.get("owner_user_id")), "status": {"$ne": "deleted"}})
    if not farm:
        raise APIError("Farm record no longer exists.", 404, "farm_not_found")
    now = _now()
    reviewer = str(current_user_id())
    collection(VERIFICATIONS).update_one({"_id": case["_id"]}, {"$set": {"status": decision, "review_notes": notes, "reviewer_user_id": reviewer, "reviewed_at": now, "updated_at": now}})
    collection(FARMS).update_one({"_id": farm["_id"]}, {"$set": {"legal_verification_status": decision, "verification_reviewed_at": now, "verification_reviewer_user_id": reviewer, "verification_review_notes": notes, "updated_at": now}})
    return ok({"farm_id": str(farm["_id"]), "status": decision, "reviewer_user_id": reviewer, "reviewed_at": now.isoformat(), "platform_review_only": True}, "Farm verification decision saved.")


@shamba_trust_bp.post("/farms/<farm_id>/soil-scan")
@require_authenticated
@require_revenue_entitlement("shamba", "advanced_analytics")
def soil_scan(farm_id: str):
    user_id = current_user_id()
    farm = ensure_farm_verified(user_id, farm_id)
    uploaded = request.files.get("image")
    if uploaded is None or not uploaded.filename:
        raise APIError("Capture or choose a soil-sample photo first.", 400, "soil_image_required")
    declared_mime = (uploaded.mimetype or "").lower()
    if declared_mime not in {"image/jpeg", "image/png", "image/webp"}:
        raise APIError("Only JPEG, PNG and WebP images are supported.", 415, "unsupported_image_type")
    raw = uploaded.stream.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise APIError("Photo must be 5 MB or smaller.", 413, "soil_image_too_large")
    observations = _text(request.form.get("observations"), "observations", 1200, True)
    consent = str(request.form.get("analysis_consent", "")).strip().lower() in {"true", "1", "yes", "on"}
    if not consent:
        raise APIError("Confirm that the photo and observation may be processed for this scan.", 422, "soil_scan_consent_required")

    preflight, sanitized_image, sanitized_mime = _photo_preflight(raw)
    expected_format = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}.get(declared_mime)
    if preflight["format"] != expected_format:
        raise APIError("The uploaded file content does not match its declared image type. Choose a real JPEG, PNG or WebP photo.", 415, "image_type_mismatch")
    sha = hashlib.sha256(raw).hexdigest()
    prior = collection(SOIL_SCANS).find_one({"image_sha256": sha, "status": "completed"})
    if prior:
        raise APIError("This exact photo has already been used for a scan. Capture a new, genuine sample photo rather than reusing a listing or old image.", 409, "duplicate_soil_photo")

    now = _now()
    if not preflight["ready_for_ai_intake"]:
        record = {
            "owner_user_id": str(user_id), "farm_id": str(farm["_id"]), "image_sha256": sha,
            "photo_preflight": preflight, "status": "retake_required", "ai_called": False,
            "created_at": now, "updated_at": now,
        }
        inserted = collection(SOIL_SCANS).insert_one(record)
        return ok({"scan_id": str(inserted.inserted_id), "status": "retake_required", "ai_called": False, "photo_preflight": preflight, "message": "Photo quality needs improvement. Retake the photo before requesting AI guidance.", "limitations": "A camera photo cannot scan underground layers or measure pH, nutrients or contaminants."})

    # Do not persist raw bytes. When configured, an image-capable service receives the
    # photo only after deterministic MIME, size, dimension, contrast and detail checks.
    answer, analysis_mode, ai_called = _call_revelaai(sanitized_image, sanitized_mime, preflight, observations, farm)
    record = {
        "owner_user_id": str(user_id), "farm_id": str(farm["_id"]), "image_sha256": sha,
        "photo_preflight": preflight, "observations": observations,
        "analysis_mode": analysis_mode, "ai_called": ai_called,
        "ai_summary": answer[:6000], "status": "completed", "created_at": now, "updated_at": now,
        "image_retained": False,
        "limits": ["Surface photo triage only", "No subsurface scanning", "No lab chemistry values", "No fertilizer dosage recommendation without soil test and crop context"],
    }
    inserted = collection(SOIL_SCANS).insert_one(record)
    return created({
        "scan_id": str(inserted.inserted_id), "farm_id": str(farm["_id"]), "status": "completed",
        "photo_preflight": preflight, "analysis_mode": analysis_mode, "ai_called": ai_called,
        "ai_summary": answer,
        "image_retained": False,
        "limitations": ["This does not scan deep soil.", "A photo cannot reliably determine pH, nitrogen, phosphorus, potassium, salinity or heavy metals.", "Use representative samples and a qualified laboratory for these measurements."],
        "revenue_next_step": "Request a transparent laboratory-test quotation if measured nutrients or contamination results are needed.",
    }, "Soil photo preflight completed.")


@shamba_trust_bp.get("/soil-services")
@require_authenticated
def soil_services():
    return ok({"services": [
        {"id": "surface_photo_preflight", "title": "Soil Lens photo preflight", "price_kes": 0, "price_label": "Free preview", "status": "available", "description": "Photo quality and safe next-step guidance. Not a deep scan or lab result."},
        {"id": "laboratory_soil_test", "title": "Laboratory soil test", "price_kes": None, "price_label": "Quote before payment", "status": "quote_request", "description": "Measured soil characteristics from a qualified laboratory. Partner availability and price must be confirmed before payment."},
        {"id": "agronomy_consultation", "title": "Agronomy consultation", "price_kes": None, "price_label": "Quote before payment", "status": "quote_request", "description": "Request a qualified agronomist callback. Scope and price must be agreed in writing first."},
    ], "pricing_policy": "No payment is collected by these endpoints. Any later referral commission or partner relationship must be disclosed to the farmer before booking."})


@shamba_trust_bp.post("/farms/<farm_id>/soil-service-requests")
@require_authenticated
def request_soil_service(farm_id: str):
    user_id = current_user_id()
    farm = ensure_farm_verified(user_id, farm_id)
    data = request.get_json(silent=True) or {}
    service_type = _text(data.get("service_type"), "service_type", 60, True)
    if service_type not in SERVICE_TYPES:
        raise APIError("Choose laboratory_soil_test or agronomy_consultation.", 422, "invalid_service_type")
    county = _text(data.get("county"), "county", 100)
    contact = _text(data.get("preferred_contact"), "preferred_contact", 100, True)
    note = _text(data.get("note"), "note", 800)
    consent = data.get("contact_consent") is True
    if not consent:
        raise APIError("Consent to be contacted about this quote request is required.", 422, "contact_consent_required")
    now = _now()
    doc = {"owner_user_id": str(user_id), "farm_id": str(farm["_id"]), "service_type": service_type, "county": county or farm.get("county", ""), "preferred_contact": contact, "note": note, "status": "new", "quote_status": "not_quoted", "price_kes": None, "payment_status": "not_requested", "commission_disclosure_required": True, "created_at": now, "updated_at": now}
    inserted = collection(SOIL_SERVICE_LEADS).insert_one(doc)
    return created({"request_id": str(inserted.inserted_id), "status": "new", "quote_status": "not_quoted", "price_kes": None, "payment_required_now": False, "message": "Quote request recorded. No payment has been taken; availability and price must be confirmed first."}, "Soil service quote requested.")


@shamba_trust_bp.get("/soil-service-requests")
@require_authenticated
@require_roles("admin", "super_admin")
def list_soil_service_requests():
    items = list(collection(SOIL_SERVICE_LEADS).find({"status": {"$nin": ["closed", "cancelled"]}}).sort("created_at", 1).limit(200))
    return ok({"items": [_json_safe(item) for item in items], "count": len(items)})


@shamba_trust_bp.post("/safety-reports")
@require_authenticated
def report_safety_issue():
    user_id = current_user_id()
    data = request.get_json(silent=True) or {}
    listing_id = _text(data.get("listing_id"), "listing_id", 120, True)
    category = _text(data.get("category"), "category", 60, True)
    description = _text(data.get("description"), "description", 1200, True)
    if category not in REPORT_CATEGORIES:
        raise APIError("Choose a valid report category.", 422, "invalid_report_category")
    existing = collection(SAFETY_REPORTS).find_one({"reporter_user_id": str(user_id), "listing_id": listing_id, "status": "open"})
    if existing:
        raise APIError("You already reported this listing. Your existing report remains open for review.", 409, "duplicate_open_report")
    now = _now()
    doc = {"reporter_user_id": str(user_id), "listing_id": listing_id, "category": category, "description": description, "status": "open", "moderation_action": "pending_review", "created_at": now, "updated_at": now}
    result = collection(SAFETY_REPORTS).insert_one(doc)
    return created({"report_id": str(result.inserted_id), "status": "open", "message": "Report submitted for human review. Do not send money outside a protected, clearly documented transaction."}, "Safety report submitted.")


@shamba_trust_bp.get("/safety-reports")
@require_authenticated
@require_roles("admin", "super_admin")
def list_safety_reports():
    items = list(collection(SAFETY_REPORTS).find({"status": {"$in": ["open", "needs_more_info"]}}).sort("created_at", 1).limit(200))
    return ok({"items": [_json_safe(item) for item in items], "count": len(items)})


@shamba_trust_bp.post("/safety-reports/<report_id>/review")
@require_authenticated
@require_roles("admin", "super_admin")
def review_safety_report(report_id: str):
    data = request.get_json(silent=True) or {}
    decision = _text(data.get("decision"), "decision", 30, True).lower()
    note = _text(data.get("review_notes"), "review_notes", 800, True)
    if decision not in {"actioned", "dismissed", "needs_more_info"}:
        raise APIError("Decision must be actioned, dismissed or needs_more_info.", 422, "invalid_review_decision")
    try:
        oid = ObjectId(report_id)
    except (InvalidId, TypeError, ValueError):
        raise APIError("Invalid report identifier.", 400, "invalid_report_id")
    now = _now()
    report = collection(SAFETY_REPORTS).find_one({"_id": oid, "status": {"$in": ["open", "needs_more_info"]}})
    if not report:
        raise APIError("Open safety report not found.", 404, "report_not_found")

    moderated_listing = False
    if decision == "actioned":
        listing_id = str(report.get("listing_id") or "").strip()
        listing_selector: dict[str, Any] = {"_id": listing_id}
        if ObjectId.is_valid(listing_id):
            listing_selector["_id"] = ObjectId(listing_id)
        listing_result = collection("jumuiya_marketplace_listings").update_one(
            {**listing_selector, "status": "active"},
            {"$set": {
                "status": "suspended",
                "moderation_status": "under_review",
                "moderated_at": now,
                "moderated_by": str(current_user_id()),
                "moderation_reason": "Safety report actioned by platform moderator",
                "updated_at": now,
            }},
        )
        if not listing_result.matched_count:
            raise APIError("The listing was not found as active. Re-check its reference and select another review decision if it has already been removed.", 404, "active_listing_not_found")
        moderated_listing = True

    result = collection(SAFETY_REPORTS).update_one(
        {"_id": oid, "status": {"$in": ["open", "needs_more_info"]}},
        {"$set": {"status": decision, "review_notes": note, "reviewer_user_id": str(current_user_id()), "reviewed_at": now, "updated_at": now, "listing_suspended": moderated_listing}},
    )
    if not result.matched_count:
        raise APIError("Safety report changed during review. Reload the queue and try again.", 409, "report_review_conflict")
    return ok({"report_id": report_id, "status": decision, "listing_suspended": moderated_listing, "reviewed_at": now.isoformat()}, "Safety report review saved.")
