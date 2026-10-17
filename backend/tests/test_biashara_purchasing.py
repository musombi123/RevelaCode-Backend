import sys
import types
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId

_missing_module = object()
_original_db_module = sys.modules.get("backend.db", _missing_module)
_test_db_module = types.ModuleType("backend.db")
_test_db_module.get_db = lambda: None
sys.modules["backend.db"] = _test_db_module
try:
    from backend.jumuiya.biashara import services as biashara_services
    from backend.jumuiya.biashara.purchasing import service as purchasing
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
        if isinstance(value, list):
            if not part.isdigit():
                return [item.get(part, _missing) for item in value if isinstance(item, dict)]
            index = int(part)
            if index >= len(value):
                return _missing
            value = value[index]
        elif isinstance(value, dict):
            value = value.get(part, _missing)
        else:
            return _missing
    return value


def _set_path(document, path, value):
    parts = path.split(".")
    target = document
    for part in parts[:-1]:
        if isinstance(target, list):
            target = target[int(part)]
        else:
            if part.isdigit() and isinstance(target, list):
                target = target[int(part)]
            else:
                target = target.setdefault(part, [])
                if isinstance(target, dict) and part != parts[-1]:
                    continue
    final = parts[-1]
    if isinstance(target, list):
        target[int(final)] = deepcopy(value)
    else:
        target[final] = deepcopy(value)


def _matches(document, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(document, option) for option in expected):
                return False
            continue
        actual = _get_path(document, key)
        if isinstance(expected, dict) and any(str(operator).startswith("$") for operator in expected):
            for operator, value in expected.items():
                if operator == "$in":
                    items = actual if isinstance(actual, list) else [actual]
                    if not any(item in value for item in items):
                        return False
                elif operator == "$ne":
                    items = actual if isinstance(actual, list) else [actual]
                    if any(item == value for item in items):
                        return False
                elif operator == "$exists":
                    exists = actual is not _missing
                    if exists != bool(value):
                        return False
                elif operator == "$lte":
                    if actual is _missing or actual > value:
                        return False
                elif operator == "$lt":
                    if actual is _missing or actual >= value:
                        return False
                elif operator == "$gt":
                    if actual is _missing or actual <= value:
                        return False
                else:
                    raise AssertionError("Unsupported fake query operator: " + operator)
        elif actual is _missing or actual != expected:
            return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, field, direction=1):
        def key(document):
            value = _get_path(document, field)
            return value is _missing or value is None, None if value is _missing else value
        self.rows.sort(key=key, reverse=direction < 0)
        return self

    def limit(self, amount):
        self.rows = self.rows[:amount]
        return self

    def __iter__(self):
        return iter(deepcopy(self.rows))


class FakeCollection:
    def __init__(self, documents=None, unique_keys=(), fail_receipt_lines_once=False):
        self.documents = [deepcopy(document) for document in (documents or [])]
        self.unique_keys = tuple(unique_keys)
        self.fail_receipt_lines_once = fail_receipt_lines_once

    def find_one(self, query):
        for document in self.documents:
            if _matches(document, query):
                return deepcopy(document)
        return None

    def find(self, query=None, projection=None):
        query = query or {}
        return Cursor([document for document in self.documents if _matches(document, query)])

    def insert_one(self, document):
        from pymongo.errors import DuplicateKeyError
        saved = deepcopy(document)
        for keys in self.unique_keys:
            values = [saved.get(key) for key in keys]
            if all(value is not None for value in values):
                for old in self.documents:
                    if all(old.get(key) == saved.get(key) for key in keys):
                        raise DuplicateKeyError("duplicate unique key")
        saved["_id"] = saved.get("_id") or ObjectId()
        self.documents.append(saved)
        return SimpleNamespace(inserted_id=saved["_id"])

    def update_one(self, query, update):
        if self.fail_receipt_lines_once and "lines" in update.get("$set", {}):
            self.fail_receipt_lines_once = False
            raise RuntimeError("simulated crash window after inventory movement")
        for document in self.documents:
            if _matches(document, query):
                self._apply(document, update)
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    def find_one_and_update(self, query, update, return_document=None):
        for document in self.documents:
            if _matches(document, query):
                self._apply(document, update)
                return deepcopy(document)
        return None

    def _apply(self, document, update):
        for key, value in update.get("$set", {}).items():
            if "." in key:
                _set_path(document, key, value)
            else:
                document[key] = deepcopy(value)
        for key, value in update.get("$inc", {}).items():
            current = _get_path(document, key)
            if current is _missing:
                current = 0
            _set_path(document, key, current + value) if "." in key else document.__setitem__(key, current + value)
        for key, value in update.get("$addToSet", {}).items():
            items = _get_path(document, key)
            if items is _missing or items is None:
                _set_path(document, key, [])
                items = _get_path(document, key)
            if value not in items:
                items.append(deepcopy(value))
        for key, value in update.get("$push", {}).items():
            items = _get_path(document, key)
            if items is _missing or items is None:
                _set_path(document, key, [])
                items = _get_path(document, key)
            items.append(deepcopy(value))
        for key, expected in update.get("$pull", {}).items():
            items = _get_path(document, key)
            if isinstance(items, list):
                if isinstance(expected, dict):
                    items[:] = [item for item in items if not _matches(item, expected)]
                else:
                    items[:] = [item for item in items if item != expected]


@pytest.fixture
def purchasing_db(monkeypatch):
    business_id = "business-purchase-1"
    product_id = ObjectId("64b000000000000000000401")
    products = FakeCollection([{
        "_id": product_id,
        "business_id": business_id,
        "name": "Face Cream",
        "sku": "FC-01",
        "currency": "KES",
        "cost_price": 100.0,
        "price": 250.0,
        "stock_quantity": 0.0,
        "reserved_quantity": 0.0,
        "low_stock_threshold": 5,
        "status": "active",
        "pending_inventory_mutations": [],
        "active_reservations": [],
        "outbox_event_manifest": [],
        "outbox_enqueued_event_keys": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }])
    collections = {
        purchasing.SUPPLIERS_COLLECTION: FakeCollection(unique_keys=(
            ("business_id", "idempotency_key"),
        )),
        purchasing.PURCHASE_ORDERS_COLLECTION: FakeCollection(unique_keys=(
            ("business_id", "po_number"),
            ("business_id", "idempotency_key"),
        )),
        purchasing.RECEIPTS_COLLECTION: FakeCollection(unique_keys=(
            ("business_id", "purchase_order_id", "idempotency_key"),
        ), fail_receipt_lines_once=True),
        "jumuiya_products": products,
        "jumuiya_inventory_movements": FakeCollection(unique_keys=(
            ("business_id", "idempotency_key"),
        )),
        "jumuiya_outbox_events": FakeCollection(unique_keys=(
            ("business_id", "event_id"),
        )),
    }

    def get_collection(name):
        return collections[name]

    monkeypatch.setattr(purchasing, "collection", get_collection)
    monkeypatch.setattr(biashara_services, "collection", get_collection)
    monkeypatch.setattr(purchasing, "require_permission", lambda user_id, permission, business_id=None: {
        "id": business_id or ("business-purchase-1" if user_id != "other-owner" else "business-purchase-2"),
        "currency": "KES",
        "permissions": ["*"],
    })
    monkeypatch.setattr(biashara_services, "_require_business", lambda user_id: {
        "id": "business-purchase-1" if user_id != "other-owner" else "business-purchase-2",
        "currency": "KES",
        "name": "Test business",
    })
    monkeypatch.setattr(biashara_services, "require_permission", lambda user_id, permission, business_id=None: {
        "id": business_id or "business-purchase-1",
        "currency": "KES",
        "permissions": ["*"],
    })
    monkeypatch.setattr(purchasing, "_dispatch_source", lambda *args, **kwargs: {
        "enqueued": 1, "pending": 0, "errors": 0,
    })
    monkeypatch.setattr(biashara_services, "_dispatch_outbox_source", lambda *args, **kwargs: {
        "enqueued": 1, "pending": 0, "errors": 0,
    })
    monkeypatch.setattr(purchasing, "dispatch_manifest_for_record", lambda *args, **kwargs: {
        "enqueued": 1, "pending": 0, "errors": 0,
    })
    monkeypatch.setattr(purchasing, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(biashara_services, "log_action", lambda *args, **kwargs: None)

    return {
        "data": collections,
        "product_id": product_id,
    }


def _create_order(purchasing_db, quantity=5, key="po-create-0001"):
    supplier = purchasing.create_supplier("owner-1", {
        "name": "Coast Wholesale",
        "phone": "+254700000001",
        "email": "orders@coast.example.test",
        "lead_time_days": 3,
        "idempotency_key": "supplier-create-0001",
    })
    order = purchasing.create_purchase_order("owner-1", {
        "supplier_id": supplier["id"],
        "currency": "KES",
        "notes": "Restock face cream",
        "idempotency_key": key,
        "lines": [{
            "product_id": str(purchasing_db["product_id"]),
            "quantity": quantity,
            "unit_cost": "12.50",
        }],
    })
    return supplier, order


def _order_status(purchasing_db, order_id, status="ordered"):
    return purchasing.update_purchase_order_status("owner-1", order_id, status)


def test_supplier_and_purchase_order_creation_is_idempotent_and_does_not_change_stock(purchasing_db):
    supplier, first = _create_order(purchasing_db, quantity=3)
    _, second = _create_order(purchasing_db, quantity=3)

    assert supplier["name"] == "Coast Wholesale"
    assert first["id"] == second["id"]
    assert first["status"] == "draft"
    assert first["po_number"].startswith("PO-")
    assert first["subtotal_minor"] == 3750
    assert first["lines"][0]["unit_cost_minor"] == 1250
    assert first["lines"][0]["quantity_ordered"] == 3
    assert purchasing_db["data"]["jumuiya_products"].documents[0]["stock_quantity"] == 0
    assert len(purchasing_db["data"][purchasing.PURCHASE_ORDERS_COLLECTION].documents) == 1


def test_purchase_order_requires_supplier_and_product_from_same_business(purchasing_db):
    supplier, _order = _create_order(purchasing_db)
    foreign_product_id = ObjectId("64b000000000000000000402")
    purchasing_db["data"]["jumuiya_products"].documents.append({
        "_id": foreign_product_id,
        "business_id": "business-purchase-2",
        "name": "Foreign Product",
        "sku": "OTHER",
        "currency": "KES",
        "cost_price": 100,
        "stock_quantity": 0,
        "status": "active",
    })

    with pytest.raises(APIError) as supplier_error:
        purchasing.create_purchase_order("other-owner", {
            "supplier_id": supplier["id"],
            "currency": "KES",
            "idempotency_key": "po-cross-tenant-0001",
            "lines": [{"product_id": str(foreign_product_id), "quantity": 1, "unit_cost": "10.00"}],
        })
    assert supplier_error.value.code == "supplier_not_found"

    with pytest.raises(APIError) as product_error:
        purchasing.create_purchase_order("owner-1", {
            "supplier_id": supplier["id"],
            "currency": "KES",
            "idempotency_key": "po-cross-tenant-0002",
            "lines": [{"product_id": str(foreign_product_id), "quantity": 1, "unit_cost": "10.00"}],
        })
    assert product_error.value.code == "purchase_order_product_not_found"


def test_receiving_updates_stock_and_po_once_on_duplicate_receipt(purchasing_db):
    _supplier, order = _create_order(purchasing_db)
    _order_status(purchasing_db, order["id"], "ordered")
    payload = {
        "idempotency_key": "po-receive-0001",
        "lines": [{"product_id": str(purchasing_db["product_id"]), "quantity": 2}],
    }

    first = purchasing.receive_purchase_order_items("owner-1", order["id"], payload)
    second = purchasing.receive_purchase_order_items("owner-1", order["id"], payload)

    assert first["status"] == "completed"
    assert first["id"] == second["id"]
    product = purchasing_db["data"]["jumuiya_products"].documents[0]
    assert product["stock_quantity"] == 2
    movements = purchasing_db["data"]["jumuiya_inventory_movements"].documents
    assert len(movements) == 1
    assert movements[0]["source"] == "purchase_order_receipt"
    assert movements[0]["purchase_order_id"] == order["id"]

    saved_order = purchasing_db["data"][purchasing.PURCHASE_ORDERS_COLLECTION].find_one({"_id": ObjectId(order["id"])})
    assert saved_order["lines"][0]["quantity_received"] == 2
    assert saved_order["status"] == "partially_received"
    assert len(saved_order["applied_receipt_ids"]) == 1


def test_interrupted_receipt_retries_movement_without_double_count(purchasing_db):
    _supplier, order = _create_order(purchasing_db, quantity=4)
    _order_status(purchasing_db, order["id"], "ordered")
    payload = {
        "idempotency_key": "po-receive-recover-01",
        "lines": [{"product_id": str(purchasing_db["product_id"]), "quantity": 2}],
    }

    first = purchasing.receive_purchase_order_items("owner-1", order["id"], payload)
    assert first["status"] == "partial"
    assert purchasing_db["data"]["jumuiya_products"].documents[0]["stock_quantity"] == 2
    assert len(purchasing_db["data"]["jumuiya_inventory_movements"].documents) == 1

    second = purchasing.receive_purchase_order_items("owner-1", order["id"], payload)

    assert second["status"] == "completed"
    assert purchasing_db["data"]["jumuiya_products"].documents[0]["stock_quantity"] == 2
    assert len(purchasing_db["data"]["jumuiya_inventory_movements"].documents) == 1
    saved_order = purchasing_db["data"][purchasing.PURCHASE_ORDERS_COLLECTION].find_one({"_id": ObjectId(order["id"])})
    assert saved_order["lines"][0]["quantity_received"] == 2
    assert len(saved_order["applied_receipt_ids"]) == 1


def test_receipt_quantity_cannot_exceed_remaining_order_quantity(purchasing_db):
    _supplier, order = _create_order(purchasing_db, quantity=2)
    _order_status(purchasing_db, order["id"], "ordered")
    with pytest.raises(APIError) as raised:
        purchasing.receive_purchase_order_items("owner-1", order["id"], {
            "idempotency_key": "po-receive-too-much",
            "lines": [{"product_id": str(purchasing_db["product_id"]), "quantity": 3}],
        })
    assert raised.value.code == "purchase_receipt_exceeds_ordered_quantity"
    assert purchasing_db["data"]["jumuiya_products"].documents[0]["stock_quantity"] == 0
    assert len(purchasing_db["data"]["jumuiya_inventory_movements"].documents) == 0


def test_new_receipt_is_blocked_until_partial_receipt_is_recovered(purchasing_db):
    _supplier, order = _create_order(purchasing_db, quantity=4)
    _order_status(purchasing_db, order["id"], "ordered")
    first_payload = {
        "idempotency_key": "po-receive-partial-01",
        "lines": [{"product_id": str(purchasing_db["product_id"]), "quantity": 1}],
    }
    first = purchasing.receive_purchase_order_items("owner-1", order["id"], first_payload)
    assert first["status"] == "partial"

    with pytest.raises(APIError) as raised:
        purchasing.receive_purchase_order_items("owner-1", order["id"], {
            "idempotency_key": "po-receive-new-0001",
            "lines": [{"product_id": str(purchasing_db["product_id"]), "quantity": 1}],
        })
    assert raised.value.code == "purchase_receipt_recovery_required"


def test_receiving_requires_inventory_permission_before_persisting_receipt(purchasing_db, monkeypatch):
    _supplier, order = _create_order(purchasing_db)
    _order_status(purchasing_db, order["id"], "ordered")

    def denied(user_id, permission, business_id=None):
        if permission == "inventory.manage":
            raise APIError("No stock permission.", 403, "business_permission_denied")
        return {"id": business_id or "business-purchase-1"}

    monkeypatch.setattr(purchasing, "require_permission", denied)
    with pytest.raises(APIError) as raised:
        purchasing.receive_purchase_order_items("owner-1", order["id"], {
            "idempotency_key": "po-receive-denied-1",
            "lines": [{"product_id": str(purchasing_db["product_id"]), "quantity": 1}],
        })
    assert raised.value.code == "business_permission_denied"
    assert len(purchasing_db["data"][purchasing.RECEIPTS_COLLECTION].documents) == 0
