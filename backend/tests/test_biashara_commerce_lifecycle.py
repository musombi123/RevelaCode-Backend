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
    from backend.jumuiya.biashara.returns import service as returns_service
    from backend.jumuiya.biashara.inventory import counts as stock_counts
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
        "jumuiya_businesses": FakeCollection([]),
        "jumuiya_customers": FakeCollection([]),
        "jumuiya_orders": FakeCollection([]),
        "jumuiya_sales": FakeCollection([]),
        "jumuiya_inventory_movements": FakeCollection([]),
        "jumuiya_outbox_events": FakeCollection([]),
        "jumuiya_returns": FakeCollection([]),
        "jumuiya_stock_counts": FakeCollection([]),
    }
    monkeypatch.setattr(services, "collection", lambda name: collections[name])
    monkeypatch.setattr(outbox, "collection", lambda name: collections[name])
    monkeypatch.setattr(returns_service, "collection", lambda name: collections[name])
    monkeypatch.setattr(returns_service, "require_permission", lambda user_id, permission, business_id=None: {"id": business_id or "business-1"})
    monkeypatch.setattr(stock_counts, "collection", lambda name: collections[name])
    monkeypatch.setattr(stock_counts, "require_permission", lambda user_id, permission, business_id=None: {"id": business_id or "business-1"})
    monkeypatch.setattr(stock_counts, "dispatch_manifest_for_record", lambda *args, **kwargs: {"enqueued": 1, "pending": 0, "errors": 0})
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

def test_public_storefront_includes_seo_only_for_active_published_business(commerce_db, monkeypatch):
    monkeypatch.setenv("BIASHARA_PUBLIC_BASE_URL", "https://businesses.example.test")
    business_id = ObjectId("64b000000000000000000401")
    commerce_db["jumuiya_businesses"].documents.append({
        "_id": business_id,
        "business_id": str(business_id),
        "slug": "coastal-electronics",
        "name": "Coastal Electronics",
        "description": "Phones and accessories in Mombasa.",
        "phone": "+254700111222",
        "email": "sales@example.test",
        "location": "Kongowea",
        "county": "Mombasa",
        "currency": "KES",
        "logo_url": "https://cdn.example.test/logo.png",
        "status": "active",
        "website": {
            "published": True,
            "headline": "Coastal Electronics",
            "seo_title": "Coastal Electronics | Mombasa",
            "seo_description": "Shop phones and accessories in Mombasa.",
            "hero_image_url": "https://cdn.example.test/hero.png",
            "show_products": False,
            "contact_enabled": False,
            "primary_color": "#1d4ed8",
            "accent_color": "#0f766e",
        },
    })

    result = services.get_public_biashara_website("coastal-electronics")

    assert result["seo"]["canonical_url"] == "https://businesses.example.test/b/coastal-electronics"
    assert result["seo"]["open_graph"]["title"] == "Coastal Electronics | Mombasa"
    assert result["seo"]["structured_data"]["@type"] == "Store"
    assert result["business"]["phone"] == ""
    assert result["business"]["email"] == ""
    assert "telephone" not in result["seo"]["structured_data"]
    assert result["products"] == []


def test_public_storefront_rejects_unpublished_business_before_seo_render(commerce_db):
    business_id = ObjectId("64b000000000000000000402")
    commerce_db["jumuiya_businesses"].documents.append({
        "_id": business_id,
        "slug": "draft-store",
        "name": "Draft Store",
        "status": "active",
        "website": {
            "published": False,
            "headline": "Draft Store",
            "show_products": False,
        },
    })

    with pytest.raises(APIError) as raised:
        services.get_public_biashara_website("draft-store")
    assert raised.value.code == "website_not_found"

def _completed_order_for_return(db, quantity=2):
    created = services.create_order("owner-1", _payload(db, quantity=quantity))
    services.update_order_status("owner-1", created["id"], "confirmed")
    services.update_order_status("owner-1", created["id"], "processing")
    completed = services.update_order_status("owner-1", created["id"], "completed")
    assert completed["status"] == "completed"
    return completed


def test_return_request_reserves_sold_quantity_and_restock_is_idempotent(commerce_db):
    order = _completed_order_for_return(commerce_db, quantity=2)
    original_stock = commerce_db["product"]["stock_quantity"]
    payload = {
        "items": [{"product_id": str(commerce_db["product_id"]), "quantity": 1}],
        "reason": "Customer returned one unopened item",
        "restock": True,
    }

    request_one = returns_service.create_return(
        "owner-1", order["id"], payload, "return-request-0001"
    )
    replay = returns_service.create_return(
        "owner-1", order["id"], payload, "return-request-0001"
    )

    assert request_one["id"] == replay["id"]
    assert request_one["status"] == "requested"
    assert request_one["estimated_merchandise_value_minor"] == 15025
    assert commerce_db["product"]["stock_quantity"] == original_stock

    approved = returns_service.resolve_return("owner-1", request_one["id"], "approve", "Item inspected")
    again = returns_service.resolve_return("owner-1", request_one["id"], "approve", "Item inspected")

    assert approved["status"] == "completed"
    assert approved["restock_status"] == "restocked"
    assert again["status"] == "completed"
    assert commerce_db["product"]["stock_quantity"] == original_stock + 1
    restock_movements = [
        row for row in commerce_db["movements"].documents
        if row.get("reason") == "customer_return_restock"
    ]
    assert len(restock_movements) == 1
    order_after = commerce_db["orders"].find_one({"_id": ObjectId(order["id"])})
    assert order_after["returned_quantities"][str(commerce_db["product_id"])] == 1.0
    assert order_after["return_reserved_quantities"][str(commerce_db["product_id"])] == 0.0


def test_return_quantity_cannot_exceed_sold_units_even_across_requests(commerce_db):
    order = _completed_order_for_return(commerce_db, quantity=1)
    payload = {
        "items": [{"product_id": str(commerce_db["product_id"]), "quantity": 1}],
        "reason": "Package damaged",
        "restock": False,
    }
    first = returns_service.create_return("owner-1", order["id"], payload, "return-capacity-0001")
    assert first["status"] == "requested"

    with pytest.raises(APIError) as raised:
        returns_service.create_return(
            "owner-1",
            order["id"],
            {
                "items": [{"product_id": str(commerce_db["product_id"]), "quantity": 1}],
                "reason": "Second request for same sold unit",
                "restock": False,
            },
            "return-capacity-0002",
        )
    assert raised.value.code == "return_quantity_unavailable"
    saved_order = commerce_db["orders"].find_one({"_id": ObjectId(order["id"])})
    assert saved_order["return_reserved_quantities"][str(commerce_db["product_id"])] == 1.0
    assert len(commerce_db["jumuiya_returns"].documents) == 2
    assert commerce_db["jumuiya_returns"].documents[1]["status"] == "reservation_conflict"


def test_reject_return_releases_reserved_quantity_without_changing_stock(commerce_db):
    order = _completed_order_for_return(commerce_db, quantity=1)
    stock_before = commerce_db["product"]["stock_quantity"]
    result = returns_service.create_return(
        "owner-1",
        order["id"],
        {
            "items": [{"product_id": str(commerce_db["product_id"]), "quantity": 1}],
            "reason": "Customer changed mind",
            "restock": True,
        },
        "return-reject-flow-0001",
    )

    rejected = returns_service.resolve_return("owner-1", result["id"], "reject", "Seal was broken")
    assert rejected["status"] == "rejected"
    assert commerce_db["product"]["stock_quantity"] == stock_before
    order_after = commerce_db["orders"].find_one({"_id": ObjectId(order["id"])})
    assert order_after["return_reserved_quantities"][str(commerce_db["product_id"])] == 0.0
    assert order_after.get("returned_quantities", {}) == {}


def test_refund_review_never_claims_money_moved_and_is_idempotent(commerce_db):
    order = _completed_order_for_return(commerce_db, quantity=1)
    result = returns_service.create_return(
        "owner-1",
        order["id"],
        {
            "items": [{"product_id": str(commerce_db["product_id"]), "quantity": 1}],
            "reason": "Defective item",
            "restock": False,
        },
        "return-refund-review-0001",
    )
    completed = returns_service.resolve_return("owner-1", result["id"], "approve")
    assert completed["status"] == "completed"
    assert completed["restock_status"] == "not_requested"

    refund = returns_service.request_refund_review(
        "owner-1",
        result["id"],
        {"reason": "Owner should verify original receipt and payout route"},
        "refund-review-idem-0001",
    )
    replay = returns_service.request_refund_review(
        "owner-1",
        result["id"],
        {"reason": "Owner should verify original receipt and payout route"},
        "refund-review-idem-0001",
    )

    assert refund["refund_status"] == "requested_manual_review"
    assert refund["refund_request"]["status"] == "requested_manual_review"
    assert refund["refund_request"]["money_moved"] is False
    assert refund["refund_request"]["provider_refund_reference"] is None
    assert replay["refund_request"]["idempotency_key"] == "refund-review-idem-0001"

    with pytest.raises(APIError) as raised:
        returns_service.request_refund_review(
            "owner-1", result["id"], {"reason": "Different request"}, "refund-review-idem-0002"
        )
    assert raised.value.code == "refund_request_exists"


def test_returns_are_scoped_to_selected_business(commerce_db, monkeypatch):
    order = _completed_order_for_return(commerce_db, quantity=1)
    result = returns_service.create_return(
        "owner-1",
        order["id"],
        {
            "items": [{"product_id": str(commerce_db["product_id"]), "quantity": 1}],
            "reason": "Wrong item",
            "restock": False,
        },
        "return-tenant-scope-0001",
    )
    commerce_db["jumuiya_returns"].documents.append({
        "_id": ObjectId("64b000000000000000000099"),
        "business_id": "business-2",
        "idempotency_key": "other-tenant-return",
        "order_id": "other-order",
        "status": "requested",
        "created_at": result["created_at"],
    })

    assert [item["id"] for item in returns_service.list_returns("owner-1")] == [result["id"]]
    with pytest.raises(APIError) as raised:
        returns_service.get_return("owner-1", "64b000000000000000000099")
    assert raised.value.code == "return_not_found"

def test_stock_count_is_idempotent_and_zero_variance_records_no_fake_movement(commerce_db):
    first = stock_counts.create_count_session("owner-1", {}, "stock-count-start-0001")
    replay = stock_counts.create_count_session("owner-1", {}, "stock-count-start-0001")
    assert first["id"] == replay["id"]
    assert first["status"] == "in_progress"
    assert first["items"][0]["system_stock_quantity"] == 5
    assert first["items"][0]["system_reserved_quantity"] == 0
    assert len(commerce_db["jumuiya_stock_counts"].documents) == 1

    counted = stock_counts.record_count(
        "owner-1", first["id"], str(commerce_db["product_id"]), 5
    )
    assert counted["items"][0]["count_status"] == "counted"
    assert commerce_db["product"]["stock_quantity"] == 5

    done = stock_counts.finalize_count_session("owner-1", first["id"])
    replay_done = stock_counts.finalize_count_session("owner-1", first["id"])
    assert done["status"] == "completed"
    assert done["items"][0]["count_status"] == "no_adjustment"
    assert done["items"][0]["variance_quantity"] == 0
    assert replay_done["status"] == "completed"
    assert commerce_db["product"]["stock_quantity"] == 5
    assert not [
        row for row in commerce_db["movements"].documents
        if row.get("reason") == "cycle_count_reconciliation"
    ]


def test_stock_count_applies_variance_once_through_inventory_movement_ledger(commerce_db):
    session = stock_counts.create_count_session("owner-1", {}, "stock-count-variance-0001")
    product_id = str(commerce_db["product_id"])
    stock_counts.record_count("owner-1", session["id"], product_id, 3)

    finalized = stock_counts.finalize_count_session("owner-1", session["id"])
    replay = stock_counts.finalize_count_session("owner-1", session["id"])

    assert finalized["status"] == "completed"
    line = finalized["items"][0]
    assert line["count_status"] == "applied"
    assert line["variance_quantity"] == -2
    assert line["movement_id"]
    assert replay["items"][0]["movement_id"] == line["movement_id"]
    assert commerce_db["product"]["stock_quantity"] == 3
    movements = [
        row for row in commerce_db["movements"].documents
        if row.get("reason") == "cycle_count_reconciliation"
    ]
    assert len(movements) == 1
    assert movements[0]["movement_type"] == "set"
    assert movements[0]["previous_stock_quantity"] == 5
    assert movements[0]["new_stock_quantity"] == 3
    assert movements[0]["idempotency_key"] == line["adjustment_idempotency_key"]


def test_stock_count_detects_concurrent_stock_change_and_requires_recount(commerce_db):
    session = stock_counts.create_count_session("owner-1", {}, "stock-count-stale-0001")
    product_id = str(commerce_db["product_id"])
    stock_counts.record_count("owner-1", session["id"], product_id, 4)

    # A sale/delivery changes the authoritative balance after the physical count
    # started. Finalization must not overwrite it using the stale observed value.
    services.inventory_adjustment("owner-1", product_id, {
        "movement_type": "add",
        "quantity": 1,
        "reason": "supplier_delivery",
        "idempotency_key": "stock-count-stale-external-0001",
    })
    assert commerce_db["product"]["stock_quantity"] == 6

    with pytest.raises(APIError) as stale:
        stock_counts.finalize_count_session("owner-1", session["id"])
    assert stale.value.code == "stock_count_snapshot_stale"
    conflict = stock_counts.get_count_session("owner-1", session["id"])
    assert conflict["status"] == "conflict"
    assert conflict["items"][0]["count_status"] == "conflict"
    assert commerce_db["product"]["stock_quantity"] == 6

    refreshed = stock_counts.recount_item("owner-1", session["id"], product_id)
    assert refreshed["status"] == "in_progress"
    assert refreshed["items"][0]["system_stock_quantity"] == 6
    assert refreshed["items"][0]["count_attempt"] == 2
    stock_counts.record_count("owner-1", session["id"], product_id, 6)
    completed = stock_counts.finalize_count_session("owner-1", session["id"])
    assert completed["status"] == "completed"
    assert commerce_db["product"]["stock_quantity"] == 6
    assert len([
        row for row in commerce_db["movements"].documents
        if row.get("reason") == "cycle_count_reconciliation"
    ]) == 0


def test_stock_count_cannot_set_physical_stock_below_open_order_reservations(commerce_db):
    order = services.create_order("owner-1", _payload(commerce_db, quantity=2))
    session = stock_counts.create_count_session(
        "owner-1",
        {"product_ids": [str(commerce_db["product_id"])]},
        "stock-count-reserved-0001",
    )
    assert session["items"][0]["system_reserved_quantity"] == 2
    stock_counts.record_count("owner-1", session["id"], str(commerce_db["product_id"]), 1)

    with pytest.raises(APIError) as raised:
        stock_counts.finalize_count_session("owner-1", session["id"])
    assert raised.value.code == "stock_below_reserved"
    refreshed = stock_counts.get_count_session("owner-1", session["id"])
    assert refreshed["status"] == "conflict"
    assert refreshed["items"][0]["conflict_code"] == "stock_below_reserved"
    assert commerce_db["product"]["stock_quantity"] == 5
    assert commerce_db["product"]["reserved_quantity"] == 2
    assert order["status"] == "pending"


def test_stock_count_idempotency_key_rejects_changed_product_selection(commerce_db):
    first = stock_counts.create_count_session(
        "owner-1",
        {},
        "stock-count-selection-0001",
    )
    # Both selections are valid, but the same key cannot be reused to select
    # a different scope (all active products versus an explicit product list).
    with pytest.raises(APIError) as raised:
        stock_counts.create_count_session(
            "owner-1",
            {"product_ids": [str(commerce_db["product_id"])]},
            "stock-count-selection-0001",
        )
    assert raised.value.code == "idempotency_key_reused"
    assert first["status"] == "in_progress"
    assert len(commerce_db["jumuiya_stock_counts"].documents) == 1

