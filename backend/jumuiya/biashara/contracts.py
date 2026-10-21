"""Biashara workspace contracts.

These routes use the existing Jumuiya Mongo database and authenticated identity.
They deliberately do not claim external payment, automation, or sync completion.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, request

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.permissions import require_authenticated, current_user_id
from backend.jumuiya.core.responses import ok, created
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.biashara.services import get_business_for_user, clean_id, serialise, serialise_many
from backend.jumuiya.core.audit import log_action

contracts_bp = Blueprint("jumuiya_biashara_contracts", __name__)
ROLES = {"admin", "manager", "sales", "inventory", "viewer"}
AUTOMATION_STATUSES = {"enabled", "disabled"}
SYNC_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}


def _now():
    return datetime.now(timezone.utc)


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    return data


def _owner_business():
    uid = str(current_user_id())
    business = get_business_for_user(uid)
    if not business:
        raise APIError("Create a business profile first.", 409, "business_required")
    # Existing Biashara operations are owner-scoped. Do not treat an unverified
    # business as operationally enabled.
    if business.get("verification_status") != "verified" or business.get("status") != "active":
        raise APIError("Business verification is required for this operation.", 403, "business_verification_required")
    return uid, business


def _business_id(business):
    return str(business.get("id") or business.get("_id"))


def _decimal_amount(value, field="amount"):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise APIError(f"{field} must be a valid amount.", 422, "invalid_amount")
    if not amount.is_finite() or amount <= 0 or amount > Decimal("999999999999"):
        raise APIError(f"{field} must be greater than zero and within the supported limit.", 422, "invalid_amount")
    return str(amount.quantize(Decimal("0.01")))


def _owned(resource, uid, business_id, resource_id):
    doc = collection(resource).find_one({
        "_id": clean_id(resource_id),
        "owner_user_id": uid,
        "business_id": business_id,
    })
    if not doc:
        raise APIError("Resource not found for this business.", 404, "resource_not_found")
    return doc


# Finance: records are internal invoices and allocations, not payment processing.
@contracts_bp.get("/finance/invoices")
@require_authenticated
def list_invoices():
    uid, business = _owner_business()
    docs = collection("jumuiya_biashara_invoices").find({
        "owner_user_id": uid, "business_id": _business_id(business)
    }).sort("created_at", -1).limit(100)
    return ok(serialise_many(docs))


@contracts_bp.post("/finance/invoices")
@require_authenticated
def create_invoice():
    uid, business = _owner_business()
    data = _body()
    customer_name = str(data.get("customer_name") or "").strip()
    currency = str(data.get("currency") or "KES").strip().upper()
    if not customer_name or len(customer_name) > 180:
        raise APIError("customer_name is required (max 180 characters).", 422, "validation_error")
    if currency not in {"KES", "USD", "EUR", "GBP", "TZS", "UGX"}:
        raise APIError("Unsupported invoice currency.", 422, "validation_error")
    items = data.get("items")
    if not isinstance(items, list) or not items or len(items) > 100:
        raise APIError("Provide 1–100 invoice items.", 422, "validation_error")
    normalised = []
    total = Decimal("0.00")
    for item in items:
        if not isinstance(item, dict) or not str(item.get("description") or "").strip():
            raise APIError("Each invoice item needs a description.", 422, "validation_error")
        try:
            qty = Decimal(str(item.get("quantity", 1)))
            price = Decimal(str(item.get("unit_price")))
        except (InvalidOperation, TypeError, ValueError):
            raise APIError("Invoice quantities and prices must be numeric.", 422, "validation_error")
        if not qty.is_finite() or qty <= 0 or not price.is_finite() or price < 0:
            raise APIError("Invoice quantities must be positive and prices non-negative.", 422, "validation_error")
        line_total = (qty * price).quantize(Decimal("0.01"))
        total += line_total
        normalised.append({"description": str(item["description"]).strip()[:240],
                           "quantity": str(qty), "unit_price": str(price.quantize(Decimal("0.01"))),
                           "line_total": str(line_total)})
    now = _now()
    doc = {
        "owner_user_id": uid, "business_id": _business_id(business),
        "invoice_number": "INV-" + secrets.token_hex(5).upper(),
        "customer_name": customer_name, "currency": currency, "items": normalised,
        "total": str(total.quantize(Decimal("0.01"))), "allocated_amount": "0.00",
        "status": "issued", "due_date": str(data.get("due_date") or "")[:10],
        "notes": str(data.get("notes") or "")[:2000], "created_at": now, "updated_at": now,
    }
    result = collection("jumuiya_biashara_invoices").insert_one(doc)
    doc["_id"] = result.inserted_id
    log_action(uid, "biashara.invoice.created", "biashara_invoice", result.inserted_id)
    return created(serialise(doc), "Invoice recorded. No payment has been processed.")


@contracts_bp.post("/finance/invoices/<invoice_id>/allocations")
@require_authenticated
def allocate_invoice_payment(invoice_id):
    uid, business = _owner_business()
    data = _body()
    amount = Decimal(_decimal_amount(data.get("amount")))
    invoice = _owned("jumuiya_biashara_invoices", uid, _business_id(business), invoice_id)
    total = Decimal(str(invoice["total"]))
    allocated = Decimal(str(invoice.get("allocated_amount", "0")))
    if allocated + amount > total:
        raise APIError("Allocation exceeds the outstanding invoice balance.", 409, "allocation_exceeds_balance")
    method = str(data.get("method") or "").strip().lower()
    reference = str(data.get("reference") or "").strip()[:180]
    if method not in {"cash", "bank", "mobile_money", "other"} or not reference:
        raise APIError("Provide a supported method and transaction reference.", 422, "validation_error")
    now = _now()
    allocation = {"owner_user_id": uid, "business_id": _business_id(business),
                  "invoice_id": str(invoice["_id"]), "amount": str(amount),
                  "currency": invoice["currency"], "method": method, "reference": reference,
                  "recorded_by_user_id": uid, "created_at": now,
                  "verification_status": "owner_recorded_unverified"}
    result = collection("jumuiya_biashara_payment_allocations").insert_one(allocation)
    new_allocated = allocated + amount
    status = "paid_recorded" if new_allocated == total else "partially_allocated"
    collection("jumuiya_biashara_invoices").update_one(
        {"_id": invoice["_id"], "owner_user_id": uid, "business_id": _business_id(business)},
        {"$set": {"allocated_amount": str(new_allocated), "status": status, "updated_at": now}})
    allocation["_id"] = result.inserted_id
    log_action(uid, "biashara.invoice.allocation_recorded", "biashara_invoice", invoice["_id"],
               {"allocation_id": str(result.inserted_id), "verification_status": "owner_recorded_unverified"})
    return created(serialise(allocation), "Allocation recorded as unverified; this does not confirm receipt of funds.")


@contracts_bp.get("/finance/invoices/<invoice_id>/allocations")
@require_authenticated
def list_invoice_allocations(invoice_id):
    uid, business = _owner_business()
    invoice = _owned("jumuiya_biashara_invoices", uid, _business_id(business), invoice_id)
    docs = collection("jumuiya_biashara_payment_allocations").find({
        "owner_user_id": uid, "business_id": _business_id(business), "invoice_id": str(invoice["_id"])
    }).sort("created_at", -1).limit(100)
    return ok(serialise_many(docs))


# Automation rules are saved as configurations only. No arbitrary code is executed.
@contracts_bp.get("/automations/rules")
@require_authenticated
def list_automation_rules():
    uid, business = _owner_business()
    docs = collection("jumuiya_biashara_automation_rules").find({
        "owner_user_id": uid, "business_id": _business_id(business)
    }).sort("updated_at", -1).limit(100)
    return ok(serialise_many(docs))


@contracts_bp.post("/automations/rules")
@require_authenticated
def create_automation_rule():
    uid, business = _owner_business()
    data = _body()
    name = str(data.get("name") or "").strip()
    trigger = str(data.get("trigger") or "").strip().lower()
    action = str(data.get("action") or "").strip().lower()
    allowed_triggers = {"low_stock", "order_created", "invoice_overdue", "daily_summary"}
    allowed_actions = {"create_alert", "create_task", "daily_summary"}
    if not name or len(name) > 120 or trigger not in allowed_triggers or action not in allowed_actions:
        raise APIError("Provide a name and supported trigger/action.", 422, "validation_error")
    now = _now()
    doc = {"owner_user_id": uid, "business_id": _business_id(business), "name": name,
           "trigger": trigger, "action": action, "enabled": bool(data.get("enabled", False)),
           "execution_mode": "configuration_only", "last_run_at": None,
           "created_at": now, "updated_at": now}
    result = collection("jumuiya_biashara_automation_rules").insert_one(doc)
    doc["_id"] = result.inserted_id
    log_action(uid, "biashara.automation_rule.created", "biashara_automation_rule", result.inserted_id)
    return created(serialise(doc), "Automation rule saved; execution is not enabled until a supported worker is configured.")


@contracts_bp.patch("/automations/rules/<rule_id>")
@require_authenticated
def update_automation_rule(rule_id):
    uid, business = _owner_business()
    data = _body()
    update = {}
    if "name" in data:
        name = str(data["name"] or "").strip()
        if not name or len(name) > 120:
            raise APIError("name must be 1–120 characters.", 422, "validation_error")
        update["name"] = name
    if "enabled" in data:
        if not isinstance(data["enabled"], bool):
            raise APIError("enabled must be a boolean.", 422, "validation_error")
        update["enabled"] = data["enabled"]
    if not update:
        raise APIError("Provide name or enabled.", 422, "validation_error")
    update["updated_at"] = _now()
    result = collection("jumuiya_biashara_automation_rules").update_one({
        "_id": clean_id(rule_id), "owner_user_id": uid, "business_id": _business_id(business)
    }, {"$set": update})
    if not result.matched_count:
        raise APIError("Automation rule not found.", 404, "resource_not_found")
    return ok(serialise(collection("jumuiya_biashara_automation_rules").find_one({
        "_id": clean_id(rule_id), "owner_user_id": uid, "business_id": _business_id(business)
    })))


# Sync Centre tracks sync requests. It does not pretend a connector ran.
@contracts_bp.get("/sync/jobs")
@require_authenticated
def list_sync_jobs():
    uid, business = _owner_business()
    docs = collection("jumuiya_biashara_sync_jobs").find({
        "owner_user_id": uid, "business_id": _business_id(business)
    }).sort("created_at", -1).limit(100)
    return ok(serialise_many(docs))


@contracts_bp.post("/sync/jobs")
@require_authenticated
def create_sync_job():
    uid, business = _owner_business()
    data = _body()
    source = str(data.get("source") or "").strip().lower()
    direction = str(data.get("direction") or "pull").strip().lower()
    if source not in {"csv_import", "website", "inventory", "orders"} or direction not in {"pull", "push", "bidirectional"}:
        raise APIError("Unsupported sync source or direction.", 422, "validation_error")
    now = _now()
    doc = {"owner_user_id": uid, "business_id": _business_id(business), "source": source,
           "direction": direction, "status": "queued", "progress": 0,
           "message": "Queued for a configured sync worker; no external sync has run yet.",
           "created_at": now, "updated_at": now, "finished_at": None}
    result = collection("jumuiya_biashara_sync_jobs").insert_one(doc)
    doc["_id"] = result.inserted_id
    log_action(uid, "biashara.sync_job.queued", "biashara_sync_job", result.inserted_id)
    return created(serialise(doc), "Sync request queued. A worker must process it before it can be marked complete.")


# Team access contract. Pending invites do not grant access until accepted by an authenticated account.
@contracts_bp.get("/team")
@require_authenticated
def list_team():
    uid, business = _owner_business()
    bid = _business_id(business)
    members = list(collection("jumuiya_biashara_memberships").find(
        {"business_id": bid}, {"invitation_token": 0}).sort("created_at", -1).limit(200))
    invites = list(collection("jumuiya_biashara_invitations").find(
        {"business_id": bid, "status": "pending"}, {"invitation_token": 0}).sort("created_at", -1).limit(200))
    return ok({"members": serialise_many(members), "invitations": serialise_many(invites), "owner_user_id": uid})


@contracts_bp.post("/team/invitations")
@require_authenticated
def invite_team_member():
    uid, business = _owner_business()
    data = _body()
    email = str(data.get("email") or "").strip().lower()
    role = str(data.get("role") or "").strip().lower()
    if "@" not in email or len(email) > 254 or role not in ROLES - {"admin"}:
        raise APIError("Provide a valid email and a supported non-admin role.", 422, "validation_error")
    bid = _business_id(business)
    invites = collection("jumuiya_biashara_invitations")
    existing = invites.find_one({"business_id": bid, "email": email, "status": "pending"})
    if existing:
        raise APIError("A pending invitation already exists for this email.", 409, "invitation_exists")
    now = _now()
    doc = {"owner_user_id": uid, "business_id": bid, "email": email, "role": role,
           "status": "pending", "invitation_token": secrets.token_urlsafe(32),
           "created_at": now, "expires_at": now + timedelta(days=30),
           "delivery_status": "not_configured", "created_by_user_id": uid}
    result = invites.insert_one(doc)
    doc["_id"] = result.inserted_id
    safe = serialise(doc)
    safe.pop("invitation_token", None)
    log_action(uid, "biashara.team.invitation_created", "biashara_invitation", result.inserted_id, {"email": email, "role": role})
    return created(safe, "Invitation recorded but not delivered: email delivery is not configured.")


@contracts_bp.delete("/team/members/<member_id>")
@require_authenticated
def remove_team_member(member_id):
    uid, business = _owner_business()
    bid = _business_id(business)
    result = collection("jumuiya_biashara_memberships").delete_one({
        "_id": clean_id(member_id), "business_id": bid, "owner_user_id": uid,
        "role": {"$ne": "owner"}
    })
    if not result.deleted_count:
        raise APIError("Member not found or owner membership cannot be removed.", 404, "resource_not_found")
    log_action(uid, "biashara.team.member_removed", "biashara_membership", member_id)
    return ok({"removed": True})


# Business discovery and active-business preference. Existing owner-scoped APIs remain
# unchanged until their service layer is migrated to resolve authorized membership context.
@contracts_bp.get("/businesses")
@require_authenticated
def list_businesses():
    uid = str(current_user_id())
    docs = collection("jumuiya_businesses").find({"owner_user_id": uid}).sort("created_at", -1).limit(100)
    return ok(serialise_many(docs))


@contracts_bp.post("/businesses/active")
@require_authenticated
def set_active_business():
    uid = str(current_user_id())
    data = _body()
    bid = str(data.get("business_id") or "").strip()
    if not bid:
        raise APIError("business_id is required.", 422, "validation_error")
    business = collection("jumuiya_businesses").find_one({"_id": clean_id(bid), "owner_user_id": uid})
    if not business:
        raise APIError("Business is not owned by or accessible to this account.", 403, "business_access_denied")
    now = _now()
    collection("jumuiya_biashara_active_business").update_one(
        {"user_id": uid}, {"$set": {"user_id": uid, "business_id": str(business["_id"]), "updated_at": now}},
        upsert=True)
    log_action(uid, "biashara.active_business.changed", "business", business["_id"], {"business_id": str(business["_id"])})
    return ok({"business_id": str(business["_id"]), "name": business.get("name"), "updated_at": now.isoformat()},
              "Active business preference saved. Existing owner-scoped endpoints still use the primary business.")
