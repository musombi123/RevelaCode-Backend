# backend/services/audit_logger.py

import json
from datetime import datetime
from backend.db import get_db  # you already have db utilities

def log_domain_event(
    user_id,
    domain,
    query,
    status="success",
    metadata=None
):
    """
    Records every domain-level interaction.
    """

    db = get_db()
    entry = {
        "user_id": user_id,
        "domain": domain,
        "query": query[:500],  # truncate for safety
        "status": status,
        "metadata": metadata or {},
        "timestamp": datetime.utcnow().isoformat()
    }

    db.audit_logs.insert_one(entry)
