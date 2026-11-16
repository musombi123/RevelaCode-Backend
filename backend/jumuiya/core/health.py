"""Shared read-only dependency checks for Jumuiya hub health endpoints."""
from __future__ import annotations

from datetime import datetime, timezone


def database_health() -> dict:
    """Confirm MongoDB responds and the shared application database is readable.

    This performs no writes and never returns connection strings or database data.
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        from backend.db import get_db
        database = get_db()
        if database is None:
            raise RuntimeError("database_unavailable")
        database.command("ping")
        database["users"].find_one({}, {"_id": 1})
        return {
            "status": "online",
            "mongo_connected": True,
            "evidence": "mongodb_ping_and_read_access_confirmed",
            "checked_at": checked_at,
        }
    except Exception:
        return {
            "status": "degraded",
            "mongo_connected": False,
            "evidence": "mongodb_ping_or_read_access_failed",
            "checked_at": checked_at,
        }