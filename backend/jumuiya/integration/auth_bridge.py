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

JWT_ALGORITHM = "HS256"

JWT_ALGORITHMS = [JWT_ALGORITHM]


# =========================================================
# AUTH BRIDGE
# =========================================================

def install_auth_bridge(app):
    """
    Connect Jumuiya to the existing RevelaCode authentication.

    RevelaCode owns authentication.

    Jumuiya consumes the resulting JWT:

        Authorization: Bearer <token>

    and exposes the normalized identity as:

        g.jumuiya_user
    """

    if not JWT_SECRET:
        app.logger.warning(
            "Jumuiya auth bridge: JWT_SECRET is not configured."
        )

    @app.before_request
    def _jumuiya_auth_bridge():
        """
        Populate g.jumuiya_user for requests carrying
        a valid RevelaCode JWT.
        """

        # Always reset request identity.
        g.jumuiya_user = None

        # -------------------------------------------------
        # CORS PREFLIGHT
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
        # JWT CONFIGURATION
        # -------------------------------------------------

        if not JWT_SECRET:
            app.logger.error(
                "Jumuiya authentication attempted but "
                "JWT_SECRET is not configured."
            )

            return None

        # -------------------------------------------------
        # JWT VALIDATION
        # -------------------------------------------------

        try:

            payload = jwt.decode(
                token,
                JWT_SECRET,
                algorithms=JWT_ALGORITHMS,
                options={
                    "require": [
                        "sub",
                        "iat",
                        "exp",
                    ]
                },
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
            app.logger.warning(
                "Jumuiya JWT contains no usable user ID."
            )

            return None

        # -------------------------------------------------
        # LOAD AUTHORITATIVE USER
        # -------------------------------------------------

        user = _load_user(
            user_id
        )

        if not user:

            app.logger.warning(
                "Jumuiya could not resolve authenticated "
                "user %s from the RevelaCode users collection.",
                user_id,
            )

            return None

        # -------------------------------------------------
        # VERIFY ACCOUNT STATE
        # -------------------------------------------------

        if not user.get("verified", False):

            app.logger.warning(
                "Jumuiya rejected unverified user %s.",
                user_id,
            )

            return None

        # -------------------------------------------------
        # NORMALIZE IDENTITY
        # -------------------------------------------------

        normalized = normalize_user(
            user
        )

        if not normalized.get("id"):

            app.logger.warning(
                "Jumuiya resolved user %s but could not "
                "normalize the identity.",
                user_id,
            )

            return None

        # -------------------------------------------------
        # REQUEST IDENTITY
        # -------------------------------------------------

        g.jumuiya_user = normalized

        return None


# =========================================================
# REVELACODE USER LOADER
# =========================================================

def _load_user(user_id):
    """
    Load the authoritative user from the existing
    RevelaCode users collection.

    We deliberately do NOT manufacture a user from JWT
    claims when the database cannot resolve the account.
    """

    try:

        from backend.db import db

        from bson import ObjectId

        user_id_string = str(
            user_id
        )

        users = db["users"]

        user = None

        # -------------------------------------------------
        # Mongo ObjectId
        # -------------------------------------------------

        try:

            user = users.find_one(
                {
                    "_id": ObjectId(
                        user_id_string
                    )
                }
            )

        except (
            TypeError,
            ValueError,
        ):
            pass

        # -------------------------------------------------
        # String user_id
        # -------------------------------------------------

        if not user:

            user = users.find_one(
                {
                    "user_id": user_id_string
                }
            )

        # -------------------------------------------------
        # String id
        # -------------------------------------------------

        if not user:

            user = users.find_one(
                {
                    "id": user_id_string
                }
            )

        return user

    except Exception:
        return None
