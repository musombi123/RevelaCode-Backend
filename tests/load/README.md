# RPSVI staging load tests

These profiles are read-only and deliberately require an exact staging hostname. They reject known production hosts and refuse to run without `EXPECTED_STAGING_HOST`.

## Health smoke

PowerShell:

```powershell
$env:BASE_URL = "https://YOUR-STAGING-HOST"
$env:EXPECTED_STAGING_HOST = "YOUR-STAGING-HOST"
k6 run tests/load/health-smoke.js
```

## Authenticated read profile

Select a reviewed, repeatable GET endpoint. Obtain a bearer token for a dedicated synthetic staging account. Do not place a production token in this profile.

```powershell
$env:BASE_URL = "https://YOUR-STAGING-HOST"
$env:EXPECTED_STAGING_HOST = "YOUR-STAGING-HOST"
$env:API_PATH = "/YOUR/REVIEWED/READ-ONLY/ENDPOINT"
$env:ACCESS_TOKEN = "<staging-token>"
$env:TARGET_VUS = "25"
# Supply only the tenant selector/header actually required by that route.
$env:TENANT_HEADERS_JSON = '{"X-School-ID":"<synthetic-school-id>"}'
k6 run tests/load/authenticated-read.js
```

If the endpoint does not require a school header, omit `TENANT_HEADERS_JSON`. For Biashara or another tenant, use the exact existing route contract. Do not invent or change API contracts for a load script.

## Limits and safety

- The authenticated profile requires a token and is capped at 1,000 VUs on one generator.
- Increase 25 → 50 → 100 → 250 → 500 → 1,000 only after review of the previous run.
- The health profile is not an authenticated user simulation and is not evidence of hub capacity.
- These scripts only issue GET requests; choose an endpoint known to be safe for repeated reads.
- Use a named operator, approved test window, live monitoring and stop thresholds.
- Distributed tests above 1,000 VUs require an approved design, budget and separate runbook.
- Never target production. Do not stress the live API without an explicit written test window and capacity approval.
