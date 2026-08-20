from __future__ import annotations

def normalize_user(raw_user: dict) -> dict:
    if not isinstance(raw_user, dict):
        return {}
    user_id = raw_user.get("id") or raw_user.get("_id") or raw_user.get("user_id")
    roles = raw_user.get("roles")
    if not roles:
        role = raw_user.get("role")
        roles = [role] if role else ["user"]
    return {
        "id": str(user_id) if user_id is not None else None,
        "full_name": raw_user.get("full_name", ""),
        "contact": raw_user.get("contact", ""),
        "role": raw_user.get("role", "user"),
        "roles": [str(role) for role in roles if role],
        "verified": bool(raw_user.get("verified", False)),
    }
