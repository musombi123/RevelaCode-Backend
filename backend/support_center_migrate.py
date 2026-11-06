"""One-time support-team schema/bootstrap migration.

Run on the backend service after setting SUPER_ADMIN_USER_ID to the existing
owner account's MongoDB ObjectId or stable user ID. No account is created.
"""
from __future__ import annotations

from bson import ObjectId

from backend.db import get_db
from backend.support_center import ensure_indexes
from backend.support_config import SUPER_ADMIN_USER_ID


def main():
    owner_id = SUPER_ADMIN_USER_ID
    if not owner_id:
        raise SystemExit("Set SUPER_ADMIN_USER_ID to the existing owner account ID.")
    db = get_db()
    query = {"_id": ObjectId(owner_id)} if ObjectId.is_valid(owner_id) else {"$or": [{"id": owner_id}, {"user_id": owner_id}]}
    owner = db["users"].find_one(query)
    if not owner:
        raise SystemExit("The configured SUPER_ADMIN_USER_ID does not match an existing users record.")
    roles = owner.get("roles") if isinstance(owner.get("roles"), list) else []
    roles = list(dict.fromkeys([str(role).strip() for role in roles if role] + ["super_admin"]))
    # The first successful bootstrap intentionally invalidates pre-migration
    # access tokens. Persist the marker in the same atomic update so rerunning
    # this one-time migration cannot revoke sessions issued after the bootstrap.
    seeded_before = bool(owner.get("super_admin_seeded_at"))
    updates = {
        "role": "super_admin",
        "roles": roles,
        "status": "active",
        "is_active": True,
        "verified": True,
    }
    if not seeded_before:
        updates["token_version"] = int(owner.get("token_version") or 0) + 1
        updates["super_admin_seeded_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    db["users"].update_one(query, {"$set": updates})
    ensure_indexes()
    print("Support Team collections and indexes are ready.")
    if seeded_before:
        print("The existing owner is already bootstrapped; current sessions were preserved.")
    else:
        print("The existing owner is assigned SUPER_ADMIN; pre-migration sessions were invalidated once.")


if __name__ == "__main__":
    main()
