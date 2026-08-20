# backend/jumuiya/core/audit.py

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.jumuiya.core.database import collection


logger = logging.getLogger("jumuiya.audit")


# =========================================================
# TIME
# =========================================================

def now_utc():
    return datetime.now(timezone.utc)


# =========================================================
# AUDIT LOGGER
# =========================================================

def log_action(
    user_id,
    action,
    resource=None,
    resource_id=None,
    metadata=None,
):
    """
    Record an action performed inside Jumuiya.

    Shared by:

        Biashara
        Shamba
        Elimu
        Marketplace
        Wallet
        Community
        Notifications
        Administration

    Audit failures must never break the main business
    operation.
    """

    document = {
        "user_id": (
            str(user_id)
            if user_id is not None
            else None
        ),

        "action": str(action),

        "resource": (
            str(resource)
            if resource is not None
            else None
        ),

        "resource_id": (
            str(resource_id)
            if resource_id is not None
            else None
        ),

        "metadata": (
            metadata
            if isinstance(metadata, dict)
            else {}
        ),

        "created_at": now_utc(),
    }

    try:
        result = collection(
            "jumuiya_audit_logs"
        ).insert_one(document)

        return bool(result.inserted_id)

    except Exception:
        logger.exception(
            "Jumuiya audit logging failed | "
            "user_id=%s | action=%s | resource=%s | resource_id=%s",
            user_id,
            action,
            resource,
            resource_id,
        )

        # Never allow audit failure to break
        # the actual business operation.
        return False