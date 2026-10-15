"""Safe, rerunnable Biashara owner-membership migration.

Existing child records already use business_id in the current data model.
This migration only creates missing owner memberships; it never guesses which
business owns an orphaned record and never rewrites sales, orders or stock.
"""
from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.database import collection
from backend.jumuiya.biashara.tenancy.service import (
    BUSINESSES_COLLECTION,
    MEMBERSHIPS_COLLECTION,
    _permissions,
)


OWNER_MEMBERSHIP_SOURCE = "migration.owner_membership_v1"
CHILD_COLLECTIONS = (
    "jumuiya_products",
    "jumuiya_customers",
    "jumuiya_orders",
    "jumuiya_sales",
    "jumuiya_expenses",
    "jumuiya_inventory_movements",
    "jumuiya_invoices",
    "jumuiya_payments",
)
DEFAULT_LIMIT = 500


def now_utc():
    return datetime.now(timezone.utc)


def _safe_business_id(document):
    value = document.get("_id")
    return str(value) if value is not None else ""


def _business_lookup_id(value):
    """Parse an ObjectId only when valid; never let malformed legacy IDs abort a report."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return ObjectId(text)
    except (InvalidId, TypeError):
        return text


def run_owner_membership_migration(dry_run=True, limit=DEFAULT_LIMIT):
    """Preview or idempotently seed owner memberships and report unresolved records."""
    if not isinstance(dry_run, bool):
        raise ValueError("dry_run must be a boolean.")
    try:
        limit = min(max(int(limit), 1), 5000)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT

    businesses_cursor = collection(BUSINESSES_COLLECTION).find({}).sort("created_at", 1).limit(limit + 1)
    sampled_businesses = list(businesses_cursor)
    truncated = len(sampled_businesses) > limit
    businesses = sampled_businesses[:limit]
    business_ids = {_safe_business_id(item) for item in businesses if _safe_business_id(item)}
    memberships = collection(MEMBERSHIPS_COLLECTION)

    report = {
        "dry_run": dry_run,
        "limit": limit,
        "businesses_inspected": len(businesses),
        "business_scan_truncated": truncated,
        "owner_memberships_existing": 0,
        "owner_memberships_would_create": 0,
        "owner_memberships_created": 0,
        "owner_memberships_repaired": 0,
        "businesses_missing_owner": [],
        "businesses_missing_stable_id": [],
        "membership_write_conflicts": 0,
        "child_records": {},
        "rollback_plan": {
            "method": "Remove only memberships whose source is migration.owner_membership_v1, after rechecking that the user is still the business owner and there are no dependent access decisions.",
            "automatic_rollback_performed": False,
        },
        "notes": [
            "No business, product, customer, order, sale, expense, payment or inventory record is deleted or reassigned.",
            "Child records with missing/unknown business_id are reported, never assigned by guessing.",
            "The report is limited to the configured scan bound; repeat with a larger limit for a broader audit.",
        ],
    }

    for business in businesses:
        business_id = _safe_business_id(business)
        owner_id = str(business.get("owner_user_id") or "").strip()
        if not business_id:
            report["businesses_missing_stable_id"].append({"name": str(business.get("name") or "")[:120]})
            continue
        if not owner_id:
            report["businesses_missing_owner"].append({
                "business_id": business_id,
                "name": str(business.get("name") or "")[:120],
            })
            continue

        query = {"business_id": business_id, "user_id": owner_id}
        existing = memberships.find_one(query)
        if existing and existing.get("role") == "owner" and existing.get("status") == "active":
            report["owner_memberships_existing"] += 1
            continue
        if existing:
            if dry_run:
                report["owner_memberships_repaired"] += 1
            else:
                previous_state = {
                    "role": existing.get("role"),
                    "status": existing.get("status"),
                    "permissions_snapshot": existing.get("permissions_snapshot"),
                    "source": existing.get("source"),
                    "revoked_at": existing.get("revoked_at"),
                }
                memberships.update_one(
                    {"_id": existing["_id"], "business_id": business_id, "user_id": owner_id},
                    {"$set": {
                        "role": "owner",
                        "status": "active",
                        "permissions_snapshot": _permissions("owner"),
                        "updated_at": now_utc(),
                        "revoked_at": None,
                        "migration_previous_state": previous_state,
                        "source": OWNER_MEMBERSHIP_SOURCE,
                    }},
                )
                report["owner_memberships_repaired"] += 1
            continue

        report["owner_memberships_would_create"] += 1
        if dry_run:
            continue

        now = now_utc()
        document = {
            "_id": ObjectId(),
            "business_id": business_id,
            "user_id": owner_id,
            "role": "owner",
            "status": "active",
            "granted_by_user_id": owner_id,
            "permissions_snapshot": _permissions("owner"),
            "created_at": now,
            "updated_at": now,
            "joined_at": now,
            "revoked_at": None,
            "source": OWNER_MEMBERSHIP_SOURCE,
        }
        try:
            memberships.insert_one(document)
            report["owner_memberships_created"] += 1
        except DuplicateKeyError:
            # Concurrent runs are expected. If the winning row is already a
            # valid owner relationship, leave its origin untouched so a future
            # rollback cannot remove a normal application membership.
            prior = memberships.find_one(query)
            if prior and prior.get("role") == "owner" and prior.get("status") == "active":
                report["owner_memberships_existing"] += 1
            elif prior:
                previous_state = {
                    "role": prior.get("role"),
                    "status": prior.get("status"),
                    "permissions_snapshot": prior.get("permissions_snapshot"),
                    "source": prior.get("source"),
                    "revoked_at": prior.get("revoked_at"),
                }
                memberships.update_one(
                    {"_id": prior["_id"], "business_id": business_id, "user_id": owner_id},
                    {"$set": {
                        "role": "owner",
                        "status": "active",
                        "permissions_snapshot": _permissions("owner"),
                        "updated_at": now_utc(),
                        "revoked_at": None,
                        "migration_previous_state": previous_state,
                        "source": OWNER_MEMBERSHIP_SOURCE,
                    }},
                )
                report["owner_memberships_repaired"] += 1
            else:
                report["membership_write_conflicts"] += 1

    for child_collection in CHILD_COLLECTIONS:
        missing = 0
        unknown = 0
        scanned = 0
        cursor = collection(child_collection).find({}, {"business_id": 1}).limit(limit + 1)
        docs = list(cursor)
        child_truncated = len(docs) > limit
        for document in docs[:limit]:
            scanned += 1
            business_id = str(document.get("business_id") or "").strip()
            if not business_id:
                missing += 1
            elif not truncated and business_id not in business_ids:
                unknown += 1
        report["child_records"][child_collection] = {
            "records_scanned": scanned,
            "missing_business_id": missing,
            "unknown_business_id": unknown if not truncated else None,
            "scan_truncated": child_truncated,
            "unknown_check_incomplete_because_business_scan_truncated": truncated,
        }
    return report


def plan_owner_membership_rollback(limit=DEFAULT_LIMIT):
    """Report reversible membership changes; never delete or demote by itself."""
    try:
        limit = min(max(int(limit), 1), 5000)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    memberships = collection(MEMBERSHIPS_COLLECTION)
    businesses = collection(BUSINESSES_COLLECTION)
    candidates = list(
        memberships.find({"source": OWNER_MEMBERSHIP_SOURCE}).limit(limit + 1)
    )
    truncated = len(candidates) > limit
    actions = []
    skipped = []
    for member in candidates[:limit]:
        business_id = str(member.get("business_id") or "")
        user_id = str(member.get("user_id") or "")
        business_lookup_id = _business_lookup_id(business_id)
        business = businesses.find_one({"_id": business_lookup_id}) if business_lookup_id is not None else None
        if not business or str(business.get("owner_user_id") or "") != user_id:
            skipped.append({
                "membership_id": str(member.get("_id") or ""),
                "business_id": business_id,
                "reason": "owner_relationship_changed_or_business_missing",
            })
            continue
        previous = member.get("migration_previous_state")
        actions.append({
            "membership_id": str(member.get("_id") or ""),
            "business_id": business_id,
            "user_id": user_id,
            "action": "restore_previous_state" if isinstance(previous, dict) else "remove_migration_created_membership",
        })
    return {
        "automatic_rollback_performed": False,
        "memberships_inspected": min(len(candidates), limit),
        "scan_truncated": truncated,
        "rollback_candidates": actions,
        "skipped": skipped,
        "warning": "Review every candidate before executing rollback. Never remove a membership that was reused for a later staff/team assignment.",
    }
