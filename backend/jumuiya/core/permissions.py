from __future__ import annotations

from functools import wraps
from flask import g

from jumuiya.core.errors import APIError

def current_user():
    user = getattr(g, "jumuiya_user", None)
    if not user:
        raise APIError("Authentication is required.", 401, "authentication_required")
    return user

def require_authenticated(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        current_user()
        return fn(*args, **kwargs)
    return wrapper

def current_user_id():
    user = current_user()
    value = user.get("id") or user.get("_id") or user.get("user_id")
    if value is None:
        raise APIError("Authenticated user has no usable ID.", 401, "invalid_identity")
    return str(value)

def current_user_roles():
    user = current_user()
    roles = user.get("roles") or ([user.get("role")] if user.get("role") else [])
    return {str(role) for role in roles}

def require_roles(*allowed_roles):
    allowed = {str(role) for role in allowed_roles}
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            roles = current_user_roles()
            if not roles.intersection(allowed):
                raise APIError("You do not have permission to perform this action.", 403, "forbidden")
            return fn(*args, **kwargs)
        return wrapper
    return decorator
