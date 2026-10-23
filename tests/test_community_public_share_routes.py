from __future__ import annotations

import sys
import types

from flask import Flask, jsonify

# Import routes against an import-only DB module so this contract test never
# opens a real MongoDB connection. Each service is replaced with a safe stub.
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


def public_client():
    app = Flask(__name__)
    app.register_blueprint(routes.community_bp, url_prefix="/api/jumuiya/community")

    @app.errorhandler(APIError)
    def handle_api_error(error):
        return jsonify(success=False, error={"code": error.code, "message": error.message}), error.status_code

    return app.test_client()


def test_public_feed_is_readable_without_auth(monkeypatch):
    called = {}

    def fake_public_feed(*, limit, search):
        called.update(limit=limit, search=search)
        return [{"id": "post-1", "title": "Public story"}]

    monkeypatch.setattr(routes.services, "public_feed", fake_public_feed)
    response = public_client().get("/api/jumuiya/community/public/feed?q=story&limit=12")

    assert response.status_code == 200
    assert called == {"limit": 12, "search": "story"}
    payload = response.get_json()
    assert "post-1" in str(payload)


def test_public_post_is_readable_without_auth(monkeypatch):
    monkeypatch.setattr(
        routes.services,
        "public_post",
        lambda post_id: {"id": post_id, "title": "Public story"},
    )
    response = public_client().get("/api/jumuiya/community/public/posts/post-123")

    assert response.status_code == 200
    assert "post-123" in str(response.get_json())


def test_public_profile_is_readable_without_auth(monkeypatch):
    called = {}

    def fake_public_profile(profile_id, *, limit):
        called.update(profile_id=profile_id, limit=limit)
        return {"profile": {"id": profile_id, "name": "Public member"}, "posts": []}

    monkeypatch.setattr(routes.services, "public_profile", fake_public_profile)
    response = public_client().get("/api/jumuiya/community/public/profiles/profile-123?limit=40")

    assert response.status_code == 200
    assert called == {"profile_id": "profile-123", "limit": 40}
    assert "Public member" in str(response.get_json())


def test_public_media_is_readable_without_auth(monkeypatch):
    monkeypatch.setattr(
        routes.services,
        "public_media",
        lambda media_id: {"media": {"id": media_id, "url": "https://media.example/image.jpg"}, "post": {"id": "post-123"}},
    )
    response = public_client().get("/api/jumuiya/community/public/media/media-123")

    assert response.status_code == 200
    assert "media-123" in str(response.get_json())
