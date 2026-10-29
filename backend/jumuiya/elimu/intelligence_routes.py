"""Elimu intelligence endpoints built on the existing school and fee records.

The fee-risk score is an explainable heuristic, not a machine-learning
claim or a basis for automatic punishment. The register export is a review
template to map against the current official KEMIS/NEMIS import contract;
it does not submit data to government systems.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from math import isfinite
from typing import Any
import hashlib
import io
import os
import secrets
from urllib.parse import urlsplit

from bson import ObjectId
from flask import Blueprint, request, send_file

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import ok
from backend.jumuiya.elimu.permissions import authorize


intelligence_bp = Blueprint(
    "jumuiya_elimu_intelligence",
    __name__,
    url_prefix="/intelligence",
)

SCHOOLS = "jumuiya_schools"
STUDENTS = "jumuiya_students"
FEES = "jumuiya_fees"
MAX_STUDENTS = 10000
MAX_FEE_ROWS = 20000


def _text(value: Any, limit: int = 240) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _money(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return round(max(0.0, number), 2) if isfinite(number) else 0.0


def _school_query(school_id: str) -> dict:
    alternatives = [{"_id": school_id}, {"school_id": school_id}]
    if ObjectId.is_valid(school_id):
        alternatives.append({"_id": ObjectId(school_id)})
    return {"$or": alternatives}


def _member_and_school(permission: str, roles: set[str]) -> tuple[dict, dict, str]:
    user_id = current_user_id()
    member = authorize(user_id, permission)
    role = _text(member.get("role"), 40).lower()
    if role not in roles:
        raise APIError(
            "Your Elimu role cannot access this intelligence workspace.",
            403,
            "elimu_intelligence_role_required",
        )

    school_id = _text(member.get("school_id"), 160)
    if not school_id:
        raise APIError("Your active school membership has no school ID.", 403, "school_membership_required")

    school = collection(SCHOOLS).find_one(_school_query(school_id))
    if not school:
        raise APIError("School not found for this membership.", 404, "school_not_found")
    return member, school, school_id


def _student_key(student: dict) -> str:
    return _text(student.get("_id") or student.get("id"), 160)


def _index_fees(fee_rows: list[dict]) -> dict[str, list[tuple[int, dict]]]:
    """Index fee rows using the same student-ID/admission-number rules as Elimu finance."""
    index: dict[str, list[tuple[int, dict]]] = {}
    for row_number, fee in enumerate(fee_rows):
        student_ref = _text(fee.get("student_id"), 160)
        key = student_ref or _text(fee.get("admission_number"), 120)
        if key:
            index.setdefault(key, []).append((row_number, fee))
    return index


def _fees_for_student(student: dict, fee_index: dict[str, list[tuple[int, dict]]]) -> list[dict]:
    """Retrieve matching fee records in near-linear time instead of scanning every row per student."""
    keys = {_student_key(student), _text(student.get("admission_number"), 120)}
    seen: set[int] = set()
    result: list[dict] = []
    for key in keys:
        if not key:
            continue
        for row_number, fee in fee_index.get(key, []):
            if row_number not in seen:
                seen.add(row_number)
                result.append(fee)
    return result


def _fee_amounts(fee: dict) -> tuple[float, float, float]:
    required = _money(fee.get("amount", fee.get("amount_required")))
    paid_raw = fee.get("amount_paid")
    if paid_raw is None:
        paid_raw = fee.get("paid_amount")
    paid = min(required, _money(paid_raw))
    return required, paid, round(max(required - paid, 0.0), 2)


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = _text(value, 40)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _term_key(fee: dict) -> str:
    year = _text(fee.get("academic_year") or fee.get("year"), 40)
    term = _text(fee.get("term") or fee.get("period"), 40)
    if year or term:
        return f"{year}:{term}"
    return _text(fee.get("due_date") or fee.get("created_at"), 40)[:10] or "unspecified"


def _risk_for_student(student: dict, matching: list[dict], today: date) -> dict:
    required_total = 0.0
    paid_total = 0.0
    balance_total = 0.0
    flagged_overdue_terms: set[str] = set()
    overdue_rows = 0
    voteheads: dict[str, dict] = {}

    for fee in matching:
        required, paid, balance = _fee_amounts(fee)
        required_total += required
        paid_total += paid
        balance_total += balance
        status = _text(fee.get("status"), 40).lower().replace("-", "_")
        due = _date_value(fee.get("due_date"))
        is_overdue = balance > 0 and (
            status in {"overdue", "past_due", "late", "defaulted"}
            or (due is not None and due < today)
        )
        if is_overdue:
            overdue_rows += 1
            flagged_overdue_terms.add(_term_key(fee))

        label = _text(fee.get("fee_type") or fee.get("votehead") or fee.get("description"), 100) or "Unclassified fees"
        bucket = voteheads.setdefault(label, {"votehead": label, "required": 0.0, "paid": 0.0, "balance": 0.0, "records": 0})
        bucket["required"] += required
        bucket["paid"] += paid
        bucket["balance"] += balance
        bucket["records"] += 1

    required_total = round(required_total, 2)
    paid_total = round(paid_total, 2)
    balance_total = round(balance_total, 2)
    ratio = balance_total / required_total if required_total > 0 else 0.0

    if not matching:
        score = None
        risk = "insufficient_data"
        reasons = ["No fee records are available for this student."]
        confidence = "insufficient"
    else:
        score = 0
        reasons = []
        if overdue_rows:
            score += 25
            reasons.append(f"{overdue_rows} fee record(s) are overdue or past their due date.")
        if len(flagged_overdue_terms) >= 2:
            score += 30
            reasons.append("Arrears are recorded across multiple terms or periods.")
        elif len(flagged_overdue_terms) == 1:
            score += 15
            reasons.append("Arrears are recorded for at least one term or period.")
        if ratio >= 0.50:
            score += 25
            reasons.append("At least half of recorded fees remain outstanding.")
        elif ratio >= 0.20:
            score += 15
            reasons.append("A material share of recorded fees remains outstanding.")
        elif balance_total > 0:
            score += 7
            reasons.append("A fee balance remains outstanding.")
        if paid_total <= 0 and required_total > 0:
            score += 10
            reasons.append("No payment is recorded against these fee records.")
        score = min(100, score)
        risk = "high" if score >= 65 else ("moderate" if score >= 35 else "low")
        distinct_periods = {_term_key(fee) for fee in matching}
        confidence = "moderate" if len(matching) >= 3 and len(distinct_periods) >= 2 else "low"
        if not reasons:
            reasons.append("No current arrears signal was found in the available fee records.")

    return {
        "student_id": _student_key(student),
        "admission_number": _text(student.get("admission_number"), 120),
        "student_name": _text(student.get("full_name") or student.get("name"), 160) or "Unnamed student",
        "class_name": _text(student.get("class_name") or student.get("stream"), 100) or "Not assigned",
        "fee_records": len(matching),
        "terms_observed": len({_term_key(fee) for fee in matching}),
        "amount_required": required_total,
        "amount_paid": paid_total,
        "balance": balance_total,
        "overdue_records": overdue_rows,
        "risk_score": score,
        "risk_band": risk,
        "confidence": confidence,
        "reasons": reasons,
    }


@intelligence_bp.get("/fee-risk")
@require_authenticated
def fee_risk():
    """Return explainable fee-risk signals and votehead totals for one school."""
    _, school, school_id = _member_and_school(
        "fees.view",
        {"owner", "principal", "bursar"},
    )

    students_cursor = collection(STUDENTS).find({
        "school_id": school_id,
        "status": "active",
    }).limit(MAX_STUDENTS + 1)
    students = list(students_cursor)
    students_truncated = len(students) > MAX_STUDENTS
    students = students[:MAX_STUDENTS]

    fees_cursor = collection(FEES).find({"school_id": school_id}).limit(MAX_FEE_ROWS + 1)
    fee_rows = list(fees_cursor)
    fees_truncated = len(fee_rows) > MAX_FEE_ROWS
    fee_rows = fee_rows[:MAX_FEE_ROWS]
    fee_index = _index_fees(fee_rows)

    today = datetime.now(timezone.utc).date()
    rows = [_risk_for_student(student, _fees_for_student(student, fee_index), today) for student in students]
    rows.sort(key=lambda item: (
        {"high": 0, "moderate": 1, "low": 2, "insufficient_data": 3}.get(item["risk_band"], 4),
        -(item["risk_score"] if item["risk_score"] is not None else -1),
        item["student_name"].lower(),
    ))

    voteheads: dict[str, dict] = {}
    for student in students:
        for fee in _fees_for_student(student, fee_index):
            required, paid, balance = _fee_amounts(fee)
            label = _text(fee.get("fee_type") or fee.get("votehead") or fee.get("description"), 100) or "Unclassified fees"
            item = voteheads.setdefault(label, {"votehead": label, "required": 0.0, "paid": 0.0, "balance": 0.0, "records": 0})
            item["required"] += required
            item["paid"] += paid
            item["balance"] += balance
            item["records"] += 1

    votehead_rows = sorted([
        {**item, "required": round(item["required"], 2), "paid": round(item["paid"], 2), "balance": round(item["balance"], 2)}
        for item in voteheads.values()
    ], key=lambda item: item["votehead"].lower())

    assessed = [row for row in rows if row["risk_score"] is not None]
    summary = {
        "students": len(rows),
        "assessed": len(assessed),
        "high_risk": sum(1 for row in assessed if row["risk_band"] == "high"),
        "moderate_risk": sum(1 for row in assessed if row["risk_band"] == "moderate"),
        "low_risk": sum(1 for row in assessed if row["risk_band"] == "low"),
        "insufficient_data": sum(1 for row in rows if row["risk_band"] == "insufficient_data"),
        "required": round(sum(item["required"] for item in votehead_rows), 2),
        "paid": round(sum(item["paid"] for item in votehead_rows), 2),
        "balance": round(sum(item["balance"] for item in votehead_rows), 2),
    }

    return ok({
        "school": {
            "id": school_id,
            "name": _text(school.get("name") or school.get("school_name"), 160),
            "school_code": _text(school.get("school_code") or school.get("code"), 80),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "students": rows,
        "voteheads": votehead_rows,
        "methodology": {
            "name": "explainable_fee_risk_heuristic_v1",
            "description": "Signals are calculated from this school's stored fee amounts, payments, due dates, status, and period fields. They are not a trained AI model and should support human follow-up, not automatic exclusion or termination.",
            "confidence_note": "Confidence is marked low unless at least three fee records across two or more periods are available for a student.",
        },
        "truncated": {"students": students_truncated, "fee_records": fees_truncated},
    })


def _split_name(student: dict) -> tuple[str, str, str, str]:
    full_name = _text(student.get("full_name") or student.get("name"), 160)
    first = _text(student.get("first_name"), 80)
    middle = _text(student.get("middle_name"), 80)
    last = _text(student.get("last_name") or student.get("surname"), 80)
    if full_name and not any((first, middle, last)):
        parts = full_name.split()
        first = parts[0] if parts else ""
        last = parts[-1] if len(parts) > 1 else ""
        middle = " ".join(parts[1:-1]) if len(parts) > 2 else ""
    return full_name, first, middle, last


@intelligence_bp.get("/student-register-export")
@require_authenticated
def student_register_export():
    """Build a school-scoped CSV-ready register using the current student store."""
    user_id = current_user_id()
    _, school, school_id = _member_and_school(
        "students.view",
        {"owner", "principal", "registrar"},
    )

    cursor = collection(STUDENTS).find({
        "school_id": school_id,
        "status": "active",
    }).sort([("class_name", 1), ("full_name", 1)]).limit(MAX_STUDENTS + 1)
    students = list(cursor)
    truncated = len(students) > MAX_STUDENTS
    students = students[:MAX_STUDENTS]

    columns = [
        "school_code", "school_name", "upi", "nemis_number",
        "admission_number", "first_name", "middle_name", "last_name",
        "full_name", "gender", "date_of_birth", "class_name", "stream",
        "guardian_name", "guardian_phone", "guardian_email",
        "enrollment_date", "status",
    ]
    rows = []
    school_name = _text(school.get("name") or school.get("school_name"), 160)
    school_code = _text(school.get("school_code") or school.get("code"), 80)
    for student in students:
        full_name, first, middle, last = _split_name(student)
        rows.append({
            "school_code": school_code,
            "school_name": school_name,
            "upi": _text(student.get("upi") or student.get("upi_number") or student.get("unique_pupil_identifier"), 100),
            "nemis_number": _text(student.get("nemis_number") or student.get("nemis_id") or student.get("nemis_registration_number"), 100),
            "admission_number": _text(student.get("admission_number"), 120),
            "first_name": first,
            "middle_name": middle,
            "last_name": last,
            "full_name": full_name,
            "gender": _text(student.get("gender"), 30),
            "date_of_birth": _text(student.get("date_of_birth"), 40),
            "class_name": _text(student.get("class_name"), 100),
            "stream": _text(student.get("stream"), 80),
            "guardian_name": _text(student.get("guardian_name"), 160),
            "guardian_phone": _text(student.get("guardian_phone"), 80),
            "guardian_email": _text(student.get("guardian_email"), 254),
            "enrollment_date": _text(student.get("enrollment_date"), 40),
            "status": _text(student.get("status") or "active", 30),
        })

    log_action(
        user_id,
        "elimu.student_register.exported",
        "student_register",
        school_id,
        {
            "school_id": school_id,
            "row_count": len(rows),
            "truncated": truncated,
            "schema": "kenya_student_register_review_v1",
        },
    )

    return ok({
        "filename": "elimu-student-register-review.csv",
        "format": "csv",
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "official_submission": False,
        "mapping_note": "This is a CSV-ready school register template. Confirm the current official KEMIS/NEMIS import field names, required identifiers, and validation rules before uploading; this endpoint does not connect to or submit data to a government portal.",
    })


DOCUMENT_VERIFICATIONS = "jumuiya_elimu_document_verifications"


def _admission_student_query(school_id: str, student_id: str) -> dict:
    candidates: list[Any] = [student_id]
    if ObjectId.is_valid(student_id):
        candidates.append(ObjectId(student_id))
    return {
        "school_id": school_id,
        "$or": [
            {"_id": {"$in": candidates}},
            {"id": student_id},
        ],
    }


def _document_verification_url(token: str) -> str:
    """Build a QR URL against an explicitly HTTPS backend origin, never a Host header."""
    raw_origin = (
        os.getenv("ELIMU_DOCUMENT_VERIFY_BASE_URL", "").strip()
        or "https://revelacode-backend.onrender.com"
    )
    try:
        parsed = urlsplit(raw_origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("invalid verification origin")
        origin = f"https://{parsed.netloc}"
    except ValueError as exc:
        raise APIError(
            "Elimu document verification base URL must be a valid HTTPS origin.",
            503,
            "document_verification_not_configured",
        ) from exc
    return (
        origin
        + "/api/jumuiya/elimu/intelligence/verify-document/"
        + token
    )


def _pdf_text(value: Any, limit: int = 240) -> str:
    text = _text(value, limit)
    # ReportLab's built-in Helvetica is WinAnsi encoded. Replace unsupported
    # glyphs instead of allowing unusual Unicode to break PDF generation.
    return text.encode("cp1252", errors="replace").decode("cp1252")


@intelligence_bp.get("/students/<student_id>/admission-letter.pdf")
@require_authenticated
def download_admission_letter(student_id: str):
    """Generate and audit a school-scoped admission letter with a revocable QR token."""
    user_id = current_user_id()
    _, school, school_id = _member_and_school(
        "students.view",
        {"owner", "principal", "registrar"},
    )
    student = collection(STUDENTS).find_one(
        _admission_student_query(school_id, _text(student_id, 160))
    )
    if not student:
        raise APIError(
            "Student was not found in this school.",
            404,
            "student_not_found",
        )

    student_name = _pdf_text(
        student.get("full_name") or student.get("name")
        or " ".join(
            _text(student.get(key), 80)
            for key in ("first_name", "middle_name", "last_name")
            if _text(student.get(key), 80)
        ),
        180,
    ).strip()
    admission_number = _pdf_text(student.get("admission_number"), 100)
    class_name = _pdf_text(
        student.get("class_name") or student.get("stream") or "Not assigned",
        100,
    )
    if not student_name or not admission_number:
        raise APIError(
            "The learner must have a full name and admission number before an admission letter can be issued.",
            422,
            "admission_details_incomplete",
        )

    school_name = _pdf_text(
        school.get("name") or school.get("school_name") or "School",
        180,
    )
    school_code = _pdf_text(
        school.get("school_code") or school.get("code") or "",
        80,
    )
    issued_at = datetime.now(timezone.utc)
    document_id = "ELM-ADM-" + secrets.token_hex(6).upper()
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    verify_url = _document_verification_url(token)
    student_system_id = _student_key(student)
    enrollment_date = _pdf_text(student.get("enrollment_date"), 60) or "Not recorded"
    school_address = _pdf_text(
        school.get("address") or school.get("physical_address") or "",
        240,
    )

    # Build the PDF before persisting the verification token, so failed PDF
    # generation does not create a seemingly valid document without a file.
    try:
        import qrcode
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import ParagraphStyle
    except ImportError as exc:
        raise APIError(
            "Admission-letter PDF dependencies are not installed.",
            503,
            "document_generation_unavailable",
        ) from exc

    qr_image = qrcode.make(verify_url)
    qr_buffer = io.BytesIO()
    qr_image.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)

    pdf_buffer = io.BytesIO()
    page_width, page_height = A4
    pdf = canvas.Canvas(pdf_buffer, pagesize=A4)
    navy = colors.HexColor("#0A2342")
    blue = colors.HexColor("#0A74DA")
    muted = colors.HexColor("#526176")
    pale = colors.HexColor("#F2F6FB")
    margin = 48

    pdf.setFillColor(navy)
    pdf.rect(0, page_height - 96, page_width, 96, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(margin, page_height - 43, school_name[:48])
    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        margin,
        page_height - 61,
        ("School code: " + school_code) if school_code else "Jumuiya Elimu school record",
    )
    if school_address:
        pdf.setFillColor(colors.HexColor("#DCE7F5"))
        pdf.drawString(margin, page_height - 78, school_address[:90])

    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(margin, page_height - 135, "ADMISSION LETTER")
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(page_width - margin, page_height - 130, "Issued: " + issued_at.strftime("%d %B %Y"))
    pdf.drawRightString(page_width - margin, page_height - 145, "Ref: " + document_id)
    pdf.setStrokeColor(blue)
    pdf.setLineWidth(1.5)
    pdf.line(margin, page_height - 157, page_width - margin, page_height - 157)

    pdf.setFillColor(navy)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, page_height - 184, "Dear Parent/Guardian,")
    body_style = ParagraphStyle(
        "ElimuAdmissionBody",
        fontName="Helvetica",
        fontSize=10,
        leading=16,
        textColor=navy,
    )
    body = Paragraph(
        (
            f"We are pleased to confirm the admission of <b>{__import__('html').escape(student_name)}</b> "
            f"to <b>{__import__('html').escape(school_name)}</b>. Please retain this letter as a "
            "school-issued admission record. The document reference and QR code can be used to "
            "verify the record against RevelaCode Elimu."
        ),
        body_style,
    )
    _, body_height = body.wrap(page_width - margin * 2, 90)
    body.drawOn(pdf, margin, page_height - 202 - body_height)

    card_top = page_height - 232 - body_height
    card_height = 132
    pdf.setFillColor(pale)
    pdf.roundRect(margin, card_top - card_height, page_width - margin * 2, card_height, 10, fill=1, stroke=0)
    pdf.setFillColor(blue)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(margin + 16, card_top - 23, "LEARNER DETAILS")
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(margin + 16, card_top - 45, student_name[:70])
    pdf.setFont("Helvetica", 9)
    pdf.drawString(margin + 16, card_top - 64, "Admission number: " + admission_number[:70])
    pdf.drawString(margin + 16, card_top - 81, "Class / stream: " + class_name[:70])
    pdf.drawString(margin + 16, card_top - 98, "Enrolment date: " + enrollment_date[:60])
    pdf.drawString(margin + 16, card_top - 115, "Elimu system ID: " + student_system_id[:70])

    closing_y = card_top - card_height - 36
    closing_style = ParagraphStyle(
        "ElimuAdmissionClosing",
        fontName="Helvetica",
        fontSize=9,
        leading=14,
        textColor=navy,
    )
    closing = Paragraph(
        "Please contact the school office if any learner details on this letter require correction. "
        "This document confirms the record currently stored by the school; it is not a substitute "
        "for any separate government registration requirement.",
        closing_style,
    )
    _, closing_height = closing.wrap(page_width - margin * 2, 65)
    closing.drawOn(pdf, margin, closing_y - closing_height)

    sign_y = closing_y - closing_height - 45
    pdf.setStrokeColor(muted)
    pdf.setLineWidth(0.6)
    pdf.line(margin, sign_y, margin + 180, sign_y)
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin, sign_y - 14, "Authorised school representative")
    pdf.drawString(margin, sign_y - 27, "School stamp / signature")

    qr_size = 108
    qr_x = page_width - margin - qr_size
    qr_y = 70
    pdf.drawImage(ImageReader(qr_buffer), qr_x, qr_y, width=qr_size, height=qr_size, preserveAspectRatio=True, mask="auto")
    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(qr_x + qr_size / 2, qr_y - 13, "VERIFY DOCUMENT")
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(qr_x + qr_size / 2, qr_y - 25, "Scan the QR code")
    pdf.setStrokeColor(colors.HexColor("#DCE4EF"))
    pdf.line(margin, 42, page_width - margin, 42)
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(margin, 27, "Generated by RevelaCode Elimu | " + document_id)
    pdf.showPage()
    pdf.save()
    pdf_buffer.seek(0)

    collection(DOCUMENT_VERIFICATIONS).insert_one({
        "_id": token_hash,
        "document_id": document_id,
        "document_type": "admission_letter_v1",
        "school_id": school_id,
        "school_name": _text(school.get("name") or school.get("school_name") or "School", 180),
        "school_code": school_code,
        "student_id": student_system_id,
        "student_name": student_name,
        "admission_number": admission_number,
        "class_name": class_name,
        "status": "valid",
        "issued_at": issued_at,
        "issued_by": _text(user_id, 160),
    })

    try:
        log_action(
            user_id=user_id,
            action="elimu.admission_letter.generated",
            resource="elimu_document",
            resource_id=document_id,
            metadata={
                "school_id": school_id,
                "student_id": student_system_id,
                "document_type": "admission_letter_v1",
            },
        )
    except Exception:
        pass

    safe_admission = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in admission_number
    )[:60]
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"admission-letter-{safe_admission or 'student'}.pdf",
        max_age=0,
    )


@intelligence_bp.get("/verify-document/<token>")
def verify_admission_document(token: str):
    """Public, privacy-minimal QR verification endpoint for a school-issued document."""
    normalized_token = _text(token, 160)
    if not normalized_token or len(normalized_token) < 30:
        return ok({
            "verified": False,
            "status": "invalid",
            "message": "This admission document could not be verified.",
        })

    token_hash = hashlib.sha256(normalized_token.encode("utf-8")).hexdigest()
    record = collection(DOCUMENT_VERIFICATIONS).find_one({"_id": token_hash})
    if not record:
        return ok({
            "verified": False,
            "status": "invalid",
            "message": "This admission document could not be verified.",
        })
    if record.get("status") != "valid":
        return ok({
            "verified": False,
            "status": "revoked",
            "document_id": _text(record.get("document_id"), 80),
            "message": "This admission document has been revoked by the school.",
        })
    issued_at = record.get("issued_at")
    return ok({
        "verified": True,
        "status": "valid",
        "document_type": "admission_letter",
        "document_id": _text(record.get("document_id"), 80),
        "school_name": _text(record.get("school_name"), 180),
        "school_code": _text(record.get("school_code"), 80),
        "student_name": _text(record.get("student_name"), 180),
        "admission_number": _text(record.get("admission_number"), 100),
        "class_name": _text(record.get("class_name"), 100),
        "issued_at": issued_at.isoformat() if hasattr(issued_at, "isoformat") else _text(issued_at, 80),
        "message": "This admission document matches a school-issued Elimu record.",
    })


@intelligence_bp.post("/students/<student_id>/admission-letter/<document_id>/revoke")
@require_authenticated
def revoke_admission_letter(student_id: str, document_id: str):
    """Let authorized school leadership revoke a previously issued admission letter."""
    user_id = current_user_id()
    _, _, school_id = _member_and_school(
        "students.view",
        {"owner", "principal", "registrar"},
    )
    student = collection(STUDENTS).find_one(
        _admission_student_query(school_id, _text(student_id, 160))
    )
    if not student:
        raise APIError("Student was not found in this school.", 404, "student_not_found")

    verification = collection(DOCUMENT_VERIFICATIONS).find_one({
        "document_id": _text(document_id, 80),
        "school_id": school_id,
        "student_id": _student_key(student),
        "document_type": "admission_letter_v1",
        "status": "valid",
    })
    if not verification:
        raise APIError(
            "A valid admission letter for this learner was not found.",
            404,
            "admission_letter_not_found",
        )
    collection(DOCUMENT_VERIFICATIONS).update_one(
        {"_id": verification["_id"], "status": "valid", "school_id": school_id},
        {"$set": {
            "status": "revoked",
            "revoked_at": datetime.now(timezone.utc),
            "revoked_by": _text(user_id, 160),
        }},
    )
    try:
        log_action(
            user_id=user_id,
            action="elimu.admission_letter.revoked",
            resource="elimu_document",
            resource_id=_text(document_id, 80),
            metadata={"school_id": school_id, "student_id": _student_key(student)},
        )
    except Exception:
        pass
    return ok({
        "document_id": _text(document_id, 80),
        "status": "revoked",
    }, "Admission letter revoked.")
