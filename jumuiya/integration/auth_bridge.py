from __future__ import annotations

import os
import jwt
from flask import g, request

from jumuiya.core.identity import normalize_user

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")

def install_auth_bridge(app):
    @app.before_request
    def _jumuiya_auth_bridge():
        g.jumuiya_user = None

        token = request.headers.get("Authorization", "")
        if not token.startswith("Bearer "):
            return None

        raw = token[7:].strip()
        if not raw:
            return None

        try:
            payload = jwt.decode(raw, JWT_SECRET, algorithms=["HS256"])
        except Exception:
            return None

        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            return None

        user = _load_user(user_id, payload)
        if user:
            g.jumuiya_user = normalize_user(user)


def _load_user(user_id, payload):
    try:
        from backend.db import db
        from bson import ObjectId
        user = None
        try: user = db["users"].find_one({"_id": ObjectId(user_id)})
        except Exception: pass
        if not user: user = db["users"].find_one({"user_id": str(user_id)})
        if not user and payload.get("contact"): user = db["users"].find_one({"contact": payload["contact"]})
        if user: return user
    except Exception:
        pass

    return {"id": str(user_id), "contact": payload.get("contact", ""), "role": payload.get("role", "user"), "verified": True}
