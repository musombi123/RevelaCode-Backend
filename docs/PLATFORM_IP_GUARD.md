# Platform IP Guard — deployment and operation

Sci-Core uses the **RevelaCode Backend** platform IP guard. It stores block records and audit events in the existing RevelaCode Mongo database and enforces them in the Flask application's before_request hook, before ordinary API routes execute. No second database is introduced.

## Render environment

Keep the existing backend MONGO_URI and MONGO_DB_NAME configuration.

For the normal Render public web-service ingress, set:
- SCI_CORE_IP_ALLOWLIST=<stable-admin-public-ip>/32
- For a stable administrator IPv6 address, use /128.
- Multiple IPv4/IPv6 addresses or networks are comma-separated.

The client address is resolved from Cloudflare's CF-Connecting-IP header. The backend deliberately does not trust browser-supplied X-Forwarded-For or X-Real-IP. If that trusted Cloudflare header is unavailable, manual block creation returns HTTP 503 and explains that the administrator address could not be verified.

Add at least one stable platform-administrator egress address to SCI_CORE_IP_ALLOWLIST before enabling automatic blocking. This protects the administrator's known network and keeps automatic response disabled until an allowlist exists.

## What it does

- Applies an exact, globally routable public IPv4 or IPv6 address block to all non-health RevelaCode Backend routes.
- Rejects CIDR ranges as block targets, private addresses, loopback, multicast, unspecified and documentation/test addresses.
- Requires a current platform-admin session, explicit confirmation, a reason and a duration from 5 minutes to 7 days.
- Rejects attempts to block the current administrator session IP or any configured allowlisted IP.
- Persists actor, reason, source, creation time, expiry and block/unblock audit events in the existing Mongo database.
- Automatically blocks a non-allowlisted public source for 30 minutes after 50 HTTP 401 responses from /api/login or /api/auth/login within 5 minutes, but only after the administrator allowlist is configured.
- Stores failed-login IP, route and timestamp only; it never stores passwords, tokens, authorization headers or request bodies.
- Expires blocks automatically when the expiry timestamp passes. Administrators can also release them manually.

## Sci-Core API

These routes are served by the RevelaCode Backend, not the RevelaAI FastAPI service:
- GET /api/admin/security/ip-blocks
- POST /api/admin/security/ip-blocks
- POST /api/admin/security/ip-blocks/unblock

They use the existing current-database-role require_current_roles administrator guard. The dashboard calls these routes through VITE_BACKEND_URL.

## Safe rollout checklist

1. Merge and deploy the RevelaCode Backend IP Guard change.
2. In Render's RevelaCode Backend environment, add SCI_CORE_IP_ALLOWLIST with the stable admin egress public IP or network. Do not guess a mobile-carrier address; use a stable egress IP if possible.
3. Confirm /health remains healthy and open Administration → Core systems → Sci-Core Defensive Core.
4. Refresh the IP Protection panel. Confirm it reports persistent=true, status=active, current_ip matching the actual administrator egress, and enforcement=platform_request_boundary.
5. Test blocking only with a public test IP you control and that is not the current admin IP or allowlisted. Use a short 15-minute duration.
6. Verify a request from that source receives HTTP 403 with code IP_BLOCKED.
7. Release the test block from the allowed administrator connection and verify an unblocked audit event.
8. Review automatic policy status. It must remain disabled until the allowlist is configured.

## Operational boundary

This is application-layer rejection after an inbound request reaches the RevelaCode Flask service. It does not modify Render's Cloudflare edge rules, host firewall, Nginx, or any independent third-party origin. Render/Cloudflare continue to handle network-level filtering and DDoS mitigation. This feature blocks the RevelaCode Backend; a separate service needs its own integration if it must enforce the same policy.