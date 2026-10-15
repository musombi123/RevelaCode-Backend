"""Tenant-safe Biashara business selection and team membership.

RevelaCode remains the identity provider. This module does not create accounts;
staff can be attached only when their existing verified RevelaCode identity is
found. Business membership is always resolved on the backend.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import wraps

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError


logger = logging.getLogger("jumuiya.biashara.tenancy")

BUSINESSES_COLLECTION = "jumuiya_businesses"
MEMBERSHIPS_COLLECTION = "jumuiya_business_memberships"
ACTIVE_STATUSES = {"active"}

ROLE_PERMISSIONS = {
    "owner": {"*"},
    "manager": {
        "business.view", "business.manage", "team.view", "team.manage",
        "products.view", "products.manage", "inventory.view", "inventory.manage",
        "orders.view", "orders.create", "orders.manage",
        "sales.view", "sales.create", "customers.view", "customers.manage",
        "finance.view", "finance.manage", "analytics.view",
        "website.view", "website.manage", "automation.view", "automation.manage",
        "sync.view", "sync.manage",
    },
    "cashier": {
        "business.view", "products.view", "inventory.view",
        "orders.view", "orders.create", "sales.view", "sales.create",
        "customers.view",
    },
    "stock_controller": {
        "business.view", "products.view", "products.manage",
        "inventory.view", "inventory.manage", "orders.view",
    },
    "accountant": {
        "business.view", "orders.view", "sales.view",
        "finance.view", "finance.manage", "analytics.view",
    },
    "fulfilment": {
        "business.view", "orders.view", "orders.manage",
        "products.view", "inventory.view", "customers.view",
    },
    "marketing": {
        "business.view", "products.view", "customers.view",
        "analytics.view", "website.view", "website.manage",
    },
    "advisor": {
        "business.view", "products.view", "orders.view", "sales.view",
        "finance.view", "analytics.view", "automation.view", "sync.view",
    },
    "read_only": {
        "business.view", "products.view", "inventory.view", "orders.view",
        "sales.view", "customers.view", "finance.view", "analytics.view",
        "website.view", "automation.view", "sync.view", "team.view",
    },
}
ASSIGNABLE_ROLES = set(ROLE_PERMISSIONS) - {"owner"}


def now_utc():
    return datetime.now(timezone.utc)


def _clean_id(value):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return value


def _serialise(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value, list):
        return [_serialise(item) for item in value]
    if isinstance(value, dict):
        return {
            ("id" if key == "_id" else key): _serialise(item)
            for key, item in value.items()
            if key not in {"permissions_snapshot", "internal_notes"}
        }
    return value


def _request_business_id():
    try:
        from flask import has_request_context, request
        if has_request_context():
            return str(request.headers.get("X-Biashara-Business-ID", "") or "").strip() or None
    except Exception:
        return None
    return None


def _permissions(role):
    return sorted(ROLE_PERMISSIONS.get(str(role or "").strip().lower(), set()))


def _owner_membership_document(business, owner_user_id, actor_user_id=None):
    now = now_utc()
    business_id = str(business.get("_id") or business.get("id") or "")
    return {
        "business_id": business_id,
        "user_id": str(owner_user_id),
        "role": "owner",
        "status": "active",
        "granted_by_user_id": str(actor_user_id or owner_user_id),
        "permissions_snapshot": _permissions("owner"),
        "created_at": now,
        "updated_at": now,
        "joined_at": now,
        "revoked_at": None,
        "source": "owner_access_bootstrap_v1",
    }


def ensure_owner_membership(business, actor_user_id=None):
    """Idempotently backfill the current owner membership without guessing ownership."""
    owner_user_id = str(business.get("owner_user_id") or "").strip()
    business_id = str(business.get("_id") or business.get("id") or "").strip()
    if not owner_user_id or not business_id:
        return None
    memberships = collection(MEMBERSHIPS_COLLECTION)
    query = {"business_id": business_id, "user_id": owner_user_id}
    existing = memberships.find_one(query)
    if existing:
        if existing.get("role") != "owner" or existing.get("status") != "active":
            memberships.update_one(
                query,
                {"$set": {
                    "role": "owner",
                    "status": "active",
                    "permissions_snapshot": _permissions("owner"),
                    "updated_at": now_utc(),
                    "revoked_at": None,
                }},
            )
            existing = memberships.find_one(query) or existing
        return existing
    document = _owner_membership_document(business, owner_user_id, actor_user_id)
    document["_id"] = ObjectId()
    try:
        memberships.insert_one(document)
        return document
    except DuplicateKeyError:
        return memberships.find_one(query)


def _membership_for(business, user_id, ensure_owner=True):
    business_id = str(business.get("_id") or business.get("id") or "")
    user_id = str(user_id)
    if str(business.get("owner_user_id") or "") == user_id:
        return ensure_owner_membership(business, user_id) if ensure_owner else {
            "business_id": business_id,
            "user_id": user_id,
            "role": "owner",
            "status": "active",
        }
    return collection(MEMBERSHIPS_COLLECTION).find_one({
        "business_id": business_id,
        "user_id": user_id,
        "status": "active",
    })


def _context_from_documents(business, membership):
    if not business or not membership:
        raise APIError("Business not found or access denied.", 404, "business_access_denied")
    status = str(business.get("status") or "active").strip().lower()
    if status not in ACTIVE_STATUSES:
        raise APIError("This business is not active. Contact its owner or platform support.", 409, "business_inactive")
    role = str(membership.get("role") or "").strip().lower()
    if role not in ROLE_PERMISSIONS:
        raise APIError("Business membership has an unsupported role.", 403, "invalid_business_role")
    result = _serialise(business)
    result["membership_role"] = role
    result["permissions"] = _permissions(role)
    result["membership_status"] = str(membership.get("status") or "active")
    return result


def get_business_context(user_id, business_id=None):
    """Resolve one selected business and prove active membership on the server."""
    user_id = str(user_id or "").strip()
    if not user_id:
        raise APIError("Authenticated user ID is required.", 401, "authentication_required")
    selected_id = str(business_id or _request_business_id() or "").strip()
    businesses = collection(BUSINESSES_COLLECTION)

    if selected_id:
        business = businesses.find_one({"_id": _clean_id(selected_id)})
        if not business:
            # Do not reveal whether another tenant's ID exists.
            raise APIError("Business not found or access denied.", 404, "business_access_denied")
        membership = _membership_for(business, user_id)
        return _context_from_documents(business, membership)

    # Backward compatibility: a single legacy owner business remains the
    # default. Staff users can default to their only active membership.
    candidates = {}
    owned = list(businesses.find({"owner_user_id": user_id}).limit(101))
    for business in owned:
        membership = ensure_owner_membership(business, user_id)
        candidates[str(business.get("_id"))] = (business, membership)

    member_rows = list(collection(MEMBERSHIPS_COLLECTION).find({
        "user_id": user_id,
        "status": "active",
    }).limit(101))
    for membership in member_rows:
        business_id_value = str(membership.get("business_id") or "")
        if business_id_value in candidates:
            continue
        business = businesses.find_one({"_id": _clean_id(business_id_value)})
        if business and str(business.get("status") or "active").lower() == "active":
            candidates[business_id_value] = (business, membership)

    if not candidates:
        raise APIError("Create your business profile first or ask an owner to add your existing account.", 409, "business_required")
    if len(candidates) > 1:
        raise APIError(
            "Choose a business before continuing by sending its ID in the X-Biashara-Business-ID header.",
            409,
            "business_selection_required",
        )
    business, membership = next(iter(candidates.values()))
    return _context_from_documents(business, membership)


def list_accessible_businesses(user_id):
    """Return only business summary fields for businesses the caller belongs to."""
    user_id = str(user_id or "").strip()
    if not user_id:
        raise APIError("Authenticated user ID is required.", 401, "authentication_required")
    businesses = collection(BUSINESSES_COLLECTION)
    rows = {}
    for business in businesses.find({"owner_user_id": user_id}).limit(100):
        membership = ensure_owner_membership(business, user_id)
        if str(business.get("status") or "active").lower() in ACTIVE_STATUSES:
            rows[str(business.get("_id"))] = _context_from_documents(business, membership)
    for membership in collection(MEMBERSHIPS_COLLECTION).find({
        "user_id": user_id,
        "status": "active",
    }).limit(100):
        business_id = str(membership.get("business_id") or "")
        if business_id in rows:
            continue
        business = businesses.find_one({"_id": _clean_id(business_id)})
        if business and str(business.get("status") or "active").lower() in ACTIVE_STATUSES:
            rows[business_id] = _context_from_documents(business, membership)
    return [
        {
            "id": item.get("id"),
            "name": item.get("name", ""),
            "slug": item.get("slug", ""),
            "category": item.get("category", ""),
            "business_type": item.get("business_type", ""),
            "location": item.get("location", ""),
            "county": item.get("county", ""),
            "currency": item.get("currency", "KES"),
            "status": item.get("status", "active"),
            "membership_role": item.get("membership_role"),
            "permissions": item.get("permissions", []),
        }
        for item in sorted(rows.values(), key=lambda row: (str(row.get("name", "")).lower(), str(row.get("id", ""))))
    ]


def require_permission(user_id, permission, business_id=None):
    context = get_business_context(user_id, business_id=business_id)
    permissions = set(context.get("permissions") or [])
    if "*" not in permissions and str(permission) not in permissions:
        raise APIError("Your business role does not allow this action.", 403, "business_permission_denied")
    return context


def require_business_permission(permission):
    """Flask decorator that validates the caller's membership and role permission."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            from backend.jumuiya.core.permissions import current_user_id
            require_permission(current_user_id(), permission)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def _authoritative_user(user_id):
    try:
        from backend.jumuiya.integration.auth_bridge import _load_user
        return _load_user(str(user_id))
    except Exception as error:
        logger.warning("Biashara membership identity lookup failed (%s).", type(error).__name__)
        raise APIError("The target account could not be verified. Retry when identity services are available.", 503, "identity_lookup_unavailable")


def _verified_target_user(user_id):
    target_id = str(user_id or "").strip()
    if not target_id or len(target_id) > 160:
        raise APIError("A valid existing RevelaCode user ID is required.", 422, "invalid_member_user")
    user = _authoritative_user(target_id)
    if not user:
        raise APIError("The target user was not found in RevelaCode identity.", 404, "member_user_not_found")
    if not bool(user.get("verified", False)):
        raise APIError("Only verified existing RevelaCode accounts can be added to a business.", 409, "member_user_unverified")
    canonical_id = str(user.get("id") or user.get("_id") or user.get("user_id") or "")
    if canonical_id != target_id:
        raise APIError("The supplied user ID does not match the authoritative account.", 422, "invalid_member_user")
    return user


def create_business(user_id, payload):
    """Create an additional business without replacing the caller's current one."""
    _verified = _authoritative_user(user_id)
    if not _verified or not bool(_verified.get("verified", False)):
        raise APIError("A verified RevelaCode account is required to create a business.", 403, "user_unverified")
    from backend.jumuiya.biashara import services as biashara_services
    from backend.jumuiya.biashara.models import business_document

    if not isinstance(payload, dict):
        raise APIError("Business profile data is required.", 422, "invalid_business")
    name = str(payload.get("name") or "").strip()
    if not name:
        raise APIError("Business name is required.", 422, "invalid_business")
    document = business_document(str(user_id), payload, biashara_services.unique_slug(name))
    document["created_from"] = "multi_business"
    businesses = collection(BUSINESSES_COLLECTION)
    result = businesses.insert_one(document)
    document["_id"] = result.inserted_id
    ensure_owner_membership(document, actor_user_id=user_id)
    log_action(user_id, "biashara.business_created", "business", result.inserted_id, {"created_from": "multi_business"})
    result_document = _serialise(document)
    result_document["membership_role"] = "owner"
    result_document["permissions"] = _permissions("owner")
    return result_document


def list_members(user_id, business_id):
    context = require_permission(user_id, "team.view", business_id=business_id)
    members = list(collection(MEMBERSHIPS_COLLECTION).find({
        "business_id": str(context["id"]),
        "status": "active",
    }).sort("created_at", 1).limit(200))
    output = []
    for member in members:
        output.append({
            "id": str(member.get("_id") or ""),
            "business_id": str(member.get("business_id") or ""),
            "user_id": str(member.get("user_id") or ""),
            "role": member.get("role", "read_only"),
            "status": member.get("status", "active"),
            "permissions": _permissions(member.get("role")),
            "granted_by_user_id": member.get("granted_by_user_id"),
            "created_at": _serialise(member.get("created_at")),
            "joined_at": _serialise(member.get("joined_at")),
        })
    return output


def add_member(actor_user_id, business_id, member_user_id, role):
    context = require_permission(actor_user_id, "team.manage", business_id=business_id)
    actor_role = str(context.get("membership_role") or "")
    role = str(role or "").strip().lower()
    if role not in ASSIGNABLE_ROLES:
        raise APIError("Choose a supported non-owner business role.", 422, "invalid_business_role")
    if actor_role == "manager" and role == "manager":
        raise APIError("Only the business owner can grant manager access.", 403, "business_permission_denied")

    target = _verified_target_user(member_user_id)
    target_id = str(target.get("id") or target.get("_id") or target.get("user_id") or "")
    business_id_value = str(context["id"])
    business = collection(BUSINESSES_COLLECTION).find_one({"_id": _clean_id(business_id_value)})
    if not business:
        raise APIError("Business not found or access denied.", 404, "business_access_denied")
    if target_id == str(business.get("owner_user_id") or ""):
        raise APIError("The business owner already has owner membership.", 409, "owner_membership_fixed")

    memberships = collection(MEMBERSHIPS_COLLECTION)
    query = {"business_id": business_id_value, "user_id": target_id}
    existing = memberships.find_one(query)
    now = now_utc()
    if existing:
        update = memberships.find_one_and_update(
            {"_id": existing["_id"], "business_id": business_id_value, "user_id": target_id},
            {"$set": {
                "role": role,
                "status": "active",
                "granted_by_user_id": str(actor_user_id),
                "permissions_snapshot": _permissions(role),
                "updated_at": now,
                "joined_at": existing.get("joined_at") or now,
                "revoked_at": None,
            }},
        )
        member = update or memberships.find_one(query) or existing
    else:
        member = {
            "_id": ObjectId(),
            "business_id": business_id_value,
            "user_id": target_id,
            "role": role,
            "status": "active",
            "granted_by_user_id": str(actor_user_id),
            "permissions_snapshot": _permissions(role),
            "created_at": now,
            "updated_at": now,
            "joined_at": now,
            "revoked_at": None,
        }
        try:
            memberships.insert_one(member)
        except DuplicateKeyError:
            prior = memberships.find_one(query)
            if prior:
                member = memberships.find_one_and_update(
                    {"_id": prior["_id"], "business_id": business_id_value, "user_id": target_id},
                    {"$set": {
                        "role": role,
                        "status": "active",
                        "granted_by_user_id": str(actor_user_id),
                        "permissions_snapshot": _permissions(role),
                        "updated_at": now,
                        "revoked_at": None,
                    }},
                ) or prior
            else:
                raise
    log_action(actor_user_id, "biashara.member_added_or_updated", "business_membership", member["_id"], {
        "business_id": business_id_value,
        "member_user_id": target_id,
        "role": role,
    })
    return {
        "id": str(member.get("_id") or ""),
        "business_id": business_id_value,
        "user_id": target_id,
        "role": role,
        "status": "active",
        "permissions": _permissions(role),
        "created_at": _serialise(member.get("created_at")),
        "updated_at": _serialise(member.get("updated_at")),
    }


def remove_member(actor_user_id, business_id, member_user_id):
    context = require_permission(actor_user_id, "team.manage", business_id=business_id)
    business_id_value = str(context["id"])
    target_id = str(member_user_id or "").strip()
    if not target_id:
        raise APIError("Member user ID is required.", 422, "invalid_member_user")
    business = collection(BUSINESSES_COLLECTION).find_one({"_id": _clean_id(business_id_value)})
    if business and target_id == str(business.get("owner_user_id") or ""):
        raise APIError("The business owner membership cannot be revoked.", 409, "owner_membership_fixed")
    memberships = collection(MEMBERSHIPS_COLLECTION)
    current = memberships.find_one({
        "business_id": business_id_value,
        "user_id": target_id,
        "status": "active",
    })
    if not current:
        raise APIError("Active business member not found.", 404, "business_member_not_found")
    now = now_utc()
    updated = memberships.find_one_and_update(
        {"_id": current["_id"], "business_id": business_id_value, "user_id": target_id, "status": "active"},
        {"$set": {
            "status": "revoked",
            "revoked_at": now,
            "revoked_by_user_id": str(actor_user_id),
            "updated_at": now,
        }},
    )
    if not updated:
        raise APIError("Membership changed while revoking access.", 409, "membership_conflict")
    log_action(actor_user_id, "biashara.member_revoked", "business_membership", current["_id"], {
        "business_id": business_id_value,
        "member_user_id": target_id,
    })
    return {"business_id": business_id_value, "user_id": target_id, "status": "revoked", "revoked_at": _serialise(now)}
