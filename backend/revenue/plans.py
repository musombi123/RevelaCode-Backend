
"""Draft pricing catalog for Jumuiya OS.

These plans are proposals. They must not activate paid entitlements
until pricing is approved and payment verification is implemented.
"""

PRICING_STATUS = "draft"

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
        "features": [
            "Enhanced farm records",
            "Additional farm alerts",
        ],
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
]


def list_plans(hub=None):
    """Return copies of plans, optionally filtered by hub."""
    selected = PLANS

    if hub:
        normalized_hub = str(hub).strip().lower()
        selected = [
            plan for plan in PLANS
            if plan["hub"] in {normalized_hub, "all"}
        ]

    return [dict(plan, features=list(plan["features"])) for plan in selected]


def get_plan(plan_code):
    """Find a plan by its stable code."""
    normalized_code = str(plan_code or "").strip().lower()

    for plan in PLANS:
        if plan["code"] == normalized_code:
            return dict(plan, features=list(plan["features"]))

    return None