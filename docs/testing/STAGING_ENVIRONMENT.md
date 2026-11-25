# RPSVI staging environment

## Non-negotiable separation

The staging system must be a distinct deployment from production:

- Separate Render web service, e.g. `revelacode-staging-api`.
- Separate MongoDB database, named `revelacode_staging`, with a staging-only database user.
- Separate JWT/session secrets. Never copy the production signing secret into staging.
- Separate AI staging gateway and provider credentials/quotas, or keep AI calls disabled until an approved test key is configured.
- Separate email, SMS, WhatsApp, payment and webhook sandbox credentials. Default all external side effects to disabled.
- Separate test domain/host and frontend origin allow-list.
- Separate logs/metrics labels identifying environment and build SHA.

A database name alone is not sufficient isolation when production and staging share a privileged database user. Prefer a separate MongoDB project/cluster. If using the same cluster, create a staging database user restricted to the staging database only, and verify that the URI cannot access production collections.

## Render setup procedure

This is a manual infrastructure task; the repository change does not create Render resources.

1. Create a new Render Blueprint or web service from the backend repository.
2. Select the verification branch for the initial test deployment; do not point staging at `main` until the release is accepted.
3. Give it a unique service name and staging-only HTTPS hostname.
4. Use the existing Python build command: `pip install -r requirements.txt`.
5. Use the production WSGI server command: `gunicorn --config gunicorn.conf.py main:app`.
6. Set `FLASK_ENV=production` so staging uses production middleware, but set a distinct non-secret `REVELACODE_ENV=staging` marker for observability.
7. Add staging-only values for `MONGO_URI`, `MONGO_DB_NAME=revelacode_staging`, `JWT_SECRET`, service-to-service keys and any other required application secrets through Render's environment/secret interface.
8. Set `FRONTEND_ORIGINS` to the staging frontend only plus any explicitly approved local test origin. Do not add wildcard credentialed CORS.
9. Configure `REVELA_AI_URL` to the staging RevelaAI gateway only when that gateway exists and is protected with staging credentials. Otherwise disable AI-dependent test cases.
10. Do not create a background worker or cron service in the first staging deployment. The backend worker's daily pipeline can send notifications and perform external work. Add it only after all outbound effects are disabled/sandboxed and a single-run lease is verified.
11. Confirm Render logs show the staging build SHA and staging environment marker, not production values.

Render web-service environment variables do not automatically become available in a separate worker service. Every service needs its own explicit environment configuration.

## MongoDB safeguards

Before connecting the staging application:

- Verify the staging database user has no read/write access to production databases.
- Verify the target database name is exactly `revelacode_staging`.
- Confirm backups and retention for staging are independent of production.
- Use a separate staging cluster or restricted database user; do not use a production administrator URI.
- Check the MongoDB connection ceiling and total connection budget before increasing web instances or pool sizes.
- Never enable destructive index migrations or production-data imports for test setup.

The application currently creates a MongoClient and performs a ping during module import. A staging start failure caused by unavailable MongoDB should fail closed; do not point staging at production as a workaround.

## Synthetic accounts and test tenants

Create synthetic identities through the application's supported registration/invitation flows, or through a reviewed test-fixture tool once each collection's schema and validators have been confirmed.

Minimum initial fixture set:

| Tenant | Purpose | Synthetic contents |
|---|---|---|
| School Alpha | Tenant A access tests | Owner, bursar, registrar, teacher; small student/staff set |
| School Beta | Tenant B isolation tests | Different owner and staff; different student/staff set |
| Business Alpha | Biashara tenant test | Owner, manager, accountant, stock role; synthetic stock/items |
| Farm Alpha | Shamba workflow test | Test farmer and synthetic farm/crop records |
| Community test space | Jumuiya workflows | Test profile, circle and seeded posts clearly marked synthetic |

Use reserved test email domains such as `example.test`, non-routable/test phone values accepted by the app, and fake names/records. Do not use real student, parent, employee, farmer or customer data. Never create real payment transactions, send real invitations, or deliver messages to real recipients.

Do not insert guessed MongoDB documents directly. First verify the repository's actual schema, service methods, required fields and authorization flow. Record fixture IDs and ownership in a staging-only fixture manifest.

## Readiness checklist

- [ ] Staging hostname resolves over HTTPS.
- [ ] Exact staging host is recorded for `EXPECTED_STAGING_HOST`.
- [ ] Staging API health check succeeds.
- [ ] Staging database identity is verified and cannot access production data.
- [ ] At least two isolated school tenants and one business tenant exist.
- [ ] Synthetic users have distinct roles and permissions.
- [ ] Payment, email, SMS, WhatsApp, push notifications and outbound webhooks are sandboxed or disabled.
- [ ] Staging AI route targets the staging RevelaAI gateway only.
- [ ] Logs and dashboards distinguish staging from production.
- [ ] A rollback/stop procedure and named test lead are available.
- [ ] No staging worker is active unless its side effects have been reviewed.


## Independent Render Blueprint templates

Two separate templates are provided so staging resources are not appended to the production Blueprint:

- Backend: `render.rpsvi-staging.yaml` in the RevelaCode-Backend repository.
- AI gateway: `render.rpsvi-staging.yaml` in the RevelaAI repository.

Create each as a **new, independent Blueprint** in Render and select the corresponding branch and YAML path. Do not add either service to the production Blueprint. Render supports separate independent Blueprints from YAML and `autoDeployTrigger: off` disables automatic deployment; inspect the Blueprint preview carefully before applying it. The templates deliberately use the `0.5c-512mb` plan as a small always-on staging starting point, not as a 100K-user capacity tier. Confirm the current price in Render before applying it. [Render Blueprint reference](https://render.com/docs/blueprint-spec).

### Creation order and secret hand-off

1. Create the backend Blueprint first. In the Blueprint prompt, provide a MongoDB URI whose database user is restricted to the staging backend database. Do not provide the production URI.
2. Let Render generate the staging backend `JWT_SECRET`. Retrieve it through the protected Render environment interface; never place it in GitHub, YAML, chat or a tester document.
3. Provide a new, random staging-only `REVELAAI_SERVICE_KEY` when prompted. Save it in your organisation's secret manager. Enter the exact same value into both the backend and AI staging services.
4. Set `FRONTEND_ORIGINS` and `FRONTEND_URL` to the actual staging frontend origin only. Until a staging frontend exists, keep browser-origin access disabled or use an explicitly approved test origin.
5. Create the AI Blueprint. Set `REVELACODE_BACKEND_URL` to the actual HTTPS hostname of the staging backend (not production). Copy the staging backend's generated `JWT_SECRET` into the AI service only if a route in the AI platform requires it; never reuse the production key.
6. Provide a separate MongoDB URI for AI staging. The current RevelaAI Smart Memory service selects the database named `revelai`; use a dedicated staging cluster or a database user restricted to that isolated test database. Do not point this URI at production Smart Memory.
7. Provide a staging-only Gemini API key with a budget/quota appropriate for the capped benchmark. Do not add production provider keys or enable other providers yet.
8. Set AI `CORS_ORIGINS` to the exact staging frontend origin only. The application is changed so an `ENVIRONMENT=staging` process does not inherit production/default browser origins.
9. Wait until both services have been manually deployed and healthy. Confirm each service's reported build/commit and hostname. Verify the staging backend's configured AI URL resolves to the staging AI gateway and the AI gateway's auth verifier targets the staging backend.
10. Confirm no production email, SMS, WhatsApp, payment, OAuth, webhook, or scheduled-worker integration is configured. Do not create a worker or cron service for this first staging pass.

Render's `sync: false` values are prompted during initial Blueprint creation; adding a new `sync: false` key to an existing Blueprint later requires entering it manually in the service's Environment settings. Review every prompted value before saving. See [Render environment variable reference](https://render.com/docs/blueprint-spec#setting-environment-variables).

### Hostname allow-list for the load scripts

Expected initial hosts from the service names are:

- `revelacode-rpsvi-staging.onrender.com`
- `revelaai-rpsvi-staging.onrender.com`

Treat these as expected names, not proof that a service exists. Confirm the actual assigned hostname in Render before running k6 and set `EXPECTED_STAGING_HOST` to that exact host. The k6 scripts reject known production hosts, require HTTPS, require exact host equality and reject a non-origin URL with a path. Never place a real access token in a command transcript or source file.

### Important capacity caveat

The `0.5c-512mb` service plan is only a controlled initial staging foothold. It is not sized or validated for 100,000 concurrent sessions. Higher capacity gates require a separately budgeted staging environment with scaled app instances, adequate MongoDB capacity, distributed load generators and monitoring. The default staging plan should first be used to validate correctness and establish low-load latency.

The backend also isolates its CORS allow-list when `REVELACODE_ENV=staging` (or `ENVIRONMENT=staging`): it starts with no default origins and accepts only the explicitly configured HTTP(S) values from `FRONTEND_ORIGINS`. The production defaults remain unchanged for production and other non-staging environments. For the supplied frontend Blueprint, configure only `https://revelacode-rpsvi-frontend.onrender.com` after confirming the actual hostname.
