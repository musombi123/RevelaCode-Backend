import sys
import types
from copy import deepcopy
from types import SimpleNamespace

import pytest
from bson import ObjectId

# This suite uses only in-memory collections and must not initialize a live DB.
_missing_module = object()
_original_db_module = sys.modules.get("backend.db", _missing_module)
_test_db_module = types.ModuleType("backend.db")
_test_db_module.get_db = lambda: None
sys.modules["backend.db"] = _test_db_module
try:
    from backend.jumuiya.biashara.automation import services as automation
    from backend.jumuiya.biashara.automation import worker as automation_worker
    from backend.jumuiya.biashara import services as biashara
finally:
    if _original_db_module is _missing_module:
        sys.modules.pop("backend.db", None)
    else:
        sys.modules["backend.db"] = _original_db_module

from backend.jumuiya.core.errors import APIError


_missing = object()


def _get_path(document, path):
    value = document
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part, _missing)
        else:
            return _missing
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
                    if (actual is not _missing) != bool(value):
                        return False
                elif operator == "$in":
                    if actual not in value:
                        return False
                elif operator == "$ne":
                    if actual is not _missing and actual == value:
                        return False
                elif operator == "$lte":
                    if actual is _missing or actual > value:
                        return False
                elif operator == "$gt":
                    if actual is _missing or actual <= value:
                        return False
                else:
                    raise AssertionError("Unsupported fake query operator: " + operator)
        elif actual is _missing or actual != expected:
            return False
    return True


def _set_path(document, path, value):
    parts = path.split(".")
    target = document
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = deepcopy(value)


class Cursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, field, direction=1):
        def key_fn(document):
            value = _get_path(document, field)
            return value is _missing, None if value is _missing else value
        self.documents.sort(key=key_fn, reverse=direction < 0)
        return self

    def limit(self, amount):
        self.documents = self.documents[:amount]
        return self

    def __iter__(self):
        return iter(deepcopy(self.documents))


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = [deepcopy(document) for document in (documents or [])]

    def find_one(self, query):
        for document in self.documents:
            if _matches(document, query):
                return deepcopy(document)
        return None

    def find(self, query, projection=None):
        return Cursor([document for document in self.documents if _matches(document, query)])

    def insert_one(self, document):
        saved = deepcopy(document)
        saved["_id"] = saved.get("_id") or ObjectId()
        if saved.get("task_key") and self.find_one({
            "business_id": saved.get("business_id"),
            "task_key": saved["task_key"],
        }):
            from pymongo.errors import DuplicateKeyError
            raise DuplicateKeyError("duplicate task key")
        if saved.get("run_key") and self.find_one({
            "business_id": saved.get("business_id"),
            "run_key": saved["run_key"],
        }):
            from pymongo.errors import DuplicateKeyError
            raise DuplicateKeyError("duplicate run key")
        self.documents.append(saved)
        return SimpleNamespace(inserted_id=saved["_id"])

    def update_one(self, query, update):
        for document in self.documents:
            if _matches(document, query):
                for key, value in update.get("$set", {}).items():
                    _set_path(document, key, value)
                for key, value in update.get("$inc", {}).items():
                    document[key] = document.get(key, 0) + value
                for key, value in update.get("$addToSet", {}).items():
                    values = document.setdefault(key, [])
                    if value not in values:
                        values.append(deepcopy(value))
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    def find_one_and_update(self, query, update, **kwargs):
        for document in self.documents:
            if _matches(document, query):
                for key, value in update.get("$set", {}).items():
                    _set_path(document, key, value)
                for key, value in update.get("$inc", {}).items():
                    document[key] = document.get(key, 0) + value
                return deepcopy(document)
        return None


@pytest.fixture
def automation_db(monkeypatch):
    product_id = ObjectId("64b000000000000000000101")
    data = {
        automation.RULES_COLLECTION: FakeCollection(),
        automation.RUNS_COLLECTION: FakeCollection(),
        automation.TASKS_COLLECTION: FakeCollection(),
        "jumuiya_products": FakeCollection([{
            "_id": product_id,
            "business_id": "business-1",
            "name": "Face cream",
            "sku": "FC-01",
            "stock_quantity": 5,
            "reserved_quantity": 4,
            "status": "active",
        }]),
        "jumuiya_payments": FakeCollection(),
        "jumuiya_invoices": FakeCollection(),
        "jumuiya_outbox_events": FakeCollection(),
    }
    monkeypatch.setattr(automation, "collection", lambda name: data[name])
    monkeypatch.setattr(automation_worker, "collection", lambda name: data[name])
    monkeypatch.setattr(automation, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        automation,
        "require_permission",
        lambda user_id, permission, business_id=None: {
            "id": business_id or ("business-1" if user_id != "other-owner" else "business-2"),
            "permissions": ["*"],
        },
    )
    monkeypatch.setattr(
        automation,
        "get_business_context",
        lambda user_id, business_id=None: {
            "id": business_id or ("business-1" if user_id != "other-owner" else "business-2"),
            "permissions": ["*"],
        },
    )
    monkeypatch.setattr(biashara, "_require_business", lambda user_id: {
        "id": "business-1" if user_id != "other-owner" else "business-2",
        "currency": "KES",
    })
    return {"data": data, "product_id": product_id}


def test_order_event_creates_one_durable_follow_up_task_on_duplicate_delivery(automation_db):
    rule = automation.create_rule("owner-1", {
        "name": "Follow up on new orders",
        "trigger_event": "order.created",
        "action_type": "create_fulfillment_task",
        "conditions": {"minimum_amount_minor": 1000},
        "enabled": True,
    })
    event = {
        "business_id": "business-1",
        "event_id": "stable-order-event-1",
        "event_type": "order.created",
        "entity_type": "order",
        "entity_id": "order-00000001",
        "payload": {
            "status": "pending",
            "source_channel": "pos",
            "total_amount_minor": 2500,
            "currency": "KES",
        },
    }

    first = automation.dispatch_event_automations(event)
    second = automation.dispatch_event_automations(event)

    assert first["matched_rules"] == 1
    assert first["created_runs"] == 1
    assert first["created_tasks"] == 1
    assert second["created_runs"] == 0
    assert second["created_tasks"] == 0
    tasks = automation.list_tasks("owner-1")
    assert len(tasks) == 1
    assert tasks[0]["status"] == "open"
    assert tasks[0]["details"]["order_id"] == "order-00000001"
    assert tasks[0]["approval_required"] is False
    runs = automation.list_runs("owner-1")
    assert len(runs) == 1
    assert runs[0]["status"] == "created"
    assert runs[0]["rule_id"] == rule["id"]


def test_reorder_suggestion_requires_approval_and_never_creates_purchase_order(automation_db):
    automation.create_rule("owner-1", {
        "name": "Suggest reorder when stock is low",
        "trigger_event": "product.inventory_adjusted",
        "action_type": "create_reorder_suggestion",
        "conditions": {
            "available_quantity_lte": 2,
            "target_stock_quantity": 10,
        },
        "enabled": True,
    })
    product_id = str(automation_db["product_id"])
    event = {
        "business_id": "business-1",
        "event_id": "stable-stock-event-1",
        "event_type": "product.inventory_adjusted",
        "entity_type": "product",
        "entity_id": product_id,
        "payload": {"product_id": product_id, "stock_quantity": 5, "reserved_quantity": 4},
    }

    result = automation.dispatch_event_automations(event)
    task = automation.list_tasks("owner-1")[0]

    assert result["created_tasks"] == 1
    assert task["task_type"] == "reorder_suggestion"
    assert task["status"] == "pending_approval"
    assert task["approval_required"] is True
    assert task["details"]["available_quantity"] == 1
    assert task["details"]["suggested_reorder_quantity"] == 9
    assert task["details"]["purchase_order_created"] is False

    approved = automation.decide_task("owner-1", task["id"], "approve", "Supplier quote still needed")
    assert approved["status"] == "approved_for_manual_action"
    assert approved["details"]["purchase_order_created"] is False
    assert approved["decision"] == "approve"


def test_unverified_payment_task_never_changes_payment_verification_state(automation_db):
    payment_id = ObjectId("64b000000000000000000102")
    automation_db["data"]["jumuiya_payments"].documents.append({
        "_id": payment_id,
        "business_id": "business-1",
        "invoice_id": "invoice-1",
        "amount_minor": 1200,
        "currency": "KES",
        "payment_method": "mpesa",
        "payment_status": "verification_required",
        "verification_status": "unverified_manual",
        "allocation_status": "not_allocated_pending_verification",
        "provider_verified": False,
    })
    automation.create_rule("owner-1", {
        "name": "Review external payment evidence",
        "trigger_event": "payment.recorded",
        "action_type": "create_payment_review_task",
        "conditions": {},
        "enabled": True,
    })
    event = {
        "business_id": "business-1",
        "event_id": "stable-payment-event-1",
        "event_type": "payment.recorded",
        "entity_type": "payment",
        "entity_id": str(payment_id),
        "payload": {
            "status": "not_allocated_pending_verification",
            "payment_status": "verification_required",
            "payment_verification_status": "unverified_manual",
            "payment_method": "mpesa",
            "amount_minor": 1200,
            "currency": "KES",
        },
    }

    automation.dispatch_event_automations(event)
    task = automation.list_tasks("owner-1")[0]
    assert task["task_type"] == "payment_evidence_review"
    assert task["status"] == "pending_review"
    assert task["details"]["provider_verified"] is False

    reviewed = automation.decide_task("owner-1", task["id"], "acknowledge", "Need to check provider statement")
    assert reviewed["status"] == "reviewed_unverified"
    saved_payment = automation_db["data"]["jumuiya_payments"].find_one({"_id": payment_id})
    assert saved_payment["payment_status"] == "verification_required"
    assert saved_payment["verification_status"] == "unverified_manual"
    assert saved_payment["provider_verified"] is False


def test_rule_and_task_reads_are_scoped_to_current_business(automation_db, monkeypatch):
    automation.create_rule("owner-1", {
        "name": "Owner one rule",
        "trigger_event": "order.created",
        "action_type": "create_fulfillment_task",
        "conditions": {},
        "enabled": True,
    })
    automation.create_rule("other-owner", {
        "name": "Owner two rule",
        "trigger_event": "order.created",
        "action_type": "create_fulfillment_task",
        "conditions": {},
        "enabled": True,
    })

    assert [rule["name"] for rule in automation.list_rules("owner-1")] == ["Owner one rule"]
    assert [rule["name"] for rule in automation.list_rules("other-owner")] == ["Owner two rule"]


def test_automation_rejects_unsupported_action_for_trigger(automation_db):
    with pytest.raises(APIError) as raised:
        automation.create_rule("owner-1", {
            "name": "Do a risky unsupported thing",
            "trigger_event": "order.created",
            "action_type": "create_reorder_suggestion",
            "conditions": {"available_quantity_lte": 1, "target_stock_quantity": 9},
            "enabled": True,
        })
    assert raised.value.code == "invalid_automation_action"
    assert len(automation_db["data"][automation.RULES_COLLECTION].documents) == 0

def _automation_outbox_event(business_id="business-1", event_id="worker-event-001", status="retry", attempts=0):
    from datetime import datetime, timezone
    return {
        "_id": ObjectId(),
        "business_id": business_id,
        "event_id": event_id,
        "event_key": event_id,
        "event_type": "order.created",
        "entity_type": "order",
        "entity_id": "order-worker-001",
        "payload": {
            "status": "pending",
            "source_channel": "pos",
            "total_amount_minor": 2500,
            "currency": "KES",
        },
        "automation_dispatch_status": status,
        "automation_dispatch_attempt_count": attempts,
        "automation_dispatch_lease_owner": None,
        "automation_dispatch_lease_token": None,
        "automation_dispatch_lease_expires_at": None,
        "automation_last_error_code": None,
        "automation_last_run_count": 0,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def test_worker_recovers_retry_events_idempotently_without_marking_provider_delivery(automation_db):
    automation.create_rule("owner-1", {
        "name": "Worker order follow-up",
        "trigger_event": "order.created",
        "action_type": "create_fulfillment_task",
        "conditions": {},
        "enabled": True,
    })
    event = _automation_outbox_event()
    automation_db["data"]["jumuiya_outbox_events"].documents.append(deepcopy(event))

    first = automation_worker.run_dispatch_batch("worker-test-1", limit=5)
    replay = automation_worker.run_dispatch_batch("worker-test-1", limit=5)

    assert first["claimed"] == 1
    assert first["processed"] == 1
    assert first["provider_delivery_attempted"] is False
    assert replay["claimed"] == 0
    saved = automation_db["data"]["jumuiya_outbox_events"].find_one({"event_id": event["event_id"]})
    assert saved["automation_dispatch_status"] == "processed"
    # Provider outbox status is a separate field and is never set to delivered.
    assert saved.get("state") is None
    assert saved["automation_dispatch_lease_token"] is None
    assert saved["automation_dispatch_lease_expires_at"] is None
    assert len(automation.list_tasks("owner-1")) == 1
    assert len(automation.list_runs("owner-1")) == 1


def test_worker_reclaims_expired_lease_and_old_worker_cannot_acknowledge(automation_db):
    from datetime import datetime, timezone

    event = _automation_outbox_event(status="processing", attempts=1)
    event["automation_dispatch_lease_owner"] = "worker-old"
    event["automation_dispatch_lease_token"] = "stale-token"
    event["automation_dispatch_lease_expires_at"] = datetime(2000, 1, 1, tzinfo=timezone.utc)
    automation_db["data"]["jumuiya_outbox_events"].documents.append(deepcopy(event))

    report = automation_worker.run_dispatch_batch("worker-new", limit=1)
    current = automation_db["data"]["jumuiya_outbox_events"].find_one({"event_id": event["event_id"]})

    assert report["claimed"] == 1
    assert report["processed"] == 1
    assert current["automation_dispatch_status"] == "processed"
    assert current["automation_dispatch_lease_owner"] is None
    assert automation_worker._finish_claim(
        event, "worker-old", "stale-token", "processed", run_count=99
    ) is False
    assert current["automation_last_run_count"] != 99


def test_worker_dead_letters_after_bounded_internal_dispatch_attempts(automation_db, monkeypatch):
    event = _automation_outbox_event(status="retry", attempts=automation_worker.MAX_DISPATCH_ATTEMPTS - 1)
    automation_db["data"]["jumuiya_outbox_events"].documents.append(deepcopy(event))
    monkeypatch.setattr(automation, "process_event_for_automations", lambda _event: {
        "processed": False,
        "error_code": "automation_test_failure",
    })

    first = automation_worker.run_dispatch_batch("worker-failure-test", limit=1)
    replay = automation_worker.run_dispatch_batch("worker-failure-test", limit=1)

    assert first["claimed"] == 1
    assert first["dead_lettered"] == 1
    assert replay["claimed"] == 0
    current = automation_db["data"]["jumuiya_outbox_events"].find_one({"event_id": event["event_id"]})
    assert current["automation_dispatch_status"] == "dead_letter"
    assert current["automation_last_error_code"] == "automation_test_failure"


def test_worker_can_filter_recovery_to_one_business(automation_db):
    target = _automation_outbox_event(business_id="business-1", event_id="target-event")
    other = _automation_outbox_event(business_id="business-2", event_id="other-event")
    automation_db["data"]["jumuiya_outbox_events"].documents.extend([deepcopy(target), deepcopy(other)])

    report = automation_worker.run_dispatch_batch("worker-tenant-filter", limit=10, business_id="business-1")

    assert report["claimed"] == 1
    assert report["processed"] == 1
    target_saved = automation_db["data"]["jumuiya_outbox_events"].find_one({"event_id": "target-event"})
    other_saved = automation_db["data"]["jumuiya_outbox_events"].find_one({"event_id": "other-event"})
    assert target_saved["automation_dispatch_status"] == "processed"
    assert other_saved["automation_dispatch_status"] == "retry"

def test_operator_can_replay_dead_lettered_automation_with_a_fresh_retry_window(automation_db):
    automation.create_rule("owner-1", {
        "name": "Recover manually replayed order follow-up",
        "trigger_event": "order.created",
        "action_type": "create_fulfillment_task",
        "conditions": {},
        "enabled": True,
    })
    event = _automation_outbox_event(
        event_id="manual-replay-worker-event",
        status="dead_letter",
        attempts=automation_worker.MAX_DISPATCH_ATTEMPTS,
    )
    automation_db["data"]["jumuiya_outbox_events"].documents.append(deepcopy(event))

    result = automation.replay_failed_automation_dispatches("owner-1", limit=10)

    saved = automation_db["data"]["jumuiya_outbox_events"].find_one({
        "event_id": "manual-replay-worker-event",
    })
    assert result["inspected"] == 1
    assert result["dead_letters_reset"] == 1
    assert result["processed"] == 1
    assert result["provider_delivery_attempted"] is False
    assert saved["automation_dispatch_status"] == "processed"
    assert saved["automation_manual_replay_count"] == 1
    assert saved["automation_last_manual_replay_by_user_id"] == "owner-1"
    assert len(automation.list_tasks("owner-1")) == 1

