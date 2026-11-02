# Biashara OS — modules and permission matrix

## Role principles

Membership roles are server-side authorization inputs. The company may label a job differently in the UI, but the backend maps it to explicit permissions. A company record's employee job function does not silently grant platform access; the employee must first be an active company member through the invitation flow.

## Roles

| Role | Primary responsibility | Representative access |
|---|---|---|
| CEO / Director | Company owner and executive accountability | All company modules, company profile, team, finance, reports and integrations |
| Operations Manager | Daily business operations | Orders, sales, inventory, production, machines, quality, approved team/attendance views |
| HR Manager | Employee administration | Employee register, attendance, leave and payroll preparation |
| Accountant | Financial operations | Invoices, expenses, payment allocation, M-Pesa reconciliation, eTIMS status and finance reports |
| Store Keeper | Inventory control | Products, stock movements, suppliers, purchases and production material issue |
| Factory Floor Lead | Production execution | Production batches, hourly machine readings, quality inspection and relevant stock visibility |
| Sales Agent | Customer-facing sales | Sales, customers, orders and assigned website inquiries |
| Employee | Self-service staff member | Own clock-in/clock-out and limited personal attendance |
| Read-only Staff | Limited observation | Explicitly permitted dashboard and report reads |

CEO/Director access is not assignable through ordinary staff invitations. Platform administrator access is not a business membership role.

## Permission vocabulary

Permissions are checked by the backend, not inferred from menu visibility.

- dashboard.view, reports.view
- sales.view, sales.create, orders.view, orders.create, orders.update
- customers.view, customers.create, catalog.view, catalog.manage
- inventory.view, inventory.create, inventory.adjust, inventory.manage
- suppliers.view, suppliers.manage, purchases.view, purchases.create
- finance.view, finance.create, finance.allocate, expenses.view, expenses.create
- invoices.view, invoices.create, invoices.allocate, mpesa.reconcile, etims.view, integrations.view
- production.view, production.create, production.update, production.materials.view
- machines.view, machines.create, machines.readings.create
- quality.view, quality.inspect
- hr.view, hr.employees.manage, hr.attendance.view, hr.attendance.manage, hr.attendance.self, hr.leave.manage, hr.payroll.prepare
- team.view, team.manage, website.view, website.manage, website.inquiries.view
- automations.view, automations.manage, sync.view, sync.request

## Permission summary

| Permission area | CEO / Director | Operations Manager | HR Manager | Accountant | Store Keeper | Factory Floor Lead | Sales Agent | Employee |
|---|---|---|---|---|---|---|---|---|
| Company settings / full reports | Full | Limited operational | No | Financial reports | No | No | No | No |
| Sales / customers / orders | Full | Operational | No | Read finance context | No | No | Assigned sales | No |
| Inventory / suppliers | Full | Operational | No | Read financial context | Manage | Read materials | Read catalogue | No |
| Production / machines | Full | Manage | No | Read costs when enabled | Material issue | Execute / log | No | No |
| Quality inspection | Full | Inspect / manage | No | No | No | Inspect / record | No | No |
| Finance / invoices | Full | Limited expenses | No | Manage | No | No | No | No |
| HR employee register | Full | Attendance view | Manage | No | No | No | No | No |
| Own attendance | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Team invitations / removal | Full | Limited where granted | HR-scoped | No | No | No | No | No |
| Integration readiness | Full | View | No | View | No | No | No | No |

This table is a product-level summary; the authoritative source is backend/jumuiya/biashara/templates.py. Always verify the actual permission set in code when adding a route. A UI restriction must never replace a backend permission check.

## Industry modules

| Module | Retail | Hardware | Factory | Salon | Professional services |
|---|---:|---:|---:|---:|---:|
| Sales and customers | Yes | Yes | Yes | Yes | Yes |
| Inventory and suppliers | Yes | Yes | Yes | Optional | Optional |
| Finance and debts | Yes | Yes | Yes | Yes | Yes |
| HR and attendance | Yes | Yes | Yes | Yes | Yes |
| M-Pesa readiness/checkout | Yes | Yes | Yes | Yes | Yes |
| eTIMS readiness | Yes | Yes | Yes | Yes | Yes |
| Production / machines / quality | No | No | Yes | No | No |
| Website / team / sync | Yes | Yes | Yes | Yes | Yes |

eTIMS and WhatsApp modules in this table describe enabled product surfaces, not production provider activation. The integration readiness endpoint reports provider configuration and remains truthful about gated capabilities.

## Employment and privacy guardrails

Attendance clocking uses an authenticated member account and an employee record link. GPS is optional. The current HR implementation does not collect facial recognition templates or biometrics. Late and overtime values are operational records, not automated disciplinary decisions.

No rule should automatically terminate employment or permanently block an employee after an absence threshold. Alerts and escalations may be automated; high-impact employment actions require an authorized human process and audit record.
