from copy import deepcopy
import re
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
from backend.jumuiya.biashara.sync import outbox


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
                if op == "$regex":
                    options = expected.get("$options", "")
                    flags = re.IGNORECASE if "i" in str(options) else 0
                    if not any(re.search(str(value), str(item), flags) for item in values if item is not None):
                        return False
                if op == "$options":
                    continue
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
                if op not in {"$exists", "$ne", "$in", "$lte", "$gte", "$elemMatch", "$regex", "$options"}:
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


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, field, direction=1):
        def key_fn(document):
            value = document.get(field)
            return value is None, value
        self.documents.sort(key=key_fn, reverse=direction < 0)
        return self

    def limit(self, amount):
        self.documents = self.documents[:amount]
        return self

    def __iter__(self):
        return iter(deepcopy(self.documents))


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = [deepcopy(doc) for doc in (documents or [])]

    def find(self, query, projection=None):
        return FakeCursor([doc for doc in self.documents if _matches(doc, query)])

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
        # MongoDB determines matching array-filter elements before applying any
        # update fields. Snapshot matching objects so changing state in one
        # field does not prevent the rest of that atomic update from applying.
        matched_arrays = {}
        for key in update.get("$set", {}):
            if ".$[" not in key:
                continue
            array_name, tail = key.split(".$[", 1)
            identifier, _nested_path = tail.split("].", 1)
            filters = next((item for item in array_filters if any(k.startswith(identifier + ".") for k in item)), {})
            predicates = {k[len(identifier) + 1:]: v for k, v in filters.items()}
            cache_key = (array_name, identifier)
            if cache_key not in matched_arrays:
                matched_arrays[cache_key] = [
                    member for member in document.setdefault(array_name, [])
                    if _matches(member, predicates)
                ]

        for key, value in update.get("$set", {}).items():
            if ".$[" in key:
                array_name, tail = key.split(".$[", 1)
                identifier, nested_path = tail.split("].", 1)
                for member in matched_arrays.get((array_name, identifier), []):
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
        "jumuiya_sales": FakeCollection([]),
        "jumuiya_inventory_movements": FakeCollection([]),
        "jumuiya_outbox_events": FakeCollection([]),
    }
    monkeypatch.setattr(services, "collection", lambda name: collections[name])
    monkeypatch.setattr(outbox, "collection", lambda name: collections[name])
    monkeypatch.setattr(services, "_require_business", lambda user_id: {"id": "business-1", "currency": "KES"})
    monkeypatch.setattr(services, "require_permission", lambda user_id, permission, business_id=None: {"id": business_id or "business-1"})
    monkeypatch.setattr(services, "log_action", lambda *args, **kwargs: None)
    return {
        "product_id": product_id,
        "product": products.documents[0],
        **collections,
        "orders": collections["jumuiya_orders"],
        "sales": collections["jumuiya_sales"],
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

def test_pos_sale_uses_canonical_totals_consumes_stock_once_and_does_not_fake_mpesa_verification(commerce_db):
    payload = {
        "items": [{
            "product_id": str(commerce_db["product_id"]),
            "quantity": 2,
            "unit_price": 0.01,
            "name": "Forged sale name",
        }],
        "amount": 0.02,
        "currency": "USD",
        "payment_method": "mpesa",
        "reference": "manual-stk-checkout",
        "idempotency_key": "pos-sale-attempt-0001",
    }

    sale = services.record_sale("owner-1", payload)

    assert sale["amount"] == 300.5
    assert sale["amount_minor"] == 30050
    assert sale["currency"] == "KES"
    assert sale["items"][0]["name"] == "Original catalogue item"
    assert sale["items"][0]["unit_price"] == 150.25
    assert sale["payment_status"] == "verification_required"
    assert sale["payment_verification_status"] == "unverified_manual"
    assert sale["provider_verified"] is False

    order = commerce_db["orders"].find_one({"_id": ObjectId(sale["order_id"])})
    assert order["status"] == "completed"
    assert order["inventory_status"] == "consumed"
    assert order["payment_status"] == "verification_required"
    assert order["payment_verification_status"] == "unverified_manual"
    assert commerce_db["products"].documents[0]["stock_quantity"] == 3
    assert commerce_db["products"].documents[0]["reserved_quantity"] == 0
    assert len(commerce_db["movements"].documents) == 2


def test_pos_sale_retry_is_idempotent_and_does_not_duplicate_sale_stock_or_movements(commerce_db):
    payload = {
        "items": [{"product_id": str(commerce_db["product_id"]), "quantity": 1}],
        "amount": 0.01,
        "payment_method": "cash",
        "reference": "counter-receipt",
        "idempotency_key": "pos-sale-attempt-0002",
    }

    first = services.record_sale("owner-1", payload)
    second = services.record_sale("owner-1", payload)

    assert first["id"] == second["id"]
    assert first["amount"] == 150.25
    assert first["payment_status"] == "manual_attested"
    assert first["payment_verification_status"] == "manual_attested"
    assert first["provider_verified"] is False
    assert len(commerce_db["sales"].documents) == 1
    assert len(commerce_db["orders"].documents) == 1
    assert commerce_db["products"].documents[0]["stock_quantity"] == 4
    assert commerce_db["products"].documents[0]["reserved_quantity"] == 0
    assert len(commerce_db["movements"].documents) == 2


def test_pos_sale_rejects_idempotency_key_reuse_with_different_items(commerce_db):
    first_payload = {
        "items": [{"product_id": str(commerce_db["product_id"]), "quantity": 1}],
        "payment_method": "cash",
        "idempotency_key": "pos-sale-attempt-0003",
    }
    services.record_sale("owner-1", first_payload)
    changed_payload = {
        **first_payload,
        "items": [{"product_id": str(commerce_db["product_id"]), "quantity": 2}],
    }

    with pytest.raises(APIError) as raised:
        services.record_sale("owner-1", changed_payload)
    assert raised.value.code == "idempotency_key_reused"
    assert len(commerce_db["sales"].documents) == 1
    assert commerce_db["products"].documents[0]["stock_quantity"] == 4


def test_existing_order_sale_uses_order_snapshots_and_rejects_second_canonical_sale(commerce_db):
    order = services.create_order("owner-1", _payload(commerce_db, quantity=1))
    sale_payload = {
        "order_id": order["id"],
        "amount": 0.01,
        "currency": "USD",
        "payment_method": "cash",
        "reference": "walk-in-paid",
    }
    sale = services.record_sale("owner-1", sale_payload)
    assert sale["amount"] == 150.25
    assert sale["order_id"] == order["id"]

    with pytest.raises(APIError) as raised:
        services.record_sale("owner-1", {
            **sale_payload,
            "reference": "different-receipt-reference",
        })
    assert raised.value.code == "sale_already_recorded"
    assert len(commerce_db["sales"].documents) == 1
    assert commerce_db["products"].documents[0]["stock_quantity"] == 4


def test_sale_schema_allows_server_calculated_amount_but_expense_still_requires_amount():
    from jumuiya.biashara.schemas import expense_payload, sale_payload

    sale = sale_payload({
        "items": [{"product_id": "64b000000000000000000001", "quantity": 1}],
    })
    assert sale["amount"] == 0.0

    with pytest.raises(ValueError):
        expense_payload({"title": "Rent"})

def test_product_stock_edit_creates_ledger_movement_and_preserves_idempotency(commerce_db):
    first = services.update_product(
        "owner-1",
        str(commerce_db["product_id"]),
        {
            "stock_quantity": 4,
            "idempotency_key": "product-stock-edit-0001",
        },
    )
    second = services.update_product(
        "owner-1",
        str(commerce_db["product_id"]),
        {
            "stock_quantity": 4,
            "idempotency_key": "product-stock-edit-0001",
        },
    )

    assert first["stock_quantity"] == 4
    assert second["stock_quantity"] == 4
    assert len(commerce_db["movements"].documents) == 1
    movement = commerce_db["movements"].documents[0]
    assert movement["movement_type"] == "set"
    assert movement["idempotency_key"] == "product-stock-edit-0001"
    assert movement["previous_stock_quantity"] == 5
    assert movement["new_stock_quantity"] == 4


def test_product_archive_is_blocked_while_stock_is_reserved(commerce_db):
    commerce_db["products"].documents[0]["reserved_quantity"] = 1
    commerce_db["products"].documents[0]["active_reservations"] = [{
        "order_id": "order-open-1",
        "quantity": 1,
        "state": "reserved",
    }]

    with pytest.raises(APIError) as raised:
        services.delete_product("owner-1", str(commerce_db["product_id"]))

    assert raised.value.code == "product_has_open_reservations"
    assert commerce_db["products"].documents[0]["status"] == "active"


def test_inventory_adjustment_rejects_removal_that_would_consume_reserved_stock(commerce_db):
    commerce_db["products"].documents[0]["reserved_quantity"] = 4

    with pytest.raises(APIError) as raised:
        services.inventory_adjustment("owner-1", str(commerce_db["product_id"]), {
            "movement_type": "remove",
            "quantity": 2,
            "reason": "broken_item",
            "idempotency_key": "stock-remove-reserved-1",
        })

    assert raised.value.code == "insufficient_stock"
    assert commerce_db["products"].documents[0]["stock_quantity"] == 5
    assert len(commerce_db["movements"].documents) == 0

def test_customer_create_is_tenant_scoped_idempotent_and_sync_recoverable(commerce_db):
    payload = {
        "name": "Amina Hassan",
        "phone": "+254700111222",
        "email": "amina@example.test",
        "notes": "Prefers WhatsApp contact",
        "idempotency_key": "customer-create-0001",
    }
    first = services.create_customer("owner-1", payload)
    second = services.create_customer("owner-1", payload)

    assert first["id"] == second["id"]
    assert len(commerce_db["jumuiya_customers"].documents) == 1
    saved = commerce_db["jumuiya_customers"].documents[0]
    assert saved["business_id"] == "business-1"
    assert saved["idempotency_key"] == "customer-create-0001"
    assert saved["request_fingerprint"]
    assert saved["outbox_event_manifest"][0]["event_type"] == "customer.created"
    assert len(commerce_db["jumuiya_outbox_events"].documents) == 1

    # Other tenants' customer rows never appear in this business's search.
    other_id = ObjectId("64b000000000000000000099")
    commerce_db["jumuiya_customers"].documents.append({
        "_id": other_id,
        "business_id": "business-2",
        "name": "Amina Hassan",
        "phone": "+254700111222",
        "email": "amina@example.test",
        "created_at": saved["created_at"],
    })
    customers = services.list_customers("owner-1", search="Amina")
    assert len(customers) == 1
    assert customers[0]["id"] == first["id"]


def test_customer_idempotency_key_reuse_with_changed_details_is_rejected(commerce_db):
    services.create_customer("owner-1", {
        "name": "James Otieno",
        "phone": "+254711222333",
        "idempotency_key": "customer-create-0002",
    })
    with pytest.raises(APIError) as raised:
        services.create_customer("owner-1", {
            "name": "James Otieno",
            "phone": "+254711222334",
            "idempotency_key": "customer-create-0002",
        })
    assert raised.value.code == "idempotency_key_reused"
    assert len(commerce_db["jumuiya_customers"].documents) == 1

def test_inventory_history_is_bounded_and_tenant_scoped(commerce_db):
    result = services.inventory_adjustment(
        "owner-1",
        str(commerce_db["product_id"]),
        {
            "movement_type": "add",
            "quantity": 1,
            "reason": "supplier_delivery",
            "idempotency_key": "inventory-history-add-0001",
        },
    )
    commerce_db["movements"].documents.append({
        "_id": ObjectId("64b000000000000000000088"),
        "business_id": "business-2",
        "product_id": str(commerce_db["product_id"]),
        "movement_type": "add",
        "quantity": 50,
        "reason": "other_tenant",
        "created_at": result["movement"]["created_at"],
    })

    rows = services.inventory_history("owner-1", str(commerce_db["product_id"]), limit=1)
    assert len(rows) == 1
    assert rows[0]["id"] == result["movement"]["id"]
    assert rows[0]["business_id"] == "business-1"

    with pytest.raises(APIError) as raised:
        services.inventory_history("owner-1", "64b000000000000000000088", limit=10)
    assert raised.value.code == "product_not_found"


def test_order_status_service_requires_orders_manage_permission(commerce_db, monkeypatch):
    created = services.create_order("owner-1", _payload(commerce_db, quantity=1))

    def deny_order_management(user_id, permission, business_id=None):
        if permission == "orders.manage":
            raise APIError("Forbidden for this role.", 403, "business_permission_denied")
        return {"id": business_id or "business-1"}

    monkeypatch.setattr(services, "require_permission", deny_order_management)

    with pytest.raises(APIError) as raised:
        services.update_order_status("owner-1", created["id"], "confirmed")
    assert raised.value.code == "business_permission_denied"
    order = commerce_db["orders"].find_one({"_id": ObjectId(created["id"])})
    assert order["status"] == "pending"
    assert commerce_db["product"]["reserved_quantity"] == 1


def test_cashier_can_record_pos_sale_without_order_management_permission(commerce_db, monkeypatch):
    permissions = {"sales.create", "orders.create"}

    def cashier_permissions(user_id, permission, business_id=None):
        if permission not in permissions:
            raise APIError("Forbidden for cashier role.", 403, "business_permission_denied")
        return {"id": business_id or "business-1"}

    monkeypatch.setattr(services, "require_permission", cashier_permissions)
    sale = services.record_sale("cashier-1", {
        "items": [{"product_id": str(commerce_db["product_id"]), "quantity": 1}],
        "amount": 1,
        "payment_method": "cash",
        "idempotency_key": "cashier-pos-sale-0001",
    })

    assert sale["amount"] == 150.25
    order = commerce_db["orders"].find_one({"_id": ObjectId(sale["order_id"])})
    assert order["status"] == "completed"
    assert order["inventory_status"] == "consumed"
    assert commerce_db["product"]["stock_quantity"] == 4
    assert commerce_db["product"]["reserved_quantity"] == 0

def test_zero_delta_stock_set_still_records_idempotency_and_cannot_be_reapplied_later(commerce_db):
    first = services.inventory_adjustment(
        "owner-1",
        str(commerce_db["product_id"]),
        {
            "movement_type": "set",
            "quantity": 5,
            "reason": "opening_count_confirmed",
            "idempotency_key": "stock-set-noop-0001",
        },
    )
    replay = services.inventory_adjustment(
        "owner-1",
        str(commerce_db["product_id"]),
        {
            "movement_type": "set",
            "quantity": 5,
            "reason": "opening_count_confirmed",
            "idempotency_key": "stock-set-noop-0001",
        },
    )

    assert first["movement"]["id"] == replay["movement"]["id"]
    assert first["replayed"] is False
    assert replay["replayed"] is True
    assert first["movement"]["previous_stock_quantity"] == 5
    assert first["movement"]["new_stock_quantity"] == 5
    assert len(commerce_db["movements"].documents) == 1

    # Even a no-op set consumed the idempotency key. It cannot later be reused
    # to overwrite a different stock state after another transaction occurs.
    commerce_db["products"].documents[0]["stock_quantity"] = 4
    with pytest.raises(APIError) as raised:
        services.inventory_adjustment(
            "owner-1",
            str(commerce_db["product_id"]),
            {
                "movement_type": "set",
                "quantity": 6,
                "reason": "opening_count_confirmed",
                "idempotency_key": "stock-set-noop-0001",
            },
        )
    assert raised.value.code == "idempotency_key_reused"
    assert commerce_db["products"].documents[0]["stock_quantity"] == 4

