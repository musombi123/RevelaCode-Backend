"""Central support and permanent platform-owner contact configuration.

Environment variables take precedence over these repository defaults. Keep
provider secrets (Resend and Google OAuth) in Render, never in source control.
"""
import os

DEFAULT_SUPER_ADMIN_USER_ID = "6a3eba8277b5d149effbafc0"
DEFAULT_SUPER_ADMIN_CONTACT_EMAIL = "musombiwilliam769@gmail.com"

SUPER_ADMIN_USER_ID = str(
    os.getenv("SUPER_ADMIN_USER_ID") or DEFAULT_SUPER_ADMIN_USER_ID
).strip()

SUPER_ADMIN_CONTACT_EMAIL = str(
    os.getenv("SUPER_ADMIN_CONTACT_EMAIL") or DEFAULT_SUPER_ADMIN_CONTACT_EMAIL
).strip().lower()

# Public support sender/Reply-To stays on the verified RevelaCode domain.
SUPPORT_EMAIL = str(
    os.getenv("SUPPORT_EMAIL") or "support@revelacode.co.ke"
).strip().lower()
