# Support Team — Render environment configuration

This file documents the deployment values for the Support Team foundation.
Set the values in the **RevelaCode Backend** Render service environment, not
in frontend `VITE_*` variables.

## Permanent owner identity

| Variable | Value | Purpose |
|---|---|---|
| `SUPER_ADMIN_USER_ID` | `6a3eba8277b5d149effbafc0` | Existing MongoDB user ID used by the one-time role migration and Super Admin identity check |
| `SUPER_ADMIN_CONTACT_EMAIL` | `musombiwilliam769@gmail.com` | Permanent owner notification contact; receives owner-level Support Team alerts |
| `SUPPORT_EMAIL` | `support@revelacode.co.ke` | Public support sender, reply-to and inbound receiving address |

The backend also has these two owner defaults in `backend/support_config.py`.
Set the same values explicitly in Render so deployment configuration is visible
and does not depend on repository fallbacks. The owner ID must already exist in
the backend `users` collection. The migration does not create an account.

## Other environment variables

| Variable | Render value / action | Purpose |
|---|---|---|
| `RESEND_WEBHOOK_SECRET` | Copy the signing secret from the Resend inbound webhook configuration; do not commit it | Verifies inbound Resend webhooks |
| `GOOGLE_WEB_CLIENT_ID` | Create a Google OAuth **Web application** client and paste its Client ID | Web OAuth client |
| `GOOGLE_WEB_CLIENT_SECRET` | Paste the matching Google OAuth Client Secret | Server-side code exchange; secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | `https://revelacode-backend.onrender.com/api/oauth/google/callback` | Must exactly match the redirect URI registered in Google Cloud |
| `GOOGLE_ANDROID_RETURN_URI` | `https://revelacode.co.ke/oauth/android-callback` | Verified HTTPS Android App Link return URI; domain association requires `/.well-known/assetlinks.json` and the APK signing certificate SHA-256 |
| `FRONTEND_URL` | `https://revelacode.co.ke` | Canonical frontend origin |
| `WEB_APP_VERSION` | Set to the deployed web release label | Shown in Support Center System Health |
| `ANDROID_APP_VERSION` | Set to the published APK version label | Shown in Support Center System Health |
| `SUPPORT_EMAIL_RETENTION_DAYS` | Leave unset for the current code default of `90`, or set an approved value | Email-content retention threshold |
| `SUPPORT_TICKET_RETENTION_DAYS` | Leave unset for the current code default of `365`, or set an approved value | Solved-ticket retention threshold |

## Apply safely

1. Add the owner ID, owner contact and support mailbox values to the Render
   backend service environment. Do not place OAuth client secrets or webhook
   secrets in GitHub or frontend environment variables.
2. Add the Google OAuth credentials only after creating the matching Web
   application client in Google Cloud. Register the exact backend callback URL
   shown above.
3. Configure the Resend `email.received` webhook to
   `https://revelacode-backend.onrender.com/api/support-center/inbound/resend`
   and copy its signing secret into `RESEND_WEBHOOK_SECRET`. Confirm the
   receiving-domain/MX arrangement before changing DNS; do not overwrite
   existing root-domain MX records without checking the current mailbox host.
4. Back up MongoDB, then run the one-time migration from the backend service:
   `python -m backend.support_center_migrate`. It checks that the configured
   owner ID exists before assigning the Super Admin role and invalidating
   existing sessions.
5. Do not schedule `backend.support_center_retention` until the proposed
   retention periods are approved and the deployment has been tested.

The code defaults do **not** set Render environment variables, create a
production database role, configure Google or Resend credentials, or deploy
the branch. Merge/deploy and the one-time migration remain separate actions.
