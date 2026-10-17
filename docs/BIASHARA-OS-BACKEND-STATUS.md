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

### Encrypted integration configuration

- The API is registered at `/api/jumuiya/biashara/integrations` and accepts named WooCommerce, WhatsApp Cloud API and M-Pesa Daraja connection configurations. New connections default to disabled. A DELETE endpoint removes the encrypted connection record.
- Credential bundles are encrypted with Fernet before the MongoDB insert/update. Only credential field names and redacted configuration status are returned; ciphertext and raw credentials are never included in normal API responses or audit payloads.
- The server fails closed when no valid encryption key is configured. The key must be kept in the hosting environment/secret manager, backed up securely, and never committed to the repository.
- A multi-key ring supports rotation using `BIASHARA_INTEGRATION_ENCRYPTION_KEYS` (JSON mapping key IDs to Fernet keys) and `BIASHARA_INTEGRATION_CURRENT_KEY_ID`. Keep old keys available until every connection encrypted with them has been re-encrypted; changing a key without preserving the old key makes those credentials unreadable.
- Connections begin disabled. The registry reports `configured_unverified` until a supported connectivity test succeeds; test status and timestamp are surfaced without exposing credentials. WooCommerce connectivity testing uses a read-only products request. WhatsApp Cloud and the general integration registry do not claim a connection test is complete where no provider-specific test exists.
- WooCommerce supports a read-only catalog preview and an explicit selected-product import under `/<connection_id>/woocommerce/products/preview` and `/<connection_id>/woocommerce/products/import`. The owner/manager must configure `metadata.store_currency` only after checking the store settings; imports are blocked unless it matches the selected business currency. Import currently handles published simple products only. External HTML descriptions are converted to text, SKU conflicts are skipped, mappings are idempotent and source markers allow recovery if the product insert succeeds before the mapping acknowledgement.
- Catalog import deliberately **does not import stock or cost price**. It creates the local product with zero stock, because inventory source-of-truth and reconciliation must be agreed before either system overwrites the other.
- An owner/manager can explicitly push selected local product IDs using `POST /<connection_id>/woocommerce/products/sync`. Supported outbound fields are name, SKU, price and description. The adapter GETs the remote product first, compares its external version and tracked field snapshot with the last acknowledged version, and records a conflict without writing if the remote version changed.
- Before a PUT, the intent is persisted as `outcome_unknown`. Timeouts, server errors and un-verifiable successful responses are reconciled with GET; the next request never blindly repeats the PUT. Stock quantities and cost price are not sent.
- Mapping health is available at `GET /<connection_id>/woocommerce/products/mappings`. A conflict can be resolved explicitly at `POST /<connection_id>/woocommerce/products/<local_product_id>/sync-conflict/resolve`: `accept_remote` applies only name/SKU/price/description locally, while `push_local` requires the exact fields the operator chooses and rebases against the latest remote version. If the remote version changes again during resolution, the action stops and refreshes the conflict.
- WooCommerce order import, return/refund synchronization and unattended background sync remain unimplemented; the current product sync is a selected, explicit operation, not a bidirectional autonomous connector.
- Inbound webhook delivery is implemented for enabled WooCommerce and WhatsApp Cloud connections. WooCommerce signatures are verified from `X-WC-Webhook-Signature`; WhatsApp uses the `hub.challenge` / verification-token handshake and `X-Hub-Signature-256`. Verified webhook bodies are encrypted before persistence and deduplicated by provider delivery key (WooCommerce) or body digest (WhatsApp). The inbox returns redacted summaries only. Events start as `pending_review` with `effects_applied: false`; acknowledgement/dismissal does not import or mutate commerce/payment records.
- A separate Daraja STK path exists under `/api/jumuiya/biashara/finance/mpesa`. It verifies the configured callback source IP, correlates checkout/merchant IDs, validates receipt, amount and phone match, uses invoice-balance reservations, quarantines ambiguous outcomes and does not treat a status query or browser redirect as proof of payment. This still requires real Safaricom merchant credentials, environment-specific callback source IP configuration and staging verification; it is not evidence of live settlement reconciliation or eTIMS compliance.
- Routes: `GET/POST /api/jumuiya/biashara/integrations`, `PATCH /<connection_id>`, `PATCH /<connection_id>/enabled`, `DELETE /<connection_id>`, `POST /<connection_id>/woocommerce/test`, `GET /<connection_id>/woocommerce/products/preview`, `POST /<connection_id>/woocommerce/products/import`, `POST /<connection_id>/woocommerce/products/sync`, `GET /<connection_id>/woocommerce/products/mappings`, `POST /<connection_id>/woocommerce/products/<local_product_id>/sync-conflict/resolve`, `GET /webhook-deliveries`, `POST /webhook-deliveries/<delivery_id>/decision`, and provider webhook routes at `/<connection_id>/webhook`. Webhook routes require provider proof rather than a user JWT.

Generate a fresh Fernet key once in a trusted environment and store it in the platform's environment secret manager:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the resulting value as `BIASHARA_INTEGRATION_ENCRYPTION_KEY` and keep a secure backup. For a staged key rotation, configure both old and new keys in `BIASHARA_INTEGRATION_ENCRYPTION_KEYS`, set `BIASHARA_INTEGRATION_CURRENT_KEY_ID` to the new key ID, and re-encrypt connections by issuing a credentials update with an empty `credentials` object for each connection. Keep the old key in the ring until verification is complete.

### Custom-domain ownership claims

- An owner/manager can claim a fully qualified hostname through `POST /api/jumuiya/biashara/website/domains`. The response gives the TXT record name `_revelacode-verification.<hostname>` and a value prefixed with `revelacode-domain-verification=`.
- Publish that TXT value in the authoritative DNS zone, then call `POST /api/jumuiya/biashara/website/domains/<claim_id>/verify`. The backend resolves TXT records itself and compares the exact challenge token. Failed lookups remain pending and can be retried; a previously verified claim is demoted if the proof disappears on a later check.
- Claims are tenant-scoped and the hostname is unique across businesses. The owner can list claims at `GET /api/jumuiya/biashara/website/domains` and remove a claim with `DELETE /api/jumuiya/biashara/website/domains/<claim_id>`.
- A verified TXT record proves DNS control only. Every claim reports `domain_serving_status: not_configured`; this code does not configure CDN/hosting routing, issue TLS certificates, or claim that the custom hostname serves the storefront.
- DNS lookups use a short resolver timeout; failures return a retryable pending state without exposing resolver exceptions. Configure outbound DNS access and monitor resolver health in the deployment environment.

### Public storefront SEO metadata

- The public storefront response includes a separate `seo` object containing title, description, canonical path, Open Graph values, Twitter card metadata and a Store structured-data object.
- An absolute canonical URL is returned only when `BIASHARA_PUBLIC_BASE_URL` is configured as a plausible public HTTPS origin. The service never derives its canonical domain from the request Host header; otherwise it returns a relative canonical path and `canonical_url: null`.
- Contact details are included in structured data only when the website contact setting is enabled. Hero images are emitted in social metadata only when they use a valid HTTPS URL.
- The API serves only active businesses whose website is published. This metadata does not represent domain ownership verification: `domain_verification_status` remains `not_implemented`, and a production frontend still needs to render the returned meta tags/JSON-LD and add route-level sitemap/robots behavior.

### Revenue catalogue and entitlement visibility

- The existing revenue engine records transaction intents only; an intent is not a subscription and never proves payment.
- `GET /api/revenue/entitlements` (optionally `?hub=biashara`) returns the authenticated user's effective access snapshot.
- While `PRICING_STATUS` remains `draft` or the entitlement resolver's billing flag is false, the response stays on the free baseline, reports `billing_enabled: false`, and does not even query subscription records.
- The read-only resolver accepts paid access only from a separate subscription record that is active, payment-verified, has a provider reference and verification timestamp, has started but not expired, has not been revoked, and references a currently available plan.
- It does not create or activate subscriptions and does not enforce numeric plan limits. Feature/limit policy and verified checkout/webhook flows remain required before paid access can be enabled.

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
  backend/tests/test_biashara_tenancy.py \
  backend/tests/test_biashara_integrations.py
```

See the [Biashara validation workflow](https://github.com/musombi123/RevelaCode-Backend/actions/workflows/biashara-storefront-check.yml) for the current run result on the branch. A successful CI run validates these automated tests; it does not replace staging tests against a real MongoDB replica set or provider sandbox.

## Still required before a paid pilot

- Run the membership migration in staging and verify multi-business switching end to end from the frontend.
- Exercise access controls on every API route with each role using a real authenticated test account; keep the negative cross-tenant suite growing as resources are added.
- Extend WooCommerce from controlled catalog import into outbound product update sync and order import/reconciliation. External source/version conflict policies and local stock ownership must be visible before writes.
- Add provider-specific WhatsApp connectivity and message-send workflows with consent, opt-out, template and approval rules; current webhook handling only verifies and queues for human review.
- Exercise the Daraja path in Safaricom sandbox and production onboarding environments with real merchant credentials, source-IP verification at the trusted edge and outage/replay drills; do not claim real settlement reconciliation until it is implemented and tested.
- Complete the actual KRA-approved eTIMS onboarding/certification path before claiming eTIMS compliance.
- Add a real worker process and operational monitoring for provider sync; this branch currently provides durable queue primitives and internal automation dispatch, not a complete external-channel sync service.
- Review the operational chart of accounts, VAT/tax treatment, refunds, settlement entries and closing controls with a Kenyan accountant before using this journal as formal books.
- Add a verified subscription lifecycle, provider-confirmed payment updates, machine-readable feature/limit policies and paid-feature enforcement before billing or paid entitlements are enabled.
- Configure production custom-domain routing/TLS after DNS ownership verification, render SEO metadata in the frontend, and add public-route sitemap/robots integration.
