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

    Jumuiya consumes the existing RevelaCode JWT:

        Authorization: Bearer <token>

    and exposes the authenticated, normalized identity as:

        g.jumuiya_user
    """

    if not JWT_SECRET:
        app.logger.error(
            "Jumuiya auth bridge: JWT_SECRET is not configured."
        )

    @app.before_request
    def _jumuiya_auth_bridge():
        """
        Resolve the authenticated RevelaCode user for Jumuiya.

        This function intentionally does not manufacture a user
        from JWT claims. The JWT must resolve to a real user in
        the RevelaCode users collection.
        """

        # -------------------------------------------------
        # RESET REQUEST IDENTITY
        # -------------------------------------------------

        g.jumuiya_user = None

        # -------------------------------------------------
        # CORS PREFLIGHT
        # -------------------------------------------------

        if request.method == "OPTIONS":
            return None

        # -------------------------------------------------
        # AUTHORIZATION HEADER
        # -------------------------------------------------

        authorization = (
            request.headers.get(
                "Authorization",
                "",
            )
            .strip()
        )

        if not authorization:
            return None

        # We currently support the RevelaCode JWT scheme:
        #
        # Authorization: Bearer <token>
        #
        if not authorization.startswith("Bearer "):
            app.logger.warning(
                "Jumuiya received unsupported Authorization "
                "scheme."
            )
            return None

        token = authorization[
            len("Bearer "):
        ].strip()

        if not token:
            app.logger.warning(
                "Jumuiya received an empty Bearer token."
            )
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

            app.logger.info(
                "Jumuiya JWT accepted. sub=%s",
                payload.get("sub"),
            )

        except jwt.ExpiredSignatureError:
            app.logger.warning(
                "Jumuiya rejected JWT: token expired."
            )
            return None

        except jwt.InvalidSignatureError:
            app.logger.warning(
                "Jumuiya rejected JWT: invalid signature."
            )
            return None

        except jwt.MissingRequiredClaimError as error:
            app.logger.warning(
                "Jumuiya rejected JWT: missing required "
                "claim: %s",
                error,
            )
            return None

        except jwt.DecodeError:
            app.logger.warning(
                "Jumuiya rejected JWT: decode error."
            )
            return None

        except jwt.InvalidTokenError as error:
            app.logger.warning(
                "Jumuiya rejected JWT: invalid token: %s",
                error,
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

        user_id = str(user_id)

        # -------------------------------------------------
        # LOAD AUTHORITATIVE USER
        # -------------------------------------------------

        user = _load_user(user_id)

        if not user:
            app.logger.warning(
                "Jumuiya JWT is valid, but user was not "
                "found in the RevelaCode users collection. "
                "user_id=%s",
                user_id,
            )
            return None

        # -------------------------------------------------
        # ACCOUNT STATE
        # -------------------------------------------------

        verified = bool(
            user.get("verified", False)
        )

        app.logger.info(
            "Jumuiya resolved user. user_id=%s verified=%s",
            user_id,
            verified,
        )

        if not verified:
            app.logger.warning(
                "Jumuiya rejected user %s because "
                "verified=%s.",
                user_id,
                verified,
            )
            return None

        # -------------------------------------------------
        # NORMALIZE IDENTITY
        # -------------------------------------------------

        try:
            normalized = normalize_user(user)

        except Exception:
            app.logger.exception(
                "Jumuiya failed to normalize user %s.",
                user_id,
            )
            return None

        if not normalized:
            app.logger.warning(
                "Jumuiya normalization returned an empty "
                "identity for user %s.",
                user_id,
            )
            return None

        if not normalized.get("id"):
            app.logger.warning(
                "Jumuiya resolved user %s but could not "
                "normalize a usable identity ID.",
                user_id,
            )
            return None

        # -------------------------------------------------
        # REQUEST IDENTITY
        # -------------------------------------------------

        g.jumuiya_user = normalized

        app.logger.info(
            "Jumuiya authentication established. "
            "user_id=%s",
            normalized.get("id"),
        )

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

    Supported identifiers:

        1. MongoDB ObjectId
        2. user_id string
        3. id string
    """

    try:
        from bson import ObjectId
        from backend.db import db

        users = db["users"]

        user_id_string = str(user_id)

        # -------------------------------------------------
        # TRY MONGO OBJECT ID
        # -------------------------------------------------

        try:
            object_id = ObjectId(
                user_id_string
            )

            user = users.find_one(
                {
                    "_id": object_id
                }
            )

            if user:
                return user

        except (
            TypeError,
            ValueError,
        ):
            pass

        # -------------------------------------------------
        # TRY STRING user_id
        # -------------------------------------------------

        user = users.find_one(
            {
                "user_id": user_id_string
            }
        )

        if user:
            return user

        # -------------------------------------------------
        # TRY STRING id
        # -------------------------------------------------

        user = users.find_one(
            {
                "id": user_id_string
            }
        )

        if user:
            return user

        return None

    except Exception:
        return None
        
