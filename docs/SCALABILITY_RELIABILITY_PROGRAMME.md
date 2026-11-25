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
