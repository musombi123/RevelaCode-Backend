"""Per-user, per-hub 30-day trials for the shared Jumuiya Revenue Engine.

Trials are entitlement records, not payment records. They use the existing
RevelaCode MongoDB database and the jumuiya_ collection namespace.
"""

from __future__ import annotations

from datetime import timedelta, timezone

from flask import jsonify, request
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.audit import log_action, now_utc
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.revenue import revenue_bp

TRIALS_COLLECTION = "jumuiya_revenue_trials"
TRIAL_DAYS = 30

# Each separately metered hub gets its own trial. Faith covers the RevelaCode
# Theology/Faith experience; Smart AI is separately metered from the hubs.
TRIAL_HUBS = {
    "shamba": "Shamba",
    "biashara": "Biashara",
    "elimu": "Elimu",
    "community": "Community",
    "smart_ai": "RevelaAI / Smart AI",
    "marketplace": "Marketplace",
    "faith": "Faith & Scripture",
}

_INDEXES_READY = False


def _trials():
    global _INDEXES_READY
    rows = collection(TRIALS_COLLECTION)
    if not _INDEXES_READY:
        rows.create_index(
            [("user_id", ASCENDING), ("hub", ASCENDING)],
            unique=True,
            name="uq_revenue_trial_user_hub",
        )
        rows.create_index(
            [("user_id", ASCENDING), ("ends_at", DESCENDING)],
            name="ix_revenue_trial_user_ends",
        )
        _INDEXES_READY = True
    return rows


def _as_utc(value):
    if value is None:
        return None
    # PyMongo commonly returns naive datetimes in UTC unless tz_aware is set.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _iso(value):
    normalized = _as_utc(value)
    return normalized.isoformat() if normalized else None


def _public_trial(row, now=None):
    now = _as_utc(now or now_utc())
    ends_at = _as_utc(row.get("ends_at"))
    started_at = _as_utc(row.get("started_at"))
    active = bool(ends_at and ends_at > now)
    return {
        "id": str(row.get("_id", "")),
        "hub": row.get("hub"),
        "hub_name": TRIAL_HUBS.get(row.get("hub"), row.get("hub")),
        "status": "active" if active else "expired",
        "trial_days": row.get("trial_days", TRIAL_DAYS),
        "started_at": _iso(started_at),
        "ends_at": _iso(ends_at),
        "days_remaining": max(0, (ends_at - now).days) if active else 0,
        "access": "trial" if active else "upgrade_required",
    }


def _error(message, status, code):
    return jsonify({"success": False, "error": message, "code": code}), status


@revenue_bp.get("/trials")
@require_authenticated
def list_my_hub_trials():
    """List the caller's own trial status for every supported hub."""
    user_id = current_user_id()
    now = now_utc()
    rows = list(_trials().find({"user_id": user_id}).sort("started_at", DESCENDING))
    by_hub = {row.get("hub"): row for row in rows}
    result = []
    for hub, name in TRIAL_HUBS.items():
        row = by_hub.get(hub)
        result.append(
            _public_trial(row, now) if row else {
                "hub": hub,
                "hub_name": name,
                "status": "not_started",
                "trial_days": TRIAL_DAYS,
                "started_at": None,
                "ends_at": None,
                "days_remaining": 0,
                "access": "start_trial",
            }
        )
    from backend.revenue.mpesa import checkout_is_production_configured
    checkout_enabled = checkout_is_production_configured()
    return jsonify({
        "success": True,
        "trial_days": TRIAL_DAYS,
        "trials": result,
        "billing_enabled": checkout_enabled,
        "checkout_enabled": checkout_enabled,
        "note": "Trials are tracked centrally. Paid access is activated only after the provider confirms payment.",
    }), 200


@revenue_bp.post("/trials/start")
@require_authenticated
def start_hub_trial():
    """Start a hub's one-time 30-day trial; repeated requests never reset it."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("A JSON request body is required.", 400, "invalid_json_body")
    extra = set(payload) - {"hub"}
    if extra:
        return _error("Unsupported fields: " + ", ".join(sorted(extra)), 400, "unsupported_fields")
    raw_hub = payload.get("hub")
    if not isinstance(raw_hub, str):
        return _error("A valid hub is required.", 400, "invalid_hub")
    hub = raw_hub.strip().lower()
    if hub not in TRIAL_HUBS:
        return _error("Unsupported hub. Choose a hub from the published trial catalogue.", 400, "unsupported_hub")

    user_id = current_user_id()
    rows = _trials()
    existing = rows.find_one({"user_id": user_id, "hub": hub})
    now = now_utc()
    if existing:
        trial = _public_trial(existing, now)
        if trial["status"] == "active":
            return jsonify({
                "success": True,
                "created": False,
                "trial": trial,
                "message": "Your trial is already active. Its end date has not been changed.",
            }), 200
        return _error(
            "This hub's free trial has already been used. Choose a plan to continue after trial access.",
            409,
            "trial_already_used",
        )

    document = {
        "user_id": user_id,
        "hub": hub,
        "trial_days": TRIAL_DAYS,
        "status": "active",
        "started_at": now,
        "ends_at": now + timedelta(days=TRIAL_DAYS),
        "created_at": now,
        "updated_at": now,
        "source": "self_service",
    }
    try:
        result = rows.insert_one(document)
        document["_id"] = result.inserted_id
    except DuplicateKeyError:
        # Another request/process may have won the unique-index race.
        existing = rows.find_one({"user_id": user_id, "hub": hub})
        if not existing:
            return _error("The trial could not be confirmed. Please retry.", 503, "trial_creation_conflict")
        trial = _public_trial(existing, now)
        if trial["status"] == "active":
            return jsonify({"success": True, "created": False, "trial": trial}), 200
        return _error("This hub's free trial has already been used.", 409, "trial_already_used")

    try:
        log_action(
            user_id=user_id,
            action="revenue.hub_trial_started",
            resource="revenue_trial",
            resource_id=str(document["_id"]),
            metadata={"hub": hub, "trial_days": TRIAL_DAYS},
        )
    except Exception:
        # The durable trial record must not be lost because an audit sink is
        # temporarily unavailable; the application logger can report this.
        from flask import current_app
        current_app.logger.exception("Trial started but audit event could not be written")

    return jsonify({
        "success": True,
        "created": True,
        "trial": _public_trial(document, now),
        "message": f"Your {TRIAL_DAYS}-day {TRIAL_HUBS[hub]} trial has started.",
    }), 201


@revenue_bp.get("/entitlements")
@require_authenticated
def get_my_hub_entitlements():
    """Resolve free, trial, or paid access using the central entitlement service."""
    hub = request.args.get("hub", "").strip().lower()
    if hub not in TRIAL_HUBS:
        return _error("A supported hub query parameter is required.", 400, "invalid_hub")
    feature = request.args.get("feature", "essential").strip().lower()
    from backend.revenue.subscriptions import resolve_entitlement
    try:
        entitlement = resolve_entitlement(current_user_id(), hub, feature)
    except ValueError as exc:
        return _error(str(exc), 400, "invalid_entitlement_request")
    return jsonify({
        **entitlement,
        "hub_name": TRIAL_HUBS[hub],
        "trial_days": TRIAL_DAYS,
    }), 200
