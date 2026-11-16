from __future__ import annotations

from types import SimpleNamespace

from backend.jumuiya.core.health import database_health


class FakeCollection:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.calls = []

    def find_one(self, query, projection):
        self.calls.append((query, projection))
        if self.should_fail:
            raise RuntimeError("private database detail")
        return None


class FakeDatabase:
    def __init__(self, *, ping_fails=False, read_fails=False):
        self.ping_fails = ping_fails
        self.users = FakeCollection(read_fails)
        self.commands = []

    def command(self, name):
        self.commands.append(name)
        if self.ping_fails:
            raise RuntimeError("private database detail")
        return {"ok": 1}

    def __getitem__(self, name):
        assert name == "users"
        return self.users


def install_fake_database(monkeypatch, database):
    monkeypatch.setitem(
        __import__("sys").modules,
        "backend.db",
        SimpleNamespace(get_db=lambda: database),
    )


def test_database_health_confirms_ping_and_read_access(monkeypatch):
    database = FakeDatabase()
    install_fake_database(monkeypatch, database)

    result = database_health()

    assert result["status"] == "online"
    assert result["mongo_connected"] is True
    assert result["evidence"] == "mongodb_ping_and_read_access_confirmed"
    assert database.commands == ["ping"]
    assert database.users.calls == [({}, {"_id": 1})]
    assert result["checked_at"]


def test_database_health_reports_ping_failure_without_leaking_exception(monkeypatch):
    install_fake_database(monkeypatch, FakeDatabase(ping_fails=True))

    result = database_health()

    assert result["status"] == "degraded"
    assert result["mongo_connected"] is False
    assert result["evidence"] == "mongodb_ping_or_read_access_failed"
    assert "private database detail" not in str(result)


def test_database_health_reports_read_permission_failure(monkeypatch):
    install_fake_database(monkeypatch, FakeDatabase(read_fails=True))

    result = database_health()

    assert result["status"] == "degraded"
    assert result["mongo_connected"] is False
    assert "private database detail" not in str(result)