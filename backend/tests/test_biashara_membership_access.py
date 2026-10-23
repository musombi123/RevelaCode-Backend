from copy import deepcopy

import pytest
from bson import ObjectId

from backend.jumuiya.biashara import access, services
from backend.jumuiya.core.errors import APIError


class FakeCursor:
    def __init__(self, documents):
        self.documents = [deepcopy(doc) for doc in documents]

    def sort(self, *args, **kwargs):
        return self

    def limit(self, amount):
        self.documents = self.documents[:amount]
        return self

    def __iter__(self):
        return iter(self.documents)


def _matches(document, query):
    for key, expected in query.items():
        actual = document.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and actual not in expected["$in"]:
                return False
            continue
        if str(actual) != str(expected):
            return False
    return True


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = [deepcopy(doc) for doc in (documents or [])]

    def find_one(self, query, *args, **kwargs):
        for document in self.documents:
            if _matches(document, query):
                return deepcopy(document)
        return None

    def find(self, query, *args, **kwargs):
        return FakeCursor([doc for doc in self.documents if _matches(doc, query)])


@pytest.fixture
def access_db(monkeypatch):
    owned_id = ObjectId("64b000000000000000000101")
    member_id = ObjectId("64b000000000000000000102")
    owned = {"_id": owned_id, "owner_user_id": "member-user", "name": "My Shop",
             "status": "active", "verification_status": "verified"}
    shared = {"_id": member_id, "owner_user_id": "owner-user", "name": "Shared Store",
              "status": "active", "verification_status": "verified"}
    collections = {
        "jumuiya_businesses": FakeCollection([owned, shared]),
        "jumuiya_biashara_memberships": FakeCollection([{
            "_id": ObjectId("64b000000000000000000103"),
            "business_id": str(member_id), "user_id": "member-user",
            "role": "sales", "status": "active", "created_at": "2026-01-01",
        }]),
        "jumuiya_biashara_active_business": FakeCollection([{
            "user_id": "member-user", "business_id": str(member_id),
        }]),
    }
    monkeypatch.setattr(access, "collection", lambda name: collections[name])
    return {"collections": collections, "owned_id": owned_id, "member_id": member_id}


def test_member_can_resolve_business_with_active_membership(access_db):
    result = access.resolve_business_access("member-user", str(access_db["member_id"]))
    assert result["business"]["name"] == "Shared Store"
    assert result["role"] == "sales"
    assert result["is_owner"] is False


def test_pending_membership_does_not_grant_business_access(access_db):
    access_db["collections"]["jumuiya_biashara_memberships"].documents[0]["status"] = "pending"
    assert access.resolve_business_access("member-user", str(access_db["member_id"])) is None


def test_active_business_preference_switches_from_owned_to_member_business(access_db):
    result = access.resolve_business_access("member-user")
    assert result["business"]["name"] == "Shared Store"
    assert result["role"] == "sales"


def test_business_list_contains_only_owned_and_active_member_businesses(access_db):
    result = access.list_business_access("member-user")
    assert {item["name"] for item in result} == {"My Shop", "Shared Store"}
    roles = {item["name"]: item["access_role"] for item in result}
    assert roles["My Shop"] == "owner"
    assert roles["Shared Store"] == "sales"
    selected = {item["name"]: item["is_active"] for item in result}
    assert selected["Shared Store"] is True


def test_biashara_service_enforces_member_role(monkeypatch):
    business = {"id": "business-1", "status": "active", "verification_status": "verified"}
    monkeypatch.setattr(services, "resolve_business_access", lambda user_id: {
        "business": business, "role": "sales", "is_owner": False, "membership": {"role": "sales"}
    })
    with pytest.raises(APIError) as exc:
        services._require_business("sales-user", allowed_roles={"owner", "manager"})
    assert exc.value.code == "business_role_forbidden"
    assert services._require_business("sales-user", allowed_roles={"owner", "sales"}) == business
