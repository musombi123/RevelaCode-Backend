"""Safaricom Daraja STK Push checkout and callback adapter.

This adapter uses the existing backend database gateway and revenue records.
Callbacks are treated as notifications, not proof by themselves: subscription
activation requires an STK Push Query response for the same CheckoutRequestID
with a final ResultCode of zero. If Daraja returns an accepted-but-pending
query response, the checkout remains pending for later reconciliation.
"""
from __future__ import annotations

import base64
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
from flask import current_app, jsonify, request
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.audit import log_action, now_utc
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.revenue import revenue_bp
from backend.revenue.money import MoneyValidationError, to_money
from backend.revenue.plans import get_plan
from backend.revenue.subscriptions import activate_verified_payment

logger = logging.getLogger("jumuiya.revenue.mpesa")
CHECKOUTS_COLLECTION = "jumuiya_revenue_mpesa_checkouts"
TOKEN_LOCK = threading.Lock()
_TOKEN = None
_TOKEN_EXPIRES = 0.0
HTTP_TIMEOUT = 12.0


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _environment() -> str:
    value = _env("MPESA_ENV", "sandbox").lower()
    return value if value in {"sandbox", "production"} else ""


def _base_url() -> str:
    environment = _environment()
    if environment == "sandbox":
        return "https://sandbox.safaricom.co.ke"
    if environment == "production":
        return "https://api.safaricom.co.ke"
    return ""


def checkout_is_configured() -> bool:
    """Return Daraja configuration readiness without exposing credentials."""
    callback = _env("MPESA_CALLBACK_URL")
    try:
        from urllib.parse import urlsplit
        parsed = urlsplit(callback)
        callback_ok = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        callback_ok = False
    return bool(
        _base_url()
        and _env("MPESA_CONSUMER_KEY")
        and _env("MPESA_CONSUMER_SECRET")
        and _env("MPESA_SHORTCODE").isdigit()
        and _env("MPESA_PASSKEY")
        and callback_ok
    )


def checkout_is_production_configured() -> bool:
    """Only live Daraja configuration may expose paid checkout/activation."""
    return _environment() == "production" and checkout_is_configured()


def _checkout_rows():
    rows = collection(CHECKOUTS_COLLECTION)
    rows.create_index(
        [("user_id", ASCENDING), ("idempotency_key", ASCENDING)],
        unique=True,
        name="uq_mpesa_checkout_user_idempotency",
    )
    rows.create_index(
        [("checkout_request_id", ASCENDING)],
        unique=True,
        sparse=True,
        name="uq_mpesa_checkout_request",
    )
    rows.create_index(
        [("merchant_request_id", ASCENDING)],
        sparse=True,
        name="ix_mpesa_merchant_request",
    )
    rows.create_index([("created_at", DESCENDING)], name="ix_mpesa_checkout_created")
    return rows


def _error(message, status=400, code="invalid_request"):
    return jsonify({
        "success": False,
        "message": message,
        "error": {"message": message, "code": code},
        "code": code,
    }), status


def _phone(value):
    if not isinstance(value, str):
        raise ValueError("Enter a valid Kenyan M-Pesa phone number.")
    raw = re.sub(r"[\s()+-]", "", value.strip())
    if raw.startswith("0") and len(raw) == 10:
        raw = "254" + raw[1:]
    elif raw.startswith("7") or raw.startswith("1"):
        if len(raw) == 9:
            raw = "254" + raw
    if not re.fullmatch(r"254[17][0-9]{8}", raw):
        raise ValueError("Use a Kenyan mobile number such as 0712345678 or 254712345678.")
    return raw


def _timestamp():
    return datetime.now(timezone(timedelta(hours=3))).strftime("%Y%m%d%H%M%S")


def _password(timestamp):
    shortcode = _env("MPESA_SHORTCODE")
    raw = f"{shortcode}{_env('MPESA_PASSKEY')}{timestamp}"
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def _access_token():
    global _TOKEN, _TOKEN_EXPIRES
    now = time.monotonic()
    if _TOKEN and now < _TOKEN_EXPIRES - 60:
        return _TOKEN
    with TOKEN_LOCK:
        now = time.monotonic()
        if _TOKEN and now < _TOKEN_EXPIRES - 60:
            return _TOKEN
        key, secret = _env("MPESA_CONSUMER_KEY"), _env("MPESA_CONSUMER_SECRET")
        if not key or not secret or not _base_url():
            raise RuntimeError("M-Pesa Daraja credentials are not configured.")
        try:
            response = requests.get(
                _base_url() + "/oauth/v1/generate",
                params={"grant_type": "client_credentials"},
                auth=(key, secret),
                headers={"Accept": "application/json"},
                timeout=HTTP_TIMEOUT,
                allow_redirects=False,
                proxies={"http": "", "https": ""},
            )
        except requests.RequestException:
            raise RuntimeError("Daraja authentication service is unavailable.") from None
        if 300 <= response.status_code < 400 or response.status_code != 200:
            raise RuntimeError("Daraja authentication request was rejected.")
        try:
            data = response.json()
        except ValueError:
            raise RuntimeError("Daraja returned an invalid authentication response.") from None
        token = str(data.get("access_token") or "").strip() if isinstance(data, dict) else ""
        if not token:
            raise RuntimeError("Daraja authentication response did not include an access token.")
        try:
            expiry = int(data.get("expires_in", 3600))
        except (TypeError, ValueError):
            expiry = 3600
        _TOKEN = token
        _TOKEN_EXPIRES = time.monotonic() + min(max(expiry, 120), 3600)
        return token


def _daraja_post(path, payload):
    token = _access_token()
    try:
        response = requests.post(
            _base_url() + path,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=HTTP_TIMEOUT,
            allow_redirects=False,
            proxies={"http": "", "https": ""},
        )
    except requests.RequestException:
        raise RuntimeError("Daraja payment service is unavailable.") from None
    if 300 <= response.status_code < 400 or response.status_code != 200:
        logger.warning("Daraja request rejected | path=%s status=%s", path, response.status_code)
        raise RuntimeError("Daraja did not accept the payment request.")
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError("Daraja returned an invalid response.") from None
    if not isinstance(data, dict):
        raise RuntimeError("Daraja returned an invalid response.")
    return data


def _query_checkout(checkout):
    """Query Daraja for the final result of the server-created STK checkout."""
    timestamp = _timestamp()
    shortcode = _env("MPESA_SHORTCODE")
    return _daraja_post(
        "/mpesa/stkpushquery/v1/query",
        {
            "BusinessShortCode": shortcode,
            "Password": _password(timestamp),
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout["checkout_request_id"],
        },
    )


def _public_checkout(row):
    return {
        "id": str(row.get("_id", "")),
        "hub": row.get("hub"),
        "plan_code": row.get("plan_code"),
        "amount": row.get("amount"),
        "currency": row.get("currency", "KES"),
        "status": row.get("status", "pending"),
        "checkout_request_id": row.get("checkout_request_id"),
        "merchant_request_id": row.get("merchant_request_id"),
        "receipt": row.get("receipt"),
        "created_at": row.get("created_at").isoformat() if hasattr(row.get("created_at"), "isoformat") else row.get("created_at"),
        "updated_at": row.get("updated_at").isoformat() if hasattr(row.get("updated_at"), "isoformat") else row.get("updated_at"),
        "message": row.get("message"),
        "subscription": row.get("subscription"),
        "billing_enabled": checkout_is_configured(),
    }


def _apply_final_result(checkout, result):
    """Apply only a final success query; pending/indeterminate results never activate."""
    query_checkout_id = str(result.get("CheckoutRequestID") or checkout.get("checkout_request_id") or "")
    result_code = result.get("ResultCode")
    if query_checkout_id != str(checkout.get("checkout_request_id") or ""):
        logger.warning("Daraja query checkout ID mismatch")
        return False
    query_merchant_id = str(result.get("MerchantRequestID") or "").strip()
    stored_merchant_id = str(checkout.get("merchant_request_id") or "").strip()
    if query_merchant_id and stored_merchant_id and query_merchant_id != stored_merchant_id:
        logger.warning("Daraja query merchant request ID mismatch")
        return False
    if result_code is None:
        # Query API may report only that a status query was accepted. That is not
        # the transaction result; leave it pending and retry later.
        _checkout_rows().update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "status": "awaiting_verification",
                "updated_at": now_utc(),
                "message": "Daraja accepted the status query; final result is not available yet.",
            }},
        )
        return False
    if str(result_code) != "0":
        _checkout_rows().update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "status": "failed",
                "result_code": str(result_code)[:30],
                "result_description": str(result.get("ResultDesc") or result.get("ResponseDescription") or "Payment was not completed.")[:300],
                "updated_at": now_utc(),
            }},
        )
        return False

    # Amount and phone come from our own checkout request, not callback metadata.
    # The successful final Daraja query is tied to the same high-entropy checkout ID.
    event = {
        "provider": "mpesa",
        "provider_transaction_id": str(checkout["checkout_request_id"]),
        "user_id": str(checkout["user_id"]),
        "plan_code": str(checkout["plan_code"]),
        "amount": str(checkout["amount"]),
        "currency": str(checkout.get("currency") or "KES"),
        "receipt": str(checkout.get("receipt") or checkout["checkout_request_id"])[:128],
        "metadata": {
            "checkout_request_id": checkout["checkout_request_id"],
            "merchant_request_id": checkout.get("merchant_request_id"),
            "verification_source": "daraja_stkpushquery",
        },
    }
    response, status_code = activate_verified_payment(event)
    body = response.get_json(silent=True) if hasattr(response, "get_json") else {}
    if status_code not in {200, 201} or not isinstance(body, dict) or body.get("success") is not True:
        _checkout_rows().update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "status": "verified_activation_failed",
                "result_code": "0",
                "result_description": "Payment query succeeded but subscription activation was rejected; support review is required.",
                "activation_error_code": (body or {}).get("code") if isinstance(body, dict) else None,
                "updated_at": now_utc(),
            }},
        )
        logger.error("Verified M-Pesa payment could not activate a subscription | checkout_id=%s", checkout.get("checkout_request_id"))
        return False
    subscription = body.get("subscription")
    _checkout_rows().update_one(
        {"_id": checkout["_id"]},
        {"$set": {
            "status": "succeeded",
            "result_code": "0",
            "result_description": "Payment verified and subscription activated.",
            "subscription": subscription,
            "updated_at": now_utc(),
            "verified_at": now_utc(),
        }},
    )
    return True


@revenue_bp.post("/checkout")
@require_authenticated
def revenue_start_checkout():
    """Initiate an STK prompt using server-managed approved plan pricing."""
    if not checkout_is_production_configured():
        return _error(
            "Live M-Pesa checkout is not enabled. Configure production Daraja credentials and the registered public HTTPS callback URL.",
            503,
            "mpesa_live_checkout_not_configured",
        )
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("A JSON request body is required.", 400, "invalid_json_body")
    if set(payload) != {"plan_code", "phone"}:
        return _error("Provide only plan_code and phone.", 400, "invalid_checkout_request")
    plan_code = payload.get("plan_code")
    if not isinstance(plan_code, str) or not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", plan_code.strip()):
        return _error("A valid plan_code is required.", 400, "invalid_plan_code")
    plan_code = plan_code.strip().lower()
    plan = get_plan(plan_code)
    if not plan:
        return _error("Plan not found.", 404, "plan_not_found")
    if str(plan.get("status") or "").lower() != "available":
        return _error("This plan is not enabled for checkout. Choose a plan marked available.", 409, "plan_not_purchasable")
    hub = str(plan.get("hub") or "").strip().lower()
    if hub not in {"shamba", "biashara", "elimu", "community", "smart_ai", "marketplace", "faith"}:
        return _error("Only hub subscription plans can be purchased here.", 400, "subscription_plan_required")
    if str(plan.get("interval") or "").lower() not in {"month", "year"}:
        return _error("This plan does not represent a monthly or yearly subscription.", 400, "invalid_subscription_interval")
    try:
        amount = to_money(plan.get("amount"), allow_zero=False)
        phone = _phone(payload.get("phone"))
    except MoneyValidationError:
        return _error("This plan does not have a valid positive price.", 409, "invalid_plan_price")
    except ValueError as exc:
        return _error(str(exc), 400, "invalid_phone_number")
    if amount != amount.to_integral_value():
        return _error("M-Pesa STK Push requires a whole-KES plan price. Update the plan price first.", 409, "whole_kes_amount_required")
    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if not idempotency_key or len(idempotency_key) > 128 or any(ord(ch) < 33 or ord(ch) == 127 for ch in idempotency_key):
        return _error("A valid Idempotency-Key header is required.", 400, "invalid_idempotency_key")

    user_id = current_user_id()
    rows = _checkout_rows()
    existing = rows.find_one({"user_id": user_id, "idempotency_key": idempotency_key})
    retry_failed_initiation = bool(
        existing
        and existing.get("status") == "initiation_failed"
        and not existing.get("checkout_request_id")
    )
    if existing:
        if existing.get("plan_code") != plan_code or existing.get("phone") != phone:
            return _error("This Idempotency-Key was already used for a different checkout.", 409, "idempotency_conflict")
        if not retry_failed_initiation:
            return jsonify({"success": True, "replayed": True, "checkout": _public_checkout(existing)}), 200

    shortcode = _env("MPESA_SHORTCODE")
    timestamp = _timestamp()
    transaction_type = _env("MPESA_TRANSACTION_TYPE", "CustomerPayBillOnline")
    if transaction_type not in {"CustomerPayBillOnline", "CustomerBuyGoodsOnline"}:
        return _error("MPESA_TRANSACTION_TYPE must be CustomerPayBillOnline or CustomerBuyGoodsOnline.", 503, "invalid_mpesa_transaction_type")
    party_b = _env("MPESA_PARTY_B", shortcode)
    callback_url = _env("MPESA_CALLBACK_URL")
    document = {
        "user_id": user_id,
        "idempotency_key": idempotency_key,
        "plan_code": plan_code,
        "hub": hub,
        "amount": f"{amount:.2f}",
        "currency": str(plan.get("currency") or "KES").upper(),
        "phone": phone,
        "provider": "mpesa",
        "status": "initiating",
        "subscription_activated": False,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    if retry_failed_initiation:
        document = existing
        rows.update_one(
            {"_id": existing["_id"]},
            {"$set": {"status": "initiating", "message": None, "updated_at": now_utc()}},
        )
    else:
        try:
            inserted = rows.insert_one(document)
            document["_id"] = inserted.inserted_id
        except DuplicateKeyError:
            existing = rows.find_one({"user_id": user_id, "idempotency_key": idempotency_key})
            if existing:
                if existing.get("plan_code") != plan_code or existing.get("phone") != phone:
                    return _error("This Idempotency-Key was already used for a different checkout.", 409, "idempotency_conflict")
                return jsonify({"success": True, "replayed": True, "checkout": _public_checkout(existing)}), 200
            return _error("The checkout could not be safely started. Retry with a new Idempotency-Key.", 409, "checkout_conflict")

    try:
        response = _daraja_post(
            "/mpesa/stkpush/v1/processrequest",
            {
                "BusinessShortCode": shortcode,
                "Password": _password(timestamp),
                "Timestamp": timestamp,
                "TransactionType": transaction_type,
                "Amount": int(amount),
                "PartyA": phone,
                "PartyB": party_b,
                "PhoneNumber": phone,
                "CallBackURL": callback_url,
                "AccountReference": plan_code[:12],
                "TransactionDesc": f"RevelaCode {plan_code}"[:100],
            },
        )
    except RuntimeError as exc:
        rows.update_one(
            {"_id": document["_id"]},
            {"$set": {"status": "initiation_failed", "message": str(exc)[:300], "updated_at": now_utc()}},
        )
        return _error(str(exc), 503, "mpesa_initiation_failed")

    if str(response.get("ResponseCode", "")) != "0" or not response.get("CheckoutRequestID") or not response.get("MerchantRequestID"):
        rows.update_one(
            {"_id": document["_id"]},
            {"$set": {
                "status": "initiation_failed",
                "message": str(response.get("errorMessage") or response.get("ResponseDescription") or "Daraja did not return valid checkout identifiers.")[:300],
                "updated_at": now_utc(),
            }},
        )
        return _error("Daraja did not accept the STK Push request.", 502, "mpesa_request_rejected")

    checkout_id = str(response["CheckoutRequestID"])
    merchant_id = str(response["MerchantRequestID"])
    # CheckoutRequestID is the stable provider reference used for deduplication.
    try:
        rows.update_one(
            {"_id": document["_id"]},
            {"$set": {
                "checkout_request_id": checkout_id,
                "merchant_request_id": merchant_id,
                "status": "pending",
                "message": str(response.get("CustomerMessage") or "Check your phone and enter your M-Pesa PIN to approve payment.")[:300],
                "updated_at": now_utc(),
            }},
        )
    except Exception:
        current_app.logger.exception("STK request was accepted but its IDs could not be persisted")
        return _error("M-Pesa accepted the request but checkout tracking needs administrator reconciliation.", 503, "checkout_tracking_failed")

    try:
        log_action(
            user_id=user_id,
            action="revenue.mpesa.checkout_started",
            resource="revenue_mpesa_checkout",
            resource_id=checkout_id,
            metadata={"hub": hub, "plan_code": plan_code, "amount": f"{amount:.2f}", "currency": document["currency"]},
        )
    except Exception:
        current_app.logger.exception("M-Pesa checkout started but its audit event could not be written")
    saved = rows.find_one({"_id": document["_id"]})
    return jsonify({
        "success": True,
        "replayed": False,
        "message": "STK Push sent. Confirm the payment on your phone; access activates only after verification.",
        "checkout": _public_checkout(saved or document),
    }), 201


@revenue_bp.post("/providers/mpesa/callback")
def revenue_mpesa_callback():
    """Receive Daraja's asynchronous callback; callback data alone never activates access."""
    payload = request.get_json(silent=True)
    try:
        callback = payload.get("Body", {}).get("stkCallback", {}) if isinstance(payload, dict) else {}
        checkout_id = str(callback.get("CheckoutRequestID") or "").strip()
        if not checkout_id:
            return jsonify({"ResultCode": 0, "ResultDesc": "Callback acknowledged"}), 200
        rows = _checkout_rows()
        checkout = rows.find_one({"checkout_request_id": checkout_id})
        if not checkout:
            logger.warning("Received M-Pesa callback for unknown checkout request")
            return jsonify({"ResultCode": 0, "ResultDesc": "Callback acknowledged"}), 200
        if checkout.get("status") == "succeeded":
            return jsonify({"ResultCode": 0, "ResultDesc": "Callback already applied"}), 200

        try:
            result_code = int(callback.get("ResultCode"))
        except (TypeError, ValueError):
            result_code = None
        callback_meta = {}
        raw_items = (callback.get("CallbackMetadata") or {}).get("Item", [])
        if isinstance(raw_items, list):
            for item in raw_items:
                if not isinstance(item, dict) or not isinstance(item.get("Name"), str):
                    continue
                key, value = item["Name"], item.get("Value")
                if key in {"MpesaReceiptNumber", "Amount", "TransactionDate", "PhoneNumber"} and isinstance(value, (str, int, float)):
                    callback_meta[key] = value

        # A callback is an untrusted notification. Even a failure result is
        # reconciled against Daraja's query before we change a final status.
        rows.update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "callback_result_code": str(result_code) if result_code is not None else None,
                "callback_result_description": str(callback.get("ResultDesc") or "")[:300],
                "callback_metadata": callback_meta,
                # Persist the real receipt before subscription/ledger activation.
                "receipt": callback_meta.get("MpesaReceiptNumber") or checkout.get("receipt"),
                "status": "callback_received",
                "callback_received_at": now_utc(),
                "updated_at": now_utc(),
            }},
        )
        checkout = rows.find_one({"_id": checkout["_id"]})
        try:
            query_result = _query_checkout(checkout)
        except RuntimeError as exc:
            rows.update_one(
                {"_id": checkout["_id"]},
                {"$set": {
                    "status": "awaiting_verification",
                    "message": str(exc)[:300],
                    "updated_at": now_utc(),
                }},
            )
            return jsonify({"ResultCode": 0, "ResultDesc": "Callback acknowledged; verification pending"}), 200

        if str(query_result.get("CheckoutRequestID") or checkout_id) != checkout_id:
            logger.error("M-Pesa status query returned a different CheckoutRequestID")
            rows.update_one(
                {"_id": checkout["_id"]},
                {"$set": {"status": "awaiting_verification", "updated_at": now_utc()}},
            )
        else:
            success = _apply_final_result(checkout, query_result)
            if success:
                rows.update_one({"_id": checkout["_id"]}, {"$set": {"receipt": callback_meta.get("MpesaReceiptNumber")}})
        return jsonify({"ResultCode": 0, "ResultDesc": "Callback acknowledged"}), 200
    except Exception:
        logger.exception("M-Pesa callback processing failed")
        # Return 200 so the callback is not retried indefinitely; checkout stays
        # pending for the authenticated status/reconciliation endpoint.
        return jsonify({"ResultCode": 0, "ResultDesc": "Callback acknowledged for reconciliation"}), 200


@revenue_bp.get("/checkout/<checkout_id>")
@require_authenticated
def revenue_get_checkout(checkout_id):
    user_id = current_user_id()
    checkout = _checkout_rows().find_one({
        "checkout_request_id": checkout_id,
        "user_id": user_id,
    })
    if not checkout:
        return _error("Checkout not found.", 404, "checkout_not_found")
    return jsonify({"success": True, "checkout": _public_checkout(checkout)}), 200


@revenue_bp.post("/checkout/<checkout_id>/refresh")
@require_authenticated
def revenue_refresh_checkout(checkout_id):
    """Request a fresh Daraja status query; never infer payment from browser state."""
    user_id = current_user_id()
    rows = _checkout_rows()
    checkout = rows.find_one({
        "checkout_request_id": checkout_id,
        "user_id": user_id,
    })
    if not checkout:
        return _error("Checkout not found.", 404, "checkout_not_found")
    if checkout.get("status") == "succeeded":
        return jsonify({"success": True, "checkout": _public_checkout(checkout), "replayed": True}), 200
    if not checkout.get("checkout_request_id"):
        return _error("Daraja did not provide a checkout reference; support reconciliation is required.", 409, "checkout_not_submitted")
    try:
        result = _query_checkout(checkout)
    except RuntimeError as exc:
        return _error(str(exc), 503, "mpesa_query_failed")
    success = _apply_final_result(checkout, result)
    fresh = rows.find_one({"_id": checkout["_id"]})
    return jsonify({
        "success": True,
        "verified": success,
        "checkout": _public_checkout(fresh or checkout),
    }), 200
