from __future__ import annotations

import sys
import types

from flask import Flask, g, jsonify

# Route contract tests must not open a real MongoDB connection.
if "backend.db" not in sys.modules:
    _test_db_module = types.ModuleType("backend.db")

    class _ImportOnlyCollection:
        def __init__(self, name):
            self.name = name

    class _ImportOnlyDatabase:
        def get_collection(self, name):
            return _ImportOnlyCollection(name)

    _test_db_module.db = _ImportOnlyDatabase()
    _test_db_module.get_db = lambda: _test_db_module.db
    sys.modules["backend.db"] = _test_db_module

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.biashara import routes


def authenticated_client():
    app = Flask(__name__)
    app.register_blueprint(
        routes.biashara_bp,
        url_prefix="/api/jumuiya/biashara",
    )

    @app.before_request
    def attach_test_identity():
        g.jumuiya_user = {"id": "member-123"}

    @app.errorhandler(APIError)
    def handle_api_error(error):
        return (
            jsonify(
                success=False,
                error={"code": error.code, "message": error.message},
            ),
            error.status_code,
        )

    return app.test_client()


def test_list_services_passes_authenticated_business_context(monkeypatch):
    called = {}

    def fake_list(user_id, status, search, limit):
        called.update(user_id=user_id, status=status, search=search, limit=limit)
        return [{"id": "service-1", "name": "Consulting", "price": 1200}]

    monkeypatch.setattr(routes.services, "list_services", fake_list)
    response = authenticated_client().get(
        "/api/jumuiya/biashara/services?status=active&search=consult&limit=20"
    )

    assert response.status_code == 200
    assert called == {
        "user_id": "member-123",
        "status": "active",
        "search": "consult",
        "limit": 20,
    }
    assert response.get_json()["data"][0]["id"] == "service-1"


def test_create_service_validates_and_persists_service_payload(monkeypatch):
    called = {}

    def fake_create(user_id, payload):
        called.update(user_id=user_id, payload=payload)
        return {"id": "service-2", **payload}

    monkeypatch.setattr(routes.services, "create_service", fake_create)
    response = authenticated_client().post(
        "/api/jumuiya/biashara/services",
        json={
            "name": "Equipment repair",
            "description": "Repair and maintenance",
            "category": "Maintenance",
            "service_type": "repair",
            "price": 2500,
            "currency": "KES",
            "unit": "visit",
            "duration_minutes": 90,
            "status": "active",
        },
    )

    assert response.status_code == 201
    assert called["user_id"] == "member-123"
    assert called["payload"]["name"] == "Equipment repair"
    assert called["payload"]["price"] == 2500.0
    assert response.get_json()["data"]["id"] == "service-2"


def test_archive_service_calls_business_scoped_service_delete(monkeypatch):
    called = {}

    def fake_delete(user_id, service_id):
        called.update(user_id=user_id, service_id=service_id)
        return {"id": service_id, "status": "deleted"}

    monkeypatch.setattr(routes.services, "delete_service", fake_delete)
    response = authenticated_client().delete(
        "/api/jumuiya/biashara/services/service-7"
    )

    assert response.status_code == 200
    assert called == {"user_id": "member-123", "service_id": "service-7"}
    assert response.get_json()["data"]["status"] == "deleted"


def test_public_customer_order_uses_public_order_service(monkeypatch):
    called = {}

    def fake_public_order(slug, payload):
        called.update(slug=slug, payload=payload)
        return {
            "accepted": True,
            "order": {
                "id": "order-1",
                "status": "pending",
                "inventory_status": "reserved",
            },
        }

    monkeypatch.setattr(routes.services, "create_public_biashara_order", fake_public_order)
    response = authenticated_client().post(
        "/api/jumuiya/biashara/public/demo-business/orders",
        json={
            "name": "Customer",
            "phone": "+254712345678",
            "items": [{"product_id": "product-1", "quantity": 2}],
            "notes": "Deliver tomorrow",
        },
    )

    assert response.status_code == 201
    assert called["slug"] == "demo-business"
    assert called["payload"]["items"][0]["quantity"] == 2
    assert response.get_json()["data"]["order"]["inventory_status"] == "reserved"
