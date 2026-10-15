from copy import deepcopy
import sys
import types
from types import SimpleNamespace

import pytest
from bson import ObjectId

# backend.db performs a connection ping at import time. Isolate that bootstrap
# here because all service collections are replaced with in-memory fakes below.
_missing_module = object()
_original_db_module = sys.modules.get("backend.db", _missing_module)
_test_db_module = types.ModuleType("backend.db")
_test_db_module.get_db = lambda: None
sys.modules["backend.db"] = _test_db_module
try:
    from backend.jumuiya.biashara import services
finally:
    if _original_db_module is _missing_module:
        sys.modules.pop("backend.db", None)
    else:
        sys.modules["backend.db"] = _original_db_module

from backend.jumuiya.core.errors import APIError


def _values(document, path):
    values = [document]
    for part in path.split("."):
        found = []
        for value in values:
            if isinstance(value, list):
                found.extend(item[part] for item in value if isinstance(item, dict) and part in item)
            elif isinstance(value, dict) and part in value:
                found.append(value[part])
        values = found
    return values, bool(values)


def _matches(document, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(document, item) for item in expected):
                return False
            continue
        values, exists = _values(document, key)
        if isinstance(expected, dict) and any(k.startswith("$") for k in expected):
            for op, value in expected.items():
                if op == "$exists" and exists != bool(value):
                    return False
                if op == "$ne" and any(item == value for item in values):
                    return False
                if op == "$in" and not any(item in value for item in values):
                    return False
                if op == "$lte" and not any(item <= value for item in values):
                    return False
                if op == "$gte" and not any(item >= value for item in values):
                    return False
                if op == "$elemMatch" and not any(
                    isinstance(item, list) and any(_matches(member, value) for member in item)
                    for item in values
                ):
                    return False
                if op not in {"$exists", "$ne", "$in", "$lte", "$gte", "$elemMatch"}:
                    raise AssertionError(f"Unsupported fake query operator: {op}")
        elif not exists or not any(item == expected for item in values):
            return False
    return True


def _set_path(document, path, value):
    current = document
    parts = path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = deepcopy(value)


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = [deepcopy(doc) for doc in (documents or [])]

    def find_one(self, query):
        for document in self.documents:
            if _matches(document, query):
                return deepcopy(document)
        return None

    def insert_one(self, document):
        created = deepcopy(document)
        created["_id"] = created.get("_id") or ObjectId()
        self.documents.append(created)
        return SimpleNamespace(inserted_id=created["_id"])

    def _apply(self, document, update, array_filters=None):
        array_filters = array_filters or []
        for key, value in update.get("$set", {}).items():
            if ".$[" in key:
                array_name, tail = key.split(".$[", 1)
                identifier, nested_path = tail.split("].", 1)
                filters = next((item for item in array_filters if any(k.startswith(identifier + ".") for k in item)), {})
                predicates = {k[len(identifier) + 1:]: v for k, v in filters.items()}
                for member in document.setdefault(array_name, []):
                    if _matches(member, predicates):
                        _set_path(member, nested_path, value)
            else:
                _set_path(document, key, value)
        for key, value in update.get("$inc", {}).items():
            document[key] = document.get(key, 0) + value
        for key, value in update.get("$addToSet", {}).items():
            items = document.setdefault(key, [])
            if value not in items:
                items.append(deepcopy(value))
        for key, value in update.get("$push", {}).items():
            document.setdefault(key, []).append(deepcopy(value))
        for key, value in update.get("$pull", {}).items():
            items = document.get(key, [])
            document[key] = [item for item in items if not (_matches(item, value) if isinstance(value, dict) else item == value)]

    def find_one_and_update(self, query, update, return_document=None, array_filters=None):
        for document in self.documents:
            if _matches(document, query):
                self._apply(document, update, array_filters)
                return deepcopy(document)
        return None

    def update_one(self, query, update):
        for document in self.documents:
            if _matches(document, query):
                self._apply(document, update)
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


@pytest.fixture
def commerce_db(monkeypatch):
    product_id = ObjectId("64b000000000000000000001")
    products = FakeCollection([{
        "_id": product_id,
        "business_id": "business-1",
        "name": "Original catalogue item",
        "sku": "SKU-001",
        "price": 150.25,
        "currency": "KES",
        "stock_quantity": 5.0,
        "status": "active",
        "active_reservations": [],
    }])
    collections = {
        "jumuiya_products": products,
        "jumuiya_customers": FakeCollection([]),
        "jumuiya_orders": FakeCollection([]),
        "jumuiya_inventory_movements": FakeCollection([]),
    }
    monkeypatch.setattr(services, "collection", lambda name: collections[name])
    monkeypatch.setattr(services, "_require_business", lambda user_id: {"id": "business-1", "currency": "KES"})
    monkeypatch.setattr(services, "log_action", lambda *args, **kwargs: None)
    return {
        "product_id": product_id,
        "product": products.documents[0],
        **collections,
        "orders": collections["jumuiya_orders"],
        "movements": collections["jumuiya_inventory_movements"],
        "products": products,
    }


def _payload(db, quantity=2, **extra):
    return {
        "items": [{"product_id": str(db["product_id"]), "quantity": quantity, "unit_price": 0.01, "name": "Forged client name"}],
        "total_amount": 0.02,
        "currency": "USD",
        "notes": "Website/manual order",
        **extra,
    }


def test_order_uses_server_catalogue_price_and_reserves_available_stock(commerce_db):
    result = services.create_order("owner-1", _payload(commerce_db))
    assert result["total_amount"] == 300.5
    assert result["total_amount_minor"] == 30050
    assert result["subtotal_minor"] == 30050
    assert result["currency"] == "KES"
    assert result["items"][0]["name"] == "Original catalogue item"
    assert result["items"][0]["unit_price"] == 150.25
    assert result["items"][0]["line_total_minor"] == 30050
    assert result["payment_status"] == "unpaid"
    assert result["inventory_status"] == "reserved"
    assert result["status_history"][0]["to"] == "pending"
    assert commerce_db["product"]["stock_quantity"] == 5
    assert commerce_db["product"]["reserved_quantity"] == 2
    assert len(commerce_db["movements"].documents) == 1


def test_order_idempotency_key_replays_without_duplicate_reservation(commerce_db):
    payload = _payload(commerce_db, idempotency_key="checkout-attempt-0001")
    first = services.create_order("owner-1", payload)
    second = services.create_order("owner-1", payload)
    assert first["id"] == second["id"]
    assert commerce_db["product"]["reserved_quantity"] == 2
    assert len(commerce_db["orders"].documents) == 1
    assert len(commerce_db["movements"].documents) == 1


def test_order_rejects_reusing_idempotency_key_with_different_payload(commerce_db):
    services.create_order("owner-1", _payload(commerce_db, idempotency_key="checkout-attempt-0002"))
    with pytest.raises(APIError) as raised:
        services.create_order("owner-1", _payload(commerce_db, quantity=1, idempotency_key="checkout-attempt-0002"))
    assert raised.value.code == "idempotency_key_reused"
    assert commerce_db["product"]["reserved_quantity"] == 2


def test_order_rejects_quantity_above_available_stock_and_keeps_failure_record(commerce_db):
    with pytest.raises(APIError, match="Insufficient available stock"):
        services.create_order("owner-1", _payload(commerce_db, quantity=6))
    assert len(commerce_db["orders"].documents) == 1
    assert commerce_db["orders"].documents[0]["status"] == "cancelled"
    assert commerce_db["orders"].documents[0]["inventory_status"] == "reservation_failed"
    assert commerce_db["product"].get("reserved_quantity", 0) == 0
    assert commerce_db["product"]["stock_quantity"] == 5


def test_cancelled_order_releases_reservation_once(commerce_db):
    created = services.create_order("owner-1", _payload(commerce_db))
    cancelled = services.update_order_status("owner-1", created["id"], "cancelled")
    again = services.update_order_status("owner-1", created["id"], "cancelled")
    assert cancelled["status"] == "cancelled"
    assert again["status"] == "cancelled"
    assert commerce_db["product"]["stock_quantity"] == 5
    assert commerce_db["product"]["reserved_quantity"] == 0
    assert commerce_db["product"]["active_reservations"] == []
    assert len(commerce_db["movements"].documents) == 2


def test_processing_consumes_reserved_stock_once(commerce_db):
    created = services.create_order("owner-1", _payload(commerce_db))
    services.update_order_status("owner-1", created["id"], "confirmed")
    processing = services.update_order_status("owner-1", created["id"], "processing")
    completed = services.update_order_status("owner-1", created["id"], "completed")
    assert processing["inventory_status"] == "consumed"
    assert completed["status"] == "completed"
    assert commerce_db["product"]["stock_quantity"] == 3
    assert commerce_db["product"]["reserved_quantity"] == 0
    assert commerce_db["product"]["active_reservations"] == []
    assert len(commerce_db["movements"].documents) == 2


def test_order_status_transition_must_follow_lifecycle(commerce_db):
    order_id = ObjectId("64b000000000000000000002")
    commerce_db["orders"].documents.append({
        "_id": order_id,
        "business_id": "business-1",
        "status": "pending",
        "inventory_status": "reserved",
        "items": [{"product_id": str(commerce_db["product_id"]), "quantity": 1}],
        "status_history": [{"from": None, "to": "pending"}],
    })
    with pytest.raises(APIError, match="cannot move from pending to completed"):
        services.update_order_status("owner-1", str(order_id), "completed")
    assert commerce_db["orders"].documents[0]["status"] == "pending"


def test_order_status_history_tracks_legal_transitions(commerce_db):
    order_id = ObjectId("64b000000000000000000003")
    commerce_db["orders"].documents.append({
        "_id": order_id,
        "business_id": "business-1",
        "status": "pending",
        "items": [{"product_id": str(commerce_db["product_id"]), "quantity": 1}],
        "status_history": [{"from": None, "to": "pending"}],
    })
    services.update_order_status("owner-1", str(order_id), "confirmed")
    services.update_order_status("owner-1", str(order_id), "processing")
    result = services.update_order_status("owner-1", str(order_id), "completed")
    assert result["status"] == "completed"
    assert [item["to"] for item in result["status_history"]] == ["pending", "confirmed", "processing", "completed"]
    assert commerce_db["product"]["stock_quantity"] == 4
    assert commerce_db["product"].get("reserved_quantity", 0) == 0


def test_order_payload_does_not_require_client_calculated_total():
    from jumuiya.biashara.schemas import order_payload
    result = order_payload({"items": [{"product_id": "64b000000000000000000001", "quantity": 1}]})
    assert result["total_amount"] == 0.0
