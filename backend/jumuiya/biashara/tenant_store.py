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
from datetime import datetime, timedelta, timezone

from flask import g, has_request_context
from urllib.parse import urlsplit
from pymongo import ASCENDING, DESCENDING, ReplaceOne

from backend.db import client, get_db
from backend.jumuiya.core.database import collection as core_collection
from backend.jumuiya.core.errors import APIError


TENANT_DB_PREFIX = "revelacode_biz_"
TENANT_REGISTRY = "jumuiya_biashara_tenants"
DOMAIN_REGISTRY = "jumuiya_biashara_domains"
TENANT_SCHEMA_VERSION = 2
MIGRATION_LOCK_MINUTES = 10

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
    "jumuiya_biashara_payment_intents",
    "jumuiya_biashara_automation_rules",
    "jumuiya_biashara_sync_jobs",
    "jumuiya_factory_production_batches",
    "jumuiya_factory_quality_checks",
    "jumuiya_factory_machines",
    "jumuiya_factory_machine_readings",
    "jumuiya_factory_alerts",
    "jumuiya_biashara_employees",
    "jumuiya_biashara_attendance",
    "jumuiya_biashara_leave_requests",
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


def _domain_registry():
    registry = core_collection(DOMAIN_REGISTRY)
    registry.create_index([("hostname", ASCENDING)], unique=True, name="uq_biashara_hostname")
    registry.create_index([("business_id", ASCENDING), ("status", ASCENDING)], name="ix_biashara_domain_business")
    return registry


def business_id_for_hostname(hostname):
    """Resolve only an explicitly verified company hostname; never trust raw host input."""
    raw = str(hostname or "").strip()
    try:
        parsed = urlsplit(raw if "://" in raw else "//" + raw)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    if not host or len(host) > 253:
        return None
    record = _domain_registry().find_one({
        "hostname": host,
        "status": "active",
        "verification_status": "verified",
    })
    return str(record.get("business_id")) if record and record.get("business_id") else None


def business_id_for_origin(origin):
    """Map a browser Origin to a verified tenant; membership is still checked later."""
    return business_id_for_hostname(origin)

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
    database["jumuiya_biashara_payment_intents"].create_index(
        [("business_id", ASCENDING), ("idempotency_key", ASCENDING)],
        unique=True, name="uq_biashara_mpesa_idempotency",
    )
    database["jumuiya_biashara_payment_intents"].create_index(
        [("business_id", ASCENDING), ("invoice_id", ASCENDING), ("active_slot", ASCENDING)],
        unique=True, partialFilterExpression={"active_slot": {"$type": "string"}},
        name="uq_biashara_invoice_active_checkout",
    )
    database["jumuiya_biashara_payment_allocations"].create_index(
        [("business_id", ASCENDING), ("provider_receipt", ASCENDING)],
        unique=True, partialFilterExpression={"provider_receipt": {"$type": "string"}},
        name="uq_biashara_mpesa_receipt",
    )
    database["jumuiya_biashara_employees"].create_index(
        [("business_id", ASCENDING), ("system_id", ASCENDING)],
        unique=True, name="uq_biashara_employee_system_id",
    )
    database["jumuiya_biashara_employees"].create_index(
        [("business_id", ASCENDING), ("user_id", ASCENDING)],
        unique=True, partialFilterExpression={"user_id": {"$type": "string"}},
        name="uq_biashara_employee_user",
    )
    database["jumuiya_biashara_attendance"].create_index(
        [("business_id", ASCENDING), ("user_id", ASCENDING), ("local_date", DESCENDING)],
        name="ix_biashara_attendance_user_date",
    )
    database["jumuiya_biashara_attendance"].create_index(
        [("business_id", ASCENDING), ("user_id", ASCENDING), ("open_shift", ASCENDING)],
        unique=True, partialFilterExpression={"open_shift": True},
        name="uq_biashara_attendance_open_shift",
    )
    database["jumuiya_biashara_leave_requests"].create_index(
        [("business_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)],
        name="ix_biashara_leave_status_created",
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

def _register_business_domain(business_id, business_slug, tenant_id):
    if not business_slug:
        return
    slug = re.sub(r"[^a-z0-9-]", "", str(business_slug).lower()).strip("-")
    if not slug:
        return
    hostname = slug + ".revelacode.co.ke"
    _domain_registry().update_one(
        {"hostname": hostname, "business_id": business_id},
        {"$setOnInsert": {
            "hostname": hostname,
            "business_id": business_id,
            "tenant_id": tenant_id,
            "verification_token": secrets.token_urlsafe(24),
            "status": "pending_dns",
            "verification_status": "pending",
            "created_at": _now(),
        }, "$set": {"updated_at": _now()}},
        upsert=True,
    )


def ensure_business_tenant(business_id, *, business_slug=None, migrate_legacy=True):
    """Provision, resume or schema-upgrade one company database.

    Only one request owns the migration lease at a time. Legacy copies are
    idempotent and retain their source records until a reviewed cleanup.
    """
    key = _business_key(business_id)
    db_name = database_name_for_business(key)
    tenant_id = "biz_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
    registry = _registry()
    now = _now()
    existing = registry.find_one({"business_id": key})
    if existing and existing.get("database_name") not in (None, db_name):
        raise APIError("The company tenant registry points to an unexpected database.", 503, "business_tenant_registry_mismatch")

    if (
        existing
        and existing.get("status") == "active"
        and existing.get("database_name") == db_name
        and int(existing.get("schema_version", 0) or 0) >= TENANT_SCHEMA_VERSION
        and (not migrate_legacy or existing.get("migration_status") == "complete")
    ):
        database = client[db_name]
        _ensure_tenant_indexes(database)
        _register_business_domain(key, business_slug, existing.get("tenant_id") or tenant_id)
        return existing

    registry.update_one(
        {"business_id": key},
        {"$setOnInsert": {
            "business_id": key,
            "tenant_id": tenant_id,
            "database_name": db_name,
            "status": "provisioning",
            "schema_version": 0,
            "migration_status": "pending",
            "created_at": now,
        }, "$set": {"updated_at": now}},
        upsert=True,
    )

    lock_token = secrets.token_urlsafe(24)
    claim_query = {
        "business_id": key,
        "$or": [
            {
                "status": {"$in": ["provisioning", "migration_failed"]},
                "$or": [
                    {"migration_lock_until": {"$lte": now}},
                    {"migration_lock_until": {"$exists": False}},
                ],
            },
            {"status": "migrating", "migration_lock_until": {"$lte": now}},
            {
                "status": "active",
                "$or": [
                    {"schema_version": {"$lt": TENANT_SCHEMA_VERSION}},
                    {"schema_version": {"$exists": False}},
                    {"migration_status": "new_tenant"},
                ],
            },
        ],
    }
    claim = registry.update_one(
        claim_query,
        {"$set": {
            "database_name": db_name,
            "tenant_id": tenant_id,
            "status": "migrating",
            "migration_lock_token": lock_token,
            "migration_lock_until": now + timedelta(minutes=MIGRATION_LOCK_MINUTES),
            "updated_at": now,
        }},
    )
    if not claim.modified_count:
        current = registry.find_one({"business_id": key}) or {}
        if (
            current.get("status") == "active"
            and current.get("database_name") == db_name
            and int(current.get("schema_version", 0) or 0) >= TENANT_SCHEMA_VERSION
            and (not migrate_legacy or current.get("migration_status") == "complete")
        ):
            database = client[db_name]
            _ensure_tenant_indexes(database)
            _register_business_domain(key, business_slug, current.get("tenant_id") or tenant_id)
            return current
        raise APIError(
            "Company database provisioning or migration is already in progress. Retry after the current operation completes.",
            503,
            "business_tenant_provisioning",
        )

    database = client[db_name]
    metadata = database["jumuiya_tenant_metadata"]
    try:
        copied = _copy_legacy_business_records(database, key) if migrate_legacy else 0
        _ensure_tenant_indexes(database)
        schema_version = TENANT_SCHEMA_VERSION if migrate_legacy else 0
        metadata.update_one(
            {"_id": "tenant"},
            {"$set": {
                "business_id": key,
                "tenant_id": tenant_id,
                "database_name": db_name,
                "schema_version": schema_version,
                "updated_at": _now(),
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        registry.update_one(
            {"business_id": key, "migration_lock_token": lock_token, "status": "migrating"},
            {"$set": {
                "database_name": db_name,
                "tenant_id": tenant_id,
                "schema_version": schema_version,
                "status": "active",
                "migration_status": "complete" if migrate_legacy else "new_tenant",
                "legacy_documents_copied": copied,
                "updated_at": _now(),
            }, "$unset": {"migration_lock_token": "", "migration_lock_until": "", "migration_error": ""}},
        )
    except Exception as exc:
        registry.update_one(
            {"business_id": key, "migration_lock_token": lock_token},
            {"$set": {
                "status": "migration_failed",
                "migration_error": str(exc)[:500],
                "updated_at": _now(),
            }, "$unset": {"migration_lock_token": "", "migration_lock_until": ""}},
        )
        raise

    _register_business_domain(key, business_slug, tenant_id)
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
    """Use the tenant DB for company records and the central DB for shared registries.

    Tenant-owned records fail closed when a verified request context is missing.
    Background jobs must call tenant_collection(name, explicit_business_id).
    """
    if name in TENANT_COLLECTIONS:
        business_id = current_business_id()
        if not business_id:
            raise APIError(
                "A verified Biashara company context is required for this record.",
                409,
                "business_context_required",
            )
        return tenant_collection(name, business_id)
    return core_collection(name)
