"""Signature-verified, encrypted inbound webhook inbox.

Supported incoming event envelopes:
- WooCommerce HMAC-SHA256 signatures in X-WC-Webhook-Signature.
- WhatsApp Cloud verification challenges and X-Hub-Signature-256 events.

Verified payloads are encrypted before persistence and only queued for review.
This module does not mutate products, orders, customers, invoices or payments.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.biashara.integrations import service as connection_service
from backend.jumuiya.biashara.tenancy.service import require_permission


DELIVERIES_COLLECTION = "jumuiya_integration_webhook_deliveries"
MAX_WEBHOOK_BODY_BYTES = 1_048_576
_ALLOWED_DELIVERY_ID = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_ALLOWED_EVENT_NAME = re.compile(r"^[A-Za-z0-9._-]{1,160}$")


def now_utc():
    return datetime.now(timezone.utc)


def _clean_id(value):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return value


def _as_iso(value):
    if not isinstance(value, datetime):
        return value
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def _public_delivery(document, duplicate=False):
    return {
        "id": str(document.get("_id") or ""),
        "connection_id": str(document.get("connection_id") or ""),
        "provider": document.get("provider"),
        "delivery_key": document.get("delivery_key"),
        "event_type": document.get("event_type"),
        "status": document.get("status", "pending_review"),
        "payload_sha256": document.get("payload_sha256"),
        "event_summary": dict(document.get("event_summary") or {}),
        "received_at": _as_iso(document.get("received_at")),
        "duplicate": bool(duplicate),
        "effects_applied": False,
    }


def _safe_summary_text(value, maximum=100):
    if not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    if not text or len(text) > maximum or any(ord(char) < 32 for char in text):
        return None
    return text


def _event_summary(provider, event_type, payload):
    """Return only non-sensitive operational identifiers and event counts."""
    summary = {"payload_kind": "object" if isinstance(payload, dict) else "array"}
    if provider == "woocommerce" and isinstance(payload, dict):
        resource = str(event_type).split(".", 1)[0].lower()
        if resource in {"order", "product", "customer", "coupon"}:
            summary["resource_type"] = resource
            resource_id = _safe_summary_text(payload.get("id"), 100)
            if resource_id:
                summary["resource_id"] = resource_id
            status = _safe_summary_text(payload.get("status"), 40)
            if status and re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", status):
                summary["resource_status"] = status
            if resource == "order":
                currency = _safe_summary_text(payload.get("currency"), 3)
                total = _safe_summary_text(payload.get("total"), 32)
                if currency and re.fullmatch(r"[A-Z]{3}", currency.upper()):
                    summary["currency"] = currency.upper()
                if total and re.fullmatch(r"[0-9]+(?:\.[0-9]{1,4})?", total):
                    summary["reported_total"] = total
        return summary

    if provider == "whatsapp_cloud" and isinstance(payload, dict):
        entries = payload.get("entry") if isinstance(payload.get("entry"), list) else []
        fields = set()
        message_count = 0
        status_count = 0
        for entry in entries[:1000]:
            if not isinstance(entry, dict):
                continue
            changes = entry.get("changes") if isinstance(entry.get("changes"), list) else []
            for change in changes[:1000]:
                if not isinstance(change, dict):
                    continue
                field = _safe_summary_text(change.get("field"), 80)
                if field and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", field):
                    fields.add(field)
                value = change.get("value") if isinstance(change.get("value"), dict) else {}
                messages = value.get("messages") if isinstance(value.get("messages"), list) else []
                statuses = value.get("statuses") if isinstance(value.get("statuses"), list) else []
                message_count += len(messages)
                status_count += len(statuses)
        summary.update({
            "entry_count": min(len(entries), 1000),
            "change_fields": sorted(fields)[:40],
            "message_count": message_count,
            "status_count": status_count,
        })
    return summary


def _load_connection(connection_id):
    connection = collection(connection_service.CONNECTIONS_COLLECTION).find_one({
        "_id": _clean_id(connection_id),
        "enabled": True,
    })
    if not connection:
        # Do not reveal whether an inactive or another provider's connection exists.
        raise APIError("Webhook connection not found or disabled.", 404, "webhook_connection_unavailable")
    return connection


def _parse_payload(raw_body):
    if not isinstance(raw_body, (bytes, bytearray)):
        raise APIError("Webhook body must be raw bytes.", 400, "invalid_webhook_body")
    if not raw_body or len(raw_body) > MAX_WEBHOOK_BODY_BYTES:
        raise APIError("Webhook body is empty or exceeds the allowed size.", 413, "webhook_body_too_large")
    try:
        payload = json.loads(bytes(raw_body).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise APIError("Webhook body must be valid UTF-8 JSON.", 400, "invalid_webhook_json")
    if not isinstance(payload, (dict, list)):
        raise APIError("Webhook JSON must be an object or array.", 400, "invalid_webhook_json")
    return payload


def _verify_woocommerce(raw_body, headers, credentials):
    secret = str(credentials.get("webhook_secret") or "")
    supplied = str(headers.get("X-WC-Webhook-Signature") or "").strip()
    delivery_id = str(
        headers.get("X-WC-Webhook-Delivery-ID")
        or headers.get("X-WC-Delivery-ID")
        or ""
    ).strip()
    topic = str(headers.get("X-WC-Webhook-Topic") or "").strip()

    if not secret:
        raise APIError("WooCommerce webhook_secret is not configured for this connection.", 409, "webhook_secret_not_configured")
    if not supplied or not delivery_id or not topic:
        raise APIError("Required WooCommerce webhook headers are missing.", 400, "invalid_webhook_headers")
    if not _ALLOWED_DELIVERY_ID.fullmatch(delivery_id) or not _ALLOWED_EVENT_NAME.fullmatch(topic):
        raise APIError("WooCommerce webhook headers are invalid.", 400, "invalid_webhook_headers")

    expected = base64.b64encode(
        hmac.new(secret.encode("utf-8"), bytes(raw_body), hashlib.sha256).digest()
    ).decode("ascii")
    if not hmac.compare_digest(expected, supplied):
        raise APIError("Webhook signature verification failed.", 401, "webhook_signature_invalid")
    return delivery_id, topic


def _verify_whatsapp(raw_body, headers, credentials):
    secret = str(credentials.get("app_secret") or "")
    supplied = str(headers.get("X-Hub-Signature-256") or "").strip()
    if not secret or not supplied:
        raise APIError("WhatsApp webhook signature is not configured or present.", 401, "webhook_signature_invalid")
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), bytes(raw_body), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        raise APIError("Webhook signature verification failed.", 401, "webhook_signature_invalid")
    return hashlib.sha256(bytes(raw_body)).hexdigest()


def verify_whatsapp_challenge(connection_id, mode, verify_token, challenge):
    connection = _load_connection(connection_id)
    if connection.get("provider") != "whatsapp_cloud":
        raise APIError("Webhook connection not found or disabled.", 404, "webhook_connection_unavailable")
    credentials = connection_service._decrypt_credentials(connection)
    expected_token = str(credentials.get("verify_token") or "")
    challenge = str(challenge or "")
    if (
        str(mode or "") != "subscribe"
        or not expected_token
        or not isinstance(verify_token, str)
        or not hmac.compare_digest(expected_token, verify_token)
        or not challenge
        or len(challenge) > 500
    ):
        raise APIError("Webhook verification failed.", 403, "webhook_verification_failed")
    return challenge


def receive_webhook(connection_id, raw_body, headers):
    """Verify, encrypt and idempotently queue an inbound provider webhook."""
    if len(raw_body or b"") > MAX_WEBHOOK_BODY_BYTES:
        raise APIError("Webhook body exceeds the allowed size.", 413, "webhook_body_too_large")
    connection = _load_connection(connection_id)
    provider = str(connection.get("provider") or "")
    if provider not in {"woocommerce", "whatsapp_cloud"}:
        raise APIError("Inbound webhook processing is not implemented for this provider.", 501, "webhook_provider_unsupported")

    credentials = connection_service._decrypt_credentials(connection)
    if provider == "woocommerce":
        delivery_key, event_type = _verify_woocommerce(raw_body, headers, credentials)
    else:
        delivery_key = _verify_whatsapp(raw_body, headers, credentials)
        event_type_value = None
        try:
            interim = json.loads(bytes(raw_body).decode("utf-8"))
            if isinstance(interim, dict):
                event_object = str(interim.get("object") or "webhook").strip().lower()
                if re.fullmatch(r"[a-z0-9._-]{1,80}", event_object):
                    event_type_value = event_object
        except (UnicodeDecodeError, json.JSONDecodeError):
            interim = None
        event_type = event_type_value or "whatsapp.webhook"

    payload = _parse_payload(raw_body)
    payload_hash = hashlib.sha256(bytes(raw_body)).hexdigest()
    business_id = str(connection.get("business_id") or "")
    connection_id_value = str(connection.get("_id") or "")
    delivery_key = str(delivery_key)
    deliveries = collection(DELIVERIES_COLLECTION)
    query = {
        "business_id": business_id,
        "connection_id": connection_id_value,
        "delivery_key": delivery_key,
    }
    existing = deliveries.find_one(query)
    if existing:
        return _public_delivery(existing, duplicate=True)

    # Encrypt the raw, signature-verified payload at rest. It is not copied into
    # logs, API responses, task descriptions or automation events.
    keyring, key_id = connection_service._keyring()
    ciphertext = keyring[key_id].encrypt(bytes(raw_body)).decode("ascii")
    document = {
        "_id": ObjectId(),
        "business_id": business_id,
        "connection_id": connection_id_value,
        "provider": provider,
        "delivery_key": delivery_key,
        "event_type": event_type,
        "status": "pending_review",
        "effects_applied": False,
        "payload_sha256": payload_hash,
        "event_summary": _event_summary(provider, event_type, payload),
        "payload_ciphertext": ciphertext,
        "payload_key_id": key_id,
        "payload_content_type": "application/json",
        "received_at": now_utc(),
        "updated_at": now_utc(),
    }
    try:
        deliveries.insert_one(document)
    except DuplicateKeyError:
        existing = deliveries.find_one(query)
        if existing:
            return _public_delivery(existing, duplicate=True)
        raise

    return _public_delivery(document, duplicate=False)


def list_webhook_deliveries(user_id, limit=50, status=None, provider=None):
    context = require_permission(user_id, "integration.view")
    business_id = str(context.get("id") or "")
    if not business_id:
        raise APIError("Selected business is unavailable.", 409, "business_id_missing")
    try:
        limit = min(max(int(limit), 1), 100)
    except (TypeError, ValueError):
        limit = 50
    query = {"business_id": business_id}
    if status:
        clean_status = str(status).strip().lower()
        if clean_status not in {"pending_review", "processing", "processed", "failed", "dismissed"}:
            raise APIError("Unknown webhook delivery status.", 422, "invalid_webhook_status")
        query["status"] = clean_status
    if provider:
        clean_provider = str(provider).strip().lower()
        if clean_provider not in connection_service.PROVIDERS:
            raise APIError("Unknown integration provider.", 422, "invalid_integration_provider")
        query["provider"] = clean_provider
    rows = collection(DELIVERIES_COLLECTION).find(query).sort("received_at", -1).limit(limit)
    return [_public_delivery(row) for row in rows]
