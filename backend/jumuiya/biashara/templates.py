"""Industry templates and server-side Biashara role permissions."""
from __future__ import annotations

TEMPLATES = {
    "general": {
        "label": "General business",
        "modules": ["sales", "customers", "inventory", "debts", "finance", "mpesa", "etims", "hr", "website", "team", "automations", "sync", "reports"],
    },
    "retail_shop": {
        "label": "Retail shop",
        "modules": ["sales", "customers", "inventory", "finance", "debts", "suppliers", "mpesa", "etims", "hr", "website", "team", "automations", "sync", "reports"],
    },
    "hardware": {
        "label": "Hardware",
        "modules": ["sales", "customers", "inventory", "finance", "debts", "suppliers", "purchases", "mpesa", "etims", "hr", "website", "team", "automations", "sync", "reports"],
    },
    "factory": {
        "label": "Manufacturing / factory",
        "modules": ["sales", "customers", "inventory", "finance", "debts", "suppliers", "purchases", "mpesa", "etims", "production", "machines", "quality", "hr", "website", "team", "automations", "sync", "reports"],
    },
    "salon": {
        "label": "Salon and personal services",
        "modules": ["sales", "customers", "appointments", "inventory", "finance", "mpesa", "etims", "debts", "hr", "website", "team", "sync", "reports"],
    },
    "professional_services": {
        "label": "Professional services",
        "modules": ["sales", "customers", "invoicing", "finance", "mpesa", "etims", "debts", "projects", "hr", "website", "team", "sync", "reports"],
    },
    "school": {
        "label": "School business",
        # School-operated businesses remain within Biashara and use its tenant,
        # finance, commerce, team, website and synchronization contracts.
        # Dedicated admissions, student records and fee-ledger APIs are not
        # provided by this template until a Biashara-owned school service exists.
        "modules": ["sales", "customers", "orders", "finance", "debts", "mpesa", "etims", "hr", "website", "team", "sync", "reports"],
    },
}

ROLE_LABELS = {
    "ceo": "CEO",
    "director": "Director",
    "operations_manager": "Operations Manager",
    "hr_manager": "HR Manager",
    "accountant": "Accountant",
    "store_keeper": "Store Keeper",
    "factory_floor_lead": "Factory Floor Lead",
    "sales_agent": "Sales Agent",
    "employee": "Employee",
    "admin": "Business Administrator",
    "manager": "Manager",
    "sales": "Sales Staff",
    "inventory": "Inventory Staff",
    "viewer": "Read-only Staff",
}

ALL = frozenset({"*"})

ROLE_PERMISSIONS = {
    # Platform roles are server-assigned only; they are deliberately omitted
    # from ROLE_LABELS so they cannot be granted through ordinary staff invites.
    "super_admin": ALL,
    "platform_admin": ALL,
    "revelacode_admin": ALL,
    "ceo": ALL,
    "director": ALL,
    "admin": ALL,
    "operations_manager": frozenset({
        "dashboard.view", "reports.view", "sales.view", "sales.create", "orders.view", "orders.create", "orders.update",
        "customers.view", "customers.create", "catalog.view", "catalog.manage", "website.view", "website.manage",
        "website.inquiries.view", "inventory.view", "inventory.create", "inventory.adjust", "inventory.manage",
        "production.view", "production.create", "production.update", "production.materials.view",
        "machines.view", "machines.create", "machines.readings.create", "quality.view", "quality.inspect",
        "suppliers.view", "purchases.view", "purchases.create", "automations.view", "automations.manage",
        "team.view", "team.manage", "attendance.view", "hr.view", "hr.attendance.view", "sync.view", "sync.request", "hr.attendance.self", "integrations.view",
    }),
    "manager": frozenset({
        "dashboard.view", "reports.view", "sales.view", "sales.create", "orders.view", "orders.create", "orders.update",
        "customers.view", "customers.create", "catalog.view", "catalog.manage",
        "inventory.view", "inventory.create", "inventory.adjust", "inventory.manage",
        "production.view", "production.create", "production.update",
        "machines.view", "machines.readings.create", "quality.view", "quality.inspect", "team.view",
        "sync.view", "sync.request", "expenses.view", "expenses.create", "hr.attendance.self", "integrations.view",
    }),
    "hr_manager": frozenset({
        "dashboard.view", "hr.view", "hr.employees.manage", "hr.attendance.view",
        "hr.attendance.manage", "hr.leave.manage", "hr.payroll.prepare", "team.view", "team.manage", "hr.attendance.self",
    }),
    "accountant": frozenset({
        "dashboard.view", "reports.view", "finance.view", "finance.create", "finance.allocate",
        "expenses.view", "expenses.create", "sales.view", "orders.view", "customers.view",
        "invoices.view", "invoices.create", "invoices.allocate", "mpesa.reconcile", "etims.view",
        "sync.view", "sync.request", "hr.attendance.self", "integrations.view",
    }),
    "store_keeper": frozenset({
        "dashboard.view", "inventory.view", "inventory.create", "inventory.adjust", "inventory.manage",
        "suppliers.view", "suppliers.manage", "purchases.view", "purchases.create",
        "production.materials.view", "sync.view", "sync.request", "hr.attendance.self",
    }),
    "inventory": frozenset({
        "dashboard.view", "inventory.view", "inventory.create", "inventory.adjust", "inventory.manage",
        "suppliers.view", "purchases.view",
    }),
    "factory_floor_lead": frozenset({
        "dashboard.view", "production.view", "production.create", "production.update",
        "machines.view", "machines.readings.create", "quality.view", "quality.inspect",
        "inventory.view", "sync.view", "hr.attendance.self",
    }),
    "sales_agent": frozenset({
        "dashboard.view", "sales.view", "sales.create", "customers.view", "customers.create",
        "orders.view", "orders.create", "orders.update", "catalog.view",
        "website.inquiries.view", "sync.view", "hr.attendance.self",
    }),
    "employee": frozenset({"dashboard.view", "hr.attendance.self", "sync.view"}),
    "sales": frozenset({
        "dashboard.view", "sales.view", "sales.create", "customers.view", "customers.create",
        "orders.view", "orders.create", "catalog.view", "inventory.view", "hr.attendance.self",
    }),
    "viewer": frozenset({
        "dashboard.view", "reports.view", "sales.view", "inventory.view", "customers.view", "orders.view",
    }),
}

LEGACY_ROLE_ALIASES = {
    "owner": "ceo",
    "business_owner": "ceo",
    "chief_executive": "ceo",
    "operations": "operations_manager",
    "principal": "operations_manager",
    "teacher": "employee",
    "bursar": "accountant",
    "store": "store_keeper",
    "storekeeper": "store_keeper",
    "hr": "hr_manager",
    "factory_floor": "factory_floor_lead",
    "librarian": "sales_agent",
    "staff": "employee",
}

def normalize_role(role):
    value = str(role or "").strip().lower().replace("-", "_").replace(" ", "_")
    return LEGACY_ROLE_ALIASES.get(value, value)

def role_permissions(role):
    normalized = normalize_role(role)
    return ROLE_PERMISSIONS.get(normalized, frozenset())

def has_permission(role, permission):
    permissions = role_permissions(role)
    return "*" in permissions or permission in permissions

def template_config(template):
    key = str(template or "general").strip().lower()
    config = TEMPLATES.get(key)
    if not config:
        return None
    return {"key": key, **config, "roles": [
        {"key": role, "label": label, "permissions": sorted(ROLE_PERMISSIONS.get(role, ())) if "*" not in ROLE_PERMISSIONS.get(role, ()) else ["*"]}
        for role, label in ROLE_LABELS.items()
        if role in ROLE_PERMISSIONS
    ]}
