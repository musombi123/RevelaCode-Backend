from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.jumuiya.biashara import tenant_store
from backend.jumuiya.biashara.integrations import _etims_status, _whatsapp_status
from backend.jumuiya.biashara.templates import has_permission, normalize_role, template_config
from backend.jumuiya.biashara.schemas import product_payload
from backend.jumuiya.core.errors import APIError


def test_business_database_name_is_stable_hashed_and_within_mongodb_limit():
    first = tenant_store.database_name_for_business("65f123456789abcdef123456")
    again = tenant_store.database_name_for_business("65f123456789abcdef123456")
    second = tenant_store.database_name_for_business("65f123456789abcdef123457")

    assert first == again
    assert first.startswith("rcb_")
    assert re.fullmatch(r"rcb_[a-f0-9]{32}", first)
    assert len(first.encode("utf-8")) <= 38
    assert first != second
    assert "sarefactory" not in tenant_store.database_name_for_business("sarefactory")


def test_failed_legacy_tenant_registry_can_resume_but_completed_tenants_are_not_repointed():
    business_id = "65f123456789abcdef123456"
    legacy_name = tenant_store._legacy_database_name_for_business(business_id)
    now = datetime.now(timezone.utc)

    failed = {
        "database_name": legacy_name,
        "status": "migration_failed",
        "migration_status": "pending",
    }
    expired_migration = {
        "database_name": legacy_name,
        "status": "migrating",
        "migration_status": "pending",
        "migration_lock_until": now - timedelta(seconds=1),
    }
    active_migration = {
        "database_name": legacy_name,
        "status": "migrating",
        "migration_status": "pending",
        "migration_lock_until": now + timedelta(minutes=5),
    }
    completed = {
        "database_name": legacy_name,
        "status": "active",
        "migration_status": "complete",
    }

    assert tenant_store._legacy_tenant_registry_can_resume(failed, legacy_name, now)
    assert tenant_store._legacy_tenant_registry_can_resume(expired_migration, legacy_name, now)
    assert not tenant_store._legacy_tenant_registry_can_resume(active_migration, legacy_name, now)
    assert not tenant_store._legacy_tenant_registry_can_resume(completed, legacy_name, now)


def test_tenant_collection_fails_closed_without_a_verified_request_context(monkeypatch):
    monkeypatch.setattr(tenant_store, "current_business_id", lambda: None)
    monkeypatch.setattr(
        tenant_store,
        "core_collection",
        lambda name: pytest.fail("Tenant-owned data must never fall back to the shared database."),
    )

    with pytest.raises(APIError) as error:
        tenant_store.biashara_collection("jumuiya_products")

    assert error.value.code == "business_context_required"


def test_central_business_registry_stays_in_the_core_database(monkeypatch):
    expected = object()
    monkeypatch.setattr(tenant_store, "core_collection", lambda name: expected)

    assert tenant_store.biashara_collection("jumuiya_businesses") is expected
    assert tenant_store.biashara_collection("jumuiya_biashara_memberships") is expected


def test_only_verified_and_active_company_domain_records_resolve(monkeypatch):
    record = {
        "hostname": "sarefactory.revelacode.co.ke",
        "business_id": "business-123",
        "status": "active",
        "verification_status": "verified",
    }
    registry = SimpleNamespace(find_one=lambda query: record if query["hostname"] == record["hostname"] else None)
    monkeypatch.setattr(tenant_store, "_domain_registry", lambda: registry)

    assert tenant_store.business_id_for_hostname("https://SAREFACTORY.revelacode.co.ke") == "business-123"
    assert tenant_store.business_id_for_origin("https://sarefactory.revelacode.co.ke") == "business-123"
    assert tenant_store.business_id_for_hostname("not a hostname with spaces") is None


@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [
        ("teacher", "employee"),
        ("principal", "operations_manager"),
        ("bursar", "accountant"),
        ("store", "store_keeper"),
        ("factory-floor", "factory_floor_lead"),
        ("owner", "ceo"),
    ],
)
def test_elimu_and_biashara_role_aliases_normalize_to_company_roles(legacy, canonical):
    assert normalize_role(legacy) == canonical


def test_factory_role_permissions_are_server_side_and_limited():
    assert has_permission("accountant", "invoices.allocate")
    assert has_permission("factory_floor_lead", "production.create")
    assert has_permission("factory_floor_lead", "machines.readings.create")
    assert not has_permission("factory_floor_lead", "finance.view")
    assert not has_permission("sales_agent", "hr.employees.manage")
    assert has_permission("ceo", "finance.view")


@pytest.mark.parametrize("template", ["general", "retail_shop", "hardware", "factory", "salon", "professional_services"])
def test_company_templates_enable_common_business_modules(template):
    config = template_config(template)
    modules = set(config["modules"])

    assert {"sales", "finance", "hr", "mpesa", "etims", "debts", "sync"} <= modules


def test_factory_template_adds_production_machine_and_quality_modules():
    modules = set(template_config("factory")["modules"])

    assert {"production", "machines", "quality", "automations"} <= modules


def test_school_template_is_a_biashara_business_not_an_elimu_launcher():
    modules = set(template_config("school")["modules"])

    assert {"sales", "customers", "orders", "finance", "hr", "team", "website", "sync"} <= modules
    assert "elimu" not in modules


def test_unknown_industry_template_is_rejected():
    assert template_config("unknown-industry") is None


def test_etims_readiness_never_claims_submission_enabled_without_certification(monkeypatch):
    for key in (
        "BIASHARA_ETIMS_MODE",
        "BIASHARA_ETIMS_ADAPTER",
        "BIASHARA_ETIMS_BASE_URL",
        "BIASHARA_ETIMS_CERTIFICATION_REFERENCE",
        "BIASHARA_ETIMS_CERTIFIED",
    ):
        monkeypatch.delenv(key, raising=False)

    status = _etims_status()

    assert status["state"] == "not_configured"
    assert status["submission_enabled"] is False
    assert status["checks"]["certification_flag"] is False


def test_whatsapp_credentials_do_not_imply_business_commands_are_enabled(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "present")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "present")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "present")
    monkeypatch.setenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "present")

    status = _whatsapp_status()

    assert status["state"] == "configuration_present"
    assert status["business_commands_enabled"] is False


def test_product_payload_supports_raw_material_and_finished_goods():
    raw = product_payload({
        "name": "Maize",
        "sku": "RAW-MAIZE",
        "price": 0,
        "cost_price": 85,
        "stock_quantity": 100,
        "unit": "kg",
        "production_type": "raw_material",
    })
    finished = product_payload({
        "name": "Maize flour",
        "sku": "FLOUR-2KG",
        "price": 140,
        "cost_price": 95,
        "stock_quantity": 0,
        "unit": "2kg bag",
        "production_type": "finished_good",
    })

    assert raw["production_type"] == "raw_material"
    assert raw["unit"] == "kg"
    assert raw["cost_price"] == 85.0
    assert finished["production_type"] == "finished_good"
    assert finished["unit"] == "2kg bag"


def test_product_payload_defaults_existing_catalogue_records_to_resale():
    result = product_payload({"name": "Soap", "price": 20})

    assert result["production_type"] == "resale"


def test_product_payload_rejects_unknown_inventory_type():
    with pytest.raises(ValueError, match="production_type must be one of"):
        product_payload({"name": "Unknown", "price": 10, "production_type": "unknown"})



def test_retail_and_factory_templates_include_inventory():
    for template in ("retail_shop", "hardware", "factory"):
        assert "inventory" in template_config(template)["modules"]


def test_professional_services_template_uses_projects_and_invoicing():
    modules = set(template_config("professional_services")["modules"])
    assert {"projects", "invoicing", "finance", "sales"} <= modules
    assert "inventory" not in modules
