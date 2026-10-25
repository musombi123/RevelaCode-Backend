from copy import deepcopy
from types import SimpleNamespace

import pytest
from bson import ObjectId

from backend.jumuiya.biashara import services
from backend.jumuiya.core.errors import APIError


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = [deepcopy(doc) for doc in (documents or [])]

    def find_one(self, query):
        for doc in self.documents:
            if "_id" in query and str(doc.get("_id")) != str(query["_id"]):
                continue
            if "business_id" in query and str(doc.get("business_id")) != str(query["business_id"]):
                continue
            if "status" in query and doc.get("status") != query["status"]:
                continue
            if "owner_user_id" in query and str(doc.get("owner_user_id")) != str(query["owner_user_id"]):
                continue
            return deepcopy(doc)
        return None

    def insert_one(self, document):
        created = deepcopy(document)
        created["_id"] = created.get("_id") or ObjectId()
        self.documents.append(created)
        return SimpleNamespace(inserted_id=created["_id"])

    def find_one_and_update(self, query, update, return_document=None):
        for doc in self.documents:
            matches = True
            for key, expected in query.items():
                if isinstance(expected, dict) and "$gte" in expected:
                    if float(doc.get(key, 0) or 0) < float(expected["$gte"]):
                        matches = False
                        break
                elif str(doc.get(key)) != str(expected):
                    matches = False
                    break
            if not matches:
                continue
            for key, value in update.get("$inc", {}).items():
                doc[key] = float(doc.get(key, 0) or 0) + float(value)
            doc.update(deepcopy(update.get("$set", {})))
            for key, value in update.get("$push", {}).items():
                doc.setdefault(key, []).append(deepcopy(value))
            return deepcopy(doc)
        return None


@pytest.fixture
def commerce_db(monkeypatch):
    product_id = ObjectId("64b000000000000000000001")
    product = {
        "_id": product_id,
        "business_id": "business-1",
        "name": "Original catalogue item",
        "sku": "SKU-001",
        "price": 150.25,
        "currency": "KES",
        "stock_quantity": 5,
        "status": "active",
    }
    products = FakeCollection([product])
    customers = FakeCollection([])
    orders = FakeCollection([])
    collections = {
        "jumuiya_products": products,
        "jumuiya_customers": customers,
        "jumuiya_orders": orders,
    }
    monkeypatch.setattr(services, "collection", lambda name: collections[name])
    monkeypatch.setattr(services, "_require_business", lambda user_id, allowed_roles=None: {
        "id": "business-1",
        "currency": "KES",
    })
    monkeypatch.setattr(services, "log_action", lambda *args, **kwargs: None)
    return {
        "product_id": product_id,
        "product": product,
        "products": products,
        "customers": customers,
        "orders": orders,
    }


def test_order_uses_server_catalogue_price_and_ignores_client_total(commerce_db):
    result = services.create_order("owner-1", {
        "items": [{
            "product_id": str(commerce_db["product_id"]),
            "quantity": 2,
            "unit_price": 0.01,
            "name": "Forged client name",
        }],
        "total_amount": 0.02,
        "currency": "USD",
        "notes": "Website/manual order",
    })

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
    # Accepted pending orders reserve stock immediately.
    assert commerce_db["product"]["stock_quantity"] == 3


def test_order_rejects_quantity_above_current_stock(commerce_db):
    with pytest.raises(APIError, match="Insufficient stock"):
        services.create_order("owner-1", {
            "items": [{
                "product_id": str(commerce_db["product_id"]),
                "quantity": 6,
            }],
            "total_amount": 900.0,
        })

    assert commerce_db["orders"].documents == []


def test_order_status_transition_must_follow_lifecycle(commerce_db):
    order_id = ObjectId("64b000000000000000000002")
    commerce_db["orders"].documents.append({
        "_id": order_id,
        "business_id": "business-1",
        "status": "pending",
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
        "status_history": [{"from": None, "to": "pending"}],
    })

    services.update_order_status("owner-1", str(order_id), "confirmed")
    services.update_order_status("owner-1", str(order_id), "processing")
    result = services.update_order_status("owner-1", str(order_id), "completed")

    assert result["status"] == "completed"
    assert [item["to"] for item in result["status_history"]] == [
        "pending", "confirmed", "processing", "completed"
    ]


def test_order_payload_does_not_require_client_calculated_total():
    from jumuiya.biashara.schemas import order_payload

    result = order_payload({
        "items": [{"product_id": "64b000000000000000000001", "quantity": 1}],
    })
    assert result["total_amount"] == 0.0
