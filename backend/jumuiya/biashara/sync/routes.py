"""Authenticated Biashara Sync Centre API.

These routes expose durable event state and safe operator controls. They do
not simulate a provider connection or claim an event was delivered.
"""

from flask import Blueprint, request

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import ok
from backend.jumuiya.biashara import services
from backend.jumuiya.biashara.tenancy.service import require_business_permission
from backend.jumuiya.biashara.sync.outbox import (
    get_outbox_summary,
    list_outbox_events,
    repair_outbox_manifests,
    replay_dead_letter_event,
)


biashara_sync_bp = Blueprint("jumuiya_biashara_sync", __name__)


def _business():
    return services._require_business(current_user_id())


@biashara_sync_bp.get("/status")
@require_authenticated
@require_business_permission("sync.view")
def sync_status():
    business = _business()
    summary = get_outbox_summary(business["id"])
    return ok(summary, "Biashara synchronization status loaded.")


@biashara_sync_bp.get("/events")
@require_authenticated
@require_business_permission("sync.view")
def sync_events():
    business = _business()
    state = request.args.get("state", "")
    limit = request.args.get("limit", 50)
    events = list_outbox_events(business["id"], state=state, limit=limit)
    return ok(
        events,
        "Biashara sync events loaded.",
        meta={"count": len(events), "limit": min(max(int(limit) if str(limit).isdigit() else 50, 1), 100)},
    )


@biashara_sync_bp.post("/events/<event_id>/retry")
@require_authenticated
@require_business_permission("sync.manage")
def retry_sync_event(event_id):
    user_id = current_user_id()
    business = services._require_business(user_id)
    event = replay_dead_letter_event(
        business_id=business["id"],
        event_id=event_id,
        actor_user_id=user_id,
    )
    log_action(user_id, "biashara.sync_event_replayed", "sync_event", event_id)
    return ok(
        event,
        "Sync event returned to the queue. Delivery is not confirmed until a provider adapter succeeds.",
    )


@biashara_sync_bp.post("/repair")
@require_authenticated
@require_business_permission("sync.manage")
def repair_pending_sync_manifests():
    user_id = current_user_id()
    business = services._require_business(user_id)
    inventory_report = services.repair_pending_inventory_movements(user_id, limit=100)
    outbox_report = repair_outbox_manifests(business_id=business["id"], limit=100)
    report = {
        "inventory_recovery": inventory_report,
        "outbox_recovery": outbox_report,
    }
    log_action(
        user_id,
        "biashara.sync_manifest_repair_requested",
        "business",
        business["id"],
    )
    return ok(
        report,
        "Pending inventory and sync manifests were checked. Provider delivery remains a separate worker outcome.",
    )
