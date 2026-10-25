# RevelaCode TOTP MFA deployment

RevelaCode's authenticator-based multi-factor authentication does not require Twilio, SMS, or a paid verification service. TOTP codes are generated locally by an authenticator app and verified by the existing Flask backend.

## Configure the encryption key before enrolling users

Before enabling MFA in production, add a persistent secret named MFA_ENCRYPTION_KEY to the backend service's environment (for example, Render → RevelaCode Backend service → Environment). Generate a high-entropy value locally in PowerShell:

    python -c "import secrets; print(secrets.token_urlsafe(48))"

Copy the output directly into the environment variable. Do not commit the value to GitHub, put it in the frontend environment, or share it in screenshots. Keep it stable across deployments. The backend derives its Fernet-compatible encryption key from this value; if the value is changed later, previously encrypted authenticator secrets cannot be decrypted and affected users will need MFA recovery/reset.

The implementation has a JWT_SECRET compatibility fallback, but a dedicated MFA_ENCRYPTION_KEY should be set before enrolling production accounts. Do not rotate either key without planning a migration.

## User experience

1. Users enable an authenticator in Account & Security, confirm their current password, scan the locally generated QR code (or enter the manual key), and verify a current six-digit code.
2. RevelaCode displays single-use recovery codes once. Save them somewhere secure, separate from the device running the authenticator.
3. On future sign-ins, users enter their password followed by a current authenticator code or an unused recovery code.
4. Platform administrators and support accounts must enroll before being given a full access token.
5. The backend refuses protected API requests from sessions that do not carry a verified-MFA claim once MFA is enabled for that account.

## Recovery and operations

- Recovery codes are stored as hashes and are accepted once each.
- Authenticator secrets are encrypted at rest.
- Disabling MFA and rotating recovery codes require the current password and a valid authenticator or recovery code.
- A privileged account that has lost both the authenticator and all recovery codes needs a controlled administrator-assisted recovery process; never reset MFA solely because someone can access the account's email.
- Keep the backend clock synchronized. TOTP uses 30-second time steps and allows a small time drift window.
