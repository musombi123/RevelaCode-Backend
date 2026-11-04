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


def is_configured_super_admin(user_id, user):
    """Match the configured permanent owner to an existing active user record.

    Both the stable account ID and configured contact email must match. This
    grants the owner role consistently without trusting a browser/JWT role claim.
    The one-time Mongo migration can still persist the role in the user document.
    """
    if str(user_id or "").strip() != SUPER_ADMIN_USER_ID:
        return False
    if not isinstance(user, dict):
        return False
    configured_email = SUPER_ADMIN_CONTACT_EMAIL.casefold()
    stored_contacts = {
        str(user.get("email") or "").strip().casefold(),
        str(user.get("contact") or "").strip().casefold(),
    }
    stored_contacts.discard("")
    return bool(configured_email and configured_email in stored_contacts)
