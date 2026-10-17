"""Lease-based recovery worker for internal Biashara automation dispatch.

This worker processes internal rules into persisted tasks/run records only.
It never marks provider sync events as delivered and does not send messages,
move money, issue purchases, publish websites or modify payment verification.
"""
from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.biashara.sync.outbox import OUTBOX_COLLECTION, _public_event


logger = logging.getLogger("jumuiya.biashara.automation.worker")

DEFAULT_BATCH_LIMIT = 25
MAX_BATCH_LIMIT = 100
DEFAULT_LEASE_SECONDS = 90
MAX_LEASE_SECONDS = 600
MAX_DISPATCH_ATTEMPTS = 8


def now_utc():
    return datetime.now(timezone.utc)


def _worker_id(value):
    text = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}", text):
        raise APIError("worker_id must be 3–128 safe characters.", 422, "invalid_automation_worker")
    return text


def _bounded(value, default, maximum, minimum=1):
    try:
        return min(max(int(value), minimum), maximum)
    except (TypeError, ValueError, OverflowError):
        return default


def _claim_query(business_id=None):
    now = now_utc()
    lease_expired_or_free = {
        "$or": [
            {"automation_dispatch_lease_expires_at": {"$exists": False}},
            {"automation_dispatch_lease_expires_at": None},
            {"automation_dispatch_lease_expires_at": {"$lte": now}},
        ]
    }
    query = {
        "$or": [
            {
                "automation_dispatch_status": {"$in": ["pending", "retry"]},
                **lease_expired_or_free,
            },
            {
                "automation_dispatch_status": {"$exists": False},
                **lease_expired_or_free,
            },
            {
                "automation_dispatch_status": "processing",
                "automation_dispatch_lease_expires_at": {"$lte": now},
            },
        ]
    }
    if business_id is not None:
        query["business_id"] = str(business_id)
    return query


def _claim_event(worker_id, business_id=None, lease_seconds=DEFAULT_LEASE_SECONDS):
    """Atomically claim one automation dispatch record, reclaiming expired leases."""
    events = collection(OUTBOX_COLLECTION)
    now = now_utc()
    token = secrets.token_urlsafe(32)
    query = _claim_query(business_id=business_id)
    document = events.find_one_and_update(
        query,
        {
            "$set": {
                "automation_dispatch_status": "processing",
                "automation_dispatch_lease_owner": worker_id,
                "automation_dispatch_lease_token": token,
                "automation_dispatch_lease_expires_at": now + timedelta(seconds=lease_seconds),
                "automation_last_error_code": None,
                "updated_at": now,
            },
            "$inc": {"automation_dispatch_attempt_count": 1},
        },
        sort=[("created_at", 1)],
        return_document=ReturnDocument.AFTER,
    )
    if not document:
        return None
    return document


def _finish_claim(document, worker_id, lease_token, state, error_code=None, run_count=0):
    """A worker may acknowledge only while it still owns an unexpired lease."""
    now = now_utc()
    events = collection(OUTBOX_COLLECTION)
    result = events.update_one(
        {
            "business_id": str(document.get("business_id") or ""),
            "event_id": str(document.get("event_id") or ""),
            "automation_dispatch_status": "processing",
            "automation_dispatch_lease_owner": worker_id,
            "automation_dispatch_lease_token": lease_token,
            "automation_dispatch_lease_expires_at": {"$gt": now},
        },
        {
            "$set": {
                "automation_dispatch_status": state,
                "automation_last_dispatch_at": now,
                "automation_last_error_code": error_code,
                "automation_last_run_count": int(run_count or 0),
                "automation_dispatch_lease_owner": None,
                "automation_dispatch_lease_token": None,
                "automation_dispatch_lease_expires_at": None,
                "updated_at": now,
            }
        },
    )
    return bool(getattr(result, "matched_count", 0))


def run_dispatch_batch(worker_id, limit=DEFAULT_BATCH_LIMIT, lease_seconds=DEFAULT_LEASE_SECONDS, business_id=None):
    """Dispatch a bounded batch of persisted events to internal automation rules.

    Delivery is at-least-once. The automation service's stable run/task keys
    make business effects idempotent. The main provider outbox state remains
    independent; this function never sets it to delivered.
    """
    worker_id = _worker_id(worker_id)
    limit = _bounded(limit, DEFAULT_BATCH_LIMIT, MAX_BATCH_LIMIT)
    lease_seconds = _bounded(lease_seconds, DEFAULT_LEASE_SECONDS, MAX_LEASE_SECONDS)
    if business_id is not None and not str(business_id).strip():
        raise APIError("business_id must not be blank.", 422, "invalid_automation_worker")

    report = {
        "worker_id": worker_id,
        "claimed": 0,
        "processed": 0,
        "retried": 0,
        "dead_lettered": 0,
        "lease_lost": 0,
        "no_work": False,
        "provider_delivery_attempted": False,
    }

    for _ in range(limit):
        event = _claim_event(worker_id, business_id=business_id, lease_seconds=lease_seconds)
        if event is None:
            report["no_work"] = report["claimed"] == 0
            break
        report["claimed"] += 1
        token = str(event.get("automation_dispatch_lease_token") or "")
        attempts = int(event.get("automation_dispatch_attempt_count", 0) or 0)

        # Legacy/repeated inline failures are bounded too. Manual replay can
        # deliberately reset the counter after an operator investigates.
        if attempts > MAX_DISPATCH_ATTEMPTS:
            acknowledged = _finish_claim(
                event, worker_id, token, "dead_letter",
                error_code="automation_retry_exhausted",
                run_count=0,
            )
            if acknowledged:
                report["dead_lettered"] += 1
            else:
                report["lease_lost"] += 1
            continue

        try:
            from backend.jumuiya.biashara.automation.services import process_event_for_automations
            result = process_event_for_automations(_public_event(event, include_payload=True))
            processed = bool(result.get("processed"))
            error_code = result.get("error_code")
            run_count = int(result.get("created_runs", 0) or 0)
        except Exception as error:
            # Do not log event payloads, customer content or provider secrets.
            logger.warning(
                "Biashara automation worker deferred event (event_hash=%s, error=%s)",
                secrets.token_hex(6),
                type(error).__name__,
            )
            processed = False
            error_code = "automation_dispatch_failed"
            run_count = 0

        if processed:
            state = "processed"
        elif attempts >= MAX_DISPATCH_ATTEMPTS:
            state = "dead_letter"
            error_code = error_code or "automation_retry_exhausted"
        else:
            state = "retry"
            error_code = error_code or "automation_dispatch_failed"

        acknowledged = _finish_claim(
            event,
            worker_id,
            token,
            state,
            error_code=error_code,
            run_count=run_count,
        )
        if not acknowledged:
            report["lease_lost"] += 1
            continue
        if state == "processed":
            report["processed"] += 1
        elif state == "dead_letter":
            report["dead_lettered"] += 1
        else:
            report["retried"] += 1

    return report
