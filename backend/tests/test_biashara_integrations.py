import base64
import hashlib
import hmac
import json
import os
import sys
import types
from copy import deepcopy
from types import SimpleNamespace

import pytest
from bson import ObjectId
from cryptography.fernet import Fernet

_missing_module = object()
_original_db_module = sys.modules.get("backend.db", _missing_module)
_test_db_module = types.ModuleType("backend.db")
_test_db_module.get_db = lambda: None
sys.modules["backend.db"] = _test_db_module
try:
    from backend.jumuiya.biashara.integrations import service as integrations
    from backend.jumuiya.biashara.integrations import webhooks
finally:
    if _original_db_module is _missing_module:
        sys.modules.pop("backend.db", None)
    else:
        sys.modules["backend.db"] = _original_db_module

from backend.jumuiya.core.errors import APIError


def _matches(document, query):
    for key, expected in query.items():
        actual = document.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$in" not in expected:
                raise AssertionError("Unsupported query in integration test: " + repr(expected))
        elif actual != expected:
            return False
    return True


class Cursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, field, direction=1):
        self.documents.sort(key=lambda doc: doc.get(field) or datetime_min(), reverse=direction < 0)
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(deepcopy(self.documents))


def datetime_min():
    from datetime import datetime, timezone
    return datetime.min.replace(tzinfo=timezone.utc)


class FakeCollection:
    def __init__(self, enforce_connection_names=True):
        self.documents = []
        self.enforce_connection_names = enforce_connection_names

    def find(self, query=None):
        query = query or {}
        return Cursor([doc for doc in self.documents if _matches(doc, query)])

    def find_one(self, query):
        for doc in self.documents:
            if _matches(doc, query):
                return deepcopy(doc)
        return None

    def insert_one(self, document):
        saved = deepcopy(document)
        if self.enforce_connection_names and self.find_one({
            "business_id": saved["business_id"],
            "provider": saved["provider"],
            "name": saved["name"],
        }):
            from pymongo.errors import DuplicateKeyError
            raise DuplicateKeyError("duplicate integration provider/name")
        saved["_id"] = saved.get("_id") or ObjectId()
        self.documents.append(saved)
        return SimpleNamespace(inserted_id=saved["_id"])

    def find_one_and_update(self, query, update, return_document=None):
        from pymongo.errors import DuplicateKeyError
        for doc in self.documents:
            if _matches(doc, query):
                changes = deepcopy(update.get("$set", {}))
                proposed = {**doc, **changes}
                for other in self.documents:
                    if other is doc:
                        continue
                    if (
                        other.get("business_id") == proposed.get("business_id")
                        and other.get("provider") == proposed.get("provider")
                        and other.get("name") == proposed.get("name")
                    ):
                        raise DuplicateKeyError("duplicate integration provider/name")
                doc.update(changes)
                return deepcopy(doc)
        return None

    def delete_one(self, query):
        for index, doc in enumerate(self.documents):
            if _matches(doc, query):
                del self.documents[index]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


@pytest.fixture
def integration_db(monkeypatch):
    store = FakeCollection()
    deliveries = FakeCollection(enforce_connection_names=False)
    collections = {
        integrations.CONNECTIONS_COLLECTION: store,
        webhooks.DELIVERIES_COLLECTION: deliveries,
    }

    def get_collection(name):
        return collections[name]

    monkeypatch.setattr(integrations, "collection", get_collection)
    monkeypatch.setattr(webhooks, "collection", get_collection)
    monkeypatch.setattr(integrations, "log_action", lambda *args, **kwargs: None)

    def permissions(user_id, permission, business_id=None):
        return {
            "id": business_id or ("business-2" if user_id == "owner-2" else "business-1"),
            "permissions": ["*"],
        }

    monkeypatch.setattr(integrations, "require_permission", permissions)
    monkeypatch.setattr(webhooks, "require_permission", permissions)
    monkeypatch.delenv("BIASHARA_INTEGRATION_ENCRYPTION_KEYS", raising=False)
    monkeypatch.setenv("BIASHARA_INTEGRATION_CURRENT_KEY_ID", "primary")
    monkeypatch.setenv("BIASHARA_INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    store.webhook_deliveries = deliveries
    return store


def _woocommerce_payload(name="Online store", consumer_key="ck_demo", consumer_secret="cs_demo"):
    return {
        "name": name,
        "provider": "woocommerce",
        "metadata": {"store_url": "https://shop.example.test", "api_version": "wc/v3"},
        "credentials": {
            "consumer_key": consumer_key,
            "consumer_secret": consumer_secret,
        },
        "enabled": True,
    }


def test_credentials_are_encrypted_at_rest_and_never_returned(integration_db):
    response = integrations.create_connection("owner-1", _woocommerce_payload(
        consumer_key="ck_private_123",
        consumer_secret="cs_private_456",
    ))
    stored = integration_db.documents[0]

    assert response["connection_status"] == "configured_unverified"
    assert response["connected"] is False
    assert response["connectivity_test_status"] == "not_implemented"
    assert response["configured_credential_fields"] == ["consumer_key", "consumer_secret"]
    assert "credentials_ciphertext" not in response
    assert "credential_key_id" not in response
    assert "ck_private_123" not in json.dumps(response)
    assert "cs_private_456" not in json.dumps(response)
    assert "ck_private_123" not in json.dumps(stored, default=str)
    assert "cs_private_456" not in json.dumps(stored, default=str)
    assert stored["credentials_ciphertext"] != ""
    assert stored["credential_key_id"] == "primary"
    assert integrations._decrypt_credentials(stored) == {
        "consumer_key": "ck_private_123",
        "consumer_secret": "cs_private_456",
    }


def test_missing_encryption_key_fails_closed_without_persisting_credentials(integration_db, monkeypatch):
    monkeypatch.delenv("BIASHARA_INTEGRATION_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("BIASHARA_INTEGRATION_ENCRYPTION_KEYS", raising=False)

    with pytest.raises(APIError) as raised:
        integrations.create_connection("owner-1", _woocommerce_payload())

    assert raised.value.code == "integration_encryption_unavailable"
    assert len(integration_db.documents) == 0


def test_provider_metadata_and_credentials_are_strictly_validated(integration_db):
    invalid_cases = [
        {
            **_woocommerce_payload(),
            "metadata": {"store_url": "http://shop.example.test"},
        },
        {
            **_woocommerce_payload(),
            "metadata": {"store_url": "https://user:password@shop.example.test"},
        },
        {
            **_woocommerce_payload(),
            "metadata": {"store_url": "https://shop.example.test:8443"},
        },
        {
            **_woocommerce_payload(),
            "credentials": {"consumer_key": "key-only"},
        },
        {
            **_woocommerce_payload(),
            "credentials": {"consumer_key": "key", "consumer_secret": "secret", "access_token": "extra"},
        },
        {
            "name": "M-Pesa",
            "provider": "mpesa_daraja",
            "metadata": {"shortcode": "123456", "environment": "prod"},
            "credentials": {"consumer_key": "a", "consumer_secret": "b", "passkey": "c"},
        },
    ]
    for payload in invalid_cases:
        with pytest.raises(APIError):
            integrations.create_connection("owner-1", payload)
    assert len(integration_db.documents) == 0


def test_key_rotation_reencrypts_existing_credentials_without_exposing_them(integration_db, monkeypatch):
    key_v1 = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("BIASHARA_INTEGRATION_ENCRYPTION_KEY", key_v1)
    monkeypatch.delenv("BIASHARA_INTEGRATION_ENCRYPTION_KEYS", raising=False)
    monkeypatch.setenv("BIASHARA_INTEGRATION_CURRENT_KEY_ID", "v1")
    created = integrations.create_connection("owner-1", _woocommerce_payload(
        consumer_key="ck_keep",
        consumer_secret="cs_old",
    ))

    key_v2 = Fernet.generate_key().decode("ascii")
    monkeypatch.delenv("BIASHARA_INTEGRATION_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("BIASHARA_INTEGRATION_ENCRYPTION_KEYS", json.dumps({"v1": key_v1, "v2": key_v2}))
    monkeypatch.setenv("BIASHARA_INTEGRATION_CURRENT_KEY_ID", "v2")
    changed = integrations.update_connection("owner-1", created["id"], {
        "credentials": {"consumer_secret": "cs_new"},
    })

    stored = integration_db.find_one({"_id": ObjectId(created["id"])})
    assert changed["id"] == created["id"]
    assert "cs_new" not in json.dumps(changed)
    assert stored["credential_key_id"] == "v2"
    assert integrations._decrypt_credentials(stored) == {
        "consumer_key": "ck_keep",
        "consumer_secret": "cs_new",
    }


def test_connections_are_scoped_by_business_and_duplicate_names_are_rejected(integration_db):
    first = integrations.create_connection("owner-1", _woocommerce_payload())
    assert len(integrations.list_connections("owner-1")) == 1
    assert integrations.list_connections("owner-2") == []

    with pytest.raises(APIError) as raised:
        integrations.create_connection("owner-1", _woocommerce_payload())
    assert raised.value.code == "integration_connection_exists"

    other = integrations.create_connection("owner-2", _woocommerce_payload())
    assert other["id"] != first["id"]
    assert other["provider"] == "woocommerce"
    assert len(integration_db.documents) == 2


def test_enable_disable_is_a_configuration_state_not_a_connectivity_claim(integration_db):
    connection = integrations.create_connection("owner-1", _woocommerce_payload())
    disabled = integrations.set_connection_enabled("owner-1", connection["id"], False)
    assert disabled["enabled"] is False
    assert disabled["connection_status"] == "disabled"
    assert disabled["connected"] is False

    enabled = integrations.set_connection_enabled("owner-1", connection["id"], True)
    assert enabled["enabled"] is True
    assert enabled["connection_status"] == "configured_unverified"
    assert enabled["connected"] is False


def test_integration_updates_cannot_change_provider_or_business(integration_db):
    connection = integrations.create_connection("owner-1", _woocommerce_payload())
    with pytest.raises(APIError) as unknown:
        integrations.update_connection("owner-1", connection["id"], {
            "provider": "mpesa_daraja",
        })
    assert unknown.value.code == "invalid_integration_configuration"

    with pytest.raises(APIError) as not_found:
        integrations.update_connection("owner-2", connection["id"], {"name": "Stolen"})
    assert not_found.value.code == "integration_connection_not_found"

    saved = integration_db.find_one({"_id": ObjectId(connection["id"])})
    assert saved["provider"] == "woocommerce"
    assert saved["business_id"] == "business-1"
    assert saved["name"] == "Online store"

def test_renaming_connection_to_an_existing_provider_name_returns_conflict(integration_db):
    integrations.create_connection("owner-1", _woocommerce_payload(name="Primary store"))
    second = integrations.create_connection("owner-1", _woocommerce_payload(name="Outlet store"))

    with pytest.raises(APIError) as raised:
        integrations.update_connection("owner-1", second["id"], {"name": "Primary store"})

    assert raised.value.code == "integration_connection_exists"
    current = integration_db.find_one({"_id": ObjectId(second["id"])})
    assert current["name"] == "Outlet store"

def test_delete_connection_removes_encrypted_credentials_and_respects_tenant(integration_db):
    created = integrations.create_connection("owner-1", _woocommerce_payload())
    stored = integration_db.find_one({"_id": ObjectId(created["id"])})
    assert stored["credentials_ciphertext"]

    with pytest.raises(APIError) as denied:
        integrations.delete_connection("owner-2", created["id"])
    assert denied.value.code == "integration_connection_not_found"
    assert integration_db.find_one({"_id": ObjectId(created["id"])}) is not None

    result = integrations.delete_connection("owner-1", created["id"])
    assert result["status"] == "deleted"
    assert result["encrypted_credentials_removed"] is True
    assert integration_db.find_one({"_id": ObjectId(created["id"])}) is None

def test_new_connections_default_to_disabled_until_explicitly_enabled(integration_db):
    payload = _woocommerce_payload(name="Default disabled")
    payload.pop("enabled")
    connection = integrations.create_connection("owner-1", payload)

    assert connection["enabled"] is False
    assert connection["connection_status"] == "disabled"
    assert connection["connected"] is False


def test_supported_whatsapp_and_mpesa_configurations_remain_unverified(integration_db):
    whatsapp = integrations.create_connection("owner-1", {
        "name": "WhatsApp sales",
        "provider": "whatsapp_cloud",
        "metadata": {
            "phone_number_id": "1234567890123",
            "business_account_id": "1234509876",
            "graph_api_version": "v23.0",
        },
        "credentials": {
            "access_token": "whatsapp-access-token",
            "app_secret": "whatsapp-app-secret",
        },
    })
    mpesa = integrations.create_connection("owner-1", {
        "name": "M-Pesa sandbox",
        "provider": "mpesa_daraja",
        "metadata": {
            "shortcode": "123456",
            "environment": "sandbox",
        },
        "credentials": {
            "consumer_key": "mpesa-consumer-key",
            "consumer_secret": "mpesa-consumer-secret",
            "passkey": "mpesa-passkey",
        },
    })

    assert whatsapp["provider"] == "whatsapp_cloud"
    assert mpesa["provider"] == "mpesa_daraja"
    assert whatsapp["connected"] is False and mpesa["connected"] is False
    assert whatsapp["enabled"] is False and mpesa["enabled"] is False
    assert whatsapp["connectivity_test_status"] == "not_implemented"
    assert mpesa["connectivity_test_status"] == "not_implemented"

def _woo_webhook_headers(raw_body, secret, delivery_id="woo-delivery-001", topic="order.created"):
    signature = base64.b64encode(
        hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode("ascii")
    return {
        "X-WC-Webhook-Signature": signature,
        "X-WC-Webhook-Delivery-ID": delivery_id,
        "X-WC-Webhook-Topic": topic,
    }


def test_woocommerce_webhook_signature_queue_encryption_and_deduplication(integration_db):
    secret = "woocommerce-webhook-secret"
    payload = _woocommerce_payload(name="Woo webhook", consumer_key="ck_1", consumer_secret="cs_1")
    payload["credentials"]["webhook_secret"] = secret
    connection = integrations.create_connection("owner-1", payload)
    raw_body = json.dumps({
        "id": 321,
        "status": "processing",
        "billing": {"email": "customer-private@example.test"},
    }, separators=(",", ":")).encode("utf-8")
    headers = _woo_webhook_headers(raw_body, secret)

    first = webhooks.receive_webhook(connection["id"], raw_body, headers)
    replay = webhooks.receive_webhook(connection["id"], raw_body, headers)

    assert first["status"] == "pending_review"
    assert first["event_type"] == "order.created"
    assert first["event_summary"]["resource_type"] == "order"
    assert first["event_summary"]["resource_id"] == "321"
    assert first["event_summary"]["resource_status"] == "processing"
    assert first["effects_applied"] is False
    assert first["duplicate"] is False
    assert replay["duplicate"] is True
    assert len(integration_db.webhook_deliveries.documents) == 1
    stored = integration_db.webhook_deliveries.documents[0]
    assert "customer-private@example.test" not in json.dumps(stored, default=str)
    assert "status" in stored and stored["status"] == "pending_review"
    cipher = integrations._keyring()[0][stored["payload_key_id"]]
    assert cipher.decrypt(stored["payload_ciphertext"].encode("ascii")) == raw_body


def test_woocommerce_webhook_rejects_bad_signature_and_disabled_connection(integration_db):
    payload = _woocommerce_payload(name="Woo bad signature")
    payload["credentials"]["webhook_secret"] = "right-secret"
    connection = integrations.create_connection("owner-1", payload)
    body = b'{"id":1,"status":"created"}'
    headers = _woo_webhook_headers(body, "wrong-secret")

    with pytest.raises(APIError) as invalid:
        webhooks.receive_webhook(connection["id"], body, headers)
    assert invalid.value.code == "webhook_signature_invalid"
    assert len(integration_db.webhook_deliveries.documents) == 0

    disabled_payload = _woocommerce_payload(name="Disabled store")
    disabled_payload["credentials"]["webhook_secret"] = "right-secret"
    disabled_payload["enabled"] = False
    disabled_connection = integrations.create_connection("owner-1", disabled_payload)
    with pytest.raises(APIError) as disabled:
        webhooks.receive_webhook(disabled_connection["id"], body, headers)
    assert disabled.value.code == "webhook_connection_unavailable"


def test_whatsapp_challenge_and_signature_verification_are_required(integration_db):
    connection = integrations.create_connection("owner-1", {
        "name": "WhatsApp webhook",
        "provider": "whatsapp_cloud",
        "metadata": {"phone_number_id": "1234567890123"},
        "credentials": {
            "access_token": "whatsapp-access-token",
            "app_secret": "whatsapp-app-secret",
            "verify_token": "our-meta-verify-token",
        },
        "enabled": True,
    })

    challenge = webhooks.verify_whatsapp_challenge(
        connection["id"], "subscribe", "our-meta-verify-token", "challenge-123"
    )
    assert challenge == "challenge-123"

    with pytest.raises(APIError) as wrong_token:
        webhooks.verify_whatsapp_challenge(
            connection["id"], "subscribe", "not-the-token", "challenge-123"
        )
    assert wrong_token.value.code == "webhook_verification_failed"

    body = json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "waba-private-id",
            "changes": [{
                "field": "messages",
                "value": {
                    "messages": [{
                        "id": "wamid-private-id",
                        "from": "254700111222",
                        "text": {"body": "private-message-body"},
                    }],
                },
            }],
        }],
    }, separators=(",", ":")).encode("utf-8")
    signature = "sha256=" + hmac.new(
        b"whatsapp-app-secret", body, hashlib.sha256
    ).hexdigest()
    received = webhooks.receive_webhook(
        connection["id"], body, {"X-Hub-Signature-256": signature}
    )
    assert received["event_type"] == "whatsapp_business_account"
    assert received["event_summary"]["message_count"] == 1
    assert received["event_summary"]["change_fields"] == ["messages"]
    assert received["status"] == "pending_review"
    assert received["effects_applied"] is False
    stored = integration_db.webhook_deliveries.documents[0]
    assert "254700111222" not in json.dumps(stored, default=str)
    assert "private-message-body" not in json.dumps(stored, default=str)

    with pytest.raises(APIError) as invalid_sig:
        webhooks.receive_webhook(
            connection["id"], body, {"X-Hub-Signature-256": "sha256=" + "0" * 64}
        )
    assert invalid_sig.value.code == "webhook_signature_invalid"
    assert len(integration_db.webhook_deliveries.documents) == 1


def test_webhook_inbox_read_is_tenant_scoped_and_payload_is_redacted(integration_db):
    payload = _woocommerce_payload(name="Woo list", consumer_key="ck_list", consumer_secret="cs_list")
    payload["credentials"]["webhook_secret"] = "secret-for-list"
    connection = integrations.create_connection("owner-1", payload)
    body = b'{"id":99,"status":"created"}'
    webhooks.receive_webhook(
        connection["id"], body,
        _woo_webhook_headers(body, "secret-for-list", delivery_id="woo-list-001", topic="product.created"),
    )

    owner_rows = webhooks.list_webhook_deliveries("owner-1")
    other_rows = webhooks.list_webhook_deliveries("owner-2")
    assert len(owner_rows) == 1
    assert other_rows == []
    assert "payload_ciphertext" not in owner_rows[0]
    assert "payload_key_id" not in owner_rows[0]
    assert "id" in owner_rows[0]


def test_mpesa_webhook_is_not_silently_treated_as_verified(integration_db):
    connection = integrations.create_connection("owner-1", {
        "name": "M-Pesa sandbox hook",
        "provider": "mpesa_daraja",
        "metadata": {"shortcode": "123456", "environment": "sandbox"},
        "credentials": {"consumer_key": "key", "consumer_secret": "secret", "passkey": "pass"},
        "enabled": True,
    })
    with pytest.raises(APIError) as raised:
        webhooks.receive_webhook(connection["id"], b'{"ResultCode":0}', {})
    assert raised.value.code == "webhook_provider_unsupported"
    assert len(integration_db.webhook_deliveries.documents) == 0

def test_oversized_webhook_body_is_rejected_before_persistence(integration_db):
    payload = _woocommerce_payload(name="Oversized webhook")
    payload["credentials"]["webhook_secret"] = "webhook-secret"
    connection = integrations.create_connection("owner-1", payload)
    body = b"x" * (webhooks.MAX_WEBHOOK_BODY_BYTES + 1)

    with pytest.raises(APIError) as raised:
        webhooks.receive_webhook(connection["id"], body, {})

    assert raised.value.code == "webhook_body_too_large"
    assert len(integration_db.webhook_deliveries.documents) == 0

def test_webhook_review_decision_is_tenant_scoped_and_never_applies_effects(integration_db):
    payload = _woocommerce_payload(name="Reviewable store")
    payload["credentials"]["webhook_secret"] = "review-secret"
    connection = integrations.create_connection("owner-1", payload)
    body = b'{"id":456,"status":"created"}'
    received = webhooks.receive_webhook(
        connection["id"], body,
        _woo_webhook_headers(body, "review-secret", delivery_id="woo-review-001", topic="order.created"),
    )

    with pytest.raises(APIError) as denied:
        webhooks.decide_webhook_delivery("owner-2", received["id"], "acknowledge")
    assert denied.value.code == "webhook_delivery_not_found"

    reviewed = webhooks.decide_webhook_delivery(
        "owner-1", received["id"], "acknowledge", "Checked source event; not imported."
    )
    assert reviewed["status"] == "acknowledged"
    assert reviewed["decision"] == "acknowledge"
    assert reviewed["decision_note"] == "Checked source event; not imported."
    assert reviewed["effects_applied"] is False

    replay = webhooks.receive_webhook(
        connection["id"], body,
        _woo_webhook_headers(body, "review-secret", delivery_id="woo-review-001", topic="order.created"),
    )
    assert replay["duplicate"] is True
    assert replay["status"] == "acknowledged"
    assert replay["effects_applied"] is False

    with pytest.raises(APIError) as conflicting:
        webhooks.decide_webhook_delivery("owner-1", received["id"], "dismiss")
    assert conflicting.value.code == "webhook_delivery_already_reviewed"
    assert len(integration_db.webhook_deliveries.documents) == 1

def test_woocommerce_auto_sync_is_explicit_and_requires_a_successful_test(integration_db):
    payload = _woocommerce_payload()
    payload["metadata"]["store_currency"] = "KES"
    response = integrations.create_connection("owner-1", payload)
    stored = next(doc for doc in integration_db.documents if str(doc["_id"]) == response["id"])

    assert response["auto_sync_enabled"] is False
    with pytest.raises(APIError) as untested:
        integrations.set_auto_sync_enabled("owner-1", response["id"], True)
    assert untested.value.code == "integration_connection_not_tested"

    stored["last_test_status"] = "success"
    stored["last_tested_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    enabled = integrations.set_auto_sync_enabled("owner-1", response["id"], True)

    assert enabled["auto_sync_enabled"] is True
    assert enabled["auto_sync_enabled_at"]
    assert enabled["enabled"] is True
    assert "credentials_ciphertext" not in json.dumps(enabled)
    assert "consumer_secret" not in json.dumps(enabled)


def test_woocommerce_auto_sync_requires_confirmed_currency_and_is_provider_scoped(integration_db):
    payload = _woocommerce_payload()
    response = integrations.create_connection("owner-1", payload)
    stored = next(doc for doc in integration_db.documents if str(doc["_id"]) == response["id"])
    stored["last_test_status"] = "success"
    stored["last_tested_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

    with pytest.raises(APIError) as no_currency:
        integrations.set_auto_sync_enabled("owner-1", response["id"], True)
    assert no_currency.value.code == "woocommerce_store_currency_not_confirmed"

    stored["metadata"]["store_currency"] = "USD"
    with pytest.raises(APIError) as mismatch:
        integrations.set_auto_sync_enabled("owner-1", response["id"], True)
    assert mismatch.value.code == "woocommerce_currency_mismatch"


def test_metadata_or_credential_rotation_disables_auto_sync_until_retested(integration_db):
    payload = _woocommerce_payload(consumer_key="ck_before", consumer_secret="cs_before")
    payload["metadata"]["store_currency"] = "KES"
    response = integrations.create_connection("owner-1", payload)
    stored = next(doc for doc in integration_db.documents if str(doc["_id"]) == response["id"])
    stored["last_test_status"] = "success"
    stored["last_tested_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    integrations.set_auto_sync_enabled("owner-1", response["id"], True)

    updated = integrations.update_connection("owner-1", response["id"], {
        "credentials": {
            "consumer_key": "ck_after",
            "consumer_secret": "cs_after",
        }
    })

    assert updated["auto_sync_enabled"] is False
    assert updated["connectivity_test_status"] == "not_tested"
    with pytest.raises(APIError) as needs_test:
        integrations.set_auto_sync_enabled("owner-1", response["id"], True)
    assert needs_test.value.code == "integration_connection_not_tested"


def test_disabling_connection_also_disables_auto_sync(integration_db):
    payload = _woocommerce_payload()
    payload["metadata"]["store_currency"] = "KES"
    response = integrations.create_connection("owner-1", payload)
    stored = next(doc for doc in integration_db.documents if str(doc["_id"]) == response["id"])
    stored["last_test_status"] = "success"
    stored["last_tested_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    integrations.set_auto_sync_enabled("owner-1", response["id"], True)

    disabled = integrations.set_connection_enabled("owner-1", response["id"], False)
    assert disabled["enabled"] is False
    assert disabled["auto_sync_enabled"] is False
    assert disabled["connectivity_test_status"] == "not_tested"

