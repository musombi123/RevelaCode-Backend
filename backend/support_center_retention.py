"""Run support-data retention redaction as a scheduled Render job.

Defaults: email bodies 90 days after a ticket is solved; solved ticket PII
and descriptions 365 days after creation. Financial and audit records remain.
"""
from datetime import datetime, timedelta, timezone
import os

from backend.db import get_db


def run_retention():
    db = get_db()
    now = datetime.now(timezone.utc)
    email_days = max(30, int(os.getenv("SUPPORT_EMAIL_RETENTION_DAYS", "90")))
    ticket_days = max(email_days, int(os.getenv("SUPPORT_TICKET_RETENTION_DAYS", "365")))
    email_cutoff = now - timedelta(days=email_days)
    ticket_cutoff = now - timedelta(days=ticket_days)

    message_result = db["support_ticket_messages"].update_many(
        {"type": "email", "created_at": {"$lt": email_cutoff}, "redacted": {"$ne": True}},
        {"$set": {"body_text": "[Email content redacted under the support retention policy]", "body_html": "", "sender": None, "redacted": True, "redacted_at": now}},
    )
    ticket_result = db["support_tickets"].update_many(
        {"status": {"$in": ["resolved", "solved"]}, "created_at": {"$lt": ticket_cutoff}, "redacted": {"$ne": True}},
        {"$set": {"description": "[Ticket content redacted under the support retention policy]", "body_html": "", "email": None, "user": None, "user_id": None, "attachments": [], "redacted": True, "redacted_at": now}},
    )
    inbound_result = db["support_inbound_messages"].delete_many({"received_at": {"$lt": email_cutoff}})
    return {
        "email_messages_redacted": message_result.modified_count,
        "solved_tickets_redacted": ticket_result.modified_count,
        "inbound_metadata_deleted": inbound_result.deleted_count,
        "email_retention_days": email_days,
        "ticket_retention_days": ticket_days,
    }


if __name__ == "__main__":
    print(run_retention())
