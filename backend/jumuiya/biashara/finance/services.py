"""Biashara commercial invoices and payment-evidence records.

This module is not a double-entry ledger or an eTIMS connector. Manual entries
are labelled honestly; provider verification must come from a future adapter.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.audit import log_action
from backend.jumuiya.biashara.tenancy.service import require_permission
from backend.jumuiya.biashara import services as biashara_services
from backend.jumuiya.biashara.sync.outbox import build_outbox_manifest, dispatch_manifest_for_record
from backend.jumuiya.biashara.finance.ledger import (
    post_journal_entry,
    ledger_summary as _ledger_summary,
    list_journal_entries as _list_journal_entries,
)


def now_utc():
    return datetime.now(timezone.utc)


def _clean_id(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return value


def _ser(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat() if value.tzinfo else value.replace(tzinfo=timezone.utc).isoformat()
    if isinstance(value, list):
        return [_ser(item) for item in value]
    if isinstance(value, dict):
        return {("id" if key == "_id" else key): _ser(item) for key, item in value.items()
                if key not in {"request_fingerprint", "outbox_event_manifest", "outbox_enqueued_event_keys"}}
    return value


def _business(user_id, permission=None):
    business = biashara_services._require_business(user_id)
    business_id = str(business.get("id") or business.get("_id") or "")
    if not business_id:
        raise APIError("Business profile has no usable ID.", 409, "business_id_missing")
    if permission:
        require_permission(user_id, permission, business_id=business_id)
    return business, business_id


def _key(value, required=True):
    key = str(value or "").strip()
    if required and not key:
        raise APIError("Send an Idempotency-Key header to make this finance operation safely retryable.", 422, "idempotency_key_required")
    if key and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", key):
        raise APIError("Idempotency-Key must be 8–128 safe characters.", 422, "invalid_idempotency_key")
    return key


def _minor(value, field="amount", allow_zero=False):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise APIError(field.capitalize() + " must be a valid monetary amount.", 422, "invalid_money")
    if not amount.is_finite() or amount < 0 or (amount == 0 and not allow_zero):
        raise APIError(field.capitalize() + " must be non-negative." if allow_zero else field.capitalize() + " must be greater than zero.", 422, "invalid_money")
    return int(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def _fingerprint(data):
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _manifest(key, event_type, entity_type, entity_id, payload, actor, occurred=None):
    return build_outbox_manifest(
        event_key=key, event_type=event_type, entity_type=entity_type,
        entity_id=str(entity_id), payload=payload, actor_user_id=actor,
        occurred_at=occurred,
    )


def _dispatch(source, business_id, record_id):
    try:
        return dispatch_manifest_for_record(source, str(business_id), record_id)
    except Exception as error:
        import logging
        logging.getLogger("jumuiya.biashara.finance").warning(
            "Finance outbox dispatch deferred (source=%s, error=%s)", source, type(error).__name__
        )
        return {"enqueued": 0, "pending": 1, "errors": 1}


def _order_total_minor(order):
    if order.get("total_amount_minor") is not None:
        try:
            total = int(order["total_amount_minor"])
        except (ValueError, TypeError, OverflowError):
            raise APIError("Stored order total is invalid.", 409, "invalid_order_amount")
        if total < 0:
            raise APIError("Stored order total is invalid.", 409, "invalid_order_amount")
        return total
    items = order.get("items") or []
    if items and all(item.get("unit_price") is not None and item.get("quantity") is not None for item in items):
        total = Decimal("0.00")
        for item in items:
            try:
                price = Decimal(str(item["unit_price"]))
                quantity = Decimal(str(item["quantity"]))
            except (InvalidOperation, TypeError, ValueError):
                raise APIError("Stored order line is invalid.", 409, "invalid_order_amount")
            if not price.is_finite() or price < 0 or not quantity.is_finite() or quantity <= 0:
                raise APIError("Stored order line is invalid.", 409, "invalid_order_amount")
            total += (price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return int(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)
    return _minor(order.get("total_amount", 0), "stored order total", allow_zero=True)


def _post_invoice_journal(invoice, user_id):
    """Post issue-time receivable/revenue entry, with tax classification explicitly pending."""
    if invoice.get("status") != "issued":
        return None
    amount_minor = int(invoice.get("total_amount_minor", 0) or 0)
    if amount_minor <= 0:
        # A zero-value invoice has no monetary effect and therefore no journal.
        return None
    invoice_id = str(invoice.get("_id") or invoice.get("id") or "")
    return post_journal_entry(
        business_id=str(invoice.get("business_id") or ""),
        source_key="invoice-issued:" + invoice_id,
        source_type="invoice.issued",
        source_id=invoice_id,
        currency=invoice.get("currency", "KES"),
        lines=[
            {
                "account_code": "accounts_receivable",
                "debit_minor": amount_minor,
                "credit_minor": 0,
                "memo": "Receivable recognised on invoice issue",
            },
            {
                "account_code": "sales_revenue_unclassified",
                "debit_minor": 0,
                "credit_minor": amount_minor,
                "memo": "Commercial invoice total; tax classification pending",
            },
        ],
        actor_user_id=user_id,
        basis="Commercial invoice total posted without tax calculation; tax classification is not configured and must be reviewed before formal accounting use.",
        effective_at=invoice.get("issued_at") or invoice.get("updated_at") or now_utc(),
    )


def _post_provider_payment_journal(payment, user_id):
    """Post a verified, allocated M-Pesa receipt into clearing, not cash-on-hand."""
    if (
        payment.get("payment_status") != "provider_confirmed"
        or payment.get("verification_status") != "provider_verified"
        or payment.get("provider_verified") is not True
        or payment.get("provider_name") != "mpesa_daraja"
        or payment.get("allocation_status") != "allocated"
    ):
        return None
    amount_minor = int(payment.get("amount_minor", 0) or 0)
    if amount_minor <= 0:
        return None
    payment_id = str(payment.get("_id") or payment.get("id") or "")
    invoice_id = str(payment.get("invoice_id") or "")
    return post_journal_entry(
        business_id=str(payment.get("business_id") or ""),
        source_key="provider-payment:" + payment_id,
        source_type="payment.mpesa_allocated",
        source_id=payment_id,
        currency=payment.get("currency", "KES"),
        lines=[
            {
                "account_code": "mpesa_clearing",
                "debit_minor": amount_minor,
                "credit_minor": 0,
                "memo": "M-Pesa receipt verified; settlement still requires reconciliation",
            },
            {
                "account_code": "accounts_receivable",
                "debit_minor": 0,
                "credit_minor": amount_minor,
                "memo": "Provider payment allocated to invoice " + invoice_id[:80],
            },
        ],
        actor_user_id=user_id,
        basis="Daraja STK callback passed the configured callback-IP allow-list, matched checkout/merchant identifiers, receipt uniqueness and exact amount checks. This does not establish bank settlement reconciliation.",
        effective_at=payment.get("provider_transaction_at") or payment.get("provider_verified_at") or payment.get("updated_at") or now_utc(),
    )


def _post_cash_payment_journal(payment, user_id):
    """Post cash-on-hand against receivables only after an allocated cash attestation."""
    if (
        payment.get("payment_status") != "manual_attested"
        or payment.get("verification_status") != "manual_attested"
        or payment.get("allocation_status") != "allocated"
    ):
        return None
    amount_minor = int(payment.get("amount_minor", 0) or 0)
    if amount_minor <= 0:
        return None
    payment_id = str(payment.get("_id") or payment.get("id") or "")
    invoice_id = str(payment.get("invoice_id") or "")
    return post_journal_entry(
        business_id=str(payment.get("business_id") or ""),
        source_key="cash-payment:" + payment_id,
        source_type="payment.cash_allocated",
        source_id=payment_id,
        currency=payment.get("currency", "KES"),
        lines=[
            {
                "account_code": "cash_on_hand",
                "debit_minor": amount_minor,
                "credit_minor": 0,
                "memo": "Cash receipt recorded by manual attestation",
            },
            {
                "account_code": "accounts_receivable",
                "debit_minor": 0,
                "credit_minor": amount_minor,
                "memo": "Cash payment allocated to invoice " + invoice_id[:80],
            },
        ],
        actor_user_id=user_id,
        basis="Manual cash attestation allocated to an issued invoice; not bank reconciliation or external-provider verification.",
        effective_at=payment.get("allocated_at") or payment.get("updated_at") or now_utc(),
    )


def get_ledger_summary(user_id, currency=None, from_date=None, to_date=None):
    _business_data, business_id = _business(user_id, permission="finance.view")
    return _ledger_summary(
        business_id=business_id,
        currency=currency,
        from_date=from_date,
        to_date=to_date,
    )


def get_journal_entries(user_id, limit=50, source_type=None, from_date=None, to_date=None):
    _business_data, business_id = _business(user_id, permission="finance.view")
    return _list_journal_entries(
        business_id=business_id,
        limit=limit,
        source_type=source_type,
        from_date=from_date,
        to_date=to_date,
    )


def _get_invoice(business_id, invoice_id):
    invoice = collection("jumuiya_invoices").find_one({
        "_id": _clean_id(invoice_id), "business_id": str(business_id)
    })
    if not invoice:
        raise APIError("Invoice not found.", 404, "invoice_not_found")
    return invoice


def _invoice_view(invoice, include_payments=True):
    result = _ser(invoice)
    if include_payments:
        docs = collection("jumuiya_payments").find({
            "business_id": str(invoice.get("business_id")),
            "invoice_id": str(invoice.get("_id") or invoice.get("id")),
        }).sort("created_at", -1).limit(100)
        result["payments"] = [_ser(doc) for doc in docs]
    result["etims"] = {
        "status": invoice.get("etims_submission_status", "not_configured"),
        "control_number": None,
        "message": "No approved eTIMS connection is configured for this invoice."
    }
    return result


def list_invoices(user_id, status=None, limit=50):
    _business_data, business_id = _business(user_id, permission="finance.view")
    try:
        limit = min(max(int(limit), 1), 100)
    except (TypeError, ValueError):
        limit = 50
    query = {"business_id": business_id}
    if status:
        status = str(status).strip().lower()
        if status not in {"draft", "issued", "voided"}:
            raise APIError("Unknown invoice state.", 422, "invalid_invoice_status")
        query["status"] = status
    rows = collection("jumuiya_invoices").find(query).sort("created_at", -1).limit(limit)
    return [_invoice_view(row, include_payments=False) for row in rows]


def get_invoice(user_id, invoice_id):
    _business_data, business_id = _business(user_id, permission="finance.view")
    return _invoice_view(_get_invoice(business_id, invoice_id))


def create_invoice(user_id, payload, idempotency_key=""):
    business, business_id = _business(user_id, permission="finance.manage")
    key = _key(idempotency_key, required=False)
    order_id = str(payload.get("order_id") or "").strip()
    if not order_id:
        raise APIError("order_id is required.", 422, "invoice_order_required")
    due_date = str(payload.get("due_date") or "").strip()
    if due_date:
        try:
            date.fromisoformat(due_date)
        except ValueError:
            raise APIError("due_date must use YYYY-MM-DD.", 422, "invalid_due_date")
    notes = str(payload.get("notes") or "").strip()[:1000]

    order = biashara_services.collection("jumuiya_orders").find_one({
        "_id": _clean_id(order_id), "business_id": business_id
    })
    if not order:
        raise APIError("Order not found.", 404, "order_not_found")
    if str(order.get("status") or "pending").lower() == "cancelled":
        raise APIError("A cancelled order cannot be invoiced.", 409, "cancelled_order_invoice")

    canonical_order_id = str(order.get("_id") or order_id)
    fingerprint = _fingerprint({"order_id": canonical_order_id, "due_date": due_date, "notes": notes})
    invoices = collection("jumuiya_invoices")
    if key:
        prior = invoices.find_one({"business_id": business_id, "idempotency_key": key})
        if prior:
            if prior.get("request_fingerprint") != fingerprint:
                raise APIError("Idempotency-Key was reused for a different invoice request.", 409, "idempotency_key_reused")
            _dispatch("jumuiya_invoices", business_id, prior["_id"])
            return _invoice_view(prior)

    prior_order_invoice = invoices.find_one({
        "business_id": business_id, "source_order_id": canonical_order_id,
        "canonical_order_invoice": True
    })
    if prior_order_invoice:
        if prior_order_invoice.get("request_fingerprint") != fingerprint:
            raise APIError("This order already has an invoice with different terms.", 409, "invoice_already_exists")
        _dispatch("jumuiya_invoices", business_id, prior_order_invoice["_id"])
        return _invoice_view(prior_order_invoice)

    total_minor = _order_total_minor(order)
    currency = str(order.get("currency") or business.get("currency") or "KES").upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise APIError("Order currency is invalid.", 409, "invalid_order_currency")

    items = []
    for item in order.get("items") or []:
        try:
            quantity = Decimal(str(item.get("quantity", 0)))
        except (InvalidOperation, TypeError, ValueError):
            raise APIError("Stored order item quantity is invalid.", 409, "invalid_order_inventory")
        if not quantity.is_finite() or quantity <= 0:
            raise APIError("Stored order item quantity is invalid.", 409, "invalid_order_inventory")

        unit_minor = item.get("unit_price_minor")
        if unit_minor is None:
            unit_minor = _minor(item.get("unit_price", 0), "unit price", allow_zero=True)
        try:
            unit_minor = int(unit_minor)
        except (TypeError, ValueError, OverflowError):
            raise APIError("Stored order unit price is invalid.", 409, "invalid_order_amount")
        if unit_minor < 0:
            raise APIError("Stored order unit price is invalid.", 409, "invalid_order_amount")

        line_minor = item.get("line_total_minor")
        if line_minor is None:
            line_minor = int((Decimal(unit_minor) * quantity).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        try:
            line_minor = int(line_minor)
        except (TypeError, ValueError, OverflowError):
            raise APIError("Stored order line total is invalid.", 409, "invalid_order_amount")
        if line_minor < 0:
            raise APIError("Stored order line total is invalid.", 409, "invalid_order_amount")

        items.append({
            "product_id": str(item.get("product_id") or ""),
            "name": str(item.get("name") or "Product")[:160],
            "sku": str(item.get("sku") or "")[:80],
            "quantity": str(quantity.normalize()),
            "unit_price_minor": unit_minor,
            "line_total_minor": line_minor,
            "currency": currency,
            "tax_calculation_status": "not_configured",
            "tax_amount_minor": None,
        })

    invoice_id = ObjectId()
    now = now_utc()
    customer_snapshot = {}
    if order.get("customer_id"):
        customer = biashara_services.collection("jumuiya_customers").find_one({
            "_id": _clean_id(order["customer_id"]), "business_id": business_id
        })
        if customer:
            customer_snapshot = {
                "customer_id": str(customer.get("_id") or ""),
                "name": str(customer.get("name") or "")[:160],
                "email": str(customer.get("email") or "")[:254],
                "phone": str(customer.get("phone") or "")[:40],
            }

    document = {
        "_id": invoice_id,
        "business_id": business_id,
        "source_order_id": canonical_order_id,
        "source_channel": str(order.get("source_channel") or "manual"),
        "canonical_order_invoice": True,
        "invoice_number": None,
        "status": "draft",
        "payment_status": "unpaid",
        "document_type": "commercial_invoice",
        "items": items,
        "customer_snapshot": customer_snapshot,
        "subtotal_minor": total_minor,
        "discount_minor": 0,
        "tax_calculation_status": "not_configured",
        "tax_amount_minor": None,
        "total_amount_minor": total_minor,
        "amount_paid_minor": 0,
        "currency": currency,
        "due_date": due_date or None,
        "notes": notes,
        "etims_submission_status": "not_configured",
        "etims_control_number": None,
        "etims_provider_reference": None,
        "idempotency_key": key or None,
        "request_fingerprint": fingerprint,
        "payment_allocation_keys": [],
        "outbox_event_manifest": [],
        "outbox_enqueued_event_keys": [],
        "created_at": now,
        "updated_at": now,
        "issued_at": None,
        "voided_at": None,
    }
    invoice_event = _manifest(
        "invoice:" + str(invoice_id) + ":created", "invoice.created", "invoice", invoice_id,
        {"status": "draft", "document_type": "commercial_invoice",
         "total_amount_minor": total_minor, "amount_paid_minor": 0,
         "balance_due_minor": total_minor, "currency": currency,
         "tax_submission_status": "not_configured"},
        user_id, now
    )
    document["outbox_event_manifest"] = [invoice_event]
    try:
        invoices.insert_one(document)
    except DuplicateKeyError:
        if key:
            prior = invoices.find_one({"business_id": business_id, "idempotency_key": key})
            if prior and prior.get("request_fingerprint") == fingerprint:
                return _invoice_view(prior)
        prior = invoices.find_one({
            "business_id": business_id, "source_order_id": canonical_order_id,
            "canonical_order_invoice": True
        })
        if prior and prior.get("request_fingerprint") == fingerprint:
            return _invoice_view(prior)
        raise APIError("An invoice already exists for this order or request key.", 409, "invoice_already_exists")
    _dispatch("jumuiya_invoices", business_id, invoice_id)
    log_action(user_id, "biashara.invoice_created", "invoice", invoice_id, {
        "order_id": canonical_order_id, "amount_minor": total_minor, "currency": currency
    })
    return _invoice_view(document)


def issue_invoice(user_id, invoice_id):
    _business_data, business_id = _business(user_id, permission="finance.manage")
    invoices = collection("jumuiya_invoices")
    invoice = _get_invoice(business_id, invoice_id)
    if invoice.get("status") == "issued":
        _post_invoice_journal(invoice, user_id)
        _dispatch("jumuiya_invoices", business_id, invoice["_id"])
        return _invoice_view(invoice)
    if invoice.get("status") != "draft":
        raise APIError("Only a draft invoice can be issued.", 409, "invalid_invoice_transition")

    year = now_utc().year
    counter = collection("jumuiya_finance_counters").find_one_and_update(
        {"business_id": business_id, "sequence_name": "commercial_invoice", "year": year},
        {"$inc": {"value": 1}, "$setOnInsert": {"created_at": now_utc()}},
        upsert=True, return_document=ReturnDocument.AFTER
    )
    number = "INV-" + str(year) + "-" + str(int(counter["value"])).zfill(6)
    now = now_utc()
    event = _manifest(
        "invoice:" + str(invoice["_id"]) + ":issued", "invoice.issued", "invoice", invoice["_id"],
        {"status": "issued", "invoice_number": number,
         "total_amount_minor": int(invoice.get("total_amount_minor", 0)),
         "amount_paid_minor": int(invoice.get("amount_paid_minor", 0)),
         "currency": invoice.get("currency", "KES"),
         "tax_submission_status": invoice.get("etims_submission_status", "not_configured")},
        user_id, now
    )
    updated = invoices.find_one_and_update(
        {"_id": invoice["_id"], "business_id": business_id, "status": "draft"},
        {"$set": {"status": "issued", "invoice_number": number, "issued_at": now, "updated_at": now},
         "$addToSet": {"outbox_event_manifest": event}},
        return_document=ReturnDocument.AFTER
    )
    if not updated:
        latest = _get_invoice(business_id, invoice["_id"])
        if latest.get("status") == "issued":
            _dispatch("jumuiya_invoices", business_id, latest["_id"])
            return _invoice_view(latest)
        raise APIError("Invoice changed before it could be issued.", 409, "invoice_state_conflict")
    _post_invoice_journal(updated, user_id)
    _dispatch("jumuiya_invoices", business_id, updated["_id"])
    log_action(user_id, "biashara.invoice_issued", "invoice", updated["_id"], {
        "invoice_number": number, "amount_minor": updated.get("total_amount_minor", 0)
    })
    return _invoice_view(updated)


def void_invoice(user_id, invoice_id, reason=""):
    """Void an invoice only if no payment has been allocated to it."""
    _business_data, business_id = _business(user_id, permission="finance.manage")
    invoices = collection("jumuiya_invoices")
    invoice = _get_invoice(business_id, invoice_id)
    if invoice.get("status") == "voided":
        return _invoice_view(invoice)
    if invoice.get("status") != "issued":
        raise APIError("Only an issued invoice can be voided.", 409, "invalid_invoice_transition")
    if int(invoice.get("amount_paid_minor", 0) or 0) > 0:
        raise APIError("An invoice with allocated payments cannot be voided. Record a refund or credit-note workflow instead.", 409, "invoice_has_allocated_payments")

    unresolved_payment = collection("jumuiya_payments").find_one({
        "business_id": business_id,
        "invoice_id": str(invoice.get("_id") or invoice.get("id")),
        "allocation_status": {"$in": ["pending", "not_allocated_pending_verification", "allocated"]},
    })
    if unresolved_payment:
        raise APIError(
            "This invoice has payment evidence that must be resolved before voiding.",
            409,
            "invoice_has_unresolved_payment",
        )

    now = now_utc()
    event = _manifest(
        "invoice:" + str(invoice["_id"]) + ":voided", "invoice.voided", "invoice", invoice["_id"],
        {"status": "voided", "invoice_number": invoice.get("invoice_number"),
         "total_amount_minor": int(invoice.get("total_amount_minor", 0)),
         "currency": invoice.get("currency", "KES")},
        user_id, now
    )
    updated = invoices.find_one_and_update(
        {"_id": invoice["_id"], "business_id": business_id, "status": "issued", "amount_paid_minor": 0},
        {"$set": {"status": "voided", "voided_at": now, "void_reason": str(reason or "").strip()[:500], "updated_at": now},
         "$addToSet": {"outbox_event_manifest": event}},
        return_document=ReturnDocument.AFTER
    )
    if not updated:
        latest = _get_invoice(business_id, invoice["_id"])
        if latest.get("status") == "voided":
            return _invoice_view(latest)
        raise APIError("Invoice changed while voiding; reload and retry.", 409, "invoice_state_conflict")
    _dispatch("jumuiya_invoices", business_id, updated["_id"])
    log_action(user_id, "biashara.invoice_voided", "invoice", updated["_id"], {"reason": str(reason or "")[:120]})
    return _invoice_view(updated)


def _mark_payment_allocation(payment, invoice):
    """Allocate only manual cash attestations or provider-verified payment events."""
    business_id = str(payment["business_id"])
    payment_id = payment["_id"]
    invoice_id = str(invoice["_id"])
    payment_key = str(payment["idempotency_key"])
    alloc_key = "payment:" + payment_key
    amount_minor = int(payment["amount_minor"])
    manual_cash = (
        payment.get("payment_status") == "manual_attested"
        and payment.get("verification_status") == "manual_attested"
    )
    verified_mpesa = (
        payment.get("payment_status") == "provider_confirmed"
        and payment.get("verification_status") == "provider_verified"
        and payment.get("provider_verified") is True
        and payment.get("provider_name") == "mpesa_daraja"
    )
    if not (manual_cash or verified_mpesa):
        collection("jumuiya_payments").update_one(
            {"_id": payment_id, "business_id": business_id},
            {"$set": {"allocation_status": "not_allocated_pending_verification", "updated_at": now_utc()}}
        )
        return collection("jumuiya_payments").find_one({"_id": payment_id, "business_id": business_id}) or payment

    invoices = collection("jumuiya_invoices")
    for _attempt in range(12):
        latest = _get_invoice(business_id, invoice_id)
        if alloc_key in (latest.get("payment_allocation_keys") or []):
            break
        if latest.get("status") != "issued":
            raise APIError("Payment cannot be allocated to a non-issued invoice.", 409, "invoice_not_payable")
        total = int(latest.get("total_amount_minor", 0))
        paid = int(latest.get("amount_paid_minor", 0))
        if paid + amount_minor > total:
            updated_payment = collection("jumuiya_payments").find_one_and_update(
                {"_id": payment_id, "business_id": business_id},
                {"$set": {"allocation_status": "allocation_conflict", "updated_at": now_utc()},
                 "$addToSet": {"outbox_event_manifest": _manifest(
                     "payment:" + payment_key + ":allocation-conflict", "payment.allocation_conflict", "payment", payment_id,
                     {"status": "allocation_conflict", "payment_status": payment.get("payment_status"),
                      "amount_minor": amount_minor, "currency": payment.get("currency", "KES")},
                     payment.get("recorded_by_user_id")
                 )}},
                return_document=ReturnDocument.AFTER
            ) or payment
            _dispatch("jumuiya_payments", business_id, payment_id)
            return updated_payment

        new_paid = paid + amount_minor
        pay_state = "paid" if new_paid == total else "partially_paid"
        now = now_utc()
        event = _manifest(
            "invoice:" + invoice_id + ":allocation:" + payment_key, "invoice.payment_allocated", "invoice", invoice_id,
            {"status": "issued", "payment_status": pay_state, "amount_paid_minor": new_paid,
             "balance_due_minor": total - new_paid, "payment_id": str(payment_id),
             "amount_minor": amount_minor, "currency": latest.get("currency", "KES")},
            payment.get("recorded_by_user_id"), now
        )
        updated_invoice = invoices.find_one_and_update(
            {"_id": latest["_id"], "business_id": business_id, "status": "issued",
             "amount_paid_minor": paid, "payment_allocation_keys": {"$ne": alloc_key}},
            {"$set": {"amount_paid_minor": new_paid, "payment_status": pay_state, "updated_at": now},
             "$addToSet": {"payment_allocation_keys": alloc_key, "outbox_event_manifest": event}},
            return_document=ReturnDocument.AFTER
        )
        if updated_invoice:
            break
    else:
        raise APIError("Invoice changed repeatedly while allocating payment. Retry with the same Idempotency-Key.", 409, "payment_allocation_conflict")

    payment_event = _manifest(
        "payment:" + payment_key + ":allocated", "payment.allocated", "payment", payment_id,
        {"status": "allocated", "payment_status": payment.get("payment_status"),
         "amount_minor": amount_minor, "currency": payment.get("currency", "KES"),
         "invoice_id": invoice_id},
        payment.get("recorded_by_user_id")
    )
    updated_payment = collection("jumuiya_payments").find_one_and_update(
        {"_id": payment_id, "business_id": business_id},
        {"$set": {"allocation_status": "allocated", "allocated_at": now_utc(), "updated_at": now_utc()},
         "$addToSet": {"outbox_event_manifest": payment_event}},
        return_document=ReturnDocument.AFTER
    ) or payment
    _dispatch("jumuiya_invoices", business_id, invoice_id)
    _dispatch("jumuiya_payments", business_id, payment_id)
    if manual_cash:
        _post_cash_payment_journal(updated_payment, payment.get("recorded_by_user_id") or "")
    elif verified_mpesa:
        _post_provider_payment_journal(updated_payment, payment.get("recorded_by_user_id") or "")
    return updated_payment


def record_payment(user_id, invoice_id, payload, idempotency_key):
    """Persist payment evidence; only manual cash attestation affects invoice balance."""
    _business_data, business_id = _business(user_id, permission="finance.manage")
    key = _key(idempotency_key, required=True)
    invoice = _get_invoice(business_id, invoice_id)
    if invoice.get("status") != "issued":
        raise APIError("Payments can only be recorded against an issued invoice.", 409, "invoice_not_payable")

    amount_minor = _minor(payload.get("amount"), "payment amount")
    method = str(payload.get("payment_method") or "").strip().lower()
    if method not in {"cash", "mpesa", "mobile_money", "bank", "card", "other"}:
        raise APIError("Unsupported payment method.", 422, "invalid_payment_method")
    reference = str(payload.get("reference") or "").strip()[:160]
    fingerprint = _fingerprint({
        "invoice_id": str(invoice["_id"]), "amount_minor": amount_minor,
        "payment_method": method, "reference": reference
    })
    payments = collection("jumuiya_payments")
    prior = payments.find_one({"business_id": business_id, "idempotency_key": key})
    if prior:
        if prior.get("request_fingerprint") != fingerprint:
            raise APIError("Idempotency-Key was reused for different payment data.", 409, "idempotency_key_reused")
        if prior.get("allocation_status") == "pending":
            _mark_payment_allocation(prior, invoice)
        current_payment = payments.find_one({"_id": prior["_id"], "business_id": business_id}) or prior
        _post_cash_payment_journal(current_payment, user_id)
        return _ser(current_payment)

    now = now_utc()
    payment_id = ObjectId()
    # This endpoint cannot establish provider verification. Cash is a manual
    # owner attestation; external rail references remain unverified evidence.
    manual_cash = method == "cash"
    payment_status = "manual_attested" if manual_cash else "verification_required"
    allocation_status = "pending" if manual_cash else "not_allocated_pending_verification"
    document = {
        "_id": payment_id,
        "business_id": business_id,
        "invoice_id": str(invoice["_id"]),
        "order_id": str(invoice.get("source_order_id") or ""),
        "idempotency_key": key,
        "request_fingerprint": fingerprint,
        "amount_minor": amount_minor,
        "currency": invoice.get("currency", "KES"),
        "payment_method": method,
        "reference": reference,
        "payment_status": payment_status,
        "verification_status": "manual_attested" if manual_cash else "unverified_manual",
        "provider_verified": False,
        "provider_name": None,
        "provider_event_id": None,
        "allocation_status": allocation_status,
        "source": "manual_entry",
        "recorded_by_user_id": str(user_id),
        "created_at": now,
        "updated_at": now,
        "allocated_at": None,
        "reversed_at": None,
    }
    event = _manifest(
        "payment:" + key + ":recorded", "payment.recorded", "payment", payment_id,
        {"status": allocation_status, "payment_status": payment_status,
         "payment_verification_status": document["verification_status"],
         "payment_method": method, "amount_minor": amount_minor,
         "currency": document["currency"], "invoice_id": str(invoice["_id"])},
        user_id, now
    )
    document["outbox_event_manifest"] = [event]
    document["outbox_enqueued_event_keys"] = []
    try:
        payments.insert_one(document)
    except DuplicateKeyError:
        prior = payments.find_one({"business_id": business_id, "idempotency_key": key})
        if prior and prior.get("request_fingerprint") == fingerprint:
            return _ser(prior)
        raise APIError("A payment with this idempotency key already exists.", 409, "idempotency_key_reused")

    _dispatch("jumuiya_payments", business_id, payment_id)
    log_action(user_id, "biashara.payment_recorded", "payment", payment_id, {
        "invoice_id": str(invoice["_id"]), "amount_minor": amount_minor,
        "payment_method": method, "payment_status": payment_status
    })
    payment = payments.find_one({"_id": payment_id, "business_id": business_id}) or document
    if manual_cash:
        payment = _mark_payment_allocation(payment, invoice)
    return _ser(payment)
