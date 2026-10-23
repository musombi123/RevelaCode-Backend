"""Resolve business access using ownership or active membership."""
from __future__ import annotations

from bson import ObjectId
from bson.errors import InvalidId

from backend.jumuiya.core.database import collection


ACTIVE_STATUSES = ("active", "accepted")
ASSIGNABLE_ROLES = {"admin", "manager", "sales", "inventory", "viewer"}


def clean_business_id(value):
    if value is None:
        return None
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError, ValueError):
        return str(value)


def _find_business(business_id):
    if not business_id:
        return None
    businesses = collection("jumuiya_businesses")
    business = businesses.find_one({"_id": clean_business_id(business_id)})
    if business is None:
        business = businesses.find_one({"_id": str(business_id)})
    return business


def _find_membership(user_id, business_id):
    memberships = collection("jumuiya_biashara_memberships")
    for status in ACTIVE_STATUSES:
        membership = memberships.find_one({
            "business_id": str(business_id),
            "user_id": str(user_id),
            "status": status,
        })
        if membership:
            role = str(membership.get("role") or "viewer").strip().lower()
            if role in ASSIGNABLE_ROLES:
                return membership, role
    return None, None


def _specific(user_id, business_id):
    business = _find_business(business_id)
    if not business:
        return None
    resolved_id = str(business.get("_id") or business_id)
    if str(business.get("owner_user_id") or "") == str(user_id):
        return {"business": business, "role": "owner", "is_owner": True, "membership": None}
    membership, role = _find_membership(user_id, resolved_id)
    if not membership:
        return None
    return {"business": business, "role": role, "is_owner": False, "membership": membership}


def resolve_business_access(user_id, business_id=None):
    """Resolve a requested business, active preference, owned business or membership."""
    uid = str(user_id or "").strip()
    if not uid:
        return None
    explicit_id = str(business_id or "").strip()
    if explicit_id:
        return _specific(uid, explicit_id)

    preference = collection("jumuiya_biashara_active_business").find_one({"user_id": uid}) or {}
    preferred_id = str(preference.get("business_id") or "").strip()
    if preferred_id:
        context = _specific(uid, preferred_id)
        if context:
            return context

    owned = collection("jumuiya_businesses").find_one({"owner_user_id": uid})
    if owned:
        return {"business": owned, "role": "owner", "is_owner": True, "membership": None}

    members = collection("jumuiya_biashara_memberships").find({
        "user_id": uid, "status": {"$in": list(ACTIVE_STATUSES)}
    }).sort("created_at", -1).limit(100)
    for membership in members:
        context = _specific(uid, str(membership.get("business_id") or ""))
        if context:
            return context
    return None


def list_business_access(user_id):
    """Return serialized-by-caller business documents the user may access."""
    uid = str(user_id or "").strip()
    if not uid:
        return []
    pref = collection("jumuiya_biashara_active_business").find_one({"user_id": uid}) or {}
    active_id = str(pref.get("business_id") or "")
    businesses = {}
    owned = collection("jumuiya_businesses").find({"owner_user_id": uid}).sort("created_at", -1).limit(100)
    for business in owned:
        bid = str(business.get("_id") or "")
        if bid:
            item = dict(business)
            item.update(access_role="owner", is_owner=True, is_active=(bid == active_id))
            businesses[bid] = item
    memberships = collection("jumuiya_biashara_memberships").find({
        "user_id": uid, "status": {"$in": list(ACTIVE_STATUSES)}
    }).sort("created_at", -1).limit(100)
    for membership in memberships:
        bid = str(membership.get("business_id") or "")
        if not bid or bid in businesses:
            continue
        context = _specific(uid, bid)
        if not context:
            continue
        item = dict(context["business"])
        item.update(
            access_role=context["role"],
            is_owner=False,
            is_active=(bid == active_id),
            membership_id=str(membership.get("_id") or ""),
        )
        businesses[bid] = item
    current = resolve_business_access(uid)
    if current:
        bid = str(current["business"].get("_id") or "")
        if bid in businesses:
            businesses[bid]["is_active"] = True
    return list(businesses.values())
