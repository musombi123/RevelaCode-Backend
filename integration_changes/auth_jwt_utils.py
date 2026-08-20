import jwt
import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    JWT_SECRET = "change-me"

def generate_token(role, user_id=None, contact=None):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id) if user_id is not None else None,
        "user_id": str(user_id) if user_id is not None else None,
        "contact": contact,
        "role": role or "user",
        "iat": now,
        "exp": now + timedelta(hours=8),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def decode_token(token):
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])

def require_jwt(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = request.headers.get("Authorization", "").replace("Bearer ", "", 1).strip()
            if not token:
                return jsonify({"message": "Missing token"}), 401
            try:
                payload = decode_token(token)
                if role and payload.get("role") != role:
                    return jsonify({"message": "Forbidden"}), 403
            except Exception:
                return jsonify({"message": "Invalid token"}), 401
            return fn(*args, **kwargs)
        return wrapper
    return decorator
