import sys
import types
from copy import deepcopy
from types import SimpleNamespace

import pytest
from bson import ObjectId

_missing_module = object()
_original_db_module = sys.modules.get("backend.db", _missing_module)
_test_db_module = types.ModuleType("backend.db")
_test_db_module.get_db = lambda: None
sys.modules["backend.db"] = _test_db_module
try:
    from backend.jumuiya.biashara import domains
finally:
    if _original_db_module is _missing_module:
        sys.modules.pop("backend.db", None)
    else:
        sys.modules["backend.db"] = _original_db_module

from backend.jumuiya.core.errors import APIError


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, field, direction=1):
        self.rows.sort(key=lambda row: row.get(field) or "", reverse=direction < 0)
        return self

    def limit(self, amount):
        self.rows = self.rows[:amount]
        return self

    def __iter__(self):
        return iter(deepcopy(self.rows))


class FakeCollection:
    def __init__(self):
        self.documents = []

    def find(self, query=None):
        query = query or {}
        return Cursor([
            row for row in self.documents
            if all(row.get(key) == value for key, value in query.items())
        ])

    def find_one(self, query):
        for row in self.documents:
            if all(row.get(key) == value for key, value in query.items()):
                return deepcopy(row)
        return None

    def insert_one(self, document):
        from pymongo.errors import DuplicateKeyError
        if self.find_one({"hostname": document["hostname"]}):
            raise DuplicateKeyError("duplicate hostname")
        row = deepcopy(document)
        row["_id"] = row.get("_id") or ObjectId()
        self.documents.append(row)
        return SimpleNamespace(inserted_id=row["_id"])

    def find_one_and_update(self, query, update, return_document=None):
        for row in self.documents:
            if all(row.get(key) == value for key, value in query.items()):
                row.update(deepcopy(update.get("$set", {})))
                return deepcopy(row)
        return None

    def delete_one(self, query):
        for index, row in enumerate(self.documents):
            if all(row.get(key) == value for key, value in query.items()):
                del self.documents[index]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


@pytest.fixture
def domains_db(monkeypatch):
    store = FakeCollection()
    monkeypatch.setattr(domains, "collection", lambda name: store)
    monkeypatch.setattr(domains, "log_action", lambda *args, **kwargs: None)

    def permission_context(user_id, permission, business_id=None):
        business = business_id or ("business-2" if user_id == "owner-2" else "business-1")
        return {"id": business, "membership_role": "owner", "permissions": ["*"]}

    monkeypatch.setattr(domains, "require_permission", permission_context)
    return store


def test_hostname_normalization_and_invalid_domain_rejection():
    assert domains.normalize_hostname("  Shop.Example.CO.KE. ") == "shop.example.co.ke"
    for invalid in (
        "",
        "https://shop.example.test",
        "shop.example.test/path",
        "shop.example.test:8443",
        "user@shop.example.test",
        "localhost",
        "store.local",
        "127.0.0.1",
        "192.168.1.5",
        "single",
        "-bad.example.test",
        "bad_.example.test",
        "bad..example.test",
    ):
        with pytest.raises(APIError):
            domains.normalize_hostname(invalid)


def test_domain_claim_has_txt_challenge_and_dns_verification_is_distinct_from_live_hosting(domains_db, monkeypatch):
    created = domains.create_domain_claim("owner-1", "Shop.Example.CO.KE")
    saved = domains_db.documents[0]

    assert created["hostname"] == "shop.example.co.ke"
    assert created["status"] == "pending_dns"
    assert created["record_type"] == "TXT"
    assert created["record_name"] == "_revelacode-verification.shop.example.co.ke"
    assert created["record_value"].startswith(domains.TXT_PREFIX)
    assert created["domain_serving_status"] == "not_configured"

    expected = created["record_value"]
    monkeypatch.setattr(domains, "_lookup_txt_records", lambda name: [expected, "unrelated=txt"])
    verified = domains.verify_domain_claim("owner-1", created["id"])

    assert verified["status"] == "verified"
    assert verified["verified"] is True
    assert verified["verification_result"] == "verified"
    assert verified["domain_serving_status"] == "not_configured"
    assert saved["hostname"] == "shop.example.co.ke"
    assert domains_db.documents[0]["verified_by_user_id"] == "owner-1"


def test_missing_txt_record_leaves_domain_pending_and_retryable(domains_db, monkeypatch):
    created = domains.create_domain_claim("owner-1", "store.example.test")
    monkeypatch.setattr(domains, "_lookup_txt_records", lambda name: ["some=other-record"])

    result = domains.verify_domain_claim("owner-1", created["id"])

    assert result["status"] == "pending_dns"
    assert result["verified"] is False
    assert result["verification_result"] == "verification_txt_record_not_found"
    assert result["domain_serving_status"] == "not_configured"
    assert domains_db.documents[0]["verified_at"] is None


def test_dns_lookup_failure_is_reported_without_leaking_resolver_details(domains_db, monkeypatch):
    created = domains.create_domain_claim("owner-1", "timeout.example.test")

    def timeout(_name):
        raise TimeoutError("internal resolver endpoint and network details")

    monkeypatch.setattr(domains, "_lookup_txt_records", timeout)
    result = domains.verify_domain_claim("owner-1", created["id"])

    assert result["status"] == "pending_dns"
    assert result["verification_result"] == "dns_lookup_failed"
    assert "internal resolver endpoint" not in str(result)


def test_domain_claims_are_tenant_scoped_and_duplicate_hostnames_are_blocked(domains_db):
    first = domains.create_domain_claim("owner-1", "store.example.test")
    replay = domains.create_domain_claim("owner-1", "STORE.EXAMPLE.TEST")
    assert replay["id"] == first["id"]
    assert replay["record_value"] == first["record_value"]
    assert len(domains_db.documents) == 1

    with pytest.raises(APIError) as other_business:
        domains.create_domain_claim("owner-2", "store.example.test")
    assert other_business.value.code == "domain_already_claimed"

    assert len(domains.list_domain_claims("owner-1")) == 1
    assert domains.list_domain_claims("owner-2") == []

    with pytest.raises(APIError) as access_denied:
        domains.verify_domain_claim("owner-2", first["id"])
    assert access_denied.value.code == "domain_claim_not_found"


def test_domain_claim_deletion_does_not_claim_to_change_registrar_dns(domains_db):
    claim = domains.create_domain_claim("owner-1", "store.example.test")
    deleted = domains.delete_domain_claim("owner-1", claim["id"])

    assert deleted["status"] == "deleted"
    assert deleted["domain_serving_status"] == "not_configured"
    assert len(domains_db.documents) == 0

    with pytest.raises(APIError) as missing:
        domains.delete_domain_claim("owner-1", claim["id"])
    assert missing.value.code == "domain_claim_not_found"
