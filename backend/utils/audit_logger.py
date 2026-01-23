from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def log_admin_action(db, action, resource, actor, metadata=None):
    """
    Logs an admin action to the database.
    """
    try:
        db["admin_actions"].insert_one({
            "actor": actor,
            "action": action,
            "resource": resource,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow()
        })
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")
