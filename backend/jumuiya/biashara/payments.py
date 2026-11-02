"""Biashara invoice M-Pesa checkout.

Daraja callbacks are triggers only. A payment is allocated only after a Daraja
STK Push Query confirms the exact checkout and the callback receipt, amount and
payer match the stored invoice intent. Unknown submissions hold an invoice slot
until reconciliation rather than permitting a duplicate charge.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, request
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.db import client
from backend.jumuiya.biashara.services import _require_business
from backend.jumuiya.biashara.tenant_store import tenant_collection
from backend.jumuiya.core.database import collection as core_collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import require_authenticated, current_user_id
from backend.jumuiya.core.responses import ok, created
from backend.revenue import mpesa as daraja


payments_bp = Blueprint("jumuiya_biashara_payments", __name__)
PAYMENT_INDEX = "jumuiya_biashara_mpesa_checkout_index"
INTENTS = "jumuiya_biashara_payment_intents"
INVOICES = "jumuiya_biashara_invoices"
ALLOCATIONS = "jumuiya_biashara_payment_allocations"
CALLBACK_PATH = "/api/jumuiya/biashara/payments/mpesa/callback"
PENDING_STATES = {
    "initiating", "pending", "submission_unknown", "awaiting_verification",
    "receipt_conflict", "allocation_pending", "allocation_conflict",
}


def _now():
    return datetime.now(timezone.utc)


def _id(value):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError, ValueError):
        raise APIError("A valid invoice or payment ID is required.", 422, "invalid_resource_id")


def _decimal(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise APIError(f"{field} is invalid.", 422, "invalid_amount")
    if not result.is_finite() or result < 0:
        raise APIError(f"{field} must be a non-negative amount.", 422, "invalid_amount")
    return result.quantize(Decimal("0.01"))


def _serialize(document):
    if not document:
        return None
    result = dict(document)
    if "_id" in result:
        result["id"] = str(result.pop("_id"))
    for key, value in list(result.items()):
        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif hasattr(value, "isoformat"):
            result[key] = value.isoformat()
    return result


def _phone(value):
    if not isinstance(value, str):
        raise APIError("Enter a valid Kenyan M-Pesa phone number.", 422, "invalid_phone")
    raw = re.sub(r"[\s()+-]", "", value.strip())
    if raw.startswith("0") and len(raw) == 10:
        raw = "254" + raw[1:]
    elif (raw.startswith("7") or raw.startswith("1")) and len(raw) == 9:
        raw = "254" + raw
    if not re.fullmatch(r"254[17][0-9]{8}", raw):
        raise APIError("Use a Kenyan mobile number such as 0712345678 or 254712345678.", 422, "invalid_phone")
    return raw


def _callback_url():
    value = os.getenv("BIASHARA_MPESA_CALLBACK_URL", "").strip()
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path.rstrip("/") != CALLBACK_PATH
            or parsed.query
            or parsed.fragment
        ):
            return ""
    except ValueError:
        return ""
    return value


def _configuration_status():
    shortcode = os.getenv("MPESA_SHORTCODE", "").strip()
    transaction_type = os.getenv("MPESA_TRANSACTION_TYPE", "CustomerPayBillOnline").strip()
    required = {
        "daraja_environment": daraja._environment() == "production",
        "daraja_base_url": bool(daraja._base_url()),
        "consumer_key": bool(os.getenv("MPESA_CONSUMER_KEY", "").strip()),
        "consumer_secret": bool(os.getenv("MPESA_CONSUMER_SECRET", "").strip()),
        "shortcode": bool(shortcode.isdigit()),
        "passkey": bool(os.getenv("MPESA_PASSKEY", "").strip()),
        "stk_path": bool(daraja._endpoint_path("MPESA_STK_PATH")),
        "query_path": bool(daraja._endpoint_path("MPESA_STK_QUERY_PATH")),
        "transaction_type": transaction_type in {"CustomerPayBillOnline", "CustomerBuyGoodsOnline"},
        "callback_url": bool(_callback_url()),
        "provider_allowlist": "mpesa" in {
            item.strip().lower()
            for item in os.getenv("REVENUE_PAYMENT_PROVIDERS", "").split(",")
            if item.strip()
        },
    }
    return {
        "provider": "mpesa",
        "environment": daraja._environment() or "invalid",
        "ready": all(required.values()),
        "checks": required,
        "blockers": [key for key, valid in required.items() if not valid],
        "note": "This checks configuration shape only. A low-value live transaction and callback/query reconciliation test are still required.",
    }


def _business(permission="invoices.allocate"):
    uid = str(current_user_id())
    business = _require_business(uid, permission=permission)
    return uid, business


def _collections(business_id):
    return {
        "intents": tenant_collection(INTENTS, business_id),
        "invoices": tenant_collection(INVOICES, business_id),
        "allocations": tenant_collection(ALLOCATIONS, business_id),
    }


def _ensure_indexes(business_id):
    c = _collections(business_id)
    c["intents"].create_index(
        [("business_id", ASCENDING), ("idempotency_key", ASCENDING)],
        unique=True, name="uq_biashara_mpesa_idempotency",
    )
    c["intents"].create_index(
        [("business_id", ASCENDING), ("invoice_id", ASCENDING), ("active_slot", ASCENDING)],
        unique=True, partialFilterExpression={"active_slot": {"$type": "string"}},
        name="uq_biashara_invoice_active_checkout",
    )
    c["allocations"].create_index(
        [("business_id", ASCENDING), ("provider_receipt", ASCENDING)],
        unique=True, partialFilterExpression={"provider_receipt": {"$type": "string"}},
        name="uq_biashara_mpesa_receipt",
    )
    index = core_collection(PAYMENT_INDEX)
    index.create_index([("checkout_request_id", ASCENDING)], unique=True, name="uq_biashara_global_checkout")
    index.create_index([("business_id", ASCENDING), ("created_at", ASCENDING)], name="ix_biashara_checkout_business")


def _payment_index():
    return core_collection(PAYMENT_INDEX)


def _callback_metadata(callback):
    metadata = callback.get("CallbackMetadata") if isinstance(callback, dict) else {}
    items = metadata.get("Item") if isinstance(metadata, dict) else []
    result = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "")
        if name in {"Amount", "MpesaReceiptNumber", "PhoneNumber"}:
            result[name] = item.get("Value")
    return result


def _update_intent_status(collections, intent, status, message, extra=None, clear_slot=False):
    update = {"status": status, "status_message": str(message or "")[:500], "updated_at": _now()}
    if extra:
        update.update(extra)
    operation = {"$set": update}
    if clear_slot:
        operation["$unset"] = {"active_slot": ""}
    collections["intents"].update_one(
        {"_id": intent["_id"], "business_id": intent["business_id"]},
        operation,
    )
    return collections["intents"].find_one({"_id": intent["_id"], "business_id": intent["business_id"]})


def _query_daraja(intent):
    timestamp = daraja._timestamp()
    shortcode = os.getenv("MPESA_SHORTCODE", "").strip()
    result = daraja._daraja_post(
        "/mpesa/stkpushquery/v1/query",
        {
            "BusinessShortCode": shortcode,
            "Password": daraja._password(timestamp),
            "Timestamp": timestamp,
            "CheckoutRequestID": intent["checkout_request_id"],
        },
    )
    return result if isinstance(result, dict) else {}


def _finalize_confirmed_payment(business_id, intent_id, query_result, callback_meta):
    c = _collections(business_id)
    intents = c["intents"]
    intent = intents.find_one({"_id": _id(intent_id), "business_id": business_id})
    if not intent:
        return False, "Payment intent not found."
    if intent.get("status") == "succeeded":
        return True, "Payment already allocated."

    checkout_id = str(query_result.get("CheckoutRequestID") or "")
    merchant_id = str(query_result.get("MerchantRequestID") or "")
    if (
        checkout_id != str(intent.get("checkout_request_id") or "")
        or merchant_id != str(intent.get("merchant_request_id") or "")
        or str(query_result.get("ResultCode")) != "0"
    ):
        return False, "Daraja did not confirm this exact checkout as successful."

    receipt = str(callback_meta.get("MpesaReceiptNumber") or "").strip().upper()
    callback_amount = callback_meta.get("Amount")
    callback_phone = callback_meta.get("PhoneNumber")
    if not receipt or len(receipt) > 40:
        _update_intent_status(c, intent, "receipt_conflict", "Final success was queried, but a valid M-Pesa receipt was not supplied.")
        return False, "A provider receipt is required before allocation."
    try:
        received_amount = Decimal(str(callback_amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        received_amount = Decimal("-1")
    if received_amount != Decimal(str(intent["amount"])).quantize(Decimal("0.01")):
        _update_intent_status(c, intent, "receipt_conflict", "Callback amount did not match the invoice checkout.")
        return False, "Callback amount did not match the stored invoice intent."
    try:
        received_phone = _phone(str(callback_phone))
    except APIError:
        received_phone = ""
    if received_phone != intent.get("phone"):
        _update_intent_status(c, intent, "receipt_conflict", "Callback payer did not match the STK recipient.")
        return False, "Callback payer did not match the intended phone number."

    invoice = c["invoices"].find_one({
        "_id": _id(intent["invoice_id"]),
        "business_id": business_id,
    })
    if not invoice:
        _update_intent_status(c, intent, "allocation_conflict", "The original invoice no longer exists.")
        return False, "Invoice was not found."
    total = _decimal(invoice.get("total"), "invoice total")
    allocated = _decimal(invoice.get("allocated_amount", "0"), "invoice allocated amount")
    amount = _decimal(intent.get("amount"), "payment amount")
    if allocated + amount > total:
        _update_intent_status(c, intent, "allocation_conflict", "Invoice balance changed after the checkout was started.")
        return False, "The invoice balance changed. Manual reconciliation is required."

    now = _now()
    allocation = {
        "owner_user_id": intent["user_id"],
        "business_id": business_id,
        "invoice_id": str(invoice["_id"]),
        "amount": str(amount),
        "currency": invoice.get("currency", "KES"),
        "method": "mobile_money",
        "reference": receipt,
        "provider": "mpesa",
        "provider_receipt": receipt,
        "provider_checkout_request_id": checkout_id,
        "verification_status": "provider_verified",
        "recorded_by_user_id": intent["user_id"],
        "created_at": now,
    }
    new_allocated = allocated + amount
    new_status = "fully_allocated" if new_allocated == total else "partially_allocated"
    try:
        with client.start_session() as session:
            with session.start_transaction():
                existing_receipt = c["allocations"].find_one(
                    {"business_id": business_id, "provider_receipt": receipt},
                    session=session,
                )
                if existing_receipt:
                    if existing_receipt.get("invoice_id") == str(invoice["_id"]) and existing_receipt.get("provider_checkout_request_id") == checkout_id:
                        intents.update_one(
                            {"_id": intent["_id"], "business_id": business_id},
                            {"$set": {"status": "succeeded", "provider_receipt": receipt, "updated_at": now}, "$unset": {"active_slot": ""}},
                            session=session,
                        )
                        return True, "Payment receipt was already allocated."
                    raise APIError("This provider receipt is already allocated to another invoice.", 409, "mpesa_receipt_reused")
                c["allocations"].insert_one(allocation, session=session)
                invoice_update = c["invoices"].update_one(
                    {"_id": invoice["_id"], "business_id": business_id, "allocated_amount": str(allocated)},
                    {"$set": {"allocated_amount": str(new_allocated), "status": new_status, "updated_at": now}},
                    session=session,
                )
                if not invoice_update.modified_count:
                    raise APIError("Invoice changed during payment allocation.", 409, "invoice_allocation_conflict")
                intents.update_one(
                    {"_id": intent["_id"], "business_id": business_id, "status": {"$in": list(PENDING_STATES)}},
                    {"$set": {"status": "succeeded", "provider_receipt": receipt, "succeeded_at": now, "updated_at": now}, "$unset": {"active_slot": ""}},
                    session=session,
                )
    except DuplicateKeyError:
        existing_receipt = c["allocations"].find_one({"business_id": business_id, "provider_receipt": receipt})
        if existing_receipt and existing_receipt.get("provider_checkout_request_id") == checkout_id:
            return True, "Payment receipt was already allocated."
        _update_intent_status(c, intent, "receipt_conflict", "M-Pesa receipt number was already used.")
        return False, "M-Pesa receipt number was already used."
    except APIError as exc:
        _update_intent_status(c, intent, "allocation_conflict", str(exc))
        return False, str(exc)
    except Exception:
        _update_intent_status(c, intent, "allocation_pending", "Payment was provider-confirmed but invoice allocation needs database transaction support.")
        return False, "Payment was confirmed; allocation requires database transaction support."

    _payment_index().update_one(
        {"checkout_request_id": checkout_id, "business_id": business_id},
        {"$set": {"status": "succeeded", "provider_receipt": receipt, "updated_at": now}},
    )
    return True, "M-Pesa payment verified and allocated."


@payments_bp.get("/integrations/mpesa/status")
@require_authenticated
def mpesa_status():
    uid, business = _business("invoices.view")
    return ok(_configuration_status())


@payments_bp.post("/finance/invoices/<invoice_id>/mpesa/stk-push")
@require_authenticated
def start_invoice_stk_push(invoice_id):
    uid, business = _business("invoices.allocate")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("A JSON request body is required.", 400, "invalid_json")
    config = _configuration_status()
    if not config["ready"]:
        raise APIError("Biashara M-Pesa checkout is not configured for production.", 503, "mpesa_not_configured")

    raw_idempotency = request.headers.get("Idempotency-Key") or ""
    idempotency_key = str(raw_idempotency).strip()
    if not idempotency_key or len(idempotency_key) > 160:
        raise APIError("A valid Idempotency-Key request header is required.", 422, "idempotency_key_required")
    phone = _phone(data.get("phone"))
    c = _collections(business["id"])
    _ensure_indexes(business["id"])

    prior = c["intents"].find_one({"business_id": business["id"], "idempotency_key": idempotency_key})
    if prior:
        return ok(_serialize(prior), "Existing M-Pesa checkout intent returned; no new prompt was sent.")

    invoice = c["invoices"].find_one({"_id": _id(invoice_id), "business_id": business["id"]})
    if not invoice:
        raise APIError("Invoice was not found in this company.", 404, "invoice_not_found")
    if str(invoice.get("currency") or "KES").upper() != "KES":
        raise APIError("M-Pesa STK checkout is available only for KES invoices.", 422, "invoice_currency_unsupported")
    total = _decimal(invoice.get("total"), "invoice total")
    allocated = _decimal(invoice.get("allocated_amount", "0"), "invoice allocated amount")
    amount = total - allocated
    if amount <= 0:
        raise APIError("This invoice has no outstanding balance.", 409, "invoice_fully_allocated")
    if amount != amount.to_integral_value():
        raise APIError("Daraja STK Push accepts whole-KES amounts for this checkout. Resolve decimal balances before charging.", 422, "mpesa_whole_kes_required")

    now = _now()
    intent = {
        "_id": ObjectId(),
        "business_id": business["id"],
        "user_id": uid,
        "invoice_id": str(invoice["_id"]),
        "invoice_number": str(invoice.get("invoice_number") or ""),
        "amount": str(amount.quantize(Decimal("0.01"))),
        "currency": "KES",
        "phone": phone,
        "idempotency_key": idempotency_key,
        "active_slot": str(invoice["_id"]),
        "status": "initiating",
        "created_at": now,
        "updated_at": now,
    }
    try:
        c["intents"].insert_one(intent)
    except DuplicateKeyError:
        prior = c["intents"].find_one({"business_id": business["id"], "idempotency_key": idempotency_key})
        if prior:
            return ok(_serialize(prior), "Existing M-Pesa checkout intent returned.")
        raise APIError("An unresolved M-Pesa checkout already exists for this invoice.", 409, "mpesa_checkout_already_pending")

    timestamp = daraja._timestamp()
    shortcode = os.getenv("MPESA_SHORTCODE", "").strip()
    transaction_type = os.getenv("MPESA_TRANSACTION_TYPE", "CustomerPayBillOnline").strip()
    party_b = os.getenv("MPESA_PARTY_B", "").strip() or shortcode
    payload = {
        "BusinessShortCode": shortcode,
        "Password": daraja._password(timestamp),
        "Timestamp": timestamp,
        "TransactionType": transaction_type,
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": party_b,
        "PhoneNumber": phone,
        "CallBackURL": _callback_url(),
        "AccountReference": str(invoice.get("invoice_number") or "BIASHARA")[:12],
        "TransactionDesc": ("Invoice " + str(invoice.get("invoice_number") or ""))[:80],
    }
    try:
        result = daraja._daraja_post("/mpesa/stkpush/v1/processrequest", payload)
    except Exception:
        _update_intent_status(c, intent, "submission_unknown", "Daraja did not confirm whether the STK request was accepted.")
        return ok(_serialize(c["intents"].find_one({"_id": intent["_id"]})),
                  "STK submission is uncertain. Do not request another prompt; reconcile this checkout first.")

    response_code = str(result.get("ResponseCode") or "")
    if response_code != "0":
        _update_intent_status(c, intent, "initiation_failed",
                              str(result.get("ResponseDescription") or "Daraja rejected the request."),
                              clear_slot=True)
        raise APIError("Daraja rejected the M-Pesa STK request.", 502, "mpesa_stk_rejected")
    checkout_id = str(result.get("CheckoutRequestID") or "").strip()
    merchant_id = str(result.get("MerchantRequestID") or "").strip()
    if not checkout_id or not merchant_id:
        _update_intent_status(c, intent, "submission_unknown", "Daraja accepted the request but returned incomplete request identifiers.")
        return ok(_serialize(c["intents"].find_one({"_id": intent["_id"]})),
                  "STK request identifiers are incomplete. Reconciliation is required before retrying.")

    c["intents"].update_one(
        {"_id": intent["_id"], "business_id": business["id"]},
        {"$set": {
            "checkout_request_id": checkout_id,
            "merchant_request_id": merchant_id,
            "daraja_response_code": response_code,
            "daraja_response_description": str(result.get("ResponseDescription") or "")[:300],
            "status": "pending",
            "updated_at": _now(),
        }},
    )
    _payment_index().insert_one({
        "business_id": business["id"],
        "intent_id": str(intent["_id"]),
        "invoice_id": str(invoice["_id"]),
        "checkout_request_id": checkout_id,
        "merchant_request_id": merchant_id,
        "status": "pending",
        "created_at": now,
        "updated_at": _now(),
    })
    intent = c["intents"].find_one({"_id": intent["_id"], "business_id": business["id"]})
    return created(_serialize(intent), "STK Push submitted. Payment remains pending until provider reconciliation confirms it.")


@payments_bp.post("/payments/mpesa/callback")
def receive_biashara_mpesa_callback():
    payload = request.get_json(silent=True)
    callback = payload.get("Body", {}).get("stkCallback", {}) if isinstance(payload, dict) else {}
    checkout_id = str(callback.get("CheckoutRequestID") or "").strip()
    merchant_id = str(callback.get("MerchantRequestID") or "").strip()
    if not checkout_id:
        return {"ResultCode": 0, "ResultDesc": "Callback acknowledged"}, 200
    index = _payment_index().find_one({"checkout_request_id": checkout_id})
    if not index:
        return {"ResultCode": 0, "ResultDesc": "Unknown Biashara checkout acknowledged"}, 200
    business_id = str(index.get("business_id") or "")
    intent_id = str(index.get("intent_id") or "")
    c = _collections(business_id)
    intent = c["intents"].find_one({"_id": _id(intent_id), "business_id": business_id})
    if not intent:
        _payment_index().update_one({"checkout_request_id": checkout_id}, {"$set": {"status": "orphaned", "updated_at": _now()}})
        return {"ResultCode": 0, "ResultDesc": "Checkout index acknowledged"}, 200
    if intent.get("status") == "succeeded":
        return {"ResultCode": 0, "ResultDesc": "Payment already reconciled"}, 200
    if merchant_id != str(intent.get("merchant_request_id") or ""):
        _update_intent_status(c, intent, "awaiting_verification", "Callback identifiers did not match the stored checkout.")
        return {"ResultCode": 0, "ResultDesc": "Callback acknowledged for reconciliation"}, 200
    callback_meta = _callback_metadata(callback)
    c["intents"].update_one(
        {"_id": intent["_id"], "business_id": business_id},
        {"$set": {"last_callback_metadata": callback_meta, "callback_received_at": _now(), "updated_at": _now()}},
    )
    try:
        query_result = _query_daraja(intent)
    except Exception:
        _update_intent_status(c, intent, "awaiting_verification", "Provider query is temporarily unavailable.")
        return {"ResultCode": 0, "ResultDesc": "Callback acknowledged for reconciliation"}, 200
    query_code = query_result.get("ResultCode")
    if query_code is None:
        _update_intent_status(c, intent, "awaiting_verification", "Provider query has not returned a final result.")
        return {"ResultCode": 0, "ResultDesc": "Callback acknowledged for reconciliation"}, 200
    if str(query_code) != "0":
        _update_intent_status(c, intent, "failed", str(query_result.get("ResultDesc") or "Payment was not completed."), clear_slot=True)
        _payment_index().update_one({"checkout_request_id": checkout_id}, {"$set": {"status": "failed", "updated_at": _now()}})
        return {"ResultCode": 0, "ResultDesc": "Payment result recorded"}, 200
    success, message = _finalize_confirmed_payment(business_id, intent_id, query_result, callback_meta)
    if not success:
        _payment_index().update_one({"checkout_request_id": checkout_id}, {"$set": {"status": "reconciliation_required", "message": message[:500], "updated_at": _now()}})
    return {"ResultCode": 0, "ResultDesc": "Callback accepted; reconciliation status recorded"}, 200


@payments_bp.get("/finance/invoices/<invoice_id>/mpesa/status")
@require_authenticated
def invoice_mpesa_status(invoice_id):
    uid, business = _business("invoices.view")
    c = _collections(business["id"])
    invoice = c["invoices"].find_one({"_id": _id(invoice_id), "business_id": business["id"]})
    if not invoice:
        raise APIError("Invoice was not found.", 404, "invoice_not_found")
    rows = c["intents"].find({"business_id": business["id"], "invoice_id": str(invoice["_id"])}).sort("created_at", -1).limit(5)
    return ok({"invoice_id": str(invoice["_id"]), "checkouts": [_serialize(item) for item in rows]})
