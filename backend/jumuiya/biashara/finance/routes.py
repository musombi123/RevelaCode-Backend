"""Authenticated API for commercial invoices and payment evidence."""
from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import created, ok
from backend.jumuiya.biashara.finance import schemas, services


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
def list_invoices():
    rows = services.list_invoices(
        current_user_id(),
        status=request.args.get("status"),
        limit=request.args.get("limit", 50),
    )
    return ok(rows, "Biashara invoices loaded.", meta={"count": len(rows)})


@biashara_finance_bp.post("/invoices")
@require_authenticated
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
def get_invoice(invoice_id):
    return ok(services.get_invoice(current_user_id(), invoice_id), "Biashara invoice loaded.")


@biashara_finance_bp.post("/invoices/<invoice_id>/issue")
@require_authenticated
def issue_invoice(invoice_id):
    result = services.issue_invoice(current_user_id(), invoice_id)
    return ok(result, "Commercial invoice issued. Tax calculation and eTIMS submission remain not configured unless explicitly enabled.")


@biashara_finance_bp.post("/invoices/<invoice_id>/void")
@require_authenticated
def void_invoice(invoice_id):
    data = _body()
    reason = data.get("reason", "")
    if not isinstance(reason, str):
        raise APIError("reason must be text.", 422, "invalid_finance_payload")
    return ok(services.void_invoice(current_user_id(), invoice_id, reason), "Commercial invoice voided.")


@biashara_finance_bp.post("/invoices/<invoice_id>/payments")
@require_authenticated
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
