# RPSVI test-case catalogue

This catalogue defines safe, repeatable checks. The coordinator assigns exact cases and accounts. A test case is not permission to probe an unlisted endpoint or environment.

## Standard case record

Each case should have: case ID, track, risk, environment, build SHA, required role/account, preconditions, steps, expected result, actual result, evidence, request ID, status, reviewer and retest result.

## Functional tests

| ID | Area | Test | Expected result |
|---|---|---|---|
| FUNC-AUTH-01 | Authentication | Valid staging account signs in | Correct account is authenticated; no other identity is returned |
| FUNC-AUTH-02 | Session | Expired/revoked staging session is reused | Request is rejected according to the existing contract |
| FUNC-ELIMU-01 | Elimu | Assigned teacher opens their class records | Only authorised school/class data is shown |
| FUNC-ELIMU-02 | Elimu | Bursar opens finance workflows | Access matches the bursar permission matrix |
| FUNC-BIZ-01 | Biashara | Assigned business role opens permitted module | Only authorised business data/actions appear |
| FUNC-SHAMBA-01 | Shamba | Assigned farmer opens their farm | Only farms belonging to the authorised profile appear |
| FUNC-JUM-01 | Jumuiya | Assigned member opens profile/circle/feed | Access follows membership and visibility rules |
| FUNC-SYNC-01 | Sync | Assigned offline changes are replayed once | Existing sync conflict/idempotency contract is preserved |

## Security tests

Use only assigned synthetic accounts and non-destructive inputs. The test lead should map every case to the actual route and permission model before assignment.

| ID | Control | Safe verification |
|---|---|---|
| SEC-AUTH-01 | Authentication | Missing, malformed, expired and revoked staging tokens are rejected |
| SEC-AUTHZ-01 | Function-level authorisation | A role cannot invoke a function absent from its permission matrix |
| SEC-TENANT-01 | School isolation | School Alpha user cannot read or mutate School Beta records by substituting an identifier |
| SEC-TENANT-02 | Business isolation | Business Alpha user cannot read or mutate another synthetic business tenant |
| SEC-INPUT-01 | Validation | Invalid types, oversized fields and malformed identifiers receive controlled validation errors |
| SEC-RATE-01 | Rate limiting | Approved low-rate test confirms configured limit and Retry-After behaviour |
| SEC-SESSION-01 | Session security | Revocation and expiry are enforced consistently |
| SEC-HEADERS-01 | Response headers | Baseline security headers are present; HSTS appears only on HTTPS |
| SEC-CORS-01 | CORS | Only configured and verified origins are accepted; credentialed wildcard CORS is absent |
| SEC-AUDIT-01 | Audit trail | Privileged test action produces a bounded audit record without secrets |

Do not brute force, exploit, scan unrelated infrastructure or conduct availability attacks. Do not use a real tenant to test isolation.

## Performance tests

Only run on the exact staging hostname with an approved test window, target VU count and named operator.

| ID | Profile | Notes |
|---|---|---|
| PERF-HEALTH-01 | Public health baseline | Establish network and application health latency only; not representative user capacity |
| PERF-READ-01 | Authenticated read | Choose one reviewed GET route and synthetic account |
| PERF-TENANT-01 | Multi-tenant read mix | Use separate tokens/tenant IDs and confirm no cross-tenant leakage |
| PERF-SPIKE-01 | Short traffic spike | Only after sustained load profile passes; pre-agreed abort thresholds |
| PERF-SOAK-01 | Sustained workload | Run for approved duration; monitor resource growth, pool wait and latency |

A k6 virtual user is a simulated execution loop, not necessarily a real browser, logged-in human or open WebSocket. Report VUs, request rate and active session semantics separately.

## Reliability tests

Run only on staging with external side effects disabled:

- REL-DB-01: short MongoDB connection timeout; verify bounded failure and recovery.
- REL-PROV-01: model-provider timeout; verify bounded response and fallback metadata.
- REL-WORK-01: controlled restart of one staging worker after its side effects have been disabled; verify no duplicated job.
- REL-SYNC-01: interrupt a test sync, reconnect and replay the same idempotency key; verify one committed mutation.
- REL-RETRY-01: retry a safe, idempotent operation and verify consistent outcome.
- REL-RECOVER-01: restore dependency and confirm health/readiness recover.

Do not simulate payment/provider failures through live payment credentials.

## AI integration tests

- AI-ROUTE-01: record actual `provider` and `model` in the authenticated response.
- AI-FALLBACK-01: in a provider-mocked test, force primary failure and confirm fallback metadata.
- AI-LATENCY-01: measure complete non-streaming response latency and server-observed response waiting time.
- AI-QUALITY-01: evaluate fixed, versioned prompts using a documented rubric and blinded reviewers.
- AI-COST-01: record actual input/output token usage and provider pricing version when available.

The existing `/api/chat` path persists conversation turns. Use only a dedicated synthetic staging account. Do not run AI prompts against a production account.
