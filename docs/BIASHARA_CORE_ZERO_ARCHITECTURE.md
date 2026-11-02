# Biashara OS — Core-Zero architecture

## Product invariant

Biashara OS is not a second operating system. It is a business launcher on the shared RevelaCode Core-Zero runtime, in the same way Elimu is the education launcher. Core-Zero owns identity, company membership, permissions, audit history, offline transport, sync contracts, notifications and integration boundaries. Elimu and Biashara keep their own domain workflows.

Do not fork the entire Elimu application into a second product. Reuse shared services and build a new module only where the business domain differs.

## Architecture layers

### Layer 1 — Core-Zero platform services

- Identity and authenticated account sessions.
- Tenant registry and verified domain-to-company resolution.
- Role and permission evaluation on the backend.
- Audit trail and operational event history.
- Offline mutation outbox and synchronization protocol.
- Notification and integration gateways.
- Shared reporting and observability contracts.

### Layer 2 — Industry template

The company profile persists one validated template key:

| Template | Enabled workflow families |
|---|---|
| general | Sales, customers, inventory, finance, HR, debts, integrations, website |
| retail_shop | POS/sales, inventory, customers, finance, suppliers, debts |
| hardware | Sales, stock, supplier purchases, finance, debts |
| factory | Sales, inventory, production, machines, quality, HR, finance |
| salon | Appointments, services, stock, sales, HR and finance |
| professional_services | Invoicing, customer records, projects, HR and finance |
| school | Elimu launcher; education workflows remain in Elimu |

Templates change navigation, terminology and defaults. They never grant backend access. A hidden module is not an authorization control.

### Layer 3 — Company role

The membership role is normalized to a server-side permission set. UI display labels do not grant access. The backend validates the user's active ownership or membership for every operation and resolves the selected company from a verified request context.

## Tenant and data model

The central RevelaCode database retains:

- jumuiya_businesses — company profile and verification state.
- jumuiya_biashara_memberships — company membership and role.
- jumuiya_biashara_invitations — single-use invitation records.
- jumuiya_biashara_active_business — selected-company preference.
- jumuiya_biashara_tenants — tenant database registry.
- jumuiya_biashara_domains — verified company hostname registry.
- The minimal payment callback index used to locate an M-Pesa checkout's tenant.

Each company has its own MongoDB database in the existing MongoDB cluster. The database name is derived from the business ID using a SHA-256 prefix:

revelacode_biz_<24-hex-character-hash>

Never use a company slug as a database name or trust a client-supplied database name.

Operational records (products, customers, orders, sales, expenses, invoices, payment intents, inventory movements, production batches, quality checks, machines, employee records and attendance) are written to the company database. Identity, membership, company profile and invitations remain central.

### Tenant provisioning lifecycle

1. Resolve a company from the authenticated user's active membership/ownership, optional X-Business-ID, or a verified company Origin.
2. Reject a company ID that conflicts with the verified Origin.
3. Claim the provisioning/migration lease in the central registry.
4. Create or open the deterministic company database.
5. Copy legacy company-owned records by original document ID using idempotent upserts. Never delete the source records during this migration.
6. Create tenant-scoped indexes and write the tenant schema version.
7. Mark the registry active and release the lease.
8. Register the company hostname as pending DNS verification; activate it only after DNS and serving-platform checks pass.

Concurrent requests must not run the same migration simultaneously. A tenant-owned collection must fail closed if no verified company context exists. Background workers must pass an explicit business ID to tenant services; they must not depend on Flask request-local state.

## Data flow examples

### Product sale

Authenticated user → tenant/permission check → sale validation → inventory movement → payment allocation → invoice/reporting events → audit

All writes and reads use the same company ID. The backend must calculate price and totals from server-side catalogue data.

### Factory production

Raw-material inventory → production batch → actual output + wastage + recoverable by-products → quality hold → quality decision → finished-goods stock

Raw material is deducted when a batch begins. Completion must account for the full input. Finished goods become sellable only after a passing quality inspection. A rejected batch remains unreleased.

### M-Pesa invoice collection

Invoice → idempotent STK intent → shared Daraja adapter → callback correlation → exact checkout query → callback receipt/amount/phone validation → invoice allocation

An STK prompt is not proof of payment. Ambiguous submissions remain unresolved and hold the invoice slot until reconciled. A payment allocation is not an eTIMS acceptance.

### Offline operation

Local PWA/native store → user/tenant-scoped queue → stable mutation ID → reconnect → authenticated backend tenant check → server idempotency → acknowledgement

The browser queue preserves the original company ID and idempotency key. Sensitive HR, payment, invoice, credential and identity paths are not blindly cached or queued. The current factory operational mutations use the safe replay path; HR clocking and payment initiation remain online-only until a secure offline protocol is implemented.

## Shared implementation boundaries

Reuse the existing RevelaCode backend, existing authentication and existing sync transport. Do not add another database technology or a second backend. Use shared Daraja, notifications and Core-Zero adapters where already present. Build separate workflow modules only for real domain differences.

## Deployment gates

- Configure the MongoDB deployment for transactions/replica-set support before enabling atomic factory stock movements and invoice allocation.
- Configure wildcard DNS and Render custom-domain routing before marking company subdomains active.
- Set M-Pesa credentials and the exact public HTTPS callback URL in the backend environment; complete controlled callback/query verification before production.
- Keep eTIMS submission disabled until the applicable KRA OSCU/VSCU integration testing, vetting and certification gates are completed.
- Keep WhatsApp business commands disabled until webhook verification, phone-to-user binding, company authorization and command-level tests exist.

## Non-negotiable security rules

- A business ID from a browser is a selector, not authority. Membership/ownership is checked server-side.
- All operational reads, writes, exports, caches, jobs and callbacks must be company-scoped.
- No cross-tenant fallback to the shared database is allowed for tenant-owned collections.
- Payment and tax statuses must be distinct and evidence-based.
- No irreversible or high-impact employment decisions are performed automatically.
- Preserve Elimu API contracts and run Elimu regression tests for any change to shared Core-Zero services.
