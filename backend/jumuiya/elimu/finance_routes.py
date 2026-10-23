"""School fee payment instructions and receipt reconciliation.

This module stores school-owned payment instructions and submitted receipt
claims in the existing Jumuiya Elimu database. It deliberately does not claim
to initiate an M-Pesa STK push, charge a bank account, or verify external
settlement without a configured payment-provider integration.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from html import escape
from math import isfinite
from typing import Any
from urllib.parse import urlparse

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


def _normalize_sms_phone(value: Any) -> str:
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


def _send_fee_reminder_sms(recipient: str, body: str) -> None:
    sid = (os.getenv("TWILIO_SID") or os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
    auth = (os.getenv("TWILIO_AUTH") or os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
    sender = (os.getenv("TWILIO_NUMBER") or os.getenv("TWILIO_FROM_NUMBER") or "").strip()
    if not sid or not auth or not sender:
        raise RuntimeError("sms_delivery_not_configured")
    from twilio.rest import Client
    Client(sid, auth).messages.create(body=body, from_=sender, to=recipient)


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

    sms_phone = _normalize_sms_phone(guardian_phone_raw)
    payment_sms = ""
    if instructions:
        # Use the first active school payment route, keeping SMS practical.
        payment_sms = " " + instructions[0]
    sms_body = (
        f"School fee reminder from {school_name}: {student_name} (Student ID {student_label}, {program}). "
        f"Required KES {required:,.2f}; paid KES {paid:,.2f}; balance KES {balance:,.2f}. "
        f"Please pay using school instructions or contact the Bursar if already paid."
    )
    if payment_sms and len(sms_body) + len(payment_sms) < 1500:
        sms_body += payment_sms

    sent_channels = []
    warnings = []
    if guardian_email:
        try:
            _send_fee_reminder_email(guardian_email, subject, email_text, html_body)
            sent_channels.append("email")
        except Exception:
            warnings.append("Email was not sent. Check RESEND_API_KEY, EMAIL_FROM, and the configured sender domain.")
    if guardian_phone_raw:
        if not sms_phone:
            warnings.append("SMS was not sent because the recorded guardian phone is not in a supported international format. Use +254… or a Kenyan 07…/01… number.")
        else:
            try:
                _send_fee_reminder_sms(sms_phone, sms_body)
                sent_channels.append("sms")
            except Exception:
                warnings.append("SMS was not sent. Check TWILIO_SID, TWILIO_AUTH, TWILIO_NUMBER, and Twilio account permissions.")

    log_record = {
        "school_id": school_id,
        "student_id": status["student_id"],
        "admission_number": status["admission_number"],
        "student_name": status["student_name"],
        "sent_by": _uid(uid),
        "channels_sent": sent_channels,
        "warnings": warnings,
        "amount_required": required,
        "amount_paid": paid,
        "balance": balance,
        "status": "sent" if sent_channels else "failed",
        "created_at": _now(),
    }
    audit = collection(REMINDERS).insert_one(log_record)
    if not sent_channels:
        raise APIError("No fee reminder was delivered. Configure Resend for parent email and/or Twilio for parent SMS, and verify the student's saved guardian contact.", 503, "fee_reminder_delivery_failed")

    return created({
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
    }, "School fee reminder sent to the recorded parent/guardian contact.")


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
