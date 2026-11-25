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
