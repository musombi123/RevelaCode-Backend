from __future__ import annotations

import time

import jwt
import pytest
from flask import Flask

from backend import account_documents as documents
from backend.routes import elimu_learning_routes as elimu_routes
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
    monkeypatch.setattr(documents, "certificates_col", db[documents.certificates_col.name] if hasattr(documents.certificates_col, "name") else db["revelacode_account_certificates"])
    monkeypatch.setattr(documents, "JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("REVELACODE_CERTIFICATE_SIGNING_KEY", "test-only-certificate-key")

    app = Flask(__name__)
    app.register_blueprint(documents.account_documents_bp)
    app.register_blueprint(elimu_routes.elimu_learning_bp)
    return app.test_client(), db


def token_for(user_id="user-1", *, expired=False):
    now = int(time.time())
    claims = {
        "sub": user_id,
        "iat": now - 7200 if expired else now,
        "exp": now - 1 if expired else now + 3600,
    }
    return jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")


def headers_for(user_id="user-1", *, expired=False):
    return {"Authorization": f"Bearer {token_for(user_id, expired=expired)}"}


def test_profile_export_requires_a_valid_current_session(account_client):
    client, _ = account_client
    missing = client.get("/api/accounts/profile/download?format=json")
    assert missing.status_code == 401

    invalid = client.get("/api/accounts/profile/download?format=json", headers={"Authorization": "Bearer invalid"})
    assert invalid.status_code == 401

    expired = client.get("/api/accounts/profile/download?format=json", headers=headers_for(expired=True))
    assert expired.status_code == 401


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

    unsupported = client.get("/api/accounts/profile/download?format=html", headers=headers_for())
    assert unsupported.status_code == 400


def test_account_certificate_is_issued_idempotently_signed_and_owner_download_only(account_client):
    client, db = account_client
    issued = client.post("/api/accounts/certificates", headers=headers_for(), json={})
    assert issued.status_code == 201
    certificate_id = issued.get_json()["certificate_id"]
    assert certificate_id.startswith("RC-AC-")

    repeat = client.post("/api/accounts/certificates", headers=headers_for(), json={})
    assert repeat.status_code == 200
    assert repeat.get_json()["certificate_id"] == certificate_id
    assert repeat.get_json()["already_issued"] is True

    downloaded = client.get(f"/api/accounts/certificates/{certificate_id}/download", headers=headers_for())
    assert downloaded.status_code == 200
    assert downloaded.mimetype == "application/pdf"
    assert downloaded.data.startswith(b"%PDF")

    denied = client.get(
        f"/api/accounts/certificates/{certificate_id}/download",
        headers=headers_for("user-2"),
    )
    assert denied.status_code == 404

    public = client.get(f"/api/verify/certificate/{certificate_id}")
    assert public.status_code == 200
    result = public.get_json()
    assert result["valid"] is True
    assert result["certificate_id"] == certificate_id
    assert result["user"]["name"] == "Verified Test Learner"
    assert "email" not in result["user"]


def test_account_certificate_rejects_unverified_identity_and_detects_tampering(account_client):
    client, db = account_client
    db["users"].rows[0]["verified"] = False
    refused = client.post("/api/accounts/certificates", headers=headers_for(), json={})
    assert refused.status_code == 409

    db["users"].rows[0]["verified"] = True
    issued = client.post("/api/accounts/certificates", headers=headers_for(), json={})
    assert issued.status_code == 201
    certificate_id = issued.get_json()["certificate_id"]

    collection = db["revelacode_account_certificates"]
    record = collection.find_one({"certificate_id": certificate_id})
    record["claims"]["full_name"] = "Altered Name"
    collection.rows = [record if row.get("certificate_id") == certificate_id else row for row in collection.rows]
    response = client.get(f"/api/verify/certificate/{certificate_id}")
    assert response.status_code == 200
    assert response.get_json()["valid"] is False
    assert response.get_json()["reason"] == "signature_invalid"


def test_only_current_database_admin_can_revoke_and_revoked_certificates_fail_verification(account_client):
    client, db = account_client
    issued = client.post("/api/accounts/certificates", headers=headers_for(), json={})
    assert issued.status_code == 201
    certificate_id = issued.get_json()["certificate_id"]

    refused = client.post(f"/api/accounts/certificates/{certificate_id}/revoke", headers=headers_for(), json={"reason": "test"})
    assert refused.status_code == 403

    # Simulate an administrator role change in the authoritative account row.
    db["users"].rows[0]["role"] = "admin"
    revoked = client.post(f"/api/accounts/certificates/{certificate_id}/revoke", headers=headers_for(), json={"reason": "test revocation"})
    assert revoked.status_code == 200
    assert revoked.get_json()["status"] == "revoked"

    checked = client.get(f"/api/verify/certificate/{certificate_id}")
    assert checked.status_code == 200
    assert checked.get_json()["valid"] is False
    assert checked.get_json()["reason"] == "certificate_revoked"


def test_public_verifier_rejects_unknown_certificate_ids(account_client):
    client, _ = account_client
    malformed = client.get("/api/verify/certificate/not-a-certificate")
    assert malformed.status_code == 404
    assert malformed.get_json()["valid"] is False
