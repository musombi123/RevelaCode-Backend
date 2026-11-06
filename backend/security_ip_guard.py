"""Platform-wide defensive IP protection for the RevelaCode Flask API.

Blocks are enforced before route handlers at the existing Flask application
boundary. Records are stored in the existing RevelaCode Mongo database.
"""
from __future__ import annotations

import ipaddress
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.db import get_db

logger = logging.getLogger("revelacode.security.ip_guard")

AUTO_BLOCK_THRESHOLD = 50
AUTO_BLOCK_WINDOW_MINUTES = 5
AUTO_BLOCK_DURATION_MINUTES = 30


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def client_ip_from_request(req) -> str | None:
    """Use Cloudflare's single client-IP header on Render; never trust XFF."""
    raw = str(req.headers.get("CF-Connecting-IP") or "").strip()
    if not raw:
        return None
    try:
        address = ipaddress.ip_address(raw)
        return address.compressed if address.is_global else None
    except ValueError:
        return None


def parse_public_ip(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or len(raw) > 64 or "/" in raw:
        raise ValueError("Provide one exact public IPv4 or IPv6 address.")
    try:
        address = ipaddress.ip_address(raw)
    except ValueError as exc:
        raise ValueError("The IP address is not valid.") from exc
    if not address.is_global:
        raise ValueError("Only globally routable public IP addresses can be blocked.")
    return address.compressed


def admin_allowlist():
    raw = (
        os.getenv("SCI_CORE_IP_ALLOWLIST", "")
        or os.getenv("REVELACODE_IP_ALLOWLIST", "")
    )
    values = [part.strip() for part in raw.split(",") if part.strip()]
    networks = []
    for value in values:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            logger.warning("Ignoring malformed IP allowlist entry")
    return networks


def is_allowlisted(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return any(address in network for network in admin_allowlist())


def ensure_indexes() -> None:
    db = get_db()
    db["security_ip_blocks"].create_index([("ip", 1), ("active", 1)])
    db["security_ip_blocks"].create_index([("expires_at", 1)])
    db["security_ip_events"].create_index([("created_at", -1)])
    db["security_auth_failures"].create_index([("ip", 1), ("created_at", -1)])
    db["security_auth_failures"].create_index(
        [("created_at", 1)], expireAfterSeconds=2592000
    )


def _serialize_block(row: dict) -> dict:
    def iso(value):
        return value.isoformat() if isinstance(value, datetime) else value

    return {
        "ip": str(row.get("ip") or ""),
        "reason": str(row.get("reason") or "")[:300],
        "source": str(row.get("source") or "manual"),
        "created_by": str(row.get("created_by") or "unknown"),
        "created_at": iso(row.get("created_at")),
        "expires_at": iso(row.get("expires_at")),
        "duration_minutes": row.get("duration_minutes"),
        "status": "active",
    }


def active_blocks(limit: int = 100) -> list[dict]:
    db = get_db()
    now = utcnow()
    rows = db["security_ip_blocks"].find({"active": True}).sort(
        "created_at", -1
    ).limit(max(1, min(int(limit), 250)))
    result = []
    for row in rows:
        expires = row.get("expires_at")
        if isinstance(expires, datetime):
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= now:
                db["security_ip_blocks"].update_one(
                    {"_id": row["_id"]},
                    {"$set": {
                        "active": False,
                        "status": "expired",
                        "expired_at": now,
                    }},
                )
                continue
        result.append(_serialize_block(row))
    return result


def ip_is_blocked(ip: str | None) -> dict | None:
    if not ip:
        return None
    try:
        normalized = parse_public_ip(ip)
        if is_allowlisted(normalized):
            return None
        db = get_db()
        row = db["security_ip_blocks"].find_one({
            "ip": normalized,
            "active": True,
        })
        if not row:
            return None
        expires = row.get("expires_at")
        if isinstance(expires, datetime):
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= utcnow():
                db["security_ip_blocks"].update_one(
                    {"_id": row["_id"]},
                    {"$set": {
                        "active": False,
                        "status": "expired",
                        "expired_at": utcnow(),
                    }},
                )
                return None
        return _serialize_block(row)
    except Exception as exc:
        # A database outage must not lock out all users. Admin APIs report the
        # degraded state and never claim a block was created without a DB write.
        logger.warning("IP block lookup unavailable | error_type=%s", type(exc).__name__)
        return None


def block_ip(
    ip: Any,
    *,
    actor: str,
    reason: str,
    duration_minutes: Any,
    current_ip: str | None,
    source: str = "manual",
) -> dict:
    normalized = parse_public_ip(ip)
    if is_allowlisted(normalized):
        raise ValueError("This address is protected by the administrator IP allowlist.")
    if not current_ip:
        raise RuntimeError(
            "The administrator public IP could not be verified. Confirm the trusted Cloudflare ingress header."
        )
    try:
        current = ipaddress.ip_address(current_ip)
    except ValueError as exc:
        raise RuntimeError("The administrator public IP could not be verified.") from exc
    if current == ipaddress.ip_address(normalized):
        raise ValueError("You cannot block the IP address used by this administrator session.")

    try:
        duration = int(duration_minutes)
    except (TypeError, ValueError) as exc:
        raise ValueError("Block duration must be an integer number of minutes.") from exc
    if duration < 5 or duration > 10080:
        raise ValueError("Block duration must be between 5 minutes and 7 days.")

    normalized_reason = str(reason or "").strip()
    if len(normalized_reason) < 8 or len(normalized_reason) > 300:
        raise ValueError("Enter a reason between 8 and 300 characters.")

    db = get_db()
    now = utcnow()
    expires = now + timedelta(minutes=duration)
    record = {
        "ip": normalized,
        "active": True,
        "status": "active",
        "reason": normalized_reason,
        "source": source if source in {"manual", "auto_bruteforce"} else "manual",
        "created_by": str(actor or "unknown")[:128],
        "created_at": now,
        "expires_at": expires,
        "duration_minutes": duration,
    }
    db["security_ip_blocks"].update_one(
        {"ip": normalized, "active": True},
        {"$set": record},
        upsert=True,
    )
    db["security_ip_events"].insert_one({
        "action": "blocked",
        "ip": normalized,
        "actor": record["created_by"],
        "reason": normalized_reason,
        "source": record["source"],
        "created_at": now,
    })
    return _serialize_block(record)


def unblock_ip(ip: Any, *, actor: str, reason: str) -> dict:
    normalized = parse_public_ip(ip)
    normalized_reason = str(reason or "").strip()
    if len(normalized_reason) < 8 or len(normalized_reason) > 300:
        raise ValueError("Enter an unblock reason between 8 and 300 characters.")
    db = get_db()
    now = utcnow()
    result = db["security_ip_blocks"].update_many(
        {"ip": normalized, "active": True},
        {"$set": {
            "active": False,
            "status": "unblocked",
            "unblocked_at": now,
            "unblocked_by": str(actor or "unknown")[:128],
        }},
    )
    if result.modified_count:
        db["security_ip_events"].insert_one({
            "action": "unblocked",
            "ip": normalized,
            "actor": str(actor or "unknown")[:128],
            "reason": normalized_reason,
            "source": "manual",
            "created_at": now,
        })
    return {
        "ip": normalized,
        "status": "unblocked",
        "records_released": int(result.modified_count),
    }


def recent_events(limit: int = 50) -> list[dict]:
    db = get_db()
    rows = db["security_ip_events"].find({}).sort(
        "created_at", -1
    ).limit(max(1, min(int(limit), 100)))
    return [{
        "action": str(row.get("action") or ""),
        "ip": str(row.get("ip") or ""),
        "actor": str(row.get("actor") or ""),
        "reason": str(row.get("reason") or "")[:300],
        "source": str(row.get("source") or ""),
        "created_at": row.get("created_at").isoformat()
        if isinstance(row.get("created_at"), datetime) else row.get("created_at"),
    } for row in rows]


def recent_auth_failures(limit: int = 50) -> list[dict]:
    db = get_db()
    rows = db["security_auth_failures"].find({}).sort(
        "created_at", -1
    ).limit(max(1, min(int(limit), 100)))
    return [{
        "ip": str(row.get("ip") or ""),
        "path": str(row.get("path") or "")[:180],
        "created_at": row.get("created_at").isoformat()
        if isinstance(row.get("created_at"), datetime) else row.get("created_at"),
    } for row in rows]


def protection_snapshot(current_ip: str | None) -> dict:
    db = get_db()
    ensure_indexes()
    blocks = active_blocks(100)
    return {
        "persistent": True,
        "status": "active",
        "enforcement": "platform_request_boundary",
        "storage": "mongodb",
        "active_blocks": len(blocks),
        "automatic_blocking": bool(admin_allowlist()),
        "auto_block_requires_allowlist": True,
        "auto_block_threshold": AUTO_BLOCK_THRESHOLD,
        "auto_block_window_minutes": AUTO_BLOCK_WINDOW_MINUTES,
        "auto_block_duration_minutes": AUTO_BLOCK_DURATION_MINUTES,
        "allowlist_configured": bool(admin_allowlist()),
        "blocks": blocks,
        "recent_events": recent_events(50),
        "recent_auth_failures": recent_auth_failures(50),
        "current_ip": current_ip or "",
    }


def record_failed_login(ip: str | None, path: str) -> None:
    if not ip or path not in {"/api/login", "/api/auth/login"}:
        return
    if not admin_allowlist():
        return
    try:
        normalized = parse_public_ip(ip)
        if is_allowlisted(normalized):
            return
        db = get_db()
        now = utcnow()
        db["security_auth_failures"].insert_one({
            "ip": normalized,
            "path": path,
            "created_at": now,
        })
        attempts = db["security_auth_failures"].count_documents({
            "ip": normalized,
            "created_at": {"$gte": now - timedelta(minutes=AUTO_BLOCK_WINDOW_MINUTES)},
        })
        if attempts >= AUTO_BLOCK_THRESHOLD and not ip_is_blocked(normalized):
            block_ip(
                normalized,
                actor="revelacode-auto-defence",
                reason=f"{attempts} invalid login responses within {AUTO_BLOCK_WINDOW_MINUTES} minutes.",
                duration_minutes=AUTO_BLOCK_DURATION_MINUTES,
                current_ip="8.8.8.8",
                source="auto_bruteforce",
            )
    except Exception as exc:
        logger.warning("Failed-login signal could not be persisted | error_type=%s", type(exc).__name__)
