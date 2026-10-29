# Biashara OS and Small Biashara — implementation roadmap

## Product rule

Biashara OS uses the existing RevelaCode/Jumuiya backend and the existing Biashara workspace. It is configuration-driven, not a second operating system or a separate backend fork. Elimu and Biashara may share identity, permissions, audit logging, offline-sync contracts and notification infrastructure, while each hub keeps its own domain rules.

This branch introduces the first configuration step: an industry template, business scale and a simple/advanced workspace mode. It is **not** a claim that every planned module or external integration is already live.

## 1. Three architecture layers

### Tenant boundary
- Every business-owned record must be scoped to an authenticated business ID; the server must resolve the selected business from the authenticated user's ownership or membership.
- Add an explicit immutable **tenant_id** where it improves consistency, and enforce it in every read, update, delete, background job, export and sync operation.
- Never trust a client-supplied business ID, role, owner ID or verification state.
- Start with the existing shared database and strict tenant scoping. Do not create a separate database per customer by default; physical database-per-tenant can be evaluated later if scale, regulatory or contract requirements justify its operational and migration cost.
- Subdomains such as **sarefactory.revelacode.co.ke** should resolve through a trusted tenant/domain registry, then be checked against the authenticated membership. A hostname must never grant access on its own.

### Industry template
Persist **industry_template** with a validated allow-list. Initial values:
- **general**
- **retail_shop**
- **hardware**
- **factory**
- **salon**
- **professional_services**
- **school**

Templates should configure navigation, terminology, optional modules and onboarding defaults. They must not create separate copies of the same services or bypass backend permissions. The existing category field remains the business's descriptive category; the template is the workflow configuration.

### Workspace mode
Persist **business_scale** (**micro**, **small**, **growing**, **enterprise**) and **workspace_mode** (**simple**, **advanced**). The UI mode is a convenience, not an authorization boundary. Backend role checks and object-level business scoping remain mandatory for every API call.

## 2. Small Biashara edition

Target users: kiosks, salons, market traders, sole proprietors, small retailers and family-run businesses that need to sell and track cash without navigating enterprise tools.

### Minimum workflow
1. Quick sale: item/service, quantity, discount if authorized, payment method, amount received and receipt/reference.
2. Stock: add/reduce/adjust stock with an audit reason; low-stock threshold and a restock list.
3. Customers and debts: customer balance, amount paid, remaining balance, due date and reminder status.
4. Expenses and cash summary: recorded income, expense, cash/M-Pesa split and daily closing.
5. Orders and a simple public storefront where relevant.
6. Offline queue and sync status: show what is local, queued, synced or in conflict.

Keep the first navigation focused on daily work. Hide advanced automation, staff administration and operational intelligence in simple mode. Do not hide modules from backend authorization checks based on the mode.

### Pricing principle
Small Biashara should have a genuinely usable low-cost entry plan. Do not force a shop to configure HR, factory production, machine monitoring or enterprise automation before it can record its first sale. Usage limits and paid upgrades should be explicit and loaded through the existing RevelaCode revenue/plan system.

## 3. Shared roles and permission model

Use normalized role identifiers plus a permission matrix, not a UI-only role rename.

- Owner / CEO / Director: business profile, staff access, financial overview and approved configuration.
- Operations Manager: orders, services, daily operations and approved reporting.
- Accountant / Bursar: invoices, expenses, payment allocation and reconciliation.
- Inventory / Store Keeper: products, stock movements and reorder requests.
- Staff / Sales Agent: sales and assigned customer workflows only.
- Factory Floor Lead: production batches and quality records only when those modules are enabled.
- HR: attendance and employment records only when enabled.

The role shown in the UI may use industry-specific wording, but authorization uses server-side permissions. A role must not inherit access merely because its display name matches another hub's role.

## 4. Modules and rollout order

### Common business modules
- Sales, receipts, customer records and debt tracking.
- Product/service catalogue and inventory ledger.
- Expenses, invoicing, payment allocation and finance summaries.
- Stock alerts, reorder drafts, audit history and sync diagnostics.
- Public website/storefront using existing Biashara website functionality.
- WhatsApp queries using verified user/business identity and only data the sender is authorized to see.

### Factory modules
- Production batch: material input, expected output, actual output, wastage, units and cost variance.
- Machine register and worker-submitted hourly output; alert on threshold breaches, not automatic disciplinary action.
- Quality checks and batch grades with traceable operator, timestamp and product/batch reference.

### Automation guardrails
Use a rule engine with **observe → alert → request review → approve → execute** states, an audit trail and idempotent jobs. Stock thresholds may create reorder drafts; a person approves supplier orders unless the business explicitly authorizes bounded auto-ordering. Attendance anomalies should alert the manager. Employment termination, staff-account blocking, payroll changes and other high-impact actions must require an authorized human decision and a recorded reason; do not automatically dismiss or permanently block a worker from a missed-attendance rule alone.

## 5. M-Pesa and eTIMS

- Reuse the existing Daraja/revenue integration. Treat an ambiguous STK Push outcome as **submission_unknown** and reconcile it using the provider callback/query path before offering another charge. Use idempotency keys to prevent duplicate payment intents.
- Keep payment state separate from invoice/tax state. A successful M-Pesa payment does not by itself prove an eTIMS tax invoice was accepted.
- KRA provides OSCU/VSCU system-to-system integration paths and requires the relevant development, testing, vetting and certification process. Until the integration is certified and production-tested, show eTIMS as setup/sandbox/certification-pending rather than promising automatic filing or displaying an unaccepted document as a valid tax invoice.
- Store the KRA response/identifier and final status for every attempted submission; provide retry/reconciliation tools for recoverable failures. Never silently mark an invoice accepted.
- Keep tenant-specific credentials encrypted and access-controlled; never place them in frontend code or logs.

## 6. Offline-first contract

- Keep one shared sync contract across Biashara, Elimu and other ecosystem hubs, but let each hub register its own entity schemas.
- PWA: use IndexedDB for queued operations and local records. Android: use the existing Capacitor application and add SQLite only where the native offline storage path is actually wired and tested.
- Every mutation should include a stable operation ID/idempotency key, tenant/business ID, entity ID, client timestamp and schema version.
- Sync must surface queued, synced, rejected and conflict states. Conflict resolution must preserve the original server record and include an audit trail.
- Never claim a payment, eTIMS submission, staff action or stock movement has synced while it remains only on-device. Show a local/offline receipt as provisional where applicable.

## 7. Three implementation phases

### Phase A — onboarding and Small Biashara shell
- Select industry template and business scale during onboarding.
- Persist validated configuration in the existing business record.
- Load a simpler navigation for micro/small businesses; retain advanced mode for growing companies and factory templates.
- Add schema tests for allowed templates and persistence.
- Keep existing API paths and verification rules intact.

### Phase B — tenant and permissions hardening
- Audit every Biashara route for business-scoped filters and role checks.
- Add/standardize tenant identifiers and indexes only after reviewing existing records and migration strategy.
- Introduce a domain-to-tenant registry for subdomains and test host spoofing, cross-business object access, and membership changes.
- Define role-to-permission tests.

### Phase C — commerce MVP and expansion
- Complete quick sales, customer debts, expense entry, stock movement and low-stock alerts.
- Wire offline queue and replay tests.
- Validate M-Pesa reconciliation end-to-end.
- Start eTIMS sandbox work and the KRA certification path separately from ordinary invoice generation.
- Add factory batch costing and quality workflows after the common commerce path is reliable.

## 8. Definition of done

- New template and scale values are validated on the server and saved in the existing business record.
- Existing businesses without these fields continue to load in advanced mode; no destructive database split or API contract break is introduced.
- Simple navigation is consistent on desktop and mobile, but the backend still enforces authorization independently.
- Tests cover invalid template values, profile updates, unverified business access, cross-tenant access and sync idempotency.
- Integrations are shown as available only when credentials, provider responses, certification and production checks support that claim.
- No feature is marked live merely because its menu item or configuration field exists.
