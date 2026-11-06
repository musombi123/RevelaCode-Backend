"""Regression tests for platform-wide IP blocking and defensive auto-response."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend import security_ip_guard as guard


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, key, direction=-1):
        self.rows.sort(
            key=lambda row: row.get(key) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=direction < 0,
        )
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def __iter__(self):
        return iter(self.rows)


class FakeCollection:
    def __init__(self):
        self.rows = []
        self.next_id = 1

    def create_index(self, *args, **kwargs):
        return "index"

    def _matches(self, row, query):
        for key, expected in (query or {}).items():
            value = row.get(key)
            if isinstance(expected, dict) and "$gte" in expected:
                if value is None or value < expected["$gte"]:
                    return False
            elif value != expected:
                return False
        return True

    def insert_one(self, document):
        row = {"_id": str(self.next_id), **dict(document)}
        self.next_id += 1
        self.rows.append(row)
        return type("InsertResult", (), {"inserted_id": row["_id"]})()

    def find_one(self, query=None):
        return next((row.copy() for row in self.rows if self._matches(row, query or {})), None)

    def find(self, query=None):
        return FakeCursor([row.copy() for row in self.rows if self._matches(row, query or {})])

    def count_documents(self, query=None):
        return sum(1 for row in self.rows if self._matches(row, query or {}))

    def update_one(self, query, update, upsert=False):
        for row in self.rows:
            if self._matches(row, query):
                row.update(update.get("$set", {}))
                return type("UpdateResult", (), {"modified_count": 1, "upserted_id": None})()
        if upsert:
            row = {"_id": str(self.next_id), **dict(query), **update.get("$set", {})}
            self.next_id += 1
            self.rows.append(row)
            return type("UpdateResult", (), {"modified_count": 0, "upserted_id": row["_id"]})()
        return type("UpdateResult", (), {"modified_count": 0, "upserted_id": None})()

    def update_many(self, query, update):
        count = 0
        for row in self.rows:
            if self._matches(row, query):
                row.update(update.get("$set", {}))
                count += 1
        return type("UpdateResult", (), {"modified_count": count})()


class FakeDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, FakeCollection())


@pytest.fixture
def database(monkeypatch):
    db = FakeDatabase()
    monkeypatch.setattr(guard, "get_db", lambda: db)
    monkeypatch.setenv("SCI_CORE_IP_ALLOWLIST", "")
    return db


def test_client_ip_uses_cloudflare_header_not_spoofable_forwarding_headers():
    class Request:
        headers = {
            "CF-Connecting-IP": "1.1.1.1",
            "X-Forwarded-For": "8.8.8.8",
        }

    assert guard.client_ip_from_request(Request()) == "1.1.1.1"

    class NoCloudflareHeader:
        headers = {"X-Forwarded-For": "1.1.1.1"}

    assert guard.client_ip_from_request(NoCloudflareHeader()) is None


def test_manual_block_is_persistent_and_audited(database):
    result = guard.block_ip(
        "1.1.1.1",
        actor="admin-1",
        reason="Repeated suspicious application requests",
        duration_minutes=30,
        current_ip="8.8.8.8",
    )
    assert result["status"] == "active"
    assert guard.ip_is_blocked("1.1.1.1")["ip"] == "1.1.1.1"
    assert database["security_ip_events"].count_documents({"action": "blocked"}) == 1


def test_manual_block_rejects_private_ranges_and_admin_self_block(database):
    for ip in ("10.0.0.1", "127.0.0.1", "192.0.2.1", "1.1.1.0/24", "invalid"):
        with pytest.raises(ValueError):
            guard.block_ip(
                ip,
                actor="admin-1",
                reason="Repeated suspicious application requests",
                duration_minutes=30,
                current_ip="8.8.8.8",
            )

    with pytest.raises(ValueError, match="cannot block the IP address"):
        guard.block_ip(
            "1.1.1.1",
            actor="admin-1",
            reason="Repeated suspicious application requests",
            duration_minutes=30,
            current_ip="1.1.1.1",
        )


def test_allowlist_protects_administrator_addresses(database, monkeypatch):
    monkeypatch.setenv("SCI_CORE_IP_ALLOWLIST", "8.8.8.0/24")
    with pytest.raises(ValueError, match="administrator IP allowlist"):
        guard.block_ip(
            "8.8.8.8",
            actor="admin-1",
            reason="Repeated suspicious application requests",
            duration_minutes=30,
            current_ip="9.9.9.9",
        )


def test_unblock_releases_enforcement_and_audits_event(database):
    guard.block_ip(
        "1.1.1.1",
        actor="admin-1",
        reason="Repeated suspicious application requests",
        duration_minutes=30,
        current_ip="8.8.8.8",
    )
    result = guard.unblock_ip(
        "1.1.1.1",
        actor="admin-1",
        reason="Administrator verified and released this source.",
    )
    assert result["records_released"] == 1
    assert guard.ip_is_blocked("1.1.1.1") is None
    assert database["security_ip_events"].count_documents({}) == 2


def test_expired_block_is_deactivated_before_enforcement(database):
    guard.block_ip(
        "1.1.1.1",
        actor="admin-1",
        reason="Repeated suspicious application requests",
        duration_minutes=30,
        current_ip="8.8.8.8",
    )
    row = database["security_ip_blocks"].rows[0]
    row["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert guard.ip_is_blocked("1.1.1.1") is None
    assert row["active"] is False


def test_failed_login_auto_block_requires_explicit_admin_allowlist(database, monkeypatch):
    monkeypatch.setattr(guard, "AUTO_BLOCK_THRESHOLD", 2)
    assert guard.record_failed_login("1.1.1.1", "/api/login") is None
    assert database["security_auth_failures"].count_documents({}) == 0


def test_repeated_failed_login_auto_blocks_non_allowlisted_source(database, monkeypatch):
    monkeypatch.setenv("SCI_CORE_IP_ALLOWLIST", "8.8.8.8/32")
    monkeypatch.setattr(guard, "AUTO_BLOCK_THRESHOLD", 2)
    guard.record_failed_login("1.1.1.1", "/api/login")
    guard.record_failed_login("1.1.1.1", "/api/auth/login")
    block = guard.ip_is_blocked("1.1.1.1")
    assert block is not None
    assert block["source"] == "auto_bruteforce"
    assert database["security_auth_failures"].count_documents({"ip": "1.1.1.1"}) == 2


def test_login_failure_handler_ignores_non_login_endpoints(database, monkeypatch):
    monkeypatch.setenv("SCI_CORE_IP_ALLOWLIST", "8.8.8.8/32")
    guard.record_failed_login("1.1.1.1", "/api/admin/security/ip-blocks")
    assert database["security_auth_failures"].count_documents({}) == 0
