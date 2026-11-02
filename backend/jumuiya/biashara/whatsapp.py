"""Tenant-safe, read-only WhatsApp commands for Biashara.

This reuses the Meta Cloud API credentials and signature model already used by
Elimu, but does not share Elimu's school/parent identity or fee data. A sender is
resolved through a hash-only central phone index to one active company employee;
the authenticated company membership and role are revalidated before any tenant
database is read.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from flask import Blueprint, request
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.biashara.access import resolve_business_access
from backend.jumuiya.biashara.templates import has_permission
from backend.jumuiya.biashara.tenant_store import tenant_collection, set_business_tenant_context
from backend.jumuiya.core.database import collection as core_collection

whatsapp_bp = Blueprint("jumuiya_biashara_whatsapp", __name__)
LOCAL_ZONE = ZoneInfo("Africa/Nairobi")
PHONE_IDENTITIES = "jumuiya_biashara_whatsapp_identities"
INBOUND_MESSAGES = "jumuiya_biashara_whatsapp_inbound"


def _now():
    return datetime.now(timezone.utc)


def valid_meta_signature(raw_body, signature, app_secret):
    if not app_secret or not signature:
        return False
    expected = "sha256=" + hmac.new(
        str(app_secret).encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(str(signature).strip(), expected)


def _text(value, maximum=500):
    result = str(value or "").strip()
    return result[:maximum]


def normalize_phone(value):
    """Normalize Kenyan or international WhatsApp numbers to E.164."""
    raw = _text(value, 80)
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        normalized = "+" + digits
    elif digits.startswith("254") and len(digits) == 12:
        normalized = "+" + digits
    elif digits.startswith("0") and len(digits) == 10:
        normalized = "+254" + digits[1:]
    elif digits.startswith(("7", "1")) and len(digits) == 9:
        normalized = "+254" + digits
    else:
        return ""
    return normalized if re.fullmatch(r"\+[1-9]\d{7,14}", normalized) else ""


def phone_hash(value):
    normalized = normalize_phone(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def ensure_whatsapp_identity_indexes():
    identities = core_collection(PHONE_IDENTITIES)
    identities.create_index(
        [("phone_hash", ASCENDING), ("status", ASCENDING)],
        name="ix_biashara_whatsapp_phone_status",
    )
    identities.create_index(
        [("business_id", ASCENDING), ("employee_id", ASCENDING)],
        unique=True,
        name="uq_biashara_whatsapp_employee",
    )
    inbound = core_collection(INBOUND_MESSAGES)
    inbound.create_index([("created_at", ASCENDING)], name="ix_biashara_whatsapp_inbound_created")


def sync_employee_whatsapp_identity(employee):
    """Upsert one hash-only phone mapping for an already-linked active employee."""
    ensure_whatsapp_identity_indexes()
    employees = core_collection(PHONE_IDENTITIES)
    business_id = str(employee.get("business_id") or "")
    employee_id = str(employee.get("_id") or employee.get("id") or "")
    user_id = str(employee.get("user_id") or "")
    digest = phone_hash(employee.get("phone"))
    active = bool(
        employee.get("status") == "active"
        and user_id
        and digest
    )
    if not business_id or not employee_id:
        return False
    update = {
        "business_id": business_id,
        "employee_id": employee_id,
        "user_id": user_id if active else "",
        "phone_hash": digest if active else "",
        "status": "active" if active else "inactive",
        "updated_at": _now(),
    }
    employees.update_one(
        {"business_id": business_id, "employee_id": employee_id},
        {"$set": update, "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )
    return active


def _send_whatsapp_text(recipient, text_body):
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    api_version = (os.getenv("WHATSAPP_API_VERSION") or "v26.0").strip()
    if not access_token or not phone_number_id:
        raise RuntimeError("whatsapp_cloud_api_not_configured")

    import requests

    response = requests.post(
        f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalize_phone(recipient).lstrip("+"),
            "type": "text",
            "text": {"preview_url": False, "body": _text(text_body, 3800)},
        },
        timeout=(5, 20),
    )
    try:
        result = response.json()
    except ValueError:
        result = {}
    if response.status_code >= 400 or not isinstance(result.get("messages"), list) or not result["messages"]:
        raise RuntimeError("whatsapp_text_delivery_failed")
    return _text(result["messages"][0].get("id"), 240)


def _resolve_employee(sender):
    digest = phone_hash(sender)
    if not digest:
        return None, "This phone number is not in a supported format. Use a Kenyan mobile number such as 0712345678."
    ensure_whatsapp_identity_indexes()
    matches = list(core_collection(PHONE_IDENTITIES).find({
        "phone_hash": digest,
        "status": "active",
    }).limit(3))
    # A phone registered to multiple companies/accounts is deliberately
    # ambiguous. Never guess which company the sender intended.
    unique = {(row.get("business_id"), row.get("employee_id"), row.get("user_id")) for row in matches}
    if len(unique) != 1:
        return None, (
            "This number is not linked to one unique active Biashara employee account. "
            "Ask your company HR/Admin to link your WhatsApp number to your accepted company account."
        )
    row = matches[0]
    business_id = str(row.get("business_id") or "")
    user_id = str(row.get("user_id") or "")
    context = resolve_business_access(user_id, business_id)
    if not context:
        return None, "Your company membership is not active. Contact the company administrator."
    business = context.get("business") or {}
    if business.get("status") != "active" or business.get("verification_status") != "verified":
        return None, "This company is not currently active and verified for Biashara access."
    membership_role = "owner" if context.get("is_owner") else str(context.get("role") or "viewer")
    set_business_tenant_context(
        business_id,
        business_slug=business.get("slug"),
        migrate_legacy=True,
    )
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        employee_object_id = ObjectId(str(row.get("employee_id")))
    except (InvalidId, TypeError, ValueError):
        return None, "Your employee link needs to be repaired by company HR."
    employee = tenant_collection("jumuiya_biashara_employees", business_id).find_one({
        "_id": employee_object_id,
        "business_id": business_id,
        "user_id": user_id,
        "status": "active",
    })
    if not employee or phone_hash(employee.get("phone")) != digest:
        return None, "Your employee link could not be verified. Contact company HR."
    return {
        "business": business,
        "business_id": business_id,
        "user_id": user_id,
        "role": membership_role,
        "employee": employee,
    }, ""


def _daily_window(now=None):
    current = now or _now()
    local_now = current.astimezone(LOCAL_ZONE)
    start_local = datetime.combine(local_now.date(), time.min, tzinfo=LOCAL_ZONE)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _money(value):
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")
    return amount if amount.is_finite() else Decimal("0.00")


def _sales_today(context):
    start, end = _daily_window()
    sales = tenant_collection("jumuiya_sales", context["business_id"])
    records = list(sales.find({
        "business_id": context["business_id"],
        "created_at": {"$gte": start, "$lt": end},
    }).limit(5000))
    total = sum((_money(row.get("amount")) for row in records), Decimal("0.00"))
    top_products = {}
    for sale in records:
        items = sale.get("items") if isinstance(sale.get("items"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = _text(item.get("product_name") or item.get("name") or item.get("description"), 120)
            if not name:
                continue
            try:
                quantity = Decimal(str(item.get("quantity") or 0))
            except (InvalidOperation, TypeError, ValueError):
                quantity = Decimal("0")
            top_products[name] = top_products.get(name, Decimal("0")) + quantity
    best = sorted(top_products.items(), key=lambda pair: pair[1], reverse=True)[:1]
    company_name = _text(context["business"].get("name"), 100) or "Your company"
    response = [
        f"{company_name} — sales today ({datetime.now(LOCAL_ZONE).date().isoformat()})",
        f"Revenue: KSh {total:,.2f}",
        f"Transactions: {len(records)}",
        f"Top product: {best[0][0]} ({best[0][1]:g})" if best else "Top product: no item-level records",
    ]
    if len(records) >= 5000:
        response.append("Note: report reached the 5,000-record response cap.")
    return "\n".join(response)


def _stock_alerts(context):
    products = tenant_collection("jumuiya_products", context["business_id"])
    records = list(products.find({
        "business_id": context["business_id"],
        "status": {"$ne": "deleted"},
    }).limit(2000))
    alerts = []
    for product in records:
        try:
            quantity = Decimal(str(product.get("stock_quantity") or 0))
            threshold = Decimal(str(product.get("reorder_level", 10) or 10))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if quantity <= threshold:
            alerts.append((quantity, _text(product.get("name"), 100), threshold))
    alerts.sort(key=lambda item: item[0])
    company_name = _text(context["business"].get("name"), 100) or "Your company"
    lines = [f"{company_name} — stock alerts", f"Products at/below reorder level: {len(alerts)}"]
    for quantity, name, threshold in alerts[:15]:
        lines.append(f"• {name}: {quantity:g} remaining (reorder level {threshold:g})")
    if len(alerts) > 15:
        lines.append(f"...and {len(alerts) - 15} more.")
    return "\n".join(lines)


def _production_today(context):
    start, end = _daily_window()
    batches = tenant_collection("jumuiya_factory_production_batches", context["business_id"])
    rows = list(batches.find({
        "business_id": context["business_id"],
        "created_at": {"$gte": start, "$lt": end},
    }).limit(2000))
    input_total = sum((_money(row.get("input_quantity")) for row in rows), Decimal("0.00"))
    output_total = sum((_money(row.get("actual_output_quantity")) for row in rows), Decimal("0.00"))
    waste_total = sum((_money(row.get("wastage_quantity")) for row in rows), Decimal("0.00"))
    completed = [row for row in rows if row.get("actual_output_quantity") is not None]
    yield_pct = (output_total / input_total * Decimal("100")) if input_total else Decimal("0")
    company_name = _text(context["business"].get("name"), 100) or "Your company"
    return "\n".join([
        f"{company_name} — production today ({datetime.now(LOCAL_ZONE).date().isoformat()})",
        f"Batches started: {len(rows)}",
        f"Batches completed: {len(completed)}",
        f"Material input: {input_total:g}",
        f"Finished output: {output_total:g}",
        f"Wastage: {waste_total:g}",
        f"Output/input yield: {yield_pct:.2f}%",
    ])


def build_command_reply(context, message_text):
    """Dispatch only a small, explicit set of read-only management commands."""
    command = re.sub(r"\s+", " ", _text(message_text, 500).lower()).strip()
    if command in {"help", "commands", "menu"}:
        return (
            "Biashara Assistant commands:\n"
            "• sales today\n"
            "• stock alerts\n"
            "• production today\n"
            "Only read-only reports are available. For other actions, sign in to Biashara OS."
        )
    if command in {"sales today", "today sales", "sales report today"}:
        if not has_permission(context["role"], "sales.view"):
            return "Your company role does not permit access to sales reports."
        return _sales_today(context)
    if command in {"stock alerts", "low stock", "stock today"}:
        if not has_permission(context["role"], "inventory.view"):
            return "Your company role does not permit access to stock reports."
        return _stock_alerts(context)
    if command in {"production today", "today production", "production report today"}:
        if not has_permission(context["role"], "production.view"):
            return "Your company role does not permit access to production reports."
        return _production_today(context)
    return "I do not recognize that command. Send HELP to see the available read-only Biashara reports."


@whatsapp_bp.get("/whatsapp/webhook")
def verify_biashara_whatsapp_webhook():
    expected_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "").strip()
    mode = request.args.get("hub.mode", "")
    received_token = request.args.get("hub.verify_token", "")
    challenge = request.args.get("hub.challenge", "")
    if not expected_token:
        return "WhatsApp webhook verify token is not configured.", 503
    if mode == "subscribe" and challenge and hmac.compare_digest(received_token, expected_token):
        return challenge, 200, {"Content-Type": "text/plain; charset=utf-8"}
    return "Forbidden", 403


@whatsapp_bp.post("/whatsapp/webhook")
def receive_biashara_whatsapp_webhook():
    app_secret = os.getenv("WHATSAPP_APP_SECRET", "").strip()
    if not app_secret:
        return "WhatsApp webhook signature verification is not configured.", 503
    raw_body = request.get_data(cache=True)
    signature = request.headers.get("X-Hub-Signature-256", "").strip()
    if not valid_meta_signature(raw_body, signature, app_secret):
        return "Invalid webhook signature.", 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}, 200

    messages = []
    for entry in payload.get("entry", []) if isinstance(payload.get("entry"), list) else []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", []) if isinstance(entry.get("changes"), list) else []:
            if not isinstance(change, dict) or change.get("field") != "messages":
                continue
            value = change.get("value") if isinstance(change.get("value"), dict) else {}
            for inbound in value.get("messages", []) if isinstance(value.get("messages"), list) else []:
                if isinstance(inbound, dict) and _text(inbound.get("type"), 30).lower() == "text":
                    messages.append(inbound)

    for inbound in messages:
        message_id = _text(inbound.get("id"), 240)
        sender = normalize_phone(inbound.get("from"))
        text_obj = inbound.get("text") if isinstance(inbound.get("text"), dict) else {}
        message_text = _text(text_obj.get("body"), 500)
        if not message_id or not sender or not message_text:
            continue

        events = core_collection(INBOUND_MESSAGES)
        sender_digest = phone_hash(sender)
        try:
            events.insert_one({
                "_id": message_id,
                "sender_hash": sender_digest,
                "status": "processing",
                "created_at": _now(),
            })
        except DuplicateKeyError:
            # Meta retries must never produce a second report or duplicate reply.
            continue

        reply = ""
        outbound_id = ""
        try:
            context, identity_error = _resolve_employee(sender)
            if not context:
                reply = identity_error
            else:
                reply = build_command_reply(context, message_text)
            outbound_id = _send_whatsapp_text(sender, reply)
            events.update_one(
                {"_id": message_id, "status": "processing"},
                {"$set": {"status": "replied", "outbound_message_id": outbound_id, "replied_at": _now()}},
            )
        except Exception:
            events.update_one(
                {"_id": message_id, "status": "processing"},
                {"$set": {"status": "delivery_failed", "updated_at": _now()}},
            )
            # Do not return provider secrets or exception details to Meta.
    return {"status": "accepted"}, 200
