import sys
import types
from copy import deepcopy
from datetime import datetime, timezone

import pytest

# Core database configuration pings Mongo on import; these tests use only an
# in-memory collection and must never connect to a live database.
_missing_module = object()
_original_db_module = sys.modules.get("backend.db", _missing_module)
_test_db_module = types.ModuleType("backend.db")
_test_db_module.get_db = lambda: None
sys.modules["backend.db"] = _test_db_module
try:
    from backend.jumuiya.biashara.sync import outbox
    from backend.jumuiya.biashara.automation import services as automation_services
finally:
    if _original_db_module is _missing_module:
        sys.modules.pop("backend.db", None)
    else:
        sys.modules["backend.db"] = _original_db_module

from backend.jumuiya.core.errors import APIError


def _matches(document, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(document, option) for option in expected):
                return False
            continue
        actual = document.get(key, _missing_module)
        if isinstance(expected, dict) and any(k.startswith("$") for k in expected):
            for operator, value in expected.items():
                if operator == "$exists":
                    if (actual is not _missing_module) != bool(value):
                        return False
                elif operator == "$in":
                    if actual not in value:
                        return False
                elif operator == "$lte":
                    if actual is _missing_module or actual > value:
                        return False
                elif operator == "$lt":
                    if actual is _missing_module or actual >= value:
                        return False
                elif operator == "$gt":
                    if actual is _missing_module or actual <= value:
                        return False
                else:
                    raise AssertionError(f"Unsupported fake query operator: {operator}")
        elif actual is _missing_module or actual != expected:
            return False
    return True


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, key, direction=1):
        def key_fn(doc):
            value = doc.get(key)
            return (value is None, value)
        self.documents.sort(key=key_fn, reverse=direction < 0)
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(deepcopy(self.documents))


class FakeCollection:
    def __init__(self):
        self.documents = []

    def find_one(self, query):
        for document in self.documents:
            if _matches(document, query):
                return deepcopy(document)
        return None

    def insert_one(self, document):
        saved = deepcopy(document)
        saved["_id"] = saved.get("_id") or f"doc-{len(self.documents) + 1}"
        if self.find_one({"business_id": saved.get("business_id"), "event_id": saved.get("event_id")}):
            from pymongo.errors import DuplicateKeyError
            raise DuplicateKeyError("duplicate event")
        self.documents.append(saved)
        return types.SimpleNamespace(inserted_id=saved["_id"])

    def find(self, query, projection=None):
        return FakeCursor([doc for doc in self.documents if _matches(doc, query)])

    def update_one(self, query, update):
        for document in self.documents:
            if not _matches(document, query):
                continue
            self._apply(document, update)
            return types.SimpleNamespace(matched_count=1, modified_count=1)
        return types.SimpleNamespace(matched_count=0, modified_count=0)

    def find_one_and_update(self, query, update, sort=None, return_document=None):
        candidates = [doc for doc in self.documents if _matches(doc, query)]
        if sort and candidates:
            for key, direction in reversed(sort):
                candidates.sort(key=lambda doc: doc.get(key), reverse=direction < 0)
        if not candidates:
            return None
        document = candidates[0]
        self._apply(document, update)
        return deepcopy(document)

    def _apply(self, document, update):
        for key, value in update.get("$set", {}).items():
            document[key] = deepcopy(value)
        for key, value in update.get("$inc", {}).items():
            document[key] = document.get(key, 0) + value
        for key in update.get("$addToSet", {}):
            value = update["$addToSet"][key]
            target = document.setdefault(key, [])
            if value not in target:
                target.append(deepcopy(value))
        for key in update.get("$unset", {}):
            document.pop(key, None)

    def count_documents(self, query):
        return sum(1 for document in self.documents if _matches(document, query))


@pytest.fixture
def outbox_db(monkeypatch):
    events = FakeCollection()
    monkeypatch.setattr(outbox, "collection", lambda name: events)
    monkeypatch.setattr(automation_services, "collection", lambda name: events)
    return events


def test_outbox_event_is_idempotent_and_payload_is_allowlisted(outbox_db):
    first = outbox.enqueue_outbox_event(
        "business-1",
        "order:order-1:created",
        "order.created",
        "order",
        "order-1",
        payload={"status": "pending", "total_amount_minor": 12345, "customer_name": "private name"},
    )
    second = outbox.enqueue_outbox_event(
        "business-1",
        "order:order-1:created",
        "order.created",
        "order",
        "order-1",
        payload={"status": "pending", "total_amount_minor": 12345, "customer_name": "different ignored value"},
    )

    assert first["event_id"] == second["event_id"]
    assert len(outbox_db.documents) == 1
    assert first["payload"] == {"status": "pending", "total_amount_minor": 12345}


def test_outbox_rejects_same_event_key_with_different_canonical_content(outbox_db):
    outbox.enqueue_outbox_event(
        "business-1", "order:order-2:created", "order.created", "order", "order-2",
        payload={"status": "pending"},
    )
    with pytest.raises(APIError) as raised:
        outbox.enqueue_outbox_event(
            "business-1", "order:order-2:created", "order.created", "order", "order-2",
            payload={"status": "confirmed"},
        )
    assert raised.value.code == "outbox_event_key_conflict"


def test_worker_must_hold_lease_to_acknowledge_event(outbox_db):
    outbox.enqueue_outbox_event(
        "business-1", "sale:sale-1:created", "sale.created", "sale", "sale-1",
        payload={"amount_minor": 2500, "currency": "KES"},
    )
    claimed = outbox.claim_due_events("worker-a", business_id="business-1", limit=1)
    assert len(claimed) == 1
    assert claimed[0]["state"] == "processing"
    assert claimed[0]["lease_token"]
    assert claimed[0]["attempt_count"] == 1

    with pytest.raises(APIError) as raised:
        outbox.mark_event_delivered(
            "business-1", claimed[0]["event_id"], "worker-a", "wrong-token"
        )
    assert raised.value.code == "outbox_lease_conflict"

    delivered = outbox.mark_event_delivered(
        "business-1", claimed[0]["event_id"], "worker-a", claimed[0]["lease_token"],
        provider_result_reference="provider-ack-1",
    )
    assert delivered["state"] == "delivered"
    assert delivered["provider_result_reference"] == "provider-ack-1"
    assert outbox.claim_due_events("worker-a", business_id="business-1", limit=1) == []


def test_retry_backoff_dead_letter_and_operator_replay(outbox_db):
    outbox.enqueue_outbox_event(
        "business-1", "order:order-3:confirmed", "order.status_changed", "order", "order-3",
        payload={"status": "confirmed"},
    )
    first = outbox.claim_due_events("worker-b", business_id="business-1", limit=1)[0]
    retried = outbox.mark_event_failed(
        "business-1", first["event_id"], "worker-b", first["lease_token"], "provider_timeout"
    )
    assert retried["state"] == "retry"
    assert retried["last_error_code"] == "provider_timeout"
    assert retried["next_attempt_at"] is not None

    # Simulate the retry timer expiring in the isolated fake collection.
    outbox_db.update_one(
        {"business_id": "business-1", "event_id": first["event_id"]},
        {"$set": {"next_attempt_at": datetime(2000, 1, 1, tzinfo=timezone.utc)}},
    )
    second = outbox.claim_due_events("worker-b", business_id="business-1", limit=1)[0]
    assert second["attempt_count"] == 2
    dead = outbox.mark_event_failed(
        "business-1", second["event_id"], "worker-b", second["lease_token"],
        "invalid_provider_config", retryable=False,
    )
    assert dead["state"] == "dead_letter"

    replayed = outbox.replay_dead_letter_event(
        "business-1", first["event_id"], actor_user_id="owner-1"
    )
    assert replayed["state"] == "pending"
    assert replayed["replay_count"] == 1
    assert replayed["attempt_count"] == 2


def test_manifest_repair_enqueues_once_from_source_record(outbox_db, monkeypatch):
    sources = FakeCollection()
    manifest = outbox.build_outbox_manifest(
        "order:order-4:created",
        "order.created",
        "order",
        "order-4",
        payload={"status": "pending"},
        actor_user_id="owner-1",
    )
    sources.documents.append({
        "_id": "source-1",
        "business_id": "business-1",
        "outbox_event_manifest": [manifest],
        "outbox_enqueued_event_keys": [],
    })

    original_collection = outbox.collection
    monkeypatch.setattr(
        outbox,
        "collection",
        lambda name: sources if name == "jumuiya_orders" else outbox_db,
    )
    # Repair sees the durable embedded intent and marks it acknowledged after
    # the idempotent queue insert. A second repair makes no duplicate.
    first = outbox.dispatch_manifest_for_record("jumuiya_orders", "business-1", "source-1")
    second = outbox.dispatch_manifest_for_record("jumuiya_orders", "business-1", "source-1")
    assert first["enqueued"] == 1
    assert second["enqueued"] == 0
    assert len(outbox_db.documents) == 1

def test_expired_worker_lease_is_reclaimed_and_old_worker_cannot_ack(outbox_db):
    outbox.enqueue_outbox_event(
        "business-1",
        "order:order-5:created",
        "order.created",
        "order",
        "order-5",
        payload={"status": "pending"},
    )
    first = outbox.claim_due_events("worker-old", business_id="business-1", limit=1)[0]
    outbox_db.update_one(
        {"business_id": "business-1", "event_id": first["event_id"]},
        {"$set": {"lease_expires_at": datetime(2000, 1, 1, tzinfo=timezone.utc)}},
    )

    second = outbox.claim_due_events("worker-new", business_id="business-1", limit=1)[0]
    assert second["lease_token"] != first["lease_token"]
    assert second["attempt_count"] == 2

    with pytest.raises(APIError) as raised:
        outbox.mark_event_delivered(
            "business-1", first["event_id"], "worker-old", first["lease_token"]
        )
    assert raised.value.code == "outbox_lease_conflict"

    done = outbox.mark_event_delivered(
        "business-1", second["event_id"], "worker-new", second["lease_token"]
    )
    assert done["state"] == "delivered"

