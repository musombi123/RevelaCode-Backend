"""Persistent platform IP blocking for defensive security operations.

Blocks exact globally-routable client IPs at the Flask request boundary.
Uses the existing authoritative RevelaCode MongoDB database; it does not
change host firewalls or external network ACLs.
"""
from __future__ import annotations

import ipaddress
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from flask import Blueprint, jsonify, request

security_bp = Blueprint("security_bp", __name__)
_INDEX_LOCK = threading.Lock()
_INDEX_READY = False

AUTH_FAILURE_PATHS = {
    "/api/auth/login",
    "/api/login",
    "/api/auth/mfa/login-verify",
}
AUTH_FAILURE_THRESHOLD = 10
AUTH_FAILURE_WINDOW_MINUTES = 10
AUTO_BLOCK_MINUTES = 30
MAX_MANUAL_BLOCK_MINUTES = 10080


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _collections():
    """Return collections from the exact Mongo database backing user accounts."""
    from backend import auth_gate as auth

    if not auth.MONGO_AVAILABLE or auth.users_col is None:
        raise RuntimeError("Persistent MongoDB is required for IP protection.")
    try:
        database = auth.users_col.database
        database.command("ping")
    except Exception as exc:
        raise RuntimeError("The authoritative user database is unavailable.") from exc
    global _INDEX_READY
    if not _INDEX_READY:
        with _INDEX_LOCK:
            if not _INDEX_READY:
                database["security_ip_blocks"].create_index([("ip", 1), ("active", 1)])
                database["security_ip_blocks"].create_index([("expires_at", 1)])
                database["security_ip_events"].create_index([("created_at", -1)])
                database["security_auth_failures"].create_index([("ip", 1), ("created_at", -1)])
                _INDEX_READY = True
    return database, auth


def _public_ip(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or "/" in raw or len(raw) > 64:
        raise ValueError("Enter one IPv4 or IPv6 address, not a network range.")
    try:
        parsed = ipaddress.ip_address(raw)
    except ValueError as exc:
        raise ValueError("The IP address is invalid.") from exc
    if not parsed.is_global:
        raise ValueError("Only public, globally routable IP addresses can be blocked.")
    return parsed.compressed


def _allowlisted(ip: str) -> bool:
    address = ipaddress.ip_address(ip)
    entries = [
        value.strip()
        for value in os.getenv("REVELACODE_IP_ALLOWLIST", "").split(",")
        if value.strip()
    ]
    for value in entries:
        try:
            if address in ipaddress.ip_network(value, strict=False):
                return True
        except ValueError:
            continue
    return False


def current_client_ip() -> str | None:
    """Use request.remote_addr after the app's trusted single-hop ProxyFix."""
    value = str(request.remote_addr or "").strip()
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError:
        return None


def _expires(record: dict) -> datetime | None:
    value = record.get("expires_at")
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return _now()
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return _now()


def find_active_block(ip: str | None) -> dict | None:
    if not ip:
        return None
    try:
        normalized = ipaddress.ip_address(ip).compressed
    except ValueError:
        return None
    try:
        database, _auth = _collections()
        record = database["security_ip_blocks"].find_one(
            {"ip": normalized, "active": True},
            sort=[("created_at", -1)],
        )
    except Exception:
        # Existing platform requests remain available during an IP-guard
        # database outage; administrative operations show an explicit 503.
        return None
    if not record:
        return None
    expiry = _expires(record)
    if expiry and expiry <= _now():
        try:
            database["security_ip_blocks"].update_one(
                {"_id": record["_id"]},
                {"$set": {"active": False, "status": "expired", "expired_at": _now()}},
            )
        except Exception:
            pass
        return None
    return record


def enforce_ip_block():
    """Flask before_request hook. Return a 403 for currently blocked IPs."""
    if request.method == "OPTIONS":
        return None
    if request.path in {"/", "/health", "/healthz", "/api/health", "/api/system/health"}:
        return None
    ip = current_client_ip()
    record = find_active_block(ip)
    if not record:
        return None
    expiry = _expires(record)
    seconds = max(1, int((expiry - _now()).total_seconds())) if expiry else 3600
    response = jsonify(
        success=False,
        code="ip_blocked",
        message="This source address is temporarily blocked by RevelaCode security controls.",
        retry_after_seconds=seconds,
        block_expires_at=expiry.isoformat() if expiry else None,
    )
    response.status_code = 403
    response.headers["Retry-After"] = str(seconds)
    response.headers["Cache-Control"] = "no-store"
    return response


def _audit(database, action: str, ip: str, actor: str, reason: str, source: str):
    database["security_ip_events"].insert_one({
        "event_id": uuid4().hex,
        "action": action,
        "ip": ip,
        "actor": str(actor or "unknown")[:128],
        "reason": str(reason or "")[:300],
        "source": source,
        "created_at": _now(),
    })


def block_ip(
    ip: str,
    *,
    actor: str,
    reason: str,
    duration_minutes: int,
    source: str = "manual",
    protect_current_ip: str | None = None,
) -> dict:
    normalized = _public_ip(ip)
    if _allowlisted(normalized):
        raise ValueError("This address is protected by the administrator IP allowlist.")
    if protect_current_ip:
        try:
            if ipaddress.ip_address(protect_current_ip) == ipaddress.ip_address(normalized):
                raise ValueError("You cannot block the address used by this administrator session.")
        except ValueError as exc:
            if str(exc).startswith("You cannot"):
                raise
    try:
        duration = int(duration_minutes)
    except (TypeError, ValueError) as exc:
        raise ValueError("Block duration must be a whole number of minutes.") from exc
    if duration < 5 or duration > MAX_MANUAL_BLOCK_MINUTES:
        raise ValueError("Block duration must be between 5 minutes and 7 days.")
    clean_reason = str(reason or "").strip()
    if len(clean_reason) < 8 or len(clean_reason) > 300:
        raise ValueError("Enter a reason between 8 and 300 characters.")

    database, _auth = _collections()
    created = _now()
    expires = created + timedelta(minutes=duration)
    record = {
        "block_id": uuid4().hex,
        "ip": normalized,
        "active": True,
        "status": "active",
        "reason": clean_reason,
        "source": source if source in {"manual", "auto_bruteforce"} else "manual",
        "created_by": str(actor or "unknown")[:128],
        "created_at": created,
        "expires_at": expires,
        "duration_minutes": duration,
    }
    database["security_ip_blocks"].update_one(
        {"ip": normalized, "active": True},
        {"$set": record},
        upsert=True,
    )
    _audit(database, "blocked", normalized, actor, clean_reason, record["source"])
    return {
        "ip": normalized,
        "status": "blocked",
        "reason": clean_reason,
        "source": record["source"],
        "created_by": record["created_by"],
        "created_at": created.isoformat(),
        "expires_at": expires.isoformat(),
        "duration_minutes": duration,
    }


def unblock_ip(ip: str, *, actor: str, reason: str = "Administrator released the block") -> dict:
    normalized = _public_ip(ip)
    database, _auth = _collections()
    now = _now()
    result = database["security_ip_blocks"].update_many(
        {"ip": normalized, "active": True},
        {"$set": {
            "active": False,
            "status": "unblocked",
            "unblocked_at": now,
            "unblocked_by": str(actor or "unknown")[:128],
        }},
    )
    if result.modified_count:
        _audit(database, "unblocked", normalized, actor, reason, "manual")
    return {"ip": normalized, "status": "unblocked", "records_released": int(result.modified_count)}


def list_active_blocks(limit: int = 100) -> list[dict]:
    database, _auth = _collections()
    now = _now()
    cursor = database["security_ip_blocks"].find({"active": True}).sort("created_at", -1).limit(max(1, min(int(limit), 250)))
    rows = []
    for record in cursor:
        expiry = _expires(record)
        if expiry and expiry <= now:
            database["security_ip_blocks"].update_one(
                {"_id": record["_id"]},
                {"$set": {"active": False, "status": "expired", "expired_at": now}},
            )
            continue
        created = record.get("created_at")
        rows.append({
            "ip": record.get("ip"),
            "reason": record.get("reason", ""),
            "source": record.get("source", "manual"),
            "created_by": record.get("created_by", ""),
            "created_at": created.isoformat() if isinstance(created, datetime) else created,
            "expires_at": expiry.isoformat() if expiry else None,
            "duration_minutes": record.get("duration_minutes"),
            "status": "active",
        })
    return rows


def protection_status() -> dict:
    try:
        database, _auth = _collections()
        active = database["security_ip_blocks"].count_documents({"active": True, "expires_at": {"$gt": _now()}})
        return {
            "status": "active",
            "enforcement": "platform_request_boundary",
            "storage": "mongodb",
            "persistent": True,
            "active_blocks": int(active),
            "automatic_blocking": True,
            "auto_block_threshold": AUTH_FAILURE_THRESHOLD,
            "auto_block_window_minutes": AUTH_FAILURE_WINDOW_MINUTES,
            "auto_block_duration_minutes": AUTO_BLOCK_MINUTES,
            "allowlist_configured": bool(os.getenv("REVELACODE_IP_ALLOWLIST", "").strip()),
        }
    except Exception:
        return {
            "status": "degraded",
            "enforcement": "platform_request_boundary",
            "storage": "unavailable",
            "persistent": False,
            "active_blocks": 0,
            "automatic_blocking": False,
            "allowlist_configured": bool(os.getenv("REVELACODE_IP_ALLOWLIST", "").strip()),
        }


def record_failed_authentication(ip: str | None, path: str, status_code: int) -> dict | None:
    """Persist failed login evidence and temporarily block repeated sources."""
    if status_code != 401 or path not in AUTH_FAILURE_PATHS or not ip:
        return None
    try:
        normalized = _public_ip(ip)
        if _allowlisted(normalized):
            return None
        database, _auth = _collections()
        now = _now()
        failures = database["security_auth_failures"]
        failures.insert_one({
            "ip": normalized,
            "path": path,
            "status_code": 401,
            "created_at": now,
        })
        since = now - timedelta(minutes=AUTH_FAILURE_WINDOW_MINUTES)
        count = failures.count_documents({
            "ip": normalized,
            "created_at": {"$gte": since},
        })
        if count < AUTH_FAILURE_THRESHOLD:
            return None
        # Avoid repeatedly creating the same active ban.
        existing = database["security_ip_blocks"].find_one({"ip": normalized, "active": True})
        if existing and (_expires(existing) is None or _expires(existing) > now):
            return None
        return block_ip(
            normalized,
            actor="system:auto-defense",
            reason=f"{count} failed authentication attempts within {AUTH_FAILURE_WINDOW_MINUTES} minutes.",
            duration_minutes=AUTO_BLOCK_MINUTES,
            source="auto_bruteforce",
        )
    except (ValueError, RuntimeError):
        return None


def _require_current_platform_admin():
    """Validate bearer identity and resolve the current admin role from MongoDB."""
    from backend import auth_gate as auth
    from bson import ObjectId

    authorization = (request.headers.get("Authorization") or "").strip()
    if not authorization.startswith("Bearer "):
        return None, (jsonify(success=False, code="authentication_required"), 401)
    try:
        claims = auth.jwt.decode(
            authorization[7:].strip(),
            auth.JWT_SECRET,
            algorithms=[auth.JWT_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
    except auth.jwt.ExpiredSignatureError:
        return None, (jsonify(success=False, code="token_expired"), 401)
    except auth.jwt.InvalidTokenError:
        return None, (jsonify(success=False, code="invalid_token"), 401)

    user_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
    if not user_id or not auth.MONGO_AVAILABLE or auth.users_col is None:
        return None, (jsonify(success=False, code="admin_verification_unavailable"), 503)
    try:
        projection = {
            "_id": 1, "id": 1, "user_id": 1, "role": 1, "roles": 1,
            "status": 1, "is_active": 1, "token_version": 1,
        }
        user = None
        if ObjectId.is_valid(user_id):
            user = auth.users_col.find_one({"_id": ObjectId(user_id)}, projection)
        if user is None:
            user = auth.users_col.find_one({"$or": [{"id": user_id}, {"user_id": user_id}]}, projection)
    except Exception:
        return None, (jsonify(success=False, code="admin_verification_unavailable"), 503)
    if not user:
        return None, (jsonify(success=False, code="user_not_found"), 403)
    canonical_id = str(user.get("_id") or user.get("id") or user.get("user_id") or "")
    if canonical_id != user_id:
        return None, (jsonify(success=False, code="user_identity_mismatch"), 403)
    if int(claims.get("token_version") or 0) != int(user.get("token_version") or 0):
        return None, (jsonify(success=False, code="session_revoked"), 401)
    status = str(user.get("status") or "active").casefold()
    if user.get("is_active") is False or status not in {"active", "verified", "approved"}:
        return None, (jsonify(success=False, code="account_inactive"), 403)
    raw_roles = user.get("roles") if isinstance(user.get("roles"), (list, tuple, set)) else []
    roles = {str(role).strip().casefold() for role in raw_roles if str(role).strip()}
    singular = str(user.get("role") or "").strip().casefold()
    if singular:
        roles.add(singular)
    if auth.is_configured_super_admin(canonical_id, user):
        roles.add("super_admin")
    if not roles.intersection(auth.PLATFORM_ADMIN_ROLES):
        return None, (jsonify(success=False, code="admin_required"), 403)
    return canonical_id, None


@security_bp.get("/api/admin/security/ip-blocks")
def get_ip_blocks():
    actor, error = _require_current_platform_admin()
    if error:
        return error
    try:
        return jsonify(
            success=True,
            protection=protection_status(),
            blocks=list_active_blocks(),
            current_ip=current_client_ip(),
        )
    except RuntimeError:
        return jsonify(success=False, code="ip_protection_storage_unavailable"), 503


@security_bp.post("/api/admin/security/ip-blocks")
def create_ip_block():
    actor, error = _require_current_platform_admin()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    try:
        result = block_ip(
            payload.get("ip"),
            actor=actor,
            reason=payload.get("reason", ""),
            duration_minutes=payload.get("duration_minutes", 60),
            source="manual",
            protect_current_ip=current_client_ip(),
        )
        return jsonify(success=True, block=result, protection=protection_status()), 201
    except ValueError as exc:
        return jsonify(success=False, code="invalid_ip_block_request", message=str(exc)), 400
    except RuntimeError:
        return jsonify(success=False, code="ip_protection_storage_unavailable"), 503


@security_bp.post("/api/admin/security/ip-blocks/unblock")
def release_ip_block():
    actor, error = _require_current_platform_admin()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    try:
        result = unblock_ip(
            payload.get("ip"),
            actor=actor,
            reason=str(payload.get("reason") or "Administrator released the block"),
        )
        return jsonify(success=True, result=result, protection=protection_status())
    except ValueError as exc:
        return jsonify(success=False, code="invalid_ip_unblock_request", message=str(exc)), 400
    except RuntimeError:
        return jsonify(success=False, code="ip_protection_storage_unavailable"), 503
