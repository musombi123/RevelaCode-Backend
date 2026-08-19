from functools import wraps
from flask import g
from jumuiya.core.errors import APIError

def require_authenticated(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not getattr(g, "jumuiya_user", None):
            raise APIError("Authentication is required.", 401, "authentication_required")
        return fn(*args, **kwargs)
    return wrapper

def current_user_id():
    user = getattr(g, "jumuiya_user", None)
    if not user:
        raise APIError("Authentication is required.", 401, "authentication_required")
    value = user.get("id") or user.get("_id") or user.get("user_id")
    if value is None:
        raise APIError("Authenticated user has no usable ID.", 401, "invalid_identity")
    return str(value)
