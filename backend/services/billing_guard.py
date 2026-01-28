# backend/services/billing_guard.py

from flask import abort

DOMAIN_POLICIES = {
    "culture": {
        "free": True,
        "daily_limit": 20
    },
    "business": {
        "free": False,
        "daily_limit": 5
    },
    "prophetic": {
        "free": True,
        "daily_limit": 10
    }
}

def enforce_domain_policy(domain, user):
    policy = DOMAIN_POLICIES.get(domain)

    if not policy:
        abort(400, "Domain policy not found")

    if not policy["free"] and not user.get("is_premium"):
        abort(402, "Upgrade required for this domain")

    # You already have rate limiting logic → hook here later
    return True
