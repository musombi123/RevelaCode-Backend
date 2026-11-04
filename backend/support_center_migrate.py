"""One-time support-team schema/bootstrap migration.

Run on the backend service after setting SUPER_ADMIN_USER_ID to the existing
owner account's MongoDB ObjectId or stable user ID. No account is created.
"""
from __future__ import annotations

import os
from bson import ObjectId

from backend.db import get_db
from backend.support_center import ensure_indexes


def main():
    owner_id = str(os.getenv("SUPER_ADMIN_USER_ID") or "").strip()
    if not owner_id:
        raise SystemExit("Set SUPER_ADMIN_USER_ID to the existing owner account ID.")
    db = get_db()
    query = {"_id": ObjectId(owner_id)} if ObjectId.is_valid(owner_id) else {"$or": [{"id": owner_id}, {"user_id": owner_id}]}
    owner = db["users"].find_one(query)
    if not owner:
        raise SystemExit("The configured SUPER_ADMIN_USER_ID does not match an existing users record.")
    roles = owner.get("roles") if isinstance(owner.get("roles"), list) else []
    roles = list(dict.fromkeys([str(role).strip() for role in roles if role] + ["super_admin"]))
    db["users"].update_one(query, {"$set": {
        "role": "super_admin",
        "roles": roles,
        "status": "active",
        "is_active": True,
        "verified": True,
        "token_version": int(owner.get("token_version") or 0) + 1,
        "super_admin_seeded_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    }})
    ensure_indexes()
    print("Support Team collections and indexes are ready.")
    print("The existing owner account is assigned SUPER_ADMIN; existing sessions were invalidated.")


if __name__ == "__main__":
    main()
