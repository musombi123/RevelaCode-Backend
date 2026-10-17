"""Lease-based WooCommerce product auto-sync jobs.

Only product metadata edits for already-mapped/imported products are eligible.
The current connector writes name, SKU, price and description only: this worker
never writes stock quantities/cost price, creates a remote product, imports an
order or claims that a remote write succeeded when the outcome is ambiguous.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.biashara.integrations import service as integration_service
from backend.jumuiya.biashara.integrations import woocommerce
from backend.jumuiya.biashara.sync.outbox import OUTBOX_COLLECTION


logger = logging.getLogger("jumuiya.biashara.integrations.worker")

SYNC_JOBS_COLLECTION = "jumuiya_provider_sync_jobs"
BUSINESSES_COLLECTION = "jumuiya_businesses"
MAPPINGS_COLLECTION = woocommerce.MAPPINGS_COLLECTION
SUPPORTED_EVENT_TYPES = {"product.updated"}
MAX_BATCH_LIMIT = 100
DEFAULT_BATCH_LIMIT = 10
DEFAULT_LEASE_SECONDS = 90
MAX_LEASE_SECONDS = 600
MAX_ATTEMPTS = 8

TERMINAL_STATUSES = {
    "completed", "conflict", "outcome_unknown", "skipped", "blocked", "dead_letter"
}
PERMANENT_CONFIGURATION_ERRORS = {
    "woocommerce_connection_not_found",
    "woocommerce_api_version_invalid",
    "woocommerce_credentials_incomplete",
    "integration_encryption_unavailable",
    "integration_credentials_unreadable",
    "woocommerce_store_currency_not_confirmed",
    "woocommerce_currency_mismatch",
    "woocommerce_store_url_invalid",
    "woocommerce_store_host_blocked",
    "woocommerce_store_dns_failed",
    "woocommerce_store_dns_invalid",
}


def now_utc():
    return datetime.now(timezone.utc)


def _clean_id(value):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return value


def _limit(value, default, maximum=MAX_BATCH_LIMIT):
    try:
        return min(max(int(value), 1), maximum)
    except (TypeError, ValueError, OverflowError):
        return default


def _worker_id(value):
    worker_id = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}", worker_id):
        raise APIError("worker_id must be 3–128 safe characters.", 422, "invalid_provider_sync_worker")
    return worker_id


def _utc_datetime(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


def _serialise(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value, list):
        return [_serialise(item) for item in value]
    if isinstance(value, dict):
        return {
            ("id" if key == "_id" else key): _serialise(item)
            for key, item in value.items()
            if key not in {
                "credentials_ciphertext", "credential_key_id", "credentials",
                "request_fingerprint", "provider_response", "raw_payload",
                "lease_token", "provider_sync_fanout_lease_token",
            }
        }
    return value


def _public_job(document):
    """Allowlist the Sync Centre result; never return remote payloads or credentials."""
    return {
        "id": str(document.get("_id") or ""),
        "business_id": str(document.get("business_id") or ""),
        "provider": document.get("provider", "woocommerce"),
        "connection_id": str(document.get("connection_id") or ""),
        "connection_name": document.get("connection_name", ""),
        "source_event_id": str(document.get("source_event_id") or ""),
        "source_event_type": document.get("source_event_type"),
        "product_id": str(document.get("product_id") or ""),
        "external_product_id": str(document.get("external_product_id") or ""),
        "status": document.get("status"),
        "attempt_count": int(document.get("attempt_count", 0) or 0),
        "manual_replay_count": int(document.get("manual_replay_count", 0) or 0),
        "last_result_status": document.get("last_result_status"),
        "last_error_code": document.get("last_error_code"),
        "last_result_reason": document.get("last_result_reason"),
        "next_attempt_at": _serialise(document.get("next_attempt_at")),
        "created_at": _serialise(document.get("created_at")),
        "updated_at": _serialise(document.get("updated_at")),
        "finished_at": _serialise(document.get("finished_at")),
        "last_attempt_at": _serialise(document.get("last_attempt_at")),
    }


def _eligible_connections(business_id):
    connections = collection(integration_service.CONNECTIONS_COLLECTION)
    rows = connections.find({
        "business_id": str(business_id),
        "provider": "woocommerce",
        "enabled": True,
        "auto_sync_enabled": True,
        "last_test_status": "success",
    }).sort("created_at", 1).limit(100)
    return list(rows)


def _mapping_for(business_id, connection_id, product_id):
    return collection(MAPPINGS_COLLECTION).find_one({
        "business_id": str(business_id),
        "connection_id": str(connection_id),
        "resource_type": "product",
        "local_resource_id": str(product_id),
        "import_status": "imported",
    })


def _create_job(event, connection, mapping=None, skip_reason=None):
    business_id = str(event.get("business_id") or "")
    event_id = str(event.get("event_id") or "")
    product_id = str(event.get("entity_id") or "")
    connection_id = str(connection.get("_id") or "")
    fingerprint = hashlib.sha256(
        (business_id + ":" + connection_id + ":" + event_id).encode("utf-8")
    ).hexdigest()
    jobs = collection(SYNC_JOBS_COLLECTION)
    query = {
        "business_id": business_id,
        "connection_id": connection_id,
        "source_event_id": event_id,
    }
    prior = jobs.find_one(query)
    if prior:
        return prior, False

    now = now_utc()
    status = "skipped" if skip_reason else "pending"
    document = {
        "_id": ObjectId(),
        "business_id": business_id,
        "provider": "woocommerce",
        "connection_id": connection_id,
        "connection_name": str(connection.get("name") or "")[:100],
        "source_event_id": event_id,
        "source_event_type": str(event.get("event_type") or "")[:100],
        "product_id": product_id,
        "external_product_id": str((mapping or {}).get("external_id") or ""),
        "job_key": fingerprint,
        "status": status,
        "attempt_count": 0,
        "manual_replay_count": 0,
        "next_attempt_at": None,
        "lease_owner": None,
        "lease_token": None,
        "lease_expires_at": None,
        "last_attempt_at": None,
        "last_result_status": "skipped" if skip_reason else None,
        "last_error_code": skip_reason,
        "last_result_reason": skip_reason,
        "created_at": now,
        "updated_at": now,
        "finished_at": now if skip_reason else None,
    }
    try:
        jobs.insert_one(document)
        return document, True
    except DuplicateKeyError:
        prior = jobs.find_one(query)
        if prior:
            return prior, False
        raise


def _free_fanout_lease_clause(now):
    return {
        "$or": [
            {"provider_sync_fanout_lease_expires_at": {"$exists": False}},
            {"provider_sync_fanout_lease_expires_at": None},
            {"provider_sync_fanout_lease_expires_at": {"$lte": now}},
        ]
    }


def _claim_source_event(worker_id, business_id=None, lease_seconds=DEFAULT_LEASE_SECONDS):
    now = now_utc()
    lease_clause = _free_fanout_lease_clause(now)
    query = {
        "entity_type": "product",
        "event_type": {"$in": sorted(SUPPORTED_EVENT_TYPES)},
        "$or": [
            {
                "provider_sync_fanout_status": {"$in": ["pending", "retry"]},
                **lease_clause,
            },
            {
                "provider_sync_fanout_status": {"$exists": False},
                **lease_clause,
            },
            {
                "provider_sync_fanout_status": "processing",
                "provider_sync_fanout_lease_expires_at": {"$lte": now},
            },
        ],
    }
    if business_id is not None:
        query["business_id"] = str(business_id)
    token = secrets.token_urlsafe(32)
    event = collection(OUTBOX_COLLECTION).find_one_and_update(
        query,
        {
            "$set": {
                "provider_sync_fanout_status": "processing",
                "provider_sync_fanout_lease_owner": worker_id,
                "provider_sync_fanout_lease_token": token,
                "provider_sync_fanout_lease_expires_at": now + timedelta(seconds=lease_seconds),
                "provider_sync_fanout_last_error_code": None,
                "updated_at": now,
            },
            "$inc": {"provider_sync_fanout_attempt_count": 1},
        },
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
    )
    if not event:
        return None
    return event


def _finish_source(event, worker_id, token, state, job_count=0, error_code=None):
    now = now_utc()
    result = collection(OUTBOX_COLLECTION).update_one(
        {
            "business_id": str(event.get("business_id") or ""),
            "event_id": str(event.get("event_id") or ""),
            "provider_sync_fanout_status": "processing",
            "provider_sync_fanout_lease_owner": worker_id,
            "provider_sync_fanout_lease_token": token,
            "provider_sync_fanout_lease_expires_at": {"$gt": now},
        },
        {
            "$set": {
                "provider_sync_fanout_status": state,
                "provider_sync_fanout_job_count": int(job_count or 0),
                "provider_sync_fanout_last_error_code": error_code,
                "provider_sync_fanout_last_at": now,
                "provider_sync_fanout_lease_owner": None,
                "provider_sync_fanout_lease_token": None,
                "provider_sync_fanout_lease_expires_at": None,
                "updated_at": now,
            }
        },
    )
    return bool(getattr(result, "matched_count", 0))


def _event_after_opt_in(event, connection):
    enabled_at = _utc_datetime(connection.get("auto_sync_enabled_at"))
    event_at = _utc_datetime(event.get("created_at"))
    return bool(enabled_at and event_at and event_at >= enabled_at)


def _fanout_event(event, worker_id, lease_seconds):
    business_id = str(event.get("business_id") or "")
    event_id = str(event.get("event_id") or "")
    product_id = str(event.get("entity_id") or "")
    token = str(event.get("provider_sync_fanout_lease_token") or "")
    attempts = int(event.get("provider_sync_fanout_attempt_count", 0) or 0)

    if attempts > MAX_ATTEMPTS:
        acknowledged = _finish_source(event, worker_id, token, "dead_letter", error_code="sync_fanout_retry_exhausted")
        return {"dispatched": 0, "jobs_created": 0, "jobs_skipped": 0, "dead_lettered": int(acknowledged), "lease_lost": int(not acknowledged)}

    connections = _eligible_connections(business_id)
    dispatched = 0
    created = 0
    skipped = 0
    for connection in connections:
        if not _event_after_opt_in(event, connection):
            continue
        mapping = _mapping_for(business_id, connection["_id"], product_id)
        job, inserted = _create_job(
            event,
            connection,
            mapping=mapping,
            skip_reason=None if mapping else "no_imported_product_mapping",
        )
        dispatched += 1
        if inserted:
            created += 1
            if job.get("status") == "skipped":
                skipped += 1

    state = "dispatched" if dispatched else "no_eligible_connections"
    acknowledged = _finish_source(
        event,
        worker_id,
        token,
        state,
        job_count=dispatched,
    )
    if not acknowledged:
        return {"dispatched": dispatched, "jobs_created": created, "jobs_skipped": skipped, "dead_lettered": 0, "lease_lost": 1}
    return {
        "dispatched": dispatched,
        "jobs_created": created,
        "jobs_skipped": skipped,
        "dead_lettered": 0,
        "lease_lost": 0,
    }


def fanout_product_update_events(worker_id, limit=25, lease_seconds=DEFAULT_LEASE_SECONDS, business_id=None):
    """Create one durable sync job per opted-in connection for eligible product events."""
    worker_id = _worker_id(worker_id)
    limit = _limit(limit, 25, MAX_BATCH_LIMIT)
    lease_seconds = _limit(lease_seconds, DEFAULT_LEASE_SECONDS, MAX_LEASE_SECONDS)
    report = {
        "events_claimed": 0,
        "events_dispatched": 0,
        "jobs_created": 0,
        "jobs_skipped": 0,
        "dead_lettered": 0,
        "lease_lost": 0,
    }
    events = collection(OUTBOX_COLLECTION)
    for _ in range(limit):
        event = _claim_source_event(worker_id, business_id=business_id, lease_seconds=lease_seconds)
        if event is None:
            break
        report["events_claimed"] += 1
        try:
            result = _fanout_event(event, worker_id, lease_seconds)
        except Exception as error:
            attempts = int(event.get("provider_sync_fanout_attempt_count", 0) or 0)
            state = "dead_letter" if attempts >= MAX_ATTEMPTS else "retry"
            token = str(event.get("provider_sync_fanout_lease_token") or "")
            acknowledged = _finish_source(
                event,
                worker_id,
                token,
                state,
                error_code="provider_sync_fanout_failed",
            )
            report["dead_lettered"] += int(acknowledged and state == "dead_letter")
            report["lease_lost"] += int(not acknowledged)
            logger.warning(
                "Biashara provider sync fanout deferred (event_hash=%s, error=%s)",
                hashlib.sha256(str(event.get("event_id", "")).encode("utf-8")).hexdigest()[:12],
                type(error).__name__,
            )
            continue
        report["events_dispatched"] += int(result.get("dispatched", 0) > 0)
        report["jobs_created"] += int(result.get("jobs_created", 0) or 0)
        report["jobs_skipped"] += int(result.get("jobs_skipped", 0) or 0)
        report["dead_lettered"] += int(result.get("dead_lettered", 0) or 0)
        report["lease_lost"] += int(result.get("lease_lost", 0) or 0)
    return report


def _free_job_lease_clause(now):
    return {
        "$or": [
            {"lease_expires_at": {"$exists": False}},
            {"lease_expires_at": None},
            {"lease_expires_at": {"$lte": now}},
        ]
    }


def _claim_job(worker_id, business_id=None, lease_seconds=DEFAULT_LEASE_SECONDS):
    now = now_utc()
    due_clause = {
        "$or": [
            {"next_attempt_at": {"$exists": False}},
            {"next_attempt_at": None},
            {"next_attempt_at": {"$lte": now}},
        ]
    }
    query = {
        "$or": [
            {
                "status": {"$in": ["pending", "retry"]},
                **due_clause,
                **_free_job_lease_clause(now),
            },
            {
                "status": "processing",
                "lease_expires_at": {"$lte": now},
            },
        ],
    }
    if business_id is not None:
        query["business_id"] = str(business_id)
    token = secrets.token_urlsafe(32)
    job = collection(SYNC_JOBS_COLLECTION).find_one_and_update(
        query,
        {
            "$set": {
                "status": "processing",
                "lease_owner": worker_id,
                "lease_token": token,
                "lease_expires_at": now + timedelta(seconds=lease_seconds),
                "last_attempt_at": now,
                "last_error_code": None,
                "updated_at": now,
            },
            "$inc": {"attempt_count": 1},
        },
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
    )
    return job


def _finish_job(job, worker_id, token, status, result_status=None, error_code=None, reason=None):
    now = now_utc()
    next_attempt = None
    finished_at = now if status in TERMINAL_STATUSES else None
    if status == "retry":
        attempts = int(job.get("attempt_count", 1) or 1)
        base_delay = min((2 ** min(attempts, 7)) * 5, 900)
        jitter = int(hashlib.sha256(str(job.get("job_key") or "").encode("utf-8")).hexdigest()[:2], 16) % 7
        next_attempt = now + timedelta(seconds=base_delay + jitter)
    result = collection(SYNC_JOBS_COLLECTION).update_one(
        {
            "_id": job["_id"],
            "business_id": str(job.get("business_id") or ""),
            "status": "processing",
            "lease_owner": worker_id,
            "lease_token": token,
            "lease_expires_at": {"$gt": now},
        },
        {
            "$set": {
                "status": status,
                "last_result_status": result_status or status,
                "last_error_code": str(error_code or "")[:120] or None,
                "last_result_reason": str(reason or "")[:240] or None,
                "next_attempt_at": next_attempt,
                "finished_at": finished_at,
                "lease_owner": None,
                "lease_token": None,
                "lease_expires_at": None,
                "updated_at": now,
            }
        },
    )
    return bool(getattr(result, "matched_count", 0))


def _interpret_sync_result(report):
    results = report.get("results") if isinstance(report, dict) else None
    if not isinstance(results, list) or not results:
        return "retry", "sync_result_missing", "WooCommerce adapter returned no per-product result."
    result = results[0] if isinstance(results[0], dict) else {}
    status = str(result.get("status") or "failed").lower()
    reason = str(result.get("reason") or "")
    error_code = str(result.get("error_code") or "")
    if status in {"synced", "no_changes"}:
        return "completed", status, reason or status
    if status in {"conflict", "outcome_unknown"}:
        return status, status, reason or error_code or status
    if status == "skipped":
        return "skipped", status, reason or status
    if status == "in_progress":
        return "retry", status, reason or "mapping_sync_lease_busy"
    return "retry", status, reason or error_code or "provider_sync_failed"


def _process_job(job):
    business_id = str(job.get("business_id") or "")
    connection_id = str(job.get("connection_id") or "")
    product_id = str(job.get("product_id") or "")

    connection = collection(integration_service.CONNECTIONS_COLLECTION).find_one({
        "_id": _clean_id(connection_id),
        "business_id": business_id,
        "provider": "woocommerce",
    })
    if not connection:
        return "blocked", "connection_not_found", "Integration connection is missing."
    if not connection.get("enabled") or not connection.get("auto_sync_enabled"):
        return "skipped", "auto_sync_disabled", "The connection or its auto-sync setting is disabled."
    if connection.get("last_test_status") != "success":
        return "blocked", "integration_connection_not_tested", "Re-test the provider connection before retrying this sync job."

    business = collection(BUSINESSES_COLLECTION).find_one({"_id": _clean_id(business_id)})
    if not business:
        return "blocked", "business_not_found", "Business record is missing."
    owner_user_id = str(business.get("owner_user_id") or "").strip()
    if not owner_user_id:
        return "blocked", "business_owner_missing", "Business owner identity is missing."

    result = woocommerce.sync_products(
        owner_user_id,
        connection_id,
        [product_id],
        business_id=business_id,
    )
    state, result_status, reason = _interpret_sync_result(result)
    error_code = reason if state in {"retry", "blocked"} else None
    return state, error_code, result_status + (": " + reason if reason and reason != result_status else "")


def run_woocommerce_sync_batch(worker_id, limit=DEFAULT_BATCH_LIMIT, lease_seconds=DEFAULT_LEASE_SECONDS, business_id=None):
    """Fan out local product events, then process bounded external sync jobs."""
    worker_id = _worker_id(worker_id)
    limit = _limit(limit, DEFAULT_BATCH_LIMIT, MAX_BATCH_LIMIT)
    lease_seconds = _limit(lease_seconds, DEFAULT_LEASE_SECONDS, MAX_LEASE_SECONDS)
    if business_id is not None and not str(business_id).strip():
        raise APIError("business_id must not be blank.", 422, "invalid_provider_sync_worker")

    fanout = fanout_product_update_events(
        worker_id=worker_id + "-fanout",
        limit=min(limit, MAX_BATCH_LIMIT),
        lease_seconds=lease_seconds,
        business_id=business_id,
    )
    report = {
        "worker_id": worker_id,
        "fanout": fanout,
        "claimed": 0,
        "completed": 0,
        "retried": 0,
        "conflicts": 0,
        "outcome_unknown": 0,
        "skipped": 0,
        "blocked": 0,
        "dead_lettered": 0,
        "lease_lost": 0,
        "no_work": False,
    }

    for _ in range(limit):
        job = _claim_job(worker_id, business_id=business_id, lease_seconds=lease_seconds)
        if job is None:
            report["no_work"] = report["claimed"] == 0
            break
        report["claimed"] += 1
        token = str(job.get("lease_token") or "")
        attempts = int(job.get("attempt_count", 0) or 0)
        if attempts > MAX_ATTEMPTS:
            if _finish_job(job, worker_id, token, "dead_letter", result_status="dead_letter", error_code="provider_sync_retry_exhausted", reason="Retry limit reached; inspect connection and mapping before replay."):
                report["dead_lettered"] += 1
            else:
                report["lease_lost"] += 1
            continue

        try:
            state, error_code, reason = _process_job(job)
        except APIError as error:
            if error.code == "woocommerce_write_outcome_unknown":
                state, error_code, reason = "outcome_unknown", error.code, error.message
            elif error.code in PERMANENT_CONFIGURATION_ERRORS:
                state, error_code, reason = "blocked", error.code, error.message
            else:
                state, error_code, reason = "retry", error.code, error.message
        except Exception as error:
            logger.warning(
                "Biashara provider sync failed (job_hash=%s, error=%s)",
                hashlib.sha256(str(job.get("job_key") or "").encode("utf-8")).hexdigest()[:12],
                type(error).__name__,
            )
            state, error_code, reason = "retry", "provider_sync_internal_error", "The worker failed before a stable provider result was recorded."

        if state == "retry" and attempts >= MAX_ATTEMPTS:
            state = "dead_letter"
            error_code = error_code or "provider_sync_retry_exhausted"
        acknowledged = _finish_job(
            job,
            worker_id,
            token,
            state,
            result_status=state,
            error_code=error_code,
            reason=reason,
        )
        if not acknowledged:
            report["lease_lost"] += 1
            continue
        if state == "completed":
            report["completed"] += 1
        elif state == "retry":
            report["retried"] += 1
        elif state == "conflict":
            report["conflicts"] += 1
        elif state == "outcome_unknown":
            report["outcome_unknown"] += 1
        elif state == "skipped":
            report["skipped"] += 1
        elif state == "blocked":
            report["blocked"] += 1
        elif state == "dead_letter":
            report["dead_lettered"] += 1

    return report


def list_sync_jobs(user_id, status=None, connection_id=None, limit=50):
    _context, business_id = integration_service._business(user_id, "integration.view")
    try:
        limit = min(max(int(limit), 1), 100)
    except (TypeError, ValueError, OverflowError):
        limit = 50
    query = {"business_id": business_id}
    if status:
        normalized = str(status).strip().lower()
        if normalized not in {
            "pending", "processing", "retry", "completed", "conflict",
            "outcome_unknown", "skipped", "blocked", "dead_letter",
        }:
            raise APIError("Unknown provider sync job status.", 422, "invalid_provider_sync_status")
        query["status"] = normalized
    if connection_id:
        query["connection_id"] = str(connection_id)
    rows = collection(SYNC_JOBS_COLLECTION).find(query).sort("created_at", -1).limit(limit)
    return [_public_job(row) for row in rows]


def retry_sync_job(user_id, job_id):
    _context, business_id = integration_service._business(user_id, "integration.manage")
    jobs = collection(SYNC_JOBS_COLLECTION)
    current = jobs.find_one({"_id": _clean_id(job_id), "business_id": business_id})
    if not current:
        raise APIError("Provider sync job not found.", 404, "provider_sync_job_not_found")
    if current.get("status") not in {"retry", "blocked", "dead_letter"}:
        raise APIError(
            "Only retry, blocked or dead-letter jobs can be replayed here. Resolve remote conflicts or ambiguous outcomes through product mapping reconciliation.",
            409,
            "provider_sync_job_not_replayable",
        )
    now = now_utc()
    result = jobs.find_one_and_update(
        {
            "_id": current["_id"],
            "business_id": business_id,
            "status": current.get("status"),
        },
        {
            "$set": {
                "status": "pending",
                "attempt_count": 0,
                "next_attempt_at": None,
                "last_error_code": None,
                "last_result_reason": "Manual replay requested; re-check connection and current remote state.",
                "lease_owner": None,
                "lease_token": None,
                "lease_expires_at": None,
                "manual_replay_by_user_id": str(user_id),
                "manual_replay_at": now,
                "updated_at": now,
                "finished_at": None,
            },
            "$inc": {"manual_replay_count": 1},
        },
        return_document=ReturnDocument.AFTER,
    )
    if not result:
        raise APIError("Provider sync job changed while replaying. Reload and retry.", 409, "provider_sync_job_conflict")
    log_action(user_id, "biashara.provider_sync_job_replayed", "provider_sync_job", current["_id"], {
        "connection_id": current.get("connection_id"),
        "source_event_id": current.get("source_event_id"),
        "provider": current.get("provider"),
    })
    return _public_job(result)
