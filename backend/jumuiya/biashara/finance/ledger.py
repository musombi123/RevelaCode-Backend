"""Immutable double-entry journal primitives for Biashara.

This is an operational ledger foundation, not a certified accounting product.
Until tax setup is configured, invoice revenue is deliberately posted to an
unclassified revenue account and journal entries carry an explicit basis note.
No tax, eTIMS acceptance or settlement state is inferred by this module.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.biashara.sync.outbox import build_outbox_manifest, dispatch_manifest_for_record


JOURNAL_COLLECTION = "jumuiya_journal_entries"

CHART_OF_ACCOUNTS = {
    "accounts_receivable": {"name": "Accounts receivable", "type": "asset"},
    "cash_on_hand": {"name": "Cash on hand", "type": "asset"},
    "sales_revenue_unclassified": {"name": "Commercial revenue (tax classification pending)", "type": "income"},
    "operating_expense": {"name": "Operating expense", "type": "expense"},
    "expense_settlement_unclassified": {"name": "Expense funding or payable (classification pending)", "type": "liability"},
}

LEDGER_BASIS_WARNING = (
    "Operational ledger only. Tax classification is not configured; these entries "
    "do not establish eTIMS submission, tax compliance or bank/provider settlement."
)


def now_utc():
    return datetime.now(timezone.utc)


def _clean_id(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return value


def _serialize(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {
            ("id" if key == "_id" else key): _serialize(item)
            for key, item in value.items()
            if key not in {"request_fingerprint", "outbox_event_manifest", "outbox_enqueued_event_keys"}
        }
    return value


def _normalise_lines(lines):
    if not isinstance(lines, list) or len(lines) < 2:
        raise APIError("A journal entry must contain at least two lines.", 422, "invalid_journal_lines")

    normalised = []
    debit_total = 0
    credit_total = 0
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise APIError(f"Journal line {index + 1} must be an object.", 422, "invalid_journal_lines")
        account_code = str(line.get("account_code") or "").strip()
        account = CHART_OF_ACCOUNTS.get(account_code)
        if not account:
            raise APIError(f"Account {account_code or '(blank)'} is not enabled in the Biashara operational chart.", 422, "invalid_journal_account")
        try:
            debit = int(line.get("debit_minor", 0) or 0)
            credit = int(line.get("credit_minor", 0) or 0)
        except (TypeError, ValueError, OverflowError):
            raise APIError("Journal line amounts must be integer minor units.", 422, "invalid_journal_amount")
        if debit < 0 or credit < 0 or (debit and credit) or not (debit or credit):
            raise APIError("Each journal line must have a positive debit or credit, not both.", 422, "invalid_journal_amount")
        debit_total += debit
        credit_total += credit
        normalised.append({
            "line_number": index + 1,
            "account_code": account_code,
            "account_name": account["name"],
            "account_type": account["type"],
            "debit_minor": debit,
            "credit_minor": credit,
            "memo": str(line.get("memo") or "")[:300],
        })

    if debit_total != credit_total:
        raise APIError("Journal debits must equal credits.", 422, "unbalanced_journal_entry")
    if debit_total <= 0:
        raise APIError("A journal entry must post a non-zero amount.", 422, "empty_journal_entry")
    return normalised, debit_total, credit_total


def _fingerprint(entry):
    stable = {
        "business_id": entry["business_id"],
        "source_key": entry["source_key"],
        "source_type": entry["source_type"],
        "source_id": entry["source_id"],
        "currency": entry["currency"],
        # Use the requested effective time only when the caller explicitly
        # supplied one. A generated current-time default must not break retries.
        "requested_effective_at": entry.get("idempotency_effective_at"),
        "basis": entry["basis"],
        "lines": entry["lines"],
    }
    raw = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def post_journal_entry(
    business_id,
    source_key,
    source_type,
    source_id,
    currency,
    lines,
    actor_user_id,
    basis,
    effective_at=None,
):
    """Persist a balanced, immutable journal entry exactly once per source key."""
    business_id = str(business_id or "").strip()
    source_key = str(source_key or "").strip()
    source_type = str(source_type or "").strip().lower()
    source_id = str(source_id or "").strip()
    currency = str(currency or "").strip().upper()
    basis = str(basis or "").strip()[:500]
    if not business_id:
        raise APIError("Business ID is required.", 422, "journal_business_required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,180}", source_key):
        raise APIError("Journal source key must be 8–181 safe characters.", 422, "invalid_journal_source_key")
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,79}", source_type):
        raise APIError("Journal source type is invalid.", 422, "invalid_journal_source")
    if not source_id or len(source_id) > 200:
        raise APIError("Journal source ID is invalid.", 422, "invalid_journal_source")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise APIError("Journal currency must be a 3-letter ISO currency code.", 422, "invalid_journal_currency")
    if not basis:
        raise APIError("Journal basis is required.", 422, "journal_basis_required")

    normalised_lines, debit_total, credit_total = _normalise_lines(lines)
    when = effective_at or now_utc()
    if isinstance(when, str):
        try:
            when = datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            raise APIError("Journal effective time is invalid.", 422, "invalid_journal_date")
    if not isinstance(when, datetime):
        raise APIError("Journal effective time is invalid.", 422, "invalid_journal_date")
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    else:
        when = when.astimezone(timezone.utc)

    document = {
        "_id": ObjectId(),
        "business_id": business_id,
        "source_key": source_key,
        "source_type": source_type,
        "source_id": source_id,
        "currency": currency,
        "status": "posted",
        "lines": normalised_lines,
        "total_debit_minor": debit_total,
        "total_credit_minor": credit_total,
        "basis": basis,
        "posted_by_user_id": str(actor_user_id)[:128] if actor_user_id is not None else None,
        "effective_at": when,
        "created_at": now_utc(),
        "immutable": True,
    }
    document["idempotency_effective_at"] = when.isoformat() if effective_at is not None else None
    document["request_fingerprint"] = _fingerprint(document)
    document.pop("idempotency_effective_at", None)
    event = build_outbox_manifest(
        event_key="journal:" + source_key,
        event_type="ledger.entry_posted",
        entity_type="journal_entry",
        entity_id=document["_id"],
        payload={
            "status": "posted",
            "amount_minor": debit_total,
            "currency": currency,
        },
        actor_user_id=actor_user_id,
        occurred_at=when,
    )
    document["outbox_event_manifest"] = [event]
    document["outbox_enqueued_event_keys"] = []

    entries = collection(JOURNAL_COLLECTION)
    prior = entries.find_one({"business_id": business_id, "source_key": source_key})
    if prior:
        if prior.get("request_fingerprint") != document["request_fingerprint"]:
            raise APIError("This journal source key is already used by different accounting data.", 409, "journal_source_conflict")
        _dispatch_entry(prior)
        return _serialize(prior)

    try:
        entries.insert_one(document)
    except DuplicateKeyError:
        prior = entries.find_one({"business_id": business_id, "source_key": source_key})
        if prior and prior.get("request_fingerprint") == document["request_fingerprint"]:
            _dispatch_entry(prior)
            return _serialize(prior)
        if prior:
            raise APIError("This journal source key is already used by different accounting data.", 409, "journal_source_conflict")
        raise

    _dispatch_entry(document)
    return _serialize(document)


def _dispatch_entry(entry):
    try:
        dispatch_manifest_for_record(
            JOURNAL_COLLECTION,
            str(entry.get("business_id") or ""),
            entry.get("_id"),
        )
    except Exception:
        # Journal commit is authoritative; outbox recovery can dispatch later.
        return False
    return True


def list_journal_entries(business_id, limit=50, source_type=None, from_date=None, to_date=None):
    """Return a bounded, tenant-scoped journal list."""
    business_id = str(business_id or "").strip()
    try:
        limit = min(max(int(limit), 1), 100)
    except (TypeError, ValueError):
        limit = 50
    query = {"business_id": business_id}
    if source_type:
        source_type = str(source_type).strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,79}", source_type):
            raise APIError("Journal source filter is invalid.", 422, "invalid_journal_source")
        query["source_type"] = source_type
    if from_date:
        try:
            date_value = date.fromisoformat(str(from_date))
        except ValueError:
            raise APIError("from_date must use YYYY-MM-DD.", 422, "invalid_journal_date")
        query.setdefault("effective_at", {})["$gte"] = datetime.combine(date_value, time.min, timezone.utc)
    if to_date:
        try:
            date_value = date.fromisoformat(str(to_date))
        except ValueError:
            raise APIError("to_date must use YYYY-MM-DD.", 422, "invalid_journal_date")
        query.setdefault("effective_at", {})["$lt"] = datetime.combine(date_value + timedelta(days=1), time.min, timezone.utc)
    docs = collection(JOURNAL_COLLECTION).find(query).sort("effective_at", -1).limit(limit)
    return [_serialize(item) for item in docs]


def ledger_summary(business_id, currency=None, from_date=None, to_date=None):
    """Return account balances based only on posted immutable journal lines."""
    business_id = str(business_id or "").strip()
    query = {"business_id": business_id, "status": "posted"}
    if currency:
        normalized_currency = str(currency).strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized_currency):
            raise APIError("currency must be a 3-letter ISO currency code.", 422, "invalid_journal_currency")
        query["currency"] = normalized_currency
    if from_date:
        try:
            value = date.fromisoformat(str(from_date))
        except ValueError:
            raise APIError("from_date must use YYYY-MM-DD.", 422, "invalid_journal_date")
        query.setdefault("effective_at", {})["$gte"] = datetime.combine(value, time.min, timezone.utc)
    if to_date:
        try:
            value = date.fromisoformat(str(to_date))
        except ValueError:
            raise APIError("to_date must use YYYY-MM-DD.", 422, "invalid_journal_date")
        query.setdefault("effective_at", {})["$lt"] = datetime.combine(value + timedelta(days=1), time.min, timezone.utc)

    pipeline = [
        {"$match": query},
        {"$unwind": "$lines"},
        {"$group": {
            "_id": {"currency": "$currency", "account_code": "$lines.account_code",
                    "account_name": "$lines.account_name", "account_type": "$lines.account_type"},
            "debit_minor": {"$sum": "$lines.debit_minor"},
            "credit_minor": {"$sum": "$lines.credit_minor"},
            "line_count": {"$sum": 1},
        }},
        {"$sort": {"_id.currency": 1, "_id.account_code": 1}},
    ]
    rows = list(collection(JOURNAL_COLLECTION).aggregate(pipeline))
    accounts = []
    totals = {}
    for row in rows:
        key = row.get("_id") or {}
        currency_code = key.get("currency", "KES")
        debit = int(row.get("debit_minor", 0) or 0)
        credit = int(row.get("credit_minor", 0) or 0)
        account_type = key.get("account_type", "unknown")
        # Debit-normal balances for assets/expenses; credit-normal for liabilities,
        # equity and income. Negative values remain visible rather than concealed.
        balance = debit - credit if account_type in {"asset", "expense"} else credit - debit
        accounts.append({
            "currency": currency_code,
            "account_code": key.get("account_code"),
            "account_name": key.get("account_name"),
            "account_type": account_type,
            "debit_minor": debit,
            "credit_minor": credit,
            "normal_balance_minor": balance,
            "line_count": int(row.get("line_count", 0) or 0),
        })
        totals.setdefault(currency_code, {"debit_minor": 0, "credit_minor": 0, "is_balanced": True})
        totals[currency_code]["debit_minor"] += debit
        totals[currency_code]["credit_minor"] += credit
        totals[currency_code]["is_balanced"] = (
            totals[currency_code]["debit_minor"] == totals[currency_code]["credit_minor"]
        )
    return {
        "accounts": accounts,
        "totals_by_currency": totals,
        "chart_of_accounts": CHART_OF_ACCOUNTS,
        "basis_warning": LEDGER_BASIS_WARNING,
        "posting_model": "immutable_double_entry_minor_units",
        "tax_status": "not_configured",
        "etims_status": "not_configured",
    }
