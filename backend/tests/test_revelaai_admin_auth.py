"""Regression tests for server-side current-role authorization."""
from __future__ import annotations

import os
import time

os.environ.setdefault("JWT_SECRET", "test-only-revelacode-secret-for-admin-auth")

import jwt
import pytest
from flask import Flask

from backend import auth_gate


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(auth_gate, "MONGO_AVAILABLE", False)
    users = {
        "admin": {"_id": "admin-user-id", "role": "admin"},
        "platform_admin": {"_id": "platform-admin-user-id", "role": "platform_admin"},
        "super_admin": {"_id": "super-admin-user-id", "role": "super_admin"},
        "revelacode_admin": {"_id": "revelacode-admin-user-id", "role": "revelacode_admin"},
        "member": {"_id": "member-user-id", "role": "user"},
    }
    monkeypatch.setattr(auth_gate, "load_users_file", lambda: users)
    app = Flask(__name__)
    app.register_blueprint(auth_gate.auth_bp)
    return app.test_client()


def token_for(user_id: str, *, claimed_role: str | None = None) -> str:
    now = int(time.time())
    claims = {"sub": user_id, "iat": now - 1, "exp": now + 300}
    if claimed_role:
        # The authorization endpoint must ignore this claim and consult the current user record.
        claims["role"] = claimed_role
    return jwt.encode(claims, auth_gate.JWT_SECRET, algorithm=auth_gate.JWT_ALGORITHM)


def test_current_database_admin_is_authorized(client):
    response = client.get(
        "/api/auth/verify-admin",
        headers={"Authorization": f"Bearer {token_for('admin-user-id', claimed_role='user')}"},
    )
    assert response.status_code == 200
    assert response.get_json()["authorized"] is True
    assert response.get_json()["role"] == "admin"


@pytest.mark.parametrize(
    ("role", "user_id"),
    [
        ("platform_admin", "platform-admin-user-id"),
        ("super_admin", "super-admin-user-id"),
        ("revelacode_admin", "revelacode-admin-user-id"),
    ],
)
def test_platform_admin_role_aliases_are_authorized_from_current_record(client, role, user_id):
    response = client.get(
        "/api/auth/verify-admin",
        headers={"Authorization": f"Bearer {token_for(user_id, claimed_role='user')}"},
    )
    assert response.status_code == 200
    assert response.get_json()["authorized"] is True
    assert response.get_json()["role"] == role


def test_non_admin_is_denied_even_with_admin_jwt_claim(client):
    response = client.get(
        "/api/auth/verify-admin",
        headers={"Authorization": f"Bearer {token_for('member-user-id', claimed_role='admin')}"},
    )
    assert response.status_code == 403
    assert response.get_json()["code"] == "admin_required"


def test_missing_bearer_token_is_rejected(client):
    response = client.get("/api/auth/verify-admin")
    assert response.status_code == 401
    assert response.get_json()["code"] == "authentication_required"


def test_unknown_user_cannot_become_admin(client):
    response = client.get(
        "/api/auth/verify-admin",
        headers={"Authorization": f"Bearer {token_for('missing-user-id', claimed_role='admin')}"},
    )
    assert response.status_code == 404
    assert response.get_json()["code"] == "user_not_found"
