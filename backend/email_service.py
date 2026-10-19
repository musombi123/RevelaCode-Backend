# backend/email_service.py

import os
import re
from html import escape

import resend

resend.api_key = os.getenv("RESEND_API_KEY")


def send_test_email(recipient):
    try:
        response = resend.Emails.send(
            {
                "from": os.getenv(
                    "EMAIL_FROM",
                    "onboarding@resend.dev"
                ),
                "to": [recipient],
                "subject": "RevelaCode Email Test",
                "html": """
                    <h2>Hello from RevelaCode 🚀</h2>
                    <p>Your Resend email integration is working successfully.</p>
                """,
            }
        )

        print("Email sent:", response)
        return response

    except Exception as e:
        print("Email failed:", e)
        raise


def send_verification_email(recipient, code, purpose="activation"):
    """Deliver a short-lived RevelaCode verification code through Resend.

    RESEND_API_KEY and EMAIL_FROM must be configured on the backend.
    Never return or log the code in an API response.
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

    sender = os.getenv("EMAIL_FROM", "onboarding@resend.dev").strip()
    if not sender:
        raise RuntimeError("EMAIL_FROM is not configured.")

    if purpose == "password_reset":
        subject = "Reset your RevelaCode password"
        heading = "Password reset code"
        explanation = "Use this code to reset your RevelaCode password."
    else:
        subject = "Activate your RevelaCode account"
        heading = "Your RevelaCode activation code"
        explanation = "Use this code to verify your email address and activate your RevelaCode account."

    safe_code = escape(code)
    safe_heading = escape(heading)
    safe_explanation = escape(explanation)
    response = resend.Emails.send({
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
    })
    return response
