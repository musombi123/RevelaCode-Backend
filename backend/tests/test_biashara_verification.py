from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest
from bson import ObjectId

from backend.jumuiya.biashara import schemas, services, verification
from backend.jumuiya.core.errors import APIError


def _matches_clause(document, clause):
    for key, expected in clause.items():
        if key == "$and":
            if not all(_matches_clause(document, part) for part in expected):
                return False
            continue
        if isinstance(expected, dict) and "$exists" in expected:
            if (key in document) is not bool(expected["$exists"]):
                return False
            continue
        if isinstance(expected, dict) and "$in" in expected:
            if document.get(key) not in expected["$in"]:
                return False
            continue
        if document.get(key) != expected:
            return False
    return True


class FakeBusinessCollection:
    def __init__(self, docs=None):
        self.documents = [deepcopy(doc) for doc in (docs or [])]

    def find_one(self, query, *args, **kwargs):
        for document in self.documents:
            if _matches_clause(document, query):
                return deepcopy(document)
        return None

    def insert_one(self, document):
        saved = deepcopy(document)
        saved["_id"] = saved.get("_id") or ObjectId()
        self.documents.append(saved)
        return SimpleNamespace(inserted_id=saved["_id"])

    def find_one_and_update(self, query, update, return_document=None):
        for document in self.documents:
            if not _matches_clause(document, query):
                continue
            document.update(deepcopy(update.get("$set", {})))
            for key in update.get("$unset", {}):
                document.pop(key, None)
            for key, value in update.get("$push", {}).items():
                document.setdefault(key, []).append(deepcopy(value))
            return deepcopy(document)
        return None


def _pending_business():
    return {
        "_id": ObjectId("64b000000000000000000111"),
        "owner_user_id": "owner-1",
        "name": "Coastal Electronics",
        "business_type": "Sole Proprietorship",
        "category": "Electronics",
        "phone": "+254712345678",
        "email": "owner@example.com",
        "county": "Mombasa",
        "location": "Nyali",
        "status": "pending_verification",
        "verification_status": "pending",
        "review_notes": "",
    }


def test_business_payload_does_not_accept_client_status():
    payload = schemas.business_payload({
        "name": "Coastal Electronics",
        "status": "active",
        "verification_status": "verified",
    })

    assert "status" not in payload
    assert "verification_status" not in payload


def test_new_business_is_created_as_pending_application(monkeypatch):
    businesses = FakeBusinessCollection()
    monkeypatch.setattr(services, "collection", lambda name: businesses)
    monkeypatch.setattr(services, "unique_slug", lambda name, current_id=None: "coastal-electronics")
    monkeypatch.setattr(services, "log_action", lambda *args, **kwargs: None)

    result = services.create_or_update_business("owner-1", {
        "name": "Coastal Electronics",
        "business_type": "Sole Proprietorship",
        "category": "Electronics",
        "phone": "+254712345678",
        "email": "owner@example.com",
        "county": "Mombasa",
        "location": "Nyali",
        "status": "active",
        "verification_status": "verified",
    })

    assert result["status"] == "pending_verification"
    assert result["verification_status"] == "pending"
    assert result["owner_user_id"] == "owner-1"
    assert result["verification_history"][0]["event"] == "submitted"


def test_business_workspace_is_denied_before_verification(monkeypatch):
    monkeypatch.setattr(services, "get_business_for_user", lambda user_id: {
        "id": "business-1",
        "status": "pending_verification",
        "verification_status": "pending",
    })

    with pytest.raises(APIError) as exc:
        services._require_business("owner-1")

    assert exc.value.code == "business_verification_required"


def test_business_workspace_requires_both_verified_and_active(monkeypatch):
    monkeypatch.setattr(services, "get_business_for_user", lambda user_id: {
        "id": "business-1",
        "status": "active",
        "verification_status": "verified",
    })

    assert services._require_business("owner-1")["id"] == "business-1"


def test_admin_approval_requires_both_verification_checks(monkeypatch):
    businesses = FakeBusinessCollection([_pending_business()])
    monkeypatch.setattr(verification, "collection", lambda name: businesses)
    monkeypatch.setattr(verification, "log_action", lambda *args, **kwargs: None)

    with pytest.raises(APIError) as exc:
        verification.review_application(
            "admin-1",
            str(businesses.documents[0]["_id"]),
            decision="approve",
            checks={"business_details_checked": True},
        )

    assert exc.value.code == "verification_checks_incomplete"
    assert businesses.documents[0]["verification_status"] == "pending"


def test_admin_approval_activates_verified_business(monkeypatch):
    businesses = FakeBusinessCollection([_pending_business()])
    monkeypatch.setattr(verification, "collection", lambda name: businesses)
    monkeypatch.setattr(verification, "log_action", lambda *args, **kwargs: None)

    result = verification.review_application(
        "admin-1",
        str(businesses.documents[0]["_id"]),
        decision="approve",
        checks={
            "business_details_checked": True,
            "owner_contact_checked": True,
        },
    )

    assert result["status"] == "active"
    assert result["verification_status"] == "verified"
    assert result["verified_by_user_id"] == "admin-1"
    assert result["verification_checks"] == {
        "business_details_checked": True,
        "owner_contact_checked": True,
    }
    assert result["verification_history"][-1]["event"] == "approve"


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        ("reject", "rejected"),
        ("needs_information", "needs_information"),
    ],
)
def test_admin_can_reject_or_request_information(monkeypatch, decision, expected_status):
    businesses = FakeBusinessCollection([_pending_business()])
    monkeypatch.setattr(verification, "collection", lambda name: businesses)
    monkeypatch.setattr(verification, "log_action", lambda *args, **kwargs: None)

    result = verification.review_application(
        "admin-1",
        str(businesses.documents[0]["_id"]),
        decision=decision,
        notes="Please confirm the submitted business contact details.",
        checks={},
    )

    assert result["verification_status"] == expected_status
    assert result["review_notes"] == "Please confirm the submitted business contact details."


def test_admin_cannot_reject_without_review_notes(monkeypatch):
    businesses = FakeBusinessCollection([_pending_business()])
    monkeypatch.setattr(verification, "collection", lambda name: businesses)

    with pytest.raises(APIError) as exc:
        verification.review_application(
            "admin-1",
            str(businesses.documents[0]["_id"]),
            decision="reject",
            notes="   ",
            checks={},
        )

    assert exc.value.code == "review_notes_required"
