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
| `MICROSOFT_CLIENT_ID` | Register a Microsoft Entra app and copy its Application (client) ID | Microsoft OIDC client ID |
| `MICROSOFT_CLIENT_SECRET` | Create a client secret in Microsoft Entra; store only in Render | Microsoft server-side code exchange secret |
| `MICROSOFT_TENANT_ID` | `common` for personal/work/school accounts, or a specific tenant ID | Microsoft authority scope |
| `MICROSOFT_OAUTH_REDIRECT_URI` | `https://revelacode-backend.onrender.com/api/oauth/microsoft/callback` | Must exactly match the Microsoft app registration Web redirect URI |
| `GITHUB_CLIENT_ID` | Create a GitHub OAuth App and copy the Client ID | GitHub sign-in client ID |
| `GITHUB_CLIENT_SECRET` | Create a matching GitHub OAuth App secret; store only in Render | GitHub server-side code exchange secret |
| `GITHUB_OAUTH_REDIRECT_URI` | `https://revelacode-backend.onrender.com/api/oauth/github/callback` | Must exactly match the GitHub OAuth App callback URL |
| `AFRICASTALKING_USERNAME` | Africa’s Talking application username | SMS delivery account |
| `AFRICASTALKING_API_KEY` | Copy the API key from the Africa’s Talking dashboard; store only in Render | SMS API authentication secret |
| `AFRICASTALKING_SENDER_ID` | Optional; set only after Africa’s Talking approves the sender ID | Branded SMS sender; approval may be required |
| `AFRICASTALKING_ENV` | `production` for real SMS, `sandbox` for provider sandbox | SMS API environment |
| `REVELACODE_WEBAUTHN_RP_ID` | `revelacode.co.ke` | Passkey relying-party ID; must match the registered web domain |
| `REVELACODE_WEBAUTHN_ORIGINS` | Comma-separated trusted origins, including `https://revelacode.co.ke` and the required first-party hub hosts | Explicit WebAuthn origin allowlist |
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

## Additional identity methods

1. Create a Microsoft Entra app registration for the accounts you intend to accept. Add the exact Microsoft callback URL above as a **Web** redirect URI. Use `common` only when the app should accept both personal Microsoft accounts and organizational/school accounts. Store the secret in Render, not Vite variables.
2. Create a GitHub OAuth App. Set its callback URL to the exact backend callback above and grant the `read:user` and `user:email` scopes at sign-in. The identity flow reads the verified primary email and does not retain the GitHub OAuth access token or grant repository access.
3. Configure Africa’s Talking with a live account, an application, an API key and an approved sender ID/shortcode as required for your Kenyan route. SMS delivery is a paid provider service. Do not enable `AFRICASTALKING_ENV=production` until the provider account and billing are ready. The API key must remain server-side.
4. Passkeys require HTTPS and the correct relying-party domain. Set `REVELACODE_WEBAUTHN_RP_ID` to the registrable domain and `REVELACODE_WEBAUTHN_ORIGINS` to the exact production origins that should be trusted. Do not add wildcard origins. Browser support is required; native Android WebView support must be validated separately.
5. Social-provider sign-in creates regular member accounts only. Existing accounts must sign in using their current method and then link an external provider from Account & Security; a matching email is never silently linked to another account.
