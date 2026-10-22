"""Daily Elimu student lifecycle checks for Render Cron.

The job uses the existing Jumuiya Elimu collections and notifications store.
Student records are retained for audit; completed learners are graduated and
removed from active views rather than physically deleted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import logging
import secrets
from typing import Any

from bson import ObjectId
from bson.binary import Binary
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from backend.jumuiya.core.database import collection

logger = logging.getLogger("elimu.lifecycle")

SCHOOLS = "jumuiya_schools"
STUDENTS = "jumuiya_students"
MEMBERS = "jumuiya_elimu_school_members"
PORTAL_LINKS = "jumuiya_elimu_portal_links"
CERTIFICATES = "jumuiya_elimu_completion_certificates"
TERM_DAYS_DEFAULT = 90
PARENT_RESPONSE_DAYS = 14


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any, limit: int = 180) -> str:
    return str(value or "").strip()[:limit]


def _iso_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
    except (TypeError, ValueError):
        return None


def _school_query(school_id: str) -> dict:
    alternatives = [{"_id": school_id}, {"school_id": school_id}]
    if ObjectId.is_valid(school_id):
        alternatives.append({"_id": ObjectId(school_id)})
    return {"$or": alternatives}


def _notify(user_id: Any, title: str, message: str, kind: str, data: dict) -> bool:
    normalized = _text(user_id, 160)
    if not normalized:
        return False
    try:
        from backend.jumuiya.notifications.services import notify
        notify(normalized, {
            "title": title,
            "message": message,
            "type": kind,
            "data": data,
        })
        return True
    except Exception:
        logger.exception("Unable to create Elimu lifecycle notification for user=%s", normalized)
        return False


def _notify_parent_accounts(student: dict, title: str, message: str, kind: str, data: dict) -> int:
    student_id = str(student.get("_id", ""))
    school_id = _text(student.get("school_id"), 160)
    links = collection(PORTAL_LINKS).find({
        "school_id": school_id,
        "student_id": student_id,
        "requester_type": "parent",
        "status": "verified",
    }).limit(100)
    sent = 0
    seen = set()
    for link in links:
        parent_id = _text(link.get("requester_user_id"), 160)
        if parent_id and parent_id not in seen:
            seen.add(parent_id)
            sent += int(_notify(parent_id, title, message, kind, data))
    return sent


def _term_days(school: dict) -> int:
    settings = school.get("settings") if isinstance(school.get("settings"), dict) else {}
    academic = settings.get("academic") if isinstance(settings.get("academic"), dict) else {}
    candidates = (
        academic.get("term_length_days"),
        academic.get("one_term_days"),
        settings.get("term_length_days"),
        settings.get("one_term_days"),
    )
    for value in candidates:
        try:
            days = int(value)
            if 30 <= days <= 180:
                return days
        except (TypeError, ValueError):
            continue
    return TERM_DAYS_DEFAULT


def _registrar_ids(school_id: str) -> list[str]:
    members = collection(MEMBERS).find({
        "school_id": school_id,
        "status": "active",
        "role": {"$in": ["registrar", "owner", "principal"]},
    }).limit(200)
    return list(dict.fromkeys(_text(item.get("user_id"), 160) for item in members if _text(item.get("user_id"), 160)))


def _certificate_pdf(school: dict, student: dict, code: str, completed_at: datetime) -> bytes:
    buffer = BytesIO()
    page_size = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=page_size)
    width, height = page_size

    pdf.setFillColor(colors.HexColor("#F4FAF6"))
    pdf.rect(0, 0, width, height, stroke=0, fill=1)
    pdf.setStrokeColor(colors.HexColor("#177245"))
    pdf.setLineWidth(3)
    pdf.roundRect(26, 26, width - 52, height - 52, 18, stroke=1, fill=0)
    pdf.setStrokeColor(colors.HexColor("#D4AF37"))
    pdf.setLineWidth(1.4)
    pdf.roundRect(36, 36, width - 72, height - 72, 14, stroke=1, fill=0)

    school_name = _text(school.get("name") or school.get("school_name") or school.get("institution_name"), 160) or "School"
    student_name = _text(student.get("full_name") or student.get("display_name"), 160) or "Learner"
    course_name = _text(student.get("course_name") or student.get("programme_name") or student.get("class_name"), 140) or "the enrolled course"
    completion_date = completed_at.astimezone(timezone.utc).strftime("%d %B %Y")

    pdf.setFillColor(colors.HexColor("#177245"))
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawCentredString(width / 2, height - 72, school_name.upper())
    pdf.setFillColor(colors.HexColor("#22312A"))
    pdf.setFont("Helvetica-Bold", 30)
    pdf.drawCentredString(width / 2, height - 132, "CERTIFICATE OF COMPLETION")
    pdf.setFillColor(colors.HexColor("#5E6B63"))
    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(width / 2, height - 174, "PROUDLY PRESENTED TO")
    pdf.setFillColor(colors.HexColor("#14251B"))
    pdf.setFont("Helvetica-Bold", 25)
    pdf.drawCentredString(width / 2, height - 216, student_name)
    pdf.setFillColor(colors.HexColor("#38483E"))
    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(width / 2, height - 254, "for successfully completing")
    pdf.setFillColor(colors.HexColor("#177245"))
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawCentredString(width / 2, height - 284, course_name)
    pdf.setFillColor(colors.HexColor("#38483E"))
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(width / 2, height - 320, f"Completed on {completion_date}")
    pdf.setStrokeColor(colors.HexColor("#177245"))
    pdf.line(width / 2 - 130, 95, width / 2 + 130, 95)
    pdf.setFillColor(colors.HexColor("#38483E"))
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(width / 2, 78, "School Administration")
    pdf.setFillColor(colors.HexColor("#6A786F"))
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(width / 2, 58, f"Certificate ID: {code}")
    pdf.save()
    return buffer.getvalue()


def _issue_completion_certificate(school: dict, student: dict, now: datetime) -> bool:
    school_id = _text(student.get("school_id"), 160)
    student_id = str(student.get("_id", ""))
    existing = collection(CERTIFICATES).find_one({
        "school_id": school_id,
        "student_id": student_id,
        "certificate_type": "course_completion",
    })
    if existing:
        return False

    code = "ELM-" + secrets.token_hex(5).upper()
    completed_at = _iso_date(student.get("course_completed_at") or student.get("completion_date") or student.get("leaving_date")) or now
    pdf_bytes = _certificate_pdf(school, student, code, completed_at)
    doc = {
        "school_id": school_id,
        "student_id": student_id,
        "student_user_id": _text(student.get("student_user_id"), 160),
        "student_name": _text(student.get("full_name") or student.get("display_name"), 160),
        "admission_number": _text(student.get("admission_number"), 80),
        "course_name": _text(student.get("course_name") or student.get("programme_name") or student.get("class_name"), 140),
        "certificate_type": "course_completion",
        "certificate_code": code,
        "status": "issued",
        "completed_at": completed_at,
        "issued_at": now,
        "pdf_bytes": Binary(pdf_bytes),
        "created_at": now,
        "updated_at": now,
    }
    collection(CERTIFICATES).insert_one(doc)
    collection(STUDENTS).update_one(
        {"_id": student["_id"], "school_id": school_id},
        {"$set": {
            "status": "graduated",
            "completion_status": "successful",
            "course_completed": True,
            "course_completed_at": completed_at,
            "lifecycle.certificate_issued_at": now,
            "lifecycle.certificate_code": code,
            "lifecycle.review_status": "course_completed",
            "updated_at": now,
        }},
    )
    notification_data = {"school_id": school_id, "student_id": student_id, "certificate_id": code}
    student_user_id = _text(student.get("student_user_id"), 160)
    _notify(student_user_id, "Congratulations on completing your course!", f"Congratulations {doc['student_name']}! Your course-completion certificate has been issued by { _text(school.get('name') or school.get('school_name'), 160) or 'your school'}. Certificate ID: {code}.", "success", notification_data)
    _notify_parent_accounts(student, "Student course completion certificate issued", f"{doc['student_name']} has successfully completed the course. A congratulatory certificate is available through the Elimu parent portal. Certificate ID: {code}.", "success", notification_data)
    return True


def run_lifecycle_checks() -> dict:
    now = now_utc()
    schools_checked = 0
    students_checked = 0
    parents_notified = 0
    registrar_alerts = 0
    certificates_issued = 0

    schools = list(collection(SCHOOLS).find({
        "status": "active",
        "is_demo": {"$ne": True},
    }).limit(10000))

    for school in schools:
        school_id = str(school.get("_id") or school.get("school_id") or "")
        if not school_id:
            continue
        schools_checked += 1
        term_days = _term_days(school)
        students = collection(STUDENTS).find({"school_id": school_id}).limit(20000)
        for student in students:
            students_checked += 1
            status = _text(student.get("status"), 30).lower()
            course_completed = (
                student.get("course_completed") is True
                or _text(student.get("completion_status"), 30).lower() in {"completed", "successful", "graduated"}
                or status == "graduated"
            )
            if course_completed:
                try:
                    certificates_issued += int(_issue_completion_certificate(school, student, now))
                except Exception:
                    logger.exception("Completion certificate failed for student=%s school=%s", str(student.get("_id")), school_id)
                continue

            if status != "inactive":
                continue

            lifecycle = student.get("lifecycle") if isinstance(student.get("lifecycle"), dict) else {}
            inactive_since = (
                _iso_date(student.get("inactive_since"))
                or _iso_date(lifecycle.get("inactive_since"))
                or _iso_date(student.get("status_changed_at"))
                or _iso_date(student.get("updated_at"))
            )
            if not inactive_since or now - inactive_since < timedelta(days=term_days):
                continue

            student_id = str(student.get("_id", ""))
            notification_data = {"school_id": school_id, "student_id": student_id, "admission_number": student.get("admission_number")}
            if not lifecycle.get("parent_reminder_sent_at"):
                count = _notify_parent_accounts(
                    student,
                    "Please confirm your child's school status",
                    f"{_text(student.get('full_name'), 160) or 'Your child'} has been marked inactive for at least one academic term. Please contact the school or respond in the Elimu parent portal within {PARENT_RESPONSE_DAYS} days. The registrar will be asked to review the record if there is no response.",
                    "action_needed",
                    notification_data,
                )
                parents_notified += count
                deadline = now + timedelta(days=PARENT_RESPONSE_DAYS)
                collection(STUDENTS).update_one(
                    {"_id": student["_id"], "school_id": school_id, "status": "inactive", "lifecycle.parent_reminder_sent_at": {"$exists": False}},
                    {"$set": {
                        "lifecycle.parent_reminder_sent_at": now,
                        "lifecycle.parent_response_deadline": deadline,
                        "lifecycle.review_status": "parent_reminded",
                        "updated_at": now,
                    }},
                )
                lifecycle["parent_reminder_sent_at"] = now
                lifecycle["parent_response_deadline"] = deadline

            deadline = _iso_date(lifecycle.get("parent_response_deadline"))
            parent_response = lifecycle.get("parent_response_at")
            if deadline and now >= deadline and not parent_response and not lifecycle.get("registrar_review_requested_at"):
                for registrar_id in _registrar_ids(school_id):
                    registrar_alerts += int(_notify(
                        registrar_id,
                        "Inactive student requires registrar review",
                        f"{_text(student.get('full_name'), 160) or 'A student'} has been inactive for more than one term and no guardian response was recorded within {PARENT_RESPONSE_DAYS} days. Review the enrolment and decide whether to retain, transfer, or close the active record.",
                        "action_needed",
                        notification_data,
                    ))
                collection(STUDENTS).update_one(
                    {"_id": student["_id"], "school_id": school_id, "lifecycle.registrar_review_requested_at": {"$exists": False}},
                    {"$set": {
                        "lifecycle.registrar_review_requested_at": now,
                        "lifecycle.review_status": "registrar_review_required",
                        "updated_at": now,
                    }},
                )

    return {
        "ok": True,
        "schools_checked": schools_checked,
        "students_checked": students_checked,
        "parents_notified": parents_notified,
        "registrar_alerts": registrar_alerts,
        "certificates_issued": certificates_issued,
        "checked_at": now.isoformat(),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run_lifecycle_checks())
