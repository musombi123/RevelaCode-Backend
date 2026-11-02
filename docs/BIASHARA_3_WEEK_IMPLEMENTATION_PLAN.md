# Biashara OS — three-week manufacturing pilot plan

## Delivery objective

Deliver a usable first manufacturing pilot on the existing Core-Zero platform. The three-week window targets an operational MVP with controlled integrations; it does not promise KRA certification, production WhatsApp commands, machine telemetry or advanced payroll inside the same window.

## Week 1 — tenant, templates and access

**Deliverables**
- Reuse Elimu/Core-Zero authentication, identity, permissions, sync contracts and notification services.
- Provision one MongoDB database per company using the central tenant registry.
- Migrate existing company-owned records idempotently; retain legacy source records.
- Support general, retail, hardware, factory, salon, professional-services and Elimu templates.
- Validate the CEO, Operations Manager, HR Manager, Accountant, Store Keeper, Factory Floor Lead, Sales Agent and Employee role permissions.
- Resolve verified subdomains to the tenant only after DNS/hosting verification.
- Add company-scoped API calls to the active Biashara workspaces.

**Exit criteria**
- A company registers and is approved through the existing business verification process.
- Its tenant database is provisioned and isolated.
- A member cannot read or write another company’s data.
- A company can select a template and invite employees with limited roles.
- Elimu fee, exam and attendance flows still pass regression tests.

## Week 2 — commerce, inventory and manufacturing

**Deliverables**
- Product catalogue with explicit resale, raw_material, finished_good and consumable types, units and cost price.
- Invoice, sales, customer debt and stock movement flows.
- Factory production batch creation with raw material deduction.
- Actual output, wastage and recoverable by-product reconciliation.
- Quality hold, quality grade and finished-goods release.
- Machine register, hourly output records and threshold alerts.
- Offline-safe factory mutation queue with stable idempotency keys and tenant replay context.
- Daraja STK checkout and callback/query reconciliation using the shared payment adapter.

**Exit criteria**
- A batch cannot consume more raw material than available stock.
- Every completed batch accounts for material input.
- Failed/rejected quality batches do not become sellable inventory.
- Duplicate offline replays do not duplicate supported factory mutations.
- An M-Pesa payment does not mark an invoice paid until its provider result and callback metadata are reconciled.
- Ambiguous STK submission keeps an invoice checkout unresolved rather than sending a second prompt.

## Week 3 — HR, integration readiness and pilot acceptance

**Deliverables**
- Employee register and generated System IDs.
- Link an existing company member to an employee record after invitation acceptance.
- Shift start/end, optional GPS clock-in/out, late and overtime calculations.
- CEO/Operations/HR dashboards and factory yield/wastage alerts.
- Integration readiness view for Daraja, eTIMS and WhatsApp.
- Company public website/storefront with only approved public information.
- Pilot data setup and training for one Migori manufacturing company.
- Backup, restore, audit, role and tenant-isolation checklists.

**Exit criteria**
- Director sees sales, debts, stock alerts, production batches, yield and active incidents.
- Factory Floor Lead can record batches and machine readings.
- HR can manage employee records; staff can only view their own attendance.
- Operations continue on the offline-safe factory paths and synchronize on reconnect.
- The company can use its approved public website and company domain where DNS is configured.

## Parallel external work — not assumed complete in three weeks

- Configure Daraja production credentials and a real callback domain; perform a controlled low-value live test after sandbox validation.
- Complete the relevant KRA OSCU/VSCU testing, vetting and certification. eTIMS submission stays disabled until approved.
- Configure WhatsApp Cloud API webhook verification, signed callback handling, verified user/phone binding and command authorization before enabling sales-report commands.
- Set up wildcard DNS and Render custom-domain routing for company subdomains.
- Validate the MongoDB replica-set/transaction deployment required for atomic stock and payment operations.
- Implement secure offline attendance only after a privacy-preserving, tamper-aware local protocol is designed.
- Add payroll/tax calculations, payslip delivery, supplier auto-ordering, sensor/PLC integrations and enterprise consolidation after the pilot is stable.

## Pilot success measures

Track these with the pilot company:
- Sales recorded and reconciled per trading day.
- Inventory adjustments with an auditable reason.
- Raw-material input, output, wastage and yield per batch.
- Quality rejection and rework rates.
- Machine output and downtime alerts.
- Open customer debts and collection status.
- Offline mutation queue age, retries, conflicts and duplicate prevention.
- Payment intents by status: pending, succeeded, failed, unknown and reconciliation required.

## Release rule

A visible screen is not proof that a workflow is production-ready. Every feature must pass its API, permission, tenant-isolation, offline/idempotency and failure-path tests before being advertised as live. Keep Elimu regression tests green throughout the Biashara upgrade.
