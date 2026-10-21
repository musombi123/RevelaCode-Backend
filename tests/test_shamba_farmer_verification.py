from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from bson import ObjectId

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.shamba import models, schemas, services


def valid_farmer_payload(**overrides):
    payload = {
        "farmer_name": "Amina Wanjiku",
        "phone": "+254700000001",
        "county": "Mombasa",
        "town": "Likoni",
        "farming_type": "mixed",
        "experience_years": 4,
        "primary_crops": ["maize", "beans"],
        "livestock": ["poultry"],
        "irrigation_available": False,
        "declaration": True,
        "privacy_consent": True,
    }
    payload.update(overrides)
    return payload


def test_farmer_schema_requires_core_identity_fields():
    with pytest.raises(ValueError, match="phone is required"):
        schemas.farmer_payload({
            "farmer_name": "Amina",
            "county": "Mombasa",
            "town": "Likoni",
            "farming_type": "mixed",
        })


def test_farmer_schema_normalizes_crops_and_boolean_values():
    payload = schemas.farmer_payload(valid_farmer_payload(
        primary_crops="Maize, beans, maize",
        irrigation_available="false",
    ))
    assert payload["primary_crops"] == ["Maize", "beans"]
    assert payload["irrigation_available"] is False


def test_farmer_schema_rejects_invalid_experience_and_boolean():
    with pytest.raises(ValueError, match="whole number"):
        schemas.farmer_payload(valid_farmer_payload(experience_years=2.5))
    with pytest.raises(ValueError, match="Boolean"):
        schemas.farmer_payload(valid_farmer_payload(irrigation_available="maybe"))


def test_farmer_review_requires_notes_for_negative_decisions():
    with pytest.raises(ValueError, match="Review notes are required"):
        schemas.farmer_review_payload({"decision": "rejected"})
    with pytest.raises(ValueError, match="Decision must be"):
        schemas.farmer_review_payload({"decision": "pending"})


def test_farmer_document_has_pending_server_owned_review_state():
    document = models.farmer_document("user-123", valid_farmer_payload())
    assert document["owner_user_id"] == "user-123"
    assert document["user_id"] == "user-123"
    assert document["profile_completed"] is True
    assert document["verification_status"] == "pending"
    assert document["verification_reviewer_user_id"] is None


def test_farm_document_starts_without_rights_verification():
    document = models.farm_document("user-123", {"name": "Demo Farm"})
    assert document["owner_user_id"] == "user-123"
    assert document["legal_verification_status"] == "not_submitted"
    assert document["publication_status"] == "pending_verification"


def test_create_farm_blocks_missing_or_unapproved_farmer(monkeypatch):
    class UnusedCollection:
        def insert_one(self, document):
            raise AssertionError("farm insert must not happen before approval")

    monkeypatch.setattr(services, "get_farmer", lambda user_id: {
        "id": "farmer-1",
        "verification_status": "pending",
    })
    monkeypatch.setattr(services, "_collection", lambda name: UnusedCollection())

    with pytest.raises(APIError) as error:
        services.create_farm("user-123", {"name": "Demo Farm"})

    assert error.value.status_code == 403
    assert error.value.code == "farmer_profile_verification_required"


def test_create_farm_works_only_for_approved_farmer(monkeypatch):
    farmer_id = str(ObjectId())
    farm_id = ObjectId()

    class FakeCollection:
        def __init__(self):
            self.documents = []

        def insert_one(self, document):
            saved = deepcopy(document)
            saved["_id"] = farm_id
            self.documents.append(saved)
            return SimpleNamespace(inserted_id=farm_id)

        def find_one(self, query, **kwargs):
            return next(
                (deepcopy(item) for item in self.documents if item.get("_id") == query.get("_id")),
                None,
            )

    collection = FakeCollection()
    monkeypatch.setattr(services, "get_farmer", lambda user_id: {
        "id": farmer_id,
        "verification_status": "approved",
    })
    monkeypatch.setattr(services, "_collection", lambda name: collection)
    monkeypatch.setattr(services, "log_action", lambda *args, **kwargs: None)

    farm = services.create_farm("user-123", {"name": "Demo Farm"})

    assert farm["name"] == "Demo Farm"
    assert farm["farmer_profile_id"] == farmer_id
    assert farm["legal_verification_status"] == "not_submitted"
    assert len(collection.documents) == 1


def test_farmer_draft_schema_allows_partial_data_without_consent_submission():
    payload = schemas.farmer_payload({
        "intent": "draft",
        "farmer_name": "Amina",
        "preferred_contact_method": "whatsapp",
    })
    assert payload["intent"] == "draft"
    assert payload["farmer_name"] == "Amina"
    assert payload["phone"] == ""
    assert payload["declaration"] is False


def test_farmer_submission_requires_declaration_and_privacy_consent():
    data = valid_farmer_payload()
    data["declaration"] = False
    with pytest.raises(ValueError, match="Confirm that the profile information is accurate"):
        schemas.farmer_payload(data)

    data = valid_farmer_payload()
    data["privacy_consent"] = False
    with pytest.raises(ValueError, match="Consent to use these details"):
        schemas.farmer_payload(data)


def test_gps_coordinates_require_consent_and_valid_pair():
    data = valid_farmer_payload(latitude=-4.05, longitude=39.67, gps_consent=False)
    with pytest.raises(ValueError, match="GPS consent"):
        schemas.farmer_payload(data)

    data = valid_farmer_payload(latitude=91, longitude=39.67, gps_consent=True)
    with pytest.raises(ValueError, match="latitude must be at least -90 and at most 90"):
        schemas.farmer_payload(data)


def test_verified_is_accepted_as_additive_review_decision_alias():
    payload = schemas.farmer_review_payload({"decision": "verified"})
    assert payload["decision"] == "approved"


def test_farmer_document_draft_does_not_start_in_review():
    document = models.farmer_document("user-123", {
        **valid_farmer_payload(),
        "intent": "draft",
    })
    assert document["verification_status"] == "draft"
    assert document["verification_submitted_at"] is None
