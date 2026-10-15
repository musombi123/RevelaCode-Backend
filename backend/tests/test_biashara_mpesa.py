import json
import sys
import types
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import requests
from bson import ObjectId

_missing_module = object()
_original_db_module = sys.modules.get("backend.db", _missing_module)
_test_db_module = types.ModuleType("backend.db")
_test_db_module.get_db = lambda: None
sys.modules["backend.db"] = _test_db_module
try:
    from backend.jumuiya.biashara.finance import mpesa
    from backend.jumuiya.biashara.finance import services as finance_services
    from backend.jumuiya.biashara.finance import ledger
    from backend.jumuiya.biashara.integrations import service as integration_service
finally:
    if _original_db_module is _missing_module:
        sys.modules.pop("backend.db", None)
    else:
        sys.modules["backend.db"] = _original_db_module

from backend.jumuiya.core.errors import APIError


_missing = object()
BUSINESS_ID = "business-1"
CONNECTION_ID = ObjectId("64b000000000000000000301")
INVOICE_ID = ObjectId("64b000000000000000000302")


def _get(document, path):
    value = document
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part, _missing)
        else:
            return _missing
    return value


def _matches(document, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(document, item) for item in expected):
                return False
            continue
        actual = _get(document, key)
        if isinstance(expected, dict) and any(name.startswith("$") for name in expected):
            for operator, value in expected.items():
                if operator == "$exists":
                    if (actual is not _missing) != bool(value):
                        return False
                elif operator == "$in":
                    if actual is _missing:
                        if None not in value:
                            return False
                    elif isinstance(actual, list):
                        if not any(item in value for item in actual):
                            return False
                    elif actual not in value:
                        return False
                elif operator == "$ne":
                    if actual is not _missing and (
                        actual == value or isinstance(actual, list) and value in actual
                    ):
                        return False
                elif operator == "$type":
                    if value == "string" and not isinstance(actual, str):
                        return False
                else:
                    raise AssertionError("Unsupported fake Mongo operator: " + operator)
        elif actual is _missing or actual != expected:
            return False
    return True


def _set(document, path, value):
    parts = path.split(".")
    target = document
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = deepcopy(value)


class Cursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, field, direction=1):
        self.documents.sort(key=lambda item: item.get(field) or datetime.min.replace(tzinfo=timezone.utc), reverse=direction < 0)
        return self

    def limit(self, amount):
        self.documents = self.documents[:amount]
        return self

    def __iter__(self):
        return iter(deepcopy(self.documents))


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = [deepcopy(item) for item in (documents or [])]

    def find_one(self, query):
        for item in self.documents:
            if _matches(item, query):
                return deepcopy(item)
        return None

    def find(self, query=None, projection=None):
        query = query or {}
        return Cursor([item for item in self.documents if _matches(item, query)])

    def insert_one(self, document):
        saved = deepcopy(document)
        saved["_id"] = saved.get("_id") or ObjectId()
        if saved.get("business_id") and saved.get("idempotency_key"):
            if self.find_one({"business_id": saved["business_id"], "idempotency_key": saved["idempotency_key"]}):
                from pymongo.errors import DuplicateKeyError
                raise DuplicateKeyError("duplicate payment idempotency key")
        if saved.get("business_id") and saved.get("source_key"):
            if self.find_one({"business_id": saved["business_id"], "source_key": saved["source_key"]}):
                from pymongo.errors import DuplicateKeyError
                raise DuplicateKeyError("duplicate journal source key")
        if saved.get("business_id") and saved.get("checkout_request_id") and saved.get("connection_id"):
            if self.find_one({
                "business_id": saved["business_id"],
                "connection_id": saved["connection_id"],
                "checkout_request_id": saved["checkout_request_id"],
            }):
                from pymongo.errors import DuplicateKeyError
                raise DuplicateKeyError("duplicate callback checkout")
        self.documents.append(saved)
        return SimpleNamespace(inserted_id=saved["_id"])

    def update_one(self, query, update):
        for item in self.documents:
            if _matches(item, query):
                self._apply(item, update)
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    def find_one_and_update(self, query, update, return_document=None):
        for item in self.documents:
            if _matches(item, query):
                self._apply(item, update)
                return deepcopy(item)
        return None

    def _apply(self, item, update):
        for key, value in update.get("$set", {}).items():
            _set(item, key, value)
        for key, value in update.get("$inc", {}).items():
            item[key] = item.get(key, 0) + value
        for key, value in update.get("$addToSet", {}).items():
            target = item.setdefault(key, [])
            if value not in target:
                target.append(deepcopy(value))
        for key, value in update.get("$unset", {}).items():
            item.pop(key, None)


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return deepcopy(self._body)


def _stk_callback(amount="25.00", receipt="AB123CD456", result_code=0):
    metadata = []
    if amount is not None:
        metadata.append({"Name": "Amount", "Value": amount})
    if receipt is not None:
        metadata.append({"Name": "MpesaReceiptNumber", "Value": receipt})
    metadata.append({"Name": "TransactionDate", "Value": "20261015140000"})
    metadata.append({"Name": "PhoneNumber", "Value": 254712345678})
    return json.dumps({
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "merchant-request-001",
                "CheckoutRequestID": "ws_CO_001",
                "ResultCode": result_code,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {"Item": metadata} if result_code == 0 else {},
            }
        }
    }, separators=(",", ":")).encode("utf-8")


@pytest.fixture
def mpesa_db(monkeypatch):
    connection = {
        "_id": CONNECTION_ID,
        "business_id": BUSINESS_ID,
        "provider": "mpesa_daraja",
        "enabled": True,
        "name": "Daraja sandbox",
        "metadata": {
            "shortcode": "600123",
            "environment": "sandbox",
            "transaction_type": "CustomerPayBillOnline",
        },
        "credentials_ciphertext": "encrypted-config-only",
        "credential_key_id": "test",
    }
    invoice = {
        "_id": INVOICE_ID,
        "business_id": BUSINESS_ID,
        "status": "issued",
        "invoice_number": "INV-2026-0001",
        "currency": "KES",
        "total_amount_minor": 2500,
        "amount_paid_minor": 0,
        "payment_status": "unpaid",
        "payment_allocation_keys": [],
        "source_order_id": "order-1",
        "updated_at": datetime(2026, 10, 15, tzinfo=timezone.utc),
    }
    data = {
        mpesa.PAYMENTS_COLLECTION: FakeCollection(),
        mpesa.INVOICES_COLLECTION: FakeCollection([invoice]),
        mpesa.CONNECTIONS_COLLECTION: FakeCollection([connection]),
        mpesa.CALLBACKS_COLLECTION: FakeCollection(),
        ledger.JOURNAL_COLLECTION: FakeCollection(),
    }
    collection = lambda name: data[name]
    monkeypatch.setattr(mpesa, "collection", collection)
    monkeypatch.setattr(finance_services, "collection", collection)
    monkeypatch.setattr(integration_service, "collection", collection)
    monkeypatch.setattr(ledger, "collection", collection)
    monkeypatch.setattr(mpesa, "require_permission", lambda user_id, permission, business_id=None: {
        "id": business_id or BUSINESS_ID, "permissions": ["*"]
    })
    monkeypatch.setattr(integration_service, "_decrypt_credentials", lambda _document: {
        "consumer_key": "consumer-key-test",
        "consumer_secret": "consumer-secret-test",
        "passkey": "passkey-test",
    })
    monkeypatch.setattr(mpesa, "dispatch_manifest_for_record", lambda *args, **kwargs: {
        "enqueued": 1, "pending": 0, "errors": 0
    })
    monkeypatch.setattr(finance_services, "_dispatch", lambda *args, **kwargs: None)
    monkeypatch.setattr(ledger, "dispatch_manifest_for_record", lambda *args, **kwargs: {
        "enqueued": 1, "pending": 0, "errors": 0
    })
    monkeypatch.setattr(mpesa, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setenv("BIASHARA_MPESA_CALLBACK_BASE_URL", "https://api.example.test")
    monkeypatch.setenv("BIASHARA_MPESA_CALLBACK_ALLOWED_IPS", "196.201.214.200,196.201.214.206")
    return {"data": data, "connection": connection, "invoice": invoice}


def _payment_payload(amount="25.00"):
    return {
        "connection_id": str(CONNECTION_ID),
        "phone_number": "0712345678",
        "amount": amount,
    }


def _ok_requests(monkeypatch, on_post=None):
    calls = {"get": [], "post": []}

    def get(url, **kwargs):
        calls["get"].append((url, kwargs))
        return FakeResponse(200, {"access_token": "mock-only-access-token", "expires_in": "3599"})

    def post(url, **kwargs):
        calls["post"].append((url, kwargs))
        if on_post:
            on_post()
        return FakeResponse(200, {
            "ResponseCode": "0",
            "MerchantRequestID": "merchant-request-001",
            "CheckoutRequestID": "ws_CO_001",
            "CustomerMessage": "Check your phone",
        })

    monkeypatch.setattr(mpesa.requests, "get", get)
    monkeypatch.setattr(mpesa.requests, "post", post)
    return calls


def test_stk_push_saves_one_idempotent_request_and_allocates_only_correlated_verified_callback(mpesa_db, monkeypatch):
    calls = {}

    def early_callback():
        # This simulates Daraja's callback arriving before the outbound response
        # writes CheckoutRequestID to the payment intent.
        received = mpesa.receive_stk_callback(
            str(CONNECTION_ID),
            _stk_callback(),
            "196.201.214.200",
        )
        assert received["event_status"] == "pending_match"
        assert received["effects_applied"] is False

    calls = _ok_requests(monkeypatch, on_post=early_callback)
    first = mpesa.start_stk_push("owner-1", str(INVOICE_ID), _payment_payload(), "stk-payment-request-0001")
    replay = mpesa.start_stk_push("owner-1", str(INVOICE_ID), _payment_payload(), "stk-payment-request-0001")

    assert len(calls["get"]) == 1
    assert len(calls["post"]) == 1
    assert calls["get"][0][0] == "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    posted = calls["post"][0][1]["json"]
    assert calls["post"][0][0] == "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    assert posted["BusinessShortCode"] == "600123"
    assert posted["Amount"] == 25
    assert posted["PartyA"] == "254712345678"
    assert posted["PartyB"] == "600123"
    assert posted["CallBackURL"] == f"https://api.example.test/api/jumuiya/biashara/finance/mpesa/callback/{CONNECTION_ID}"
    assert "passkey-test" not in json.dumps(posted)
    assert first["id"] == replay["id"]
    assert first["payment_status"] == "provider_confirmed"
    assert first["verification_status"] == "provider_verified"
    assert first["provider_verified"] is True
    assert first["allocation_status"] == "allocated"
    assert first["reference"] == "AB123CD456"

    invoice = mpesa_db["data"][mpesa.INVOICES_COLLECTION].find_one({"_id": INVOICE_ID})
    assert invoice["amount_paid_minor"] == 2500
    assert invoice["payment_status"] == "paid"
    assert len(mpesa_db["data"][mpesa.PAYMENTS_COLLECTION].documents) == 1
    journal = mpesa_db["data"][ledger.JOURNAL_COLLECTION].documents
    assert len(journal) == 1
    assert journal[0]["source_type"] == "payment.mpesa_allocated"
    assert journal[0]["total_debit_minor"] == journal[0]["total_credit_minor"] == 2500
    assert journal[0]["lines"][0]["account_code"] == "mpesa_clearing"
    assert journal[0]["lines"][1]["account_code"] == "accounts_receivable"

    duplicate = mpesa.receive_stk_callback(
        str(CONNECTION_ID),
        _stk_callback(),
        "196.201.214.200",
    )
    assert duplicate["duplicate"] is True
    assert duplicate["effects_applied"] is True
    assert len(journal) == 1


def test_callback_source_allowlist_fails_closed_and_does_not_change_invoice(mpesa_db, monkeypatch):
    calls = _ok_requests(monkeypatch)
    payment = mpesa.start_stk_push(
        "owner-1", str(INVOICE_ID), _payment_payload(), "stk-payment-request-0002"
    )

    with pytest.raises(APIError) as raised:
        mpesa.receive_stk_callback(str(CONNECTION_ID), _stk_callback(), "203.0.113.45")
    assert raised.value.code == "mpesa_callback_source_rejected"
    assert payment["payment_status"] == "pending_provider_confirmation"
    invoice = mpesa_db["data"][mpesa.INVOICES_COLLECTION].find_one({"_id": INVOICE_ID})
    assert invoice["amount_paid_minor"] == 0
    assert len(mpesa_db["data"][mpesa.CALLBACKS_COLLECTION].documents) == 0


def test_callback_amount_mismatch_is_quarantined_without_payment_allocation(mpesa_db, monkeypatch):
    _ok_requests(monkeypatch)
    payment = mpesa.start_stk_push(
        "owner-1", str(INVOICE_ID), _payment_payload(), "stk-payment-request-0003"
    )
    result = mpesa.receive_stk_callback(
        str(CONNECTION_ID),
        _stk_callback(amount="24.00", receipt="AB123CD457"),
        "196.201.214.200",
    )

    assert result["event_status"] == "conflict"
    assert result["effects_applied"] is False
    stored = mpesa_db["data"][mpesa.PAYMENTS_COLLECTION].find_one({"_id": ObjectId(payment["id"])})
    assert stored["payment_status"] == "pending_provider_confirmation"
    assert stored["provider_verified"] is False
    invoice = mpesa_db["data"][mpesa.INVOICES_COLLECTION].find_one({"_id": INVOICE_ID})
    assert invoice["amount_paid_minor"] == 0
    assert mpesa_db["data"][ledger.JOURNAL_COLLECTION].documents == []


def test_ambiguous_provider_timeout_is_not_resent_on_idempotent_retry(mpesa_db, monkeypatch):
    calls = {"get": 0, "post": 0}

    def get(url, **kwargs):
        calls["get"] += 1
        return FakeResponse(200, {"access_token": "mock-only-access-token"})

    def post(url, **kwargs):
        calls["post"] += 1
        raise requests.Timeout("synthetic timeout")

    monkeypatch.setattr(mpesa.requests, "get", get)
    monkeypatch.setattr(mpesa.requests, "post", post)

    with pytest.raises(APIError) as first_error:
        mpesa.start_stk_push("owner-1", str(INVOICE_ID), _payment_payload(), "stk-payment-request-0004")
    assert first_error.value.code == "mpesa_request_outcome_unknown"

    saved = mpesa_db["data"][mpesa.PAYMENTS_COLLECTION].find_one({
        "business_id": BUSINESS_ID,
        "idempotency_key": "mpesa-stk:stk-payment-request-0004",
    })
    assert saved["payment_status"] == "provider_request_unknown"
    assert saved["provider_verified"] is False

    with pytest.raises(APIError) as retry_error:
        mpesa.start_stk_push("owner-1", str(INVOICE_ID), _payment_payload(), "stk-payment-request-0004")
    assert retry_error.value.code == "mpesa_request_outcome_unknown"
    assert calls == {"get": 1, "post": 1}


def test_missing_callback_ip_allowlist_stops_stk_before_any_provider_request(mpesa_db, monkeypatch):
    monkeypatch.delenv("BIASHARA_MPESA_CALLBACK_ALLOWED_IPS", raising=False)
    calls = _ok_requests(monkeypatch)

    with pytest.raises(APIError) as raised:
        mpesa.start_stk_push("owner-1", str(INVOICE_ID), _payment_payload(), "stk-payment-request-0005")

    assert raised.value.code == "mpesa_callback_allowlist_not_configured"
    assert calls["get"] == []
    assert calls["post"] == []
    assert mpesa_db["data"][mpesa.PAYMENTS_COLLECTION].documents == []
