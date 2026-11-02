from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from bson import ObjectId

from backend.jumuiya.biashara import whatsapp


def test_whatsapp_phone_normalization_supports_kenyan_formats():
    assert whatsapp.normalize_phone("0712345678") == "+254712345678"
    assert whatsapp.normalize_phone("254712345678") == "+254712345678"
    assert whatsapp.normalize_phone("+254712345678") == "+254712345678"
    assert whatsapp.normalize_phone("not-a-phone") == ""


def test_whatsapp_phone_registry_uses_hash_not_plaintext():
    digest = whatsapp.phone_hash("0712345678")

    assert digest == hashlib.sha256(b"+254712345678").hexdigest()
    assert "+254712345678" not in digest
    assert whatsapp.phone_hash("invalid") == ""


def test_meta_webhook_signature_validation_uses_constant_time_hmac():
    body = b'{"object":"whatsapp_business_account"}'
    secret = "unit-test-secret"
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert whatsapp.valid_meta_signature(body, signature, secret)
    assert not whatsapp.valid_meta_signature(body, signature + "x", secret)
    assert not whatsapp.valid_meta_signature(body, "", secret)
    assert not whatsapp.valid_meta_signature(body, signature, "")


def test_help_command_only_lists_read_only_biashara_reports():
    context = {"business": {"name": "Sare Factory"}, "business_id": "biz-1", "role": "ceo"}
    reply = whatsapp.build_command_reply(context, "HELP")

    assert "sales today" in reply
    assert "stock alerts" in reply
    assert "production today" in reply
    assert "read-only" in reply.lower()


def test_sales_report_checks_role_before_reading_tenant_data(monkeypatch):
    def forbidden_collection(*args, **kwargs):
        raise AssertionError("An unauthorized role must not read tenant data.")

    monkeypatch.setattr(whatsapp, "tenant_collection", forbidden_collection)
    context = {"business": {"name": "Sare Factory"}, "business_id": "biz-1", "role": "employee"}

    reply = whatsapp.build_command_reply(context, "sales today")

    assert "does not permit" in reply


def test_sales_today_report_is_company_scoped_and_uses_nairobi_day(monkeypatch):
    now = datetime.now(timezone.utc)
    fake_records = [
        {
            "business_id": "biz-1",
            "amount": 120000,
            "created_at": now,
            "items": [{"product_name": "Unga", "quantity": 10}],
        },
        {
            "business_id": "biz-1",
            "amount": 25000,
            "created_at": now,
            "items": [{"product_name": "Unga", "quantity": 2}, {"name": "Rice", "quantity": 3}],
        },
    ]

    class FakeCursor:
        def limit(self, count):
            assert count == 5000
            return fake_records

    class FakeSales:
        def find(self, query):
            assert query["business_id"] == "biz-1"
            assert query["created_at"]["$gte"] < query["created_at"]["$lt"]
            return FakeCursor()

    monkeypatch.setattr(
        whatsapp,
        "tenant_collection",
        lambda name, business_id: FakeSales() if name == "jumuiya_sales" and business_id == "biz-1" else None,
    )
    context = {"business": {"name": "Sare Factory"}, "business_id": "biz-1", "role": "ceo"}

    reply = whatsapp.build_command_reply(context, "sales today")

    assert "Revenue: KSh 145,000.00" in reply
    assert "Transactions: 2" in reply
    assert "Top product: Unga (12)" in reply


def test_stock_and_production_commands_check_distinct_permissions(monkeypatch):
    def forbidden_collection(*args, **kwargs):
        raise AssertionError("Unauthorized report access must be blocked before reading.")

    monkeypatch.setattr(whatsapp, "tenant_collection", forbidden_collection)
    context = {"business": {"name": "Sare Factory"}, "business_id": "biz-1", "role": "sales_agent"}

    assert "does not permit" in whatsapp.build_command_reply(context, "stock alerts")
    assert "does not permit" in whatsapp.build_command_reply(context, "production today")


def test_command_parser_does_not_execute_unrecognized_actions():
    context = {"business": {"name": "Sare Factory"}, "business_id": "biz-1", "role": "ceo"}

    reply = whatsapp.build_command_reply(context, "delete employee 123")

    assert "do not recognize" in reply.lower()
    assert "employee" not in reply.lower() or "read-only" in reply.lower()



def test_linked_company_owner_can_be_resolved_without_changing_company_role(monkeypatch):
    employee_id = ObjectId()
    digest = whatsapp.phone_hash("0712345678")
    identity = {
        "business_id": "biz-owner",
        "employee_id": str(employee_id),
        "user_id": "owner-user",
        "phone_hash": digest,
        "status": "active",
    }

    class FakeCursor:
        def limit(self, count):
            assert count == 3
            return [identity]

    class FakeRegistry:
        def find(self, query):
            assert query == {"phone_hash": digest, "status": "active"}
            return FakeCursor()

    class FakeEmployees:
        def find_one(self, query):
            assert query == {
                "_id": employee_id,
                "business_id": "biz-owner",
                "user_id": "owner-user",
                "status": "active",
            }
            return {
                "_id": employee_id,
                "business_id": "biz-owner",
                "user_id": "owner-user",
                "phone": "0712345678",
                "status": "active",
            }

    monkeypatch.setattr(whatsapp, "ensure_whatsapp_identity_indexes", lambda: None)
    monkeypatch.setattr(whatsapp, "core_collection", lambda name: FakeRegistry())
    monkeypatch.setattr(
        whatsapp,
        "resolve_business_access",
        lambda user_id, business_id: {
            "business": {"_id": "biz-owner", "name": "Sare Factory", "slug": "sarefactory", "status": "active", "verification_status": "verified"},
            "role": "ceo",
            "is_owner": True,
            "membership": None,
        } if user_id == "owner-user" and business_id == "biz-owner" else None,
    )
    monkeypatch.setattr(whatsapp, "set_business_tenant_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(whatsapp, "tenant_collection", lambda name, business_id: FakeEmployees())

    resolved, error = whatsapp._resolve_employee("+254712345678")

    assert error == ""
    assert resolved["role"] == "owner"
    assert resolved["user_id"] == "owner-user"
    assert resolved["employee"]["_id"] == employee_id
