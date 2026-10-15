"""Safaricom Daraja STK Push adapter for Biashara.

The adapter only posts a payment after a matching callback is received from an
explicitly configured Daraja callback IP allow-list, the CheckoutRequestID and
MerchantRequestID match the persisted intent, and the callback amount/receipt
pass validation. Credentials remain encrypted in the integration registry.

Requires:
- An enabled mpesa_daraja connection with correct merchant credentials.
- BIASHARA_MPESA_CALLBACK_BASE_URL set to the public API origin/path.
- BIASHARA_MPESA_CALLBACK_ALLOWED_IPS set to the current Safaricom-published
  callback source IPs for the environment/deployment.

The callback handler intentionally does not trust X-Forwarded-For or similar
headers. Reverse proxies must preserve a trusted connecting peer address or
perform the allow-list check at the edge.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
import base64

import requests
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.audit import log_action
from backend.jumuiya.biashara.tenancy.service import require_permission
from backend.jumuiya.biashara.integrations import service as integration_service
from backend.jumuiya.biashara.finance import services as finance_services
from backend.jumuiya.biashara.sync.outbox import build_outbox_manifest, dispatch_manifest_for_record


PAYMENTS_COLLECTION = "jumuiya_payments"
INVOICES_COLLECTION = "jumuiya_invoices"
CONNECTIONS_COLLECTION = integration_service.CONNECTIONS_COLLECTION
CALLBACKS_COLLECTION = "jumuiya_mpesa_callback_events"

REQUEST_TIMEOUT = (3.05, 15)
MAX_CALLBACK_BODY_BYTES = 128 * 1024
IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
PHONE_RE = re.compile(r"^254[17][0-9]{8}$")
RECEIPT_RE = re.compile(r"^[A-Za-z0-9]{5,32}$")
SHORTCODE_RE = re.compile(r"^[0-9]{5,10}$")


def now_utc():
    return datetime.now(timezone.utc)


def _clean_id(value):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return value


def _public_payment_intent(payment):
    """Allowlisted projection; never expose phone, credentials or raw provider payload."""
    return {
        "id": str(payment.get("_id") or ""),
        "invoice_id": str(payment.get("invoice_id") or ""),
        "order_id": str(payment.get("order_id") or ""),
        "payment_method": payment.get("payment_method"),
        "amount_minor": int(payment.get("amount_minor", 0) or 0),
        "currency": payment.get("currency", "KES"),
        "payment_status": payment.get("payment_status"),
        "verification_status": payment.get("verification_status"),
        "provider_verified": bool(payment.get("provider_verified", False)),
        "provider_name": payment.get("provider_name"),
        "provider_event_id": payment.get("provider_event_id"),
        "provider_request_status": payment.get("provider_request_status"),
        "checkout_request_id": payment.get("checkout_request_id"),
        "merchant_request_id": payment.get("merchant_request_id"),
        "customer_message": payment.get("customer_message"),
        "allocation_status": payment.get("allocation_status"),
        "reference": payment.get("reference"),
        "created_at": _iso(payment.get("created_at")),
        "updated_at": _iso(payment.get("updated_at")),
    }


def _iso(value):
    if not isinstance(value, datetime):
        return value
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def _minor(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise APIError("Payment amount must be a valid monetary value.", 422, "invalid_payment_amount")
    if not amount.is_finite() or amount <= 0:
        raise APIError("Payment amount must be greater than zero.", 422, "invalid_payment_amount")
    quantized = amount.quantize(Decimal("0.01"))
    if quantized != amount:
        raise APIError("Payment amount supports at most two decimal places.", 422, "invalid_payment_amount")
    return int(quantized * 100)


def _phone(value):
    raw = str(value or "").strip().replace(" ", "").replace("-", "")
    if raw.startswith("+"):
        raw = raw[1:]
    if raw.startswith("0") and len(raw) == 10:
        raw = "254" + raw[1:]
    if not PHONE_RE.fullmatch(raw):
        raise APIError("Use a Kenyan mobile number such as 2547XXXXXXXX or 07XXXXXXXX.", 422, "invalid_mpesa_phone")
    return raw


def _public_callback_base():
    raw = os.getenv("BIASHARA_MPESA_CALLBACK_BASE_URL", "").strip().rstrip("/")
    if not raw:
        raise APIError(
            "M-Pesa requests are disabled until BIASHARA_MPESA_CALLBACK_BASE_URL is configured.",
            503,
            "mpesa_callback_url_not_configured",
        )
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise APIError("The M-Pesa callback base URL must be a clean HTTPS origin/path.", 503, "mpesa_callback_url_invalid")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local")):
        raise APIError("The M-Pesa callback URL must be publicly reachable.", 503, "mpesa_callback_url_invalid")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise APIError("The M-Pesa callback URL must not use a private IP address.", 503, "mpesa_callback_url_invalid")
    except ValueError:
        if "." not in host:
            raise APIError("The M-Pesa callback host is invalid.", 503, "mpesa_callback_url_invalid")
    return raw


def _allowed_callback_ips():
    raw = os.getenv("BIASHARA_MPESA_CALLBACK_ALLOWED_IPS", "").strip()
    if not raw:
        raise APIError(
            "M-Pesa callbacks are disabled until the Safaricom source IP allow-list is configured.",
            503,
            "mpesa_callback_allowlist_not_configured",
        )
    result = set()
    try:
        for item in raw.split(","):
            item = item.strip()
            if item:
                result.add(str(ipaddress.ip_address(item)))
    except ValueError:
        raise APIError("BIASHARA_MPESA_CALLBACK_ALLOWED_IPS contains an invalid IP address.", 503, "mpesa_callback_allowlist_invalid")
    if not result:
        raise APIError("BIASHARA_MPESA_CALLBACK_ALLOWED_IPS is empty.", 503, "mpesa_callback_allowlist_not_configured")
    return result


def _assert_callback_source(remote_addr):
    allowed = _allowed_callback_ips()
    try:
        peer = str(ipaddress.ip_address(str(remote_addr or "").strip()))
    except ValueError:
        raise APIError("The callback peer address is unavailable; provider event was not accepted.", 403, "mpesa_callback_source_rejected")
    if peer not in allowed:
        raise APIError("M-Pesa callback source IP is not allow-listed.", 403, "mpesa_callback_source_rejected")
    return peer


def _connection(business_id, connection_id, enabled=True):
    query = {
        "_id": _clean_id(connection_id),
        "business_id": str(business_id),
        "provider": "mpesa_daraja",
    }
    if enabled:
        query["enabled"] = True
    document = collection(CONNECTIONS_COLLECTION).find_one(query)
    if not document:
        raise APIError("Enabled M-Pesa connection not found for this business.", 404, "mpesa_connection_not_found")
    metadata = document.get("metadata") or {}
    shortcode = str(metadata.get("shortcode") or "").strip()
    environment = str(metadata.get("environment") or "").strip().lower()
    if not SHORTCODE_RE.fullmatch(shortcode) or environment not in {"sandbox", "production"}:
        raise APIError("M-Pesa connection metadata is invalid.", 409, "mpesa_connection_invalid")
    credentials = integration_service._decrypt_credentials(document)
    required = {"consumer_key", "consumer_secret", "passkey"}
    if required - set(credentials):
        raise APIError("M-Pesa connection is missing required credentials.", 409, "mpesa_credentials_incomplete")
    return document, metadata, credentials


def _provider_root(environment):
    return "https://sandbox.safaricom.co.ke" if environment == "sandbox" else "https://api.safaricom.co.ke"


def _response_json(response, action):
    status = int(getattr(response, "status_code", 0) or 0)
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError, AttributeError):
        body = None
    if status < 200 or status >= 300:
        # A server/transport response can be ambiguous after a payment request;
        # callers decide whether the outcome is unknown or definitively rejected.
        raise APIError(
            f"Daraja {action} returned HTTP {status or 'unknown'}.",
            502,
            "mpesa_provider_http_error",
            details={"provider_http_status": status, "outcome_may_be_unknown": status >= 500},
        )
    if not isinstance(body, dict):
        raise APIError(f"Daraja {action} returned an invalid response.", 502, "mpesa_provider_response_invalid")
    return body


def _access_token(credentials, environment):
    url = _provider_root(environment) + "/oauth/v1/generate?grant_type=client_credentials"
    try:
        response = requests.get(
            url,
            auth=(credentials["consumer_key"], credentials["consumer_secret"]),
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        body = _response_json(response, "authentication")
    except APIError:
        raise
    except requests.RequestException as error:
        raise APIError(
            "Daraja authentication could not be reached. No payment request was submitted.",
            502,
            "mpesa_authentication_unavailable",
            details={"error_type": type(error).__name__},
        )
    token = body.get("access_token")
    if not isinstance(token, str) or not token.strip() or len(token) > 8192:
        raise APIError("Daraja authentication did not return an access token.", 502, "mpesa_authentication_invalid")
    return token.strip()


def _fingerprint(data):
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _payment_event(payment, event_key, event_type, payload, actor_user_id):
    return build_outbox_manifest(
        event_key=event_key,
        event_type=event_type,
        entity_type="payment",
        entity_id=payment["_id"],
        payload=payload,
        actor_user_id=actor_user_id,
        occurred_at=now_utc(),
    )


def _dispatch_payment(payment_id, business_id):
    try:
        dispatch_manifest_for_record(PAYMENTS_COLLECTION, str(business_id), payment_id)
    except Exception as error:
        # The payment state is durable and the outbox manifest remains repairable.
        return {"enqueued": 0, "pending": 1, "errors": 1, "error_type": type(error).__name__}
    return {"enqueued": 1, "pending": 0, "errors": 0}


def _issue_stk_request(connection, metadata, credentials, payment, invoice, phone):
    callback_url = _public_callback_base() + (
        "/api/jumuiya/biashara/finance/mpesa/callback/" + str(connection["_id"])
    )
    environment = metadata["environment"]
    root = _provider_root(environment)
    token = _access_token(credentials, environment)
    timestamp = now_utc().strftime("%Y%m%d%H%M%S")
    shortcode = str(metadata["shortcode"])
    password = base64.b64encode((shortcode + credentials["passkey"] + timestamp).encode("utf-8")).decode("ascii")
    invoice_number = str(invoice.get("invoice_number") or invoice.get("_id") or "")
    reference = re.sub(r"[^A-Za-z0-9]", "", invoice_number).upper()
    account_reference = ("BI" + reference)[-12:] or "BIASHARA"
    transaction_type = str(metadata.get("transaction_type") or "CustomerPayBillOnline")
    amount_shillings = int(payment["amount_minor"]) // 100
    body = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": transaction_type,
        "Amount": amount_shillings,
        "PartyA": phone,
        "PartyB": shortcode,
        "PhoneNumber": phone,
        "CallBackURL": callback_url,
        "AccountReference": account_reference,
        "TransactionDesc": "Biashara Pay",
    }
    url = root + "/mpesa/stkpush/v1/processrequest"
    try:
        response = requests.post(
            url,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/json"},
            json=body,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
        result = _response_json(response, "STK Push")
    except APIError:
        raise
    except requests.RequestException as error:
        raise APIError(
            "Daraja did not return a definitive response. The phone prompt may or may not have been sent; do not retry with a new key.",
            502,
            "mpesa_request_outcome_unknown",
            details={"error_type": type(error).__name__, "outcome_may_be_unknown": True},
        )
    code = str(result.get("ResponseCode") or "").strip()
    if code != "0":
        safe_code = str(result.get("errorCode") or code or "provider_rejected")[:80]
        raise APIError(
            "Daraja did not accept the STK Push request.",
            502,
            "mpesa_stk_push_rejected",
            details={"provider_response_code": safe_code},
        )
    checkout_id = str(result.get("CheckoutRequestID") or "").strip()
    merchant_id = str(result.get("MerchantRequestID") or "").strip()
    if not checkout_id or not merchant_id or len(checkout_id) > 200 or len(merchant_id) > 200:
        raise APIError(
            "Daraja accepted the request but omitted its correlation identifiers. The request outcome requires reconciliation.",
            502,
            "mpesa_request_outcome_unknown",
            details={"outcome_may_be_unknown": True},
        )
    message = result.get("CustomerMessage")
    if not isinstance(message, str):
        message = "Check your phone to complete the M-Pesa payment."
    return {
        "checkout_request_id": checkout_id,
        "merchant_request_id": merchant_id,
        "customer_message": message[:200],
    }


def start_stk_push(user_id, invoice_id, payload, idempotency_key):
    """Create one STK request intent; network retries never generate a second prompt."""
    context = require_permission(user_id, "finance.manage")
    business_id = str(context.get("id") or "")
    if not business_id:
        raise APIError("Selected business is unavailable.", 409, "business_id_missing")
    require_permission(user_id, "integration.view", business_id=business_id)

    if not isinstance(payload, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    raw_key = str(idempotency_key or "").strip()
    if not IDEMPOTENCY_RE.fullmatch(raw_key):
        raise APIError("Provide an Idempotency-Key of 8–128 safe characters.", 422, "invalid_idempotency_key")
    connection_id = str(payload.get("connection_id") or "").strip()
    if not connection_id:
        raise APIError("connection_id is required.", 422, "mpesa_connection_required")
    phone = _phone(payload.get("phone_number"))
    amount_minor = _minor(payload.get("amount"))
    if amount_minor < 100 or amount_minor % 100:
        raise APIError("STK Push payments must be at least KES 1.00 and use whole-shilling amounts.", 422, "invalid_mpesa_amount")

    invoice = finance_services._get_invoice(business_id, invoice_id)
    if invoice.get("status") != "issued":
        raise APIError("M-Pesa payments can only be requested for issued invoices.", 409, "invoice_not_payable")
    if str(invoice.get("currency") or "KES").upper() != "KES":
        raise APIError("Daraja STK Push currently supports KES invoices only.", 409, "mpesa_currency_unsupported")
    due_minor = int(invoice.get("total_amount_minor", 0) or 0) - int(invoice.get("amount_paid_minor", 0) or 0)
    if due_minor <= 0:
        raise APIError("This invoice has no outstanding balance.", 409, "invoice_already_paid")
    if amount_minor > due_minor:
        raise APIError("The STK amount exceeds the invoice balance due.", 409, "payment_exceeds_invoice_balance")

    connection, metadata, credentials = _connection(business_id, connection_id, enabled=True)
    # Validate all required deployment settings before creating a durable request intent.
    callback_base = _public_callback_base()
    _allowed_callback_ips()
    phone_hash = hashlib.sha256(phone.encode("utf-8")).hexdigest()
    internal_key = "mpesa-stk:" + raw_key
    fingerprint = _fingerprint({
        "business_id": business_id,
        "invoice_id": str(invoice["_id"]),
        "connection_id": str(connection["_id"]),
        "amount_minor": amount_minor,
        "phone_hash": phone_hash,
    })
    payments = collection(PAYMENTS_COLLECTION)
    prior = payments.find_one({"business_id": business_id, "idempotency_key": internal_key})
    if prior:
        if prior.get("request_fingerprint") != fingerprint:
            raise APIError("Idempotency-Key was reused for a different M-Pesa request.", 409, "idempotency_key_reused")
        if prior.get("checkout_request_id") or prior.get("payment_status") in {
            "provider_confirmed", "provider_failed", "provider_request_rejected",
        }:
            return _public_payment_intent(prior)
        raise APIError(
            "The previous M-Pesa request has no definitive outcome. Reuse the same key only after checking its status; a new prompt was not sent.",
            409,
            "mpesa_request_outcome_unknown",
        )

    # OAuth is read-only. If this fails, do not create a dangling payment intent.
    token = _access_token(credentials, metadata["environment"])
    now = now_utc()
    payment_id = ObjectId()
    document = {
        "_id": payment_id,
        "business_id": business_id,
        "invoice_id": str(invoice["_id"]),
        "order_id": str(invoice.get("source_order_id") or ""),
        "idempotency_key": internal_key,
        "request_fingerprint": fingerprint,
        "amount_minor": amount_minor,
        "currency": "KES",
        "payment_method": "mpesa",
        "reference": "",
        "payment_status": "provider_requesting",
        "verification_status": "provider_pending",
        "provider_verified": False,
        "provider_name": "mpesa_daraja",
        "provider_connection_id": str(connection["_id"]),
        "provider_event_id": None,
        "provider_request_status": "requesting",
        "checkout_request_id": None,
        "merchant_request_id": None,
        "provider_phone_hash": phone_hash,
        "provider_phone_masked": "••••" + phone[-3:],
        "provider_request_environment": metadata["environment"],
        "allocation_status": "not_allocated_pending_verification",
        "source": "mpesa_stk_push",
        "recorded_by_user_id": str(user_id),
        "created_at": now,
        "updated_at": now,
        "allocated_at": None,
        "provider_verified_at": None,
        "provider_result_code": None,
        "provider_error_code": None,
        "outbox_enqueued_event_keys": [],
    }
    event = _payment_event(
        document,
        "payment:" + internal_key + ":stk-requested",
        "payment.stk_push_requested",
        {"status": "requesting", "payment_status": "provider_requesting",
         "payment_method": "mpesa", "amount_minor": amount_minor, "currency": "KES",
         "invoice_id": str(invoice["_id"]), "connection_id": str(connection["_id"])},
        user_id,
    )
    document["outbox_event_manifest"] = [event]
    try:
        payments.insert_one(document)
    except DuplicateKeyError:
        prior = payments.find_one({"business_id": business_id, "idempotency_key": internal_key})
        if prior and prior.get("request_fingerprint") == fingerprint:
            if prior.get("checkout_request_id"):
                return _public_payment_intent(prior)
            raise APIError("The prior request has no definitive result. It was not sent again.", 409, "mpesa_request_outcome_unknown")
        raise APIError("M-Pesa idempotency key conflicts with a different request.", 409, "idempotency_key_reused")
    _dispatch_payment(payment_id, business_id)

    try:
        request_result = _issue_stk_request(connection, metadata, credentials, document, invoice, phone)
    except APIError as error:
        details = error.details or {}
        ambiguous = bool(details.get("outcome_may_be_unknown")) or error.code == "mpesa_request_outcome_unknown"
        now = now_utc()
        payments.update_one(
            {"_id": payment_id, "business_id": business_id, "payment_status": "provider_requesting"},
            {"$set": {
                "payment_status": "provider_request_unknown" if ambiguous else "provider_request_rejected",
                "provider_request_status": "outcome_unknown" if ambiguous else "rejected",
                "verification_status": "provider_request_outcome_unknown" if ambiguous else "provider_request_rejected",
                "provider_error_code": error.code,
                "provider_result_code": details.get("provider_response_code"),
                "updated_at": now,
            }},
        )
        failed = payments.find_one({"_id": payment_id, "business_id": business_id}) or document
        failed_event = _payment_event(
            failed,
            "payment:" + internal_key + ":stk-request-result",
            "payment.stk_push_request_result",
            {"status": failed.get("provider_request_status"),
             "payment_status": failed.get("payment_status"),
             "payment_method": "mpesa", "amount_minor": amount_minor, "currency": "KES"},
            user_id,
        )
        payments.update_one(
            {"_id": payment_id, "business_id": business_id},
            {"$addToSet": {"outbox_event_manifest": failed_event}},
        )
        _dispatch_payment(payment_id, business_id)
        raise

    now = now_utc()
    updated = payments.find_one_and_update(
        {"_id": payment_id, "business_id": business_id, "payment_status": "provider_requesting"},
        {"$set": {
            "payment_status": "pending_provider_confirmation",
            "provider_request_status": "accepted",
            "verification_status": "provider_pending",
            "checkout_request_id": request_result["checkout_request_id"],
            "merchant_request_id": request_result["merchant_request_id"],
            "customer_message": request_result["customer_message"],
            "updated_at": now,
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise APIError("M-Pesa request intent changed while saving the provider response.", 409, "mpesa_request_state_conflict")
    _dispatch_payment(payment_id, business_id)

    # A callback can race the outbound response write. Any already received
    # event remains pending_match and is retried now that IDs are persisted.
    pending = collection(CALLBACKS_COLLECTION).find({
        "business_id": business_id,
        "connection_id": str(connection["_id"]),
        "checkout_request_id": request_result["checkout_request_id"],
        "status": "pending_match",
    }).limit(5)
    for callback in pending:
        _apply_callback_event(callback)
    current = payments.find_one({"_id": payment_id, "business_id": business_id}) or updated
    log_action(user_id, "biashara.mpesa_stk_requested", "payment", payment_id, {
        "invoice_id": str(invoice["_id"]),
        "amount_minor": amount_minor,
        "environment": metadata["environment"],
        "request_status": current.get("provider_request_status"),
    })
    return _public_payment_intent(current)


def _callback_metadata(callback):
    body = callback.get("Body") if isinstance(callback, dict) else None
    stk = body.get("stkCallback") if isinstance(body, dict) else None
    if not isinstance(stk, dict):
        raise APIError("M-Pesa callback is missing Body.stkCallback.", 400, "mpesa_callback_invalid")
    checkout_id = str(stk.get("CheckoutRequestID") or "").strip()
    merchant_id = str(stk.get("MerchantRequestID") or "").strip()
    if not checkout_id or not merchant_id or len(checkout_id) > 200 or len(merchant_id) > 200:
        raise APIError("M-Pesa callback correlation IDs are missing or invalid.", 400, "mpesa_callback_invalid")
    try:
        result_code = int(stk.get("ResultCode"))
    except (TypeError, ValueError, OverflowError):
        raise APIError("M-Pesa callback result code is invalid.", 400, "mpesa_callback_invalid")
    result_desc = str(stk.get("ResultDesc") or "")[:200]
    items = []
    metadata = stk.get("CallbackMetadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("Item"), list):
        items = metadata["Item"][:40]
    values = {}
    for item in items:
        if isinstance(item, dict):
            name = str(item.get("Name") or "")
            if name in {"Amount", "MpesaReceiptNumber", "TransactionDate", "PhoneNumber"}:
                values[name] = item.get("Value")
    amount_minor = None
    if values.get("Amount") is not None:
        try:
            amount = Decimal(str(values["Amount"]))
            if amount.is_finite() and amount > 0 and amount.quantize(Decimal("0.01")) == amount:
                amount_minor = int(amount * 100)
        except (InvalidOperation, TypeError, ValueError):
            amount_minor = None
    receipt = str(values.get("MpesaReceiptNumber") or "").strip().upper()
    if receipt and not RECEIPT_RE.fullmatch(receipt):
        receipt = ""
    phone_value = str(values.get("PhoneNumber") or "").strip()
    phone_last3 = phone_value[-3:] if phone_value.isdigit() and len(phone_value) >= 3 else None
    transaction_date = None
    raw_transaction_date = str(values.get("TransactionDate") or "").strip()
    if re.fullmatch(r"[0-9]{14}", raw_transaction_date):
        try:
            transaction_date = datetime.strptime(raw_transaction_date, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            transaction_date = None
    return {
        "checkout_request_id": checkout_id,
        "merchant_request_id": merchant_id,
        "result_code": result_code,
        "result_description": result_desc,
        "amount_minor": amount_minor,
        "receipt_number": receipt or None,
        "phone_last3": phone_last3,
        "transaction_at": transaction_date,
    }


def receive_stk_callback(connection_id, raw_body, remote_addr):
    """Authenticate by configured peer-IP allow-list and persist a sanitized callback."""
    if not isinstance(raw_body, (bytes, bytearray)) or not raw_body or len(raw_body) > MAX_CALLBACK_BODY_BYTES:
        raise APIError("M-Pesa callback body is empty or too large.", 413, "mpesa_callback_body_invalid")
    source_ip = _assert_callback_source(remote_addr)
    connection = collection(CONNECTIONS_COLLECTION).find_one({
        "_id": _clean_id(connection_id),
        "provider": "mpesa_daraja",
    })
    if not connection:
        raise APIError("M-Pesa connection not found.", 404, "mpesa_connection_not_found")
    try:
        callback = json.loads(bytes(raw_body).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise APIError("M-Pesa callback must be valid UTF-8 JSON.", 400, "mpesa_callback_invalid")
    parsed = _callback_metadata(callback)
    business_id = str(connection.get("business_id") or "")
    if not business_id:
        raise APIError("M-Pesa connection has no business owner.", 409, "mpesa_connection_invalid")
    fingerprint_data = {
        "checkout_request_id": parsed["checkout_request_id"],
        "merchant_request_id": parsed["merchant_request_id"],
        "result_code": parsed["result_code"],
        "amount_minor": parsed["amount_minor"],
        "receipt_number": parsed["receipt_number"],
        "phone_last3": parsed["phone_last3"],
        "transaction_at": _iso(parsed["transaction_at"]),
    }
    fingerprint = _fingerprint(fingerprint_data)
    callbacks = collection(CALLBACKS_COLLECTION)
    query = {
        "business_id": business_id,
        "connection_id": str(connection["_id"]),
        "checkout_request_id": parsed["checkout_request_id"],
    }
    existing = callbacks.find_one(query)
    if existing:
        if existing.get("request_fingerprint") != fingerprint:
            callbacks.update_one(
                {"_id": existing["_id"], "business_id": business_id},
                {"$set": {"status": "conflict", "conflict_reason": "callback_content_changed", "updated_at": now_utc()}},
            )
            raise APIError("A different callback was already stored for this checkout request. It was not applied.", 409, "mpesa_callback_conflict")
        event = existing
    else:
        event = {
            "_id": ObjectId(),
            **query,
            "merchant_request_id": parsed["merchant_request_id"],
            "result_code": parsed["result_code"],
            "result_description": parsed["result_description"],
            "amount_minor": parsed["amount_minor"],
            "receipt_number": parsed["receipt_number"],
            "phone_last3": parsed["phone_last3"],
            "transaction_at": parsed["transaction_at"],
            "source_ip": source_ip,
            "payload_sha256": hashlib.sha256(bytes(raw_body)).hexdigest(),
            "request_fingerprint": fingerprint,
            "status": "pending_match",
            "effects_applied": False,
            "received_at": now_utc(),
            "updated_at": now_utc(),
        }
        try:
            callbacks.insert_one(event)
        except DuplicateKeyError:
            event = callbacks.find_one(query)
            if not event or event.get("request_fingerprint") != fingerprint:
                raise APIError("M-Pesa callback conflicts with an existing event.", 409, "mpesa_callback_conflict")
    applied = _apply_callback_event(event)
    return {
        "ResultCode": 0,
        "ResultDesc": "Accepted",
        "event_status": applied.get("status", "pending_match"),
        "duplicate": bool(existing),
        "effects_applied": applied.get("effects_applied", False),
    }


def _apply_callback_event(event):
    """Apply only a matched, allow-listed callback with exact amount and unique receipt."""
    business_id = str(event.get("business_id") or "")
    connection_id = str(event.get("connection_id") or "")
    checkout_id = str(event.get("checkout_request_id") or "")
    payment = collection(PAYMENTS_COLLECTION).find_one({
        "business_id": business_id,
        "provider_name": "mpesa_daraja",
        "provider_connection_id": connection_id,
        "checkout_request_id": checkout_id,
    })
    callbacks = collection(CALLBACKS_COLLECTION)
    if not payment:
        callbacks.update_one(
            {"_id": event["_id"], "business_id": business_id, "status": "pending_match"},
            {"$set": {"status": "pending_match", "updated_at": now_utc()}},
        )
        return {**event, "status": "pending_match", "effects_applied": False}

    if str(payment.get("merchant_request_id") or "") != str(event.get("merchant_request_id") or ""):
        callbacks.update_one(
            {"_id": event["_id"], "business_id": business_id},
            {"$set": {"status": "conflict", "conflict_reason": "merchant_request_id_mismatch", "updated_at": now_utc()}},
        )
        return {**event, "status": "conflict", "effects_applied": False}

    if payment.get("payment_status") == "provider_confirmed" and payment.get("provider_event_id") == event.get("receipt_number"):
        callbacks.update_one(
            {"_id": event["_id"], "business_id": business_id},
            {"$set": {"status": "applied", "effects_applied": True, "updated_at": now_utc()}},
        )
        return {**event, "status": "applied", "effects_applied": True}

    if payment.get("payment_status") not in {"provider_requesting", "pending_provider_confirmation", "provider_request_unknown"}:
        callbacks.update_one(
            {"_id": event["_id"], "business_id": business_id},
            {"$set": {"status": "conflict", "conflict_reason": "payment_not_awaiting_confirmation", "updated_at": now_utc()}},
        )
        return {**event, "status": "conflict", "effects_applied": False}

    if int(event.get("result_code", -1)) != 0:
        now = now_utc()
        updated = collection(PAYMENTS_COLLECTION).find_one_and_update(
            {
                "_id": payment["_id"],
                "business_id": business_id,
                "payment_status": {"$in": ["provider_requesting", "pending_provider_confirmation", "provider_request_unknown"]},
                "checkout_request_id": checkout_id,
            },
            {"$set": {
                "payment_status": "provider_failed",
                "verification_status": "provider_callback_failed",
                "provider_verified": False,
                "provider_request_status": "completed_with_failure",
                "provider_result_code": int(event["result_code"]),
                "provider_error_code": "mpesa_stk_callback_failed",
                "updated_at": now,
            }},
            return_document=ReturnDocument.AFTER,
        ) or payment
        callbacks.update_one(
            {"_id": event["_id"], "business_id": business_id},
            {"$set": {"status": "processed_failure", "effects_applied": False, "updated_at": now}},
        )
        _dispatch_payment(updated["_id"], business_id)
        return {"status": "processed_failure", "effects_applied": False}

    receipt = str(event.get("receipt_number") or "")
    amount_minor = event.get("amount_minor")
    if not RECEIPT_RE.fullmatch(receipt) or not isinstance(amount_minor, int) or amount_minor != int(payment.get("amount_minor", 0)):
        callbacks.update_one(
            {"_id": event["_id"], "business_id": business_id},
            {"$set": {"status": "conflict", "conflict_reason": "receipt_or_amount_mismatch", "updated_at": now_utc()}},
        )
        return {**event, "status": "conflict", "effects_applied": False}

    duplicate_receipt = collection(PAYMENTS_COLLECTION).find_one({
        "business_id": business_id,
        "provider_name": "mpesa_daraja",
        "provider_event_id": receipt,
        "_id": {"$ne": payment["_id"]},
    })
    if duplicate_receipt:
        callbacks.update_one(
            {"_id": event["_id"], "business_id": business_id},
            {"$set": {"status": "conflict", "conflict_reason": "receipt_already_used", "updated_at": now_utc()}},
        )
        return {**event, "status": "conflict", "effects_applied": False}

    now = now_utc()
    updated = collection(PAYMENTS_COLLECTION).find_one_and_update(
        {
            "_id": payment["_id"],
            "business_id": business_id,
            "payment_status": {"$in": ["provider_requesting", "pending_provider_confirmation", "provider_request_unknown"]},
            "checkout_request_id": checkout_id,
            "provider_event_id": {"$in": [None, ""]},
        },
        {"$set": {
            "payment_status": "provider_confirmed",
            "verification_status": "provider_verified",
            "provider_verified": True,
            "provider_event_id": receipt,
            "reference": receipt,
            "provider_request_status": "confirmed",
            "provider_result_code": 0,
            "provider_verified_at": now,
            "provider_transaction_at": event.get("transaction_at"),
            "provider_phone_last3": event.get("phone_last3"),
            "updated_at": now,
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        latest = collection(PAYMENTS_COLLECTION).find_one({"_id": payment["_id"], "business_id": business_id})
        if latest and latest.get("payment_status") == "provider_confirmed" and latest.get("provider_event_id") == receipt:
            callbacks.update_one(
                {"_id": event["_id"], "business_id": business_id},
                {"$set": {"status": "applied", "effects_applied": True, "updated_at": now_utc()}},
            )
            return {"status": "applied", "effects_applied": True}
        callbacks.update_one(
            {"_id": event["_id"], "business_id": business_id},
            {"$set": {"status": "conflict", "conflict_reason": "payment_state_changed", "updated_at": now_utc()}},
        )
        return {"status": "conflict", "effects_applied": False}

    invoice = finance_services._get_invoice(business_id, str(updated["invoice_id"]))
    allocated = finance_services._mark_payment_allocation(updated, invoice)
    if allocated.get("allocation_status") == "allocated":
        finance_services._post_provider_payment_journal(allocated, allocated.get("recorded_by_user_id") or "")
    _dispatch_payment(updated["_id"], business_id)
    log_action(
        updated.get("recorded_by_user_id") or "mpesa_callback",
        "biashara.mpesa_payment_verified",
        "payment",
        updated["_id"],
        {"business_id": business_id, "amount_minor": amount_minor, "receipt_suffix": receipt[-4:]},
    )
    status = "applied" if allocated.get("allocation_status") == "allocated" else "allocation_conflict"
    callbacks.update_one(
        {"_id": event["_id"], "business_id": business_id},
        {"$set": {"status": status, "effects_applied": True, "updated_at": now_utc(),
                  "payment_id": str(updated["_id"]), "allocation_status": allocated.get("allocation_status")}},
    )
    return {"status": status, "effects_applied": True, "allocation_status": allocated.get("allocation_status")}


def list_mpesa_intents(user_id, limit=50, status=None):
    context = require_permission(user_id, "finance.view")
    business_id = str(context.get("id") or "")
    try:
        limit = min(max(int(limit), 1), 100)
    except (TypeError, ValueError):
        limit = 50
    query = {"business_id": business_id, "source": "mpesa_stk_push"}
    if status:
        allowed = {
            "provider_requesting", "provider_request_unknown", "provider_request_rejected",
            "pending_provider_confirmation", "provider_confirmed", "provider_failed",
        }
        clean = str(status).strip().lower()
        if clean not in allowed:
            raise APIError("Unknown M-Pesa payment state.", 422, "invalid_mpesa_payment_status")
        query["payment_status"] = clean
    docs = collection(PAYMENTS_COLLECTION).find(query).sort("created_at", -1).limit(limit)
    return [_public_payment_intent(row) for row in docs]


def process_pending_callbacks(user_id, limit=100):
    """Owner-triggered recovery for callbacks that arrived before their request IDs were saved."""
    context = require_permission(user_id, "finance.manage")
    business_id = str(context.get("id") or "")
    try:
        limit = min(max(int(limit), 1), 100)
    except (TypeError, ValueError):
        limit = 100
    callbacks = collection(CALLBACKS_COLLECTION)
    events = list(callbacks.find({"business_id": business_id, "status": "pending_match"}).sort("received_at", 1).limit(limit))
    report = {"inspected": len(events), "matched": 0, "still_pending": 0, "conflicts": 0}
    for event in events:
        result = _apply_callback_event(event)
        state = str(result.get("status") or event.get("status"))
        report["matched" if state in {"applied", "allocation_conflict", "processed_failure"} else "conflicts" if state == "conflict" else "still_pending"] += 1
    return report
