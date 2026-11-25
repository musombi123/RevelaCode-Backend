# RevelaCode operations, security and scalability

**Evidence snapshot:** 25 November 2026  
**Primary sources:** `render.yaml`, `gunicorn.conf.py`, `backend/db.py`, `docs/SCALABILITY_RELIABILITY_PROGRAMME.md`, `docs/CAPACITY_AND_RELEASE_GATES.md`, and `docs/PLATFORM_IP_GUARD.md`.

## 1. Current deployment shape

The checked-in Render Blueprint defines:

| Service | Current declared responsibility | Entry point / schedule |
|---|---|---|
| Web API | Flask API | Gunicorn: `main:app` |
| Background worker | Legacy scheduled/importer jobs isolated from HTTP app | `python -m backend.background_worker` |
| Market data refresh | Biashara market-data refresh | Every 6 hours |
| Elimu student lifecycle | Student lifecycle automation | Daily |
| Elimu teacher reminders | Teacher reminder processing | Every 5 minutes |

The repository's web start command is `gunicorn --config gunicorn.conf.py main:app`. Gunicorn defaults in source are conservative starting values: 2 gthread workers, 4 threads per worker, a 60-second timeout and worker recycling. These defaults are configurable. They are not load-tested optimal settings.

The background worker runs in a separate process and deliberately does not import the Flask web application. The capacity runbook warns that it should remain a single instance until coordination is distributed; multiple replicas could duplicate scheduled work if distributed leases/queues are not in place.

A Render YAML file is desired configuration. It does not, alone, prove the corresponding services are deployed, healthy, correctly provisioned or paid for at a particular tier. Deployment dashboard evidence is required for those claims.

## 2. MongoDB connection budgeting

The backend creates a PyMongo client per Python process. The current default maximum pool size is configurable and set to 20 in the checked-in database configuration. With multiple web workers, separate background processes and Cron services, total connections can multiply.

The rough planning model is:

```text
potential connections ≈
  web processes × pool size
  + worker processes × pool size
  + cron/job processes × their pool sizes
  + operational reserve
```

This is a planning bound, not a live connection count. Pool size, worker count and MongoDB limits must be tuned together against observed connection use, pool wait, database latency and the selected database tier.

## 3. Existing security controls identified in source

The source includes the following controls:

- Explicit browser-origin allowlisting and verified custom-domain checks.
- CORS preflight rejection for unsupported origins, methods and headers.
- One trusted proxy hop when the Render deployment environment is detected, with configurable trust.
- Baseline response security headers and HTTPS HSTS behavior.
- Request correlation IDs, application timing and slow-request warnings.
- Platform IP-block enforcement before ordinary routes, with audit events and failed-login metadata capture.
- JWT authentication and backend role/permission checks.
- Tenant membership and verified-company context requirements in Biashara.
- User-scoped service-to-service authorization for the RevelaAI context gateway.
- Input and business-rule validation across domain routes and schemas.

These are code controls, not proof of an independent penetration test or a complete security audit. The programme documents outstanding route-level authorization review, tenant-isolation tests, rate-limit coverage, upload/webhook review and secret-history review.

### IP guard boundary

The platform IP guard is an application-layer control that rejects requests at the Flask application boundary. Its documentation explicitly states that it does not change Render's Cloudflare edge rules, host firewall, Nginx or independent origins. It is not a substitute for a managed WAF or DDoS mitigation.

Do not publish private allowlisted IPs, abuse thresholds or administrative credentials in public research material.

## 4. Reliability and background work

The reliability programme separates long-running work from HTTP request processes and identifies the need for:

- durable job delivery;
- idempotency and safe retry semantics;
- distributed job leases before horizontal worker replication;
- bounded timeouts and retry policies;
- circuit breaking for external services;
- dead-letter and recovery handling;
- resilience tests for network interruption and external provider failure.

The repository's capacity runbook says Redis, Celery and FastAPI are not currently required by the implemented programme. No such component should be described as deployed merely because it appears in a future architecture discussion. Redis or a durable queue should only be introduced with a defined workload, service plan, failure policy and tested integration.

## 5. Capacity: what is and is not established

The platform has a goal of serving large traffic, but the checked-in capacity runbook explicitly says there is no measured evidence that the production deployment can sustain 100,000 concurrent users.

Three different targets must not be mixed:

- 100,000 registered accounts;
- 100,000 monthly active users;
- 100,000 simultaneous concurrent users.

They require different capacity models.

The current source controls—Gunicorn concurrency settings, MongoDB pool controls, short-lived bounded caches, request metrics and k6 test profiles—are engineering foundations. They are not benchmark results.

The documented verification path calls for a staging environment, representative authenticated multi-tenant scenarios, progressive virtual-user load, and measurements of throughput, p50/p95/p99 latency, error rate, CPU, memory, MongoDB connections, pool waits, slow queries and recovery. Higher-level tests require distributed load generators.

**External claim rule:** do not advertise a 100K concurrency guarantee, a specific requests-per-second value, an uptime SLA or a production readiness certification until a repeatable report demonstrates it on the target infrastructure.

## 6. Operational checklist

Before a partner or investor is told that the platform is production-ready, collect:

- Current Render service list, plan, region, running commit and health status.
- MongoDB provider, tier, region, connection ceiling, indexes, backups and restore test.
- Background worker and Cron deployment status.
- Dependency lock and vulnerability scan results with triage, not only raw scanner counts.
- Staging regression results and end-to-end API smoke tests.
- Tenant isolation/security test results.
- Load-test report with workload description and measured percentiles.
- Incident response, monitoring, alerting, backup retention and rollback procedures.
- Secret rotation and access-control evidence.

## 7. Known scale and security gaps

The repository's own runbooks identify these outstanding gates:

1. Complete route-by-route authentication, authorization and tenant-query review.
2. Complete secret-history review and document credential rotation.
3. Run representative query profiling and tune only evidenced hotspots.
4. Finish safe durable job coordination before horizontal worker scaling.
5. Provision and validate shared rate limiting / edge protection where required.
6. Test upload, callback and offline mutation validation/idempotency.
7. Run controlled staging load and dependency-failure tests.
8. Publish measured capacity, not an aspiration.

## 8. How a founder should explain the current position

A defensible statement is:

> RevelaCode is built on a Flask and MongoDB foundation with separate web, background-job and scheduled-service responsibilities. The codebase includes configurable request concurrency, database pool controls, explicit origin checks, scoped identity and security telemetry. We are treating 100,000-user scale as a target to validate, not a capacity claim. We will publish concurrency and latency figures after representative staging tests on the intended infrastructure.

That answer is stronger than a large unsupported number because it shows an understanding of constraints, risks and the evidence required.
