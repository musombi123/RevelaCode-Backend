from __future__ import annotations

import sys
import types

from flask import Flask, g, jsonify

# Route contract tests must not open a real MongoDB connection.
if "backend.db" not in sys.modules:
    _test_db_module = types.ModuleType("backend.db")

    class _ImportOnlyCollection:
        def __init__(self, name):
            self.name = name

    class _ImportOnlyDatabase:
        def get_collection(self, name):
            return _ImportOnlyCollection(name)

    _test_db_module.db = _ImportOnlyDatabase()
    _test_db_module.get_db = lambda: _test_db_module.db
    sys.modules["backend.db"] = _test_db_module

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.notifications import routes


def authenticated_client():
    app = Flask(__name__)
    app.register_blueprint(
        routes.notifications_bp,
        url_prefix="/api/jumuiya/notifications",
    )

    @app.before_request
    def attach_test_identity():
        g.jumuiya_user = {"id": "member-123"}

    @app.errorhandler(APIError)
    def handle_api_error(error):
        return (
            jsonify(
                success=False,
                error={"code": error.code, "message": error.message},
            ),
            error.status_code,
        )

    return app.test_client()


def test_list_notifications_uses_authenticated_user_and_bounded_limit(monkeypatch):
    called = {}

    def fake_list(user_id, limit):
        called.update(user_id=user_id, limit=limit)
        return [{"id": "notification-1", "title": "Order received", "read": False}]

    monkeypatch.setattr(routes.services, "list_notifications", fake_list)
    response = authenticated_client().get("/api/jumuiya/notifications?limit=25")

    assert response.status_code == 200
    assert called == {"user_id": "member-123", "limit": 25}
    assert response.get_json()["data"][0]["id"] == "notification-1"


def test_mark_notification_read_uses_jumuiya_read_route(monkeypatch):
    called = {}

    def fake_mark_read(user_id, notification_id):
        called.update(user_id=user_id, notification_id=notification_id)
        return {"id": notification_id, "read": True}

    monkeypatch.setattr(routes.services, "mark_read", fake_mark_read)
    response = authenticated_client().put(
        "/api/jumuiya/notifications/notification-123/read"
    )

    assert response.status_code == 200
    assert called == {
        "user_id": "member-123",
        "notification_id": "notification-123",
    }
    assert response.get_json()["data"]["read"] is True


def test_mark_all_notifications_read_uses_authenticated_user(monkeypatch):
    called = {}

    def fake_mark_all_read(user_id):
        called["user_id"] = user_id
        return {"updated": 4, "read": True}

    monkeypatch.setattr(routes.services, "mark_all_read", fake_mark_all_read)
    response = authenticated_client().put("/api/jumuiya/notifications/read-all")

    assert response.status_code == 200
    assert called == {"user_id": "member-123"}
    assert response.get_json()["data"]["updated"] == 4
