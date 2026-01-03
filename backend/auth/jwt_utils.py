import jwt
import os
from datetime import datetime, timedelta
from flask import request, jsonify

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")

def generate_token(role):
    payload = {
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=8)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def require_jwt(role=None):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            if not token:
                return jsonify({"message": "Missing token"}), 401

            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
                if role and payload.get("role") != role:
                    return jsonify({"message": "Forbidden"}), 403
            except Exception:
                return jsonify({"message": "Invalid token"}), 401

            return fn(*args, **kwargs)
        return wrapper
    return decorator
