"""Single-use email invitations for RevelaCode support staff."""
from __future__ import annotations

import html
import os
from urllib.parse import urlencode

from backend.support_config import SUPPORT_EMAIL


ROLE_LABELS = {
    "support": "Support Agent",
    "support_agent": "Support Agent",
    "support_admin": "Support Administrator",
}


def send_admin_invitation_email(*, recipient: str, full_name: str, role: str, token: str, expires_at, existing_account: bool = False, current_role: str = "") -> dict:
    """Send a single-use invitation link; the raw token is never stored."""
    recipient = str(recipient or "").strip().lower()
    full_name = str(full_name or "").strip()
    role = str(role or "").strip().lower()
    if not recipient or "@" not in recipient or any(ch.isspace() for ch in recipient):
        raise ValueError("A valid invitation email address is required.")
    if role not in ROLE_LABELS:
        raise ValueError("Only Support Agent and Support Administrator invitations are supported.")
    if not token or len(str(token)) < 32:
        raise ValueError("A valid single-use invitation token is required.")

    api_key = str(os.getenv("RESEND_API_KEY") or "").strip()
    support_email = SUPPORT_EMAIL
    sender = f"RevelaCode Support <{support_email}>"
    frontend_url = str(
        os.getenv("FRONTEND_URL")
        or os.getenv("REVELACODE_FRONTEND_URL")
        or "https://revelacode.co.ke"
    ).strip().rstrip("/")

    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured.")
    if not sender:
        raise RuntimeError("EMAIL_FROM or SUPPORT_EMAIL_FROM is not configured.")
    if not frontend_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        raise RuntimeError("FRONTEND_URL must use HTTPS outside local development.")

    invite_url = f"{frontend_url}/support-invitation?{urlencode({'token': token, 'email': recipient})}"
    label = ROLE_LABELS[role]
    expiry_text = expires_at.strftime("%d %B %Y at %H:%M UTC") if hasattr(expires_at, "strftime") else str(expires_at)
    safe_name = html.escape(full_name or "there")
    safe_label = html.escape(label)
    safe_expiry = html.escape(expiry_text)
    safe_url = html.escape(invite_url, quote=True)
    safe_current_role = html.escape(str(current_role or "existing account").replace("_", " "))
    if existing_account:
        subject = f"Action required: approve a RevelaCode role change to {label}"
        heading = "A role change has been requested"
        explanation = (
            f"A RevelaCode administrator has requested to change the role on your existing account "
            f"from {safe_current_role} to <strong>{safe_label}</strong>. Your current access will not change "
            "unless you explicitly accept. You may decline, and your current access will remain unchanged."
        )
        button_label = "Review role-change request"
        action_text = f"Review and accept or decline this role-change request: {invite_url}"
        password_text = "You do not need to create another account or set a new password."
    else:
        subject = f"Invitation to join the RevelaCode {label} team"
        heading = "Your team invitation"
        explanation = (
            f"You have been invited to join the RevelaCode ecosystem as <strong>{safe_label}</strong>. "
            "Accept the invitation to set your password and activate your account."
        )
        button_label = "Accept invitation"
        action_text = f"Accept the invitation and set your password: {invite_url}"
        password_text = (
            "Support Administrators can supervise support operations and manage approved study and policy content, "
            "but do not receive platform-owner financial or user-sanction permissions."
        )

    try:
        import resend
    except ImportError as exc:
        raise RuntimeError("The Resend SDK is not installed.") from exc

    resend.api_key = api_key
    response = resend.Emails.send({
        "from": sender,
        "to": [recipient],
        "reply_to": support_email,
        "subject": subject,
        "html": f"""<!doctype html>
<html lang="en"><body style="margin:0;padding:24px;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#0f172a">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;border-radius:18px;overflow:hidden">
<tr><td style="padding:24px 28px;background:#0f172a;color:#fff"><div style="font-size:12px;font-weight:700;letter-spacing:1.3px;color:#6ee7b7">REVELACODE</div><h1 style="margin:12px 0 0;font-size:24px">{heading}</h1></td></tr>
<tr><td style="padding:28px;line-height:1.65;font-size:15px">
<p>Hello {safe_name},</p><p>{explanation}</p>
<p>{password_text}</p>
<p style="margin:24px 0"><a href="{safe_url}" style="display:inline-block;padding:13px 20px;border-radius:10px;background:#047857;color:white;font-weight:700;text-decoration:none">{button_label}</a></p>
<p style="color:#64748b;font-size:13px">This link is single-use and expires on {safe_expiry}. If you were not expecting this invitation, ignore this email.</p>
</td></tr><tr><td style="padding:16px 28px;background:#f8fafc;border-top:1px solid #e2e8f0;color:#64748b;font-size:12px">RevelaCode · Code. Innovate. Transform.</td></tr></table></body></html>""",
        "text": (
            f"Hello {full_name or 'there'},\n\n"
            + (f"A RevelaCode administrator requests to change your existing account role from {current_role or 'your current role'} to {label}. Your role will not change unless you accept. You may decline.\n{action_text}\n{password_text}\n\n" if existing_account else f"You have been invited to join the RevelaCode ecosystem as {label}.\n{action_text}\n{password_text}\n\n")
            + f"This single-use link expires on {expiry_text}. If you were not expecting this request, ignore this email."
        ),
    })
    return {"provider": "resend", "accepted": True, "response": response}
