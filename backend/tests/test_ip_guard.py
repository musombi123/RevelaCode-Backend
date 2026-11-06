"""Regression tests for persistent IP blocking and safe administrator controls."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from flask import Flask

from backend.security import ip_guard


class FakeCursor(list):
    def sort(self, key, direction=-1):
        self.sort_key = key
        self.reverse = direction < 0
        super().sort(key=lambda row: row.get(key), reverse=self.reverse)
        return self

    def limit(self, count):
        del self[max(0, int(count)) :]
        return self


class FakeCollection:
    def __init__(self):
        self.rows = []

    def create_index(self, *_args, **_kwargs):
        return "fake-index"

    def insert_one(self, document):
        row = dict(document)
        row.setdefault("_id", str(len(self.rows) + 1))
        self.rows.append(row)
        return SimpleNamespace(inserted_id=row["_id"])

    @staticmethod
    def _match(row, query):
        for key, expected in (query or {}).items():
            actual = row.get(key)
            if isinstance(expected, dict):
                if "$gte" in expected and not (actual is not None and actual >= expected["$gte"]):
                    return False
                if "$gt" in expected and not (actual is not None and actual > expected["$gt"]):
                    return False
            elif actual != expected:
                return False
        return True

    def find_one(self, query=None, sort=None):
        matches = [row for row in self.rows if self._match(row, query)]
        if sort and matches:
            key, direction = sort[0]
            matches.sort(key=lambda row: row.get(key), reverse=direction < 0)
        return matches[0] if matches else None

    def find(self, query=None):
        return FakeCursor([row for row in self.rows if self._match(row, query)])

    def count_documents(self, query=None):
        return sum(1 for row in self.rows if self._match(row, query))

    def update_one(self, query, update, upsert=False):
        row = self.find_one(query)
        if row:
            row.update(update.get("$set", {}))
            return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            row = dict(query)
            row.update(update.get("$set", {}))
            self.insert_one(row)
            return SimpleNamespace(matched_count=0, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    def update_many(self, query, update):
        count = 0
        for row in self.rows:
            if self._match(row, query):
                row.update(update.get("$set", {}))
                count += 1
        return SimpleNamespace(matched_count=count, modified_count=count)


class FakeDatabase(dict):
    def __missing__(self, name):
        value = FakeCollection()
        self[name] = value
        return value

    def command(self, *_args, **_kwargs):
        return {"ok": 1}


@pytest.fixture
def fake_store(monkeypatch):
    database = FakeDatabase()
    monkeypatch.setattr(ip_guard, "_collections", lambda: (database, object()))
    monkeypatch.setattr(ip_guard, "_INDEX_READY", True)
    return database


def test_manual_block_is_persisted_and_enforced(fake_store):
    record = ip_guard.block_ip(
        "8.8.8.8",
        actor="admin-1",
        reason="Repeated credential abuse from this source",
        duration_minutes=60,
    )
    assert record["status"] == "blocked"
    assert ip_guard.find_active_block("8.8.8.8")["active"] is True

    app = Flask(__name__)
    app.add_url_rule("/api/example", view_func=lambda: "not reached")

    with app.test_request_context(
        "/api/example",
        environ_base={"REMOTE_ADDR": "8.8.8.8"},
    ):
        response = ip_guard.enforce_ip_block()

    assert response.status_code == 403
    assert response.get_json()["code"] == "ip_blocked"


def test_manual_block_cannot_block_current_admin_or_non_public_ip(fake_store):
    with pytest.raises(ValueError, match="cannot block"):
        ip_guard.block_ip(
            "8.8.8.8",
            actor="admin-1",
            reason="Repeated credential abuse from source",
            duration_minutes=60,
            protect_current_ip="8.8.8.8",
        )
    with pytest.raises(ValueError, match="public"):
        ip_guard.block_ip(
            "127.0.0.1",
            actor="admin-1",
            reason="Test local address",
            duration_minutes=60,
        )


def test_allowlisted_ip_is_never_blocked(fake_store, monkeypatch):
    monkeypatch.setattr(ip_guard, "_allowlisted", lambda ip: ip == "8.8.8.8")
    with pytest.raises(ValueError, match="allowlist"):
        ip_guard.block_ip(
            "8.8.8.8",
            actor="admin-1",
            reason="Repeated credential abuse from source",
            duration_minutes=60,
        )
    assert ip_guard.find_active_block("8.8.8.8") is None


def test_repeated_failed_logins_trigger_temporary_block(fake_store, monkeypatch):
    monkeypatch.setattr(ip_guard, "_allowlisted", lambda _ip: False)
    result = None
    for _ in range(ip_guard.AUTH_FAILURE_THRESHOLD):
        result = ip_guard.record_failed_authentication("8.8.4.4", "/api/auth/login", 401)
    assert result is not None
    assert result["source"] == "auto_bruteforce"
    assert result["duration_minutes"] == ip_guard.AUTO_BLOCK_MINUTES
    assert ip_guard.find_active_block("8.8.4.4") is not None


def test_non_login_failures_do_not_trigger_automatic_block(fake_store):
    for _ in range(ip_guard.AUTH_FAILURE_THRESHOLD + 2):
        result = ip_guard.record_failed_authentication("1.1.1.1", "/api/auth/me", 401)
    assert result is None
    assert ip_guard.find_active_block("1.1.1.1") is None


def test_unblock_releases_only_the_selected_ip(fake_store):
    for ip in ("8.8.8.8", "8.8.4.4"):
        ip_guard.block_ip(
            ip,
            actor="admin-1",
            reason="Repeated credential abuse from source",
            duration_minutes=60,
        )
    result = ip_guard.unblock_ip("8.8.8.8", actor="admin-1")
    assert result["records_released"] == 1
    assert ip_guard.find_active_block("8.8.8.8") is None
    assert ip_guard.find_active_block("8.8.4.4") is not None


def test_admin_api_requires_current_admin_and_exposes_persistent_blocks(fake_store, monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(ip_guard.security_bp)
    monkeypatch.setattr(ip_guard, "_require_current_platform_admin", lambda: ("admin-1", None))
    client = app.test_client()

    response = client.post(
        "/api/admin/security/ip-blocks",
        json={
            "ip": "8.8.8.8",
            "reason": "Repeated credential abuse from source",
            "duration_minutes": 120,
        },
    )
    assert response.status_code == 201
    assert response.get_json()["block"]["ip"] == "8.8.8.8"

    listed = client.get("/api/admin/security/ip-blocks")
    assert listed.status_code == 200
    assert listed.get_json()["protection"]["persistent"] is True
    assert listed.get_json()["blocks"][0]["ip"] == "8.8.8.8"

    released = client.post(
        "/api/admin/security/ip-blocks/unblock",
        json={"ip": "8.8.8.8"},
    )
    assert released.status_code == 200
    assert released.get_json()["result"]["status"] == "unblocked"


def test_admin_api_does_not_authorize_from_client_supplied_role(fake_store, monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(ip_guard.security_bp)
    monkeypatch.setattr(
        ip_guard,
        "_require_current_platform_admin",
        lambda: (None, (app.response_class("forbidden", status=403), 403)),
    )
    response = app.test_client().get("/api/admin/security/ip-blocks")
    assert response.status_code == 403


def test_raw_forwarded_for_header_is_not_trusted_by_the_ip_guard():
    app = Flask(__name__)
    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "8.8.8.8"},
        headers={"X-Forwarded-For": "1.1.1.1"},
    ):
        # Only a trusted ProxyFix deployment may rewrite REMOTE_ADDR before
        # this helper runs; the guard never parses arbitrary XFF itself.
        assert ip_guard.current_client_ip() == "8.8.8.8"
