# backend/jumuiya/elimu/portal_routes.py
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import re
import math

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, request, send_file

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import created, ok
from backend.jumuiya.elimu import school_verification
from backend.jumuiya.elimu.timetable.models import ENTRIES as TIMETABLE_ENTRIES, TIMETABLES as TIMETABLES_COLLECTION


# These child blueprints are registered under /api/jumuiya/elimu.
parent_bp = Blueprint("jumuiya_elimu_parent_portal", __name__, url_prefix="/parent")
student_bp = Blueprint("jumuiya_elimu_student_portal", __name__, url_prefix="/student")
portal_review_bp = Blueprint("jumuiya_elimu_portal_review", __name__, url_prefix="/portal")

SCHOOLS = "jumuiya_schools"
STUDENTS = "jumuiya_students"
CLASSES = "jumuiya_classes"
LESSONS = "jumuiya_lessons"
ASSIGNMENTS = "jumuiya_assignments"
ASSESSMENTS = "jumuiya_assessments"
ATTENDANCE = "jumuiya_attendance"
FEES = "jumuiya_fees"
EVENTS = "jumuiya_school_events"
PUBLIC_DOCUMENTS = "jumuiya_elimu_public_documents"
PORTAL_LINKS = "jumuiya_elimu_portal_links"
MEMBERS = "jumuiya_elimu_school_members"
CERTIFICATES = "jumuiya_elimu_completion_certificates"
MAX_NOTES = 500
MAX_LIST = 100


def _now():
    return datetime.now(timezone.utc)


def _text(value, limit=160):
    return str(value or "").strip()[:limit]


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_phone(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("0") and len(digits) >= 9:
        digits = "254" + digits[1:]
    elif len(digits) == 9:
        digits = "254" + digits
    return digits


def _ser(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _ser(item) for key, item in value.items() if key != "_id"}
    if isinstance(value, list):
        return [_ser(item) for item in value]
    return value


def _object_id(value, label="identifier"):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError, ValueError):
        raise APIError(f"The {label} is invalid.", 400, "invalid_identifier")


def _json_body():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise APIError("A JSON request body is required.", 400, "invalid_json")
    return payload


def _school_for_public_slug(value):
    slug = _text(value, 120).lower()
    if not slug:
        raise APIError("Enter the school's public identifier.", 422, "validation_error")
    verified_values = list({
        "verified",
        str(getattr(school_verification, "VERIFIED", "verified")),
    })
    school = collection(SCHOOLS).find_one({
        "status": "active",
        "verification_status": {"$in": verified_values},
        "is_demo": {"$ne": True},
        "public_profile_enabled": True,
        "$or": [
            {"public_slug": slug},
            {"code": slug},
            {"school_code": slug},
        ],
    })
    if not school:
        # Do not reveal whether a particular school or student record exists.
        raise APIError("The published school could not be found. Check the school identifier.", 404, "school_not_found")
    return school


def _find_student(school, identifier):
    value = _text(identifier, 120)
    if not value:
        return None
    sid = str(school["_id"])
    return collection(STUDENTS).find_one({
        "school_id": sid,
        "status": "active",
        "$or": [
            {"admission_number": value},
            {"student_code": value},
            {"student_portal_id": value},
        ],
    })


def _project_student(student, school_name=""):
    lifecycle = student.get("lifecycle") if isinstance(student.get("lifecycle"), dict) else {}
    return {
        "id": str(student["_id"]),
        "student_id": str(student["_id"]),
        "full_name": _text(student.get("full_name"), 160),
        "display_name": _text(student.get("full_name"), 160),
        "admission_number": _text(student.get("admission_number"), 80),
        "student_code": _text(student.get("student_code"), 80),
        "class_name": _text(student.get("class_name"), 100),
        "stream": _text(student.get("stream"), 50),
        "status": _text(student.get("status"), 30),
        "school_id": str(student.get("school_id", "")),
        "school_name": school_name,
        "enrollment_date": _ser(student.get("enrollment_date")),
        "leaving_date": _ser(student.get("leaving_date")),
        "student_duration": _text(student.get("student_duration") or student.get("duration_period"), 80),
        "course_name": _text(student.get("course_name") or student.get("programme_name"), 140),
        "completion_status": _text(student.get("completion_status"), 40),
        "course_completed_at": _ser(student.get("course_completed_at")),
        "portal_duration": _text(student.get("student_duration") or student.get("duration_period"), 80),
        "portal_expires_at": _ser(student.get("leaving_date") or student.get("course_completed_at")),
        "lifecycle_notice": {
            "parent_reminder_sent_at": _ser(lifecycle.get("parent_reminder_sent_at")),
            "parent_response_deadline": _ser(lifecycle.get("parent_response_deadline")),
            "parent_response_at": _ser(lifecycle.get("parent_response_at")),
            "parent_response_kind": _text(lifecycle.get("parent_response_kind"), 40),
            "registrar_review_requested_at": _ser(lifecycle.get("registrar_review_requested_at")),
            "review_status": _text(lifecycle.get("review_status"), 40),
        },
    }


def _request_link(requester_type, payload):
    uid = str(current_user_id())
    school = _school_for_public_slug(payload.get("school_slug"))
    identifier = _text(payload.get("student_identifier"), 120)
    if not identifier:
        raise APIError("Enter the admission number or school-issued student identifier.", 422, "validation_error")

    student = _find_student(school, identifier)
    if not student:
        # Uniform response prevents this endpoint being used to enumerate students.
        return created({"status": "pending_review"}, "If the details match the school's records, the request can proceed to school review.")

    contact_match = "not_required"
    if requester_type == "parent":
        entered_phone = _normalize_phone(payload.get("guardian_phone"))
        entered_email = _text(payload.get("guardian_email"), 254).lower()
        if not entered_phone and not entered_email:
            raise APIError("Enter the guardian phone or email already registered with the school.", 422, "guardian_contact_required")
        registered_phone = _normalize_phone(student.get("guardian_phone"))
        registered_email = _text(student.get("guardian_email"), 254).lower()
        phone_matches = bool(entered_phone and registered_phone and entered_phone == registered_phone)
        email_matches = bool(entered_email and registered_email and entered_email == registered_email)
        if not phone_matches and not email_matches:
            # Do not disclose whether a student number or contact is incorrect.
            return created({"status": "pending_review"}, "If the details match the school's student and guardian records, the request can proceed to school review.")
        contact_match = "both" if phone_matches and email_matches else "phone" if phone_matches else "email"

    if requester_type == "student":
        linked_user = _text(student.get("student_user_id"), 160)
        if linked_user and linked_user != uid:
            return created({"status": "pending_review"}, "Request received. If the details match an eligible student record, the school will review the request.")

    existing = collection(PORTAL_LINKS).find_one({
        "requester_type": requester_type,
        "requester_user_id": uid,
        "school_id": str(school["_id"]),
        "student_id": str(student["_id"]),
        "status": {"$in": ["pending_review", "verified"]},
    })
    if existing:
        return ok({"status": existing.get("status", "pending_review")}, "A request or verified link already exists for this student.")

    relationship = _text(payload.get("relationship", "parent"), 40).lower() if requester_type == "parent" else "student"
    if requester_type == "parent" and relationship not in {"parent", "guardian", "caregiver"}:
        raise APIError("Choose parent, legal guardian, or authorized caregiver.", 422, "validation_error")

    result = collection(PORTAL_LINKS).insert_one({
        "requester_type": requester_type,
        "requester_user_id": uid,
        "school_id": str(school["_id"]),
        "school_name": _text(school.get("name"), 180),
        "student_id": str(student["_id"]),
        "relationship": relationship,
        "contact_match": contact_match,
        "notes": _text(payload.get("notes"), MAX_NOTES),
        "status": "pending_review",
        "created_at": _now(),
        "updated_at": _now(),
        "reviewed_at": None,
        "reviewed_by": None,
    })
    return created({"request_id": str(result.inserted_id), "status": "pending_review"}, "Request submitted. The school must verify the relationship before private student records become available.")


def _school_owner_record():
    uid = str(current_user_id())
    verified_values = list({"verified", str(getattr(school_verification, "VERIFIED", "verified"))})
    school = collection(SCHOOLS).find_one({
        "owner_user_id": uid,
        "status": "active",
        "verification_status": {"$in": verified_values},
        "is_demo": {"$ne": True},
    })
    if not school:
        raise APIError("Only the owner of a verified, active school can review portal requests.", 403, "school_owner_required")
    return school


def _verified_parent_link(student_id):
    uid = str(current_user_id())
    link = collection(PORTAL_LINKS).find_one({
        "requester_type": "parent",
        "requester_user_id": uid,
        "student_id": str(student_id),
        "status": "verified",
    })
    if not link:
        raise APIError("A verified guardian link is required for this student.", 403, "guardian_link_required")
    return link


def _student_for_current_user():
    uid = str(current_user_id())
    matches = list(collection(STUDENTS).find({
        "student_user_id": uid,
        "status": "active",
    }).limit(2))
    if not matches:
        return None
    if len(matches) > 1:
        raise APIError("More than one student record is linked to this account. Contact the school to resolve the duplicate link.", 409, "multiple_student_links")
    return matches[0]


def _school_record(school_id):
    conditions = [{"_id": str(school_id)}, {"school_id": str(school_id)}]
    try:
        conditions.append({"_id": ObjectId(str(school_id))})
    except (InvalidId, TypeError, ValueError):
        pass
    return collection(SCHOOLS).find_one({"$or": conditions})


def _public_payment_accounts(school_id):
    school = _school_record(school_id) or {}
    settings = school.get("settings") if isinstance(school.get("settings"), dict) else {}
    finance = settings.get("finance") if isinstance(settings.get("finance"), dict) else {}
    accounts = finance.get("payment_accounts") if isinstance(finance.get("payment_accounts"), list) else []
    fields = (
        "id", "type", "label", "account_name", "account_number", "paybill",
        "till", "bank_name", "branch", "account_reference", "instructions",
        "currency", "active",
    )
    return [
        {key: account.get(key) for key in fields if key in account}
        for account in accounts
        if isinstance(account, dict) and account.get("active") is not False
    ]


def _school_name(school_id):
    try:
        oid = ObjectId(str(school_id))
    except (InvalidId, TypeError, ValueError):
        return ""
    school = collection(SCHOOLS).find_one({"_id": oid}, {"name": 1})
    return _text(school.get("name"), 180) if school else ""


def _attendance_summary(student):
    sid = str(student["_id"])
    docs = list(collection(ATTENDANCE).find({
        "school_id": str(student.get("school_id", "")),
        "student_id": sid,
    }).limit(1000))
    counts = {"present": 0, "absent": 0, "late": 0, "excused": 0}
    for row in docs:
        status = _text(row.get("status"), 30).lower()
        if status in counts:
            counts[status] += 1
    total = sum(counts.values())
    counts["total_sessions"] = total
    counts["attendance_rate"] = round(((counts["present"] + counts["late"]) / total) * 100, 1) if total else None
    return counts


def _student_assignments(student, limit=20):
    query = {"school_id": str(student.get("school_id", "")), "status": {"$ne": "archived"}}
    class_name = _text(student.get("class_name"), 100)
    if class_name:
        query["class_name"] = class_name
    return list(collection(ASSIGNMENTS).find(query).sort("created_at", -1).limit(limit))


def _student_assessments(student, limit=20):
    return list(collection(ASSESSMENTS).find({
        "school_id": str(student.get("school_id", "")),
        "student_id": str(student["_id"]),
    }).sort("created_at", -1).limit(limit))


def _student_timetable_entries(student):
    school_id = str(student.get("school_id", ""))
    class_id = _text(student.get("class_id"), 100)
    if not school_id or not class_id:
        return []
    # Entry documents use class_id/timetable_id (not class_name), and only
    # entries attached to a published master timetable may reach students.
    published = list(collection(TIMETABLES_COLLECTION).find({
        "school_id": school_id,
        "status": "published",
    }, {"_id": 1}).limit(100))
    timetable_ids = [str(item.get("_id")) for item in published]
    if not timetable_ids:
        return []
    return list(collection(TIMETABLE_ENTRIES).find({
        "school_id": school_id,
        "class_id": class_id,
        "timetable_id": {"$in": timetable_ids},
    }).sort([("day", 1), ("start_time", 1)]).limit(100))


def _student_documents(student, parent=False):
    sid = str(student["_id"])
    visibility_fields = [
        {"parent_visible": True},
        {"visible_to_parents": True},
    ] if parent else [
        {"student_visible": True},
        {"visible_to_students": True},
    ]
    return list(collection(PUBLIC_DOCUMENTS).find({
        "school_id": str(student.get("school_id", "")),
        "student_id": sid,
        "$or": visibility_fields,
        "status": {"$in": ["published", "active"]},
    }).sort("created_at", -1).limit(100))


def _safe_document(item):
    return {
        "id": str(item.get("_id", "")),
        "title": _text(item.get("title") or item.get("name") or item.get("filename"), 180),
        "description": _text(item.get("description"), 1000),
        "category": _text(item.get("category"), 80),
        "document_type": _text(item.get("document_type"), 80),
        "download_url": _text(item.get("download_url") or item.get("url"), 1200),
        "created_at": _ser(item.get("created_at")),
    }


def _safe_assignment(item):
    return {
        "id": str(item.get("_id", "")),
        "title": _text(item.get("title") or item.get("name"), 180),
        "description": _text(item.get("description"), 1200),
        "subject": _text(item.get("subject"), 100),
        "class_name": _text(item.get("class_name"), 100),
        "due_date": _ser(item.get("due_date")),
        "status": _text(item.get("status"), 40),
        "created_at": _ser(item.get("created_at")),
    }


def _safe_assessment(item):
    return {
        "id": str(item.get("_id", "")),
        "title": _text(item.get("title") or item.get("name"), 180),
        "subject": _text(item.get("subject"), 100),
        "score": item.get("score", item.get("marks_obtained")),
        "total_marks": item.get("total_marks", item.get("maximum_score")),
        "status": _text(item.get("status"), 40),
        "assessed_at": _ser(item.get("assessed_at") or item.get("created_at")),
    }


# ============================================================================
# PARENT / GUARDIAN PORTAL
# ============================================================================

@parent_bp.get("/children")
@require_authenticated
def parent_children():
    uid = str(current_user_id())
    links = list(collection(PORTAL_LINKS).find({
        "requester_type": "parent",
        "requester_user_id": uid,
        "status": {"$in": ["pending_review", "verified", "rejected"]},
    }).sort("created_at", -1).limit(MAX_LIST))
    children = []
    for link in links:
        state = _text(link.get("status"), 40).lower()
        if state == "verified":
            try:
                student = collection(STUDENTS).find_one({
                    "_id": ObjectId(str(link.get("student_id", ""))),
                    "school_id": str(link.get("school_id", "")),
                    "status": {"$in": ["active", "inactive", "graduated"]},
                })
            except (InvalidId, TypeError, ValueError):
                student = None
            if not student:
                continue
            item = _project_student(student, _text(link.get("school_name"), 180))
            item.update({"link_status": "verified", "verification_status": "verified", "relationship": link.get("relationship", "parent"), "link_id": str(link["_id"])})
            children.append(item)
        else:
            # Pending/rejected responses intentionally contain no student name,
            # admission number, class, or other information to enumerate records.
            children.append({
                "id": str(link["_id"]),
                "display_name": "Student link request",
                "class_name": "Details hidden until verification",
                "school_name": _text(link.get("school_name"), 180),
                "link_status": state,
                "verification_status": state,
                "relationship": link.get("relationship", "parent"),
            })
    return ok({"children": children})


@parent_bp.post("/children/link")
@require_authenticated
def parent_link_child():
    return _request_link("parent", _json_body())


@parent_bp.get("/children/<student_id>")
@require_authenticated
def parent_child_profile(student_id):
    link = _verified_parent_link(student_id)
    try:
        student_oid = ObjectId(str(student_id))
    except (InvalidId, TypeError, ValueError):
        raise APIError("Student not found.", 404, "student_not_found")
    student = collection(STUDENTS).find_one({
        "_id": student_oid,
        "school_id": str(link.get("school_id", "")),
        "status": {"$in": ["active", "inactive", "graduated"]},
    })
    if not student:
        raise APIError("Student not found.", 404, "student_not_found")
    projected = _project_student(student, _text(link.get("school_name"), 180))
    return ok({"student": projected, "school_name": projected["school_name"], "link_status": "verified"})


@parent_bp.get("/children/<student_id>/documents")
@require_authenticated
def parent_child_documents(student_id):
    link = _verified_parent_link(student_id)
    student = collection(STUDENTS).find_one({
        "_id": _object_id(student_id, "student ID"),
        "school_id": str(link.get("school_id", "")),
        "status": {"$in": ["active", "inactive", "graduated"]},
    })
    if not student:
        raise APIError("Student not found.", 404, "student_not_found")
    documents = [_safe_document(item) for item in _student_documents(student, parent=True)]
    certificate = collection(CERTIFICATES).find_one({
        "school_id": str(student.get("school_id", "")),
        "student_id": str(student["_id"]),
        "certificate_type": "course_completion",
        "status": "issued",
    })
    if certificate:
        documents.insert(0, {
            "id": str(certificate.get("certificate_code") or certificate.get("_id") or ""),
            "title": "Course completion certificate",
            "description": f"Congratulations! Certificate for { _text(certificate.get('student_name'), 160) or 'the student' } · { _text(certificate.get('course_name'), 140) or 'completed course' }",
            "document_type": "completion_certificate",
            "certificate_code": _text(certificate.get("certificate_code"), 80),
            "created_at": _ser(certificate.get("issued_at")),
            "downloadable": True,
        })
    return ok({"documents": documents})


@parent_bp.get("/children/<student_id>/finance")
@require_authenticated
def parent_child_finance(student_id):
    link = _verified_parent_link(student_id)
    student = collection(STUDENTS).find_one({
        "_id": _object_id(student_id, "student ID"),
        "school_id": str(link.get("school_id", "")),
        "status": "active",
    })
    if not student:
        raise APIError("Student not found.", 404, "student_not_found")
    school_id = str(student.get("school_id", ""))
    fees = list(collection(FEES).find({
        "school_id": school_id,
        "student_id": str(student["_id"]),
    }).sort("created_at", -1).limit(500))
    total_due = 0.0
    total_paid = 0.0
    result = []
    for fee in fees:
        amount = _number(fee.get("amount"))
        paid = _number(fee.get("amount_paid") if fee.get("amount_paid") is not None else fee.get("paid_amount"))
        balance = max(amount - paid, 0)
        total_due += balance
        total_paid += max(paid, 0)
        result.append({
            "id": str(fee.get("_id", "")),
            "title": _text(fee.get("title") or fee.get("description") or fee.get("fee_type"), 180),
            "description": _text(fee.get("description") or fee.get("title"), 180),
            "fee_type": _text(fee.get("fee_type") or fee.get("category") or fee.get("title"), 80),
            "term": _text(fee.get("term"), 50),
            "academic_year": _text(fee.get("academic_year"), 30),
            "amount": amount,
            "paid_amount": paid,
            "balance": balance,
            "status": _text(fee.get("status"), 40),
            "due_date": _ser(fee.get("due_date")),
            "date": _ser(fee.get("created_at") or fee.get("date")),
            "currency": _text(fee.get("currency") or "KES", 8),
        })
    return ok({
        "student": _project_student(student, _text(link.get("school_name"), 180)),
        "fees": result,
        "total_due": round(total_due, 2),
        "total_paid": round(total_paid, 2),
        "payment_accounts": _public_payment_accounts(school_id),
        "payment_mode": "manual_receipt_review",
        "payment_notice": "Use the school's listed instructions and submit proof for review. The portal does not claim a provider-confirmed online payment until a payment gateway is connected.",
    })


@parent_bp.post("/children/<student_id>/finance/receipts")
@require_authenticated
def parent_submit_fee_receipt(student_id):
    link = _verified_parent_link(student_id)
    student = collection(STUDENTS).find_one({
        "_id": _object_id(student_id, "student ID"),
        "school_id": str(link.get("school_id", "")),
        "status": "active",
    })
    if not student:
        raise APIError("Student not found.", 404, "student_not_found")

    payload = _json_body()
    fee_id = _text(payload.get("fee_id"), 160)
    if not fee_id:
        raise APIError("Choose a fee statement line before submitting a receipt.", 422, "fee_required")
    method = _text(payload.get("payment_method"), 20).lower()
    if method not in {"mpesa", "bank"}:
        raise APIError("payment_method must be mpesa or bank.", 422, "validation_error")
    try:
        amount = float(payload.get("amount"))
    except (TypeError, ValueError):
        amount = 0.0
    if not math.isfinite(amount) or amount <= 0 or amount > 1000000000:
        raise APIError("Enter a valid positive receipt amount.", 422, "validation_error")
    reference = _text(payload.get("payment_reference"), 120)
    receipt_url = _text(payload.get("receipt_url"), 500)
    notes = _text(payload.get("notes"), 800)
    if not reference and not receipt_url:
        raise APIError("Enter the M-Pesa/bank reference or attach a receipt URL.", 422, "receipt_evidence_required")
    if receipt_url:
        parsed = urlparse(receipt_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise APIError("Receipt URL must use HTTPS.", 422, "invalid_receipt_url")

    school_id = str(student.get("school_id", ""))
    conditions = [{"_id": candidate} for candidate in ([fee_id, _object_id(fee_id, "fee ID")] if ObjectId.is_valid(fee_id) else [fee_id])]
    fee = collection(FEES).find_one({
        "school_id": school_id,
        "student_id": str(student["_id"]),
        "$or": conditions,
    })
    if not fee:
        raise APIError("The selected fee record does not belong to this student.", 404, "fee_not_found")
    total = _number(fee.get("amount"))
    paid = _number(fee.get("amount_paid") if fee.get("amount_paid") is not None else fee.get("paid_amount"))
    balance = max(total - paid, 0)
    if amount > balance + 0.0001:
        raise APIError("Receipt amount exceeds the outstanding balance.", 422, "receipt_exceeds_balance")

    receipts_collection = collection("jumuiya_elimu_fee_receipts")
    duplicate = None
    if reference:
        duplicate = receipts_collection.find_one({
            "school_id": school_id,
            "payment_reference": reference,
            "status": {"$in": ["pending", "approved"]},
        })
    if duplicate:
        raise APIError("This payment reference has already been submitted to the school.", 409, "duplicate_payment_reference")

    now = _now()
    receipt = {
        "school_id": school_id,
        "student_id": str(student["_id"]),
        "student_name": _text(student.get("full_name"), 160),
        "admission_number": _text(student.get("admission_number"), 80),
        "fee_id": str(fee.get("_id") or fee_id),
        "fee_type": _text(fee.get("fee_type") or fee.get("title") or fee.get("description"), 80),
        "parent_user_id": str(current_user_id()),
        "payment_method": method,
        "amount": round(amount, 2),
        "currency": _text(fee.get("currency") or "KES", 8),
        "payment_reference": reference,
        "receipt_url": receipt_url,
        "notes": notes,
        "status": "pending",
        "submitted_at": now,
        "created_at": now,
        "updated_at": now,
    }
    result = receipts_collection.insert_one(receipt)
    receipt["_id"] = result.inserted_id

    try:
        school = _school_record(school_id) or {}
        owner_id = str(school.get("owner_user_id") or school.get("owner_id") or "")
        if owner_id:
            from backend.jumuiya.notifications.services import notify
            notify(owner_id, {
                "title": "School fee receipt awaiting review",
                "message": f"A parent submitted a {method.upper()} receipt for {receipt['student_name'] or 'a student'} ({receipt['admission_number'] or 'no admission number'}).",
                "type": "action_needed",
                "data": {"school_id": school_id, "student_id": str(student["_id"]), "receipt_id": str(result.inserted_id)},
            })
    except Exception:
        pass

    return created({
        "receipt": _ser(receipt),
        "status": "pending",
        "payment_notice": "Receipt submitted for school review; this is not confirmation that the external payment has settled.",
    }, "Fee receipt submitted for school review.")




@parent_bp.get("/children/<student_id>/completion-certificate")
@require_authenticated
def parent_download_completion_certificate(student_id):
    link = _verified_parent_link(student_id)
    student = collection(STUDENTS).find_one({
        "_id": _object_id(student_id, "student ID"),
        "school_id": str(link.get("school_id", "")),
    })
    if not student:
        raise APIError("Student not found.", 404, "student_not_found")
    certificate = collection(CERTIFICATES).find_one({
        "school_id": str(student.get("school_id", "")),
        "student_id": str(student["_id"]),
        "certificate_type": "course_completion",
        "status": "issued",
    })
    if not certificate or not certificate.get("pdf_bytes"):
        raise APIError("No completion certificate has been issued for this student yet.", 404, "certificate_not_found")
    content = bytes(certificate["pdf_bytes"])
    admission = re.sub(r"[^A-Za-z0-9_-]+", "-", _text(student.get("admission_number"), 60)) or str(student["_id"])
    return send_file(
        BytesIO(content),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{admission}-completion-certificate.pdf",
        max_age=0,
    )


@parent_bp.post("/children/<student_id>/inactivity-response")
@require_authenticated
def parent_respond_to_inactivity_reminder(student_id):
    link = _verified_parent_link(student_id)
    student = collection(STUDENTS).find_one({
        "_id": _object_id(student_id, "student ID"),
        "school_id": str(link.get("school_id", "")),
        "status": "inactive",
    })
    if not student:
        raise APIError("This student is no longer marked inactive or the record was not found.", 409, "inactive_student_not_found")
    lifecycle = student.get("lifecycle") if isinstance(student.get("lifecycle"), dict) else {}
    if not lifecycle.get("parent_reminder_sent_at"):
        raise APIError("No inactivity reminder is awaiting a response.", 409, "inactivity_response_not_expected")
    if lifecycle.get("parent_response_at"):
        raise APIError("A response has already been recorded for this reminder.", 409, "inactivity_already_responded")
    payload = _json_body()
    response_kind = _text(payload.get("response"), 40).lower()
    if response_kind not in {"still_enrolled", "withdrawn", "please_contact_me"}:
        raise APIError("response must be still_enrolled, withdrawn, or please_contact_me.", 422, "invalid_inactivity_response")
    notes = _text(payload.get("notes"), 800)
    now = _now()
    collection(STUDENTS).update_one(
        {"_id": student["_id"], "school_id": str(student.get("school_id", "")), "status": "inactive", "lifecycle.parent_response_at": {"$exists": False}},
        {"$set": {
            "lifecycle.parent_response_at": now,
            "lifecycle.parent_response_kind": response_kind,
            "lifecycle.parent_response_notes": notes,
            "lifecycle.review_status": "parent_responded",
            "updated_at": now,
        }},
    )
    school_id = str(student.get("school_id", ""))
    notify_message = {
        "still_enrolled": "The parent/guardian confirms the learner is still enrolled and requests a status review.",
        "withdrawn": "The parent/guardian reports the learner has withdrawn. The registrar should verify details before closing the enrolment record.",
        "please_contact_me": "The parent/guardian responded to the inactivity reminder and requests contact from the school.",
    }[response_kind]
    for member in collection(MEMBERS).find({
        "school_id": school_id,
        "status": "active",
        "role": {"$in": ["registrar", "owner", "principal"]},
    }).limit(200):
        try:
            from backend.jumuiya.notifications.services import notify
            notify(str(member.get("user_id") or ""), {
                "title": "Parent responded to student inactivity reminder",
                "message": f"{_text(student.get('full_name'), 160) or 'A student'}: {notify_message}" + (f" Parent notes: {notes}" if notes else ""),
                "type": "action_needed",
                "data": {"school_id": school_id, "student_id": str(student["_id"]), "parent_response": response_kind},
            })
        except Exception:
            pass
    return ok({"recorded": True, "response": response_kind, "responded_at": now.isoformat()}, "Your response has been sent to the school for review.")



# ============================================================================
# STUDENT PORTAL
# ============================================================================

@student_bp.post("/link")
@require_authenticated
def student_request_link():
    return _request_link("student", _json_body())


@student_bp.get("/dashboard")
@require_authenticated
def student_dashboard():
    student = _student_for_current_user()
    if not student:
        return ok({"linked": False, "student": None, "school": None, "class_info": None, "summary": {}, "recent_assignments": [], "upcoming_events": [], "recent_assessments": [], "message": "This account is not yet linked to an active Elimu student record."})
    assignments = _student_assignments(student, 10)
    assessments = _student_assessments(student, 10)
    attendance = _attendance_summary(student)
    school_name = _school_name(student.get("school_id"))
    class_name = _text(student.get("class_name"), 100)
    events = list(collection(EVENTS).find({
        "school_id": str(student.get("school_id", "")),
        "status": {"$nin": ["cancelled", "archived"]},
        "visibility": {"$in": ["public", "community", "school"]},
    }).sort("start_date", 1).limit(5))
    return ok({
        "linked": True,
        "student": _project_student(student, school_name),
        "school": {"name": school_name},
        "class_info": {"name": class_name},
        "summary": {
            "pending_assignments": sum(1 for item in assignments if _text(item.get("status"), 30).lower() not in {"submitted", "graded", "completed"}),
            "lessons_available": collection(LESSONS).count_documents({"school_id": str(student.get("school_id", "")), "class_name": class_name, "status": "published"}) if class_name else 0,
            "attendance_rate": attendance.get("attendance_rate"),
            "assessments_count": len(assessments),
        },
        "attendance": attendance,
        "assignments": [_safe_assignment(item) for item in assignments],
        "recent_assignments": [_safe_assignment(item) for item in assignments[:5]],
        "assessments": [_safe_assessment(item) for item in assessments],
        "recent_assessments": [_safe_assessment(item) for item in assessments[:5]],
        "timetable": [_ser(item) for item in _student_timetable_entries(student)],
        "documents": [_safe_document(item) for item in _student_documents(student, parent=False)],
        "upcoming_events": [{"id": str(item.get("_id", "")), "title": _text(item.get("title") or item.get("name"), 180), "description": _text(item.get("description"), 1000), "start_at": _ser(item.get("start_date") or item.get("start_at")), "location": _text(item.get("location") or item.get("venue"), 180)} for item in events],
    })


@student_bp.get("/lessons")
@require_authenticated
def student_lessons():
    student = _student_for_current_user()
    if not student:
        raise APIError("Submit a student-link request and wait for school verification before accessing lessons.", 403, "student_link_required")
    class_name = _text(student.get("class_name"), 100)
    query = {"school_id": str(student.get("school_id", "")), "status": "published"}
    if class_name:
        query["class_name"] = class_name
    lessons = list(collection(LESSONS).find(query).sort("created_at", -1).limit(100))
    return ok({"lessons": [{"id": str(item.get("_id", "")), "title": _text(item.get("title"), 180), "subject": _text(item.get("subject"), 100), "description": _text(item.get("description"), 1200), "content": _text(item.get("content"), 8000), "created_at": _ser(item.get("created_at"))} for item in lessons]})


@student_bp.get("/assignments")
@require_authenticated
def student_assignments():
    student = _student_for_current_user()
    if not student:
        raise APIError("Submit a student-link request and wait for school verification before accessing assignments.", 403, "student_link_required")
    return ok({"assignments": [_safe_assignment(item) for item in _student_assignments(student, 100)]})


@student_bp.get("/assessments")
@require_authenticated
def student_assessments():
    student = _student_for_current_user()
    if not student:
        raise APIError("Submit a student-link request and wait for school verification before accessing assessments.", 403, "student_link_required")
    return ok({"assessments": [_safe_assessment(item) for item in _student_assessments(student, 100)]})


@student_bp.get("/attendance")
@require_authenticated
def student_attendance():
    student = _student_for_current_user()
    if not student:
        raise APIError("Submit a student-link request and wait for school verification before accessing attendance.", 403, "student_link_required")
    return ok({"attendance": _attendance_summary(student)})


@student_bp.get("/timetable")
@require_authenticated
def student_timetable():
    student = _student_for_current_user()
    if not student:
        raise APIError("Submit a student-link request and wait for school verification before accessing the timetable.", 403, "student_link_required")
    return ok({"timetable": [_ser(item) for item in _student_timetable_entries(student)]})


@student_bp.get("/documents")
@require_authenticated
def student_documents():
    student = _student_for_current_user()
    if not student:
        raise APIError("Submit a student-link request and wait for school verification before accessing documents.", 403, "student_link_required")
    return ok({"documents": [_safe_document(item) for item in _student_documents(student, parent=False)]})


# ============================================================================
# SCHOOL OWNER REVIEW QUEUE
# ============================================================================

@portal_review_bp.get("/requests")
@require_authenticated
def list_portal_requests():
    school = _school_owner_record()
    sid = str(school["_id"])
    docs = list(collection(PORTAL_LINKS).find({"school_id": sid, "status": "pending_review"}).sort("created_at", -1).limit(MAX_LIST))
    result = []
    for link in docs:
        student = None
        try:
            if link.get("student_id"):
                student = collection(STUDENTS).find_one({"_id": ObjectId(str(link["student_id"])), "school_id": sid})
        except (InvalidId, TypeError, ValueError):
            student = None
        result.append({
            "id": str(link["_id"]),
            "requester_type": _text(link.get("requester_type"), 30),
            "requester_user_id": _text(link.get("requester_user_id"), 160),
            "relationship": _text(link.get("relationship"), 40),
            "contact_match": _text(link.get("contact_match"), 30),
            "notes": _text(link.get("notes"), MAX_NOTES),
            "status": _text(link.get("status"), 40),
            "student": {"id": str(student["_id"]), "full_name": _text(student.get("full_name"), 160), "admission_number": _text(student.get("admission_number"), 80), "class_name": _text(student.get("class_name"), 100)} if student else None,
            "created_at": _ser(link.get("created_at")),
        })
    return ok({"requests": result, "count": len(result)})


@portal_review_bp.post("/requests/<request_id>/review")
@require_authenticated
def review_portal_request(request_id):
    school = _school_owner_record()
    sid = str(school["_id"])
    oid = _object_id(request_id, "request ID")
    payload = _json_body()
    decision = _text(payload.get("decision"), 40).lower()
    if decision not in {"approve", "verify", "verified", "reject", "rejected"}:
        raise APIError("Decision must be approve or reject.", 422, "validation_error")
    link = collection(PORTAL_LINKS).find_one({"_id": oid, "school_id": sid, "status": "pending_review"})
    if not link:
        raise APIError("The pending portal request was not found.", 404, "portal_request_not_found")
    approve = decision in {"approve", "verify", "verified"}
    if approve and link.get("requester_type") == "student":
        try:
            student_oid = ObjectId(str(link.get("student_id", "")))
        except (InvalidId, TypeError, ValueError):
            raise APIError("The student record is no longer available.", 409, "student_link_conflict")
        existing = collection(STUDENTS).find_one({"_id": student_oid, "school_id": sid, "status": "active"})
        if not existing:
            raise APIError("The student record is no longer active.", 409, "student_link_conflict")
        linked_user = _text(existing.get("student_user_id"), 160)
        requester = str(link.get("requester_user_id", ""))
        if linked_user and linked_user != requester:
            raise APIError("This student record is already linked to another account.", 409, "student_already_linked")
        collection(STUDENTS).update_one({"_id": student_oid, "school_id": sid}, {"$set": {"student_user_id": requester, "updated_at": _now()}})
    status = "verified" if approve else "rejected"
    collection(PORTAL_LINKS).update_one({"_id": oid, "school_id": sid, "status": "pending_review"}, {"$set": {"status": status, "reviewed_at": _now(), "reviewed_by": str(current_user_id()), "updated_at": _now()}})
    return ok({"id": str(oid), "status": status}, "Portal request approved." if approve else "Portal request rejected.")
