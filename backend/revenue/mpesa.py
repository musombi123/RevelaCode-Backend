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
from urllib.parse import urlsplit

import requests
from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app, jsonify, request
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.audit import log_action, now_utc
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.permissions import current_user_id, require_authenticated, require_roles
from backend.revenue import revenue_bp
from backend.revenue.money import MoneyValidationError, to_money
from backend.revenue.plans import get_plan
from backend.revenue.subscriptions import ADMIN_ROLES, activate_verified_payment

logger = logging.getLogger("jumuiya.revenue.mpesa")
CHECKOUTS_COLLECTION = "jumuiya_revenue_mpesa_checkouts"
TOKEN_LOCK = threading.Lock()
CHECKOUT_INDEX_LOCK = threading.Lock()
_CHECKOUT_INDEXES_READY = False
_TOKEN = None
_TOKEN_EXPIRES = 0.0
HTTP_TIMEOUT = 12.0


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _environment() -> str:
    value = _env("MPESA_ENV", "sandbox").lower()
    return value if value in {"sandbox", "production"} else ""


def _expected_base_url() -> str:
    environment = _environment()
    if environment == "sandbox":
        return "https://sandbox.safaricom.co.ke"
    if environment == "production":
        return "https://api.safaricom.co.ke"
    return ""


def _base_url() -> str:
    """Return a validated Daraja host; never allow env config to switch environments."""
    expected = _expected_base_url()
    configured = _env("MPESA_STK_URL")
    if not expected or not configured:
        return ""
    try:
        parsed = urlsplit(configured)
        expected_host = urlsplit(expected).hostname
        if (
            parsed.scheme != "https"
            or parsed.hostname != expected_host
            or parsed.port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            return ""
    except ValueError:
        return ""
    return expected


_STK_PATHS = {
    "MPESA_STK_PATH": "/mpesa/stkpush/v1/processrequest",
    "MPESA_STK_QUERY_PATH": "/mpesa/stkpushquery/v1/query",
}


def _endpoint_path(name: str) -> str:
    """Resolve a configured Daraja path, requiring the documented endpoint."""
    expected = _STK_PATHS.get(name)
    configured = _env(name)
    if not expected or not configured:
        return ""
    return configured if configured == expected else ""


def _daraja_path_for(path: str) -> str:
    for variable, expected in _STK_PATHS.items():
        if path == expected:
            resolved = _endpoint_path(variable)
            if not resolved:
                raise RuntimeError(f"{variable} is missing or invalid.")
            return resolved
    raise RuntimeError("Unsupported Daraja endpoint path.")


def checkout_is_configured() -> bool:
    """Return Daraja configuration readiness without exposing credentials."""
    callback = _env("MPESA_CALLBACK_URL")
    try:
        from urllib.parse import urlsplit
        parsed = urlsplit(callback)
        callback_ok = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.path.rstrip("/") == "/api/revenue/providers/mpesa/callback"
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        callback_ok = False
    return bool(
        _base_url()
        and _endpoint_path("MPESA_STK_PATH")
        and _endpoint_path("MPESA_STK_QUERY_PATH")
        and _env("MPESA_CONSUMER_KEY")
        and _env("MPESA_CONSUMER_SECRET")
        and _env("MPESA_SHORTCODE").isdigit()
        and _env("MPESA_PASSKEY")
        and callback_ok
    )


def checkout_configuration_status() -> dict:
    """Return redacted, administrator-only diagnostics for each live checkout gate.

    Never return credential values, passkeys, access tokens, or a callback URL
    containing unexpected user information. This only validates configuration
    shape; it does not test Daraja credentials against Safaricom or prove that
    the public callback is reachable.
    """
    from urllib.parse import urlsplit

    environment = _environment()
    providers = {
        item.strip().lower()
        for item in _env("REVENUE_PAYMENT_PROVIDERS", "").split(",")
        if item.strip()
    }
    callback = _env("MPESA_CALLBACK_URL")
    parsed = None
    try:
        parsed = urlsplit(callback)
    except ValueError:
        parsed = None

    configured_stk_url = _env("MPESA_STK_URL")
    expected_stk_url = _expected_base_url()
    checks = {
        "production_environment": environment == "production",
        "stk_url_present": bool(configured_stk_url),
        "stk_url_matches_environment": bool(_base_url() and expected_stk_url),
        "stk_path_valid": bool(_endpoint_path("MPESA_STK_PATH")),
        "stk_query_path_valid": bool(_endpoint_path("MPESA_STK_QUERY_PATH")),
        "mpesa_provider_enabled": "mpesa" in providers,
        "consumer_key_present": bool(_env("MPESA_CONSUMER_KEY")),
        "consumer_secret_present": bool(_env("MPESA_CONSUMER_SECRET")),
        "shortcode_numeric": bool(_env("MPESA_SHORTCODE")) and _env("MPESA_SHORTCODE").isdigit(),
        "passkey_present": bool(_env("MPESA_PASSKEY")),
        "callback_https": bool(parsed and parsed.scheme == "https"),
        "callback_host_present": bool(parsed and parsed.hostname),
        "callback_path_matches": bool(
            parsed
            and parsed.path.rstrip("/") == "/api/revenue/providers/mpesa/callback"
        ),
        "callback_has_no_credentials": bool(
            parsed and parsed.username is None and parsed.password is None
        ),
        "callback_has_no_query_or_fragment": bool(
            parsed and not parsed.query and not parsed.fragment
        ),
    }

    labels = {
        "production_environment": "Set MPESA_ENV=production for live charges.",
        "stk_url_present": "MPESA_STK_URL is missing; set it to https://api.safaricom.co.ke for production or https://sandbox.safaricom.co.ke for sandbox.",
        "stk_url_matches_environment": "MPESA_STK_URL must use the official Safaricom host matching MPESA_ENV, with no path, query, or fragment.",
        "stk_path_valid": "MPESA_STK_PATH must be /mpesa/stkpush/v1/processrequest.",
        "stk_query_path_valid": "MPESA_STK_QUERY_PATH must be /mpesa/stkpushquery/v1/query.",
        "mpesa_provider_enabled": "REVENUE_PAYMENT_PROVIDERS must include mpesa.",
        "consumer_key_present": "MPESA_CONSUMER_KEY is missing from the backend environment.",
        "consumer_secret_present": "MPESA_CONSUMER_SECRET is missing from the backend environment.",
        "shortcode_numeric": "MPESA_SHORTCODE must be the numeric shortcode registered for the live Daraja account.",
        "passkey_present": "MPESA_PASSKEY is missing from the backend environment.",
        "callback_https": "MPESA_CALLBACK_URL must use HTTPS.",
        "callback_host_present": "MPESA_CALLBACK_URL must contain a valid public hostname.",
        "callback_path_matches": "MPESA_CALLBACK_URL must end with /api/revenue/providers/mpesa/callback.",
        "callback_has_no_credentials": "MPESA_CALLBACK_URL must not embed a username or password.",
        "callback_has_no_query_or_fragment": "MPESA_CALLBACK_URL must not contain a query string or fragment.",
    }
    blockers = [labels[key] for key, passed in checks.items() if not passed]
    return {
        "environment": environment or "invalid",
        "expected_callback_url": "https://revelacode-backend.onrender.com/api/revenue/providers/mpesa/callback",
        "checks": checks,
        "blockers": blockers,
        "checkout_enabled": checkout_is_production_configured(),
        "configuration_shape_valid": checkout_is_configured(),
        "provider_allowlist": sorted(providers),
        "note": "Configuration shape only; credentials are not tested against Daraja and callback reachability is not verified.",
    }


def checkout_is_production_configured() -> bool:
    """Only live Daraja configuration explicitly enabled by policy can charge."""
    providers = {
        item.strip().lower()
        for item in _env("REVENUE_PAYMENT_PROVIDERS", "").split(",")
        if item.strip()
    }
    return (
        _environment() == "production"
        and checkout_is_configured()
        and "mpesa" in providers
    )


def _checkout_rows():
    global _CHECKOUT_INDEXES_READY
    rows = collection(CHECKOUTS_COLLECTION)
    if not _CHECKOUT_INDEXES_READY:
        with CHECKOUT_INDEX_LOCK:
            if not _CHECKOUT_INDEXES_READY:
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
                # Atomic one-unresolved-checkout-per-user/hub fence. Only
                # unresolved checkouts retain this unique sparse key.
                rows.create_index(
                    [("active_checkout_slot", ASCENDING)],
                    unique=True,
                    sparse=True,
                    name="uq_mpesa_active_checkout_slot",
                )
                rows.create_index(
                    [("merchant_request_id", ASCENDING)],
                    sparse=True,
                    name="ix_mpesa_merchant_request",
                )
                rows.create_index(
                    [("created_at", DESCENDING)],
                    name="ix_mpesa_checkout_created",
                )
                _CHECKOUT_INDEXES_READY = True
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
    """Build the Daraja STK password from configured credentials and timestamp."""
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
    resolved_path = _daraja_path_for(path)
    token = _access_token()
    try:
        response = requests.post(
            _base_url() + resolved_path,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=HTTP_TIMEOUT,
            allow_redirects=False,
            proxies={"http": "", "https": ""},
        )
    except requests.RequestException:
        raise RuntimeError("Daraja payment service is unavailable.") from None
    if 300 <= response.status_code < 400:
        logger.warning("Daraja request redirected | path=%s status=%s", resolved_path, response.status_code)
        raise RuntimeError("Daraja returned an unexpected redirect.")
    if response.status_code != 200:
        provider_code = ""
        provider_message = ""
        try:
            error_body = response.json()
            if isinstance(error_body, dict):
                provider_code = str(
                    error_body.get("errorCode")
                    or error_body.get("ResponseCode")
                    or error_body.get("requestId")
                    or ""
                )[:80]
                provider_message = str(
                    error_body.get("errorMessage")
                    or error_body.get("ResponseDescription")
                    or error_body.get("ResultDesc")
                    or ""
                )[:240]
        except (ValueError, TypeError):
            pass
        # Log only whitelisted, length-limited provider diagnostic fields; never
        # log request payloads, tokens, passkeys, phone numbers, or full bodies.
        logger.warning(
            "Daraja request returned HTTP error | path=%s status=%s provider_code=%s provider_message=%s",
            resolved_path, response.status_code, provider_code, provider_message,
        )
        # A normal 4xx response (except timeout) is an explicit provider-side
        # rejection, not an ambiguous network failure. Return a safe rejection
        # result so the checkout handler can mark initiation_failed and release
        # its slot instead of incorrectly locking the user in submission_unknown.
        if (
            resolved_path == _STK_PATHS["MPESA_STK_PATH"]
            and 400 <= response.status_code < 500
            and response.status_code != 408
        ):
            description = (
                f"Daraja rejected the STK Push request (HTTP {response.status_code}). "
                "Check the live shortcode, transaction type and Daraja request configuration."
            )
            return {
                "ResponseCode": "HTTP_REJECTED",
                "ResponseDescription": description,
            }
        # Timeouts and server-side failures can occur after the provider has
        # accepted a request. Keep them ambiguous; never permit an unsafe retry.
        raise RuntimeError("Daraja did not confirm the payment request.")
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
        "user_id": str(row.get("user_id", "")),
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
        "billing_enabled": checkout_is_production_configured(),
    }


def _apply_final_result(checkout, result):
    """Apply only a final success query; pending/indeterminate results never activate."""
    query_checkout_id = str(result.get("CheckoutRequestID") or "").strip()
    result_code = result.get("ResultCode")
    if query_checkout_id != str(checkout.get("checkout_request_id") or ""):
        logger.warning("Daraja query checkout ID mismatch")
        return False
    query_merchant_id = str(result.get("MerchantRequestID") or "").strip()
    stored_merchant_id = str(checkout.get("merchant_request_id") or "").strip()
    if not stored_merchant_id or not query_merchant_id or query_merchant_id != stored_merchant_id:
        logger.warning("Daraja query merchant request ID missing or mismatched")
        return False
    if str(result_code) == "0" and _environment() != "production":
        # Never let a historical sandbox transaction create a paid entitlement or
        # revenue record, even if its provider query reports a success.
        _checkout_rows().update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "status": "sandbox_verified",
                "result_code": "0",
                "result_description": "Sandbox result received for test only. No subscription or revenue was created.",
                "updated_at": now_utc(),
            }, "$unset": {"active_checkout_slot": ""}},
        )
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
            }, "$unset": {"active_checkout_slot": ""}},
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
        "receipt": (str(checkout.get("receipt") or "").strip()[:128] or None),
        "metadata": {
            "checkout_request_id": checkout["checkout_request_id"],
            "merchant_request_id": checkout.get("merchant_request_id"),
            "verification_source": "daraja_stkpushquery",
        },
    }
    response, status_code = activate_verified_payment(
        event,
        plan_override=checkout.get("plan_snapshot"),
    )
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
        }, "$unset": {"active_checkout_slot": ""}},
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
    if hub == "community":
        return _error(
            "Community is permanently free and cannot be purchased as a subscription.",
            409,
            "community_permanently_free",
        )
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

    # Replays of the same idempotency key were returned above. A new key
    # must not create another charge while a subscription is already active
    # or the user's previous checkout has not reached a terminal result.
    from backend.revenue.subscriptions import _active_subscription
    if _active_subscription(user_id, hub):
        return _error(
            "This hub already has an active paid subscription. No new payment was started.",
            409,
            "active_subscription_exists",
        )
    unresolved = rows.find_one(
        {
            "user_id": user_id,
            "hub": hub,
            "status": {
                "$in": [
                    "initiating",
                    "pending",
                    "callback_received",
                    "awaiting_verification",
                    "verified_activation_failed",
                    "submission_unknown",
                ]
            },
        },
        sort=[("created_at", DESCENDING)],
    )
    if unresolved:
        return jsonify({
            "success": False,
            "code": "checkout_already_pending",
            "message": "A payment for this hub is still unresolved. Refresh its status before attempting another payment.",
            "checkout": _public_checkout(unresolved),
        }), 409

    try:
        _access_token()
    except RuntimeError as exc:
        return _error(
            "Daraja authentication is not ready. No checkout was submitted; check the provider configuration.",
            503,
            "mpesa_auth_unavailable",
        )

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
        "plan_snapshot": {
            "code": plan_code,
            "name": str(plan.get("name") or ""),
            "hub": hub,
            "amount": f"{amount:.2f}",
            "currency": str(plan.get("currency") or "KES").upper(),
            "interval": str(plan.get("interval") or "").lower(),
            "status": "available",
        },
        "phone": phone,
        "provider": "mpesa",
        "status": "initiating",
        "subscription_activated": False,
        "active_checkout_slot": f"{user_id}:{hub}",
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    if retry_failed_initiation:
        document = existing
        try:
            claimed = rows.update_one(
                {
                    "_id": existing["_id"],
                    "status": "initiation_failed",
                    "checkout_request_id": {"$exists": False},
                },
                {"$set": {
                    "status": "initiating",
                    "message": None,
                    "updated_at": now_utc(),
                    "active_checkout_slot": f"{user_id}:{hub}",
                }},
            )
        except DuplicateKeyError:
            claimed = None
        if not claimed or claimed.modified_count != 1:
            current = rows.find_one({"_id": existing["_id"]}) or existing
            if current.get("status") == "initiating" or current.get("active_checkout_slot"):
                return jsonify({"success": True, "replayed": True, "checkout": _public_checkout(current)}), 200
            return _error("The previous checkout state changed. Refresh before retrying.", 409, "checkout_state_conflict")
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
            blocking = rows.find_one({
                "user_id": user_id,
                "hub": hub,
                "active_checkout_slot": f"{user_id}:{hub}",
            })
            if blocking:
                return jsonify({
                    "success": False,
                    "code": "checkout_already_pending",
                    "message": "A payment for this hub is already being submitted or remains unresolved. Refresh its status before retrying.",
                    "checkout": _public_checkout(blocking),
                }), 409
            return _error("The checkout could not be safely started. Refresh and retry only after checking payment status.", 409, "checkout_conflict")

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
                "TransactionDesc": "RevelaCode"[:13],
            },
        )
    except RuntimeError as exc:
        # The STK request may have reached Daraja even if the HTTP response was
        # lost. Keep the user/hub slot reserved until a human reconciles it;
        # another idempotency key must never risk a second charge.
        rows.update_one(
            {"_id": document["_id"]},
            {"$set": {
                "status": "submission_unknown",
                "message": "The STK submission result could not be confirmed. Do not retry payment until finance has reconciled this checkout.",
                "submission_error": str(exc)[:200],
                "updated_at": now_utc(),
            }},
        )
        saved = rows.find_one({"_id": document["_id"]}) or document
        return jsonify({
            "success": False,
            "code": "mpesa_submission_unknown",
            "message": "M-Pesa submission could not be confirmed. Do not attempt another payment; this checkout requires reconciliation.",
            "checkout": _public_checkout(saved),
        }), 503

    if str(response.get("ResponseCode", "")) != "0":
        rows.update_one(
            {"_id": document["_id"]},
            {"$set": {
                "status": "initiation_failed",
                "message": str(response.get("errorMessage") or response.get("ResponseDescription") or "Daraja rejected the STK Push request.")[:300],
                "updated_at": now_utc(),
            }, "$unset": {"active_checkout_slot": ""}},
        )
        rejected = rows.find_one({"_id": document["_id"]}) or document
        return jsonify({
            "success": False,
            "code": "mpesa_request_rejected",
            "message": str(rejected.get("message") or "Daraja rejected the STK Push request. No checkout was accepted."),
            "checkout": _public_checkout(rejected),
        }), 502

    if not response.get("CheckoutRequestID") or not response.get("MerchantRequestID"):
        # ResponseCode 0 means Daraja accepted the request. Missing correlation
        # IDs make the outcome impossible to track safely, so retain the slot
        # and require finance to reconcile the provider record before another try.
        rows.update_one(
            {"_id": document["_id"]},
            {"$set": {
                "status": "submission_unknown",
                "message": "Daraja accepted the STK request but did not return both checkout identifiers. Do not retry until finance reconciles the provider record.",
                "submission_error": "accepted_response_missing_checkout_identifiers",
                "updated_at": now_utc(),
            }},
        )
        saved = rows.find_one({"_id": document["_id"]}) or document
        return jsonify({
            "success": False,
            "code": "mpesa_checkout_reference_missing",
            "message": "Daraja accepted the request but its checkout identifiers are missing. Do not pay again; finance reconciliation is required.",
            "checkout": _public_checkout(saved),
        }), 503

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


def _validated_callback_receipt(checkout, callback_meta):
    """Validate callback receipt fields against the exact server-side checkout."""
    callback_amount = to_money(callback_meta.get("Amount"), allow_zero=False)
    expected_amount = to_money(checkout.get("amount"), allow_zero=False)
    callback_phone = _phone(str(callback_meta.get("PhoneNumber") or ""))
    expected_phone = _phone(str(checkout.get("phone") or ""))
    receipt = str(callback_meta.get("MpesaReceiptNumber") or "").strip().upper()
    if callback_amount != expected_amount:
        raise ValueError("Callback amount does not match the checkout amount.")
    if callback_phone != expected_phone:
        raise ValueError("Callback payer does not match the checkout phone number.")
    if not re.fullmatch(r"[A-Z0-9]{6,20}", receipt):
        raise ValueError("Callback receipt number is missing or malformed.")
    return receipt




def _sandbox_config():
    """Read only dedicated sandbox credentials; never fall back to live secrets."""
    from urllib.parse import urlsplit

    callback = _env("MPESA_SANDBOX_CALLBACK_URL")
    try:
        parsed = urlsplit(callback)
        callback_ok = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.path.rstrip("/") == "/api/revenue/providers/mpesa/callback"
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        callback_ok = False

    return {
        "enabled": _env("MPESA_SANDBOX_ENABLED").lower() == "true",
        "consumer_key": _env("MPESA_SANDBOX_CONSUMER_KEY"),
        "consumer_secret": _env("MPESA_SANDBOX_CONSUMER_SECRET"),
        "passkey": _env("MPESA_SANDBOX_PASSKEY"),
        "shortcode": _env("MPESA_SANDBOX_SHORTCODE"),
        "callback_url": callback,
        "callback_ok": callback_ok,
    }


def _sandbox_stk_token(config):
    """Obtain a token from the hard-coded sandbox host using sandbox-only secrets."""
    try:
        response = requests.get(
            "https://sandbox.safaricom.co.ke/oauth/v1/generate",
            params={"grant_type": "client_credentials"},
            auth=(config["consumer_key"], config["consumer_secret"]),
            headers={"Accept": "application/json"},
            timeout=HTTP_TIMEOUT,
            allow_redirects=False,
            proxies={"http": "", "https": ""},
        )
    except requests.RequestException:
        raise RuntimeError("Daraja Sandbox authentication service is unavailable.") from None
    if response.status_code != 200:
        raise RuntimeError("Daraja Sandbox authentication request was rejected.")
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError("Daraja Sandbox returned an invalid authentication response.") from None
    token = str(data.get("access_token") or "").strip() if isinstance(data, dict) else ""
    if not token:
        raise RuntimeError("Daraja Sandbox did not return an access token.")
    return token


@revenue_bp.post("/admin/sandbox-stk-push")
@require_authenticated
@require_roles(*ADMIN_ROLES)
def revenue_admin_sandbox_stk_push():
    """Send a fixed KES 1 STK request to Sandbox only; never creates billing records."""
    config = _sandbox_config()
    if not (
        config["enabled"]
        and config["consumer_key"]
        and config["consumer_secret"]
        and config["passkey"]
        and config["shortcode"] == "174379"
        and config["callback_ok"]
    ):
        return _error(
            "Sandbox STK testing is disabled or incompletely configured. Set the dedicated MPESA_SANDBOX_* variables; live checkout settings are not used.",
            503,
            "mpesa_sandbox_test_not_configured",
        )

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {"phone"}:
        return _error("Provide only the Sandbox test phone number as phone.", 400, "invalid_sandbox_request")
    try:
        phone = _phone(payload.get("phone"))
    except ValueError as exc:
        return _error(str(exc), 400, "invalid_phone_number")

    timestamp = _timestamp()
    password = base64.b64encode(
        f'{config["shortcode"]}{config["passkey"]}{timestamp}'.encode("utf-8")
    ).decode("ascii")
    try:
        token = _sandbox_stk_token(config)
        response = requests.post(
            "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
            json={
                "BusinessShortCode": config["shortcode"],
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": 1,
                "PartyA": phone,
                "PartyB": config["shortcode"],
                "PhoneNumber": phone,
                "CallBackURL": config["callback_url"],
                "AccountReference": "RC-SANDBOX",
                "TransactionDesc": "Sandbox test",
            },
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=HTTP_TIMEOUT,
            allow_redirects=False,
            proxies={"http": "", "https": ""},
        )
    except requests.RequestException:
        return _error(
            "Daraja Sandbox did not return a confirmed response. Check Sandbox logs before retrying.",
            503,
            "mpesa_sandbox_submission_unknown",
        )
    if response.status_code != 200:
        # A Sandbox test never touches live checkout state. Do not echo provider
        # bodies, credentials, access tokens, or request payloads to the client.
        return _error(
            f"Daraja Sandbox rejected the test request (HTTP {response.status_code}). Check Sandbox product access and test inputs.",
            502,
            "mpesa_sandbox_request_rejected",
        )
    try:
        result = response.json()
    except ValueError:
        return _error("Daraja Sandbox returned an invalid response.", 502, "mpesa_sandbox_invalid_response")
    if not isinstance(result, dict):
        return _error("Daraja Sandbox returned an invalid response.", 502, "mpesa_sandbox_invalid_response")
    response_code = str(result.get("ResponseCode") or "")
    if response_code != "0":
        return jsonify({
            "success": False,
            "code": "mpesa_sandbox_request_rejected",
            "message": str(result.get("ResponseDescription") or result.get("errorMessage") or "Daraja Sandbox rejected the test request.")[:300],
        }), 502

    checkout_id = str(result.get("CheckoutRequestID") or "").strip()
    merchant_id = str(result.get("MerchantRequestID") or "").strip()
    if not checkout_id or not merchant_id:
        return _error(
            "Sandbox accepted the request but did not return both request identifiers. Check Daraja Sandbox logs before retrying.",
            503,
            "mpesa_sandbox_reference_missing",
        )
    return jsonify({
        "success": True,
        "message": "Daraja Sandbox accepted the KES 1 test STK request. No production checkout, subscription, or revenue record was created.",
        "checkout_request_id": checkout_id,
        "merchant_request_id": merchant_id,
        "environment": "sandbox",
        "amount": 1,
        "currency": "KES",
        "billing_record_created": False,
    }), 200


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
        already_succeeded = checkout.get("status") == "succeeded"

        try:
            result_code = int(callback.get("ResultCode"))
        except (TypeError, ValueError):
            result_code = None
        if already_succeeded and result_code != 0:
            # Do not let a late/duplicate failure notification downgrade a
            # checkout that was already confirmed by a server-side Daraja query.
            return jsonify({"ResultCode": 0, "ResultDesc": "Callback already applied"}), 200

        callback_meta = {}
        raw_items = (callback.get("CallbackMetadata") or {}).get("Item", [])
        if isinstance(raw_items, list):
            for item in raw_items:
                if not isinstance(item, dict) or not isinstance(item.get("Name"), str):
                    continue
                key, value = item["Name"], item.get("Value")
                if key in {"MpesaReceiptNumber", "Amount", "TransactionDate", "PhoneNumber"} and isinstance(value, (str, int, float)):
                    callback_meta[key] = value

        # Correlate the callback against both IDs from our original STK request.
        # These IDs and metadata are client-facing, so we also query Daraja below.
        callback_merchant_id = str(callback.get("MerchantRequestID") or "").strip()
        stored_merchant_id = str(checkout.get("merchant_request_id") or "").strip()
        if (
            str(callback.get("CheckoutRequestID") or "").strip() != checkout_id
            or not callback_merchant_id
            or not stored_merchant_id
            or callback_merchant_id != stored_merchant_id
        ):
            logger.warning("M-Pesa callback identifiers do not match the stored checkout")
            rows.update_one(
                {"_id": checkout["_id"]},
                {"$set": {
                    "status": "succeeded" if already_succeeded else "awaiting_verification",
                    "callback_received_at": now_utc(),
                    "message": "Callback identifier mismatch; payment requires provider reconciliation.",
                    "updated_at": now_utc(),
                }},
            )
            return jsonify({"ResultCode": 0, "ResultDesc": "Callback acknowledged for reconciliation"}), 200

        validated_receipt = None
        if result_code == 0:
            # The STK query confirms the payment result but often omits the M-Pesa
            # receipt. Only use callback metadata after its amount and payer match
            # this exact server-created checkout.
            try:
                validated_receipt = _validated_callback_receipt(checkout, callback_meta)
            except (MoneyValidationError, ValueError, TypeError):
                rows.update_one(
                    {"_id": checkout["_id"]},
                    {"$set": {
                        "callback_result_code": "0",
                        "callback_result_description": str(callback.get("ResultDesc") or "")[:300],
                        "callback_metadata": callback_meta,
                        "status": "succeeded" if already_succeeded else "awaiting_verification",
                        "callback_received_at": now_utc(),
                        "message": "Successful callback metadata failed correlation checks; no subscription was activated.",
                        "updated_at": now_utc(),
                    }},
                )
                logger.warning("M-Pesa success callback failed amount/payer/receipt validation")
                return jsonify({"ResultCode": 0, "ResultDesc": "Callback acknowledged for reconciliation"}), 200

        if already_succeeded:
            # A public callback cannot supply a trusted receipt by itself. Query
            # Daraja again before accepting receipt metadata for a paid checkout.
            try:
                late_query = _query_checkout(checkout)
            except RuntimeError:
                late_query = {}
            if (
                str(late_query.get("CheckoutRequestID") or "").strip() != checkout_id
                or str(late_query.get("MerchantRequestID") or "").strip() != stored_merchant_id
                or str(late_query.get("ResultCode")) != "0"
            ):
                rows.update_one(
                    {"_id": checkout["_id"]},
                    {"$set": {
                        "callback_metadata": callback_meta,
                        "callback_received_at": now_utc(),
                        "status": "succeeded",
                        "message": "Payment remains verified; a new receipt could not be correlated with a final successful Daraja query.",
                        "updated_at": now_utc(),
                    }},
                )
                return jsonify({"ResultCode": 0, "ResultDesc": "Callback acknowledged for reconciliation"}), 200

            receipt_event = {
                "provider": "mpesa",
                "provider_transaction_id": str(checkout["checkout_request_id"]),
                "user_id": str(checkout["user_id"]),
                "plan_code": str(checkout["plan_code"]),
                "amount": str(checkout["amount"]),
                "currency": str(checkout.get("currency") or "KES"),
                "receipt": validated_receipt,
                "metadata": {
                    "checkout_request_id": checkout_id,
                    "merchant_request_id": checkout.get("merchant_request_id"),
                    "verification_source": "daraja_verified_checkout_late_callback",
                },
            }
            response, status_code = activate_verified_payment(
                receipt_event,
                plan_override=checkout.get("plan_snapshot"),
            )
            body = response.get_json(silent=True) if hasattr(response, "get_json") else {}
            if status_code in {200, 201} and isinstance(body, dict) and body.get("success") is True:
                rows.update_one(
                    {"_id": checkout["_id"]},
                    {"$set": {
                        "receipt": validated_receipt,
                        "callback_result_code": "0",
                        "callback_result_description": str(callback.get("ResultDesc") or "")[:300],
                        "callback_metadata": callback_meta,
                        "callback_received_at": now_utc(),
                        "receipt_updated_at": now_utc(),
                        "status": "succeeded",
                        "message": "M-Pesa receipt reconciled into the existing subscription and revenue ledger.",
                        "updated_at": now_utc(),
                    }},
                )
            else:
                logger.error("Late M-Pesa receipt could not be reconciled | checkout_id=%s", checkout_id)
                rows.update_one(
                    {"_id": checkout["_id"]},
                    {"$set": {
                        "callback_metadata": callback_meta,
                        "callback_received_at": now_utc(),
                        "status": "succeeded",
                        "message": "Payment remains verified; its M-Pesa receipt needs finance reconciliation.",
                        "updated_at": now_utc(),
                    }},
                )
            return jsonify({"ResultCode": 0, "ResultDesc": "Callback acknowledged"}), 200

        # A callback is still reconciled against Daraja's query before changing
        # final state. Save its receipt only after the amount/payer checks above.
        rows.update_one(
            {"_id": checkout["_id"]},
            {"$set": {
                "callback_result_code": str(result_code) if result_code is not None else None,
                "callback_result_description": str(callback.get("ResultDesc") or "")[:300],
                "callback_metadata": callback_meta,
                # Receipt metadata is not persisted until the server-side
                # Daraja query below confirms the final successful transaction.
                "receipt": checkout.get("receipt"),
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

        query_merchant_id = str(query_result.get("MerchantRequestID") or "").strip()
        if (
            str(query_result.get("CheckoutRequestID") or "").strip() != checkout_id
            or not stored_merchant_id
            or query_merchant_id != stored_merchant_id
        ):
            logger.error("M-Pesa status query returned mismatched checkout or merchant identifiers")
            rows.update_one(
                {"_id": checkout["_id"]},
                {"$set": {
                    "status": "awaiting_verification",
                    "message": "Daraja query identifiers did not match the stored checkout; no receipt was accepted.",
                    "updated_at": now_utc(),
                }},
            )
        else:
            # Only enrich the receipt after a server-to-server query has
            # confirmed ResultCode 0 for the exact checkout and merchant IDs.
            if str(query_result.get("ResultCode")) == "0" and validated_receipt:
                rows.update_one(
                    {"_id": checkout["_id"]},
                    {"$set": {
                        "receipt": validated_receipt,
                        "receipt_updated_at": now_utc(),
                        "updated_at": now_utc(),
                    }},
                )
                checkout["receipt"] = validated_receipt
            _apply_final_result(checkout, query_result)
        return jsonify({"ResultCode": 0, "ResultDesc": "Callback acknowledged"}), 200
    except Exception:
        logger.exception("M-Pesa callback processing failed")
        # Return 200 so the callback is not retried indefinitely; checkout stays
        # pending for the authenticated status/reconciliation endpoint.
        return jsonify({"ResultCode": 0, "ResultDesc": "Callback acknowledged for reconciliation"}), 200


@revenue_bp.post("/admin/checkouts/<checkout_id>/refresh")
@require_authenticated
@require_roles(*ADMIN_ROLES)
def revenue_admin_refresh_checkout(checkout_id):
    """Reconcile a pending checkout against Daraja for approved finance admins."""
    rows = _checkout_rows()
    checkout = rows.find_one({"checkout_request_id": checkout_id})
    if not checkout:
        return _error("Checkout not found.", 404, "checkout_not_found")
    if checkout.get("status") == "succeeded":
        return jsonify({"success": True, "verified": True, "replayed": True, "checkout": _public_checkout(checkout)}), 200
    if not checkout.get("checkout_request_id"):
        return _error("Daraja did not provide a checkout reference; support reconciliation is required.", 409, "checkout_not_submitted")
    try:
        result = _query_checkout(checkout)
    except RuntimeError as exc:
        return _error(str(exc), 503, "mpesa_query_failed")
    if str(result.get("CheckoutRequestID") or "").strip() != checkout_id:
        return _error("Daraja did not return a matching checkout reference.", 502, "mpesa_checkout_mismatch")
    success = _apply_final_result(checkout, result)
    fresh = rows.find_one({"_id": checkout["_id"]}) or checkout
    try:
        log_action(
            user_id=current_user_id(),
            action="revenue.mpesa.checkout_reconciled",
            resource="revenue_mpesa_checkout",
            resource_id=checkout_id,
            metadata={"status": fresh.get("status"), "verified": success},
        )
    except Exception:
        current_app.logger.exception("M-Pesa checkout reconciliation succeeded but audit logging failed")
    return jsonify({
        "success": True,
        "verified": success,
        "checkout": _public_checkout(fresh),
    }), 200


@revenue_bp.post("/admin/checkouts/by-id/<checkout_row_id>/resolve-no-payment")
@require_authenticated
@require_roles(*ADMIN_ROLES)
def revenue_admin_resolve_unknown_checkout(checkout_row_id):
    """Release an ambiguous submission only after an admin verifies no charge occurred."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {"resolution", "evidence_reference", "notes"}:
        return _error(
            "Provide resolution='provider_checked_no_charge', evidence_reference, and notes.",
            400,
            "invalid_manual_resolution",
        )
    if payload.get("resolution") != "provider_checked_no_charge":
        return _error(
            "The only supported manual resolution is provider_checked_no_charge.",
            400,
            "invalid_manual_resolution",
        )
    evidence = payload.get("evidence_reference")
    notes = payload.get("notes")
    if not isinstance(evidence, str) or not 6 <= len(evidence.strip()) <= 160:
        return _error("Enter the provider reconciliation/report reference (6–160 characters).", 422, "invalid_evidence_reference")
    if not isinstance(notes, str) or not 10 <= len(notes.strip()) <= 1000:
        return _error("Add 10–1,000 characters explaining the provider-side review.", 422, "invalid_resolution_notes")
    try:
        row_id = ObjectId(checkout_row_id)
    except (InvalidId, TypeError, ValueError):
        return _error("Invalid checkout record identifier.", 400, "invalid_checkout_id")

    rows = _checkout_rows()
    checkout = rows.find_one({"_id": row_id})
    if not checkout:
        return _error("Checkout not found.", 404, "checkout_not_found")
    if checkout.get("status") not in {"initiating", "submission_unknown"} or checkout.get("checkout_request_id"):
        return _error(
            "Only an ambiguous submission without a Daraja checkout reference can be manually resolved here.",
            409,
            "checkout_not_manually_resolvable",
        )
    if checkout.get("status") == "initiating":
        last_updated = checkout.get("updated_at")
        if not isinstance(last_updated, datetime):
            return _error(
                "The initiation timestamp is missing. Keep the checkout locked and ask support to reconcile it.",
                409,
                "checkout_initiation_timestamp_missing",
            )
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=timezone.utc)
        else:
            last_updated = last_updated.astimezone(timezone.utc)
        if now_utc() - last_updated < timedelta(minutes=5):
            return _error(
                "The STK request may still be in flight. Wait at least five minutes from the last initiation update and check Daraja before resolving it.",
                409,
                "checkout_initiation_still_fresh",
            )
    if checkout.get("callback_received_at") or checkout.get("callback_metadata"):
        return _error(
            "Provider callback evidence exists. Use the Daraja reconciliation action instead of manually releasing this checkout.",
            409,
            "provider_evidence_exists",
        )

    actor = current_user_id()
    now = now_utc()
    updated = rows.update_one(
        {
            "_id": row_id,
            "status": checkout.get("status"),
            "checkout_request_id": {"$exists": False},
        },
        {
            "$set": {
                "status": "failed",
                "result_description": "Finance reviewed the provider records and confirmed no charge occurred.",
                "manual_resolution": {
                    "resolution": "provider_checked_no_charge",
                    "evidence_reference": evidence.strip(),
                    "notes": notes.strip(),
                    "resolved_by": str(actor),
                    "resolved_at": now,
                },
                "updated_at": now,
            },
            "$unset": {"active_checkout_slot": ""},
        },
    )
    if updated.modified_count != 1:
        return _error("The checkout changed during resolution. Reload the queue and review it again.", 409, "checkout_state_conflict")

    try:
        log_action(
            user_id=actor,
            action="revenue.mpesa.submission_resolved_no_charge",
            resource="revenue_mpesa_checkout",
            resource_id=checkout_row_id,
            metadata={
                "provider": "mpesa",
                "hub": checkout.get("hub"),
                "evidence_reference": evidence.strip(),
            },
        )
    except Exception:
        current_app.logger.exception("Unknown submission released after provider review, but audit logging failed")

    resolved = rows.find_one({"_id": row_id}) or checkout
    return jsonify({
        "success": True,
        "message": "The provider review was recorded and this checkout slot was released. The customer may retry with a new checkout only after confirming the previous request did not charge.",
        "checkout": _public_checkout(resolved),
    }), 200


@revenue_bp.get("/checkouts/current")
@require_authenticated
def revenue_current_checkout():
    """Return the authenticated user's most recent unresolved hub checkout."""
    user_id = current_user_id()
    hub = request.args.get("hub", "").strip().lower()
    if hub and hub not in {"shamba", "biashara", "elimu", "community", "smart_ai", "marketplace", "faith"}:
        return _error("Unsupported hub.", 400, "unsupported_hub")
    query = {
        "user_id": user_id,
        "status": {
            "$in": [
                "initiating",
                "pending",
                "callback_received",
                "awaiting_verification",
                "verified_activation_failed",
                "submission_unknown",
            ]
        },
    }
    if hub:
        query["hub"] = hub
    checkout = _checkout_rows().find_one(query, sort=[("created_at", DESCENDING)])
    return jsonify({
        "success": True,
        "checkout": _public_checkout(checkout) if checkout else None,
    }), 200


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
