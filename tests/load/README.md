# RevelaCode API load checks

The k6 script in this directory is a read-only staging smoke/load profile.

## Run

Install k6, then run:

```bash
BASE_URL=https://YOUR-STAGING-API k6 run tests/load/health-smoke.js
```

PowerShell:

```powershell
$env:BASE_URL = "https://YOUR-STAGING-API"
k6 run tests/load/health-smoke.js
```

The initial profile ramps to 50 virtual users and checks the public `/health`
endpoint. It is a connectivity and baseline exercise, not proof of 50
concurrent authenticated users or production capacity.

Before testing authenticated Elimu, Biashara, Shamba or Jumuiya workloads,
prepare dedicated test tenants and synthetic data, define safe request rates,
and ensure payment, email, import, and other side-effecting endpoints are
excluded. Increase load progressively only after reviewing p95/p99 latency,
error rates, CPU/memory, Gunicorn worker saturation and MongoDB pool wait.

Never run stress tests against production without an approved test window.
