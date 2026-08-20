# backend/jumuiya/integration/auth_bridge.py

from __future__ import annotations

import os

import jwt
from flask import g, request

from backend.jumuiya.core.identity import normalize_user


# =========================================================
# CONFIGURATION
# =========================================================

JWT_SECRET = os.getenv("JWT_SECRET")

JWT_ALGORITHMS = ["HS256"]


# =========================================================
# AUTH BRIDGE
# =========================================================

def install_auth_bridge(app):
    """
    Connect Jumuiya to the existing RevelaCode authentication.

    Jumuiya does NOT create its own authentication system.

    Existing RevelaCode JWT:
        Authorization: Bearer <token>

    becomes:

        g.jumuiya_user

    for all Jumuiya modules.
    """

    if not JWT_SECRET:
        app.logger.warning(
            "Jumuiya auth bridge: JWT_SECRET is not configured."
        )

    @app.before_request
    def _jumuiya_auth_bridge():

        # Always reset the identity for every request.
        g.jumuiya_user = None

        # -------------------------------------------------
        # OPTIONS / PREFLIGHT
        # -------------------------------------------------

        if request.method == "OPTIONS":
            return None

        # -------------------------------------------------
        # AUTHORIZATION HEADER
        # -------------------------------------------------

        authorization = request.headers.get(
            "Authorization",
            "",
        ).strip()

        if not authorization:
            return None

        if not authorization.startswith("Bearer "):
            return None

        token = authorization[
            len("Bearer "):
        ].strip()

        if not token:
            return None

        # -------------------------------------------------
        # JWT
        # -------------------------------------------------

        if not JWT_SECRET:
            app.logger.error(
                "Jumuiya authentication attempted "
                "but JWT_SECRET is not configured."
            )
            return None

        try:

            payload = jwt.decode(
                token,
                JWT_SECRET,
                algorithms=JWT_ALGORITHMS,
            )

        except jwt.ExpiredSignatureError:

            app.logger.info(
                "Jumuiya rejected expired JWT."
            )
            return None

        except jwt.InvalidTokenError:

            app.logger.info(
                "Jumuiya rejected invalid JWT."
            )
            return None

        except Exception:

            app.logger.exception(
                "Unexpected JWT validation error."
            )
            return None

        # -------------------------------------------------
        # USER ID
        # -------------------------------------------------

        user_id = (
            payload.get("sub")
            or payload.get("user_id")
            or payload.get("id")
        )

        if user_id is None:
            return None

        # -------------------------------------------------
        # LOAD REVELACODE USER
        # -------------------------------------------------

        user = _load_user(
            user_id,
            payload,
        )

        if not user:
            return None

        # -------------------------------------------------
        # NORMALIZE
        # -------------------------------------------------

        normalized = normalize_user(
            user
        )

        if not normalized.get("id"):
            return None

        g.jumuiya_user = normalized

        return None


# =========================================================
# REVELACODE USER LOADER
# =========================================================

def _load_user(user_id, payload=None):

    payload = payload or {}

    try:

        from backend.db import db

        from bson import ObjectId

        user = None

        user_id_string = str(
            user_id
        )

        # -------------------------------------------------
        # OBJECT ID
        # -------------------------------------------------

        try:

            user = db["users"].find_one(
                {
                    "_id": ObjectId(
                        user_id_string
                    )
                }
            )

        except Exception:
            pass

        # -------------------------------------------------
        # STRING USER ID
        # -------------------------------------------------

        if not user:

            user = db["users"].find_one(
                {
                    "user_id": user_id_string
                }
            )

        # -------------------------------------------------
        # ID FIELD
        # -------------------------------------------------

        if not user:

            user = db["users"].find_one(
                {
                    "id": user_id_string
                }
            )

        # -------------------------------------------------
        # CONTACT FALLBACK
        # -------------------------------------------------

        contact = payload.get(
            "contact"
        )

        if not user and contact:

            user = db["users"].find_one(
                {
                    "contact": contact
                }
            )

        if user:
            return user

    except Exception:
        return None

    # -----------------------------------------------------
    # JWT FALLBACK
    # -----------------------------------------------------
    #
    # We can still construct a minimal identity from a
    # trusted JWT when the corresponding user document
    # cannot be loaded.
    #
    # This keeps Jumuiya usable with existing JWTs while
    # avoiding a second authentication system.
    # -----------------------------------------------------

    return {
        "id": str(user_id),

        "full_name": (
            payload.get("full_name")
            or payload.get("name")
            or ""
        ),

        "contact": (
            payload.get("contact")
            or payload.get("phone")
            or ""
        ),

        "role": (
            payload.get("role")
            or "user"
        ),

        "roles": (
            payload.get("roles")
            or [payload.get("role", "user")]
        ),

        "verified": bool(
            payload.get(
                "verified",
                True,
            )
        ),
    }