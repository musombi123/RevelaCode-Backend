"""School finance, WhatsApp fee queries, and verified M-Pesa reconciliation.

School payment instructions, fee records, receipt claims, and automatically
verified M-Pesa payments all use the existing Jumuiya Elimu data store. Daraja
callbacks are notifications only; fee balances are updated only after a
correlated provider status query confirms the same checkout.
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
    elif digits.startswith(("7", "1")) and len(digits) == 9:
        normalized = "+254" + digits
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


def _whatsapp_phone_variants(value: Any) -> list[str]:
    """Return common Kenyan representations for a normalized parent number."""
    normalized = _normalize_whatsapp_phone(value)
    if not normalized:
        return []
    digits = normalized.lstrip("+")
    national = digits[3:] if digits.startswith("254") else digits
    variants = {
        normalized,
        digits,
        national,
        "0" + national if len(national) == 9 else "",
        "254" + national if len(national) == 9 else "",
        "+254" + national if len(national) == 9 else "",
    }
    return sorted(item for item in variants if item)


def _send_whatsapp_text(recipient: str, text_body: str) -> str:
    """Send a user-requested reply inside WhatsApp's customer-service window."""
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    api_version = (os.getenv("WHATSAPP_API_VERSION") or "v26.0").strip()
    if not access_token or not phone_number_id:
        raise RuntimeError("whatsapp_cloud_api_not_configured")

    import requests

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
            "type": "text",
            "text": {
                "preview_url": False,
                "body": _text(text_body, 3800),
            },
        },
        timeout=(5, 20),
    )
    try:
        result = response.json()
    except ValueError:
        result = {}
    if response.status_code >= 400 or not isinstance(result.get("messages"), list) or not result["messages"]:
        raise RuntimeError("whatsapp_text_delivery_failed")
    return _text(result["messages"][0].get("id"), 240)


ELIMU_MPESA_CHECKOUTS = "jumuiya_elimu_mpesa_checkouts"
ELIMU_FEE_PAYMENT_LEDGER = "jumuiya_elimu_fee_payments"
ELIMU_MPESA_PENDING = {
    "initiating",
    "pending",
    "submission_unknown",
    "awaiting_verification",
    "verified_pending_allocation",
    "allocation_partial",
    "allocation_conflict",
    "receipt_conflict",
}


def _elimu_mpesa_callback_url() -> str:
    """Validate the Elimu-specific public HTTPS callback path."""
    value = os.getenv("ELIMU_MPESA_CALLBACK_URL", "").strip()
    if not value:
        return ""
    expected_path = "/api/jumuiya/elimu/finance/mpesa/callback"
    try:
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path.rstrip("/") != expected_path
            or parsed.query
            or parsed.fragment
        ):
            return ""
    except ValueError:
        return ""
    return value


def _fee_rows_for_student(school_id: str, student: dict) -> list[dict]:
    student_id = _text(student.get("_id") or student.get("id"), 160)
    admission = _text(student.get("admission_number"), 120)
    rows = list(collection(FEES).find({"school_id": school_id}).limit(5000))
    matched = []
    for fee in rows:
        fee_student_id = _text(fee.get("student_id"), 160)
        fee_admission = _text(fee.get("admission_number"), 120)
        if (
            fee_student_id == student_id
            or (admission and fee_student_id == admission)
            or (not fee_student_id and admission and fee_admission == admission)
        ):
            matched.append(fee)
    matched.sort(key=lambda item: (
        _text(item.get("due_date"), 40) or "9999-12-31",
        _text(item.get("term"), 40),
        _text(item.get("_id") or item.get("id"), 160),
    ))
    return matched


def _fee_payment_allocations(school_id: str, student: dict) -> tuple[list[dict], float]:
    """Plan a full-balance allocation across outstanding voteheads in due-date order."""
    allocations = []
    total = 0.0
    for fee in _fee_rows_for_student(school_id, student):
        required = _safe_money(fee.get("amount"))
        paid_raw = fee.get("amount_paid")
        if paid_raw is None:
            paid_raw = fee.get("paid_amount")
        paid = min(required, _safe_money(paid_raw))
        balance = round(max(required - paid, 0.0), 2)
        if balance <= 0:
            continue
        fee_id = _text(fee.get("_id") or fee.get("id"), 160)
        if not fee_id:
            raise APIError("A fee record has no stable identifier, so online payment was not started.", 409, "fee_record_id_missing")
        allocations.append({
            "fee_id": fee_id,
            "votehead": _text(fee.get("fee_type") or fee.get("votehead") or fee.get("description") or "School fees", 120),
            "amount": balance,
        })
        total += balance
    return allocations, round(total, 2)


def _clear_elimu_fee_locks(school_id: str, checkout_id: str) -> None:
    try:
        collection(FEES).update_many(
            {"school_id": school_id, "active_mpesa_checkout_id": checkout_id},
            {"$unset": {"active_mpesa_checkout_id": "", "active_mpesa_checkout_started_at": ""}},
        )
    except Exception:
        # The checkout state remains durable and can be reconciled by finance.
        pass


def _start_elimu_fee_stk(school: dict, student: dict, sender: str, inbound_message_id: str) -> dict:
    """Create a single idempotent STK request for this guardian's full recorded fee balance."""
    callback_url = _elimu_mpesa_callback_url()
    if not callback_url:
        return {
            "ok": False,
            "message": (
                "Live school-fee M-Pesa is not enabled yet. No payment prompt was sent. "
                "The backend needs ELIMU_MPESA_CALLBACK_URL set to the public HTTPS URL ending "
                "in /api/jumuiya/elimu/finance/mpesa/callback."
            ),
        }

    try:
        from backend.revenue import mpesa as daraja
        if not daraja.checkout_is_production_configured():
            return {
                "ok": False,
                "message": (
                    "Live school-fee M-Pesa is not ready, so no payment prompt was sent. "
                    "The school administrator must verify the production Daraja configuration first."
                ),
            }
        phone = daraja._phone(_normalize_whatsapp_phone(sender))
    except (RuntimeError, ValueError):
        return {
            "ok": False,
            "message": "The M-Pesa request could not be prepared safely. No payment prompt was sent; please contact the school Bursar.",
        }

    school_id = _text(school.get("school_id") or school.get("_id"), 160)
    student_id = _text(student.get("_id") or student.get("id"), 160)
    admission = _text(student.get("admission_number"), 120)
    school_name = _text(school.get("name") or school.get("school_name"), 160) or "Your school"
    student_name = _text(student.get("full_name") or student.get("name"), 160) or "the learner"

    if (
        not school_id
        or not student_id
        or _normalize_whatsapp_phone(student.get("guardian_phone")) != _normalize_whatsapp_phone(sender)
    ):
        return {"ok": False, "message": "This WhatsApp number could not be matched safely to the learner record. No payment prompt was sent."}

    try:
        allocations, total_balance = _fee_payment_allocations(school_id, student)
    except APIError:
        return {"ok": False, "message": "The fee records could not be prepared for payment. Please contact the school Bursar."}

    if not allocations or total_balance <= 0:
        return {"ok": False, "message": f"{school_name}: no outstanding fee balance is available for an M-Pesa prompt."}
    if abs(total_balance - round(total_balance)) > 0.000001:
        return {
            "ok": False,
            "message": (
                f"{school_name}: the recorded balance is KES {total_balance:,.2f}. "
                "Daraja STK Push requires a whole-KES amount here; please ask the Bursar to review the fee records."
            ),
        }

    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError

    rows = collection(ELIMU_MPESA_CHECKOUTS)
    ledger = collection(ELIMU_FEE_PAYMENT_LEDGER)
    try:
        rows.create_index([("school_id", 1), ("idempotency_key", 1)], unique=True, name="uq_elimu_mpesa_school_idempotency")
        rows.create_index([("checkout_request_id", 1)], unique=True, sparse=True, name="uq_elimu_mpesa_checkout_request")
        ledger.create_index([("provider_receipt", 1)], unique=True, sparse=True, name="uq_elimu_fee_payment_receipt")
        ledger.create_index([("checkout_id", 1)], unique=True, name="uq_elimu_fee_payment_checkout")
    except Exception:
        # An index conflict must not silently bypass idempotency; verify readiness below.
        existing_indexes = list(rows.list_indexes())
        required = {"uq_elimu_mpesa_school_idempotency", "uq_elimu_mpesa_checkout_request"}
        if not required.issubset({item.get("name") for item in existing_indexes}):
            return {"ok": False, "message": "M-Pesa checkout storage is not ready. No payment prompt was sent; contact RevelaCode support."}

    idempotency_key = hashlib.sha256(
        f"{_text(inbound_message_id, 240)}:{school_id}:{student_id}".encode("utf-8")
    ).hexdigest()
    existing = rows.find_one({"school_id": school_id, "idempotency_key": idempotency_key})
    if existing:
        if existing.get("status") in {"pending", "awaiting_verification", "submission_unknown", "verified_pending_allocation", "allocation_partial"}:
            return {
                "ok": False,
                "message": (
                    f"A payment request is already unresolved for {student_name}. "
                    "Do not request another prompt. Send FEES to check the balance later, or contact the Bursar for reconciliation."
                ),
            }
        return {
            "ok": False,
            "message": "This WhatsApp payment request was already processed. Send FEES for a current balance; do not repeat a payment request.",
        }

    unresolved = rows.find_one({
        "school_id": school_id,
        "student_id": student_id,
        "status": {"$in": list(ELIMU_MPESA_PENDING)},
    }, sort=[("created_at", -1)])
    if unresolved:
        return {
            "ok": False,
            "message": (
                f"A payment for {student_name} is still awaiting confirmation. "
                "No second prompt was sent. Please send FEES later or contact the Bursar."
            ),
        }

    checkout_doc = {
        "school_id": school_id,
        "school_name": school_name,
        "student_id": student_id,
        "student_name": student_name,
        "admission_number": admission,
        "phone": phone,
        "amount": f"{int(round(total_balance))}.00",
        "currency": "KES",
        "fee_allocations": allocations,
        "idempotency_key": idempotency_key,
        "provider": "mpesa",
        "status": "initiating",
        "created_from": "whatsapp_parent_bot",
        "inbound_message_id": _text(inbound_message_id, 240),
        "created_at": _now(),
        "updated_at": _now(),
    }
    try:
        inserted = rows.insert_one(checkout_doc)
        checkout_doc["_id"] = inserted.inserted_id
    except DuplicateKeyError:
        return {
            "ok": False,
            "message": "This payment request has already been recorded. Send FEES to check the balance; do not request another prompt.",
        }

    checkout_id = str(checkout_doc["_id"])
    claimed_fee_ids = []
    for allocation in allocations:
        fee_candidates = _id_candidates(allocation["fee_id"])
        amount = float(allocation["amount"])
        claimed = collection(FEES).find_one_and_update(
            {
                "school_id": school_id,
                "_id": {"$in": fee_candidates},
                "$or": [
                    {"active_mpesa_checkout_id": {"$exists": False}},
                    {"active_mpesa_checkout_id": None},
                    {"active_mpesa_checkout_id": ""},
                ],
                "$expr": {
                    "$gte": [
                        {
                            "$subtract": [
                                {"$ifNull": ["$amount", 0]},
                                {"$ifNull": ["$amount_paid", {"$ifNull": ["$paid_amount", 0]}]},
                            ]
                        },
                        amount,
                    ]
                },
            },
            {"$set": {
                "active_mpesa_checkout_id": checkout_id,
                "active_mpesa_checkout_started_at": _now(),
            }},
            return_document=ReturnDocument.AFTER,
        )
        if not claimed:
            _clear_elimu_fee_locks(school_id, checkout_id)
            rows.update_one(
                {"_id": checkout_doc["_id"]},
                {"$set": {
                    "status": "fee_state_conflict",
                    "message": "A fee balance changed or another payment is already in progress; no STK prompt was sent.",
                    "updated_at": _now(),
                }},
            )
            return {
                "ok": False,
                "message": "A fee balance changed or another payment is already in progress. No prompt was sent; refresh the fee statement or contact the Bursar.",
            }
        claimed_fee_ids.append(allocation["fee_id"])

    shortcode = os.getenv("MPESA_SHORTCODE", "").strip()
    timestamp = daraja._timestamp()
    transaction_type = os.getenv("MPESA_TRANSACTION_TYPE", "CustomerPayBillOnline").strip()
    if transaction_type not in {"CustomerPayBillOnline", "CustomerBuyGoodsOnline"}:
        _clear_elimu_fee_locks(school_id, checkout_id)
        rows.update_one({"_id": checkout_doc["_id"]}, {"$set": {"status": "initiation_failed", "message": "Invalid transaction type", "updated_at": _now()}})
        return {"ok": False, "message": "M-Pesa transaction configuration is invalid. No prompt was sent; contact the school administrator."}

    party_b = os.getenv("MPESA_PARTY_B", shortcode).strip() or shortcode
    account_ref = re.sub(r"[^A-Za-z0-9]", "", admission or student_id)[-12:] or "ELIMUFEE"
    try:
        response = daraja._daraja_post(
            "/mpesa/stkpush/v1/processrequest",
            {
                "BusinessShortCode": shortcode,
                "Password": daraja._password(timestamp),
                "Timestamp": timestamp,
                "TransactionType": transaction_type,
                "Amount": int(round(total_balance)),
                "PartyA": phone,
                "PartyB": party_b,
                "PhoneNumber": phone,
                "CallBackURL": callback_url,
                "AccountReference": account_ref,
                "TransactionDesc": "Elimu school fees",
            },
        )
    except RuntimeError:
        rows.update_one(
            {"_id": checkout_doc["_id"]},
            {"$set": {
                "status": "submission_unknown",
                "message": "STK submission could not be confirmed; do not retry until finance reconciliation.",
                "updated_at": _now(),
            }},
        )
        return {
            "ok": False,
            "message": (
                f"M-Pesa submission for {student_name} could not be confirmed. "
                "Do not make another payment request. The school must reconcile this checkout before retrying."
            ),
        }

    checkout_request_id = _text(response.get("CheckoutRequestID"), 200)
    merchant_request_id = _text(response.get("MerchantRequestID"), 200)
    if str(response.get("ResponseCode", "")) != "0":
        _clear_elimu_fee_locks(school_id, checkout_id)
        rows.update_one(
            {"_id": checkout_doc["_id"]},
            {"$set": {
                "status": "initiation_failed",
                "message": _text(response.get("ResponseDescription") or response.get("errorMessage") or "Daraja rejected the STK request.", 300),
                "updated_at": _now(),
            }},
        )
        return {
            "ok": False,
            "message": f"Safaricom did not accept the M-Pesa prompt for {student_name}. No fee was cleared. Please contact the Bursar before trying again.",
        }

    if not checkout_request_id or not merchant_request_id:
        rows.update_one(
            {"_id": checkout_doc["_id"]},
            {"$set": {
                "status": "submission_unknown",
                "message": "Daraja accepted the request but returned incomplete checkout identifiers; manual reconciliation is required.",
                "updated_at": _now(),
            }},
        )
        return {
            "ok": False,
            "message": "The M-Pesa request response was incomplete. Do not retry; the school must reconcile the checkout first.",
        }

    rows.update_one(
        {"_id": checkout_doc["_id"]},
        {"$set": {
            "status": "pending",
            "checkout_request_id": checkout_request_id,
            "merchant_request_id": merchant_request_id,
            "provider_response_code": str(response.get("ResponseCode", ""))[:40],
            "message": _text(response.get("CustomerMessage") or response.get("ResponseDescription") or "STK prompt submitted.", 300),
            "updated_at": _now(),
        }},
    )
    log_action(
        user_id="whatsapp-parent",
        action="elimu.fees.mpesa_stk_initiated",
        resource="elimu_fee_checkout",
        resource_id=checkout_id,
        metadata={
            "school_id": school_id,
            "student_id": student_id,
            "amount": int(round(total_balance)),
            "channel": "whatsapp",
        },
    )
    return {
        "ok": True,
        "message": (
            f"M-Pesa prompt sent for {school_name}.\\n"
            f"Learner: {student_name}\\n"
            f"Amount: KES {int(round(total_balance)):,}\\n"
            "Enter your M-Pesa PIN only if the prompt shows the correct school payment and amount. "
            "Never share your PIN. After payment, send FEES to check the recorded balance."
        ),
    }


def _handle_whatsapp_fee_query(sender: str, message_text: str, inbound_message_id: str = "") -> str:
    """Answer only with fee data belonging to active learners linked to this sender."""
    normalized_sender = _normalize_whatsapp_phone(sender)
    if not normalized_sender:
        return "I could not verify this WhatsApp number. Please contact your school office to update the parent/guardian contact."

    command = _text(message_text, 500).lower()
    if not command or command in {"hi", "hello", "habari", "help", "menu", "start"}:
        return (
            "Jumuiya Elimu Parent Assistant\\n"
            "Send FEES to check the balance for a linked learner.\\n"
            "If more than one learner is linked, send FEES followed by the learner's admission number.\\n"
            "For an official receipt or payment dispute, contact the school Bursar."
        )

    pay_match = re.fullmatch(
        r"pay(?:\\s+([a-z0-9][a-z0-9/._-]{0,39}))?",
        command,
        flags=re.IGNORECASE,
    )
    match = re.fullmatch(
        r"(?:fees?|balance|fee balance)(?:\\s+([a-z0-9][a-z0-9/._-]{0,39}))?",
        command,
        flags=re.IGNORECASE,
    )
    if pay_match:
        requested_action = "pay"
        requested_identifier = _text(pay_match.group(1), 40).lower()
        name_query = ""
        match = None
    elif match:
        requested_action = "fees"
        name_query = ""
        requested_identifier = _text(match.group(1), 40).lower()
    else:
        requested_action = "fees"
        # Also allow a parent to refer to a child's name, but only among records
        # linked to this same WhatsApp number.
        name_query = re.sub(r"^(?:check|show|what is|what's)\\s+", "", command).strip()
        if not name_query or len(name_query) > 80:
            return "Please send FEES, FEES followed by the learner's admission number, or PAY to request an M-Pesa prompt."
        requested_identifier = ""

    variants = _whatsapp_phone_variants(normalized_sender)
    candidates = list(
        collection(STUDENTS).find({
            "status": "active",
            "guardian_phone": {"$in": variants},
        }).limit(1000)
    )
    linked = []
    seen = set()
    for student in candidates:
        if _normalize_whatsapp_phone(student.get("guardian_phone")) != normalized_sender:
            continue
        student_id = _text(student.get("_id") or student.get("id"), 160)
        if not student_id or student_id in seen:
            continue
        seen.add(student_id)
        admission = _text(student.get("admission_number"), 120)
        if requested_identifier and requested_identifier not in {
            admission.lower(),
            student_id.lower(),
        }:
            continue
        full_name = _text(student.get("full_name") or student.get("name"), 160)
        if name_query and name_query not in full_name.lower() and name_query not in admission.lower():
            continue
        school_id = _text(student.get("school_id"), 160)
        if not school_id:
            continue
        school = collection(SCHOOLS).find_one(_school_query(school_id))
        if not school:
            continue
        fee_rows = list(collection(FEES).find({"school_id": school_id}).limit(5000))
        status = _student_fee_status(student, fee_rows)
        linked.append({
            "student": student,
            "school": school,
            "status": status,
        })

    if not linked:
        return (
            "I could not find an active learner linked to this WhatsApp number and request. "
            "Please contact the Registrar to confirm the guardian number and admission number."
        )

    if len(linked) > 1:
        options = []
        for item in linked[:8]:
            status = item["status"]
            options.append(
                f"• {status['student_name']} — Admission: {status['admission_number'] or 'not recorded'} "
                f"({ _text(item['school'].get('name') or item['school'].get('school_name'), 100) or 'School' })"
            )
        more = f"\\n…and {len(linked) - 8} more linked learners." if len(linked) > 8 else ""
        return (
            "Several learners are linked to this number. Reply FEES <admission number> to check a balance or PAY <admission number> to request an M-Pesa prompt.\\n"
            + "\\n".join(options)
            + more
        )

    item = linked[0]
    status = item["status"]
    school = item["school"]
    school_name = _text(school.get("name") or school.get("school_name"), 160) or "Your school"
    if not status["fee_records"]:
        return (
            f"{school_name}\\n"
            f"Learner: {status['student_name']}\\n"
            "No fee schedule is recorded yet. Please contact the Bursar for the current fee structure."
        )

    if requested_action == "pay":
        payment_result = _start_elimu_fee_stk(
            school,
            item["student"],
            normalized_sender,
            inbound_message_id,
        )
        return payment_result["message"]

    fee_lines = []
    for fee in status["fee_items"][:8]:
        fee_lines.append(
            f"• {_text(fee.get('description') or fee.get('fee_type') or 'School fees', 100)}: "
            f"Balance KES {float(fee.get('balance') or 0):,.2f}"
        )
    details = "\\n".join(fee_lines)
    remaining = f"\\n…and {len(status['fee_items']) - 8} other fee item(s)." if len(status["fee_items"]) > 8 else ""
    return (
        f"{school_name} — Fee statement\\n"
        f"Learner: {status['student_name']}\\n"
        f"Admission no.: {status['admission_number'] or 'not recorded'}\\n"
        f"Class: {status['class_name'] or 'not assigned'}\\n"
        f"Required: KES {status['amount_required']:,.2f}\\n"
        f"Recorded paid: KES {status['amount_paid']:,.2f}\\n"
        f"Outstanding balance: KES {status['balance']:,.2f}\\n\\n"
        f"{details}{remaining}\\n\\n"
        "This statement reflects payments recorded by the school. If you have paid recently, "
        "keep the M-Pesa receipt and contact the Bursar if the balance has not updated."
    )


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
            "whatsapp_last_error_title": _text(record.get("whatsapp_last_error_title"), 240),
            "manual_whatsapp_available": bool(record.get("manual_whatsapp_available")),
            "amount_required": _safe_money(record.get("amount_required")),
            "amount_paid": _safe_money(record.get("amount_paid")),
            "balance": _safe_money(record.get("balance")),
            "warnings": record.get("warnings") if isinstance(record.get("warnings"), list) else [],
            "created_at": _serialize(record.get("created_at")),
        })
    return ok({"reminders": reminders, "count": len(reminders)})


@finance_bp.route("/mpesa/callback", methods=["POST"])
def receive_elimu_mpesa_callback():
    """Reconcile school-fee STK callbacks using a Daraja query before any ledger write."""
    payload = request.get_json(silent=True)
    callback = payload.get("Body", {}).get("stkCallback", {}) if isinstance(payload, dict) else {}
    checkout_id = _text(callback.get("CheckoutRequestID"), 200)
    merchant_id = _text(callback.get("MerchantRequestID"), 200)
    if not checkout_id:
        return {"ResultCode": 0, "ResultDesc": "Callback acknowledged"}, 200

    rows = collection(ELIMU_MPESA_CHECKOUTS)
    checkout = rows.find_one({"checkout_request_id": checkout_id})
    if not checkout:
        return {"ResultCode": 0, "ResultDesc": "Unknown Elimu checkout acknowledged"}, 200
    if checkout.get("status") == "succeeded":
        return {"ResultCode": 0, "ResultDesc": "Payment already reconciled"}, 200

    stored_merchant = _text(checkout.get("merchant_request_id"), 200)
    if not merchant_id or not stored_merchant or merchant_id != stored_merchant:
        rows.update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "status": "awaiting_verification",
                "message": "Callback identifiers did not match the stored checkout; provider reconciliation is required.",
                "callback_received_at": _now(),
                "updated_at": _now(),
            }},
        )
        return {"ResultCode": 0, "ResultDesc": "Callback acknowledged for reconciliation"}, 200

    try:
        from backend.revenue import mpesa as daraja
        query_result = daraja._daraja_post(
            "/mpesa/stkpushquery/v1/query",
            {
                "BusinessShortCode": os.getenv("MPESA_SHORTCODE", "").strip(),
                "Password": daraja._password(daraja._timestamp()),
                "Timestamp": daraja._timestamp(),
                "CheckoutRequestID": checkout_id,
            },
        )
    except Exception:
        rows.update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "status": "awaiting_verification",
                "message": "Callback received but the final Daraja query was unavailable; no fee was cleared.",
                "callback_received_at": _now(),
                "updated_at": _now(),
            }},
        )
        return {"ResultCode": 0, "ResultDesc": "Callback acknowledged for reconciliation"}, 200

    query_checkout_id = _text(query_result.get("CheckoutRequestID"), 200)
    query_merchant_id = _text(query_result.get("MerchantRequestID"), 200)
    query_code = query_result.get("ResultCode")
    if query_checkout_id != checkout_id or query_merchant_id != stored_merchant:
        rows.update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "status": "awaiting_verification",
                "message": "Daraja query identifiers did not match the stored checkout; no fee was cleared.",
                "updated_at": _now(),
            }},
        )
        return {"ResultCode": 0, "ResultDesc": "Callback acknowledged for reconciliation"}, 200

    if query_code is None:
        rows.update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "status": "awaiting_verification",
                "message": "Daraja accepted the query but has not returned a final transaction result.",
                "updated_at": _now(),
            }},
        )
        return {"ResultCode": 0, "ResultDesc": "Callback acknowledged for reconciliation"}, 200

    if str(query_code) != "0":
        rows.update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "status": "failed",
                "result_code": str(query_code)[:40],
                "result_description": _text(query_result.get("ResultDesc") or query_result.get("ResponseDescription") or "M-Pesa payment was not completed.", 300),
                "updated_at": _now(),
            }},
        )
        _clear_elimu_fee_locks(_text(checkout.get("school_id"), 160), str(checkout["_id"]))
        return {"ResultCode": 0, "ResultDesc": "Payment failure reconciled"}, 200

    # Callback metadata is considered only after the provider query is correlated.
    callback_metadata = {}
    items = (callback.get("CallbackMetadata") or {}).get("Item", [])
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("Name"), str):
                continue
            key, value = item["Name"], item.get("Value")
            if key in {"MpesaReceiptNumber", "Amount", "PhoneNumber"} and isinstance(value, (str, int, float)):
                callback_metadata[key] = value
    try:
        receipt = daraja._validated_callback_receipt(checkout, callback_metadata)
    except Exception:
        rows.update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "status": "awaiting_verification",
                "message": "Daraja query succeeded but receipt amount/payer metadata failed validation; manual reconciliation is required.",
                "updated_at": _now(),
            }},
        )
        return {"ResultCode": 0, "ResultDesc": "Payment awaiting reconciliation"}, 200

    ledger = collection(ELIMU_FEE_PAYMENT_LEDGER)
    duplicate_receipt = ledger.find_one({"provider_receipt": receipt, "checkout_id": {"$ne": str(checkout["_id"])}})
    if duplicate_receipt:
        rows.update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "status": "receipt_conflict",
                "receipt": receipt,
                "message": "This provider receipt is already linked to another Elimu checkout; manual reconciliation is required.",
                "updated_at": _now(),
            }},
        )
        return {"ResultCode": 0, "ResultDesc": "Payment receipt flagged for reconciliation"}, 200

    payment_ledger = {
        "checkout_id": str(checkout["_id"]),
        "school_id": _text(checkout.get("school_id"), 160),
        "student_id": _text(checkout.get("student_id"), 160),
        "admission_number": _text(checkout.get("admission_number"), 120),
        "provider": "mpesa",
        "provider_receipt": receipt,
        "checkout_request_id": checkout_id,
        "merchant_request_id": stored_merchant,
        "amount": float(checkout.get("amount") or 0),
        "currency": "KES",
        "fee_allocations": checkout.get("fee_allocations") if isinstance(checkout.get("fee_allocations"), list) else [],
        "status": "verified_pending_allocation",
        "verified_at": _now(),
        "created_at": checkout.get("created_at") or _now(),
    }
    try:
        ledger.update_one(
            {"checkout_id": str(checkout["_id"])},
            {"$setOnInsert": payment_ledger},
            upsert=True,
        )
    except Exception:
        rows.update_one(
            {"_id": checkout["_id"]},
            {"$set": {"status": "verified_pending_allocation", "receipt": receipt, "message": "Payment was verified but its accounting ledger could not be written yet.", "updated_at": _now()}},
        )
        return {"ResultCode": 0, "ResultDesc": "Payment verified; accounting allocation pending"}, 200

    school_id = _text(checkout.get("school_id"), 160)
    allocation_conflicts = []
    applied_fee_ids = []
    allocations = checkout.get("fee_allocations") if isinstance(checkout.get("fee_allocations"), list) else []
    for allocation in allocations:
        fee_id = _text(allocation.get("fee_id"), 160)
        amount = _safe_money(allocation.get("amount"))
        if not fee_id or amount <= 0:
            allocation_conflicts.append(fee_id or "unknown")
            continue
        candidates = _id_candidates(fee_id)
        existing_fee = collection(FEES).find_one({
            "school_id": school_id,
            "_id": {"$in": candidates},
            "applied_mpesa_checkouts": str(checkout["_id"]),
        })
        if existing_fee:
            applied_fee_ids.append(fee_id)
            continue

        from pymongo import ReturnDocument
        paid_expression = {"$ifNull": ["$amount_paid", {"$ifNull": ["$paid_amount", 0]}]}
        next_paid_expression = {"$add": [paid_expression, amount]}
        updated_fee = collection(FEES).find_one_and_update(
            {
                "school_id": school_id,
                "_id": {"$in": candidates},
                "active_mpesa_checkout_id": str(checkout["_id"]),
                "applied_mpesa_checkouts": {"$ne": str(checkout["_id"])},
                "$expr": {
                    "$gte": [
                        {"$subtract": [{"$ifNull": ["$amount", 0]}, paid_expression]},
                        amount,
                    ]
                },
            },
            [
                {"$set": {
                    "amount_paid": next_paid_expression,
                    "paid_amount": next_paid_expression,
                    "status": {"$cond": [{"$gte": [next_paid_expression, {"$ifNull": ["$amount", 0]}]}, "paid", "partial"]},
                    "applied_mpesa_checkouts": {
                        "$concatArrays": [{"$ifNull": ["$applied_mpesa_checkouts", []]}, [str(checkout["_id"])]]
                    },
                    "last_mpesa_receipt": receipt,
                    "last_mpesa_payment_at": _now(),
                    "last_mpesa_payment_amount": amount,
                    "updated_at": _now(),
                }},
                {"$unset": ["active_mpesa_checkout_id", "active_mpesa_checkout_started_at"]},
            ],
            return_document=ReturnDocument.AFTER,
        )
        if not updated_fee:
            allocation_conflicts.append(fee_id)
        else:
            applied_fee_ids.append(fee_id)

    if allocation_conflicts:
        rows.update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "status": "allocation_conflict",
                "receipt": receipt,
                "applied_fee_ids": applied_fee_ids,
                "allocation_conflict_fee_ids": allocation_conflicts,
                "message": "Payment was verified by Daraja but one or more fee balances changed. Manual reconciliation is required; do not request another payment.",
                "updated_at": _now(),
            }},
        )
        ledger.update_one(
            {"checkout_id": str(checkout["_id"])},
            {"$set": {"status": "verified_allocation_conflict", "applied_fee_ids": applied_fee_ids, "conflict_fee_ids": allocation_conflicts, "updated_at": _now()}},
        )
        _clear_elimu_fee_locks(school_id, str(checkout["_id"]))
        log_action(
            user_id="mpesa-callback",
            action="elimu.fees.mpesa_allocation_conflict",
            resource="elimu_fee_checkout",
            resource_id=str(checkout["_id"]),
            metadata={"school_id": school_id, "receipt": receipt, "applied_fee_count": len(applied_fee_ids), "conflict_count": len(allocation_conflicts)},
        )
        return {"ResultCode": 0, "ResultDesc": "Payment verified; allocation requires reconciliation"}, 200

    rows.update_one(
        {"_id": checkout["_id"]},
        {"$set": {
            "status": "succeeded",
            "receipt": receipt,
            "result_code": "0",
            "result_description": "Payment verified and allocated to school fee voteheads.",
            "verified_at": _now(),
            "applied_fee_ids": applied_fee_ids,
            "updated_at": _now(),
        }},
    )
    ledger.update_one(
        {"checkout_id": str(checkout["_id"])},
        {"$set": {"status": "applied", "updated_at": _now(), "applied_at": _now(), "applied_fee_ids": applied_fee_ids}},
    )
    log_action(
        user_id="mpesa-callback",
        action="elimu.fees.mpesa_payment_reconciled",
        resource="elimu_fee_payment",
        resource_id=str(checkout["_id"]),
        metadata={
            "school_id": school_id,
            "student_id": _text(checkout.get("student_id"), 160),
            "amount": _safe_money(checkout.get("amount")),
            "receipt": receipt,
            "fee_count": len(applied_fee_ids),
        },
    )
    return {"ResultCode": 0, "ResultDesc": "M-Pesa payment reconciled"}, 200


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
            inbound_messages = value.get("messages") if isinstance(value.get("messages"), list) else []
            for inbound in inbound_messages:
                if not isinstance(inbound, dict) or _text(inbound.get("type"), 30).lower() != "text":
                    continue
                message_id = _text(inbound.get("id"), 240)
                sender = _text(inbound.get("from"), 80)
                message_body = inbound.get("text") if isinstance(inbound.get("text"), dict) else {}
                text_body = _text(message_body.get("body"), 500)
                if not message_id or not sender or not text_body:
                    continue

                # Idempotency prevents Meta retrying the same webhook from sending
                # duplicate private fee statements to the parent.
                inbound_collection = collection("jumuiya_elimu_whatsapp_inbound")
                try:
                    from pymongo import ReturnDocument
                    recorded = inbound_collection.find_one_and_update(
                        {"_id": message_id},
                        {"$setOnInsert": {
                            "sender_hash": hashlib.sha256(sender.encode("utf-8")).hexdigest()[:24],
                            "message_type": "text",
                            "status": "received",
                            "created_at": _now(),
                        }},
                        upsert=True,
                        return_document=ReturnDocument.AFTER,
                    )
                    is_new_message = bool(recorded and recorded.get("status") == "received" and recorded.get("sender_hash") == hashlib.sha256(sender.encode("utf-8")).hexdigest()[:24])
                    # A previously processed event may still have status received if
                    # a prior handler crashed. Marking the claim separately avoids
                    # repeating a response during delivery retries.
                    claim = inbound_collection.update_one(
                        {"_id": message_id, "status": "received"},
                        {"$set": {"status": "processing", "processing_started_at": _now()}},
                    ) if is_new_message else None
                    if not claim or claim.modified_count != 1:
                        continue
                    reply = _handle_whatsapp_fee_query(sender, text_body, message_id)
                    reply_id = _send_whatsapp_text(_normalize_whatsapp_phone(sender), reply)
                    inbound_collection.update_one(
                        {"_id": message_id, "status": "processing"},
                        {"$set": {"status": "replied", "outbound_message_id": reply_id, "replied_at": _now()}},
                    )
                except Exception:
                    # Webhook callbacks must be acknowledged; do not expose parent
                    # data, access tokens, or provider diagnostics in responses.
                    try:
                        inbound_collection.update_one(
                            {"_id": message_id, "status": {"$in": ["received", "processing"]}},
                            {"$set": {"status": "delivery_failed", "updated_at": _now()}},
                        )
                    except Exception:
                        pass

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
