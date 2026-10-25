"""Free, first-party TOTP MFA for the existing RevelaCode identity system.

Secrets are encrypted at rest; ordinary API access tokens are never issued until
an enrolled user's login challenge has been satisfied.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import jwt
from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash

from backend import auth_gate as auth

try:
    import qrcode
except ImportError:  # The manual secret entry route remains usable without QR support.
    qrcode = None

mfa_bp = Blueprint("mfa_bp", __name__)
MFA_ISSUER = "RevelaCode"
CHALLENGE_SECONDS = 300
MAX_CHALLENGE_ATTEMPTS = 5
RECOVERY_CODE_COUNT = 10


class MfaFailure(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _fernet() -> Fernet:
    # Use a dedicated long-lived key in deployment. JWT_SECRET is a compatibility
    # fallback so existing environments can adopt MFA without an extra paid service.
    source = (os.getenv("MFA_ENCRYPTION_KEY") or auth.JWT_SECRET or "").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(source).digest())
    return Fernet(key)


def _encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def _decrypt_secret(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(str(ciphertext).encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError, UnicodeError):
        return None


def _new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp_at(secret: str, timestamp: float | None = None) -> str:
    padded = secret.upper() + ("=" * ((8 - len(secret) % 8) % 8))
    key = base64.b32decode(padded, casefold=True)
    counter = int((time.time() if timestamp is None else timestamp) // 30)
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
    return f"{number % 1_000_000:06d}"


def _verify_totp(secret: str, submitted: str) -> bool:
    code = str(submitted or "").strip()
    if len(code) != 6 or not code.isdigit():
        return False
    now = time.time()
    # A one-step window in either direction tolerates minor device clock drift.
    return any(
        hmac.compare_digest(_totp_at(secret, now + offset * 30), code)
        for offset in (-1, 0, 1)
    )


def _recovery_normalize(code: str) -> str:
    return "".join(ch for ch in str(code or "").upper() if ch.isalnum())


def _recovery_hash(code: str) -> str:
    pepper = hashlib.sha256((auth.JWT_SECRET + ":revelacode-recovery").encode("utf-8")).digest()
    normalized = _recovery_normalize(code).encode("ascii", errors="ignore")
    return hashlib.sha256(pepper + b":" + normalized).hexdigest()


def _new_recovery_codes() -> tuple[list[str], list[str]]:
    visible, stored = [], []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(10).upper()
        visible.append("-".join(raw[i:i + 4] for i in range(0, len(raw), 4)))
        stored.append(_recovery_hash(raw))
    return visible, stored


def _user_id(user: dict) -> str:
    return str(user.get("_id") or user.get("id") or user.get("user_id") or "").strip()


def _query_for_user(user: dict) -> dict:
    raw_id = user.get("_id")
    if raw_id is not None:
        return {"_id": raw_id}
    uid = _user_id(user)
    return {"$or": [{"id": uid}, {"user_id": uid}, {"contact": user.get("contact", "")}]}


def _lookup_user(user_id: str) -> dict | None:
    if not user_id:
        return None
    if auth.MONGO_AVAILABLE and auth.users_col is not None:
        try:
            user = None
            if auth.ObjectId.is_valid(user_id):
                user = auth.users_col.find_one({"_id": auth.ObjectId(user_id)})
            if user is None:
                user = auth.users_col.find_one({"$or": [{"id": user_id}, {"user_id": user_id}]})
            return user
        except Exception as exc:
            raise MfaFailure("user_lookup_unavailable", "Account security is temporarily unavailable.", 503) from exc

    try:
        for record in auth.load_users_file().values():
            if isinstance(record, dict) and _user_id(record) == user_id:
                return record
    except Exception as exc:
        raise MfaFailure("user_lookup_unavailable", "Account security is temporarily unavailable.", 503) from exc
    return None


def _save_user(user: dict, fields: dict | None = None, unset: list[str] | None = None) -> dict:
    fields = fields or {}
    unset = unset or []
    try:
        if auth.MONGO_AVAILABLE and auth.users_col is not None:
            update: dict = {}
            if fields:
                update["$set"] = fields
            if unset:
                update["$unset"] = {key: "" for key in unset}
            if update:
                auth.users_col.update_one(_query_for_user(user), update)
                fresh = auth.users_col.find_one(_query_for_user(user))
                return fresh or {**user, **fields}
            return user

        for key, value in fields.items():
            user[key] = value
        for key in unset:
            user.pop(key, None)
        auth.save_user_to_file(user)
        return user
    except MfaFailure:
        raise
    except Exception as exc:
        raise MfaFailure("security_update_unavailable", "Could not save the account security change.", 503) from exc


def _bearer_token() -> str:
    value = (request.headers.get("Authorization") or "").strip()
    if not value.lower().startswith("bearer "):
        raise MfaFailure("authentication_required", "Sign in to manage account security.", 401)
    token = value[7:].strip()
    if not token:
        raise MfaFailure("authentication_required", "Sign in to manage account security.", 401)
    return token


def _decode_token(token: str, expected_purpose: str | None = None) -> dict:
    try:
        claims = jwt.decode(
            token,
            auth.JWT_SECRET,
            algorithms=[auth.JWT_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise MfaFailure("token_expired", "This security session has expired. Sign in again.", 401) from exc
    except jwt.InvalidTokenError as exc:
        raise MfaFailure("invalid_token", "This security session is invalid.", 401) from exc

    purpose = claims.get("purpose")
    if expected_purpose is None and purpose is not None:
        raise MfaFailure("full_session_required", "Complete the sign-in verification before continuing.", 401)
    if expected_purpose is not None and purpose != expected_purpose:
        raise MfaFailure("invalid_challenge", "The verification challenge is invalid.", 401)
    return claims


def _current_user() -> tuple[dict, dict]:
    claims = _decode_token(_bearer_token())
    user_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
    user = _lookup_user(user_id)
    if not user or _user_id(user) != user_id:
        raise MfaFailure("user_not_found", "The account could not be found.", 401)
    return user, claims


def _challenge_user(token: str, purpose: str) -> tuple[dict, dict]:
    claims = _decode_token(token, purpose)
    user_id = str(claims.get("sub") or "").strip()
    jti = str(claims.get("jti") or "").strip()
    user = _lookup_user(user_id)
    if not user or _user_id(user) != user_id or not jti:
        raise MfaFailure("invalid_challenge", "The verification challenge is invalid.", 401)
    if (
        user.get("mfa_challenge_id") != jti
        or user.get("mfa_challenge_purpose") != purpose
    ):
        raise MfaFailure("challenge_used", "This verification challenge has already been used. Sign in again.", 401)
    attempts = int(user.get("mfa_challenge_attempts") or 0)
    if attempts >= MAX_CHALLENGE_ATTEMPTS:
        _save_user(user, unset=["mfa_challenge_id", "mfa_challenge_purpose", "mfa_challenge_attempts"])
        raise MfaFailure("too_many_attempts", "Too many incorrect codes. Sign in again to retry.", 429)
    return user, claims


def _challenge_token(user: dict, purpose: str) -> str:
    uid = _user_id(user)
    if not uid:
        raise MfaFailure("invalid_user_identity", "This account has no valid identity.", 500)
    jti = secrets.token_urlsafe(32)
    issued = int(time.time())
    payload = {
        "sub": uid,
        "user_id": uid,
        "purpose": purpose,
        "jti": jti,
        "iat": issued,
        "exp": issued + CHALLENGE_SECONDS,
    }
    _save_user(user, {
        "mfa_challenge_id": jti,
        "mfa_challenge_purpose": purpose,
        "mfa_challenge_attempts": 0,
    })
    return jwt.encode(payload, auth.JWT_SECRET, algorithm=auth.JWT_ALGORITHM)


def _record_failed_attempt(user: dict) -> None:
    attempts = int(user.get("mfa_challenge_attempts") or 0) + 1
    fields = {"mfa_challenge_attempts": attempts}
    unset = []
    if attempts >= MAX_CHALLENGE_ATTEMPTS:
        unset = ["mfa_challenge_id", "mfa_challenge_purpose", "mfa_challenge_attempts"]
    _save_user(user, fields if not unset else {}, unset=unset)


def _consume_challenge(user: dict) -> dict:
    return _save_user(user, unset=["mfa_challenge_id", "mfa_challenge_purpose", "mfa_challenge_attempts"])


def _factor_match(user: dict, code: str) -> tuple[bool, int | None]:
    secret = _decrypt_secret(user.get("mfa_secret_enc"))
    if user.get("mfa_enabled") is True and secret and _verify_totp(secret, code):
        return True, None

    stored = user.get("mfa_recovery_code_hashes")
    if isinstance(stored, list):
        submitted_hash = _recovery_hash(code)
        for index, stored_hash in enumerate(stored):
            if isinstance(stored_hash, str) and hmac.compare_digest(stored_hash, submitted_hash):
                return True, index
    return False, None


def _consume_recovery_code(user: dict, index: int | None) -> dict:
    if index is None:
        return user
    hashes = list(user.get("mfa_recovery_code_hashes") or [])
    if 0 <= index < len(hashes):
        hashes.pop(index)
    return _save_user(user, {"mfa_recovery_code_hashes": hashes})


def _make_otpauth_uri(user: dict, secret: str) -> str:
    label = str(user.get("contact") or user.get("email") or _user_id(user))
    issuer_label = quote(MFA_ISSUER, safe="")
    account_label = quote(f"{MFA_ISSUER}:{label}", safe=":")
    return (
        f"otpauth://totp/{account_label}?secret={secret}&issuer={issuer_label}"
        "&algorithm=SHA1&digits=6&period=30"
    )


def _qr_data_url(uri: str) -> str:
    if qrcode is None:
        return ""
    image = qrcode.make(uri)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    import base64 as _base64
    return "data:image/png;base64," + _base64.b64encode(buffer.getvalue()).decode("ascii")


def _require_password(user: dict, password: str) -> None:
    stored = user.get("password")
    if not password or not stored:
        raise MfaFailure("password_required", "Enter your current password to confirm this change.", 400)
    try:
        matches = check_password_hash(str(stored), str(password))
    except (ValueError, TypeError):
        matches = False
    if not matches:
        raise MfaFailure("invalid_password", "The current password is incorrect.", 401)


def _profile_redirect(user: dict) -> str:
    role = str(user.get("role") or "user").strip().casefold()
    if role in auth.PLATFORM_ADMIN_ROLES:
        return "/admin/dashboard"
    if role in {"support", "support_admin"}:
        return "/support/dashboard"
    return "/dashboard"


def _error_response(exc: MfaFailure):
    return jsonify(success=False, code=exc.code, message=exc.message), exc.status


@mfa_bp.before_app_request
def enforce_mfa_for_authenticated_api_requests():
    """Reject pre-MFA sessions after an account turns MFA on.

    Normal auth entry/challenge endpoints are exempt because they are the
    mechanism used to complete the second factor; protected application APIs
    are not. Invalid/expired tokens continue to be handled by each route's
    existing authentication guard.
    """
    if not request.path.startswith("/api/") or request.method == "OPTIONS":
        return None

    exempt_paths = {
        "/api/login", "/api/auth/login", "/api/register",
        "/api/request-code", "/api/verify", "/api/request-reset",
        "/api/verify-reset", "/api/reset-password",
        "/api/auth/mfa/login-verify", "/api/auth/mfa/setup",
        "/api/auth/mfa/enable",
    }
    if request.path in exempt_paths:
        return None

    authorization = (request.headers.get("Authorization") or "").strip()
    if not authorization.lower().startswith("bearer "):
        return None

    raw_token = authorization[7:].strip()
    if not raw_token:
        return None
    try:
        claims = jwt.decode(
            raw_token,
            auth.JWT_SECRET,
            algorithms=[auth.JWT_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
    except jwt.InvalidTokenError:
        # Keep error formatting in the route's existing auth guard.
        return None

    # Purpose-limited MFA challenges are not full API sessions.
    if claims.get("purpose") is not None:
        return None

    user_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
    if not user_id:
        return None
    try:
        user = _lookup_user(user_id)
    except MfaFailure:
        return jsonify(
            success=False,
            code="mfa_state_unavailable",
            message="We could not validate this session's security state. Please retry.",
        ), 503

    if user and user.get("mfa_enabled") is True:
        if claims.get("mfa_verified") is not True:
            return jsonify(
                success=False,
                authenticated=False,
                code="mfa_required",
                message="This account now requires authenticator verification. Sign in again and complete the second step.",
            ), 401
    return None


@mfa_bp.get("/api/auth/mfa/status")
def mfa_status():
    try:
        user, _ = _current_user()
        enabled = user.get("mfa_enabled") is True and bool(user.get("mfa_secret_enc"))
        return jsonify(
            success=True,
            enabled=enabled,
            method="totp" if enabled else None,
            recovery_codes_remaining=len(user.get("mfa_recovery_code_hashes") or []) if enabled else 0,
        ), 200
    except MfaFailure as exc:
        return _error_response(exc)


@mfa_bp.post("/api/auth/mfa/setup")
def mfa_setup():
    data = request.get_json(silent=True) or {}
    try:
        challenge_token = str(data.get("challenge_token") or "").strip()
        is_enrollment_challenge = False
        if challenge_token:
            user, _ = _challenge_user(challenge_token, "mfa_enrollment")
            is_enrollment_challenge = True
        else:
            user, _ = _current_user()
            _require_password(user, str(data.get("password") or ""))

        if user.get("mfa_enabled") is True and user.get("mfa_secret_enc"):
            raise MfaFailure("mfa_already_enabled", "Authenticator verification is already enabled.", 409)

        secret = _new_secret()
        expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        _save_user(user, {
            "mfa_setup_secret_enc": _encrypt_secret(secret),
            "mfa_setup_expires_at": expires,
            "mfa_setup_issued_at": datetime.now(timezone.utc).isoformat(),
        })
        uri = _make_otpauth_uri(user, secret)
        return jsonify(
            success=True,
            secret=secret,
            otpauth_uri=uri,
            qr_code_data_url=_qr_data_url(uri),
            expires_in=600,
            method="totp",
            challenge_enrollment=is_enrollment_challenge,
        ), 200
    except MfaFailure as exc:
        return _error_response(exc)


@mfa_bp.post("/api/auth/mfa/enable")
def mfa_enable():
    data = request.get_json(silent=True) or {}
    try:
        challenge_token = str(data.get("challenge_token") or "").strip()
        is_enrollment_challenge = False
        if challenge_token:
            user, _ = _challenge_user(challenge_token, "mfa_enrollment")
            is_enrollment_challenge = True
        else:
            user, _ = _current_user()

        expires_value = str(user.get("mfa_setup_expires_at") or "")
        try:
            expires = datetime.fromisoformat(expires_value)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
        except ValueError:
            expires = datetime.min.replace(tzinfo=timezone.utc)

        secret = _decrypt_secret(user.get("mfa_setup_secret_enc"))
        if not secret or datetime.now(timezone.utc) >= expires:
            raise MfaFailure("setup_expired", "Authenticator setup expired. Start setup again.", 410)
        if not _verify_totp(secret, str(data.get("code") or "")):
            raise MfaFailure("invalid_code", "That authenticator code is incorrect. Check the code and try again.", 400)

        visible_codes, stored_codes = _new_recovery_codes()
        _save_user(user, {
            "mfa_enabled": True,
            "mfa_secret_enc": user["mfa_setup_secret_enc"],
            "mfa_enabled_at": datetime.now(timezone.utc).isoformat(),
            "mfa_recovery_code_hashes": stored_codes,
        }, unset=[
            "mfa_setup_secret_enc", "mfa_setup_expires_at", "mfa_setup_issued_at",
            "mfa_challenge_id", "mfa_challenge_purpose", "mfa_challenge_attempts",
        ])
        # For setup initiated from Account & Security, the password and new
        # authenticator code have both been verified in this session. Rotate
        # its JWT to a session that carries the verified-MFA claim. Privileged
        # enrollment via login challenge deliberately returns no access token.
        session_token = (
            auth.create_access_token(user, mfa_verified=True)
            if not is_enrollment_challenge
            else None
        )
        return jsonify(
            success=True,
            enabled=True,
            method="totp",
            recovery_codes=visible_codes,
            recovery_codes_remaining=len(visible_codes),
            access_token=session_token,
            token_type="Bearer" if session_token else None,
            expires_in=auth.JWT_EXPIRES_HOURS * 60 * 60 if session_token else None,
            sign_in_again=is_enrollment_challenge,
            message=(
                "Authenticator enabled. Sign in again and verify your first code."
                if is_enrollment_challenge
                else "Authenticator enabled. Save your recovery codes somewhere safe."
            ),
        ), 200
    except MfaFailure as exc:
        return _error_response(exc)


@mfa_bp.post("/api/auth/mfa/login-verify")
def mfa_login_verify():
    data = request.get_json(silent=True) or {}
    token = str(data.get("challenge_token") or "").strip()
    code = str(data.get("code") or data.get("recovery_code") or "").strip()
    if not token or not code:
        return jsonify(success=False, code="challenge_and_code_required", message="Enter your authenticator or recovery code."), 400

    try:
        user, _ = _challenge_user(token, "mfa_login")
        matched, recovery_index = _factor_match(user, code)
        if not matched:
            _record_failed_attempt(user)
            return jsonify(success=False, code="invalid_mfa_code", message="The authenticator or recovery code is incorrect."), 401

        if recovery_index is not None:
            user = _consume_recovery_code(user, recovery_index)
        _consume_challenge(user)

        access_token = auth.create_access_token(user, mfa_verified=True)
        return jsonify(
            success=True,
            userId=_user_id(user),
            id=_user_id(user),
            contact=user.get("contact", ""),
            full_name=user.get("full_name") or user.get("fullName") or "",
            role=user.get("role", "user"),
            redirect=_profile_redirect(user),
            access_token=access_token,
            token_type="Bearer",
            expires_in=auth.JWT_EXPIRES_HOURS * 60 * 60,
            mfa_verified=True,
        ), 200
    except MfaFailure as exc:
        return _error_response(exc)


@mfa_bp.post("/api/auth/mfa/disable")
def mfa_disable():
    data = request.get_json(silent=True) or {}
    try:
        user, _ = _current_user()
        if not (user.get("mfa_enabled") is True and user.get("mfa_secret_enc")):
            raise MfaFailure("mfa_not_enabled", "Authenticator verification is not enabled.", 409)
        _require_password(user, str(data.get("password") or ""))
        matched, recovery_index = _factor_match(user, str(data.get("code") or ""))
        if not matched:
            raise MfaFailure("invalid_mfa_code", "Enter a valid authenticator or recovery code.", 401)
        if recovery_index is not None:
            user = _consume_recovery_code(user, recovery_index)
        _save_user(user, {"mfa_enabled": False}, unset=[
            "mfa_secret_enc", "mfa_enabled_at", "mfa_recovery_code_hashes",
            "mfa_setup_secret_enc", "mfa_setup_expires_at", "mfa_setup_issued_at",
        ])
        return jsonify(success=True, enabled=False, message="Authenticator verification has been disabled."), 200
    except MfaFailure as exc:
        return _error_response(exc)


@mfa_bp.post("/api/auth/mfa/recovery-codes")
def mfa_regenerate_recovery_codes():
    data = request.get_json(silent=True) or {}
    try:
        user, _ = _current_user()
        if not (user.get("mfa_enabled") is True and user.get("mfa_secret_enc")):
            raise MfaFailure("mfa_not_enabled", "Enable authenticator verification first.", 409)
        _require_password(user, str(data.get("password") or ""))
        matched, recovery_index = _factor_match(user, str(data.get("code") or ""))
        if not matched:
            raise MfaFailure("invalid_mfa_code", "Enter a valid authenticator or recovery code.", 401)
        if recovery_index is not None:
            user = _consume_recovery_code(user, recovery_index)

        visible_codes, stored_codes = _new_recovery_codes()
        _save_user(user, {"mfa_recovery_code_hashes": stored_codes})
        return jsonify(
            success=True,
            recovery_codes=visible_codes,
            recovery_codes_remaining=len(visible_codes),
            message="New recovery codes generated. Previous codes are no longer valid.",
        ), 200
    except MfaFailure as exc:
        return _error_response(exc)
