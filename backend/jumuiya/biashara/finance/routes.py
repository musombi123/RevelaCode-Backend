"""Authenticated API for commercial invoices and payment evidence."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import created, ok
from backend.jumuiya.biashara.tenancy.service import require_business_permission
from backend.jumuiya.biashara.finance import schemas, services, mpesa


biashara_finance_bp = Blueprint("jumuiya_biashara_finance", __name__)


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON request body is required.", 400, "invalid_json")
    return data


def _validate(schema, data):
    try:
        return schema(data)
    except ValueError as error:
        raise APIError(str(error), 422, "invalid_finance_payload")


@biashara_finance_bp.get("/invoices")
@require_authenticated
@require_business_permission("finance.view")
def list_invoices():
    rows = services.list_invoices(
        current_user_id(),
        status=request.args.get("status"),
        limit=request.args.get("limit", 50),
    )
    return ok(rows, "Biashara invoices loaded.", meta={"count": len(rows)})


@biashara_finance_bp.post("/invoices")
@require_authenticated
@require_business_permission("finance.manage")
def create_invoice():
    payload = _validate(schemas.invoice_payload, _body())
    result = services.create_invoice(
        current_user_id(),
        payload,
        idempotency_key=request.headers.get("Idempotency-Key", ""),
    )
    return created(result, "Draft commercial invoice created or recovered.")


@biashara_finance_bp.get("/invoices/<invoice_id>")
@require_authenticated
@require_business_permission("finance.view")
def get_invoice(invoice_id):
    return ok(services.get_invoice(current_user_id(), invoice_id), "Biashara invoice loaded.")


@biashara_finance_bp.post("/invoices/<invoice_id>/issue")
@require_authenticated
@require_business_permission("finance.manage")
def issue_invoice(invoice_id):
    result = services.issue_invoice(current_user_id(), invoice_id)
    return ok(result, "Commercial invoice issued. Tax calculation and eTIMS submission remain not configured unless explicitly enabled.")


@biashara_finance_bp.post("/invoices/<invoice_id>/void")
@require_authenticated
@require_business_permission("finance.manage")
def void_invoice(invoice_id):
    data = _body()
    reason = data.get("reason", "")
    if not isinstance(reason, str):
        raise APIError("reason must be text.", 422, "invalid_finance_payload")
    return ok(services.void_invoice(current_user_id(), invoice_id, reason), "Commercial invoice voided.")


@biashara_finance_bp.post("/invoices/<invoice_id>/payments")
@require_authenticated
@require_business_permission("finance.manage")
def record_payment(invoice_id):
    payload = _validate(schemas.payment_payload, _body())
    result = services.record_payment(
        current_user_id(),
        invoice_id,
        payload,
        idempotency_key=request.headers.get("Idempotency-Key", ""),
    )
    message = (
        "Payment evidence recorded. External payment remains unverified until the configured provider confirms it."
        if result.get("verification_status") == "unverified_manual"
        else "Cash receipt recorded by manual attestation and allocated to the invoice."
    )
    return created(result, message)

@biashara_finance_bp.get("/ledger/summary")
@require_authenticated
@require_business_permission("finance.view")
def ledger_summary():
    result = services.get_ledger_summary(
        current_user_id(),
        currency=request.args.get("currency"),
        from_date=request.args.get("from_date"),
        to_date=request.args.get("to_date"),
    )
    return ok(result, "Biashara operational ledger summary loaded.")


@biashara_finance_bp.get("/ledger/entries")
@require_authenticated
@require_business_permission("finance.view")
def ledger_entries():
    rows = services.get_journal_entries(
        current_user_id(),
        limit=request.args.get("limit", 50),
        source_type=request.args.get("source_type"),
        from_date=request.args.get("from_date"),
        to_date=request.args.get("to_date"),
    )
    return ok(rows, "Biashara journal entries loaded.", meta={"count": len(rows), "limit": min(max(int(request.args.get("limit", 50)) if str(request.args.get("limit", 50)).isdigit() else 50, 1), 100)})


@biashara_finance_bp.post("/invoices/<invoice_id>/mpesa/stk-push")
@require_authenticated
@require_business_permission("finance.manage")
def request_mpesa_stk_push(invoice_id):
    payload = _validate(schemas.mpesa_stk_payload, _body())
    result = mpesa.start_stk_push(
        current_user_id(),
        invoice_id,
        payload,
        idempotency_key=request.headers.get("Idempotency-Key", ""),
    )
    return created(
        result,
        "M-Pesa STK Push requested. The invoice is not paid until a correlated, allow-listed Daraja callback is validated and allocated.",
    )


@biashara_finance_bp.get("/mpesa/intents")
@require_authenticated
@require_business_permission("finance.view")
def list_mpesa_intents():
    rows = mpesa.list_mpesa_intents(
        current_user_id(),
        limit=request.args.get("limit", 50),
        status=request.args.get("status"),
    )
    return ok(rows, "Biashara M-Pesa payment intents loaded.", meta={"count": len(rows)})


@biashara_finance_bp.post("/mpesa/callbacks/reprocess")
@require_authenticated
@require_business_permission("finance.manage")
def reprocess_mpesa_callbacks():
    report = mpesa.process_pending_callbacks(current_user_id(), limit=100)
    return ok(report, "Pending M-Pesa callbacks checked for safe correlation recovery.")


@biashara_finance_bp.post("/mpesa/callback/<connection_id>")
def receive_mpesa_callback(connection_id):
    if request.content_length is not None and request.content_length > mpesa.MAX_CALLBACK_BODY_BYTES:
        raise APIError("M-Pesa callback body exceeds the allowed size.", 413, "mpesa_callback_body_invalid")
    raw_body = request.stream.read(mpesa.MAX_CALLBACK_BODY_BYTES + 1)
    result = mpesa.receive_stk_callback(
        connection_id,
        raw_body,
        request.remote_addr,
    )
    # Daraja callbacks are server-to-server. Return the provider acknowledgement
    # directly rather than the application's standard response envelope.
    return jsonify({
        "ResultCode": 0,
        "ResultDesc": "Accepted",
        "event_status": result.get("event_status"),
        "duplicate": result.get("duplicate", False),
        "effects_applied": result.get("effects_applied", False),
    }), 200

