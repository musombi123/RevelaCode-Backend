"""Regression tests for RevelaCode admin operations and role boundaries."""
from __future__ import annotations

import hashlib
import os
import time
import uuid

os.environ.setdefault("JWT_SECRET", "test-only-revelacode-admin-operations-secret")

import jwt
import pytest
from flask import Flask
from werkzeug.security import generate_password_hash, check_password_hash

from backend import auth_gate
from backend.db import get_db
from backend.routes import admin_routes, support_routes


def _token(user_id: str, *, role_claim: str = "user") -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now - 1,
            "exp": now + 600,
            # Deliberately untrusted: privileged endpoints must reload the database role.
            "role": role_claim,
            "roles": [role_claim],
        },
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )


@pytest.fixture
def admin_client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(auth_gate.auth_bp)
    app.register_blueprint(admin_routes.admin_bp, url_prefix="/api")
    app.register_blueprint(support_routes.support_bp, url_prefix="/api/support")
    return app.test_client()


@pytest.fixture
def operations_data():
    db = get_db()
    user_ids = []
    contacts = []
    ticket_ids = []
    legal_versions = []

    def make_user(role: str, *, email: str | None = None, password: str = "A-very-long-test-password-2026", **extra):
        contact = email or f"adminops-{uuid.uuid4().hex}@example.test"
        contacts.append(contact)
        document = {
            "full_name": f"Test {role}",
            "contact": contact,
            "email": contact,
            "password": generate_password_hash(password),
            "role": role,
            "roles": [role],
            "verified": True,
            "is_verified": True,
            "is_active": True,
            "status": "active",
            "created_at": str(time.time()),
            **extra,
        }
        result = db["users"].insert_one(document)
        user_ids.append(result.inserted_id)
        document["_id"] = result.inserted_id
        return document

    yield {"db": db, "make_user": make_user, "ticket_ids": ticket_ids, "legal_versions": legal_versions}

    if user_ids:
        db["users"].delete_many({"_id": {"$in": user_ids}})
    if contacts:
        db["users"].delete_many({"contact": {"$in": contacts}})
        db["admin_invitations"].delete_many({"contact": {"$in": contacts}})
    if ticket_ids:
        db["support_tickets"].delete_many({"_id": {"$in": ticket_ids}})
    for version in legal_versions:
        db["legaldocs"].delete_many({"type": "terms", "version": version})


def test_user_list_ignores_forged_admin_claim_and_uses_current_database_role(admin_client, operations_data):
    actor = operations_data["make_user"]("user")
    response = admin_client.get(
        "/api/admin/list-users",
        headers={"Authorization": f"Bearer {_token(str(actor['_id']), role_claim='revelacode_admin')}"},
    )
    assert response.status_code == 403
    assert response.get_json()["code"] == "forbidden"


def test_support_admin_cannot_ban_or_delete_accounts(admin_client, operations_data):
    support_admin = operations_data["make_user"]("support_admin")
    target = operations_data["make_user"]("user")
    headers = {"Authorization": f"Bearer {_token(str(support_admin['_id']), role_claim='revelacode_admin')}"}

    ban = admin_client.patch(
        f"/api/admin/users/{target['_id']}/status",
        headers=headers,
        json={"action": "ban"},
    )
    deletion = admin_client.delete(f"/api/admin/users/{target['_id']}", headers=headers)

    assert ban.status_code == 403
    assert deletion.status_code == 403
    stored = operations_data["db"]["users"].find_one({"_id": target["_id"]})
    assert stored["status"] == "active"
    assert stored["is_active"] is True


def test_platform_admin_can_invite_support_admin_and_invitee_sets_own_password(
    admin_client, operations_data, monkeypatch
):
    owner = operations_data["make_user"]("revelacode_admin")
    invitee_email = f"invitee-{uuid.uuid4().hex}@example.test"
    operations_data["make_user"]  # Keep helper explicit; invitation user is created only on acceptance.
    sent = {}
    monkeypatch.setattr(
        admin_routes,
        "send_admin_invitation_email",
        lambda **kwargs: (sent.update(kwargs) or {"accepted": True}),
    )
    headers = {"Authorization": f"Bearer {_token(str(owner['_id']), role_claim='user')}"}

    created = admin_client.post(
        "/api/admin/invitations",
        headers=headers,
        json={"full_name": "Support Lead", "contact": invitee_email, "role": "support_admin"},
    )
    assert created.status_code == 201
    assert "token" not in created.get_json()
    assert sent["recipient"] == invitee_email

    stored_invitation = operations_data["db"]["admin_invitations"].find_one({"contact": invitee_email})
    assert stored_invitation is not None
    assert stored_invitation["token_hash"] == hashlib.sha256(sent["token"].encode("utf-8")).hexdigest()
    assert "token" not in stored_invitation

    preview = admin_client.get(
        "/api/admin/invitations/preview",
        query_string={"token": sent["token"], "email": invitee_email},
    )
    assert preview.status_code == 200
    assert preview.get_json()["invitation"]["role"] == "support_admin"

    password = "Support-Team-Password-2026!"
    accepted = admin_client.post(
        "/api/admin/invitations/accept",
        json={
            "token": sent["token"],
            "email": invitee_email,
            "password": password,
            "confirm_password": password,
        },
    )
    assert accepted.status_code == 201
    account = operations_data["db"]["users"].find_one({"contact": invitee_email})
    assert account["role"] == "support_admin"
    assert account["roles"] == ["support_admin"]
    assert account["status"] == "active"
    assert check_password_hash(account["password"], password)

    replay = admin_client.post(
        "/api/admin/invitations/accept",
        json={
            "token": sent["token"],
            "email": invitee_email,
            "password": password,
            "confirm_password": password,
        },
    )
    assert replay.status_code == 404


def test_ban_blocks_a_valid_password_login(admin_client, operations_data):
    owner = operations_data["make_user"]("revelacode_admin")
    target_email = f"banned-{uuid.uuid4().hex}@example.test"
    target = operations_data["make_user"]("user", email=target_email)
    headers = {"Authorization": f"Bearer {_token(str(owner['_id']), role_claim='user')}"}

    response = admin_client.patch(
        f"/api/admin/users/{target['_id']}/status",
        headers=headers,
        json={"action": "ban"},
    )
    assert response.status_code == 200

    login = admin_client.post(
        "/api/login",
        json={"contact": target_email, "password": "A-very-long-test-password-2026"},
    )
    assert login.status_code == 403
    assert login.get_json()["code"] == "account_inactive"


def test_support_admin_can_publish_revisioned_legal_document_and_oversee_support_team(
    admin_client, operations_data
):
    db = operations_data["db"]
    supervisor = operations_data["make_user"]("support_admin")
    agent = operations_data["make_user"]("support")
    ticket = {
        "subject": "Ticket requiring triage",
        "user": "Example member",
        "status": "open",
        "assigned_to": None,
        "created_at": "2026-10-24T00:00:00Z",
    }
    ticket_result = db["support_tickets"].insert_one(ticket)
    operations_data["ticket_ids"].append(ticket_result.inserted_id)
    headers = {"Authorization": f"Bearer {_token(str(supervisor['_id']), role_claim='user')}"}

    version = f"test-{uuid.uuid4().hex}"
    operations_data["legal_versions"].append(version)
    legal = admin_client.put(
        "/api/admin/legal/terms",
        headers=headers,
        json={"version": version, "content": "Test Terms of Service"},
    )
    assert legal.status_code == 201

    published = admin_client.get("/api/legal/terms")
    assert published.status_code == 200
    assert published.get_json()["content"] == "Test Terms of Service"

    overview = admin_client.get("/api/support/admin/overview", headers=headers)
    team = admin_client.get("/api/support/admin/team", headers=headers)
    assignment = admin_client.post(
        f"/api/support/admin/tickets/{ticket_result.inserted_id}/assign",
        headers=headers,
        json={"support_user_id": str(agent["_id"])},
    )
    assert overview.status_code == 200
    assert team.status_code == 200
    assert any(item["id"] == str(agent["_id"]) for item in team.get_json()["team"])
    assert assignment.status_code == 200
    stored_ticket = db["support_tickets"].find_one({"_id": ticket_result.inserted_id})
    assert stored_ticket["assigned_to_user_id"] == str(agent["_id"])
