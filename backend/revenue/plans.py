"""Pricing catalogue for Jumuiya OS Revenue Engine.

Static entries are safe defaults. Platform-admin-approved catalogue edits and
new plans are stored in MongoDB, but do not enable billing or entitlements.
"""

from __future__ import annotations

from backend.jumuiya.core.database import collection

PRICING_STATUS = "draft"
PLANS_COLLECTION = "jumuiya_revenue_plans"

# These are proposed catalogue values, not approved live pricing. A plan must be
# explicitly published by a platform administrator before checkout can charge.
PLANS = [
    {
        "code": "free",
        "name": "Jumuiya Free",
        "hub": "all",
        "amount": "0.00",
        "currency": "KES",
        "interval": "month",
        "status": "available",
        "features": [
            "Essential hub features",
            "Basic records and management",
            "Limited Smart AI access",
            "Marketplace access",
        ],
    },
    {
        "code": "ai_plus",
        "name": "Smart AI Plus",
        "hub": "smart_ai",
        "amount": "199.00",
        "currency": "KES",
        "interval": "month",
        "status": "proposed",
        "features": [
            "Higher AI usage allowance",
            "Expanded AI history",
            "Eligible advanced AI features",
        ],
    },
    {
        "code": "ai_pro",
        "name": "Smart AI Pro",
        "hub": "smart_ai",
        "amount": "499.00",
        "currency": "KES",
        "interval": "month",
        "status": "proposed",
        "features": [
            "Higher AI usage allowance",
            "Advanced AI tools",
            "Priority access where available",
        ],
    },
    {
        "code": "shamba_plus",
        "name": "Shamba Plus",
        "hub": "shamba",
        "amount": "99.00",
        "currency": "KES",
        "interval": "month",
        "status": "proposed",
        "features": ["Enhanced farm records", "Additional farm alerts"],
    },
    {
        "code": "shamba_pro",
        "name": "Shamba Pro",
        "hub": "shamba",
        "amount": "299.00",
        "currency": "KES",
        "interval": "month",
        "status": "proposed",
        "features": [
            "Advanced farm analytics",
            "Crop planning tools",
            "Available market insights",
        ],
    },
    {
        "code": "biashara_starter",
        "name": "Biashara Starter",
        "hub": "biashara",
        "amount": "199.00",
        "currency": "KES",
        "interval": "month",
        "status": "proposed",
        "features": [
            "Expanded business reporting",
            "Additional inventory tools",
        ],
    },
    {
        "code": "biashara_pro",
        "name": "Biashara Pro",
        "hub": "biashara",
        "amount": "499.00",
        "currency": "KES",
        "interval": "month",
        "status": "proposed",
        "features": [
            "Advanced sales analytics",
            "Forecasting tools",
            "Business insights",
        ],
    },
    {
        "code": "elimu_small",
        "name": "Elimu Small School",
        "hub": "elimu",
        "amount": "499.00",
        "currency": "KES",
        "interval": "month",
        "status": "proposed",
        "features": [
            "School administration features",
            "Plan-specific staff access",
        ],
    },
    {
        "code": "elimu_standard",
        "name": "Elimu Standard",
        "hub": "elimu",
        "amount": "1499.00",
        "currency": "KES",
        "interval": "month",
        "status": "proposed",
        "features": [
            "Expanded school administration",
            "Additional reporting capabilities",
        ],
    },
    {
        "code": "elimu_advanced",
        "name": "Elimu Advanced",
        "hub": "elimu",
        "amount": "2999.00",
        "currency": "KES",
        "interval": "month",
        "status": "proposed",
        "features": [
            "Advanced school administration",
            "Expanded reporting and controls",
        ],
    },
    {
        "code": "marketplace_starter",
        "name": "Marketplace Starter",
        "hub": "marketplace",
        "amount": "99.00",
        "currency": "KES",
        "interval": "month",
        "status": "proposed",
        "features": [
            "Marketplace seller profile and listing tools",
            "Product and service listing management",
            "Buyer inquiry handling",
        ],
    },
    {
        "code": "community_ads_campaign",
        "name": "Community Ads Campaign",
        "hub": "advertising",
        "amount": "100.00",
        "currency": "KES",
        "interval": "one_time",
        "status": "proposed",
        "features": [
            "Community advertising campaign request",
            "Ad creative and campaign details submitted for review",
            "Placement is not automatic; billing remains disabled",
        ],
    },
]

_EDITABLE_FIELDS = ("name", "amount", "interval", "status", "features")


def _load_overrides():
    """Load admin-managed plan documents by code."""
    rows = collection(PLANS_COLLECTION).find({})
    return {
        str(row.get("code")): row
        for row in rows
        if row.get("code")
    }


def list_plans(hub=None, *, include_retired=False):
    """Return merged plan defaults and database-managed plans.

    The ``hub`` filter still includes the shared ``all`` plan. Retired plans
    are hidden from public catalogues by default but remain visible to admins.
    """
    normalized_hub = str(hub or "").strip().lower()
    overrides = _load_overrides()
    output = []
    known_codes = set()

    for base in PLANS:
        code = base["code"]
        known_codes.add(code)
        item = dict(base)
        override = overrides.get(code, {})

        for key in _EDITABLE_FIELDS:
            if key in override:
                item[key] = override[key]

        item["features"] = list(item.get("features") or [])
        if not include_retired and item.get("status") == "retired":
            continue
        if normalized_hub and item["hub"] not in {normalized_hub, "all"}:
            continue
        output.append(item)

    # Admin-created plans not present in the static seed catalogue.
    for code, stored in overrides.items():
        if code in known_codes:
            continue
        item = {
            "code": code,
            "name": stored.get("name", code),
            "hub": stored.get("hub", "all"),
            "amount": stored.get("amount", "0.00"),
            "currency": "KES",
            "interval": stored.get("interval", "month"),
            "status": stored.get("status", "proposed"),
            "features": list(stored.get("features") or []),
        }
        if not include_retired and item["status"] == "retired":
            continue
        if normalized_hub and item["hub"] not in {normalized_hub, "all"}:
            continue
        output.append(item)

    return output


def get_plan(plan_code):
    """Find a plan by stable code, including plans marked retired."""
    normalized_code = str(plan_code or "").strip().lower()
    for plan in list_plans(include_retired=True):
        if plan["code"] == normalized_code:
            return plan
    return None
