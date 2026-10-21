"""RevelaCode-owned Elimu learning APIs; catalog data is sourced from study_materials."""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import secrets
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, send_file
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from backend.db import get_db
from backend.jumuiya.core.permissions import current_user_id, require_authenticated

elimu_learning_bp = Blueprint("revelacode_elimu_learning", __name__, url_prefix="/api")
HUB_ID = "elimu-education"
PROGRESS = "revelacode_elimu_learning_progress"
CERTIFICATES = "revelacode_elimu_learning_certificates"


def _now():
    return datetime.now(timezone.utc)


def _text(value):
    return str(value or "").strip()


def _slug(value):
    return re.sub(r"[^a-z0-9_-]+", "-", _text(value).lower()).strip("-")[:100] or "general"


def _materials():
    db = get_db()
    rows = list(db["study_materials"].find({"category": {"$in": ["education", "elimu"]}}).limit(2000))
    result = []
    for row in rows:
        status = _text(row.get("status") or row.get("publication_status") or "published").lower()
        if status not in {"published", "active", "available"}:
            continue
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        mid = _text(row.get("id") or row.get("_id"))
        title = _text(row.get("title") or metadata.get("lesson_title"))
        if mid and title:
            result.append((row, metadata, mid, title))
    return result


def _hub(user_id):
    materials = _materials()
    if not materials:
        return None
    rows = list(get_db()[PROGRESS].find({"user_id": user_id, "hub_id": HUB_ID}))
    completed_lessons = {str(x.get("lesson_id")) for x in rows if x.get("action") == "complete_lesson"}
    started = {str(x.get("course_id")) for x in rows if x.get("action") == "start"}
    completed_courses = {str(x.get("course_id")) for x in rows if x.get("action") == "complete_course"}
    groups = {}
    for row, meta, mid, title in materials:
        raw_key = meta.get("course_id") or meta.get("course_title") or row.get("course_id") or row.get("course_title") or row.get("subcategory") or row.get("subject") or "General"
        key = _slug(raw_key)
        course = groups.setdefault(key, {"id": key, "course_id": key, "title": _text(meta.get("course_title") or row.get("course_title") or row.get("subcategory") or row.get("subject") or title), "description": _text(meta.get("course_description") or row.get("course_description")), "lessons": []})
        course["lessons"].append({"id": mid, "lesson_id": mid, "title": title, "description": _text(row.get("description") or meta.get("description")), "completed": mid in completed_lessons})
    courses = list(groups.values())
    for course in courses:
        course["lessons"].sort(key=lambda x: x["title"].casefold())
        course["status"] = "completed" if course["id"] in completed_courses else ("in_progress" if course["id"] in started or any(x["completed"] for x in course["lessons"]) else "not started")
    courses.sort(key=lambda x: x["title"].casefold())
    lessons = [lesson for course in courses for lesson in course["lessons"]]
    done = sum(bool(x["completed"]) for x in lessons)
    done_courses = sum(course["status"] == "completed" for course in courses)
    return {"id": HUB_ID, "name": "RevelaCode Education", "description": "Published education materials stored by RevelaCode.", "courses_count": len(courses), "courses": courses, "progress": {"completed_lessons": done, "total_lessons": len(lessons), "completed_courses": done_courses, "total_courses": len(courses), "progress_percent": round(done * 100 / len(lessons)) if lessons else 0, "hub_completed": bool(courses and lessons and done == len(lessons) and done_courses == len(courses))}}


def _key():
    secret = _text(os.getenv("REVELACODE_CERTIFICATE_SIGNING_KEY"))
    if not secret:
        secret = _text(os.getenv("JWT_SECRET"))
    if not secret:
        raise RuntimeError("Certificate signing secret is not configured")
    return hmac.new(secret.encode(), b"revelacode-elimu-learning-certificate-v1", hashlib.sha256).digest()


def _signature(claims):
    raw = json.dumps(claims, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hmac.new(_key(), raw, hashlib.sha256).hexdigest()


def _escape(value):
    return _text(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") or "Not recorded"


def _pdf(record):
    c = record["claims"]
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=22*mm, leftMargin=22*mm, topMargin=24*mm, bottomMargin=22*mm, title="RevelaCode Elimu Learning Certificate", author="RevelaCode")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="RCBrand", parent=styles["Title"], fontSize=25, textColor=colors.HexColor("#0A74DA"), spaceAfter=12))
    styles.add(ParagraphStyle(name="RCCert", parent=styles["Heading1"], fontSize=18, textColor=colors.HexColor("#2E8B57"), spaceAfter=16))
    story = [Paragraph("RevelaCode", styles["RCBrand"]), Paragraph("Elimu Learning Certificate", styles["RCCert"])]
    for label, value in [("Issued to", c.get("full_name")), ("Account ID", c.get("user_id")), ("Learning hub", c.get("hub_name")), ("Completed lessons", f'{c.get("completed_lessons", 0)} / {c.get("total_lessons", 0)}'), ("Roles recorded", ", ".join(c.get("roles") or [])), ("Certificate ID", record.get("certificate_id")), ("Issued at (UTC)", c.get("issued_at")), ("Verification endpoint", c.get("verification_url"))]:
        story.append(Paragraph(f"<b>{label}:</b> {_escape(value)}", styles["BodyText"]))
        story.append(Spacer(1, 4*mm))
    story.append(Spacer(1, 10*mm))
    story.append(Paragraph("Issuer: RevelaCode. This certificate confirms only the learning completion recorded in RevelaCode; it is not a government qualification or external accreditation.", styles["Italic"]))
    doc.build(story)
    return output.getvalue()


@elimu_learning_bp.get("/elimu/hubs")
@require_authenticated
def list_hubs():
    user_id = _text(current_user_id())
    hub = _hub(user_id)
    return jsonify(success=True, hubs=[{k: hub[k] for k in ("id", "name", "description", "courses_count")}] if hub else [])


@elimu_learning_bp.get("/elimu/hubs/<hub_id>")
@require_authenticated
def get_hub(hub_id):
    if hub_id != HUB_ID:
        return jsonify(success=False, error={"code": "hub_not_found", "message": "Learning hub not found."}), 404
    hub = _hub(_text(current_user_id()))
    if not hub:
        return jsonify(success=False, error={"code": "learning_content_unavailable", "message": "No published education materials are available yet."}), 404
    return jsonify(success=True, hub=hub)


@elimu_learning_bp.get("/elimu/progress")
@require_authenticated
def get_progress():
    """Return the authenticated user's persisted progress for the requested hub."""
    requested_hub = _text(request.args.get("hub_id")) or HUB_ID
    if requested_hub != HUB_ID:
        return jsonify(success=False, error={"code": "hub_not_found", "message": "Learning hub not found."}), 404

    user_id = _text(current_user_id())
    hub = _hub(user_id)
    if not hub:
        return jsonify(success=False, error={"code": "learning_content_unavailable", "message": "No published education materials are available yet."}), 404

    return jsonify(
        success=True,
        hub_id=HUB_ID,
        progress=hub["progress"],
        hub=hub,
    ), 200


@elimu_learning_bp.post("/elimu/progress")
@require_authenticated
def save_progress():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(success=False, error={"code": "invalid_json", "message": "A JSON object is required."}), 400
    user_id = _text(current_user_id())
    hub_id, course_id, action, lesson_id = map(_text, (payload.get("hub_id"), payload.get("course_id"), payload.get("action"), payload.get("lesson_id")))
    if hub_id != HUB_ID or action not in {"start", "complete_lesson", "complete_course"} or not course_id:
        return jsonify(success=False, error={"code": "invalid_progress_request", "message": "Hub, course or action is invalid."}), 422
    hub = _hub(user_id)
    if not hub:
        return jsonify(success=False, error={"code": "learning_content_unavailable", "message": "No published education materials are available."}), 409
    course = next((x for x in hub["courses"] if x["id"] == course_id), None)
    if not course:
        return jsonify(success=False, error={"code": "course_not_found", "message": "Course not found."}), 404
    if action == "complete_lesson" and lesson_id not in {x["id"] for x in course["lessons"]}:
        return jsonify(success=False, error={"code": "lesson_not_found", "message": "Lesson does not belong to this course."}), 404
    if action == "complete_course" and (not course["lessons"] or not all(x["completed"] for x in course["lessons"])):
        return jsonify(success=False, error={"code": "course_incomplete", "message": "Complete every recorded lesson first."}), 409
    now = _now()
    query = {"user_id": user_id, "hub_id": HUB_ID, "course_id": course_id, "action": action}
    if action == "complete_lesson":
        query["lesson_id"] = lesson_id
    get_db()[PROGRESS].update_one(query, {"$set": {"user_id": user_id, "hub_id": HUB_ID, "course_id": course_id, "action": action, "lesson_id": lesson_id or None, "updated_at": now}, "$setOnInsert": {"created_at": now}}, upsert=True)
    updated = _hub(user_id)
    return jsonify(success=True, progress=updated["progress"], hub=updated)


@elimu_learning_bp.post("/certificates/generate")
@require_authenticated
def generate_certificate():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or _text(payload.get("hub_id")) != HUB_ID:
        return jsonify(success=False, error={"code": "hub_not_found", "message": "Learning hub not found."}), 404
    user_id = _text(current_user_id())
    hub = _hub(user_id)
    if not hub or not hub["progress"]["hub_completed"]:
        return jsonify(success=False, error={"code": "learning_incomplete", "message": "Complete all recorded courses and lessons before requesting a certificate."}), 409
    db = get_db()
    existing = db[CERTIFICATES].find_one({"user_id": user_id, "hub_id": HUB_ID, "status": "active"})
    if existing:
        return jsonify(success=True, certificate_id=existing["certificate_id"], cert_id=existing["certificate_id"], already_issued=True)
    user = db["users"].find_one({"$or": [{"id": user_id}, {"user_id": user_id}]})
    if not user:
        try:
            from bson import ObjectId
            if ObjectId.is_valid(user_id):
                user = db["users"].find_one({"_id": ObjectId(user_id)})
        except Exception:
            user = None
    user = user or {}
    raw_roles = user.get("roles") if isinstance(user.get("roles"), list) else []
    if user.get("role"):
        raw_roles = list(raw_roles) + [user["role"]]
    roles = list(dict.fromkeys(str(x).strip() for x in raw_roles if str(x).strip())) or ["user"]
    cert_id = "RC-EL-" + secrets.token_hex(8).upper()
    root = _text(os.getenv("REVELACODE_PUBLIC_URL")) or "https://revelacode.co.ke"
    claims = {"certificate_id": cert_id, "user_id": user_id, "full_name": _text(user.get("full_name") or user.get("name") or user.get("username")), "roles": roles, "hub_id": HUB_ID, "hub_name": hub["name"], "completed_lessons": hub["progress"]["completed_lessons"], "total_lessons": hub["progress"]["total_lessons"], "issued_at": _now().isoformat(), "issuer": "RevelaCode", "scope": "recorded_elimu_learning_completion", "verification_url": f"{root.rstrip('/')}/api/certificates/verify/{cert_id}"}
    record = {"certificate_id": cert_id, "user_id": user_id, "hub_id": HUB_ID, "status": "active", "claims": claims, "signature": _signature(claims), "signature_algorithm": "HMAC-SHA256", "created_at": _now()}
    db[CERTIFICATES].insert_one(record)
    return jsonify(success=True, certificate_id=cert_id, cert_id=cert_id, already_issued=False, verification_url=claims["verification_url"]), 201


@elimu_learning_bp.get("/certificates/<certificate_id>")
@require_authenticated
def download_certificate(certificate_id):
    user_id = _text(current_user_id())
    record = get_db()[CERTIFICATES].find_one({"certificate_id": certificate_id, "user_id": user_id, "status": "active"})
    if not record:
        return jsonify(success=False, error={"code": "certificate_not_found", "message": "No active certificate belongs to this account."}), 404
    if not hmac.compare_digest(str(record.get("signature") or ""), _signature(record.get("claims") or {})):
        return jsonify(success=False, error={"code": "certificate_signature_invalid", "message": "Certificate integrity check failed."}), 409
    response = send_file(io.BytesIO(_pdf(record)), mimetype="application/pdf", as_attachment=True, download_name=f"{certificate_id}.pdf", max_age=0)
    response.headers["Cache-Control"] = "no-store"
    return response


@elimu_learning_bp.get("/certificates/verify/<certificate_id>")
def verify_certificate(certificate_id):
    if not re.fullmatch(r"RC-EL-[A-F0-9]{16}", str(certificate_id or "")):
        return jsonify(valid=False, certificate_id=certificate_id, reason="certificate_not_found"), 404
    record = get_db()[CERTIFICATES].find_one({"certificate_id": certificate_id})
    if not record:
        return jsonify(valid=False, certificate_id=certificate_id, reason="certificate_not_found"), 404
    if record.get("status") != "active":
        return jsonify(valid=False, certificate_id=certificate_id, reason="certificate_revoked"), 200
    claims = record.get("claims") or {}
    if not hmac.compare_digest(str(record.get("signature") or ""), _signature(claims)):
        return jsonify(valid=False, certificate_id=certificate_id, reason="signature_invalid"), 200
    # The public endpoint needs to prove the issuer record, not reveal the
    # learner's internal account ID.
    return jsonify(valid=True, certified_by="RevelaCode", issuer_role="RevelaCode Certificate Issuer", certificate_id=certificate_id, user={"name": claims.get("full_name"), "roles": claims.get("roles") or []}, hub={"name": claims.get("hub_name"), "completed_lessons": claims.get("completed_lessons"), "total_lessons": claims.get("total_lessons")}, roles=claims.get("roles") or [], issued_at=claims.get("issued_at"), verification_url=claims.get("verification_url"), signature_algorithm="HMAC-SHA256", certificate_scope="Recorded Elimu learning completion only; not a government qualification or external accreditation.")
