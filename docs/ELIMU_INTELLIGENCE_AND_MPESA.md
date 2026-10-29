# Elimu Hub intelligence and M-Pesa rollout

This change adds an Elimu Intelligence workspace, a school-scoped student register export, incoming WhatsApp fee queries, and a production-gated M-Pesa STK flow. It continues using the RevelaCode backend and the existing Jumuiya Elimu school/student/fee records.

## Feature entry points

- GET /api/jumuiya/elimu/intelligence/fee-risk — School Owner, Principal, or Bursar with fees.view.
- GET /api/jumuiya/elimu/intelligence/student-register-export — School Owner, Principal, or Registrar with students.view. Returns a CSV-ready response; the frontend downloads it as a file.
- GET /api/jumuiya/elimu/intelligence/students/<student_id>/admission-letter.pdf — School Owner, Principal, or Registrar with students.view. Generates a school-scoped PDF with an opaque QR verification token and audit event.
- GET /api/jumuiya/elimu/intelligence/verify-document/<token> — public QR verification endpoint. Returns only the document ID, school identity, learner name, admission number, class and issue date. It never returns contacts or fee data.
- POST /api/jumuiya/elimu/intelligence/students/<student_id>/admission-letter/<document_id>/revoke — authorized school Owner, Principal or Registrar can revoke an issued document; the QR then reports revoked.
- POST /api/jumuiya/elimu/finance/whatsapp/webhook — existing Meta webhook, extended to handle incoming text messages as well as delivery statuses.
- POST /api/jumuiya/elimu/finance/mpesa/callback — new public provider callback for Elimu fee checkout. Callbacks are not treated as payment proof on their own; the backend queries Daraja for the same checkout and validates provider identifiers and callback amount/payer/receipt before recording payment.

## WhatsApp parent commands

The existing webhook verification must remain configured with the Meta app secret. The Cloud API access token and phone-number ID are backend environment variables only.

- FEES — reads the fee balance for an active learner whose guardian phone matches the WhatsApp sender.
- FEES followed by an admission number — selects a linked learner when more than one learner is connected to the same guardian number.
- PAY — requests a full-balance STK prompt when exactly one linked learner is eligible.
- PAY followed by an admission number — requests the prompt for that linked learner.

The bot does not accept a student name or admission number by itself as proof of guardian identity. It requires the sender's WhatsApp number to match the guardian phone on the active learner record. If several learners are matched, the bot asks the sender to select one. A payment prompt is sent only when all required production configuration is present and an outstanding balance can be safely allocated. The current workflow sends an STK request for the learner's full recorded balance and allocates a confirmed payment to outstanding fee records in due-date order. Decimal-KES totals are refused because the configured STK flow requires a whole-KES amount.

If checkout submission becomes uncertain, the checkout and fee locks remain pending for reconciliation. Parents must not request another prompt until the unresolved payment is reviewed.

## Required Render environment configuration

Keep the existing Revenue Engine variables set in RevelaCode-Backend. Never place secrets in the frontend, APK, public repository, or AI service.

| Variable | Required value or purpose |
|---|---|
| MPESA_ENV | production for live fee payments |
| MPESA_STK_URL | https://api.safaricom.co.ke in production |
| MPESA_STK_PATH | /mpesa/stkpush/v1/processrequest |
| MPESA_STK_QUERY_PATH | /mpesa/stkpushquery/v1/query |
| MPESA_CONSUMER_KEY | Safaricom production Daraja consumer key |
| MPESA_CONSUMER_SECRET | Safaricom production Daraja consumer secret |
| MPESA_SHORTCODE | Registered live PayBill or Till shortcode |
| MPESA_PASSKEY | Live Daraja passkey for the shortcode |
| MPESA_TRANSACTION_TYPE | CustomerPayBillOnline or CustomerBuyGoodsOnline, matching the shortcode |
| MPESA_PARTY_B | Destination shortcode when required; otherwise defaults to MPESA_SHORTCODE |
| MPESA_CALLBACK_URL | Keep the existing Revenue callback URL ending in /api/revenue/providers/mpesa/callback |
| REVENUE_PAYMENT_PROVIDERS | Must include mpesa for the shared Daraja adapter's production readiness check |
| ELIMU_MPESA_CALLBACK_URL | Public HTTPS URL ending in /api/jumuiya/elimu/finance/mpesa/callback |
| WHATSAPP_WEBHOOK_VERIFY_TOKEN | Random verification token used when Meta subscribes to the webhook |
| WHATSAPP_APP_SECRET | Meta app secret used to validate X-Hub-Signature-256 |
| WHATSAPP_ACCESS_TOKEN | Server-side WhatsApp Cloud API access token |
| WHATSAPP_PHONE_NUMBER_ID | WhatsApp Cloud API phone-number ID |
| WHATSAPP_API_VERSION | Supported Graph API version, for example v26.0 |
| ELIMU_DOCUMENT_VERIFY_BASE_URL | Optional HTTPS origin for the public QR verification endpoint; defaults to https://revelacode-backend.onrender.com |

The public URL configured in ELIMU_MPESA_CALLBACK_URL must route to the deployed RevelaCode Backend and be reachable by Safaricom. Meta must be configured to deliver message webhooks to https://<backend-host>/api/jumuiya/elimu/finance/whatsapp/webhook. The app secret, tokens and shortcode secrets must not be committed to Git.

## Reconciliation model

1. The server calculates the outstanding balance from the school's fee records; clients cannot send an amount to charge.
2. A checkout intent is saved before sending STK. Idempotency indexes and fee-level checkout locks prevent a second prompt for the same learner/fee balance while a request is unresolved.
3. A Meta/Safaricom callback only signals that a result may be available. The backend queries Daraja and checks the exact checkout and merchant request IDs.
4. Before writing the fee ledger, the backend validates the callback receipt, amount and payer against the original checkout. The provider receipt is unique in the Elimu payment ledger.
5. Fee allocations are applied with conditional updates and an idempotency marker per checkout. A changed balance or partial allocation is flagged for Bursar reconciliation instead of silently overpaying a votehead.
6. A successful payment stores the receipt and updates the fee record(s). The parent can send FEES again to retrieve the latest recorded balance.

This is not a guarantee that production checkout will be live immediately after merge. Verify the live environment configuration and conduct a controlled low-value end-to-end transaction before using it for actual school collections.

## Important limits

- Fee-risk signals are an explainable heuristic based on stored fee history, not a trained/default prediction model. They must never trigger automatic exclusion or termination of a learner.
- The student-register export is a review template. It does not log into KEMIS/NEMIS or claim to meet the latest official upload schema. Confirm the current government field definition before submitting it.
- The admission-letter QR verifies a document record stored in the same backend; it does not itself certify a KEMIS/NEMIS registration.
- This change does not yet generate a fee receipt PDF/WhatsApp attachment, submit KNEC CBA files, synchronize to government systems, or implement a face-recognition attendance check. Those require dedicated schemas, permissions and end-to-end tests.
