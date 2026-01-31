from functools import wraps
from flask import request, jsonify
from backend.routes.notifications_routes import push_notification

# Simple role-based access + optional notification + logging
def require_role(role_name, notify=False, notify_text=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Import auth dynamically if not already
            from backend.auth_gate import get_role as auth_get_role
            role = auth_get_role(request)

            if role != role_name:
                return jsonify({"message": "Forbidden"}), 403

            result = f(*args, **kwargs)

            # Optional notification
            if notify and notify_text:
                push_notification(
                    f"{role_name} action: {notify_text}",
                    extra={"type": "role_action", "actor_role": role_name}
                )

            return result
        return wrapper
    return decorator
