# backend/email_service.py

import os
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