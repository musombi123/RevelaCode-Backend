from __future__ import annotations

from datetime import datetime, timezone
from jumuiya.core.database import collection

def log_action(user_id, action, resource=None, resource_id=None, metadata=None):
    doc = {
        "user_id": str(user_id) if user_id is not None else None,
        "action": str(action),
        "resource": resource,
        "resource_id": str(resource_id) if resource_id is not None else None,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc),
    }
    collection("jumuiya_audit_logs").insert_one(doc)
    return True
