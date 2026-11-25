# RPSVI capacity test plan and release gates

## 1. Define the claim

Do not use "100,000 traffic" without identifying the metric:

- 100,000 registered accounts: data and account-management capacity.
- 100,000 monthly/daily active users: usage over a defined time window.
- 100,000 concurrent sessions: simultaneous active sessions.
- 100,000 concurrent virtual users: load-generator simulation, only comparable to real users when the scenario, think time, request mix and session behaviour represent them.

The long-term engineering objective is to verify 100,000 concurrent simulated user sessions with a realistic cross-hub workload. It is not a claim about the current deployment.

## 2. Workload model

Before each test, document:

- User mix by hub: Elimu, Shamba, Biashara, Jumuiya and general platform.
- Authentication/session behaviour, request mix and think time.
- Reads versus writes, payload sizes, pagination and upload volumes.
- AI request share separately from normal API traffic.
- Target VUs, request rate, arrival rate, test duration and ramp pattern.
- Number and location of load generators.
- Build SHA, staging hostname, instance size, database tier and configuration.
- Exact test accounts/tenants and synthetic dataset version.

A simple planning example: 100,000 active sessions each making two API calls per minute produces approximately 3,333 requests per second. This is an arithmetic scenario, not a measured traffic profile or capacity result.

## 3. Progressive gates

The initial single-generator profile is capped at 1,000 VUs. Increase only when the previous level passes and the operator approves the next run.

| Gate | Concurrent VUs | Gate before proceeding |
|---|---:|---|
| A | 25 | Smoke and authentication work; no critical defect |
| B | 50 | Stable latency/error thresholds and no tenant leak |
| C | 100 | Database and app resource metrics captured |
| D | 250 | p95/p99 stable; no unbounded queue/pool wait |
| E | 500 | Sustained load stable; no worker saturation |
| F | 1,000 | Repeatable result on staging; resource headroom understood |
| G | 5,000 | Distributed generators and approved staging capacity |
| H | 10,000 | Previous distributed gate passes |
| I | 25,000 | Database, edge and app scaling evidence reviewed |
| J | 50,000 | Capacity and failure recovery reviewed |
| K | 75,000 | Near-target operational readiness reviewed |
| L | 100,000 | Full acceptance suite and sustained test pass |

A test lead may skip no gate without a recorded engineering review. Higher gates require a realistic distributed load-generation design; a single laptop or a single k6 process is not sufficient evidence.

## 4. Initial acceptance targets

These are proposed targets for ordinary API routes, not measured values and not universal guarantees. Establish a baseline first and agree per endpoint class.

| Metric | Initial target |
|---|---:|
| Ordinary API read p95 | <= 300 ms |
| Normal database-backed API p95 | <= 500 ms |
| Ordinary API p99 | <= 1,000 ms |
| HTTP 5xx rate during steady-state test | < 0.1% |
| Cross-tenant data exposure | 0 |
| Duplicate committed critical mutations | 0 |
| Unbounded queue growth or pool starvation | 0 |

For first baselines, thresholds may be marked provisional. Do not silently loosen thresholds to make a failed run pass. AI generation, file processing, payment sandboxes and external providers need their own latency budgets.

## 5. Abort criteria

Stop the test immediately if any condition occurs:

- The target hostname does not exactly match the approved staging hostname.
- A production hostname, production data or real user identity is detected.
- Any cross-tenant data exposure or unauthorised mutation is suspected.
- 5xx rate exceeds 2% for 60 seconds, or p95 exceeds twice the agreed ceiling for 2 consecutive minutes.
- MongoDB connection pool wait grows continuously, database availability degrades, or data integrity is uncertain.
- Error budgets, queue age, CPU/memory limits or third-party provider quotas exceed the signed test plan.
- Test lead, service owner or incident responder calls stop.

The operator must publish the stop reason and preserve sanitised diagnostics.

## 6. Required observations

For each run capture:

- k6 VUs, iteration count, request rate, successful/failed checks.
- p50, p90, p95, p99 latency and throughput.
- HTTP status distribution and error rate.
- CPU, memory, instance count, worker/thread saturation and restarts.
- MongoDB connections, pool wait, command/query latency, slow queries and server load.
- Queue depth/age, retries, failed tasks and worker state where applicable.
- Request IDs and sanitised error examples.
- Recovery time and data-integrity checks after the run.

## 7. Test sequence

1. Verify staging readiness and exact host guard.
2. Run health smoke (10 → 25 → 50 VUs).
3. Run a reviewed authenticated GET endpoint with a dedicated synthetic account (25 → 50 → 100 VUs).
4. Repeat the run at least twice to check variability.
5. Add multi-tenant read traffic only after tenant-isolation tests pass.
6. Add bounded writes using a separate test profile only after idempotency and cleanup plans have been reviewed.
7. Run spike, soak and dependency-failure cases separately.
8. Move to distributed generators only after the 1,000-VU gate passes and infrastructure owners approve the cost and run window.

The current repository scripts are read-only. They are not an authorisation to test mutation endpoints.

## 8. Report format

Every result must identify: run ID, tester/operator, date/time/timezone, test-plan revision, environment, hostname, app and AI build SHA, instance/database tiers, script SHA, workload definition, achieved VUs/RPS, metrics, threshold results, findings, abort events, and reviewer sign-off.

Publish the highest **passed and reproducible** gate. If the highest gate is 1,000 VUs, say "verified to 1,000 VUs under the published workload"—not "supports 100,000 users."
