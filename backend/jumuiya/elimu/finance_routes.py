"""School fee payment instructions and receipt reconciliation.

This module stores school-owned payment instructions and submitted receipt
claims in the existing Jumuiya Elimu database. It deliberately does not claim
to initiate an M-Pesa STK push, charge a bank account, or verify external
settlement without a configured payment-provider integration.
"""
from __future__ import annotations

from datetime import datetime, timezone
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
    new_status = "approved" if decision == "approve" else "rejected"
    if decision == "approve":
        fee_id = _text(receipt.get("fee_id"), 160)
        fee = collection(FEES).find_one(_fee_query(school_id, fee_id))
        if not fee or _text(fee.get("student_id"), 160) != _text(receipt.get("student_id"), 160):
            raise APIError("The linked fee record is no longer available for this student.", 409, "fee_receipt_scope_conflict")
        total = float(fee.get("amount") or 0)
        paid = float(fee.get("amount_paid") if fee.get("amount_paid") is not None else fee.get("paid_amount") or 0)
        amount = float(receipt.get("amount") or 0)
        balance = max(total - paid, 0.0)
        if amount <= 0 or amount > balance + 0.0001:
            raise APIError("The receipt amount now exceeds the outstanding balance. Reconcile the fee record before approving this receipt.", 409, "fee_balance_changed")
        status = "paid" if paid + amount >= total - 0.0001 else "partially_paid"
        fee_candidates = _id_candidates(str(fee.get("_id") or fee.get("id") or fee_id))
        from pymongo import ReturnDocument
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
            {"$set": {
                "amount_paid": round(paid + amount, 2),
                "paid_amount": round(paid + amount, 2),
                "status": status,
                "last_receipt_reviewed_at": now,
                "updated_at": now,
            }},
            return_document=ReturnDocument.AFTER,
        )
        if not updated_fee:
            raise APIError("The outstanding balance changed while this receipt was reviewed. Refresh and retry.", 409, "fee_balance_changed")

    updated_receipt = collection(RECEIPTS).find_one_and_update(
        {"_id": receipt["_id"], "school_id": school_id, "status": "pending"},
        {"$set": {
            "status": new_status,
            "review_notes": notes,
            "reviewed_by": _uid(uid),
            "reviewed_at": now,
            "updated_at": now,
        }},
        return_document=__import__("pymongo").ReturnDocument.AFTER,
    )
    if not updated_receipt:
        raise APIError("Receipt was reviewed by another staff member. Refresh the queue.", 409, "fee_receipt_already_reviewed")

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
