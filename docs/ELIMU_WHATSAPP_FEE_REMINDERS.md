# Elimu fee reminders through WhatsApp

Jumuiya Elimu does **not** require Twilio. Fee reminders support:

1. Direct WhatsApp delivery through Meta's WhatsApp Business Cloud API, when configured.
2. A prepared WhatsApp click-to-chat link when the Cloud API is not configured or the automatic send fails. The Bursar must review the chat and press **Send** in WhatsApp; opening the link is not proof that a message was delivered.
3. Email through the existing Resend integration, when configured.

## Configure direct WhatsApp delivery

In the Meta for Developers app, add the WhatsApp product/use case, connect the WhatsApp Business Account and registered sending phone number, and create a durable access token with the WhatsApp messaging permission. Copy the **Phone Number ID** (not the phone number itself).

Set these secrets on the RevelaCode Backend Render service:

- `WHATSAPP_ACCESS_TOKEN`: Meta access token with permission to send WhatsApp messages.
- `WHATSAPP_PHONE_NUMBER_ID`: ID for the connected sending number.
- `WHATSAPP_API_VERSION`: optional; defaults to `v26.0`.
- `WHATSAPP_FEE_REMINDER_TEMPLATE`: optional; defaults to `school_fee_reminder`.
- `WHATSAPP_FEE_REMINDER_LANGUAGE`: optional; defaults to `en_US`, and must match the template's actual language code.

After setting the variables, redeploy/restart the backend.

## Create the approved template

Create a **Utility** template in WhatsApp Manager named `school_fee_reminder` (or set `WHATSAPP_FEE_REMINDER_TEMPLATE` to the approved name). Use the language code configured above, and include these eight body variables in this exact order:

```text
School fee reminder from {{1}}.
Student: {{2}} (Student ID: {{3}}).
Programme/class: {{4}}.
Total fees required: KES {{5}}.
Payments recorded: KES {{6}}.
Outstanding balance: KES {{7}}.
Payment instructions: {{8}}.
If you have already paid, please send your payment reference to the school Bursar. Thank you.
```

Submit it to Meta and wait until its status is approved before enabling direct reminders. Parent/guardian consent and WhatsApp Business policies still apply. Outside the 24-hour customer-service window, business-initiated messages must use an approved template. A successful API response means WhatsApp accepted the request; delivery status can still depend on provider events and the recipient's WhatsApp availability.

## No Cloud API yet? Use the manual option

The Bursar can still use the reminder action without Meta API credentials if the student's school record has a valid guardian phone number. The backend returns a pre-filled `wa.me` link with the current required fees, paid amount, balance and configured payment instructions. The dashboard displays **Open WhatsApp and press Send**. The Bursar must complete the send inside WhatsApp.

If both direct WhatsApp and Resend email delivery are unavailable, the service records that manual sending is required instead of claiming the reminder was sent.

## Email (optional)

The existing email channel continues to use `RESEND_API_KEY` and `EMAIL_FROM`.
