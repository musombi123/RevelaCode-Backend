from unittest.mock import Mock

import pytest

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.marketplace import services


def test_shamba_listing_creation_requires_verified_farmer_before_farm_lookup(monkeypatch):
    class FakeCollection:
        def __init__(self, name):
            self.name = name
            self.calls = []

        def find_one(self, query, **kwargs):
            self.calls.append((query, kwargs))
            if self.name == "jumuiya_farmers":
                return None
            raise AssertionError("farm lookup must not happen before farmer approval")

        def insert_one(self, document):
            raise AssertionError("listing must not be inserted before farmer approval")

    seen = []
    def fake_collection(name):
        seen.append(name)
        return FakeCollection(name)

    monkeypatch.setattr(services, "collection", fake_collection)

    with pytest.raises(APIError) as error:
        services.create_listing("user-123", {
            "hub": "shamba",
            "title": "Maize",
            "price": 80,
            "quantity_available": 20,
        })

    assert error.value.status_code == 403
    assert error.value.code == "farmer_verification_required"
    assert seen == ["jumuiya_farmers"]


def test_non_shamba_listing_branch_keeps_existing_create_contract(monkeypatch):
    listing_collection = Mock()
    listing_collection.insert_one.return_value.inserted_id = "listing-id"
    monkeypatch.setattr(services, "collection", lambda name: listing_collection)
    monkeypatch.setattr(services, "listing_document", lambda user_id, data: {
        "seller_user_id": str(user_id),
        "title": data["title"],
        "hub": data["hub"],
        "status": "active",
    })
    monkeypatch.setattr(services, "log_action", lambda *args, **kwargs: None)

    result = services.create_listing("user-123", {
        "hub": "community",
        "title": "Community item",
    })

    assert result["title"] == "Community item"
    assert result["hub"] == "community"
