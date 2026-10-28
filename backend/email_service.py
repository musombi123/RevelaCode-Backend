# backend/email_service.py

import logging
import os
import re
from html import escape

import resend

logger = logging.getLogger(__name__)
resend.api_key = os.getenv("RESEND_API_KEY")


def send_test_email(recipient):
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured.")

    resend.api_key = api_key
    sender = os.getenv("EMAIL_FROM", "onboarding@resend.dev").strip()
    if not sender:
        raise RuntimeError("EMAIL_FROM is not configured.")

    try:
        response = resend.Emails.send({
            "from": sender,
            "to": [recipient],
            "subject": "RevelaCode Email Test",
            "html": (
                "<h2>Hello from RevelaCode 🚀</h2>"
                "<p>Your Resend email integration is working successfully.</p>"
            ),
        })
        logger.info("Resend test email accepted for delivery; recipient_domain=%s", recipient.rsplit("@", 1)[-1])
        return response
    except Exception:
        logger.exception("Resend test email delivery failed")
        raise


def send_verification_email(recipient, code, purpose="activation"):
    """Deliver a short-lived RevelaCode verification code through Resend.

    RESEND_API_KEY and the matching sender address must be configured on
    the backend. Never return or log the code in an API response.
    """
    recipient = str(recipient or "").strip()
    code = str(code or "").strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", recipient):
        raise ValueError("A valid email address is required.")
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("Verification code must be six digits.")

    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured.")

    if purpose == "password_reset":
        subject = "Reset your RevelaCode password"
        heading = "Password reset code"
        explanation = "Use this code to reset your RevelaCode password."
        sender = os.getenv("EMAIL_FROM", "RevelaCode <noreply@revelacode.co.ke>").strip()
    elif purpose == "support_activation":
        subject = "RevelaCode account verification assistance"
        heading = "Your account verification code"
        explanation = (
            "RevelaCode Support has sent you a fresh code to verify your email "
            "address and activate your account."
        )
        sender = os.getenv(
            "SUPPORT_EMAIL_FROM",
            "RevelaCode Support <support@revelacode.co.ke>",
        ).strip()
    else:
        subject = "Activate your RevelaCode account"
        heading = "Your RevelaCode activation code"
        explanation = "Use this code to verify your email address and activate your RevelaCode account."
        sender = os.getenv("EMAIL_FROM", "RevelaCode <noreply@revelacode.co.ke>").strip()

    if not sender:
        raise RuntimeError("The sender address is not configured for this email purpose.")

    # Apply the current deployment key at send time, not only module import.
    resend.api_key = api_key

    safe_code = escape(code)
    safe_heading = escape(heading)
    safe_explanation = escape(explanation)
    payload = {
        "from": sender,
        "to": [recipient],
        "subject": subject,
        "html": f"""
            <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;padding:28px;color:#0f172a">
              <div style="font-size:13px;font-weight:700;letter-spacing:.08em;color:#059669">REVELACODE</div>
              <h1 style="font-size:24px;margin:20px 0 10px">{safe_heading}</h1>
              <p style="font-size:15px;line-height:1.6;color:#475569">{safe_explanation}</p>
              <div style="margin:24px 0;padding:18px;background:#f1f5f9;border-radius:12px;text-align:center;font-size:32px;font-weight:700;letter-spacing:8px">{safe_code}</div>
              <p style="font-size:13px;line-height:1.6;color:#64748b">This code expires in 10 minutes. If you did not request it, you can safely ignore this email.</p>
              <p style="font-size:13px;color:#64748b;margin-top:28px">RevelaCode · Code. Innovate. Transform.</p>
            </div>
        """,
        "text": f"{heading}\n\n{explanation}\n\nCode: {code}\n\nThis code expires in 10 minutes. If you did not request it, ignore this email.",
    }

    try:
        response = resend.Emails.send(payload)
        logger.info(
            "Resend accepted verification email; purpose=%s recipient_domain=%s response=%s",
            purpose,
            recipient.rsplit("@", 1)[-1],
            response,
        )
        return response
    except Exception:
        logger.exception(
            "Resend verification email delivery failed; purpose=%s recipient_domain=%s",
            purpose,
            recipient.rsplit("@", 1)[-1],
        )
        raise
