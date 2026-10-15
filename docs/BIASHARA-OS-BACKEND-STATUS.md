# Biashara OS backend implementation status

**Working branch:** `biashara`  
**Last validation scope:** backend compile checks and the Biashara website, schema, commerce, outbox, finance, automation and tenancy suites.

This document records code paths present on the branch. It does not assert production deployment, provider approval, tax certification or successful real-money settlement.

## Implemented on this branch

### Canonical commerce and inventory

- Order totals and line snapshots use server-side catalogue values; customer and product IDs are checked against the selected business.
- Order creation supports an optional `Idempotency-Key`, reserves available stock, and records stable inventory movement keys. Fulfilment consumes reservations and supported cancellation releases them.
- Manual stock changes use compare-and-set writes, respect stock reserved for open orders, retain a pending mutation marker for recovery, and create auditable stock movements.
- Product stock edits use the inventory movement path. A product with active reservations cannot be archived.
- POS sales use the canonical order lifecycle. The entered amount/product description is not authoritative. A manually entered M-Pesa/card/bank reference is not treated as provider verification.

### Durable event outbox and Sync Centre

- Event IDs are stable and tenant-scoped; payloads are allowlisted to avoid shipping arbitrary request bodies or secrets.
- Events support leases, lease-expiry recovery, bounded retries, dead-letter state and manual replay.
- Source-document manifests can repair a failed outbox insert/acknowledgement.
- Authenticated APIs are registered under `/api/jumuiya/biashara/sync` for status, event listing, retry and source repair.
- The durable queue is the integration foundation. This branch does **not** imply a connected external WooCommerce, WhatsApp, M-Pesa or accounting channel, and it does not claim exactly-once network delivery.

### Invoices, payment evidence and provisional journal

- Invoices are sourced from canonical orders; numbering is idempotent and invoice lifecycle changes are explicit.
- Cash can be recorded as a staff-attested manual receipt. External-payment references remain unverified until a real provider adapter/status check proves the result.
- The operational journal uses integer minor units and validates that debits equal credits; journal entries are immutable and unique per source.
- Invoice issue posts receivable / unclassified commercial revenue; allocated manual cash posts cash / receivable; expenses post operating expense / unclassified funding/payable.
- These are **provisional operational postings**. The chart does not yet constitute a complete accountant-approved chart of accounts, tax calculation, financial close workflow or certified accounting product. The API states that tax/eTIMS is not configured.

### Owner-controlled automation

- Rules are versioned and limited to known trigger/action pairs; arbitrary scripts are not supported.
- Order events can create internal fulfilment tasks; invoice/payment events can create review tasks; low-stock events can create reorder suggestions.
- Reorder suggestions require approval. Approval only marks the suggestion ready for a human action; it does not create/send a purchase order.
- Payment review tasks do not mark a payment verified or change its provider-verification state.
- Runs and tasks use stable keys for safe event redelivery. Failed dispatches are visible as retry work.
- APIs are registered under `/api/jumuiya/biashara/automation`.

### Multiple businesses, staff roles and authorization

- `X-Biashara-Business-ID` selects a business only after backend membership validation; a client-supplied ID is not authorization.
- An owner with several businesses must explicitly select one for business-scoped operations.
- Memberships use existing verified RevelaCode user IDs; this does not create a second identity system.
- Role permission checks now cover primary product, stock, order, sale, expense, invoice/payment, analytics, intelligence, sync and automation endpoints.
- Business context is an allowlisted projection and does not expose the internal owner user ID.
- The unique one-business-per-owner index is replaced with a non-unique owner index; membership has a unique business/user index.
- The CLI migration seeds/reconciles owner membership rows only. Child records already scoped by `business_id` are never reassigned automatically.

## Multi-business migration procedure

Run from the repository root in the intended environment. Confirm `MONGO_URI` and `MONGO_DB_NAME` point at the correct database.

1. **Preview only (default):**

   ```powershell
   python -m backend.scripts.migrate_biashara_memberships --dry-run
   ```

   Review `businesses_missing_owner`, `businesses_missing_stable_id`, child collections with missing/unknown `business_id`, and truncated scan indicators. Do not infer ownership for those records.

2. **Apply the unambiguous owner membership backfill:**

   ```powershell
   python -m backend.scripts.migrate_biashara_memberships --apply
   ```

   The command first runs the declared index setup and then creates or repairs owner memberships. Re-running is intended to be idempotent. The command does not delete business or child records.

3. **Review rollback candidates without changing data:**

   ```powershell
   python -m backend.scripts.migrate_biashara_memberships --plan-rollback
   ```

   This is a plan only. Review each candidate and any recorded prior membership state before authorizing a rollback. It never deletes or demotes a membership automatically.

Back up the database and verify a restore before applying this to production. Run the migration in a maintenance window if your traffic volume makes index changes or membership backfills disruptive.

## Business selection and team APIs

- `GET /api/jumuiya/biashara/businesses`: list accessible business summaries.
- `POST /api/jumuiya/biashara/businesses`: create an additional business for the existing verified identity.
- `GET /api/jumuiya/biashara/businesses/<business_id>/members`: list active team members.
- `POST /api/jumuiya/biashara/businesses/<business_id>/members`: attach an existing verified user ID with a predefined non-owner role.
- `DELETE /api/jumuiya/biashara/businesses/<business_id>/members/<member_user_id>`: revoke that user's membership.
- For business-scoped workspace APIs, send `X-Biashara-Business-ID: <id>` after selecting a business from the list endpoint.

Role permissions are defined in `backend/jumuiya/biashara/tenancy/service.py`. Owner membership cannot be granted or revoked through the staff endpoint. Business members cannot access another tenant simply by changing an ID.

## Verification

The branch CI workflow runs:

```bash
python -m compileall -q backend/jumuiya/biashara backend/jumuiya/core
python -m pytest -q \
  backend/tests/test_biashara_website.py \
  backend/tests/test_schemas.py \
  backend/tests/test_biashara_commerce_lifecycle.py \
  backend/tests/test_biashara_outbox.py \
  backend/tests/test_biashara_finance.py \
  backend/tests/test_biashara_automation.py \
  backend/tests/test_biashara_tenancy.py
```

See the [Biashara validation workflow](https://github.com/musombi123/RevelaCode-Backend/actions/workflows/biashara-storefront-check.yml) for the current run result on the branch. A successful CI run validates these automated tests; it does not replace staging tests against a real MongoDB replica set or provider sandbox.

## Still required before a paid pilot

- Run the membership migration in staging and verify multi-business switching end to end from the frontend.
- Exercise access controls on every API route with each role using a real authenticated test account; keep the negative cross-tenant suite growing as resources are added.
- Add encrypted provider-secret storage, credential rotation and least-privilege integration connections before accepting provider credentials.
- Implement a real M-Pesa/payment provider adapter with provider-specified verification and reconciliation; test duplicates, malformed callbacks, reordering and downtime.
- Complete the actual KRA-approved eTIMS onboarding/certification path before claiming eTIMS compliance.
- Add a real worker process and operational monitoring for provider sync; this branch currently provides durable queue primitives and internal automation dispatch, not a complete external-channel sync service.
- Review the operational chart of accounts, VAT/tax treatment, refunds, settlement entries and closing controls with a Kenyan accountant before using this journal as formal books.
- Add domain verification/rendering/SEO acceptance tests and subscription entitlement enforcement against the deployment environment.
