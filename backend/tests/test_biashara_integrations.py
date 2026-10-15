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
    def __init__(self):
        self.documents = []

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
        if self.find_one({
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
    monkeypatch.setattr(integrations, "collection", lambda name: store)
    monkeypatch.setattr(integrations, "log_action", lambda *args, **kwargs: None)

    def permissions(user_id, permission, business_id=None):
        return {
            "id": business_id or ("business-2" if user_id == "owner-2" else "business-1"),
            "permissions": ["*"],
        }

    monkeypatch.setattr(integrations, "require_permission", permissions)
    monkeypatch.delenv("BIASHARA_INTEGRATION_ENCRYPTION_KEYS", raising=False)
    monkeypatch.setenv("BIASHARA_INTEGRATION_CURRENT_KEY_ID", "primary")
    monkeypatch.setenv("BIASHARA_INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
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

