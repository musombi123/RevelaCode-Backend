from functools import wraps
from flask import request, jsonify

from backend.routes.notifications_routes import push_notification
from backend.utils.auth_keys import get_role as auth_get_role


def require_role(role_name, notify=False, notify_text=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            role = auth_get_role(request)

            if role != role_name:
                return jsonify({
                    "success": False,
                    "message": "Forbidden"
                }), 403

            response = func(*args, **kwargs)

            if notify and notify_text:
                push_notification(
                    f"{role_name} action: {notify_text}",
                    extra={
                        "type": "role_action",
                        "actor_role": role_name
                    }
                )

            return response

        return wrapper

    return decorator