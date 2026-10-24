from __future__ import annotations

import sys
import types

from flask import Flask, g, jsonify

# This route-contract test never opens a real database connection. The routes
# import the database module, but the service methods under test are replaced
# with deterministic stubs.
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
from backend.jumuiya.community import routes


def authenticated_client():
    app = Flask(__name__)
    app.register_blueprint(
        routes.community_bp,
        url_prefix="/api/jumuiya/community",
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


def test_get_post_comments_uses_the_existing_authenticated_contract(monkeypatch):
    called = {}

    def fake_comments(post_id, *, limit):
        called.update(post_id=post_id, limit=limit)
        return [
            {
                "id": "comment-1",
                "post_id": post_id,
                "body": "A useful response",
                "author": {"id": "member-123", "name": "Test member"},
            }
        ]

    monkeypatch.setattr(routes.services, "comments", fake_comments)
    response = authenticated_client().get(
        "/api/jumuiya/community/posts/507f1f77bcf86cd799439011/comments?limit=12"
    )

    assert response.status_code == 200
    assert called == {"post_id": "507f1f77bcf86cd799439011", "limit": 12}
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"][0]["id"] == "comment-1"
    assert payload["data"][0]["body"] == "A useful response"


def test_post_comment_persists_the_authenticated_author_and_trimmed_body(monkeypatch):
    called = {}

    def fake_add_comment(user_id, post_id, body):
        called.update(user_id=user_id, post_id=post_id, body=body)
        return {
            "id": "comment-2",
            "post_id": post_id,
            "author_user_id": user_id,
            "body": body,
            "status": "published",
        }

    monkeypatch.setattr(routes.services, "add_comment", fake_add_comment)
    response = authenticated_client().post(
        "/api/jumuiya/community/posts/507f1f77bcf86cd799439011/comments",
        json={"body": "  Thanks for sharing.  "},
    )

    assert response.status_code == 201
    assert called == {
        "user_id": "member-123",
        "post_id": "507f1f77bcf86cd799439011",
        "body": "Thanks for sharing.",
    }
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["id"] == "comment-2"
    assert payload["data"]["body"] == "Thanks for sharing."


def test_post_comment_rejects_empty_body_without_calling_service(monkeypatch):
    called = {"value": False}

    def fake_add_comment(*args, **kwargs):
        called["value"] = True
        raise AssertionError("The service must not receive an empty comment.")

    monkeypatch.setattr(routes.services, "add_comment", fake_add_comment)
    response = authenticated_client().post(
        "/api/jumuiya/community/posts/507f1f77bcf86cd799439011/comments",
        json={"body": "   "},
    )

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "validation_error"
    assert called["value"] is False


def test_post_comment_rejects_body_over_limit(monkeypatch):
    response = authenticated_client().post(
        "/api/jumuiya/community/posts/507f1f77bcf86cd799439011/comments",
        json={"body": "x" * 3001},
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation_error"
