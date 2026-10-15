"""Encrypted provider-connection configuration for Biashara.

This registry stores credentials but does not call providers or claim a
connection is healthy. Credentials are encrypted with an environment-managed
Fernet key ring, never returned by API responses, and never included in logs.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from bson import ObjectId
from bson.errors import InvalidId
from cryptography.fernet import Fernet, InvalidToken
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.biashara.tenancy.service import require_permission


CONNECTIONS_COLLECTION = "jumuiya_integration_connections"

PROVIDERS = {
    "woocommerce": {
        "label": "WooCommerce",
        "required_metadata": {"store_url"},
        "optional_metadata": {"api_version"},
        "required_credentials": {"consumer_key", "consumer_secret"},
        "optional_credentials": {"webhook_secret"},
    },
    "whatsapp_cloud": {
        "label": "WhatsApp Cloud API",
        "required_metadata": {"phone_number_id"},
        "optional_metadata": {"business_account_id", "graph_api_version"},
        "required_credentials": {"access_token", "app_secret"},
        "optional_credentials": {"verify_token"},
    },
    "mpesa_daraja": {
        "label": "M-Pesa Daraja",
        "required_metadata": {"shortcode", "environment"},
        "optional_metadata": {"initiator_name", "transaction_type"},
        "required_credentials": {"consumer_key", "consumer_secret", "passkey"},
        "optional_credentials": {"initiator_password", "security_credential"},
    },
}

MAX_CREDENTIAL_FIELD_LENGTH = 16_384
MAX_CREDENTIAL_BUNDLE_LENGTH = 48_000


def now_utc():
    return datetime.now(timezone.utc)


def _clean_id(value):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return value


def _business(user_id, permission):
    context = require_permission(user_id, permission)
    business_id = str(context.get("id") or "")
    if not business_id:
        raise APIError("Selected business is unavailable.", 409, "business_id_missing")
    return context, business_id


def _keyring():
    """Load and validate an environment-managed encryption key ring."""
    raw_ring = os.getenv("BIASHARA_INTEGRATION_ENCRYPTION_KEYS", "").strip()
    current_id = os.getenv("BIASHARA_INTEGRATION_CURRENT_KEY_ID", "").strip()
    ring = {}

    if raw_ring:
        try:
            parsed = json.loads(raw_ring)
        except (TypeError, ValueError):
            raise APIError(
                "Integration encryption key configuration is invalid.",
                503,
                "integration_encryption_unavailable",
            )
        if not isinstance(parsed, dict) or not parsed:
            raise APIError(
                "Integration encryption key configuration is invalid.",
                503,
                "integration_encryption_unavailable",
            )
        for key_id, key_value in parsed.items():
            key_id = str(key_id).strip()
            if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", key_id) or not isinstance(key_value, str):
                raise APIError(
                    "Integration encryption key configuration is invalid.",
                    503,
                    "integration_encryption_unavailable",
                )
            try:
                ring[key_id] = Fernet(key_value.encode("ascii"))
            except (ValueError, UnicodeEncodeError):
                raise APIError(
                    "Integration encryption key configuration is invalid.",
                    503,
                    "integration_encryption_unavailable",
                )
        if not current_id:
            raise APIError(
                "BIASHARA_INTEGRATION_CURRENT_KEY_ID must identify the active key.",
                503,
                "integration_encryption_unavailable",
            )
    else:
        single = os.getenv("BIASHARA_INTEGRATION_ENCRYPTION_KEY", "").strip()
        if not single:
            raise APIError(
                "Integration credentials cannot be stored until the server encryption key is configured.",
                503,
                "integration_encryption_unavailable",
            )
        current_id = current_id or "primary"
        try:
            ring[current_id] = Fernet(single.encode("ascii"))
        except (ValueError, UnicodeEncodeError):
            raise APIError(
                "Integration encryption key configuration is invalid.",
                503,
                "integration_encryption_unavailable",
            )

    if current_id not in ring:
        raise APIError(
            "The configured current integration encryption key is not present in the key ring.",
            503,
            "integration_encryption_unavailable",
        )
    return ring, current_id


def _encrypt_credentials(credentials):
    ring, current_id = _keyring()
    encoded = json.dumps(
        credentials,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if len(encoded) > MAX_CREDENTIAL_BUNDLE_LENGTH:
        raise APIError("Credential bundle is too large.", 422, "integration_credentials_too_large")
    ciphertext = ring[current_id].encrypt(encoded).decode("ascii")
    return ciphertext, current_id


def _decrypt_credentials(document):
    ring, _current_id = _keyring()
    key_id = str(document.get("credential_key_id") or "")
    cipher = ring.get(key_id)
    if cipher is None:
        raise APIError(
            "The encryption key required by this connection is not available. No credential was changed.",
            503,
            "integration_encryption_key_missing",
        )
    try:
        raw = cipher.decrypt(str(document.get("credentials_ciphertext") or "").encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError, ValueError):
        raise APIError(
            "Stored integration credentials could not be decrypted. No credential was changed.",
            503,
            "integration_credentials_unreadable",
        )
    if not isinstance(data, dict):
        raise APIError(
            "Stored integration credentials are invalid. No credential was changed.",
            503,
            "integration_credentials_unreadable",
        )
    return data


def _required_text(value, field, maximum=240):
    if not isinstance(value, str):
        raise APIError(f"{field} must be text.", 422, "invalid_integration_configuration")
    value = value.strip()
    if not value or len(value) > maximum:
        raise APIError(f"{field} is required and must be at most {maximum} characters.", 422, "invalid_integration_configuration")
    if any(ord(char) < 32 for char in value):
        raise APIError(f"{field} contains unsupported control characters.", 422, "invalid_integration_configuration")
    return value


def _validate_store_url(value):
    value = _required_text(value, "store_url", 2048)
    parsed = urlparse(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise APIError("WooCommerce store_url must be an HTTPS URL.", 422, "invalid_integration_url")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise APIError(
            "WooCommerce store_url must not embed credentials, query parameters or a fragment.",
            422,
            "invalid_integration_url",
        )
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost") or host.endswith(".local"):
        raise APIError("Local-only store URLs are not supported.", 422, "invalid_integration_url")
    try:
        address = ipaddress.ip_address(host)
        if not address.is_global:
            raise APIError("Store URL must use a public host.", 422, "invalid_integration_url")
    except ValueError:
        # Hostnames are accepted; a future live adapter must still validate DNS
        # results and block private IPs to prevent SSRF/rebinding.
        if "." not in host or host.startswith(".") or host.endswith("."):
            raise APIError("Store URL host is invalid.", 422, "invalid_integration_url")
    return value.rstrip("/")


def _validate_provider_metadata(provider, metadata, existing=None):
    spec = PROVIDERS[provider]
    if not isinstance(metadata, dict):
        raise APIError("metadata must be an object.", 422, "invalid_integration_configuration")
    existing = existing or {}
    allowed = set(spec["required_metadata"]) | set(spec["optional_metadata"])
    unknown = set(metadata) - allowed
    if unknown:
        raise APIError("Unsupported metadata field(s): " + ", ".join(sorted(unknown)), 422, "invalid_integration_configuration")
    result = dict(existing)
    result.update(metadata)

    missing = set(spec["required_metadata"]) - set(result)
    if missing:
        raise APIError("Missing required metadata field(s): " + ", ".join(sorted(missing)), 422, "invalid_integration_configuration")

    clean = {}
    for field, value in result.items():
        if field == "store_url" and provider == "woocommerce":
            clean[field] = _validate_store_url(value)
        elif field == "environment" and provider == "mpesa_daraja":
            environment = str(value or "").strip().lower()
            if environment not in {"sandbox", "production"}:
                raise APIError("M-Pesa environment must be sandbox or production.", 422, "invalid_integration_configuration")
            clean[field] = environment
        elif field == "transaction_type" and provider == "mpesa_daraja":
            transaction_type = str(value or "").strip()
            if transaction_type not in {"CustomerPayBillOnline", "CustomerBuyGoodsOnline"}:
                raise APIError("M-Pesa transaction_type must be CustomerPayBillOnline or CustomerBuyGoodsOnline.", 422, "invalid_integration_configuration")
            clean[field] = transaction_type
        elif field in {"phone_number_id", "shortcode", "business_account_id", "graph_api_version", "api_version", "initiator_name"}:
            clean[field] = _required_text(value, field, 160)
        else:
            clean[field] = _required_text(value, field, 500)
    return clean


def _validate_credentials(provider, credentials, existing=None):
    spec = PROVIDERS[provider]
    if not isinstance(credentials, dict):
        raise APIError("credentials must be an object.", 422, "invalid_integration_credentials")
    existing = existing or {}
    allowed = set(spec["required_credentials"]) | set(spec["optional_credentials"])
    unknown = set(credentials) - allowed
    if unknown:
        raise APIError(
            "Unsupported credential field(s): " + ", ".join(sorted(unknown)),
            422,
            "invalid_integration_credentials",
        )

    result = dict(existing)
    for field, value in credentials.items():
        result[field] = _required_text(value, field, MAX_CREDENTIAL_FIELD_LENGTH)
    missing = set(spec["required_credentials"]) - set(result)
    if missing:
        raise APIError(
            "Missing required credential field(s): " + ", ".join(sorted(missing)),
            422,
            "invalid_integration_credentials",
        )
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_CREDENTIAL_BUNDLE_LENGTH:
        raise APIError("Credential bundle is too large.", 422, "integration_credentials_too_large")
    return result


def _public_connection(document):
    """Explicit allowlist: never expose ciphertext, credentials or fingerprints."""
    provider = str(document.get("provider") or "")
    return {
        "id": str(document.get("_id") or ""),
        "name": document.get("name", ""),
        "provider": provider,
        "provider_label": PROVIDERS.get(provider, {}).get("label", provider),
        "metadata": dict(document.get("metadata") or {}),
        "configured_credential_fields": sorted(document.get("credential_fields") or []),
        "credentials_configured": bool(document.get("credentials_ciphertext")),
        "enabled": bool(document.get("enabled", False)),
        "connection_status": "configured_unverified" if document.get("enabled") else "disabled",
        "connectivity_test_status": "not_implemented",
        "connected": False,
        "last_tested_at": None,
        "created_at": _serialise_datetime(document.get("created_at")),
        "updated_at": _serialise_datetime(document.get("updated_at")),
        "created_by_user_id": document.get("created_by_user_id"),
        "updated_by_user_id": document.get("updated_by_user_id"),
    }


def _serialise_datetime(value):
    if not isinstance(value, datetime):
        return value
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def _connection_name(value):
    return _required_text(value, "name", 100)


def list_connections(user_id):
    context, business_id = _business(user_id, "integration.view")
    rows = collection(CONNECTIONS_COLLECTION).find({"business_id": business_id}).sort("created_at", -1).limit(100)
    return [_public_connection(row) for row in rows]


def create_connection(user_id, payload):
    context, business_id = _business(user_id, "integration.manage")
    if not isinstance(payload, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    provider = str(payload.get("provider") or "").strip().lower()
    if provider not in PROVIDERS:
        raise APIError("Choose a supported integration provider.", 422, "invalid_integration_provider")
    name = _connection_name(payload.get("name"))
    metadata = _validate_provider_metadata(provider, payload.get("metadata") or {})
    credentials = _validate_credentials(provider, payload.get("credentials"))
    enabled = payload.get("enabled", False)
    if not isinstance(enabled, bool):
        raise APIError("enabled must be a boolean.", 422, "invalid_integration_configuration")
    ciphertext, key_id = _encrypt_credentials(credentials)
    now = now_utc()
    document = {
        "_id": ObjectId(),
        "business_id": business_id,
        "provider": provider,
        "name": name,
        "metadata": metadata,
        "credential_fields": sorted(credentials),
        "credentials_ciphertext": ciphertext,
        "credential_key_id": key_id,
        "enabled": enabled,
        "created_by_user_id": str(user_id),
        "updated_by_user_id": str(user_id),
        "created_at": now,
        "updated_at": now,
        "last_tested_at": None,
        "last_test_status": "not_implemented",
        "source": "owner_configured",
    }
    try:
        collection(CONNECTIONS_COLLECTION).insert_one(document)
    except DuplicateKeyError:
        raise APIError("A connection with this name already exists for this provider.", 409, "integration_connection_exists")
    log_action(user_id, "biashara.integration_connection_created", "integration_connection", document["_id"], {
        "provider": provider,
        "enabled": enabled,
        "credential_field_count": len(credentials),
    })
    return _public_connection(document)


def update_connection(user_id, connection_id, payload):
    _context, business_id = _business(user_id, "integration.manage")
    if not isinstance(payload, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    connections = collection(CONNECTIONS_COLLECTION)
    current = connections.find_one({
        "_id": _clean_id(connection_id),
        "business_id": business_id,
    })
    if not current:
        raise APIError("Integration connection not found.", 404, "integration_connection_not_found")

    allowed_fields = {"name", "metadata", "credentials"}
    unknown = set(payload) - allowed_fields
    if unknown:
        raise APIError("Unsupported update field(s): " + ", ".join(sorted(unknown)), 422, "invalid_integration_configuration")

    updates = {"updated_at": now_utc(), "updated_by_user_id": str(user_id)}
    if "name" in payload:
        updates["name"] = _connection_name(payload["name"])
    if "metadata" in payload:
        updates["metadata"] = _validate_provider_metadata(current["provider"], payload["metadata"], current.get("metadata") or {})
    if "credentials" in payload:
        # Rotation uses a complete, validated set merged with currently stored
        # values; omitted secret fields remain as configured. Only ciphertext
        # is persisted, and the response contains field names, never values.
        current_credentials = _decrypt_credentials(current)
        next_credentials = _validate_credentials(current["provider"], payload["credentials"], current_credentials)
        ciphertext, key_id = _encrypt_credentials(next_credentials)
        updates.update({
            "credentials_ciphertext": ciphertext,
            "credential_key_id": key_id,
            "credential_fields": sorted(next_credentials),
        })

    try:
        updated = connections.find_one_and_update(
            {"_id": current["_id"], "business_id": business_id, "updated_at": current.get("updated_at")},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        raise APIError("A connection with this name already exists for this provider.", 409, "integration_connection_exists")
    if not updated:
        raise APIError("Integration connection changed while saving. Reload and retry.", 409, "integration_connection_conflict")
    log_action(user_id, "biashara.integration_connection_updated", "integration_connection", current["_id"], {
        "provider": current["provider"],
        "credentials_rotated": "credentials" in payload,
    })
    return _public_connection(updated)


def set_connection_enabled(user_id, connection_id, enabled):
    _context, business_id = _business(user_id, "integration.manage")
    if not isinstance(enabled, bool):
        raise APIError("enabled must be a boolean.", 422, "invalid_integration_configuration")
    connections = collection(CONNECTIONS_COLLECTION)
    current = connections.find_one({"_id": _clean_id(connection_id), "business_id": business_id})
    if not current:
        raise APIError("Integration connection not found.", 404, "integration_connection_not_found")
    updated = connections.find_one_and_update(
        {"_id": current["_id"], "business_id": business_id, "enabled": bool(current.get("enabled", False))},
        {"$set": {
            "enabled": enabled,
            "updated_at": now_utc(),
            "updated_by_user_id": str(user_id),
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise APIError("Integration connection changed while saving. Reload and retry.", 409, "integration_connection_conflict")
    log_action(user_id, "biashara.integration_connection_toggled", "integration_connection", current["_id"], {
        "provider": current["provider"],
        "enabled": enabled,
    })
    return _public_connection(updated)

def delete_connection(user_id, connection_id):
    """Remove the encrypted configuration for a tenant-owned connection."""
    _context, business_id = _business(user_id, "integration.manage")
    connections = collection(CONNECTIONS_COLLECTION)
    current = connections.find_one({
        "_id": _clean_id(connection_id),
        "business_id": business_id,
    })
    if not current:
        raise APIError("Integration connection not found.", 404, "integration_connection_not_found")
    result = connections.delete_one({
        "_id": current["_id"],
        "business_id": business_id,
        "updated_at": current.get("updated_at"),
    })
    if not getattr(result, "deleted_count", 0):
        raise APIError("Integration connection changed while deleting. Reload and retry.", 409, "integration_connection_conflict")
    log_action(user_id, "biashara.integration_connection_deleted", "integration_connection", current["_id"], {
        "provider": current.get("provider"),
        "enabled": bool(current.get("enabled")),
        "credentials_removed": bool(current.get("credentials_ciphertext")),
    })
    return {
        "id": str(current["_id"]),
        "status": "deleted",
        "encrypted_credentials_removed": bool(current.get("credentials_ciphertext")),
    }

