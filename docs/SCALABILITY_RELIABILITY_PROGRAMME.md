# RevelaCode Scalability and Reliability Programme

## Scope and non-negotiable architecture

This programme hardens the existing RevelaCode backend in six phases. It retains the existing Flask application and API contracts, the existing authentication and authorization model, and one shared MongoDB database. Jumuiya continues to use the existing database and its `jumuiya_` collection namespace. No second database or parallel identity system is introduced.

FastAPI, Redis, Celery, or other infrastructure is introduced only after the relevant workload and deployment requirements are verified. A dependency is not considered an improvement merely because it is popular.

## Phase 1 — Baseline audit

### Confirmed repository observations

- The production Render web service currently starts with `python main.py`.
- `main.py` starts the Flask development server under its `__main__` guard. The production Render command therefore does not currently use the already-installed Gunicorn package.
- `main.py` calls `start_background_jobs()` at module import time. That starts an SDA importer thread and a daily-runner thread. Starting multiple Gunicorn worker processes without changing this lifecycle would start those jobs in every worker process.
- Render already defines separate Cron services for market-data refresh, Elimu student lifecycle, and Elimu teacher reminders. The importer and daily-runner responsibilities must be reconciled with these services before moving to multi-worker serving.
- `backend/db.py` creates a module-level PyMongo `MongoClient`, immediately pings MongoDB, and checks/creates several collections during module import. This is a shared connection per Python process; pool sizing and process multiplication must be included in capacity planning.
- The MongoDB client currently sets server-selection, connection, and socket timeouts to 10 seconds. Pool sizing and wait-queue behaviour have not yet been measured.
- Jumuiya obtains collections through `backend.db.get_db()`, enforcing the existing shared MongoDB database and `jumuiya_` prefix.
- `backend/jumuiya/core/database.py` contains a substantial central index registry, including tenant-scoped Elimu indexes for students, attendance, lessons, assignments and assessments. Existing indexes must be compared with actual query shapes and production data before adding or changing indexes.
- The application has explicit CORS handling, including dynamic verification of school and business custom domains. This must be preserved; wildcard CORS is not an acceptable performance shortcut.
- The repository already pins Flask, PyMongo and Gunicorn. Redis, Celery, FastAPI, HTTPX, Sentry and OpenTelemetry are not present in the inspected requirements file.

### Risks to resolve before production scaling changes

1. **Background-job duplication:** import-time thread startup is incompatible with naive multi-worker deployment.
2. **Database startup work:** collection existence checks and connection ping occur during module import; startup cost and multi-process effects need measurement.
3. **Connection multiplication:** each Gunicorn worker/process will own its own MongoClient pool. Worker count and MongoDB pool limits must be sized together.
4. **Custom-domain CORS lookup:** verified-domain checks perform database reads. Measure frequency and latency before deciding whether a bounded cache is appropriate.
5. **Index safety:** the existing index helper can drop/recreate indexes when options differ. Any index migration must be reviewed for data impact, uniqueness violations, and deployment locking.
6. **Unknown query hotspots:** no query profiler or representative production workload evidence has yet been collected. Do not claim capacity or add speculative indexes.

## Six-phase delivery plan

### Phase 1 — Audit and baseline
- Map routes, auth boundaries, tenant-scoped queries, database access, background jobs, existing tests and deployment services.
- Record baseline request latency, error rate, database operation latency, and resource usage where observable.
- Identify secret exposure risks without printing or copying secret values.
- Deliver an audit report and prioritized change plan.

### Phase 2 — Performance foundation
- Move production serving to a measured Gunicorn configuration only after background-job lifecycle is made safe.
- Tune MongoClient pool and timeout settings against the selected instance and MongoDB deployment.
- Optimize evidenced slow queries, pagination and response payload sizes.
- Introduce Redis only for identified cache, rate-limit or coordination requirements.
- Preserve current API response shapes and status codes.

### Phase 3 — Security hardening
- Verify authentication and authorization on sensitive routes.
- Test cross-school and cross-business tenant isolation.
- Apply endpoint-specific rate limits and safe request validation.
- Preserve the explicit CORS allow-list and verified custom-domain rules.
- Ensure secrets are supplied through deployment secret stores, not repository files or workflow logs.

### Phase 4 — Network and workload resilience
- Move long-running and scheduled work out of HTTP request handlers.
- Use a durable queue only where retry and delivery semantics are defined.
- Add bounded timeouts, retry policies for safe/idempotent operations, and circuit breaking for external dependencies.
- Ensure payment and other mutation flows use idempotency and cannot be duplicated by retries.
- Preserve offline synchronization identifiers and conflict-handling contracts.

### Phase 5 — Specialist services
- Profile before introducing FastAPI or another service runtime.
- Add a separate ASGI service only for a clearly bounded workload that benefits from asynchronous I/O or independent scaling.
- Reuse shared domain logic and the existing identity/authorization model; do not create competing sources of truth.
- Document service ownership, internal authentication, timeout budgets and deployment topology.

### Phase 6 — Verification and capacity evidence
- Add automated correctness, security and regression tests.
- Run progressive k6 load tests with realistic Elimu multi-school and cross-hub traffic.
- Measure p50/p95/p99 latency, throughput, error rate, CPU, memory, worker saturation, MongoDB pool wait and database latency.
- Run dependency-failure and network-interruption tests.
- Publish tested concurrency and bottlenecks. Registered-user counts must not be represented as concurrent-user capacity.

## Safety and release gates

- Work on the `engineering/scalability-phase-1` branch; do not push unreviewed changes directly to `main`.
- Do not change production Render start commands until background jobs are safely separated and a tested worker configuration is ready.
- Do not run load tests against production without an explicit safe test window and bounded traffic.
- Do not add mandatory Redis/Celery/FastAPI dependencies before their deployment services and secrets are provisioned.
- Do not run destructive index migrations automatically in a production startup path.
- Every implementation phase must pass its targeted tests and preserve existing API contracts before merge.

## Current status

Phase 1 has begun. The findings above are based on the inspected repository files. Route-by-route authorization review, full query profiling, existing test-suite execution, secret-history scanning, and load testing remain outstanding. No capacity claim is made at this stage.


## Implementation progress on `engineering/scalability-phase-1`

### Implemented in this branch (pending CI and deployment validation)

- Production Render web command now uses the repository's already-installed Gunicorn through `gunicorn.conf.py`.
- Conservative Gunicorn defaults: 2 gthread workers, 4 threads per worker, 60-second timeout, graceful shutdown, keepalive, and worker recycling. Values are environment-configurable. These are starting defaults, not load-tested optimal values.
- Removed import-time invocation of `start_background_jobs()` from `main.py`. Gunicorn web workers no longer each start the legacy SDA importer and daily-runner threads.
- Added a dedicated Render background worker entry point that starts those existing jobs once in its own process.
- Added worker-specific MongoDB environment declarations. The deployment owner must confirm the Render worker has all additional runtime secrets/configuration needed by imported modules and the daily pipeline before enabling production deployment.
- Added configurable MongoClient pool and wait-queue settings with conservative defaults. Total connections must be budgeted across every web and worker process.
- Added AST-based process-lifecycle regression tests and a focused GitHub Actions workflow.
- Added a read-only k6 staging health smoke profile, with instructions that explicitly prohibit unapproved production stress tests.

### Phase status — honest assessment

| Phase | Status | Remaining gate |
|---|---|---|
| 1. Backend audit | In progress | Full route/auth/tenant query inventory, secret-history review, test baseline and representative query profiling |
| 2. Performance foundation | Partially implemented | CI, Render worker environment review, MongoDB pool sizing and staging measurements; Redis cache not introduced without a provisioned Redis service and cache design |
| 3. Security hardening | Audit started | Endpoint-by-endpoint auth/tenant review, rate-limit design and tests, input/file validation review, security headers and audit coverage |
| 4. Network/workload resilience | Partially implemented | Worker isolation only; durable queue, retry/circuit-breaker policies and sync failure tests remain |
| 5. Specialist services | Architecture decision | No FastAPI service added yet. No profiling evidence currently justifies a second runtime; revisit after Phase 2 measurements |
| 6. Performance verification | Harness started | Run CI, execute k6 against staging, then add realistic authenticated multi-tenant scenarios and report measured capacity |

### Deployment warning

The Render worker service is a separate process and does not automatically inherit environment variables configured only on the web service. The blueprint declares `MONGO_URI`, `MONGO_DB_NAME`, and `IMPORT_SDA_Q3_2026`; operators must verify any other environment variables required by application imports and `backend.daily_runner` before deploying/enabling this worker. Do not remove the old job execution path from production until the worker is configured and confirmed healthy.

### Not yet claimed

No Redis, Celery, FastAPI, Flask-Limiter or circuit-breaker package has been installed. No production load test has run. No 100,000-user or concurrency capacity claim is made.


## Follow-up implementation on `engineering/scalability-completion`

The following changes extend the initial foundation while retaining Flask, the existing shared MongoDB database, and current API contracts:

- Extracted the legacy SDA import and daily-runner lifecycle into `backend/background_jobs.py`. The Render worker now imports that module directly and no longer imports `main.py` or registers the HTTP application just to run jobs.
- The daily runner now marks a date complete only after `run_pipeline()` reports success. A failed run is logged and retried by the next hourly pass.
- Removed the duplicate legacy IP-guard request hook and its duplicate blueprint registration. The active request-boundary guard and admin management routes use `backend.security_ip_guard`.
- Added a bounded per-process IP-block decision cache (default one-second TTL, maximum 4,096 entries). Manual block/unblock writes invalidate the local decision immediately. Database errors are not cached.
- Added a bounded custom-domain CORS verification cache (default five-second TTL, maximum 4,096 entries). It caches only origin-verification booleans; resolver/database failures are not cached and normal route authorization remains per-request.
- Added server-generated request correlation IDs, application timing headers, and structured slow-request warnings. The threshold is configurable with `REVELACODE_SLOW_REQUEST_THRESHOLD_MS` (default 1,000 ms).
- Added baseline response security headers: content-type sniffing protection, same-origin framing, referrer policy, camera/microphone/geolocation permissions policy, and HTTPS-only HSTS without `includeSubDomains`.
- Expanded the focused CI workflow to compile the new modules and test the worker boundary and response-header policy.
- Added a parameterized, authenticated, read-only k6 profile and a capacity/release runbook.

### Updated phase status

| Phase | Status | Outstanding production gate |
|---|---|---|
| 1. Audit | Partial | Complete the route-by-route authentication, authorization, tenant-query, secret-history and query-shape inventory |
| 2. Performance | Partial | Profile real staging traffic; size Gunicorn and Mongo pools against the actual Render/Mongo plans; optimize evidenced slow queries and pagination |
| 3. Security | Partial | Verify every sensitive route and cross-tenant boundary; provision/test edge WAF and endpoint-specific rate limits; review upload/webhook validation |
| 4. Resilience | Partial | Replace legacy thread loops with durable idempotent jobs, distributed leases, bounded retries and dead-letter/recovery handling before horizontal worker scaling |
| 5. Specialist services | Deferred by evidence | Revisit FastAPI only if profiling shows a workload that benefits from a separately scaled ASGI service |
| 6. Verification | Harness added; not measured | Run CI, deploy to staging, execute authenticated multi-tenant load and failure tests, and publish measured concurrency |

No Redis or Celery service has been provisioned, no distributed queue has been introduced, and no 100,000-concurrent-user capacity result is claimed. See `docs/CAPACITY_AND_RELEASE_GATES.md` before staging or production rollout.
