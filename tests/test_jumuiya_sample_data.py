from __future__ import annotations

from copy import deepcopy
import sys
from types import ModuleType

import pytest
from flask import Flask, g, request

# The focused admin sample-data tests replace collection access with in-memory
# fakes. Stub backend.db before importing Jumuiya so test collection does not
# require a live MongoDB server or production MONGO_URI.
if "backend.db" not in sys.modules:
    database_stub = ModuleType("backend.db")
    database_stub.get_db = lambda: None
    sys.modules["backend.db"] = database_stub

from backend.jumuiya import platform_admin_routes
from backend.jumuiya.core.errors import register_error_handlers
from backend.jumuiya.sample_data import HUB_LABELS, SAMPLE_COLLECTION, sample_fixtures, seed_sample_records


class FakeUpdateResult:
    def __init__(self, *, inserted=False, modified=False):
        self.upserted_id = "sample-inserted" if inserted else None
        self.modified_count = 1 if modified else 0


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, _fields):
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(deepcopy(self.documents))


class FakeCollection:
    def __init__(self):
        self.documents = {}

    def update_one(self, query, update, upsert=False):
        sample_id = query["sample_id"]
        is_new = sample_id not in self.documents
        document = dict(update.get("$setOnInsert", {}))
        document.update(deepcopy(update.get("$set", {})))
        self.documents[sample_id] = document
        return FakeUpdateResult(inserted=is_new, modified=not is_new)

    def count_documents(self, query):
        return sum(
            1 for document in self.documents.values()
            if all(document.get(key) == value for key, value in query.items())
        )

    def find(self, query, _projection=None):
        matched = [
            document for document in self.documents.values()
            if all(document.get(key) == value for key, value in query.items())
        ]
        return FakeCursor(matched)


def test_fixture_catalog_covers_all_jumuiya_areas_and_community_center():
    fixtures = sample_fixtures()
    assert len(fixtures) >= 30
    assert len({item["sample_id"] for item in fixtures}) == len(fixtures)
    assert {item["hub"] for item in fixtures} == set(HUB_LABELS)
    assert HUB_LABELS["community"] == "Community Center"
    community_modules = {
        item["module"] for item in fixtures if item["hub"] == "community"
    }
    assert {"Groups", "Pulse Feed", "Threads", "Events", "Trust & Moderation"} <= community_modules
    assert all(item["title"] and item["summary"] and isinstance(item["details"], dict) for item in fixtures)


def test_seed_is_idempotent_and_writes_only_the_admin_sample_collection(monkeypatch):
    from backend.jumuiya import sample_data

    fake = FakeCollection()
    requested_collections = []
    monkeypatch.setattr(
        sample_data,
        "collection",
        lambda name: requested_collections.append(name) or fake,
    )

    first = seed_sample_records()
    second = seed_sample_records()

    assert requested_collections == [SAMPLE_COLLECTION, SAMPLE_COLLECTION]
    assert first["inserted"] == len(sample_fixtures())
    assert first["total"] == len(sample_fixtures())
    assert second["inserted"] == 0
    assert second["updated"] == len(sample_fixtures())
    assert len(fake.documents) == len(sample_fixtures())
    assert all(document["is_sample"] is True for document in fake.documents.values())
    assert all(document["seed_managed"] is True for document in fake.documents.values())
    assert all("owner_user_id" not in document for document in fake.documents.values())
    assert second["counts_by_hub"]["community"] >= 5


@pytest.fixture
def admin_samples_client(monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = True
    register_error_handlers(app)
    app.register_blueprint(
        platform_admin_routes.platform_admin_bp,
        url_prefix="/api/jumuiya/admin",
    )

    @app.before_request
    def set_test_identity():
        token = request.headers.get("Authorization", "")
        if token == "Bearer test-platform-admin":
            g.jumuiya_user = {"id": "admin-test", "roles": ["revelacode_admin"]}
        elif token == "Bearer test-member":
            g.jumuiya_user = {"id": "member-test", "roles": ["user"]}

    fake = FakeCollection()
    for fixture in sample_fixtures():
        fake.documents[fixture["sample_id"]] = {
            **fixture,
            "is_sample": True,
            "seed_managed": True,
            "sample_label": "SAMPLE DATA — NOT A LIVE CUSTOMER RECORD",
        }
    monkeypatch.setattr(platform_admin_routes, "collection", lambda _name: fake)
    return app.test_client(), fake


def test_sample_records_endpoint_is_admin_only(admin_samples_client):
    client, _fake = admin_samples_client
    response = client.get("/api/jumuiya/admin/sample-records")
    assert response.status_code == 401

    member = client.get(
        "/api/jumuiya/admin/sample-records",
        headers={"Authorization": "Bearer test-member"},
    )
    assert member.status_code == 403


def test_admin_can_filter_community_center_sample_records(admin_samples_client):
    client, _fake = admin_samples_client
    response = client.get(
        "/api/jumuiya/admin/sample-records?hub=community",
        headers={"Authorization": "Bearer test-platform-admin"},
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["sample_only"] is True
    assert payload["live_tenant_collections_modified"] is False
    assert payload["filtered_count"] >= 5
    assert all(item["hub"] == "community" for item in payload["items"])
    assert payload["hubs"]["community"] == "Community Center"


def test_admin_can_restore_sample_records_without_touching_live_hub_data(admin_samples_client, monkeypatch):
    client, _fake = admin_samples_client
    called = {}
    monkeypatch.setattr(
        platform_admin_routes,
        "seed_sample_records",
        lambda: called.update({"seeded": True}) or {
            "inserted": 0,
            "updated": len(sample_fixtures()),
            "total": len(sample_fixtures()),
        },
    )

    response = client.post(
        "/api/jumuiya/admin/sample-records/seed",
        headers={"Authorization": "Bearer test-platform-admin"},
    )

    assert response.status_code == 200
    assert called["seeded"] is True
    assert response.get_json()["data"]["total"] == len(sample_fixtures())
