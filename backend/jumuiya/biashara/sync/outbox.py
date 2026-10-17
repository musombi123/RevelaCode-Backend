"""Durable, idempotent outbox primitives for Biashara OS.

The queue guarantees durable event identity and at-least-once processing
semantics. It deliberately does not claim exactly-once network delivery:
adapters must make provider calls idempotent and acknowledge an event only
after the provider confirms success.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import uuid
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError


logger = logging.getLogger("jumuiya.biashara.sync.outbox")

OUTBOX_COLLECTION = "jumuiya_outbox_events"
SOURCE_COLLECTIONS = (
    "jumuiya_orders",
    "jumuiya_sales",
    "jumuiya_inventory_movements",
    "jumuiya_products",
    "jumuiya_customers",
    "jumuiya_invoices",
    "jumuiya_payments",
    "jumuiya_journal_entries",
    "jumuiya_expenses",
    "jumuiya_suppliers",
    "jumuiya_purchase_orders",
    "jumuiya_returns",
)

OUTBOX_STATES = {"pending", "processing", "retry", "delivered", "dead_letter"}
RETRYABLE_STATES = {"pending", "retry"}
MAX_OUTBOX_ATTEMPTS = 8
MAX_EVENT_PAYLOAD_BYTES = 8192
MAX_CLAIM_LIMIT = 100

# Only these business fields may leave the canonical record through an outbox
# event. Customer names/contact details, tokens, secrets and arbitrary request
# bodies are intentionally excluded.
SAFE_PAYLOAD_FIELDS = {
    "status",
    "previous_status",
    "inventory_status",
    "source_channel",
    "amount_minor",
    "total_amount_minor",
    "currency",
    "payment_status",
    "payment_verification_status",
    "payment_method",
    "product_id",
    "order_id",
    "sale_id",
    "movement_type",
    "quantity",
    "reason",
    "previous_quantity",
    "new_quantity",
    "price_minor",
    "cost_minor",
    "stock_quantity",
    "reserved_quantity",
    "available_quantity",
    "sku",
    "invoice_number",
    "invoice_status",
    "document_type",
    "balance_due_minor",
    "amount_paid_minor",
    "amount_total_minor",
    "payment_id",
    "invoice_id",
    "due_date",
    "tax_submission_status",
    "expense_id",
    "expense_category",
    "supplier_id",
    "purchase_order_id",
    "purchase_order_number",
    "receipt_id",
    "return_id",
    "refund_status",
    "received_item_count",
    "line_count",
    "expected_delivery_date",
}


def now_utc():
    return datetime.now(timezone.utc)


def _as_datetime(value, default=None):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return default or now_utc()


def _coerce_id(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return value


def _json_value(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.replace(tzinfo=timezone.utc).isoformat()
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _safe_payload(payload):
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise APIError("Outbox payload must be an object.", 422, "invalid_outbox_payload")

    safe = {}
    for key, value in payload.items():
        if key not in SAFE_PAYLOAD_FIELDS or value is None:
            continue
        if isinstance(value, bool):
            safe[key] = value
        elif isinstance(value, int):
            safe[key] = value
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise APIError("Outbox payload contains a non-finite number.", 422, "invalid_outbox_payload")
            safe[key] = value
        elif isinstance(value, str):
            value = value.strip()
            if len(value) > 200:
                value = value[:200]
            safe[key] = value
        else:
            # Never serialize an arbitrary nested object into a provider event.
            continue

    encoded = json.dumps(safe, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_EVENT_PAYLOAD_BYTES:
        raise APIError("Outbox payload is too large.", 422, "outbox_payload_too_large")
    return safe


def build_outbox_manifest(
    event_key,
    event_type,
    entity_type,
    entity_id,
    payload=None,
    actor_user_id=None,
    occurred_at=None,
):
    """Build the durable event intent embedded in the source document.

    Embedding the manifest in the same source-document write makes a failed
    queue insert recoverable by repair_outbox_manifests().
    """
    key = str(event_key or "").strip()
    event_type = str(event_type or "").strip().lower()
    entity_type = str(entity_type or "").strip().lower()
    entity_id = str(entity_id or "").strip()
    if not key or len(key) > 220:
        raise APIError("Event key must be 1–220 characters.", 422, "invalid_event_key")
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,79}", event_type):
        raise APIError("Event type is invalid.", 422, "invalid_event_type")
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,79}", entity_type):
        raise APIError("Event entity type is invalid.", 422, "invalid_event_entity")
    if not entity_id or len(entity_id) > 200:
        raise APIError("Event entity ID is invalid.", 422, "invalid_event_entity_id")
    return {
        "event_key": key,
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payload": _safe_payload(payload),
        "actor_user_id": str(actor_user_id)[:128] if actor_user_id is not None else None,
        "occurred_at": _as_datetime(occurred_at),
    }


def _event_fingerprint(event_type, entity_type, entity_id, payload):
    canonical = {
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payload": payload,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_event_id(business_id, event_key):
    source = str(business_id) + "\0" + str(event_key)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _public_event(document, include_payload=True, include_lease=False):
    result = {
        "event_id": document.get("event_id", ""),
        "event_key": document.get("event_key", ""),
        "business_id": str(document.get("business_id", "")),
        "event_type": document.get("event_type", ""),
        "entity_type": document.get("entity_type", ""),
        "entity_id": document.get("entity_id", ""),
        "state": document.get("state", "pending"),
        "attempt_count": int(document.get("attempt_count", 0) or 0),
        "max_attempts": int(document.get("max_attempts", MAX_OUTBOX_ATTEMPTS) or MAX_OUTBOX_ATTEMPTS),
        "replay_count": int(document.get("replay_count", 0) or 0),
        "created_at": _json_value(document.get("created_at")),
        "updated_at": _json_value(document.get("updated_at")),
        "occurred_at": _json_value(document.get("occurred_at")),
        "next_attempt_at": _json_value(document.get("next_attempt_at")),
        "delivered_at": _json_value(document.get("delivered_at")),
        "last_error_code": document.get("last_error_code"),
        "last_error_at": _json_value(document.get("last_error_at")),
        "provider_result_reference": document.get("provider_result_reference"),
        "actor_user_id": document.get("actor_user_id"),
        "automation_dispatch_status": document.get("automation_dispatch_status", "pending"),
        "automation_dispatch_attempt_count": int(document.get("automation_dispatch_attempt_count", 0) or 0),
        "automation_last_dispatch_at": _json_value(document.get("automation_last_dispatch_at")),
        "automation_last_error_code": document.get("automation_last_error_code"),
        "automation_last_run_count": int(document.get("automation_last_run_count", 0) or 0),
    }
    if include_payload:
        result["payload"] = dict(document.get("payload") or {})
    if include_lease:
        result["lease_owner"] = document.get("lease_owner")
        result["lease_token"] = document.get("lease_token")
        result["lease_expires_at"] = _json_value(document.get("lease_expires_at"))
    if document.get("_id") is not None:
        result["id"] = str(document["_id"])
    return result


def _dispatch_automation_event(document):
    """Dispatch durable internal automation and retain failed attempts for replay."""
    business_id = str(document.get("business_id") or "")
    event_id = str(document.get("event_id") or "")
    if not business_id or not event_id:
        return {"processed": False, "error_code": "invalid_automation_event"}
    try:
        from backend.jumuiya.biashara.automation.services import process_event_for_automations
        result = process_event_for_automations(_public_event(document, include_payload=True))
        processed = bool(result.get("processed"))
        collection(OUTBOX_COLLECTION).update_one(
            {"business_id": business_id, "event_id": event_id},
            {
                "$set": {
                    "automation_dispatch_status": "processed" if processed else "retry",
                    "automation_last_dispatch_at": now_utc(),
                    "automation_last_error_code": result.get("error_code"),
                    "automation_last_run_count": int(result.get("created_runs", 0) or 0),
                    "updated_at": now_utc(),
                },
                "$inc": {"automation_dispatch_attempt_count": 1},
            },
        )
        return result
    except Exception as error:
        logger.warning(
            "Biashara automation dispatch deferred (event_hash=%s, error=%s)",
            hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:12],
            type(error).__name__,
        )
        try:
            collection(OUTBOX_COLLECTION).update_one(
                {"business_id": business_id, "event_id": event_id},
                {
                    "$set": {
                        "automation_dispatch_status": "retry",
                        "automation_last_dispatch_at": now_utc(),
                        "automation_last_error_code": "automation_dispatch_failed",
                        "updated_at": now_utc(),
                    },
                    "$inc": {"automation_dispatch_attempt_count": 1},
                },
            )
        except Exception:
            logger.warning("Biashara automation dispatch status update deferred.")
        return {"processed": False, "error_code": "automation_dispatch_failed"}


def enqueue_outbox_event(
    business_id,
    event_key,
    event_type,
    entity_type,
    entity_id,
    payload=None,
    actor_user_id=None,
    occurred_at=None,
):
    """Persist an idempotent, tenant-scoped event. Repeat calls return the same event."""
    business_id = str(business_id or "").strip()
    if not business_id:
        raise APIError("Business ID is required for an outbox event.", 422, "outbox_business_required")

    manifest = build_outbox_manifest(
        event_key=event_key,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        actor_user_id=actor_user_id,
        occurred_at=occurred_at,
    )
    event_id = _stable_event_id(business_id, manifest["event_key"])
    fingerprint = _event_fingerprint(
        manifest["event_type"],
        manifest["entity_type"],
        manifest["entity_id"],
        manifest["payload"],
    )
    events = collection(OUTBOX_COLLECTION)
    query = {"business_id": business_id, "event_id": event_id}
    existing = events.find_one(query)
    if existing:
        if existing.get("event_fingerprint") != fingerprint:
            raise APIError(
                "This event key was already used for different event data.",
                409,
                "outbox_event_key_conflict",
            )
        if existing.get("automation_dispatch_status") != "processed":
            _dispatch_automation_event(existing)
            existing = events.find_one(query) or existing
        return _public_event(existing)

    now = now_utc()
    document = {
        "business_id": business_id,
        "event_id": event_id,
        "event_key": manifest["event_key"],
        "event_fingerprint": fingerprint,
        "event_type": manifest["event_type"],
        "entity_type": manifest["entity_type"],
        "entity_id": manifest["entity_id"],
        "payload": manifest["payload"],
        "actor_user_id": manifest["actor_user_id"],
        "occurred_at": manifest["occurred_at"],
        "state": "pending",
        "attempt_count": 0,
        "max_attempts": MAX_OUTBOX_ATTEMPTS,
        "replay_count": 0,
        "next_attempt_at": now,
        "lease_owner": None,
        "lease_token": None,
        "lease_expires_at": None,
        "last_error_code": None,
        "last_error_at": None,
        "delivered_at": None,
        "provider_result_reference": None,
        "automation_dispatch_status": "pending",
        "automation_dispatch_attempt_count": 0,
        "automation_last_dispatch_at": None,
        "automation_last_error_code": None,
        "automation_last_run_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = events.insert_one(document)
        document["_id"] = result.inserted_id
        _dispatch_automation_event(document)
        document = events.find_one(query) or document
        return _public_event(document)
    except DuplicateKeyError:
        existing = events.find_one(query)
        if existing and existing.get("event_fingerprint") == fingerprint:
            if existing.get("automation_dispatch_status") != "processed":
                _dispatch_automation_event(existing)
                existing = events.find_one(query) or existing
            return _public_event(existing)
        if existing:
            raise APIError(
                "This event key was already used for different event data.",
                409,
                "outbox_event_key_conflict",
            )
        raise


def dispatch_manifest_for_record(source_collection_name, business_id, record_id):
    """Enqueue unacknowledged source manifests without losing recovery information."""
    if source_collection_name not in SOURCE_COLLECTIONS:
        raise APIError("Unsupported outbox source collection.", 422, "invalid_outbox_source")
    business_id = str(business_id or "").strip()
    source = collection(source_collection_name)
    query = {"_id": _coerce_id(record_id), "business_id": business_id}
    document = source.find_one(query)
    if not document:
        raise APIError("Outbox source record not found.", 404, "outbox_source_not_found")

    manifests = document.get("outbox_event_manifest")
    if not isinstance(manifests, list) or not manifests:
        return {"enqueued": 0, "pending": 0, "errors": 0}

    enqueued_keys = set(document.get("outbox_enqueued_event_keys") or [])
    enqueued = 0
    errors = 0
    for manifest in manifests:
        if not isinstance(manifest, dict):
            continue
        event_key = str(manifest.get("event_key") or "")
        if not event_key or event_key in enqueued_keys:
            continue
        try:
            enqueue_outbox_event(
                business_id=business_id,
                event_key=event_key,
                event_type=manifest.get("event_type"),
                entity_type=manifest.get("entity_type"),
                entity_id=manifest.get("entity_id"),
                payload=manifest.get("payload"),
                actor_user_id=manifest.get("actor_user_id"),
                occurred_at=manifest.get("occurred_at"),
            )
            source.update_one(
                query,
                {
                    "$addToSet": {"outbox_enqueued_event_keys": event_key},
                    "$set": {"outbox_last_dispatch_at": now_utc()},
                },
            )
            enqueued_keys.add(event_key)
            enqueued += 1
        except Exception as error:
            errors += 1
            logger.warning(
                "Biashara outbox dispatch deferred (source=%s, event_key_hash=%s, error=%s)",
                source_collection_name,
                hashlib.sha256(event_key.encode("utf-8")).hexdigest()[:12],
                type(error).__name__,
            )
    pending = sum(
        1 for item in manifests
        if isinstance(item, dict) and item.get("event_key") not in enqueued_keys
    )
    return {"enqueued": enqueued, "pending": pending, "errors": errors}


def repair_outbox_manifests(business_id=None, limit=100):
    """Repair source records whose committed event manifest has not reached the queue.

    Call from a scheduled backend worker or deployment job. Event insertion and
    source acknowledgement are independently retryable and use stable event IDs.
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 100
    limit = min(max(limit, 1), MAX_CLAIM_LIMIT)
    business_id = str(business_id).strip() if business_id is not None else None
    report = {"inspected": 0, "enqueued": 0, "pending": 0, "errors": 0, "sources": {}}

    for source_name in SOURCE_COLLECTIONS:
        remaining = limit - report["inspected"]
        if remaining <= 0:
            break
        query = {"outbox_event_manifest": {"$exists": True}}
        if business_id:
            query["business_id"] = business_id
        docs = list(
            collection(source_name)
            .find(query)
            .sort("updated_at", 1)
            .limit(remaining)
        )
        source_report = {"inspected": 0, "enqueued": 0, "pending": 0, "errors": 0}
        for document in docs:
            source_report["inspected"] += 1
            report["inspected"] += 1
            result = dispatch_manifest_for_record(
                source_name,
                str(document.get("business_id") or ""),
                document.get("_id"),
            )
            for key in ("enqueued", "pending", "errors"):
                source_report[key] += int(result.get(key, 0) or 0)
                report[key] += int(result.get(key, 0) or 0)
        report["sources"][source_name] = source_report
    return report


def pending_manifest_count(business_id=None, scan_limit=1000):
    """Approximate count of source event manifests awaiting durable queue insertion."""
    business_id = str(business_id).strip() if business_id is not None else None
    try:
        scan_limit = max(1, min(int(scan_limit), 5000))
    except (TypeError, ValueError):
        scan_limit = 1000
    pending = 0
    inspected = 0
    for source_name in SOURCE_COLLECTIONS:
        remaining = scan_limit - inspected
        if remaining <= 0:
            break
        query = {"outbox_event_manifest": {"$exists": True}}
        if business_id:
            query["business_id"] = business_id
        for document in collection(source_name).find(query).limit(remaining):
            inspected += 1
            done = set(document.get("outbox_enqueued_event_keys") or [])
            pending += sum(
                1 for item in document.get("outbox_event_manifest") or []
                if isinstance(item, dict) and item.get("event_key") not in done
            )
    return {"pending_manifest_events": pending, "source_records_scanned": inspected, "scan_limit": scan_limit}


def claim_due_events(worker_id, business_id=None, limit=10, lease_seconds=60):
    """Atomically lease due events for a worker. Delivery remains at-least-once."""
    worker_id = str(worker_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{3,128}", worker_id):
        raise APIError("Worker ID is invalid.", 422, "invalid_worker_id")
    try:
        limit = int(limit)
        lease_seconds = int(lease_seconds)
    except (TypeError, ValueError):
        raise APIError("Claim limit and lease duration must be integers.", 422, "invalid_outbox_claim")
    limit = min(max(limit, 1), MAX_CLAIM_LIMIT)
    lease_seconds = min(max(lease_seconds, 15), 900)
    now = now_utc()
    query = {
        "$or": [
            {"state": {"$in": ["pending", "retry"]}, "next_attempt_at": {"$lte": now}},
            {"state": "processing", "lease_expires_at": {"$lte": now}},
        ]
    }
    if business_id is not None:
        query["business_id"] = str(business_id)

    events = collection(OUTBOX_COLLECTION)
    claimed = []
    for _ in range(limit):
        token = uuid.uuid4().hex
        document = events.find_one_and_update(
            query,
            {
                "$set": {
                    "state": "processing",
                    "lease_owner": worker_id,
                    "lease_token": token,
                    "lease_expires_at": now + timedelta(seconds=lease_seconds),
                    "updated_at": now,
                },
                "$inc": {"attempt_count": 1},
            },
            sort=[("next_attempt_at", 1), ("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if not document:
            break
        claimed.append(_public_event(document, include_payload=True, include_lease=True))
    return claimed


def _leased_event(business_id, event_id, worker_id, lease_token):
    document = collection(OUTBOX_COLLECTION).find_one({
        "business_id": str(business_id),
        "event_id": str(event_id),
        "state": "processing",
        "lease_owner": str(worker_id),
        "lease_token": str(lease_token),
        "lease_expires_at": {"$gt": now_utc()},
    })
    if not document:
        raise APIError(
            "Outbox lease is missing, expired or owned by another worker.",
            409,
            "outbox_lease_conflict",
        )
    return document


def mark_event_delivered(business_id, event_id, worker_id, lease_token, provider_result_reference=None):
    """Acknowledge only an event held by the caller's active lease."""
    _leased_event(business_id, event_id, worker_id, lease_token)
    now = now_utc()
    reference = str(provider_result_reference or "").strip()[:160]
    update = {
        "$set": {
            "state": "delivered",
            "delivered_at": now,
            "provider_result_reference": reference or None,
            "updated_at": now,
        },
        "$unset": {
            "lease_owner": "",
            "lease_token": "",
            "lease_expires_at": "",
        },
    }
    document = collection(OUTBOX_COLLECTION).find_one_and_update(
        {
            "business_id": str(business_id),
            "event_id": str(event_id),
            "state": "processing",
            "lease_owner": str(worker_id),
            "lease_token": str(lease_token),
            "lease_expires_at": {"$gt": now},
        },
        update,
        return_document=ReturnDocument.AFTER,
    )
    if not document:
        raise APIError("Outbox lease changed before acknowledgement.", 409, "outbox_lease_conflict")
    return _public_event(document)


def _retry_delay_seconds(event_id, attempt_count):
    exponent = min(max(int(attempt_count) - 1, 0), 12)
    base = min(5 * (2 ** exponent), 21600)
    sample = int(hashlib.sha256(f"{event_id}:{attempt_count}".encode("utf-8")).hexdigest()[:8], 16)
    jitter = 0.8 + 0.4 * (sample / 0xFFFFFFFF)
    return max(1, min(int(base * jitter), 21600))


def mark_event_failed(
    business_id,
    event_id,
    worker_id,
    lease_token,
    error_code,
    retryable=True,
):
    """Persist a safe error code and schedule bounded exponential retry/dead-letter."""
    document = _leased_event(business_id, event_id, worker_id, lease_token)
    if not isinstance(retryable, bool):
        raise APIError("retryable must be a boolean.", 422, "invalid_retry_state")
    code = str(error_code or "provider_error").strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{1,100}", code):
        code = "provider_error"
    attempt_count = int(document.get("attempt_count", 1) or 1)
    max_attempts = int(document.get("max_attempts", MAX_OUTBOX_ATTEMPTS) or MAX_OUTBOX_ATTEMPTS)
    dead_letter = (not retryable) or attempt_count >= max_attempts
    now = now_utc()
    next_state = "dead_letter" if dead_letter else "retry"
    next_attempt_at = now if dead_letter else now + timedelta(
        seconds=_retry_delay_seconds(str(event_id), attempt_count)
    )
    updated = collection(OUTBOX_COLLECTION).find_one_and_update(
        {
            "business_id": str(business_id),
            "event_id": str(event_id),
            "state": "processing",
            "lease_owner": str(worker_id),
            "lease_token": str(lease_token),
            "lease_expires_at": {"$gt": now},
            "attempt_count": attempt_count,
        },
        {
            "$set": {
                "state": next_state,
                "last_error_code": code,
                "last_error_at": now,
                "next_attempt_at": next_attempt_at,
                "updated_at": now,
            },
            "$unset": {
                "lease_owner": "",
                "lease_token": "",
                "lease_expires_at": "",
            },
        },
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise APIError("Outbox lease changed while recording failure.", 409, "outbox_lease_conflict")
    return _public_event(updated)


def replay_dead_letter_event(business_id, event_id, actor_user_id):
    """Requeue a dead-letter event after an explicit operator action."""
    query = {"business_id": str(business_id), "event_id": str(event_id)}
    events = collection(OUTBOX_COLLECTION)
    document = events.find_one(query)
    if not document:
        raise APIError("Sync event not found.", 404, "outbox_event_not_found")
    if document.get("state") not in {"dead_letter", "retry"}:
        raise APIError(
            "Only failed or dead-letter events can be manually replayed.",
            409,
            "outbox_event_not_replayable",
        )
    now = now_utc()
    updated = events.find_one_and_update(
        {
            **query,
            "state": document["state"],
        },
        {
            "$set": {
                "state": "pending",
                "next_attempt_at": now,
                "manual_replay_at": now,
                "manual_replay_by": str(actor_user_id),
                "updated_at": now,
            },
            "$inc": {"replay_count": 1},
            "$unset": {
                "lease_owner": "",
                "lease_token": "",
                "lease_expires_at": "",
            },
        },
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise APIError("Sync event changed before replay was saved.", 409, "outbox_state_conflict")
    return _public_event(updated)


def list_outbox_events(business_id, state=None, limit=50):
    business_id = str(business_id or "").strip()
    if not business_id:
        raise APIError("Business ID is required.", 422, "outbox_business_required")
    state = str(state or "").strip().lower()
    if state and state not in OUTBOX_STATES:
        raise APIError("Unknown sync event state.", 422, "invalid_outbox_state")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 50
    limit = min(max(limit, 1), 100)
    query = {"business_id": business_id}
    if state:
        query["state"] = state
    documents = list(
        collection(OUTBOX_COLLECTION)
        .find(query)
        .sort("created_at", -1)
        .limit(limit)
    )
    return [_public_event(document) for document in documents]


def get_outbox_summary(business_id):
    business_id = str(business_id or "").strip()
    if not business_id:
        raise APIError("Business ID is required.", 422, "outbox_business_required")
    events = collection(OUTBOX_COLLECTION)
    states = {}
    for state in sorted(OUTBOX_STATES):
        states[state] = events.count_documents({"business_id": business_id, "state": state})
    oldest = events.find({
        "business_id": business_id,
        "state": {"$in": ["pending", "retry", "dead_letter"]},
    }).sort("created_at", 1).limit(1)
    oldest_document = next(iter(oldest), None)
    oldest_at = oldest_document.get("created_at") if oldest_document else None
    age_seconds = None
    if oldest_at:
        age_seconds = max(0, int((now_utc() - _as_datetime(oldest_at)).total_seconds()))
    manifest_state = pending_manifest_count(business_id)
    return {
        "states": states,
        "total_events": sum(states.values()),
        "oldest_actionable_event_at": _json_value(oldest_at),
        "oldest_actionable_event_age_seconds": age_seconds,
        "pending_manifest_events": manifest_state["pending_manifest_events"],
        "source_records_scanned": manifest_state["source_records_scanned"],
        "manifest_scan_limit": manifest_state["scan_limit"],
        "delivery_semantics": "at_least_once",
    }
