"""Manufacturing workflows for Biashara OS.

All records are written to the selected company's dedicated MongoDB database.
Production consumes raw-material stock at batch start. Finished goods enter
sellable inventory only after a passing quality inspection.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.db import client
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import ok, created
from backend.jumuiya.biashara import services
from backend.jumuiya.biashara.access import resolve_business_access
from backend.jumuiya.biashara.templates import has_permission
from backend.jumuiya.biashara.tenant_store import (
    set_business_tenant_context,
    tenant_collection,
)

factory_bp = Blueprint("jumuiya_biashara_factory", __name__)

def _now():
    return datetime.now(timezone.utc)

def _idempotency_key():
    value = request.headers.get("Idempotency-Key") or request.headers.get("X-Offline-Mutation-Id") or ""
    value = str(value).strip()
    if not value:
        return None
    if len(value) > 160:
        raise APIError("Idempotency key is too long.", 422, "invalid_idempotency_key")
    return value

def _id(value):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError, ValueError):
        raise APIError("A valid resource ID is required.", 422, "invalid_resource_id")

def _decimal(value, field, *, allow_zero=False, max_value="1000000000000"):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise APIError(f"{field} must be numeric.", 422, "invalid_number")
    minimum_ok = number >= 0 if allow_zero else number > 0
    if not number.is_finite() or not minimum_ok or number > Decimal(max_value):
        qualifier = "non-negative" if allow_zero else "greater than zero"
        raise APIError(f"{field} must be {qualifier} and within the supported range.", 422, "invalid_number")
    return number

def _validate_material_pair(raw, output, input_quantity, expected_output_quantity):
    """Enforce comparable material units and explicit production SKU types."""
    raw_type = str(raw.get("production_type") or "resale").strip().lower()
    output_type = str(output.get("production_type") or "resale").strip().lower()
    if raw_type != "raw_material":
        raise APIError("The selected input SKU must be classified as raw_material.", 422, "invalid_raw_material_type")
    if output_type != "finished_good":
        raise APIError("The selected output SKU must be classified as finished_good.", 422, "invalid_finished_good_type")
    raw_unit = str(raw.get("unit") or "").strip().lower()
    output_unit = str(output.get("unit") or "").strip().lower()
    if not raw_unit or raw_unit != output_unit:
        raise APIError(
            "Raw material and finished output must use the same base unit. Add unit conversion support before using mixed units.",
            422,
            "production_unit_mismatch",
        )
    if expected_output_quantity > input_quantity:
        raise APIError("Expected finished output cannot exceed raw-material input.", 422, "invalid_expected_yield")
    return raw_unit


def _serialise_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _serialise_value(item) for key, item in value.items() if key != "_id"}
    if isinstance(value, (list, tuple)):
        return [_serialise_value(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _serialise(doc):
    if not doc:
        return None
    result = _serialise_value(dict(doc))
    if "_id" in doc:
        result["id"] = str(doc["_id"])
    return result

def _business(permission):
    uid = str(current_user_id())
    business = services._require_business(uid, allowed_roles={
        "owner", "admin", "ceo", "director", "manager", "operations_manager",
        "factory_floor_lead", "accountant", "store_keeper", "inventory", "sales_agent", "sales",
    })
    context = resolve_business_access(uid, business["id"])
    role = "owner" if context and context.get("is_owner") else (context or {}).get("role", "viewer")
    if not has_permission(role, permission):
        raise APIError("Your Biashara role does not permit this factory operation.", 403, "business_permission_denied")
    info = set_business_tenant_context(business["id"], business_slug=business.get("slug"), migrate_legacy=True)
    return uid, business, info

def _collections(business_id):
    return {
        "batches": tenant_collection("jumuiya_factory_production_batches", business_id),
        "checks": tenant_collection("jumuiya_factory_quality_checks", business_id),
        "machines": tenant_collection("jumuiya_factory_machines", business_id),
        "readings": tenant_collection("jumuiya_factory_machine_readings", business_id),
        "alerts": tenant_collection("jumuiya_factory_alerts", business_id),
        "products": tenant_collection("jumuiya_products", business_id),
        "movements": tenant_collection("jumuiya_inventory_movements", business_id),
    }

@factory_bp.get("/factory/overview")
@require_authenticated
def factory_overview():
    uid, business, _ = _business("production.view")
    c = _collections(business["id"])
    base = {"business_id": business["id"]}
    batches = c["batches"]
    return ok({
        "template": business.get("industry_template", "general"),
        "batch_counts": {
            status: batches.count_documents({**base, "status": status})
            for status in ("in_progress", "quality_hold", "released", "rejected")
        },
        "input_quantity_in_progress": sum(float(row.get("input_quantity", 0) or 0) for row in batches.find({**base, "status": "in_progress"})),
        "quality_queue": batches.count_documents({**base, "status": "quality_hold"}),
        "machines_active": c["machines"].count_documents({**base, "status": "active"}),
        "open_alerts": c["alerts"].count_documents({**base, "status": "open"}),
    })

@factory_bp.get("/factory/production/batches")
@require_authenticated
def list_production_batches():
    uid, business, _ = _business("production.view")
    c = _collections(business["id"])
    rows = c["batches"].find({"business_id": business["id"]}).sort("created_at", -1).limit(100)
    return ok([_serialise(row) for row in rows])

@factory_bp.post("/factory/production/batches")
@require_authenticated
def create_production_batch():
    uid, business, _ = _business("production.create")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    batch_number = str(data.get("batch_number") or "").strip().upper()
    raw_product_id = str(data.get("raw_material_product_id") or "").strip()
    output_product_id = str(data.get("output_product_id") or "").strip()
    material_quantity = _decimal(data.get("input_quantity"), "input_quantity")
    expected_output = _decimal(data.get("expected_output_quantity"), "expected_output_quantity")
    if not batch_number or len(batch_number) > 64:
        raise APIError("batch_number is required (maximum 64 characters).", 422, "validation_error")
    if not raw_product_id or not output_product_id:
        raise APIError("Select both a raw-material product and a finished-goods product.", 422, "validation_error")
    c = _collections(business["id"])
    idempotency_key = _idempotency_key()
    if idempotency_key:
        existing = c["batches"].find_one({"business_id": business["id"], "idempotency_key": idempotency_key})
        if existing:
            return ok(_serialise(existing), "This production batch was already recorded.")
    raw_id, output_id = _id(raw_product_id), _id(output_product_id)
    now = _now()
    batch_id = ObjectId()
    batch = {
        "_id": batch_id,
        "business_id": business["id"],
        "batch_number": batch_number,
        "idempotency_key": idempotency_key,
        "raw_material_product_id": raw_product_id,
        "output_product_id": output_product_id,
        "input_quantity": float(material_quantity),
        "expected_output_quantity": float(expected_output),
        "actual_output_quantity": None,
        "wastage_quantity": None,
        "yield_percent": None,
        "status": "in_progress",
        "created_by_user_id": uid,
        "created_at": now,
        "updated_at": now,
        "events": [{"event": "started", "actor_user_id": uid, "at": now}],
    }
    movement = {
        "_id": ObjectId(),
        "business_id": business["id"],
        "product_id": raw_product_id,
        "product_name": "",
        "movement_type": "production_consumption",
        "quantity": -float(material_quantity),
        "unit": "unit",
        "reason": "Raw material issued to production batch " + batch_number,
        "reference_type": "production_batch",
        "reference_id": str(batch_id),
        "idempotency_key": "factory_batch_consume_" + str(batch_id),
        "actor_user_id": uid,
        "created_at": now,
    }
    try:
        # MongoDB transactions are required so stock deduction, movement audit,
        # and batch creation either commit together or roll back together.
        with client.start_session() as session:
            with session.start_transaction():
                raw = c["products"].find_one_and_update(
                    {"_id": raw_id, "business_id": business["id"], "status": {"$ne": "deleted"},
                     "stock_quantity": {"$gte": float(material_quantity)}},
                    {"$inc": {"stock_quantity": -float(material_quantity)}, "$set": {"updated_at": now}},
                    return_document=ReturnDocument.AFTER, session=session,
                )
                if not raw:
                    raise APIError("Raw-material stock is insufficient or the product is unavailable.", 409, "insufficient_material_stock")
                output = c["products"].find_one(
                    {"_id": output_id, "business_id": business["id"], "status": {"$ne": "deleted"}},
                    session=session,
                )
                if not output:
                    raise APIError("Finished-goods product was not found in this business.", 404, "output_product_not_found")
                unit = _validate_material_pair(raw, output, material_quantity, expected_output)
                movement["product_name"] = raw.get("name", "")
                movement["unit"] = unit
                c["movements"].insert_one(movement, session=session)
                c["batches"].insert_one(batch, session=session)
    except DuplicateKeyError:
        if idempotency_key:
            existing = c["batches"].find_one({"business_id": business["id"], "idempotency_key": idempotency_key})
            if existing:
                return ok(_serialise(existing), "This production batch was already recorded.")
        raise APIError("A production batch with this number already exists.", 409, "duplicate_batch_number")
    except APIError:
        raise
    except Exception as exc:
        # Do not report success when the database deployment lacks transaction support.
        raise APIError("Production requires MongoDB transaction support. Check the database replica-set configuration.", 503, "transactions_unavailable") from exc
    return created(_serialise(batch), "Production batch started and raw material issued.")

@factory_bp.post("/factory/production/batches/<batch_id>/complete")
@require_authenticated
def complete_production_batch(batch_id):
    uid, business, _ = _business("production.update")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    actual = _decimal(data.get("actual_output_quantity"), "actual_output_quantity")
    waste = _decimal(data.get("wastage_quantity", 0), "wastage_quantity", allow_zero=True)
    byproducts = _decimal(data.get("recoverable_byproducts_quantity", 0), "recoverable_byproducts_quantity", allow_zero=True)
    batch_collection = tenant_collection("jumuiya_factory_production_batches", business["id"])
    batch = batch_collection.find_one({"_id": _id(batch_id), "business_id": business["id"]})
    if not batch:
        raise APIError("Production batch not found.", 404, "batch_not_found")
    idempotency_key = _idempotency_key()
    if batch.get("status") != "in_progress":
        if idempotency_key and batch.get("completion_idempotency_key") == idempotency_key:
            return ok(_serialise(batch), "This production completion was already recorded.")
        raise APIError("Only an in-progress batch can be completed.", 409, "batch_state_conflict")
    total = actual + waste + byproducts
    if total > Decimal(str(batch["input_quantity"])):
        raise APIError("Finished output, wastage and recoverable by-products cannot exceed material input.", 422, "mass_balance_error")
    if total < Decimal(str(batch["input_quantity"])):
        raise APIError("Account for the full material input as output, wastage or recoverable by-products.", 422, "mass_balance_incomplete")
    yield_percent = (actual / Decimal(str(batch["input_quantity"])) * Decimal("100")).quantize(Decimal("0.01"))
    now = _now()
    result = batch_collection.update_one(
        {"_id": batch["_id"], "business_id": business["id"], "status": "in_progress"},
        {"$set": {
            "actual_output_quantity": float(actual),
            "wastage_quantity": float(waste),
            "recoverable_byproducts_quantity": float(byproducts),
            "yield_percent": float(yield_percent),
            "completion_notes": str(data.get("notes") or "")[:2000],
            "completion_idempotency_key": idempotency_key,
            "status": "quality_hold",
            "completed_by_user_id": uid,
            "completed_at": now,
            "updated_at": now,
        }, "$push": {"events": {"event": "completed_pending_quality", "actor_user_id": uid, "at": now}}},
    )
    if not result.modified_count:
        latest = batch_collection.find_one({"_id": batch["_id"], "business_id": business["id"]})
        if idempotency_key and latest and latest.get("completion_idempotency_key") == idempotency_key:
            return ok(_serialise(latest), "This production completion was already recorded.")
        raise APIError("The batch changed while it was being completed. Refresh and retry.", 409, "batch_state_conflict")
    return ok(_serialise(batch_collection.find_one({"_id": batch["_id"]})), "Batch completed and placed on quality hold.")

@factory_bp.get("/factory/quality/checks")
@require_authenticated
def list_quality_checks():
    uid, business, _ = _business("quality.view")
    rows = tenant_collection("jumuiya_factory_quality_checks", business["id"]).find(
        {"business_id": business["id"]}).sort("created_at", -1).limit(100)
    return ok([_serialise(row) for row in rows])

@factory_bp.post("/factory/quality/checks")
@require_authenticated
def inspect_quality():
    uid, business, _ = _business("quality.inspect")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    batch_id = _id(data.get("batch_id"))
    grade = str(data.get("grade") or "").strip().upper()
    if grade not in {"A", "B", "C", "REJECTED"}:
        raise APIError("grade must be A, B, C or REJECTED.", 422, "invalid_grade")
    c = _collections(business["id"])
    idempotency_key = _idempotency_key()
    if idempotency_key:
        existing = c["checks"].find_one({"business_id": business["id"], "idempotency_key": idempotency_key})
        if existing:
            return ok(_serialise(existing), "This quality inspection was already recorded.")
    existing_for_batch = c["checks"].find_one({"business_id": business["id"], "batch_id": str(batch_id)})
    if existing_for_batch:
        raise APIError("This batch already has a quality inspection.", 409, "quality_check_exists")
    now = _now()
    check = {
        "_id": ObjectId(), "business_id": business["id"], "batch_id": str(batch_id),
        "idempotency_key": idempotency_key,
        "grade": grade, "result": "passed" if grade in {"A", "B", "C"} else "rejected",
        "inspection_notes": str(data.get("inspection_notes") or "")[:3000],
        "measurements": data.get("measurements") if isinstance(data.get("measurements"), dict) else {},
        "inspected_by_user_id": uid, "created_at": now,
    }
    try:
        with client.start_session() as session:
            with session.start_transaction():
                batch = c["batches"].find_one(
                    {"_id": batch_id, "business_id": business["id"], "status": "quality_hold"},
                    session=session,
                )
                if not batch:
                    raise APIError("A completed batch awaiting inspection was not found.", 409, "quality_batch_not_ready")
                if grade in {"A", "B", "C"}:
                    output = c["products"].find_one_and_update(
                        {"_id": _id(batch["output_product_id"]), "business_id": business["id"], "status": {"$ne": "deleted"}},
                        {"$inc": {"stock_quantity": batch["actual_output_quantity"]}, "$set": {"updated_at": now}},
                        return_document=ReturnDocument.AFTER, session=session,
                    )
                    if not output:
                        raise APIError("Finished-goods product is missing; no inventory was released.", 409, "output_product_unavailable")
                    c["movements"].insert_one({
                        "_id": ObjectId(), "business_id": business["id"],
                        "product_id": str(output["_id"]), "product_name": output.get("name", ""),
                        "movement_type": "production_output", "quantity": batch["actual_output_quantity"],
                        "unit": output.get("unit", "unit"), "reason": "Quality-approved batch " + batch["batch_number"],
                        "reference_type": "production_batch", "reference_id": str(batch_id),
                        "idempotency_key": "factory_batch_output_" + str(batch_id),
                        "actor_user_id": uid, "created_at": now,
                    }, session=session)
                    next_status = "released"
                else:
                    next_status = "rejected"
                c["checks"].insert_one(check, session=session)
                c["batches"].update_one(
                    {"_id": batch_id, "business_id": business["id"], "status": "quality_hold"},
                    {"$set": {"status": next_status, "quality_grade": grade, "quality_check_id": str(check["_id"]),
                              "released_at": now if next_status == "released" else None, "updated_at": now},
                     "$push": {"events": {"event": next_status, "actor_user_id": uid, "at": now}}},
                    session=session,
                )
    except DuplicateKeyError:
        if idempotency_key:
            existing = c["checks"].find_one({"business_id": business["id"], "idempotency_key": idempotency_key})
            if existing:
                return ok(_serialise(existing), "This quality inspection was already recorded.")
        raise APIError("This batch already has a quality inspection.", 409, "quality_check_exists")
    except APIError:
        raise
    except Exception as exc:
        raise APIError("Quality release requires MongoDB transaction support. No inventory release was confirmed.", 503, "transactions_unavailable") from exc
    return created(_serialise(check), "Quality inspection recorded; batch disposition: " + next_status + ".")

@factory_bp.get("/factory/machines")
@require_authenticated
def list_machines():
    uid, business, _ = _business("machines.view")
    rows = tenant_collection("jumuiya_factory_machines", business["id"]).find(
        {"business_id": business["id"]}).sort("created_at", -1).limit(100)
    return ok([_serialise(row) for row in rows])

@factory_bp.post("/factory/machines")
@require_authenticated
def create_machine():
    uid, business, _ = _business("machines.create")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    name = str(data.get("name") or "").strip()
    code = str(data.get("machine_code") or "").strip().upper()
    if not name or not code or len(name) > 160 or len(code) > 64:
        raise APIError("Machine name and a unique machine_code are required.", 422, "validation_error")
    min_rate = _decimal(data.get("minimum_output_per_hour", 0), "minimum_output_per_hour", allow_zero=True)
    doc = {
        "_id": ObjectId(), "business_id": business["id"], "name": name, "machine_code": code,
        "line": str(data.get("line") or "")[:120], "location": str(data.get("location") or "")[:180],
        "minimum_output_per_hour": float(min_rate), "status": "active",
        "created_by_user_id": uid, "created_at": _now(), "updated_at": _now(),
    }
    idempotency_key = _idempotency_key()
    doc["idempotency_key"] = idempotency_key
    machines = tenant_collection("jumuiya_factory_machines", business["id"])
    if idempotency_key:
        existing = machines.find_one({"business_id": business["id"], "idempotency_key": idempotency_key})
        if existing:
            return ok(_serialise(existing), "This machine registration was already recorded.")
    try:
        machines.insert_one(doc)
    except DuplicateKeyError:
        if idempotency_key:
            existing = machines.find_one({"business_id": business["id"], "idempotency_key": idempotency_key})
            if existing:
                return ok(_serialise(existing), "This machine registration was already recorded.")
        raise APIError("That machine_code already exists in this business.", 409, "duplicate_machine_code")
    return created(_serialise(doc), "Machine registered.")

@factory_bp.post("/factory/machines/<machine_id>/readings")
@require_authenticated
def record_machine_reading(machine_id):
    uid, business, _ = _business("machines.readings.create")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    hours = _decimal(data.get("operating_hours"), "operating_hours")
    output = _decimal(data.get("output_quantity", 0), "output_quantity", allow_zero=True)
    now = _now()
    machines = tenant_collection("jumuiya_factory_machines", business["id"])
    machine = machines.find_one({"_id": _id(machine_id), "business_id": business["id"], "status": "active"})
    if not machine:
        raise APIError("Active machine not found.", 404, "machine_not_found")
    rate = (output / hours).quantize(Decimal("0.01"))
    idempotency_key = _idempotency_key()
    readings = tenant_collection("jumuiya_factory_machine_readings", business["id"])
    if idempotency_key:
        existing = readings.find_one({"business_id": business["id"], "idempotency_key": idempotency_key})
        if existing:
            return ok(_serialise(existing), "This machine reading was already recorded.")
    reading = {
        "_id": ObjectId(), "business_id": business["id"], "idempotency_key": idempotency_key,
        "machine_id": str(machine["_id"]),
        "machine_code": machine["machine_code"], "operating_hours": float(hours),
        "output_quantity": float(output), "output_per_hour": float(rate),
        "operator_user_id": uid, "notes": str(data.get("notes") or "")[:1500],
        "recorded_at": now,
    }
    try:
        readings.insert_one(reading)
    except DuplicateKeyError:
        if idempotency_key:
            existing = readings.find_one({"business_id": business["id"], "idempotency_key": idempotency_key})
            if existing:
                return ok(_serialise(existing), "This machine reading was already recorded.")
        raise APIError("Machine reading was already submitted.", 409, "duplicate_machine_reading")
    min_rate = Decimal(str(machine.get("minimum_output_per_hour", 0) or 0))
    alert = None
    if min_rate > 0 and rate < min_rate:
        alert = {
            "_id": ObjectId(), "business_id": business["id"], "type": "machine_output_below_threshold",
            "severity": "warning", "status": "open",
            "message": f'{machine["machine_code"]} output {rate}/hour is below threshold {min_rate}/hour.',
            "machine_id": str(machine["_id"]), "reading_id": str(reading["_id"]),
            "created_at": now,
        }
        tenant_collection("jumuiya_factory_alerts", business["id"]).insert_one(alert)
    machines.update_one({"_id": machine["_id"], "business_id": business["id"]},
                        {"$set": {"last_output_per_hour": float(rate), "last_reading_at": now, "updated_at": now}})
    return created({"reading": _serialise(reading), "alert": _serialise(alert)}, "Machine reading recorded.")

@factory_bp.get("/factory/alerts")
@require_authenticated
def list_factory_alerts():
    uid, business, _ = _business("machines.view")
    rows = tenant_collection("jumuiya_factory_alerts", business["id"]).find(
        {"business_id": business["id"], "status": "open"}).sort("created_at", -1).limit(100)
    return ok([_serialise(row) for row in rows])
