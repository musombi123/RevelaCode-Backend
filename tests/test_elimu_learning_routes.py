from __future__ import annotations

from copy import deepcopy
import sys
import types

import pytest
from flask import Flask, g, jsonify

# These route tests use deterministic in-memory databases. Prevent the
# production database module from pinging a real MongoDB instance at import
# time. This minimal object is only for module initialization; each test
# replaces route/database collection references with its own FakeDB fixture.
class _ImportOnlyCollection:
    def __init__(self, name):
        self.name = name


class _ImportOnlyDatabase:
    def get_collection(self, name):
        return _ImportOnlyCollection(name)


_test_db_module = types.ModuleType("backend.db")
_test_db_module.db = _ImportOnlyDatabase()
_test_db_module.get_db = lambda: _test_db_module.db
sys.modules["backend.db"] = _test_db_module

from backend.jumuiya.core.errors import APIError
from backend.routes import study_routes as routes


class FakeCursor(list):
    def limit(self, size):
        return FakeCursor(self[:size])


class FakeCollection:
    def __init__(self, rows=()):
        self.rows = [deepcopy(row) for row in rows]

    @staticmethod
    def _matches(document, query):
        for key, expected in (query or {}).items():
            if key == "$or":
                if not any(FakeCollection._matches(document, option) for option in expected):
                    return False
                continue
            actual = document.get(key)
            if isinstance(expected, dict):
                if "$in" in expected and actual not in expected["$in"]:
                    return False
                if "$ne" in expected and actual == expected["$ne"]:
                    return False
            elif actual != expected:
                return False
        return True

    def find(self, query=None, projection=None):
        return FakeCursor([deepcopy(row) for row in self.rows if self._matches(row, query or {})])

    def find_one(self, query=None, projection=None):
        for row in self.rows:
            if self._matches(row, query or {}):
                return deepcopy(row)
        return None

    def update_one(self, query, update, upsert=False):
        for index, row in enumerate(self.rows):
            if self._matches(row, query):
                changed = deepcopy(row)
                changed.update(deepcopy(update.get("$set", {})))
                self.rows[index] = changed
                return type("UpdateResult", (), {"matched_count": 1, "upserted_id": None})()
        if upsert:
            created = {key: value for key, value in query.items() if not key.startswith("$") and not isinstance(value, dict)}
            created.update(deepcopy(update.get("$setOnInsert", {})))
            created.update(deepcopy(update.get("$set", {})))
            self.rows.append(created)
            return type("UpdateResult", (), {"matched_count": 0, "upserted_id": "inserted"})()
        return type("UpdateResult", (), {"matched_count": 0, "upserted_id": None})()

    def insert_one(self, document):
        self.rows.append(deepcopy(document))
        return type("InsertResult", (), {"inserted_id": str(len(self.rows))})()

    def count_documents(self, query):
        return sum(self._matches(row, query) for row in self.rows)


class FakeDB:
    def __init__(self):
        self.collections = {
            "study_materials": FakeCollection([
                {
                    "id": "lesson-01",
                    "title": "Lesson 1",
                    "category": "education",
                    "status": "published",
                    "metadata": {"course_id": "foundations", "course_title": "Foundations"},
                },
                {
                    "id": "lesson-02",
                    "title": "Lesson 2",
                    "category": "elimu",
                    "status": "published",
                    "metadata": {"course_id": "foundations", "course_title": "Foundations"},
                },
                {
                    "id": "draft-lesson",
                    "title": "Unpublished",
                    "category": "education",
                    "status": "draft",
                    "metadata": {"course_id": "foundations", "course_title": "Foundations"},
                },
            ]),
            routes._ELIMU_LEARNING_PROGRESS: FakeCollection(),
            routes._ELIMU_LEARNING_CERTIFICATES: FakeCollection(),
            "users": FakeCollection([
                {
                    "_id": "user-1",
                    "id": "user-1",
                    "user_id": "user-1",
                    "full_name": "Verified Test Learner",
                    "verified": True,
                    "role": "student",
                },
                {
                    "_id": "user-2",
                    "id": "user-2",
                    "user_id": "user-2",
                    "full_name": "Another User",
                    "verified": True,
                    "role": "student",
                },
            ]),
        }

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]

    def get_collection(self, name):
        return self[name]


@pytest.fixture()
def app_client(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(routes, "get_db", lambda: db)
    monkeypatch.setenv("REVELACODE_CERTIFICATE_SIGNING_KEY", "test-only-certificate-key")

    app = Flask(__name__)
    app.register_blueprint(routes.study_bp, url_prefix="/api/study")

    @app.before_request
    def set_test_identity():
        token = (request_header := __import__("flask").request.headers.get("Authorization", ""))
        if token == "Bearer test-user-1":
            g.jumuiya_user = {"id": "user-1"}
        elif token == "Bearer test-user-2":
            g.jumuiya_user = {"id": "user-2"}

    @app.errorhandler(APIError)
    def handle_api_error(error):
        return jsonify(success=False, error={"code": error.code, "message": error.message}), error.status_code

    return app.test_client(), db


def auth(token="test-user-1"):
    return {"Authorization": f"Bearer {token}"}


def complete_all_lessons(client):
    for lesson_id in ("lesson-01", "lesson-02"):
        response = client.post(
            "/api/study/elimu/progress",
            headers=auth(),
            json={
                "hub_id": routes._ELIMU_LEARNING_HUB_ID,
                "course_id": "foundations",
                "action": "complete_lesson",
                "lesson_id": lesson_id,
            },
        )
        assert response.status_code == 200, response.get_json()
    response = client.post(
        "/api/study/elimu/progress",
        headers=auth(),
        json={"hub_id": routes._ELIMU_LEARNING_HUB_ID, "course_id": "foundations", "action": "complete_course"},
    )
    assert response.status_code == 200, response.get_json()


def test_elimu_learning_routes_require_authenticated_identity(app_client):
    client, _ = app_client
    response = client.get("/api/study/elimu/hubs")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "authentication_required"


def test_list_hubs_and_persisted_progress_read(app_client):
    client, _ = app_client
    hubs = client.get("/api/study/elimu/hubs", headers=auth())
    assert hubs.status_code == 200
    assert len(hubs.get_json()["hubs"]) == 1
    assert hubs.get_json()["hubs"][0]["id"] == routes._ELIMU_LEARNING_HUB_ID

    saved = client.post(
        "/api/study/elimu/progress",
        headers=auth(),
        json={
            "hub_id": routes._ELIMU_LEARNING_HUB_ID,
            "course_id": "foundations",
            "action": "complete_lesson",
            "lesson_id": "lesson-01",
        },
    )
    assert saved.status_code == 200
    progress = client.get(f"/api/study/elimu/progress?hub_id={routes._ELIMU_LEARNING_HUB_ID}", headers=auth())
    assert progress.status_code == 200
    assert progress.get_json()["progress"]["completed_lessons"] == 1
    assert progress.get_json()["progress"]["total_lessons"] == 2


def test_progress_rejects_unknown_lesson_and_incomplete_course(app_client):
    client, _ = app_client
    invalid_lesson = client.post(
        "/api/study/elimu/progress",
        headers=auth(),
        json={
            "hub_id": routes._ELIMU_LEARNING_HUB_ID,
            "course_id": "foundations",
            "action": "complete_lesson",
            "lesson_id": "not-in-this-course",
        },
    )
    assert invalid_lesson.status_code == 404

    incomplete = client.post(
        "/api/study/elimu/progress",
        headers=auth(),
        json={"hub_id": routes._ELIMU_LEARNING_HUB_ID, "course_id": "foundations", "action": "complete_course"},
    )
    assert incomplete.status_code == 409


def test_certificate_requires_complete_recorded_course_and_owner_for_download(app_client):
    client, db = app_client
    early = client.post("/api/study/elimu/certificates/generate", headers=auth(), json={"hub_id": routes._ELIMU_LEARNING_HUB_ID})
    assert early.status_code == 409

    complete_all_lessons(client)
    issued = client.post("/api/study/elimu/certificates/generate", headers=auth(), json={"hub_id": routes._ELIMU_LEARNING_HUB_ID})
    assert issued.status_code == 201
    certificate_id = issued.get_json()["certificate_id"]
    assert certificate_id.startswith("RC-EL-")

    downloaded = client.get(f"/api/study/elimu/certificates/{certificate_id}", headers=auth())
    assert downloaded.status_code == 200
    assert downloaded.mimetype == "application/pdf"

    other_user = client.get(f"/api/study/elimu/certificates/{certificate_id}", headers=auth("test-user-2"))
    assert other_user.status_code == 404

    valid = client.get(f"/api/study/elimu/certificates/verify/{certificate_id}")
    assert valid.status_code == 200
    assert valid.get_json()["valid"] is True
    assert valid.get_json()["certificate_id"] == certificate_id


def test_certificate_verifier_rejects_unknown_tampered_and_revoked_records(app_client):
    client, db = app_client
    complete_all_lessons(client)
    issue = client.post("/api/study/elimu/certificates/generate", headers=auth(), json={"hub_id": routes._ELIMU_LEARNING_HUB_ID})
    certificate_id = issue.get_json()["certificate_id"]
    collection = db[routes._ELIMU_LEARNING_CERTIFICATES]

    unknown = client.get("/api/study/elimu/certificates/verify/RC-EL-0000000000000000")
    assert unknown.status_code == 404
    assert unknown.get_json()["valid"] is False

    record = collection.find_one({"certificate_id": certificate_id})
    record["claims"]["full_name"] = "Tampered Name"
    collection.rows = [record if row.get("certificate_id") == certificate_id else row for row in collection.rows]
    tampered = client.get(f"/api/study/elimu/certificates/verify/{certificate_id}")
    assert tampered.get_json()["valid"] is False
    assert tampered.get_json()["reason"] == "signature_invalid"

    record["claims"]["full_name"] = "Verified Test Learner"
    record["signature"] = routes._elimu_learning_signature(record["claims"])
    record["status"] = "revoked"
    collection.rows = [record if row.get("certificate_id") == certificate_id else row for row in collection.rows]
    revoked = client.get(f"/api/study/elimu/certificates/verify/{certificate_id}")
    assert revoked.get_json()["valid"] is False
    assert revoked.get_json()["reason"] == "certificate_revoked"
