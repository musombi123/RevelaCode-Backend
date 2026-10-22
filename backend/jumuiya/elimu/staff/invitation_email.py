"""Email delivery for RevelaCode Elimu staff invitations."""

from __future__ import annotations

import html
import os
from datetime import datetime
from urllib.parse import urlencode



ROLE_LABELS = {
    "owner": "School Owner",
    "principal": "Principal / Headteacher",
    "teacher": "Teacher",
    "bursar": "Bursar",
    "registrar": "Registrar",
}


def send_staff_invitation_email(
    *,
    recipient: str,
    invitee_name: str = "",
    school_name: str,
    inviter_name: str,
    inviter_email: str = "",
    role: str,
    token: str,
    expires_at: datetime | str | None = None,
) -> dict:
    """Send an invitation using the configured Resend sender.

    The raw token is placed only in the email link. Invitation storage keeps
    its hash; callers must never return the raw token in API responses.
    """

    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "RESEND_API_KEY is not configured; staff invitation email was not sent."
        )

    sender = os.getenv("EMAIL_FROM", "onboarding@resend.dev").strip()
    frontend_url = (
        os.getenv("FRONTEND_URL")
        or os.getenv("REVELACODE_FRONTEND_URL")
        or "https://revelacode-frontend.onrender.com"
    ).strip().rstrip("/")

    if not sender:
        raise RuntimeError("EMAIL_FROM is not configured.")
    if not frontend_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        raise RuntimeError("FRONTEND_URL must be an HTTPS URL (except local development).")

    normalized_role = str(role or "").strip().lower()
    role_label = ROLE_LABELS.get(normalized_role, normalized_role.replace("_", " ").title())
    clean_school = str(school_name or "your school").strip() or "your school"
    clean_inviter = str(inviter_name or "the school owner").strip() or "the school owner"
    clean_invitee = str(invitee_name or "").strip()
    clean_recipient = str(recipient or "").strip().lower()
    if not clean_recipient or "@" not in clean_recipient:
        raise ValueError("A valid invitation recipient email is required.")
    if not token or len(str(token)) < 20:
        raise ValueError("A valid invitation token is required.")

    invite_url = f"{frontend_url}/elimu-invitation?{urlencode({'token': str(token), 'email': clean_recipient})}"
    expiry_text = "within the next 7 days"
    if isinstance(expires_at, datetime):
        expiry_text = expires_at.strftime("%d %B %Y at %H:%M UTC")
    elif isinstance(expires_at, str) and expires_at.strip():
        expiry_text = expires_at.strip()

    escaped_name = html.escape(clean_invitee or "there")
    escaped_school = html.escape(clean_school)
    escaped_inviter = html.escape(clean_inviter)
    escaped_role = html.escape(role_label)
    escaped_expiry = html.escape(expiry_text)
    escaped_url = html.escape(invite_url, quote=True)

    subject = f"Invitation to join {clean_school} on RevelaCode Elimu"
    plain_text = (
        f"Hello {clean_invitee or 'there'},\n\n"
        f"{clean_inviter} has invited you to join {clean_school} on RevelaCode Elimu as {role_label}.\n\n"
        f"Accept the invitation using this secure link: {invite_url}\n\n"
        f"This invitation expires: {expiry_text}. If you were not expecting it, you can ignore this email.\n\n"
        "RevelaCode Elimu"
    )
    html_body = f"""<!doctype html>
<html lang="en">
  <body style="margin:0;padding:24px;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:18px;overflow:hidden;">
      <tr><td style="padding:24px 28px;background:#0f172a;color:#ffffff;">
        <div style="font-size:12px;font-weight:700;letter-spacing:1.3px;color:#93c5fd;text-transform:uppercase;">RevelaCode Elimu</div>
        <h1 style="margin:12px 0 0;font-size:24px;line-height:1.3;">You have a school invitation</h1>
      </td></tr>
      <tr><td style="padding:28px;line-height:1.65;font-size:15px;">
        <p style="margin:0 0 16px;">Hello {escaped_name},</p>
        <p style="margin:0 0 16px;"><strong>{escaped_inviter}</strong> has invited you to join <strong>{escaped_school}</strong> on RevelaCode Elimu as <strong>{escaped_role}</strong>.</p>
        <p style="margin:0 0 24px;">Accept the invitation to connect your verified RevelaCode account to the school's workspace. Your access will be limited to the permissions assigned to your role.</p>
        <p style="margin:0 0 24px;"><a href="{escaped_url}" style="display:inline-block;padding:13px 20px;border-radius:10px;background:#1d4ed8;color:#ffffff;font-weight:700;text-decoration:none;">Accept invitation</a></p>
        <p style="margin:0 0 8px;color:#475569;font-size:13px;">For your security, this link is single-use and expires on {escaped_expiry}.</p>
        <p style="margin:0;color:#64748b;font-size:13px;">If you were not expecting this invitation, you can ignore this email. No school access will be granted unless the invitation is accepted.</p>
      </td></tr>
      <tr><td style="padding:16px 28px;background:#f8fafc;border-top:1px solid #e2e8f0;color:#64748b;font-size:12px;">RevelaCode · Code. Innovate. Transform.</td></tr>
    </table>
  </body>
</html>"""

    try:
        import resend
    except ImportError as exc:
        raise RuntimeError(
            "The Resend SDK is not installed. Install the backend requirements before sending staff invitations."
        ) from exc

    resend.api_key = api_key
    message = {
        "from": sender,
        "to": [clean_recipient],
        "subject": subject,
        "html": html_body,
        "text": plain_text,
    }

    # The invitation is still sent from an authorized RevelaCode sender.
    # The inviter's address is only a reply-to destination, never spoofed as From.
    clean_reply_to = str(inviter_email or "").strip()
    if clean_reply_to and "@" in clean_reply_to and " " not in clean_reply_to:
        message["reply_to"] = [clean_reply_to]

    response = resend.Emails.send(message)
    return {"provider": "resend", "accepted": True, "response": response}
