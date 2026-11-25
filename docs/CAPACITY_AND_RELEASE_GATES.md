# RevelaCode 100K-user scalability and release runbook

## What "100,000 traffic" means

The target must be defined before it can be verified:

- **100,000 registered accounts** is a data-volume and account-management target.
- **100,000 monthly active users** is a usage/throughput target.
- **100,000 simultaneous users (concurrency)** is a substantially larger infrastructure and traffic target.

These are not interchangeable. The repository currently has no measured evidence that the production deployment can sustain 100,000 concurrent users. This runbook makes the target measurable rather than claiming it prematurely.

## Current platform shape

- Flask remains the system-of-record API and keeps its existing routes and authentication contracts.
- MongoDB remains the one shared database. Jumuiya continues to use the existing database and `jumuiya_` collection namespace.
- Gunicorn serves HTTP requests. Each process owns a separate PyMongo client pool.
- The background worker is isolated from the Flask app and is not intended to be scaled horizontally until its job coordination is made distributed.
- Render Cron services remain responsible for the existing market-data refresh and Elimu lifecycle/reminder schedules.
- No Redis, Celery, or FastAPI service is currently required by the code in this programme.

## Capacity controls already in the repository

- Configurable Gunicorn worker/thread counts and worker recycling.
- Configurable MongoDB connection pool, connection timeout, and wait-queue timeout settings.
- A single active platform IP-block enforcement hook in the Flask request path.
- A bounded short-lived per-process cache for IP-block decisions; block/unblock writes invalidate the local entry.
- Baseline HTTP security headers, with HSTS only on HTTPS responses.
- A separate worker entry point that does not import the web application.
- Read-only k6 health and authenticated API profiles.

These are engineering controls, not a measured 100K capacity result.

## Connection budget

Every web worker and every separate job process can create its own MongoDB client and pool. Plan the connection ceiling using:

`maximum possible connections ≈ web processes × maxPoolSize + worker processes × maxPoolSize + cron/job processes × their client pools + operational reserve`

Do not increase Gunicorn workers or `MONGO_MAX_POOL_SIZE` independently. Set values only after checking the MongoDB service's connection limit and measuring pool wait. `minPoolSize` should remain low unless measurements justify a larger warm pool.

Current conservative defaults are starting values. They are not certified optimal settings for Render or the current MongoDB plan.

## Required infrastructure decisions for large traffic

1. Confirm the Render instance type and number of web instances that the budget supports. One small/free web instance is not a 100K-concurrency architecture.
2. Confirm MongoDB provider, cluster tier, connection cap, storage, index health, backup policy, and region/network latency.
3. Put edge-level WAF and rate limits in front of authentication, password-reset, public search, upload, and expensive AI/proxy endpoints. Use a shared rate-limit store such as Redis only after a managed instance, budget, and failure policy are provisioned.
4. Keep heavy imports, notifications, report generation, and other long-running operations off request threads. The existing isolated worker is a first step; a durable queue with idempotent tasks, retry policy, dead-letter handling, and distributed job leases is still required before adding worker replicas.
5. Add a specialist ASGI service only when profiling identifies an async-I/O workload that materially benefits. Do not split core domain logic or create a second identity/database system.

## Security and isolation gates

- Preserve explicit CORS origins and verified custom-domain checks; never replace them with wildcard credentialed CORS.
- Verify current-user authorization and tenant ownership at the route/query layer. A client-supplied school or business identifier is a selector, not proof of access.
- Test that a user from School A cannot read or mutate School B's students, fees, attendance, staff, or reports, and that business tenant boundaries behave the same way.
- Apply edge rate limits before adding application-level distributed quotas.
- Keep secrets in the deployment secret store. Never copy live credentials into workflow YAML, documentation, or test logs.
- Keep file uploads, webhook handlers, M-Pesa callbacks, and offline-sync mutations bounded and idempotent.

## Staging test sequence

1. Deploy the branch to an isolated staging service with a non-production MongoDB database.
2. Verify `/health`, auth, representative Elimu and Biashara read routes, and background worker startup.
3. Run `tests/load/health-smoke.js`.
4. Run `tests/load/authenticated-read.js` with a representative authenticated GET endpoint and tenant test account.
5. Increase concurrency progressively: 25 → 50 → 100 → 250 → 500 → 1,000 virtual users. Stop on sustained error-rate or latency threshold breach.
6. Run mixed read/write and multi-tenant tests in an isolated test environment only after the read profile is stable. Use synthetic test data and idempotency keys.
7. Simulate MongoDB latency/unavailability, external provider timeouts, worker restarts, and network loss during offline sync. Confirm retries do not duplicate payments or mutations.
8. Publish measured throughput, p50/p95/p99 latency, error rate, CPU/memory, MongoDB connections, pool wait, slow queries, queue age, and recovery time.

A single load generator should not be assumed to generate 100,000 simultaneous users reliably. Higher-level tests require distributed generators and an approved infrastructure budget.

## Background worker environment

The Render worker is a separate service and does not inherit the web service's environment. It requires:

- `MONGO_URI`: same authoritative MongoDB cluster, stored as a Render secret.
- `MONGO_DB_NAME`: `revelacode` unless the shared environment uses a different configured database.
- `IMPORT_SDA_Q3_2026`: leave `false` unless the importer is deliberately being run.
- Any additional integration secrets required by the daily news/notification tasks should be configured only if those tasks require them.

The worker now imports `backend.background_jobs`, not `main.py`; it therefore does not need Google OAuth, Resend, public CORS origins, or the web-only route configuration merely to start. Keep the worker at one instance until jobs use a distributed lease/queue. Failed daily pipeline runs are retried on the next hourly loop.

## Honest release status

The code changes in this branch improve request-path efficiency, security defaults, and process isolation. They do **not** complete an end-to-end route/tenant audit, add a distributed durable queue, enable shared rate limiting, complete Redis/Celery provisioning, or demonstrate 100,000 concurrent users.

Do not merge or advertise a 100K concurrency guarantee until CI passes, staging deployment is verified, tenant-isolation tests pass, load tests are run, and the bottlenecks have been measured and resolved.
