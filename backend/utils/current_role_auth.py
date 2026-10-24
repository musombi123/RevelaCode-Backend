"""Current-database-role authorization for sensitive RevelaCode administration.

Unlike the legacy role decorator, this module never authorizes a privileged
request from an API key or a JWT role claim alone. The signed token proves
identity; the current user document decides access.
"""
from __future__ import annotations

import os
from functools import wraps

import jwt
from bson import ObjectId
from flask import g, jsonify, request

from backend.db import get_db


PLATFORM_ADMIN_ROLES = frozenset({
    "admin",
    "platform_admin",
    "super_admin",
    "revelacode_admin",
})
SUPPORT_ROLES = frozenset({"support", "support_admin"})
INACTIVE_STATUSES = frozenset({
    "inactive", "disabled", "suspended", "blocked", "banned", "deleted",
    "revoked", "pending_invitation",
})


def _normalized_roles(user: dict) -> set[str]:
    candidates = []
    raw_roles = user.get("roles")
    if isinstance(raw_roles, str):
        candidates.append(raw_roles)
    elif isinstance(raw_roles, (list, tuple, set)):
        candidates.extend(raw_roles)
    candidates.append(user.get("role"))
    return {
        str(value).strip().casefold()
        for value in candidates
        if str(value or "").strip()
    }


def resolve_current_actor(req):
    """Return (safe_actor, error_payload, status_code).

    The lookup uses the same existing `users` collection as RevelaCode login.
    """
    authorization = str(req.headers.get("Authorization") or "").strip()
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token.strip():
        return None, {
            "success": False,
            "code": "authentication_required",
            "message": "Sign in with your RevelaCode account.",
        }, 401

    secret = str(os.getenv("JWT_SECRET") or "").strip()
    if not secret:
        return None, {
            "success": False,
            "code": "authentication_unavailable",
            "message": "Privileged authentication is not configured.",
        }, 503

    try:
        claims = jwt.decode(
            token.strip(),
            secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        return None, {
            "success": False,
            "code": "token_expired",
            "message": "Your session has expired. Sign in again.",
        }, 401
    except jwt.InvalidTokenError:
        return None, {
            "success": False,
            "code": "invalid_token",
            "message": "Your session could not be verified.",
        }, 401

    user_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
    if not user_id or len(user_id) > 128:
        return None, {
            "success": False,
            "code": "invalid_user_identity",
            "message": "The session does not contain a valid account identity.",
        }, 401

    try:
        users = get_db()["users"]
        user = None
        identifier_terms = [{"id": user_id}, {"user_id": user_id}]
        if ObjectId.is_valid(user_id):
            identifier_terms.insert(0, {"_id": ObjectId(user_id)})
        user = users.find_one({"$or": identifier_terms})
    except Exception:
        return None, {
            "success": False,
            "code": "role_lookup_unavailable",
            "message": "Current account permissions could not be verified.",
        }, 503

    if not user:
        return None, {
            "success": False,
            "code": "user_not_found",
            "message": "The account associated with this session no longer exists.",
        }, 401

    actual_id = str(user.get("_id") or user.get("id") or user.get("user_id") or "").strip()
    if actual_id != user_id:
        return None, {
            "success": False,
            "code": "user_identity_mismatch",
            "message": "The account identity could not be verified.",
        }, 403

    status = str(user.get("status") or "active").strip().casefold()
    if user.get("is_active") is False or status in INACTIVE_STATUSES:
        return None, {
            "success": False,
            "code": "account_inactive",
            "message": "This account is not active.",
        }, 403

    roles = _normalized_roles(user)
    role = str(user.get("role") or "user").strip().casefold()
    if not roles:
        roles = {role}

    return {
        "id": actual_id,
        "name": str(user.get("full_name") or user.get("fullName") or user.get("name") or ""),
        "contact": str(user.get("contact") or user.get("email") or ""),
        "email": str(user.get("email") or user.get("contact") or ""),
        "role": role,
        "roles": sorted(roles),
    }, None, 200


def require_current_roles(*allowed_roles):
    """Protect a route using roles loaded from the current users collection."""
    allowed = {str(value).strip().casefold() for value in allowed_roles if value}
    if not allowed:
        raise ValueError("require_current_roles() requires at least one role.")

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            actor, error, status = resolve_current_actor(request)
            if error:
                return jsonify(error), status

            actor_roles = set(actor["roles"]) | {actor["role"]}
            if not actor_roles.intersection(allowed):
                return jsonify({
                    "success": False,
                    "code": "forbidden",
                    "message": "Your current account role is not permitted to perform this action.",
                }), 403

            g.current_platform_actor = actor
            return fn(*args, **kwargs)

        return wrapper
    return decorator


def current_platform_actor() -> dict:
    """Return the actor attached by `require_current_roles`."""
    actor = getattr(g, "current_platform_actor", None)
    return actor if isinstance(actor, dict) else {}
