import sys
import types
from copy import deepcopy
from types import SimpleNamespace

import pytest
from bson import ObjectId

_missing_module = object()
_original_db_module = sys.modules.get("backend.db", _missing_module)
_test_db_module = types.ModuleType("backend.db")
_test_db_module.get_db = lambda: None
sys.modules["backend.db"] = _test_db_module
try:
    from backend.jumuiya.biashara.tenancy import service as tenancy
    from backend.jumuiya.biashara.tenancy import migration
finally:
    if _original_db_module is _missing_module:
        sys.modules.pop("backend.db", None)
    else:
        sys.modules["backend.db"] = _original_db_module

from backend.jumuiya.core.errors import APIError


def _get_path(document, path):
    value = document
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part, _missing_module)
        else:
            return _missing_module
    return value


def _matches(document, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(document, option) for option in expected):
                return False
            continue
        actual = _get_path(document, key)
        if isinstance(expected, dict) and any(operator.startswith("$") for operator in expected):
            for operator, value in expected.items():
                if operator == "$exists":
                    if (actual is not _missing_module) != bool(value):
                        return False
                elif operator == "$ne":
                    if actual is not _missing_module and actual == value:
                        return False
                elif operator == "$in":
                    if actual not in value:
                        return False
                else:
                    raise AssertionError("Unsupported fake query operator: " + operator)
        elif actual is _missing_module or actual != expected:
            return False
    return True


class Cursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, field, direction=1):
        def key_fn(document):
            value = _get_path(document, field)
            return value is _missing_module, None if value is _missing_module else value
        self.documents.sort(key=key_fn, reverse=direction < 0)
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(deepcopy(self.documents))


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = [deepcopy(doc) for doc in (documents or [])]

    def find_one(self, query):
        for document in self.documents:
            if _matches(document, query):
                return deepcopy(document)
        return None

    def find(self, query=None, projection=None):
        query = query or {}
        return Cursor([document for document in self.documents if _matches(document, query)])

    def insert_one(self, document):
        saved = deepcopy(document)
        saved["_id"] = saved.get("_id") or ObjectId()
        self.documents.append(saved)
        return SimpleNamespace(inserted_id=saved["_id"])

    def update_one(self, query, update):
        for document in self.documents:
            if _matches(document, query):
                for key, value in update.get("$set", {}).items():
                    document[key] = deepcopy(value)
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    def find_one_and_update(self, query, update, **kwargs):
        for document in self.documents:
            if _matches(document, query):
                for key, value in update.get("$set", {}).items():
                    document[key] = deepcopy(value)
                return deepcopy(document)
        return None


@pytest.fixture
def tenancy_db(monkeypatch):
    business_one = ObjectId("64b000000000000000000201")
    business_two = ObjectId("64b000000000000000000202")
    business_three = ObjectId("64b000000000000000000203")
    data = {
        "jumuiya_businesses": FakeCollection([
            {
                "_id": business_one,
                "owner_user_id": "owner-1",
                "name": "One Business",
                "slug": "one-business",
                "currency": "KES",
                "status": "active",
                "created_at": "2026-01-01",
            },
            {
                "_id": business_two,
                "owner_user_id": "owner-1",
                "name": "Second Business",
                "slug": "second-business",
                "currency": "KES",
                "status": "active",
                "created_at": "2026-02-01",
            },
            {
                "_id": business_three,
                "owner_user_id": "other-owner",
                "name": "Other Business",
                "slug": "other-business",
                "currency": "KES",
                "status": "active",
                "created_at": "2026-03-01",
            },
        ]),
        "jumuiya_business_memberships": FakeCollection(),
        "jumuiya_products": FakeCollection([
            {"_id": ObjectId("64b000000000000000000211"), "business_id": str(business_one), "name": "Product"},
            {"_id": ObjectId("64b000000000000000000212"), "name": "Orphan product"},
        ]),
        "jumuiya_customers": FakeCollection(),
        "jumuiya_orders": FakeCollection(),
        "jumuiya_sales": FakeCollection(),
        "jumuiya_expenses": FakeCollection(),
        "jumuiya_inventory_movements": FakeCollection(),
        "jumuiya_invoices": FakeCollection(),
        "jumuiya_payments": FakeCollection(),
    }
    monkeypatch.setattr(tenancy, "collection", lambda name: data[name])
    monkeypatch.setattr(migration, "collection", lambda name: data[name])
    monkeypatch.setattr(tenancy, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(tenancy, "_authoritative_user", lambda user_id: {
        "id": str(user_id),
        "verified": True,
        "email": str(user_id) + "@example.test",
    })
    return {
        "data": data,
        "business_one": business_one,
        "business_two": business_two,
        "business_three": business_three,
    }


def test_selected_business_is_resolved_by_membership_not_by_client_id_alone(tenancy_db):
    selected = str(tenancy_db["business_one"])
    owner_context = tenancy.get_business_context("owner-1", business_id=selected)

    assert owner_context["id"] == selected
    assert owner_context["membership_role"] == "owner"
    assert owner_context["permissions"] == ["*"]
    assert "owner_user_id" not in owner_context
    assert tenancy_db["data"][tenancy.MEMBERSHIPS_COLLECTION].find_one({
        "business_id": selected,
        "user_id": "owner-1",
        "status": "active",
    }) is not None

    with pytest.raises(APIError) as denied:
        tenancy.get_business_context("intruder", business_id=selected)
    assert denied.value.code == "business_access_denied"


def test_owner_with_multiple_businesses_must_explicitly_select_one(tenancy_db):
    with pytest.raises(APIError) as raised:
        tenancy.get_business_context("owner-1")
    assert raised.value.code == "business_selection_required"

    accessible = tenancy.list_accessible_businesses("owner-1")
    assert {item["id"] for item in accessible} == {
        str(tenancy_db["business_one"]),
        str(tenancy_db["business_two"]),
    }


def test_membership_role_limits_access_and_revocation_removes_it(tenancy_db):
    business_id = str(tenancy_db["business_one"])
    member = tenancy.add_member("owner-1", business_id, "cashier-1", "cashier")
    assert member["status"] == "active"
    assert "orders.create" in member["permissions"]
    assert "finance.manage" not in member["permissions"]

    context = tenancy.get_business_context("cashier-1", business_id=business_id)
    assert context["membership_role"] == "cashier"
    assert tenancy.require_permission("cashier-1", "orders.create", business_id=business_id)["id"] == business_id

    with pytest.raises(APIError) as denied:
        tenancy.require_permission("cashier-1", "finance.manage", business_id=business_id)
    assert denied.value.code == "business_permission_denied"

    revoked = tenancy.remove_member("owner-1", business_id, "cashier-1")
    assert revoked["status"] == "revoked"
    with pytest.raises(APIError) as no_access:
        tenancy.get_business_context("cashier-1", business_id=business_id)
    assert no_access.value.code == "business_access_denied"


def test_unverified_and_owner_identity_cannot_be_added_as_staff(tenancy_db, monkeypatch):
    monkeypatch.setattr(tenancy, "_authoritative_user", lambda user_id: {
        "id": str(user_id), "verified": False,
    })
    with pytest.raises(APIError) as unverified:
        tenancy.add_member("owner-1", str(tenancy_db["business_one"]), "unverified-user", "cashier")
    assert unverified.value.code == "member_user_unverified"

    monkeypatch.setattr(tenancy, "_authoritative_user", lambda user_id: {
        "id": str(user_id), "verified": True,
    })
    with pytest.raises(APIError) as owner_fixed:
        tenancy.add_member("owner-1", str(tenancy_db["business_one"]), "owner-1", "cashier")
    assert owner_fixed.value.code == "owner_membership_fixed"


def test_owner_membership_migration_supports_dry_run_apply_and_orphan_reporting(tenancy_db):
    dry = migration.run_owner_membership_migration(dry_run=True, limit=50)
    assert dry["dry_run"] is True
    assert dry["owner_memberships_would_create"] == 3
    assert dry["owner_memberships_created"] == 0
    assert len(tenancy_db["data"][tenancy.MEMBERSHIPS_COLLECTION].documents) == 0
    assert dry["child_records"]["jumuiya_products"]["missing_business_id"] == 1

    applied = migration.run_owner_membership_migration(dry_run=False, limit=50)
    assert applied["owner_memberships_created"] == 3
    assert len(tenancy_db["data"][tenancy.MEMBERSHIPS_COLLECTION].documents) == 3

    repeated = migration.run_owner_membership_migration(dry_run=False, limit=50)
    assert repeated["owner_memberships_created"] == 0
    assert repeated["owner_memberships_existing"] == 3
    assert len(tenancy_db["data"][tenancy.MEMBERSHIPS_COLLECTION].documents) == 3

def test_owner_membership_migration_preserves_prior_state_for_reviewable_rollback(tenancy_db):
    business_id = str(tenancy_db["business_one"])
    membership = {
        "_id": ObjectId("64b000000000000000000221"),
        "business_id": business_id,
        "user_id": "owner-1",
        "role": "cashier",
        "status": "active",
        "permissions_snapshot": ["business.view"],
        "source": "team_membership_action_v1",
        "created_at": "2026-01-05",
        "joined_at": "2026-01-05",
        "revoked_at": None,
    }
    tenancy_db["data"][tenancy.MEMBERSHIPS_COLLECTION].documents.append(membership)

    dry = migration.run_owner_membership_migration(dry_run=True, limit=50)
    assert dry["owner_memberships_repaired"] == 1
    assert dry["owner_memberships_would_create"] == 2
    assert membership["role"] == "cashier"

    applied = migration.run_owner_membership_migration(dry_run=False, limit=50)
    assert applied["owner_memberships_repaired"] == 1
    saved = tenancy_db["data"][tenancy.MEMBERSHIPS_COLLECTION].find_one({
        "business_id": business_id,
        "user_id": "owner-1",
    })
    assert saved["role"] == "owner"
    assert saved["source"] == migration.OWNER_MEMBERSHIP_SOURCE
    assert saved["migration_previous_state"]["role"] == "cashier"
    assert saved["migration_previous_state"]["source"] == "team_membership_action_v1"

    rollback = migration.plan_owner_membership_rollback(limit=50)
    candidate = next(row for row in rollback["rollback_candidates"] if row["business_id"] == business_id)
    assert candidate["action"] == "restore_previous_state"
    assert rollback["automatic_rollback_performed"] is False


def test_migration_rollback_plan_skips_malformed_business_ids_without_writes(tenancy_db):
    migration.run_owner_membership_migration(dry_run=False, limit=50)
    malformed = {
        "_id": ObjectId("64b000000000000000000222"),
        "business_id": "zzzzzzzzzzzzzzzzzzzzzzzz",
        "user_id": "owner-unknown",
        "role": "owner",
        "status": "active",
        "source": migration.OWNER_MEMBERSHIP_SOURCE,
        "created_at": "2026-10-15",
    }
    memberships = tenancy_db["data"][tenancy.MEMBERSHIPS_COLLECTION]
    memberships.documents.append(malformed)
    before = deepcopy(memberships.documents)

    rollback = migration.plan_owner_membership_rollback(limit=50)

    assert rollback["automatic_rollback_performed"] is False
    assert rollback["scan_truncated"] is False
    assert any(
        row["reason"] == "owner_relationship_changed_or_business_missing"
        and row["business_id"] == "zzzzzzzzzzzzzzzzzzzzzzzz"
        for row in rollback["skipped"]
    )
    assert memberships.documents == before


def test_application_bootstrap_membership_is_not_mislabelled_for_rollback(tenancy_db):
    business = tenancy_db["data"]["jumuiya_businesses"].find_one({
        "_id": tenancy_db["business_one"],
    })
    tenancy.ensure_owner_membership(business, actor_user_id="owner-1")

    membership = tenancy_db["data"][tenancy.MEMBERSHIPS_COLLECTION].find_one({
        "business_id": str(tenancy_db["business_one"]),
        "user_id": "owner-1",
    })
    assert membership["source"] == "owner_access_bootstrap_v1"

    rollback = migration.plan_owner_membership_rollback(limit=50)
    assert rollback["rollback_candidates"] == []

def test_manager_cannot_change_or_revoke_another_manager(tenancy_db, monkeypatch):
    business_id = str(tenancy_db["business_one"])
    tenancy.add_member("owner-1", business_id, "manager-1", "manager")

    def permission_context(user_id, permission, business_id=None):
        return {
            "id": business_id or str(tenancy_db["business_one"]),
            "membership_role": "manager" if user_id == "manager-1" else "owner",
            "permissions": ["*"],
        }

    monkeypatch.setattr(tenancy, "require_permission", permission_context)

    with pytest.raises(APIError) as modify:
        tenancy.add_member("manager-1", business_id, "manager-1", "cashier")
    assert modify.value.code == "business_permission_denied"

    with pytest.raises(APIError) as revoke:
        tenancy.remove_member("manager-1", business_id, "manager-1")
    assert revoke.value.code == "business_permission_denied"

    # The business owner can change a manager's role using the same service.
    changed = tenancy.add_member("owner-1", business_id, "manager-1", "cashier")
    assert changed["role"] == "cashier"

