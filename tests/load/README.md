# Staging load tests

These profiles are read-only. Run them against staging with a GET endpoint that is safe to request repeatedly.

## Health smoke

```powershell
k6 run -e BASE_URL=https://YOUR-STAGING-HOST tests/load/health-smoke.js
```

## Authenticated read profile

Choose an endpoint that represents a real read workload and obtain a staging token for a test account. Keep tokens out of source control and command history where possible.

```powershell
$env:BASE_URL = "https://YOUR-STAGING-HOST"
$env:API_PATH = "/YOUR/READ-ONLY/ENDPOINT"
$env:ACCESS_TOKEN = "<staging-token>"
$env:TARGET_VUS = "250"
# Add only the tenant headers actually required by the selected API contract:
$env:TENANT_HEADERS_JSON = '{"X-School-ID":"<staging-school-id>"}'
k6 run tests/load/authenticated-read.js
```

If the endpoint does not use a school header, omit `TENANT_HEADERS_JSON`. For Biashara or another tenant type, supply the exact existing header required by that route. Do not invent or change API contracts to make the load profile work.

The profile ramps through 25 and 100 virtual users before reaching `TARGET_VUS` (default 250), then ramps down. It checks p95/p99 latency and request failure rate. This is a staging profile, not proof of 100,000 concurrent-user capacity.

## Progressive capacity programme

Run at 25, 50, 100, 250, 500, then 1,000 virtual users only after the previous level is stable. Increase further only with a distributed load generator and an approved test window. Capture application CPU/memory, Gunicorn worker saturation, MongoDB connection/pool wait, query latency, and provider errors for every run.

Do not stress production without an explicitly approved test window, a traffic cap, monitoring, and a rollback/stop procedure. Never target POST/PUT/PATCH/DELETE endpoints with these profiles.
