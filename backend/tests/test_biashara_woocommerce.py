import json
import os
import sys
import types
from copy import deepcopy
from datetime import datetime, timezone
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
    from backend.jumuiya.biashara import services as biashara_services
    from backend.jumuiya.biashara.integrations import service as integration_service
    from backend.jumuiya.biashara.integrations import woocommerce
finally:
    if _original_db_module is _missing_module:
        sys.modules.pop("backend.db", None)
    else:
        sys.modules["backend.db"] = _original_db_module

from backend.jumuiya.core.errors import APIError


_missing = object()


def _get_path(document, path):
    value = document
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part, _missing)
        else:
            return _missing
    return value


def _matches(document, query):
    for key, expected in query.items():
        actual = _get_path(document, key)
        if isinstance(expected, dict) and any(str(op).startswith("$") for op in expected):
            for op, value in expected.items():
                if op == "$ne":
                    if actual is not _missing and actual == value:
                        return False
                elif op == "$in":
                    if actual not in value:
                        return False
                elif op == "$lte":
                    if actual is _missing or actual > value:
                        return False
                elif op == "$exists":
                    if (actual is not _missing) != bool(value):
                        return False
                else:
                    raise AssertionError("Unsupported query operator: " + op)
        elif actual is _missing or actual != expected:
            return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, key, direction=1):
        self.rows.sort(key=lambda doc: _get_path(doc, key), reverse=direction < 0)
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def __iter__(self):
        return iter(deepcopy(self.rows))


class FakeCollection:
    def __init__(self, documents=None, unique_keys=()):
        self.documents = [deepcopy(row) for row in (documents or [])]
        self.unique_keys = tuple(unique_keys)

    def find_one(self, query):
        for doc in self.documents:
            if _matches(doc, query):
                return deepcopy(doc)
        return None

    def find(self, query=None, projection=None):
        query = query or {}
        return Cursor([doc for doc in self.documents if _matches(doc, query)])

    def insert_one(self, document):
        from pymongo.errors import DuplicateKeyError
        saved = deepcopy(document)
        for keys in self.unique_keys:
            if all(saved.get(k) is not None for k in keys):
                if any(all(row.get(k) == saved.get(k) for k in keys) for row in self.documents):
                    raise DuplicateKeyError("duplicate unique key")
        saved["_id"] = saved.get("_id") or ObjectId()
        self.documents.append(saved)
        return SimpleNamespace(inserted_id=saved["_id"])

    def update_one(self, query, update):
        for doc in self.documents:
            if _matches(doc, query):
                for key, value in update.get("$set", {}).items():
                    doc[key] = deepcopy(value)
                for key, value in update.get("$inc", {}).items():
                    doc[key] = doc.get(key, 0) + value
                for key, value in update.get("$addToSet", {}).items():
                    current = doc.setdefault(key, [])
                    if value not in current:
                        current.append(deepcopy(value))
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    def find_one_and_update(self, query, update, return_document=None):
        for doc in self.documents:
            if _matches(doc, query):
                for key, value in update.get("$set", {}).items():
                    doc[key] = deepcopy(value)
                for key, value in update.get("$inc", {}).items():
                    doc[key] = doc.get(key, 0) + value
                for key, value in update.get("$addToSet", {}).items():
                    current = doc.setdefault(key, [])
                    if value not in current:
                        current.append(deepcopy(value))
                return deepcopy(doc)
        return None


class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self.raw = json.dumps(body).encode("utf-8")
        self.closed = False

    def iter_content(self, chunk_size=32768):
        for offset in range(0, len(self.raw), chunk_size):
            yield self.raw[offset:offset + chunk_size]

    def close(self):
        self.closed = True


def _woo_product(
    external_id=201,
    *,
    name="<b>Face Cream</b>",
    sku="FC-201",
    price="250.00",
    product_type="simple",
    status="publish",
    stock_quantity=8,
    manage_stock=True,
):
    return {
        "id": external_id,
        "name": name,
        "slug": "face-cream",
        "sku": sku,
        "type": product_type,
        "status": status,
        "price": price,
        "regular_price": price,
        "stock_status": "instock",
        "manage_stock": manage_stock,
        "stock_quantity": stock_quantity,
        "short_description": "<p>Daily <strong>skin care</strong></p>",
        "description": "<p>Product <em>description</em></p>",
        "categories": [{"id": 12, "name": "<span>Beauty</span>"}],
        "images": [{"src": "https://cdn.example.test/face-cream.jpg"}],
        "date_modified_gmt": "2026-10-15T08:00:00",
    }


@pytest.fixture
def woo_db(monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("BIASHARA_INTEGRATION_ENCRYPTION_KEY", key)
    monkeypatch.setenv("BIASHARA_INTEGRATION_CURRENT_KEY_ID", "primary")
    monkeypatch.delenv("BIASHARA_INTEGRATION_ENCRYPTION_KEYS", raising=False)
    ciphertext, key_id = integration_service._encrypt_credentials({
        "consumer_key": "ck_private_test",
        "consumer_secret": "cs_private_test",
    })
    connection_id = ObjectId("64b000000000000000000301")
    connection = {
        "_id": connection_id,
        "business_id": "business-1",
        "provider": "woocommerce",
        "name": "Primary shop",
        "metadata": {
            "store_url": "https://shop.example.test",
            "api_version": "wc/v3",
            "store_currency": "KES",
        },
        "credentials_ciphertext": ciphertext,
        "credential_key_id": key_id,
        "credential_fields": ["consumer_key", "consumer_secret"],
        "enabled": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "last_test_status": "not_implemented",
    }
    connections = FakeCollection([connection], unique_keys=(("business_id", "provider", "name"),))
    products = FakeCollection()
    mappings = FakeCollection(unique_keys=(("business_id", "connection_id", "resource_type", "external_id"),))
    collections = {
        integration_service.CONNECTIONS_COLLECTION: connections,
        woocommerce.MAPPINGS_COLLECTION: mappings,
        woocommerce.PRODUCTS_COLLECTION: products,
        "jumuiya_inventory_movements": FakeCollection(),
        "jumuiya_outbox_events": FakeCollection(),
    }

    def get_collection(name):
        return collections[name]

    monkeypatch.setattr(integration_service, "collection", get_collection)
    monkeypatch.setattr(woocommerce, "collection", get_collection)
    monkeypatch.setattr(biashara_services, "collection", get_collection)
    monkeypatch.setattr(biashara_services, "_require_business", lambda user_id: {
        "id": "business-1", "currency": "KES", "name": "Test business",
    })
    monkeypatch.setattr(biashara_services, "require_permission", lambda user_id, permission, business_id=None: {
        "id": business_id or "business-1", "currency": "KES", "permissions": ["*"],
    })
    monkeypatch.setattr(woocommerce, "require_permission", lambda user_id, permission, business_id=None: {
        "id": business_id or "business-1", "currency": "KES", "permissions": ["*"],
    })
    monkeypatch.setattr(biashara_services, "_dispatch_outbox_source", lambda *args, **kwargs: {
        "enqueued": 1, "pending": 0, "errors": 0,
    })
    monkeypatch.setattr(biashara_services, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(integration_service, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(woocommerce, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(woocommerce.socket, "getaddrinfo", lambda *args, **kwargs: [
        (2, 1, 6, "", ("93.184.216.34", 443)),
    ])

    return {
        "connection": connection,
        "connection_id": str(connection_id),
        "collections": collections,
        "products": products,
        "mappings": mappings,
        "connections": connections,
    }


def _mock_api(monkeypatch, products):
    def fake_get(url, **kwargs):
        endpoint = url.split("?", 1)[0]
        if endpoint.endswith("/products"):
            params = kwargs.get("params") or {}
            ids = params.get("include")
            if ids:
                selected = {value.strip() for value in str(ids).split(",")}
                body = [item for item in products if str(item["id"]) in selected and item["status"] == "publish"]
            else:
                body = [item for item in products if item["status"] == "publish"]
            per_page = int(params.get("per_page", 20))
            page = int(params.get("page", 1))
            start = (page - 1) * per_page
            rows = body[start:start + per_page]
            return FakeResponse(rows, headers={
                "X-WP-Total": str(len(body)),
                "X-WP-TotalPages": str(max(1, (len(body) + per_page - 1) // per_page)),
            })
        raise AssertionError("Unexpected WooCommerce URL: " + endpoint)
    monkeypatch.setattr(woocommerce.requests, "get", fake_get)


def test_connection_test_records_last_result_without_exposing_credentials(woo_db, monkeypatch):
    _mock_api(monkeypatch, [_woo_product()])
    result = woocommerce.test_connection("owner-1", woo_db["connection_id"])

    assert result["test_status"] == "success"
    assert result["sample_count"] == 1
    assert result["store_currency"]["matches_business_currency"] is True
    stored = woo_db["connections"].find_one({"_id": woo_db["connection"]["_id"]})
    assert stored["last_test_status"] == "success"
    public = integration_service._public_connection(stored)
    assert public["connected"] is True
    assert public["connectivity_test_status"] == "success"
    assert "ck_private_test" not in json.dumps(public)
    assert "cs_private_test" not in json.dumps(public)


def test_preview_sanitizes_external_html_and_does_not_change_catalog(woo_db, monkeypatch):
    _mock_api(monkeypatch, [_woo_product()])
    preview = woocommerce.preview_products("owner-1", woo_db["connection_id"], page=1, per_page=10)

    assert preview["total"] == 1
    product = preview["products"][0]
    assert product["name"] == "Face Cream"
    assert product["description"] == "Daily skin care"
    assert product["category"] == "Beauty"
    assert product["price"] == "250.00"
    assert product["importable"] is True
    assert product["source_stock_quantity"] == 8
    assert product["import_stock_policy"] == "not_imported_in_catalogue_import"
    assert len(woo_db["products"].documents) == 0
    assert len(woo_db["mappings"].documents) == 0


def test_preview_refuses_to_claim_importable_when_currency_unconfirmed_or_mismatched(woo_db, monkeypatch):
    _mock_api(monkeypatch, [_woo_product()])
    connection = woo_db["connection"]
    connection["metadata"].pop("store_currency")
    preview = woocommerce.preview_products("owner-1", woo_db["connection_id"])
    assert preview["products"][0]["importable"] is False
    assert "store_currency_not_confirmed" in preview["products"][0]["reasons"]

    connection["metadata"]["store_currency"] = "USD"
    preview = woocommerce.preview_products("owner-1", woo_db["connection_id"])
    assert preview["products"][0]["importable"] is False
    assert "currency_mismatch" in preview["products"][0]["reasons"]


def test_import_is_idempotent_and_never_imports_stock_or_cost_price(woo_db, monkeypatch):
    _mock_api(monkeypatch, [_woo_product()])
    first = woocommerce.import_products("owner-1", woo_db["connection_id"], ["201"])
    second = woocommerce.import_products("owner-1", woo_db["connection_id"], ["201"])

    assert first["imported"] == 1
    assert second["already_imported"] == 1
    assert len(woo_db["products"].documents) == 1
    local = woo_db["products"].documents[0]
    assert local["name"] == "Face Cream"
    assert local["sku"] == "FC-201"
    assert local["price"] == 250.0
    assert local["currency"] == "KES"
    assert local["stock_quantity"] == 0
    assert local["cost_price"] == 0
    assert "integration_sources" in local
    assert len(woo_db["mappings"].documents) == 1
    assert woo_db["mappings"].documents[0]["import_status"] == "imported"


def test_import_recovers_mapping_after_product_insert_before_mapping_ack(woo_db, monkeypatch):
    _mock_api(monkeypatch, [_woo_product()])
    product = biashara_services.create_product("owner-1", {
        "name": "Face Cream",
        "description": "Daily skin care",
        "category": "Beauty",
        "sku": "FC-201",
        "price": "250.00",
        "cost_price": 0,
        "currency": "KES",
        "stock_quantity": 0,
        "status": "active",
    }, _integration_source={
        "provider": "woocommerce",
        "connection_id": woo_db["connection_id"],
        "external_id": "201",
        "source_version": "2026-10-15T08:00:00",
    })
    assert product["id"]

    result = woocommerce.import_products("owner-1", woo_db["connection_id"], ["201"])

    assert result["already_imported"] == 1
    assert len(woo_db["products"].documents) == 1
    assert len(woo_db["mappings"].documents) == 1
    assert woo_db["mappings"].documents[0]["local_resource_id"] == product["id"]


def test_import_skips_local_sku_conflicts_and_unsupported_product_types(woo_db, monkeypatch):
    local = biashara_services.create_product("owner-1", {
        "name": "Existing cream",
        "sku": "FC-201",
        "price": 100,
        "currency": "KES",
        "stock_quantity": 0,
    })
    _mock_api(monkeypatch, [
        _woo_product(),
        _woo_product(202, name="Variable kit", sku="KIT-202", product_type="variable"),
    ])
    result = woocommerce.import_products("owner-1", woo_db["connection_id"], ["201", "202"])

    assert result["skipped"] == 2
    assert len(woo_db["products"].documents) == 1
    assert any(row.get("reason") == "local_sku_conflict" for row in result["results"])
    assert any("only_simple_products_supported" in row.get("reason", []) for row in result["results"])


def test_import_blocks_currency_mismatch_and_unconfirmed_currency(woo_db, monkeypatch):
    _mock_api(monkeypatch, [_woo_product()])
    woo_db["connection"]["metadata"]["store_currency"] = "USD"
    with pytest.raises(APIError) as mismatch:
        woocommerce.import_products("owner-1", woo_db["connection_id"], ["201"])
    assert mismatch.value.code == "woocommerce_currency_mismatch"

    woo_db["connection"]["metadata"].pop("store_currency")
    with pytest.raises(APIError) as unconfirmed:
        woocommerce.import_products("owner-1", woo_db["connection_id"], ["201"])
    assert unconfirmed.value.code == "woocommerce_store_currency_not_confirmed"
    assert len(woo_db["products"].documents) == 0


def test_private_dns_destinations_are_rejected_before_http(woo_db, monkeypatch):
    monkeypatch.setattr(woocommerce.socket, "getaddrinfo", lambda *args, **kwargs: [
        (2, 1, 6, "", ("127.0.0.1", 443)),
    ])
    called = []
    monkeypatch.setattr(woocommerce.requests, "get", lambda *args, **kwargs: called.append(True))
    with pytest.raises(APIError) as blocked:
        woocommerce.test_connection("owner-1", woo_db["connection_id"])
    assert blocked.value.code == "woocommerce_store_host_blocked"
    assert called == []
