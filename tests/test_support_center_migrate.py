"""Regression tests for idempotent Super Admin bootstrap session invalidation."""
import runpy
import sys
import types
from pathlib import Path

from bson import ObjectId


OWNER_ID = "6a3eba8277b5d149effbafc0"


class FakeUsers:
    def __init__(self, owner):
        self.owner = dict(owner)
        self.updates = 0

    def find_one(self, query):
        requested = query.get("_id")
        if requested == self.owner.get("_id"):
            return dict(self.owner)
        return None

    def update_one(self, query, update):
        assert query.get("_id") == self.owner.get("_id")
        self.owner.update(update.get("$set") or {})
        self.updates += 1


class FakeDatabase:
    def __init__(self, users):
        self.collections = {"users": users}

    def __getitem__(self, name):
        return self.collections[name]


def test_super_admin_bootstrap_invalidates_sessions_only_once(monkeypatch):
    owner = {
        "_id": ObjectId(OWNER_ID),
        "role": "user",
        "roles": ["user"],
        "token_version": 4,
    }
    users = FakeUsers(owner)
    database = FakeDatabase(users)
    state = {"indexes_ready": 0}

    db_module = types.ModuleType("backend.db")
    db_module.get_db = lambda: database
    support_module = types.ModuleType("backend.support_center")
    support_module.ensure_indexes = lambda: state.__setitem__("indexes_ready", state["indexes_ready"] + 1)
    config_module = types.ModuleType("backend.support_config")
    config_module.SUPER_ADMIN_USER_ID = OWNER_ID

    monkeypatch.setitem(sys.modules, "backend.db", db_module)
    monkeypatch.setitem(sys.modules, "backend.support_center", support_module)
    monkeypatch.setitem(sys.modules, "backend.support_config", config_module)

    migration_path = Path(__file__).resolve().parents[1] / "backend" / "support_center_migrate.py"
    namespace = runpy.run_path(str(migration_path), run_name="support_center_migrate_test")
    namespace["main"]()

    assert users.owner["token_version"] == 5
    assert users.owner["role"] == "super_admin"
    assert "super_admin" in users.owner["roles"]
    first_marker = users.owner["super_admin_seeded_at"]

    # Re-running the migration must still repair/ensure indexes but must not
    # invalidate the newly issued token version again.
    namespace["main"]()

    assert users.owner["token_version"] == 5
    assert users.owner["super_admin_seeded_at"] == first_marker
    assert users.updates == 2
    assert state["indexes_ready"] == 2
