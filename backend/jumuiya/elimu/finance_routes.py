"""School fee payment instructions and receipt reconciliation.

This module stores school-owned payment instructions and submitted receipt
claims in the existing Jumuiya Elimu database. It deliberately does not claim
to initiate an M-Pesa STK push, charge a bank account, or verify external
settlement without a configured payment-provider integration.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from datetime import datetime, timezone
from html import escape
from math import isfinite
from typing import Any
from urllib.parse import quote, urlparse

from bson import ObjectId
from flask import Blueprint, request

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import created, ok
from backend.jumuiya.elimu.permissions import authorize

finance_bp = Blueprint("jumuiya_elimu_finance", __name__, url_prefix="/finance")

SCHOOLS = "jumuiya_schools"
FEES = "jumuiya_fees"
RECEIPTS = "jumuiya_elimu_fee_receipts"
STUDENTS = "jumuiya_students"
REMINDERS = "jumuiya_elimu_fee_reminders"


def _now():
    return datetime.now(timezone.utc)


def _text(value: Any, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _uid(value: Any) -> str:
    return _text(value, 160)


def _id_candidates(value: Any) -> list[Any]:
    normalized = _text(value, 160)
    if not normalized:
        return []
    candidates: list[Any] = [normalized]
    if ObjectId.is_valid(normalized):
        candidates.append(ObjectId(normalized))
    return candidates


def _body() -> dict:
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise APIError("A JSON object is required.", 400, "invalid_json")
    return value


def _serialize(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items() if key != "_id"}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


def _school_query(school_id: str) -> dict:
    candidates = [{"_id": school_id}, {"school_id": school_id}]
    if ObjectId.is_valid(school_id):
        candidates.append({"_id": ObjectId(school_id)})
    return {"$or": candidates}


def _school_for_member(member: dict) -> dict:
    school_id = _uid(member.get("school_id"))
    if not school_id:
        raise APIError("Your Elimu membership has no school ID.", 403, "school_membership_required")
    school = collection(SCHOOLS).find_one(_school_query(school_id))
    if not school:
        raise APIError("School not found.", 404, "school_not_found")
    return school


def _require_finance_role(user_id: Any, permission: str) -> tuple[dict, dict]:
    member = authorize(user_id, permission)
    role = _text(member.get("role"), 40).lower()
    if role not in {"owner", "bursar"}:
        raise APIError("Only the School Owner or Bursar can manage school payment accounts and receipt reconciliation.", 403, "finance_role_required")
    return member, _school_for_member(member)


def _normalize_accounts(value: Any) -> list[dict]:
    if not isinstance(value, list) or len(value) > 12:
        raise APIError("payment_accounts must be a list with at most 12 accounts.", 422, "validation_error")
    result = []
    seen = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise APIError(f"Payment account {index + 1} must be an object.", 422, "validation_error")
        kind = _text(raw.get("type"), 20).lower()
        if kind not in {"mpesa", "bank"}:
            raise APIError("Payment account type must be 'mpesa' or 'bank'.", 422, "validation_error")
        label = _text(raw.get("label") or raw.get("account_name") or ("M-Pesa" if kind == "mpesa" else "Bank account"), 100)
        account_name = _text(raw.get("account_name"), 160)
        account_number = _text(raw.get("account_number"), 100)
        paybill = _text(raw.get("paybill"), 40)
        till = _text(raw.get("till"), 40)
        bank_name = _text(raw.get("bank_name"), 120)
        branch = _text(raw.get("branch"), 120)
        account_reference = _text(raw.get("account_reference"), 100)
        instructions = _text(raw.get("instructions"), 500)
        if kind == "mpesa" and not (paybill or till or account_number):
            raise APIError("An M-Pesa account requires a Paybill, Till, or account number.", 422, "payment_account_incomplete")
        if kind == "bank" and not (bank_name and account_number):
            raise APIError("A bank account requires a bank name and account number.", 422, "payment_account_incomplete")
        key = (kind, (paybill or till or account_number).lower(), (bank_name or "").lower())
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "id": _text(raw.get("id"), 80) or f"school-payment-{index + 1}",
            "type": kind,
            "label": label,
            "account_name": account_name,
            "account_number": account_number,
            "paybill": paybill,
            "till": till,
            "bank_name": bank_name,
            "branch": branch,
            "account_reference": account_reference,
            "instructions": instructions,
            "currency": "KES",
            "active": raw.get("active") is not False,
            "updated_at": _now().isoformat(),
        })
    return result


def _fee_query(school_id: str, fee_id: str) -> dict:
    return {
        "school_id": school_id,
        "$or": [{"_id": candidate} for candidate in _id_candidates(fee_id)],
    }



def _resolve_school_student(school_id: str, identifier: str) -> dict:
    normalized = _text(identifier, 160)
    if not normalized:
        raise APIError("Enter the Student ID or admission number first.", 422, "student_id_required")
    candidates = [{"_id": candidate} for candidate in _id_candidates(normalized)]
    candidates.extend([
        {"admission_number": normalized},
        {"student_id": normalized},
    ])
    student = collection(STUDENTS).find_one({
        "school_id": school_id,
        "$or": candidates,
    })
    if not student:
        raise APIError("No student with that ID was found in your school.", 404, "student_not_found")
    return student


def _safe_money(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return round(max(0.0, number), 2) if isfinite(number) else 0.0


def _student_fee_status(student: dict, fee_rows: list[dict]) -> dict:
    student_id = _text(student.get("_id"), 160)
    admission_number = _text(student.get("admission_number"), 120)
    matched = []
    for fee in fee_rows:
        fee_student_id = _text(fee.get("student_id"), 160)
        fee_admission = _text(fee.get("admission_number"), 120)
        if (
            fee_student_id == student_id
            or (admission_number and fee_student_id == admission_number)
            or (not fee_student_id and admission_number and fee_admission == admission_number)
        ):
            matched.append(fee)

    items = []
    required_total = 0.0
    paid_total = 0.0
    outstanding_total = 0.0
    has_overdue = False
    for fee in matched:
        amount = _safe_money(fee.get("amount"))
        paid_raw = fee.get("amount_paid")
        if paid_raw is None:
            paid_raw = fee.get("paid_amount")
        paid = min(amount, _safe_money(paid_raw))
        balance = round(max(amount - paid, 0.0), 2)
        required_total += amount
        paid_total += paid
        outstanding_total += balance
        has_overdue = has_overdue or _text(fee.get("status"), 30).lower() == "overdue"
        items.append({
            "id": _text(fee.get("_id") or fee.get("id"), 160),
            "description": _text(fee.get("description") or fee.get("fee_type") or "School fees", 180),
            "fee_type": _text(fee.get("fee_type"), 80),
            "term": _text(fee.get("term"), 50),
            "academic_year": _text(fee.get("academic_year"), 30),
            "due_date": _text(fee.get("due_date"), 30),
            "amount_required": amount,
            "amount_paid": paid,
            "balance": balance,
            "currency": _text(fee.get("currency") or "KES", 8).upper(),
            "status": "paid" if balance <= 0 and amount > 0 else ("partial" if paid > 0 else _text(fee.get("status") or "pending", 30).lower()),
        })

    required_total = round(required_total, 2)
    paid_total = round(paid_total, 2)
    outstanding_total = round(outstanding_total, 2)
    if not matched:
        status = "not_assessed"
    elif outstanding_total <= 0:
        status = "paid"
    elif has_overdue:
        status = "overdue"
    elif paid_total > 0:
        status = "partial"
    else:
        status = "pending"

    return {
        "student_id": student_id,
        "student_id_label": admission_number or student_id,
        "admission_number": admission_number,
        "student_name": _text(student.get("full_name") or student.get("name"), 160),
        "class_name": _text(student.get("class_name"), 100),
        "program_name": _text(student.get("course_name") or student.get("programme_name") or student.get("program_name") or student.get("class_name"), 160) or "Not assigned",
        "enrolment_status": _text(student.get("status") or "active", 30).lower(),
        "fee_records": len(matched),
        "amount_required": required_total,
        "amount_paid": paid_total,
        "balance": outstanding_total,
        "currency": "KES",
        "fee_status": status,
        "parent_contact_available": bool(_text(student.get("guardian_email"), 254) or _text(student.get("guardian_phone"), 80)),
        "fee_items": items,
    }


def _normalize_whatsapp_phone(value: Any) -> str:
    raw = _text(value, 80)
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        normalized = "+" + digits
    elif digits.startswith("254") and len(digits) == 12:
        normalized = "+" + digits
    elif digits.startswith("0") and len(digits) == 10:
        normalized = "+254" + digits[1:]
    else:
        return ""
    return normalized if re.fullmatch(r"\+[1-9]\d{7,14}", normalized) else ""


def _payment_instructions(school: dict, student: dict) -> list[str]:
    settings = school.get("settings") if isinstance(school.get("settings"), dict) else {}
    finance = settings.get("finance") if isinstance(settings.get("finance"), dict) else {}
    accounts = finance.get("payment_accounts") if isinstance(finance.get("payment_accounts"), list) else []
    lines = []
    for account in accounts:
        if not isinstance(account, dict) or account.get("active") is False:
            continue
        kind = _text(account.get("type"), 20).lower()
        parts = [_text(account.get("label") or account.get("account_name") or ("M-Pesa" if kind == "mpesa" else "Bank account"), 100)]
        if kind == "mpesa":
            if _text(account.get("paybill"), 40):
                parts.append("Paybill " + _text(account.get("paybill"), 40))
            if _text(account.get("till"), 40):
                parts.append("Till " + _text(account.get("till"), 40))
            reference = _text(account.get("account_reference"), 100) or _text(student.get("admission_number"), 120)
            if reference:
                parts.append("Account/reference " + reference)
            if _text(account.get("account_number"), 100):
                parts.append("Account number " + _text(account.get("account_number"), 100))
        elif kind == "bank":
            if _text(account.get("bank_name"), 120):
                parts.append(_text(account.get("bank_name"), 120))
            if _text(account.get("account_number"), 100):
                parts.append("Account " + _text(account.get("account_number"), 100))
            if _text(account.get("account_name"), 160):
                parts.append("Name " + _text(account.get("account_name"), 160))
        lines.append(" · ".join(parts))
    return lines


def _send_fee_reminder_email(recipient: str, subject: str, text_body: str, html_body: str) -> None:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("EMAIL_FROM", "RevelaCode <noreply@revelacode.co.ke>").strip()
    if not api_key or not sender:
        raise RuntimeError("email_delivery_not_configured")
    import resend
    resend.api_key = api_key
    resend.Emails.send({
        "from": sender,
        "to": [recipient],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    })


def _send_fee_reminder_whatsapp(recipient: str, parameters: list[str]) -> str:
    """Send a Meta-approved utility template through the WhatsApp Cloud API.

    The template must contain eight body placeholders in this exact order:
    school, student name, student ID, programme/class, required fees, paid,
    outstanding balance, payment instructions.
    """
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    api_version = (os.getenv("WHATSAPP_API_VERSION") or "v26.0").strip()
    template_name = (os.getenv("WHATSAPP_FEE_REMINDER_TEMPLATE") or "school_fee_reminder").strip()
    language_code = (os.getenv("WHATSAPP_FEE_REMINDER_LANGUAGE") or "en_US").strip()
    if not access_token or not phone_number_id:
        raise RuntimeError("whatsapp_cloud_api_not_configured")

    import requests

    body_parameters = [
        {"type": "text", "text": _text(value, 900)}
        for value in parameters
    ]
    response = requests.post(
        f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient.lstrip("+"),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": [{
                    "type": "body",
                    "parameters": body_parameters,
                }],
            },
        },
        timeout=(5, 20),
    )
    try:
        result = response.json()
    except ValueError:
        result = {}
    if response.status_code >= 400 or not result.get("messages"):
        # Never include credentials or full provider response in the exception.
        raise RuntimeError("whatsapp_template_delivery_failed")
    return _text((result.get("messages") or [{}])[0].get("id"), 160)


@finance_bp.get("/fee-status")
@require_authenticated
def get_student_fee_status():
    uid = current_user_id()
    member, school = _require_finance_role(uid, "fees.view")
    school_id = _uid(member.get("school_id"))
    identifier = _text(request.args.get("student_id"), 160)
    if identifier:
        student = _resolve_school_student(school_id, identifier)
        fee_rows = list(collection(FEES).find({"school_id": school_id}))
        return ok({
            "student": _student_fee_status(student, fee_rows),
            "school_name": _text(school.get("name") or school.get("school_name"), 160),
            "currency": "KES",
        })

    students = list(collection(STUDENTS).find({"school_id": school_id}))
    fee_rows = list(collection(FEES).find({"school_id": school_id}))
    results = [_student_fee_status(student, fee_rows) for student in students]
    results.sort(key=lambda item: (
        item.get("class_name", "").lower(),
        item.get("student_name", "").lower(),
    ))
    total_required = round(sum(item["amount_required"] for item in results), 2)
    total_paid = round(sum(item["amount_paid"] for item in results), 2)
    total_balance = round(sum(item["balance"] for item in results), 2)
    return ok({
        "students": results,
        "count": len(results),
        "summary": {
            "students": len(results),
            "assessed": sum(1 for item in results if item["fee_records"]),
            "amount_required": total_required,
            "amount_paid": total_paid,
            "balance": total_balance,
        },
        "currency": "KES",
    })


@finance_bp.post("/fee-reminders")
@require_authenticated
def send_student_fee_reminder():
    uid = current_user_id()
    member, school = _require_finance_role(uid, "fees.update")
    payload = _body()
    identifier = _text(payload.get("student_id") or payload.get("student_identifier"), 160)
    if not identifier:
        raise APIError("Student ID is required before a fee reminder can be sent.", 422, "student_id_required")

    school_id = _uid(member.get("school_id"))
    student = _resolve_school_student(school_id, identifier)
    fee_rows = list(collection(FEES).find({"school_id": school_id}))
    status = _student_fee_status(student, fee_rows)
    if not status["fee_records"]:
        raise APIError("No fee schedule is assigned to this student yet. A reminder cannot be sent until the required fee is recorded.", 409, "student_fees_not_assessed")
    if status["balance"] <= 0:
        raise APIError("This student has no outstanding fee balance. No reminder was sent.", 409, "no_outstanding_fee_balance")

    guardian_email = _text(student.get("guardian_email"), 254).lower()
    guardian_phone_raw = _text(student.get("guardian_phone"), 80)
    if not guardian_email and not guardian_phone_raw:
        raise APIError("No parent/guardian phone or email is recorded for this student. Ask the Registrar to update the contact; Bursar access cannot edit student records.", 422, "guardian_contact_missing")

    school_name = _text(school.get("name") or school.get("school_name"), 160) or "the school"
    student_name = status["student_name"] or "the student"
    student_label = status["admission_number"] or status["student_id"]
    program = status["program_name"]
    required = status["amount_required"]
    paid = status["amount_paid"]
    balance = status["balance"]
    subject = f"School fee reminder for {student_name} — {school_name}"
    instructions = _payment_instructions(school, student)
    payment_text = "\n".join(instructions) if instructions else "Please use the official payment instructions provided by the school."
    email_text = (
        f"Dear Parent/Guardian,\n\n"
        f"This is a school fee reminder from {school_name} for {student_name} (Student ID: {student_label}).\n"
        f"Programme/class: {program}\n"
        f"Total fees required: KES {required:,.2f}\n"
        f"Payments recorded: KES {paid:,.2f}\n"
        f"Outstanding balance: KES {balance:,.2f}\n\n"
        f"Payment instructions:\n{payment_text}\n\n"
        f"If you have already paid, please share the payment reference with the school Bursar so the account can be reconciled. Thank you.\n\n"
        f"{school_name}"
    )
    safe_school = escape(school_name)
    safe_student = escape(student_name)
    safe_label = escape(student_label)
    safe_program = escape(program)
    safe_instructions = "<br>".join(escape(line) for line in instructions) if instructions else "Please use the official payment instructions provided by the school."
    html_body = (
        '<div style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;padding:24px;color:#0f172a">'
        '<div style="font-size:12px;font-weight:700;letter-spacing:.1em;color:#047857">JUMUIYA ELIMU · FINANCE</div>'
        f'<h1 style="font-size:22px;margin:18px 0 10px">School fee reminder</h1>'
        f"<p>Dear Parent/Guardian, this is a fee reminder from <strong>{safe_school}</strong> for <strong>{safe_student}</strong> (Student ID: {safe_label}).</p>"
        f"<p>Programme/class: {safe_program}</p>"
        f'<table role="presentation" style="border-collapse:collapse;width:100%;margin:18px 0">'
        f'<tr><td style="padding:9px;background:#f8fafc">Total fees required</td><td style="padding:9px;text-align:right;font-weight:700">KES {required:,.2f}</td></tr>'
        f'<tr><td style="padding:9px;background:#f8fafc">Payments recorded</td><td style="padding:9px;text-align:right">KES {paid:,.2f}</td></tr>'
        f'<tr><td style="padding:9px;background:#fff7ed">Outstanding balance</td><td style="padding:9px;text-align:right;font-weight:700;color:#9a3412">KES {balance:,.2f}</td></tr></table>'
        f"<p><strong>Payment instructions</strong><br>{safe_instructions}</p>"
        '<p>If you have already paid, please share the payment reference with the school Bursar so the account can be reconciled. Thank you.</p>'
        f"<p>{safe_school}</p></div>"
    )

    whatsapp_phone = _normalize_whatsapp_phone(guardian_phone_raw)
    payment_text = _text(payment_text, 800)
    whatsapp_message = (
        f"School fee reminder from {school_name}\n"
        f"Student: {student_name} (Student ID: {student_label})\n"
        f"Programme/class: {program}\n"
        f"Total fees required: KES {required:,.2f}\n"
        f"Payments recorded: KES {paid:,.2f}\n"
        f"Outstanding balance: KES {balance:,.2f}\n"
        f"Payment instructions: {payment_text}\n\n"
        "If you have already paid, please send your payment reference to the school Bursar. Thank you."
    )
    manual_whatsapp_url = (
        f"https://wa.me/{whatsapp_phone.lstrip('+')}?text={quote(whatsapp_message)}"
        if whatsapp_phone else ""
    )

    sent_channels = []
    warnings = []
    whatsapp_message_id = ""
    if guardian_email:
        try:
            _send_fee_reminder_email(guardian_email, subject, email_text, html_body)
            sent_channels.append("email")
        except Exception:
            warnings.append("Email was not sent. Check RESEND_API_KEY, EMAIL_FROM, and the configured sender domain.")

    if guardian_phone_raw:
        if not whatsapp_phone:
            warnings.append("WhatsApp could not be prepared because the saved parent phone is not in a supported international format. Use +254… or a Kenyan 07…/01… number.")
        else:
            try:
                template_parameters = [
                    school_name,
                    student_name,
                    student_label,
                    program,
                    f"{required:,.2f}",
                    f"{paid:,.2f}",
                    f"{balance:,.2f}",
                    payment_text,
                ]
                whatsapp_message_id = _send_fee_reminder_whatsapp(
                    whatsapp_phone,
                    template_parameters,
                )
                sent_channels.append("whatsapp")
            except Exception:
                warnings.append(
                    "Automatic WhatsApp delivery did not complete. Configure Meta WhatsApp Cloud API credentials and an approved school_fee_reminder utility template. You can still open WhatsApp and send the prepared message manually."
                )

    # Only expose a manual send link if API-based WhatsApp delivery did not succeed.
    if "whatsapp" in sent_channels:
        manual_whatsapp_url = ""

    log_record = {
        "school_id": school_id,
        "student_id": status["student_id"],
        "admission_number": status["admission_number"],
        "student_name": status["student_name"],
        "sent_by": _uid(uid),
        "channels_sent": sent_channels,
        "warnings": warnings,
        "whatsapp_message_id": whatsapp_message_id,
        "whatsapp_delivery_status": "accepted" if whatsapp_message_id else ("manual_send_required" if manual_whatsapp_url else "not_sent"),
        "whatsapp_status_history": [],
        "amount_required": required,
        "amount_paid": paid,
        "balance": balance,
        "status": "sent" if sent_channels else ("manual_send_required" if manual_whatsapp_url else "failed"),
        "channels_attempted": (["email"] if guardian_email else []) + (["whatsapp"] if whatsapp_phone else []),
        "manual_whatsapp_available": bool(manual_whatsapp_url),
        "created_at": _now(),
    }
    audit = collection(REMINDERS).insert_one(log_record)
    if not sent_channels and not manual_whatsapp_url:
        raise APIError("No fee reminder was delivered or prepared. Configure Resend email or record a valid parent phone number for WhatsApp.", 503, "fee_reminder_delivery_failed")

    result = {
        "reminder_id": str(audit.inserted_id),
        "student": {
            "student_id": status["student_id"],
            "student_id_label": status["student_id_label"],
            "student_name": status["student_name"],
            "program_name": status["program_name"],
            "amount_required": required,
            "amount_paid": paid,
            "balance": balance,
        },
        "channels_sent": sent_channels,
        "warnings": warnings,
        "manual_whatsapp_url": manual_whatsapp_url,
        "whatsapp_message_id": whatsapp_message_id,
        "delivery_status": "sent" if sent_channels else "manual_send_required",
    }
    message = (
        "School fee reminder sent to the recorded parent/guardian contact."
        if sent_channels
        else "Reminder prepared. Open WhatsApp and press Send to deliver it to the recorded parent/guardian."
    )
    return created(result, message)


@finance_bp.get("/payment-accounts")
@require_authenticated
def get_payment_accounts():
    member = authorize(current_user_id(), "fees.view")
    school = _school_for_member(member)
    settings = school.get("settings") if isinstance(school.get("settings"), dict) else {}
    finance = settings.get("finance") if isinstance(settings.get("finance"), dict) else {}
    accounts = finance.get("payment_accounts") if isinstance(finance.get("payment_accounts"), list) else []
    return ok({"payment_accounts": _serialize(accounts), "currency": "KES"})


@finance_bp.put("/payment-accounts")
@require_authenticated
def update_payment_accounts():
    uid = current_user_id()
    member, school = _require_finance_role(uid, "fees.update")
    payload = _body()
    accounts = _normalize_accounts(payload.get("payment_accounts"))
    school_id = _uid(member.get("school_id"))
    result = collection(SCHOOLS).update_one(
        {"_id": school.get("_id")},
        {"$set": {
            "settings.finance.payment_accounts": accounts,
            "settings.finance.payment_accounts_updated_at": _now(),
            "updated_at": _now(),
        }},
    )
    if not result.matched_count:
        raise APIError("School payment settings could not be saved.", 409, "payment_account_save_conflict")
    return ok({"payment_accounts": _serialize(accounts), "currency": "KES"}, "School payment instructions saved. This configures payment instructions only; live online payment collection requires a connected provider.")


@finance_bp.get("/receipts")
@require_authenticated
def list_fee_receipts():
    member = authorize(current_user_id(), "fees.view")
    role = _text(member.get("role"), 40).lower()
    if role not in {"owner", "bursar"}:
        raise APIError("Only the School Owner or Bursar can review fee receipts.", 403, "finance_role_required")
    school_id = _uid(member.get("school_id"))
    status = _text(request.args.get("status") or "pending", 30).lower()
    if status not in {"pending", "approved", "rejected", "all"}:
        raise APIError("status must be pending, approved, rejected, or all.", 422, "validation_error")
    query: dict = {"school_id": school_id}
    if status != "all":
        query["status"] = status
    receipts = list(collection(RECEIPTS).find(query).sort("submitted_at", -1).limit(200))
    return ok({"receipts": [_serialize(item) | {"id": str(item.get("_id", ""))} for item in receipts], "count": len(receipts)})


@finance_bp.post("/receipts/<receipt_id>/review")
@require_authenticated
def review_fee_receipt(receipt_id: str):
    uid = current_user_id()
    member, school = _require_finance_role(uid, "fees.update")
    payload = _body()
    decision = _text(payload.get("decision"), 20).lower()
    notes = _text(payload.get("notes"), 1000)
    if decision not in {"approve", "reject"}:
        raise APIError("decision must be approve or reject.", 422, "validation_error")

    from pymongo import ReturnDocument

    school_id = _uid(member.get("school_id"))
    receipt_candidates = _id_candidates(receipt_id)
    receipt = collection(RECEIPTS).find_one({
        "school_id": school_id,
        "_id": {"$in": receipt_candidates},
        "status": "pending",
    })
    if not receipt:
        raise APIError("Pending fee receipt was not found. Refresh the queue.", 404, "fee_receipt_not_found")

    now = _now()
    # Claim the receipt first. Only one reviewer can take a pending receipt,
    # so retries or double-clicks cannot apply the same payment twice.
    claimed = collection(RECEIPTS).find_one_and_update(
        {"_id": receipt["_id"], "school_id": school_id, "status": "pending"},
        {"$set": {
            "status": "processing",
            "decision": decision,
            "review_notes": notes,
            "reviewed_by": _uid(uid),
            "review_started_at": now,
            "updated_at": now,
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        raise APIError("Receipt is already being reviewed. Refresh the queue.", 409, "fee_receipt_already_reviewed")

    def release_claim():
        collection(RECEIPTS).update_one(
            {"_id": receipt["_id"], "school_id": school_id, "status": "processing"},
            {"$set": {"status": "pending", "updated_at": _now()},
             "$unset": {"decision": "", "reviewed_by": "", "review_started_at": ""}},
        )

    new_status = "rejected"
    if decision == "approve":
        fee_id = _text(receipt.get("fee_id"), 160)
        fee = collection(FEES).find_one(_fee_query(school_id, fee_id))
        if not fee or _text(fee.get("student_id"), 160) != _text(receipt.get("student_id"), 160):
            release_claim()
            raise APIError("The linked fee record is no longer available for this student.", 409, "fee_receipt_scope_conflict")
        amount = float(receipt.get("amount") or 0)
        if not isfinite(amount) or amount <= 0:
            release_claim()
            raise APIError("The receipt amount is invalid.", 409, "invalid_receipt_amount")
        fee_candidates = _id_candidates(str(fee.get("_id") or fee.get("id") or fee_id))
        # Conditional atomic pipeline update guards the outstanding balance
        # and computes the cumulative paid amount and status on the server.
        updated_fee = collection(FEES).find_one_and_update(
            {
                "school_id": school_id,
                "_id": {"$in": fee_candidates},
                "$expr": {
                    "$lte": [
                        amount,
                        {"$subtract": [
                            {"$ifNull": ["$amount", 0]},
                            {"$ifNull": ["$amount_paid", {"$ifNull": ["$paid_amount", 0]}]},
                        ]},
                    ]
                },
            },
            [
                {"$set": {
                    "amount_paid": {"$add": [{"$ifNull": ["$amount_paid", {"$ifNull": ["$paid_amount", 0]}]}, amount]},
                    "paid_amount": {"$add": [{"$ifNull": ["$amount_paid", {"$ifNull": ["$paid_amount", 0]}]}, amount]},
                    "status": {"$cond": [
                        {"$gte": [
                            {"$add": [{"$ifNull": ["$amount_paid", {"$ifNull": ["$paid_amount", 0]}]}, amount]},
                            {"$ifNull": ["$amount", 0]},
                        ]},
                        "paid",
                        "partial",
                    ]},
                    "last_receipt_reviewed_at": now,
                    "updated_at": now,
                }},
            ],
            return_document=ReturnDocument.AFTER,
        )
        if not updated_fee:
            release_claim()
            raise APIError("The outstanding balance changed or the receipt amount exceeds the balance. Refresh and retry.", 409, "fee_balance_changed")
        new_status = "approved"

    updated_receipt = collection(RECEIPTS).find_one_and_update(
        {"_id": receipt["_id"], "school_id": school_id, "status": "processing", "decision": decision},
        {"$set": {
            "status": new_status,
            "review_notes": notes,
            "reviewed_by": _uid(uid),
            "reviewed_at": _now(),
            "updated_at": _now(),
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not updated_receipt:
        raise APIError("Receipt review did not complete. Contact support before reprocessing this receipt.", 500, "fee_receipt_finalize_failed")

    try:
        from backend.jumuiya.notifications.services import notify
        notify(_uid(receipt.get("parent_user_id")), {
            "title": "School fee receipt reviewed",
            "message": ("Your fee receipt has been accepted and applied to the student fee statement." if decision == "approve" else f"Your fee receipt was not accepted. {notes or 'Contact the school Bursar for clarification.'}"),
            "type": "success" if decision == "approve" else "warning",
            "data": {"school_id": school_id, "student_id": receipt.get("student_id"), "receipt_id": str(receipt["_id"]), "status": new_status},
        })
    except Exception:
        pass

    return ok({"receipt": _serialize(updated_receipt), "status": new_status}, "Receipt approved and reconciled." if decision == "approve" else "Receipt rejected.")


@finance_bp.get("/fee-reminders")
@require_authenticated
def list_student_fee_reminders():
    """Return recent finance reminders, including verified WhatsApp delivery states."""
    member, _school = _require_finance_role(current_user_id(), "fees.view")
    school_id = _uid(member.get("school_id"))
    try:
        limit = int(request.args.get("limit", "10"))
    except (TypeError, ValueError):
        limit = 10
    limit = min(max(limit, 1), 50)

    records = list(
        collection(REMINDERS)
        .find({"school_id": school_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    reminders = []
    for record in records:
        channels = record.get("channels_sent") if isinstance(record.get("channels_sent"), list) else []
        whatsapp_status = _text(record.get("whatsapp_delivery_status"), 40).lower()
        if not whatsapp_status:
            whatsapp_status = (
                "accepted" if record.get("whatsapp_message_id")
                else ("manual_send_required" if record.get("manual_whatsapp_available") else "not_sent")
            )
        reminders.append({
            "reminder_id": str(record.get("_id") or ""),
            "student_id": _text(record.get("student_id"), 160),
            "admission_number": _text(record.get("admission_number"), 120),
            "student_name": _text(record.get("student_name"), 160),
            "channels_sent": channels,
            "status": _text(record.get("status"), 40),
            "whatsapp_delivery_status": whatsapp_status,
            "whatsapp_status_updated_at": _serialize(record.get("whatsapp_status_updated_at")),
            "whatsapp_status_history": _serialize(record.get("whatsapp_status_history") or []),
            "manual_whatsapp_available": bool(record.get("manual_whatsapp_available")),
            "amount_required": _safe_money(record.get("amount_required")),
            "amount_paid": _safe_money(record.get("amount_paid")),
            "balance": _safe_money(record.get("balance")),
            "warnings": record.get("warnings") if isinstance(record.get("warnings"), list) else [],
            "created_at": _serialize(record.get("created_at")),
        })
    return ok({"reminders": reminders, "count": len(reminders)})


@finance_bp.route("/whatsapp/webhook", methods=["GET"])
def verify_whatsapp_webhook():
    """Complete the Meta webhook subscription challenge."""
    expected_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "").strip()
    mode = request.args.get("hub.mode", "")
    received_token = request.args.get("hub.verify_token", "")
    challenge = request.args.get("hub.challenge", "")
    if not expected_token:
        return "WhatsApp webhook verify token is not configured.", 503
    if mode == "subscribe" and challenge and hmac.compare_digest(received_token, expected_token):
        return challenge, 200, {"Content-Type": "text/plain; charset=utf-8"}
    return "Forbidden", 403


@finance_bp.route("/whatsapp/webhook", methods=["POST"])
def receive_whatsapp_webhook():
    """Authenticate Meta callbacks and persist WhatsApp message delivery states."""
    app_secret = os.getenv("WHATSAPP_APP_SECRET", "").strip()
    if not app_secret:
        return "WhatsApp webhook signature verification is not configured.", 503

    raw_body = request.get_data(cache=True)
    signature = request.headers.get("X-Hub-Signature-256", "").strip()
    expected_signature = "sha256=" + hmac.new(
        app_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected_signature):
        return "Invalid webhook signature.", 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}, 200

    for entry in payload.get("entry", []) if isinstance(payload.get("entry"), list) else []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", []) if isinstance(entry.get("changes"), list) else []:
            if not isinstance(change, dict) or change.get("field") != "messages":
                continue
            value = change.get("value") if isinstance(change.get("value"), dict) else {}
            statuses = value.get("statuses") if isinstance(value.get("statuses"), list) else []
            for status in statuses:
                if not isinstance(status, dict):
                    continue
                message_id = _text(status.get("id"), 240)
                status_name = _text(status.get("status"), 30).lower()
                if not message_id or status_name not in {"sent", "delivered", "read", "failed"}:
                    continue

                raw_timestamp = status.get("timestamp")
                try:
                    provider_timestamp = int(raw_timestamp)
                    if provider_timestamp < 0 or provider_timestamp > 4102444800:
                        provider_timestamp = None
                except (TypeError, ValueError, OverflowError):
                    provider_timestamp = None

                now = _now()
                provider_time = (
                    datetime.fromtimestamp(provider_timestamp, tz=timezone.utc)
                    if provider_timestamp is not None else now
                )
                errors = status.get("errors") if isinstance(status.get("errors"), list) else []
                first_error = errors[0] if errors and isinstance(errors[0], dict) else {}
                error_code = _text(first_error.get("code"), 40)
                error_title = _text(first_error.get("title") or first_error.get("message"), 240)
                history_event = {
                    "status": status_name,
                    "provider_timestamp": provider_timestamp,
                    "received_at": now,
                    "error_code": error_code,
                    "error_title": error_title,
                }
                fields = {
                    "whatsapp_delivery_status": status_name,
                    "whatsapp_status_updated_at": provider_time,
                    "whatsapp_status_received_at": now,
                    "updated_at": now,
                }
                if provider_timestamp is not None:
                    fields["whatsapp_status_timestamp"] = provider_timestamp
                if error_code:
                    fields["whatsapp_last_error_code"] = error_code
                    fields["whatsapp_last_error_title"] = error_title

                query = {"whatsapp_message_id": message_id}
                if provider_timestamp is not None:
                    # Ignore late/out-of-order events so "read" cannot regress to "sent".
                    query["$or"] = [
                        {"whatsapp_status_timestamp": {"$exists": False}},
                        {"whatsapp_status_timestamp": {"$lte": provider_timestamp}},
                    ]
                collection(REMINDERS).update_one(
                    query,
                    {
                        "$set": fields,
                        "$push": {
                            "whatsapp_status_history": {
                                "$each": [history_event],
                                "$slice": -10,
                            }
                        },
                    },
                )

    return {"status": "ok"}, 200
