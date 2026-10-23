from __future__ import annotations

import time

import jwt
import pytest
from flask import Flask

from backend import account_documents as documents
from backend.routes import study_routes as elimu_routes
from tests.test_elimu_learning_routes import FakeDB

TEST_JWT_SECRET = "test-only-jwt-secret-for-ci"


@pytest.fixture()
def account_client(monkeypatch):
    db = FakeDB()
    db["users"].rows[0].update({
        "email": "learner@example.test",
        "contact": "learner@example.test",
        "phone": "+254700000000",
        "password": "must-not-export",
        "password_hash": "must-not-export",
        "api_key": "must-not-export",
        "access_token": "must-not-export",
        "verified": True,
        "roles": ["student"],
    })
    monkeypatch.setattr(documents, "db", db)
    monkeypatch.setattr(documents, "users_col", db["users"])
    monkeypatch.setattr(documents, "certificates_col", db["revelacode_account_certificates"])
    monkeypatch.setattr(documents, "JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("REVELACODE_CERTIFICATE_SIGNING_KEY", "test-only-certificate-key")

    app = Flask(__name__)
    app.register_blueprint(documents.account_documents_bp)
    app.register_blueprint(elimu_routes.study_bp, url_prefix="/api/study")
    return app.test_client(), db


def token_for(user_id="user-1", *, expired=False):
    now = int(time.time())
    claims = {"sub": user_id, "iat": now - 7200 if expired else now, "exp": now - 1 if expired else now + 3600}
    return jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")


def headers_for(user_id="user-1", *, expired=False):
    return {"Authorization": f"Bearer {token_for(user_id, expired=expired)}"}


def test_profile_endpoint_rejects_missing_invalid_and_expired_tokens(account_client):
    client, _ = account_client
    assert client.get("/api/accounts/profile/download?format=json").status_code == 401
    assert client.get("/api/accounts/profile/download?format=json", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.get("/api/accounts/profile/download?format=json", headers=headers_for(expired=True)).status_code == 401


def test_profile_json_and_pdf_are_authoritative_private_and_downloadable(account_client):
    client, _ = account_client
    response = client.get("/api/accounts/profile/download?format=json", headers=headers_for())
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    profile = response.get_json()["profile"]
    assert profile["id"] == "user-1"
    assert profile["full_name"] == "Verified Test Learner"
    assert "student" in profile["roles"]
    for key in ("password", "password_hash", "api_key", "access_token", "token", "refresh_token"):
        assert key not in profile

    pdf = client.get("/api/accounts/profile/download?format=pdf", headers=headers_for())
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")
    assert client.get("/api/accounts/profile/download?format=html", headers=headers_for()).status_code == 400


def test_certificate_issuance_is_verified_idempotent_signed_and_owner_only(account_client):
    client, _ = account_client
    issued = client.post("/api/accounts/certificates", headers=headers_for(), json={})
    assert issued.status_code == 201
    certificate_id = issued.get_json()["certificate_id"]
    assert certificate_id.startswith("RC-AC-")
    assert issued.get_json()["verification_url"].endswith(
        f"/api/verify/certificate/{certificate_id}"
    )

    repeated = client.post("/api/accounts/certificates", headers=headers_for(), json={})
    assert repeated.status_code == 200
    assert repeated.get_json()["certificate_id"] == certificate_id
    assert repeated.get_json()["already_issued"] is True

    downloaded = client.get(f"/api/accounts/certificates/{certificate_id}/download", headers=headers_for())
    assert downloaded.status_code == 200
    assert downloaded.mimetype == "application/pdf"
    assert downloaded.data.startswith(b"%PDF")
    assert client.get(f"/api/accounts/certificates/{certificate_id}/download", headers=headers_for("user-2")).status_code == 404

    verified = client.get(f"/api/verify/certificate/{certificate_id}")
    assert verified.status_code == 200
    body = verified.get_json()
    assert body["valid"] is True
    assert body["certificate_id"] == certificate_id
    assert body["user"]["name"] == "Verified Test Learner"
    assert "email" not in body["user"]
    assert not any("last_accessed" in hub or "id" in hub for hub in body["hubs"])


def test_unverified_string_false_and_inactive_accounts_cannot_get_certificates(account_client):
    client, db = account_client
    db["users"].rows[0]["verified"] = "false"
    refused = client.post("/api/accounts/certificates", headers=headers_for(), json={})
    assert refused.status_code == 409

    db["users"].rows[0]["verified"] = True
    db["users"].rows[0]["status"] = "suspended"
    profile = client.get("/api/accounts/profile/download?format=json", headers=headers_for())
    assert profile.status_code == 403
    assert profile.get_json()["error"]["code"] == "account_inactive"
    assert client.post("/api/accounts/certificates", headers=headers_for(), json={}).status_code == 403


def test_public_verifier_rejects_unknown_altered_and_revoked_records(account_client):
    client, db = account_client
    unknown = client.get("/api/verify/certificate/RC-AC-0000000000000000")
    assert unknown.status_code == 404
    assert unknown.get_json()["valid"] is False

    issued = client.post("/api/accounts/certificates", headers=headers_for(), json={})
    certificate_id = issued.get_json()["certificate_id"]
    collection = db["revelacode_account_certificates"]
    record = collection.find_one({"certificate_id": certificate_id})
    record["claims"]["full_name"] = "Altered Name"
    collection.rows = [record if row.get("certificate_id") == certificate_id else row for row in collection.rows]
    altered = client.get(f"/api/verify/certificate/{certificate_id}").get_json()
    assert altered["valid"] is False
    assert altered["reason"] == "signature_invalid"

    record["claims"]["full_name"] = "Verified Test Learner"
    record["signature"] = documents._canonical_signature(record["claims"])
    record["status"] = "revoked"
    collection.rows = [record if row.get("certificate_id") == certificate_id else row for row in collection.rows]
    revoked = client.get(f"/api/verify/certificate/{certificate_id}").get_json()
    assert revoked["valid"] is False
    assert revoked["reason"] == "certificate_revoked"


def test_only_current_database_admin_can_revoke_certificate(account_client):
    client, db = account_client
    issued = client.post("/api/accounts/certificates", headers=headers_for(), json={})
    certificate_id = issued.get_json()["certificate_id"]

    refused = client.post(f"/api/accounts/certificates/{certificate_id}/revoke", headers=headers_for(), json={"reason": "test"})
    assert refused.status_code == 403

    # The same JWT resolves its role from the current account record, not the JWT claim.
    db["users"].rows[0]["role"] = "admin"
    revoked = client.post(f"/api/accounts/certificates/{certificate_id}/revoke", headers=headers_for(), json={"reason": "test"})
    assert revoked.status_code == 200
    assert revoked.get_json()["status"] == "revoked"
    checked = client.get(f"/api/verify/certificate/{certificate_id}")
    assert checked.get_json()["valid"] is False
    assert checked.get_json()["reason"] == "certificate_revoked"
