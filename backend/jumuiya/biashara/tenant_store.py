"""Per-company Biashara storage on the existing MongoDB cluster.

The central RevelaCode database remains the identity/tenant registry. Operational
Biashara collections are stored in a database dedicated to each business. Legacy
records are copied idempotently on first verified access; source records are
retained until a separately reviewed migration cleanup is approved.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timezone

from flask import g, has_request_context
from pymongo import ASCENDING, DESCENDING, ReplaceOne

from backend.db import client, get_db
from backend.jumuiya.core.database import collection as core_collection
from backend.jumuiya.core.errors import APIError


TENANT_DB_PREFIX = "revelacode_biz_"
TENANT_REGISTRY = "jumuiya_biashara_tenants"
DOMAIN_REGISTRY = "jumuiya_biashara_domains"

# These are operational records, not global identity, membership, or business
# directory records. They move to the company's database as part of migration.
TENANT_COLLECTIONS = frozenset({
    "jumuiya_products",
    "jumuiya_business_services",
    "jumuiya_customers",
    "jumuiya_orders",
    "jumuiya_sales",
    "jumuiya_expenses",
    "jumuiya_inventory_movements",
    "jumuiya_business_website_inquiries",
    "jumuiya_biashara_invoices",
    "jumuiya_biashara_payment_allocations",
    "jumuiya_biashara_automation_rules",
    "jumuiya_biashara_sync_jobs",
    "jumuiya_factory_production_batches",
    "jumuiya_factory_quality_checks",
    "jumuiya_factory_machines",
    "jumuiya_factory_machine_readings",
    "jumuiya_factory_alerts",
})

LEGACY_CENTRAL_COLLECTIONS = frozenset({
    "jumuiya_businesses",
    "jumuiya_biashara_active_business",
    "jumuiya_biashara_memberships",
    "jumuiya_biashara_invitations",
})

def _now():
    return datetime.now(timezone.utc)

def _business_key(business_id):
    value = str(business_id or "").strip()
    if not value or len(value) > 128:
        raise APIError("A valid business identifier is required.", 422, "invalid_business_id")
    return value

def database_name_for_business(business_id):
    """Derive a stable, Mongo-safe database name; never use a user slug as a DB name."""
    key = _business_key(business_id)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return TENANT_DB_PREFIX + digest

def _registry():
    registry = core_collection(TENANT_REGISTRY)
    registry.create_index([("business_id", ASCENDING)], unique=True, name="uq_biashara_tenant_business")
    return registry

def _ensure_tenant_indexes(database):
    for name in TENANT_COLLECTIONS:
        target = database[name]
        target.create_index([("business_id", ASCENDING), ("created_at", DESCENDING)],
                            name="ix_biashara_business_created")
    database["jumuiya_factory_production_batches"].create_index(
        [("business_id", ASCENDING), ("batch_number", ASCENDING)],
        unique=True, name="uq_factory_business_batch",
    )
    database["jumuiya_factory_production_batches"].create_index(
        [("business_id", ASCENDING), ("idempotency_key", ASCENDING)],
        unique=True, partialFilterExpression={"idempotency_key": {"$type": "string"}},
        name="uq_factory_batch_idempotency",
    )
    database["jumuiya_factory_machines"].create_index(
        [("business_id", ASCENDING), ("machine_code", ASCENDING)],
        unique=True, name="uq_factory_business_machine",
    )
    database["jumuiya_factory_machines"].create_index(
        [("business_id", ASCENDING), ("idempotency_key", ASCENDING)],
        unique=True, partialFilterExpression={"idempotency_key": {"$type": "string"}},
        name="uq_factory_machine_idempotency",
    )
    database["jumuiya_factory_quality_checks"].create_index(
        [("business_id", ASCENDING), ("batch_id", ASCENDING)],
        unique=True, name="uq_factory_quality_batch",
    )
    database["jumuiya_factory_quality_checks"].create_index(
        [("business_id", ASCENDING), ("idempotency_key", ASCENDING)],
        unique=True, partialFilterExpression={"idempotency_key": {"$type": "string"}},
        name="uq_factory_quality_idempotency",
    )
    database["jumuiya_factory_machine_readings"].create_index(
        [("business_id", ASCENDING), ("machine_id", ASCENDING), ("recorded_at", DESCENDING)],
        name="ix_factory_machine_readings",
    )
    database["jumuiya_factory_machine_readings"].create_index(
        [("business_id", ASCENDING), ("idempotency_key", ASCENDING)],
        unique=True, partialFilterExpression={"idempotency_key": {"$type": "string"}},
        name="uq_factory_reading_idempotency",
    )
    database["jumuiya_factory_alerts"].create_index(
        [("business_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
        name="ix_factory_alerts_status_created",
    )

def _copy_legacy_business_records(database, business_id):
    source_db = get_db()
    copied = 0
    for name in TENANT_COLLECTIONS:
        source = source_db[name]
        destination = database[name]
        documents = list(source.find({"business_id": business_id}))
        if not documents:
            continue
        operations = [ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) for doc in documents]
        result = destination.bulk_write(operations, ordered=False)
        copied += result.upserted_count + result.modified_count
    return copied

def ensure_business_tenant(business_id, *, business_slug=None, migrate_legacy=True):
    """Create or resume a business database and its central registry record.

    Provisioning is idempotent. Migration copies each business-scoped source
    document with its original _id and never deletes shared-database records.
    """
    key = _business_key(business_id)
    db_name = database_name_for_business(key)
    registry = _registry()
    now = _now()
    existing = registry.find_one({"business_id": key})
    if existing and existing.get("status") == "active" and existing.get("database_name") == db_name:
        database = client[db_name]
        _ensure_tenant_indexes(database)
        return existing

    registry.update_one(
        {"business_id": key},
        {"$setOnInsert": {
            "business_id": key,
            "tenant_id": "biz_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20],
            "database_name": db_name,
            "status": "provisioning",
            "created_at": now,
        }, "$set": {"updated_at": now}},
        upsert=True,
    )
    database = client[db_name]
    metadata = database["jumuiya_tenant_metadata"]
    metadata.update_one(
        {"_id": "tenant"},
        {"$set": {"business_id": key, "database_name": db_name, "schema_version": 1, "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    try:
        copied = _copy_legacy_business_records(database, key) if migrate_legacy else 0
        _ensure_tenant_indexes(database)
        registry.update_one(
            {"business_id": key},
            {"$set": {
                "database_name": db_name,
                "status": "active",
                "migration_status": "complete" if migrate_legacy else "new_tenant",
                "legacy_documents_copied": copied,
                "updated_at": _now(),
            }},
        )
    except Exception as exc:
        registry.update_one(
            {"business_id": key},
            {"$set": {"status": "migration_failed", "migration_error": str(exc)[:500], "updated_at": _now()}},
        )
        raise

    # Subdomains are registered as pending until wildcard DNS and the serving
    # platform are configured and the hostname has been verified.
    if business_slug:
        slug = re.sub(r"[^a-z0-9-]", "", str(business_slug).lower()).strip("-")
        if slug:
            hostname = slug + ".revelacode.co.ke"
            core_collection(DOMAIN_REGISTRY).update_one(
                {"hostname": hostname},
                {"$setOnInsert": {
                    "hostname": hostname,
                    "business_id": key,
                    "tenant_id": "biz_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20],
                    "verification_token": secrets.token_urlsafe(24),
                    "status": "pending_dns",
                    "verification_status": "pending",
                    "created_at": _now(),
                }, "$set": {"updated_at": _now()}},
                upsert=True,
            )
    return registry.find_one({"business_id": key})

def set_business_tenant_context(business_id, *, business_slug=None, migrate_legacy=True):
    """Attach the trusted resolved tenant to this request after membership checks."""
    info = ensure_business_tenant(
        business_id,
        business_slug=business_slug,
        migrate_legacy=migrate_legacy,
    )
    if has_request_context():
        g.biashara_business_id = _business_key(business_id)
        g.biashara_tenant_database = info["database_name"]
        g.biashara_tenant_id = info.get("tenant_id")
    return info

def current_business_id():
    if not has_request_context():
        return None
    return getattr(g, "biashara_business_id", None)

def tenant_database(business_id=None):
    key = business_id or current_business_id()
    if not key:
        raise APIError("A verified business context is required.", 409, "business_context_required")
    info = _registry().find_one({"business_id": _business_key(key), "status": "active"})
    if not info:
        raise APIError("The business database is not provisioned or its migration is incomplete.", 503,
                       "business_tenant_unavailable")
    expected = database_name_for_business(key)
    if info.get("database_name") != expected:
        raise APIError("The business database registry is inconsistent.", 503, "business_tenant_invalid")
    return client[expected]

def tenant_collection(name, business_id=None):
    if name not in TENANT_COLLECTIONS:
        raise ValueError("Collection is not on the Biashara tenant allow-list.")
    return tenant_database(business_id)[name]

def biashara_collection(name):
    """Use the tenant DB for company records and the central DB for shared registries."""
    if name in TENANT_COLLECTIONS:
        business_id = current_business_id()
        if business_id:
            return tenant_collection(name, business_id)
    return core_collection(name)
