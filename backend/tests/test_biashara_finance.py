import sys
import types
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from bson import ObjectId

# This test uses in-memory collections only; do not initialize a live DB client.
_missing = object()
_original = sys.modules.get("backend.db", _missing)
_stub = types.ModuleType("backend.db")
_stub.get_db = lambda: None
sys.modules["backend.db"] = _stub
try:
    from backend.jumuiya.biashara.finance import services as finance
    from backend.jumuiya.biashara.finance import ledger
    from backend.jumuiya.biashara import services as biashara
finally:
    if _original is _missing:
        sys.modules.pop("backend.db", None)
    else:
        sys.modules["backend.db"] = _original

from backend.jumuiya.core.errors import APIError


def _get_path(doc, key):
    value = doc
    for part in key.split("."):
        if isinstance(value, list):
            value = [item.get(part) for item in value if isinstance(item, dict) and part in item]
        elif isinstance(value, dict):
            value = value.get(part, _missing)
        else:
            return _missing
    return value


def _matches(doc, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(doc, option) for option in expected):
                return False
            continue
        actual = _get_path(doc, key)
        if isinstance(expected, dict) and any(k.startswith("$") for k in expected):
            for operator, value in expected.items():
                if operator == "$exists":
                    if (actual is not _missing) != bool(value):
                        return False
                elif operator == "$type":
                    if value == "string" and not isinstance(actual, str):
                        return False
                elif operator == "$ne":
                    if actual is not _missing and (actual == value or isinstance(actual, list) and value in actual):
                        return False
                elif operator == "$in":
                    if actual not in value:
                        return False
                else:
                    raise AssertionError("Unsupported fake Mongo query operator: " + operator)
        elif actual is _missing or actual != expected:
            return False
    return True


def _set(document, key, value):
    parts = key.split(".")
    current = document
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = deepcopy(value)


class Cursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, field, direction=1):
        self.documents.sort(key=lambda doc: doc.get(field), reverse=direction < 0)
        return self

    def limit(self, amount):
        self.documents = self.documents[:amount]
        return self

    def __iter__(self):
        return iter(deepcopy(self.documents))


class Collection:
    def __init__(self, documents=None):
        self.documents = [deepcopy(item) for item in (documents or [])]

    def find_one(self, query):
        for doc in self.documents:
            if _matches(doc, query):
                return deepcopy(doc)
        return None

    def find(self, query, projection=None):
        return Cursor([doc for doc in self.documents if _matches(doc, query)])

    def insert_one(self, document):
        value = deepcopy(document)
        value["_id"] = value.get("_id") or ObjectId()
        # Unit-level uniqueness for our invoice/payment idempotency constraints.
        for key in ("idempotency_key",):
            if value.get(key) is not None and self.find_one({
                "business_id": value.get("business_id"), key: value[key]
            }):
                from pymongo.errors import DuplicateKeyError
                raise DuplicateKeyError("duplicate idempotency key")
        if value.get("canonical_order_invoice") and self.find_one({
            "business_id": value.get("business_id"),
            "source_order_id": value.get("source_order_id"),
            "canonical_order_invoice": True,
        }):
            from pymongo.errors import DuplicateKeyError
            raise DuplicateKeyError("duplicate order invoice")
        self.documents.append(value)
        return types.SimpleNamespace(inserted_id=value["_id"])

    def _apply(self, doc, update):
        for key, value in update.get("$setOnInsert", {}).items():
            if key not in doc:
                _set(doc, key, value)
        for key, value in update.get("$set", {}).items():
            _set(doc, key, value)
        for key, value in update.get("$inc", {}).items():
            doc[key] = doc.get(key, 0) + value
        for key, value in update.get("$addToSet", {}).items():
            target = doc.setdefault(key, [])
            if value not in target:
                target.append(deepcopy(value))
        for key in update.get("$unset", {}):
            doc.pop(key, None)

    def find_one_and_update(self, query, update, upsert=False, return_document=None):
        for doc in self.documents:
            if _matches(doc, query):
                self._apply(doc, update)
                return deepcopy(doc)
        if upsert:
            doc = {}
            for key, value in query.items():
                if not key.startswith("$") and not isinstance(value, dict):
                    doc[key] = value
            self._apply(doc, update)
            doc["_id"] = ObjectId()
            self.documents.append(doc)
            return deepcopy(doc)
        return None

    def update_one(self, query, update):
        for doc in self.documents:
            if _matches(doc, query):
                self._apply(doc, update)
                return types.SimpleNamespace(matched_count=1, modified_count=1)
        return types.SimpleNamespace(matched_count=0, modified_count=0)

    def aggregate(self, pipeline):
        rows = deepcopy(self.documents)
        for stage in pipeline:
            if "$match" in stage:
                rows = [doc for doc in rows if _matches(doc, stage["$match"])]
            elif "$unwind" in stage:
                field = stage["$unwind"].lstrip("$")
                expanded = []
                for doc in rows:
                    values = doc.get(field)
                    if isinstance(values, list):
                        for value in values:
                            clone = deepcopy(doc)
                            clone[field] = deepcopy(value)
                            expanded.append(clone)
                rows = expanded
            elif "$group" in stage:
                spec = stage["$group"]
                grouped = {}
                for doc in rows:
                    key = {}
                    for output_name, expression in spec["_id"].items():
                        value = _get_path(doc, expression.lstrip("$"))
                        if isinstance(value, list):
                            value = value[0] if value else None
                        key[output_name] = value
                    token = tuple(sorted(key.items()))
                    group = grouped.setdefault(token, {"_id": key, "debit_minor": 0, "credit_minor": 0, "line_count": 0})
                    for output_name, expression in spec.items():
                        if output_name == "_id":
                            continue
                        operation, field = next(iter(expression.items()))
                        if isinstance(field, (int, float)):
                            value = field
                        else:
                            value = _get_path(doc, field.lstrip("$"))
                            if isinstance(value, list):
                                value = value[0] if value else 0
                            value = 1 if value is _missing else value
                        if operation == "$sum":
                            group[output_name] = group.get(output_name, 0) + value
                rows = list(grouped.values())
            elif "$sort" in stage:
                sort_fields = list(stage["$sort"].items())
                for field, direction in reversed(sort_fields):
                    def sort_value(doc, path=field):
                        value = _get_path(doc, path)
                        return (value is _missing, None if value is _missing else value)
                    rows.sort(key=sort_value, reverse=direction < 0)
            else:
                raise AssertionError("Unsupported aggregate stage: " + next(iter(stage)))
        return Cursor(rows)


@pytest.fixture
def finance_db(monkeypatch):
    order_id = ObjectId("64b000000000000000000011")
    order = {
        "_id": order_id,
        "business_id": "business-finance-1",
        "status": "completed",
        "source_channel": "pos",
        "currency": "KES",
        "total_amount": 123.45,
        "total_amount_minor": 12345,
        "items": [{
            "product_id": "64b000000000000000000021",
            "name": "Test item",
            "sku": "T-01",
            "quantity": 1,
            "unit_price": 123.45,
            "unit_price_minor": 12345,
            "line_total_minor": 12345,
        }],
    }
    data = {
        "jumuiya_invoices": Collection(),
        "jumuiya_payments": Collection(),
        "jumuiya_finance_counters": Collection(),
        "jumuiya_journal_entries": Collection(),
        "jumuiya_expenses": Collection(),
        "jumuiya_orders": Collection([order]),
        "jumuiya_customers": Collection(),
    }
    monkeypatch.setattr(finance, "collection", lambda name: data[name])
    monkeypatch.setattr(finance, "require_permission", lambda user_id, permission, business_id=None: {"id": business_id or "business-finance-1"})
    monkeypatch.setattr(ledger, "collection", lambda name: data[name])
    monkeypatch.setattr(ledger, "dispatch_manifest_for_record", lambda *args, **kwargs: {"enqueued": 1, "pending": 0, "errors": 0})
    monkeypatch.setattr(biashara, "collection", lambda name: data[name])
    monkeypatch.setattr(biashara, "_dispatch_outbox_source", lambda *args, **kwargs: {"enqueued": 1, "pending": 0, "errors": 0})
    monkeypatch.setattr(biashara, "require_permission", lambda user_id, permission, business_id=None: {"id": business_id or "business-finance-1"})
    monkeypatch.setattr(biashara, "_require_business", lambda user_id: {
        "id": "business-finance-1", "currency": "KES", "name": "Test Business"
    })
    monkeypatch.setattr(finance, "_dispatch", lambda *args, **kwargs: {"enqueued": 1, "pending": 0, "errors": 0})
    monkeypatch.setattr(finance, "log_action", lambda *args, **kwargs: None)
    return {"data": data, "order_id": order_id}


def _draft_invoice(db, idempotency_key="invoice-create-0001"):
    return finance.create_invoice(
        "owner-1",
        {"order_id": str(db["order_id"]), "due_date": "2026-11-01", "notes": "Demo invoice"},
        idempotency_key=idempotency_key,
    )


def test_invoice_creation_is_idempotent_and_snapshots_canonical_order(finance_db):
    first = _draft_invoice(finance_db)
    second = _draft_invoice(finance_db)

    assert first["id"] == second["id"]
    assert first["status"] == "draft"
    assert first["invoice_number"] is None
    assert first["total_amount_minor"] == 12345
    assert first["currency"] == "KES"
    assert first["items"][0]["name"] == "Test item"
    assert first["tax_calculation_status"] == "not_configured"
    assert first["etims"]["status"] == "not_configured"
    assert len(finance_db["data"]["jumuiya_invoices"].documents) == 1


def test_invoice_issue_allocates_number_once_and_tax_state_stays_honest(finance_db):
    draft = _draft_invoice(finance_db)
    first = finance.issue_invoice("owner-1", draft["id"])
    second = finance.issue_invoice("owner-1", draft["id"])

    assert first["status"] == "issued"
    assert first["invoice_number"].startswith("INV-2026-")
    assert second["invoice_number"] == first["invoice_number"]
    assert second["etims"]["status"] == "not_configured"
    assert second["amount_paid_minor"] == 0
    assert len(finance_db["data"]["jumuiya_finance_counters"].documents) == 1
    journal = finance_db["data"]["jumuiya_journal_entries"].documents
    assert len(journal) == 1
    assert journal[0]["source_key"] == "invoice-issued:" + first["id"]
    assert journal[0]["total_debit_minor"] == journal[0]["total_credit_minor"] == 12345
    assert {line["account_code"] for line in journal[0]["lines"]} == {
        "accounts_receivable", "sales_revenue_unclassified"
    }
    assert "tax classification is not configured" in journal[0]["basis"]


def test_cash_payment_allocates_once_and_updates_invoice_balance(finance_db):
    draft = _draft_invoice(finance_db)
    invoice = finance.issue_invoice("owner-1", draft["id"])
    payload = {"amount": "23.45", "payment_method": "cash", "reference": "cash-receipt-1"}

    first = finance.record_payment("owner-1", invoice["id"], payload, "cash-payment-0001")
    second = finance.record_payment("owner-1", invoice["id"], payload, "cash-payment-0001")
    refreshed = finance.get_invoice("owner-1", invoice["id"])

    assert first["id"] == second["id"]
    assert first["payment_status"] == "manual_attested"
    assert first["verification_status"] == "manual_attested"
    assert first["provider_verified"] is False
    assert first["allocation_status"] == "allocated"
    assert refreshed["amount_paid_minor"] == 2345
    assert refreshed["payment_status"] == "partially_paid"
    assert len(finance_db["data"]["jumuiya_payments"].documents) == 1
    journal = finance_db["data"]["jumuiya_journal_entries"].documents
    assert len(journal) == 2
    payment_entry = next(entry for entry in journal if entry["source_type"] == "payment.cash_allocated")
    assert payment_entry["total_debit_minor"] == payment_entry["total_credit_minor"] == 2345
    assert payment_entry["lines"][0]["account_code"] == "cash_on_hand"
    assert payment_entry["lines"][1]["account_code"] == "accounts_receivable"


def test_manual_mpesa_reference_is_not_provider_verified_or_allocated(finance_db):
    draft = _draft_invoice(finance_db)
    invoice = finance.issue_invoice("owner-1", draft["id"])
    payment = finance.record_payment(
        "owner-1",
        invoice["id"],
        {"amount": "123.45", "payment_method": "mpesa", "reference": "manual-confirmation-code"},
        "mpesa-payment-0001",
    )
    refreshed = finance.get_invoice("owner-1", invoice["id"])

    assert payment["payment_status"] == "verification_required"
    assert payment["verification_status"] == "unverified_manual"
    assert payment["provider_verified"] is False
    assert payment["allocation_status"] == "not_allocated_pending_verification"
    assert refreshed["amount_paid_minor"] == 0
    assert refreshed["payment_status"] == "unpaid"
    assert len(finance_db["data"]["jumuiya_journal_entries"].documents) == 1
    assert finance_db["data"]["jumuiya_journal_entries"].documents[0]["source_type"] == "invoice.issued"


def test_overpayment_is_retained_as_conflict_without_corrupting_invoice_balance(finance_db):
    draft = _draft_invoice(finance_db)
    invoice = finance.issue_invoice("owner-1", draft["id"])
    payment = finance.record_payment(
        "owner-1",
        invoice["id"],
        {"amount": "130.00", "payment_method": "cash", "reference": "cash-too-large"},
        "cash-payment-0002",
    )
    refreshed = finance.get_invoice("owner-1", invoice["id"])

    assert payment["allocation_status"] == "allocation_conflict"
    assert refreshed["amount_paid_minor"] == 0
    assert refreshed["payment_status"] == "unpaid"
    assert len(refreshed["payments"]) == 1


def test_idempotency_key_reuse_with_different_payment_is_rejected(finance_db):
    draft = _draft_invoice(finance_db)
    invoice = finance.issue_invoice("owner-1", draft["id"])
    finance.record_payment(
        "owner-1", invoice["id"],
        {"amount": "10.00", "payment_method": "cash", "reference": "receipt-a"},
        "cash-payment-0003",
    )
    with pytest.raises(APIError) as raised:
        finance.record_payment(
            "owner-1", invoice["id"],
            {"amount": "11.00", "payment_method": "cash", "reference": "receipt-a"},
            "cash-payment-0003",
        )
    assert raised.value.code == "idempotency_key_reused"


def test_invoice_cannot_be_issued_after_void_or_voided_with_allocated_payment(finance_db):
    draft = _draft_invoice(finance_db)
    issued = finance.issue_invoice("owner-1", draft["id"])
    finance.record_payment(
        "owner-1", issued["id"],
        {"amount": "5.00", "payment_method": "cash", "reference": "r1"},
        "cash-payment-0004",
    )
    with pytest.raises(APIError) as raised:
        finance.void_invoice("owner-1", issued["id"], "mistake")
    assert raised.value.code == "invoice_has_allocated_payments"

def test_invoice_lookup_is_scoped_to_current_business(finance_db, monkeypatch):
    draft = _draft_invoice(finance_db)
    monkeypatch.setattr(biashara, "_require_business", lambda user_id: {
        "id": "different-business", "currency": "KES"
    })
    with pytest.raises(APIError) as raised:
        finance.get_invoice("other-owner", draft["id"])
    assert raised.value.code == "invoice_not_found"


def test_invoice_cannot_be_voided_while_external_payment_evidence_is_unverified(finance_db):
    draft = _draft_invoice(finance_db)
    invoice = finance.issue_invoice("owner-1", draft["id"])
    finance.record_payment(
        "owner-1", invoice["id"],
        {"amount": "25.00", "payment_method": "mpesa", "reference": "unverified-reference"},
        "mpesa-payment-0002",
    )
    with pytest.raises(APIError) as raised:
        finance.void_invoice("owner-1", invoice["id"], "mistake")
    assert raised.value.code == "invoice_has_unresolved_payment"

def test_manual_payment_replay_repairs_missing_cash_journal(finance_db):
    draft = _draft_invoice(finance_db)
    invoice = finance.issue_invoice("owner-1", draft["id"])
    payment = finance.record_payment(
        "owner-1", invoice["id"],
        {"amount": "20.00", "payment_method": "cash", "reference": "receipt-repair"},
        "cash-payment-repair-0001",
    )
    entries = finance_db["data"]["jumuiya_journal_entries"]
    assert payment["allocation_status"] == "allocated"
    payment_entries = [row for row in entries.documents if row["source_type"] == "payment.cash_allocated"]
    assert len(payment_entries) == 1

    # Simulate a crash after allocation saved but before the journal insert.
    entries.documents = [row for row in entries.documents if row["source_type"] != "payment.cash_allocated"]
    finance.record_payment(
        "owner-1", invoice["id"],
        {"amount": "20.00", "payment_method": "cash", "reference": "receipt-repair"},
        "cash-payment-repair-0001",
    )
    assert len([row for row in entries.documents if row["source_type"] == "payment.cash_allocated"]) == 1


def test_journal_rejects_unbalanced_entries_and_reuses_source_key_safely(finance_db):
    with pytest.raises(APIError) as unbalanced:
        ledger.post_journal_entry(
            business_id="business-finance-1",
            source_key="manual-test-entry-0001",
            source_type="manual.test",
            source_id="example-1",
            currency="KES",
            lines=[
                {"account_code": "cash_on_hand", "debit_minor": 1000, "credit_minor": 0},
                {"account_code": "accounts_receivable", "debit_minor": 0, "credit_minor": 999},
            ],
            actor_user_id="owner-1",
            basis="unit-test",
        )
    assert unbalanced.value.code == "unbalanced_journal_entry"
    assert len(finance_db["data"]["jumuiya_journal_entries"].documents) == 0

    payload = dict(
        business_id="business-finance-1",
        source_key="manual-test-entry-0002",
        source_type="manual.test",
        source_id="example-2",
        currency="KES",
        lines=[
            {"account_code": "cash_on_hand", "debit_minor": 1000, "credit_minor": 0},
            {"account_code": "accounts_receivable", "debit_minor": 0, "credit_minor": 1000},
        ],
        actor_user_id="owner-1",
        basis="unit-test",
    )
    first = ledger.post_journal_entry(**payload)
    second = ledger.post_journal_entry(**payload)
    assert first["id"] == second["id"]
    assert len(finance_db["data"]["jumuiya_journal_entries"].documents) == 1

    with pytest.raises(APIError) as conflict:
        ledger.post_journal_entry(**{
            **payload,
            "lines": [
                {"account_code": "cash_on_hand", "debit_minor": 1500, "credit_minor": 0},
                {"account_code": "accounts_receivable", "debit_minor": 0, "credit_minor": 1500},
            ],
        })
    assert conflict.value.code == "journal_source_conflict"
    assert len(finance_db["data"]["jumuiya_journal_entries"].documents) == 1


def test_journal_queries_are_scoped_to_the_active_business(finance_db, monkeypatch):
    draft = _draft_invoice(finance_db)
    invoice = finance.issue_invoice("owner-1", draft["id"])
    rows = finance.get_journal_entries("owner-1")
    assert len(rows) == 1
    assert rows[0]["source_id"] == invoice["id"]

    monkeypatch.setattr(biashara, "_require_business", lambda user_id: {"id": "other-business", "currency": "KES"})
    assert finance.get_journal_entries("other-owner") == []

def test_ledger_summary_returns_balanced_minor_unit_totals(finance_db):
    draft = _draft_invoice(finance_db)
    invoice = finance.issue_invoice("owner-1", draft["id"])
    finance.record_payment(
        "owner-1", invoice["id"],
        {"amount": "23.45", "payment_method": "cash", "reference": "summary-receipt"},
        "cash-payment-summary-0001",
    )

    summary = finance.get_ledger_summary("owner-1", currency="KES")
    totals = summary["totals_by_currency"]["KES"]
    assert totals["is_balanced"] is True
    assert totals["debit_minor"] == totals["credit_minor"] == 14690
    accounts = {row["account_code"]: row for row in summary["accounts"]}
    assert accounts["accounts_receivable"]["normal_balance_minor"] == 10000
    assert accounts["cash_on_hand"]["normal_balance_minor"] == 2345
    assert accounts["sales_revenue_unclassified"]["normal_balance_minor"] == 12345
    assert summary["tax_status"] == "not_configured"
    assert summary["etims_status"] == "not_configured"

def test_expense_creates_balanced_provisional_journal_and_replays_idempotently(finance_db):
    payload = {
        "title": "Shop rent",
        "category": "rent",
        "amount": "15.50",
        "currency": "KES",
        "notes": "October rent",
        "idempotency_key": "expense-record-0001",
    }
    first = biashara.create_expense("owner-1", payload)
    second = biashara.create_expense("owner-1", payload)

    assert first["id"] == second["id"]
    assert first["amount_minor"] == 1550
    assert first["accounting_status"] == "provisional_unclassified"
    assert first["tax_status"] == "not_configured"
    assert len(finance_db["data"]["jumuiya_expenses"].documents) == 1

    entries = finance_db["data"]["jumuiya_journal_entries"].documents
    assert len(entries) == 1
    entry = entries[0]
    assert entry["source_type"] == "expense.recorded"
    assert entry["total_debit_minor"] == entry["total_credit_minor"] == 1550
    assert entry["lines"][0]["account_code"] == "operating_expense"
    assert entry["lines"][1]["account_code"] == "expense_settlement_unclassified"
    assert "funding source was not supplied" in entry["basis"]


def test_expense_idempotency_key_cannot_be_reused_for_different_amount(finance_db):
    biashara.create_expense("owner-1", {
        "title": "Packaging",
        "category": "supplies",
        "amount": "10.00",
        "currency": "KES",
        "idempotency_key": "expense-record-0002",
    })
    with pytest.raises(APIError) as raised:
        biashara.create_expense("owner-1", {
            "title": "Packaging",
            "category": "supplies",
            "amount": "11.00",
            "currency": "KES",
            "idempotency_key": "expense-record-0002",
        })
    assert raised.value.code == "idempotency_key_reused"
    assert len(finance_db["data"]["jumuiya_expenses"].documents) == 1
    assert len(finance_db["data"]["jumuiya_journal_entries"].documents) == 1

def test_allocation_retry_recovers_when_invoice_write_preceded_payment_write(finance_db):
    draft = _draft_invoice(finance_db)
    invoice = finance.issue_invoice("owner-1", draft["id"])
    payment = finance.record_payment(
        "owner-1", invoice["id"],
        {"amount": "20.00", "payment_method": "cash", "reference": "write-order-recovery"},
        "cash-payment-write-order-0001",
    )
    assert payment["allocation_status"] == "allocated"

    # Simulate a crash after the invoice's allocation key was persisted, but
    # before the payment row was marked allocated/journal insertion completed.
    payments = finance_db["data"]["jumuiya_payments"]
    stored_payment = payments.find_one({"idempotency_key": "cash-payment-write-order-0001"})
    payments.update_one(
        {"_id": stored_payment["_id"]},
        {"$set": {"allocation_status": "pending"}},
    )
    journals = finance_db["data"]["jumuiya_journal_entries"]
    journals.documents = [
        row for row in journals.documents if row["source_id"] != payment["id"]
    ]

    recovered = finance.record_payment(
        "owner-1", invoice["id"],
        {"amount": "20.00", "payment_method": "cash", "reference": "write-order-recovery"},
        "cash-payment-write-order-0001",
    )
    assert recovered["allocation_status"] == "allocated"
    assert len([
        row for row in journals.documents
        if row["source_id"] == payment["id"] and row["source_type"] == "payment.cash_allocated"
    ]) == 1
    refreshed_invoice = finance_db["data"]["jumuiya_invoices"].find_one({"_id": ObjectId(invoice["id"])})
    assert refreshed_invoice["amount_paid_minor"] == 2000


def test_verified_mpesa_allocation_conflict_posts_provider_clearing_to_suspense(finance_db):
    payment = {
        "_id": ObjectId("64b000000000000000000501"),
        "business_id": "business-finance-1",
        "invoice_id": "invoice-already-paid",
        "idempotency_key": "mpesa-stk:provider-conflict-0001",
        "amount_minor": 3500,
        "currency": "KES",
        "payment_status": "provider_confirmed",
        "verification_status": "provider_verified",
        "provider_verified": True,
        "provider_name": "mpesa_daraja",
        "allocation_status": "allocation_conflict",
        "recorded_by_user_id": "owner-1",
        "provider_verified_at": datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc),
    }

    entry = finance._post_provider_payment_journal(payment, "owner-1")

    assert entry["source_type"] == "payment.mpesa_unallocated"
    assert entry["total_debit_minor"] == entry["total_credit_minor"] == 3500
    assert entry["lines"][0]["account_code"] == "mpesa_clearing"
    assert entry["lines"][1]["account_code"] == "unallocated_customer_receipts"

