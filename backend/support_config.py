"""Single source of truth for the RevelaCode support mailbox."""
import os

SUPPORT_EMAIL = str(os.getenv("SUPPORT_EMAIL") or "support@revelacode.co.ke").strip().lower()
