"""Additional first-party identity methods for RevelaCode.

Microsoft and GitHub authenticate through their official authorization servers.
Phone OTP and WebAuthn passkeys attach to the existing Mongo users collection and
issue the same RevelaCode JWT. No provider access token is stored as a session.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
import requests
from flask import Blueprint, jsonify, redirect, request
from pymongo import ReturnDocument

from backend.auth_gate import create_access_token
from backend.db import get_db
from backend.utils.current_role_auth import resolve_current_actor

identity_bp = Blueprint("identity_methods", __name__)
UTC = timezone.utc
PROVIDERS = {"microsoft", "github"}
MAX_OTP_ATTEMPTS = 5
OTP_SECONDS = 300
OTP_RESEND_SECONDS = 60
OTP_HOURLY_LIMIT = 5


def _now():
    return datetime.now(UTC)


def _hash(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _frontend_base() -> str:
    return str(
        os.getenv("FRONTEND_URL")
        or os.getenv("REVELACODE_FRONTEND_URL")
        or "https://revelacode.co.ke"
    ).strip().rstrip("/")


def _db():
    return get_db()


def _users():
    return _db()["users"]


def _load_user_by_id(user_id: str):
    from bson import ObjectId

    value = str(user_id or "").strip()
    if not value:
        return None
    if ObjectId.is_valid(value):
        user = _users().find_one({"_id": ObjectId(value)})
        if user:
            return user
    return _users().find_one({"$or": [{"id": value}, {"user_id": value}]})


def _actor_user():
    actor, error, status = resolve_current_actor(request)
    if error:
        return None, (jsonify(error), status)
    user = _load_user_by_id(str(actor.get("id") or ""))
    if not user:
        return None, (jsonify(success=False, code="user_not_found", message="Account not found."), 404)
    state = str(user.get("status") or "active").strip().casefold()
    if user.get("is_active") is False or state in {
        "inactive", "disabled", "suspended", "blocked", "banned", "deleted", "revoked"
    }:
        return None, (jsonify(success=False, code="account_inactive", message="This account is not active."), 403)
    return user, None


def _user_id(user: dict) -> str:
    return str(user.get("_id") or user.get("id") or user.get("user_id") or "").strip()


def _verified(user: dict) -> bool:
    value = user.get("verified", user.get("is_verified", False))
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"true", "1", "yes", "verified"}


def _active(user: dict) -> bool:
    state = str(user.get("status") or "active").strip().casefold()
    return user.get("is_active") is not False and state not in {
        "inactive", "disabled", "suspended", "blocked", "banned", "deleted", "revoked",
        "pending_invitation", "locked",
    }


def _login_result(user: dict):
    """Issue the platform JWT, preserving an account's existing MFA requirement."""
    if not user or not _active(user):
        return jsonify(success=False, code="account_inactive", message="This account is not active."), 403
    if not _verified(user):
        return jsonify(success=False, code="account_not_verified", message="Verify your RevelaCode account before signing in."), 403
    if user.get("mfa_enabled") is True and user.get("mfa_secret_enc"):
        from backend.mfa_routes import _challenge_token

        return jsonify(
            success=True,
            mfa_required=True,
            challenge_token=_challenge_token(user, "mfa_login"),
            expires_in=300,
            message="Complete your existing two-step verification to finish signing in.",
        ), 200
    role = str(user.get("role") or "user")
    token = create_access_token(user)
    return jsonify(
        success=True,
        user={
            "id": _user_id(user),
            "full_name": user.get("full_name") or user.get("fullName") or user.get("name") or "",
            "contact": user.get("contact") or user.get("email") or user.get("phone") or "",
            "email": user.get("email") or "",
            "phone": user.get("phone") or "",
            "role": role,
            "roles": user.get("roles") or [role],
            "verified": _verified(user),
        },
        access_token=token,
        token_type="Bearer",
    ), 200


def _ensure_oauth_indexes():
    db = _db()
    db["identity_oauth_states"].create_index("state_hash", unique=True)
    db["identity_oauth_states"].create_index("expires_at", expireAfterSeconds=0)
    db["identity_login_tickets"].create_index("ticket_hash", unique=True)
    db["identity_login_tickets"].create_index("expires_at", expireAfterSeconds=0)


def _provider_config(provider: str):
    if provider == "microsoft":
        client_id = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
        secret = os.getenv("MICROSOFT_CLIENT_SECRET", "").strip()
        tenant = os.getenv("MICROSOFT_TENANT_ID", "common").strip() or "common"
        callback = os.getenv(
            "MICROSOFT_OAUTH_REDIRECT_URI",
            "https://revelacode-backend.onrender.com/api/oauth/microsoft/callback",
        ).strip()
        if not (client_id and secret and callback.startswith("https://")):
            raise RuntimeError("Microsoft sign-in is not configured. Set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET and MICROSOFT_OAUTH_REDIRECT_URI.")
        return {
            "client_id": client_id,
            "secret": secret,
            "callback": callback,
            "tenant": tenant,
            "authority": f"https://login.microsoftonline.com/{tenant}/v2.0",
        }
    if provider == "github":
        client_id = os.getenv("GITHUB_CLIENT_ID", "").strip()
        secret = os.getenv("GITHUB_CLIENT_SECRET", "").strip()
        callback = os.getenv(
            "GITHUB_OAUTH_REDIRECT_URI",
            "https://revelacode-backend.onrender.com/api/oauth/github/callback",
        ).strip()
        if not (client_id and secret and callback.startswith("https://")):
            raise RuntimeError("GitHub sign-in is not configured. Set GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET and GITHUB_OAUTH_REDIRECT_URI.")
        return {"client_id": client_id, "secret": secret, "callback": callback}
    raise ValueError("Unsupported identity provider.")


def _provider_authorization_url(provider: str, mode: str, actor_id: str | None, client: str):
    _ensure_oauth_indexes()
    config = _provider_config(provider)
    if mode not in {"login", "link"}:
        raise ValueError("Unsupported sign-in mode.")
    if client not in {"web", "android"}:
        raise ValueError("Unsupported client type.")
    if mode == "link" and not actor_id:
        raise ValueError("Sign in before linking an identity provider.")

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return_uri = _frontend_base() + ("/oauth/android-callback" if client == "android" else "/oauth/callback")
    _db()["identity_oauth_states"].insert_one({
        "state_hash": _hash(state),
        "provider": provider,
        "mode": mode,
        "actor_id": actor_id,
        "client": client,
        "return_uri": return_uri,
        "nonce": nonce,
        "code_verifier": verifier,
        "created_at": _now(),
        "expires_at": _now() + timedelta(minutes=10),
    })

    if provider == "microsoft":
        authority_root = config["authority"].rsplit("/v2.0", 1)[0]
        params = {
            "client_id": config["client_id"],
            "response_type": "code",
            "redirect_uri": config["callback"],
            "response_mode": "query",
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        return authority_root + "/oauth2/v2.0/authorize?" + urlencode(params)

    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["callback"],
        "scope": "read:user user:email",
        "state": state,
        "allow_signup": "true",
    }
    return "https://github.com/login/oauth/authorize?" + urlencode(params)


def _start_provider(provider: str):
    try:
        mode = str(request.args.get("mode") or "login").strip().casefold()
        client = str(request.args.get("client") or "web").strip().casefold()
        actor_id = None
        if mode == "link":
            actor, error, status = resolve_current_actor(request)
            if error:
                return jsonify(error), status
            actor_id = str(actor.get("id") or "").strip()
        authorization_url = _provider_authorization_url(provider, mode, actor_id, client)
        return redirect(authorization_url, code=302)
    except RuntimeError as exc:
        code = provider + "_not_configured"
        return jsonify(success=False, code=code, message=str(exc)), 503
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    except Exception:
        return jsonify(success=False, message="Sign-in could not be started."), 503


@identity_bp.post("/api/oauth/<provider>/link/start")
def identity_provider_link_start(provider: str):
    provider = str(provider or "").strip().casefold()
    if provider not in {"microsoft", "github"}:
        return jsonify(success=False, message="Unsupported identity provider."), 400
    user, error = _actor_user()
    if error:
        return error
    if not _verified(user):
        return jsonify(success=False, code="account_not_verified", message="Verify your RevelaCode account before linking another sign-in method."), 403
    data = request.get_json(silent=True) or {}
    client = str(data.get("client") or "web").strip().casefold()
    try:
        authorization_url = _provider_authorization_url(provider, "link", _user_id(user), client)
        return jsonify(success=True, authorization_url=authorization_url), 200
    except RuntimeError as exc:
        return jsonify(success=False, code=provider + "_not_configured", message=str(exc)), 503
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    except Exception:
        return jsonify(success=False, message="Could not start provider linking."), 503


def _identity_callback_error(state_row: dict | None, provider: str, reason: str):
    allowed = {
        _frontend_base() + "/oauth/callback",
        _frontend_base() + "/oauth/android-callback",
    }
    destination = (state_row or {}).get("return_uri")
    if destination not in allowed:
        destination = _frontend_base() + "/oauth/callback"
    return redirect(
        destination + "?" + urlencode({
            "oauth": "error",
            "provider": provider,
            "reason": str(reason or "sign_in_failed")[:180],
        }),
        code=302,
    )


def _issue_identity_ticket(user: dict, provider: str, return_uri: str | None = None):
    ticket = secrets.token_urlsafe(36)
    _db()["identity_login_tickets"].insert_one({
        "ticket_hash": _hash(ticket),
        "user_id": _user_id(user),
        "provider": provider,
        "created_at": _now(),
        "expires_at": _now() + timedelta(minutes=2),
        "used": False,
    })
    destination = return_uri if return_uri in {_frontend_base() + "/oauth/callback", _frontend_base() + "/oauth/android-callback"} else _frontend_base() + "/oauth/callback"
    return redirect(
        destination + "?"
        + urlencode({"oauth": "success", "ticket": ticket, "provider": provider}),
        code=302,
    )


def _provider_identity(provider: str, subject: str, email: str, name: str, state_row: dict):
    users = _users()
    linked = users.find_one({f"oauth_providers.{provider}.sub": subject})
    mode = str(state_row.get("mode") or "login").strip().casefold()

    if mode == "login":
        if not linked:
            raise ValueError(
                "This external account is not linked to a RevelaCode account yet. "
                "Sign in using your existing method, then connect it in Account & Security."
            )
        if not _active(linked) or not _verified(linked):
            raise ValueError("The linked RevelaCode account is not active or verified.")
        return linked

    if mode != "link":
        raise ValueError("Unsupported identity linking mode.")

    actor_id = str(state_row.get("actor_id") or "").strip()
    actor = _load_user_by_id(actor_id)
    if not actor or not _active(actor) or not _verified(actor):
        raise ValueError("Sign in to a verified RevelaCode account before linking this provider.")
    if linked and _user_id(linked) != _user_id(actor):
        raise ValueError("This external identity is already linked to another RevelaCode account.")
    users.update_one(
        {"_id": actor["_id"]},
        {
            "$set": {
                f"oauth_providers.{provider}": {
                    "sub": subject,
                    "email": email or "",
                    "linked_at": _now(),
                }
            },
            "$addToSet": {"login_methods": provider},
        },
    )
    return users.find_one({"_id": actor["_id"]})


def _microsoft_callback():
    state = str(request.args.get("state") or "").strip()
    code = str(request.args.get("code") or "").strip()
    if not state:
        return redirect(_frontend_base() + "/oauth/callback?oauth=error&provider=microsoft&reason=invalid_state")
    _ensure_oauth_indexes()
    state_row = _db()["identity_oauth_states"].find_one_and_delete({
        "state_hash": _hash(state),
        "provider": "microsoft",
        "expires_at": {"$gt": _now()},
    })
    if not state_row:
        return redirect(_frontend_base() + "/oauth/callback?oauth=error&provider=microsoft&reason=invalid_or_expired_state")
    if not code:
        reason = str(request.args.get("error_description") or request.args.get("error") or "authorization_cancelled")[:160]
        return _identity_callback_error(state_row, "microsoft", reason)

    try:
        config = _provider_config("microsoft")
        authority = config["authority"]
        metadata_response = requests.get(
            authority + "/.well-known/openid-configuration", timeout=12
        )
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        token_response = requests.post(
            metadata["token_endpoint"],
            data={
                "client_id": config["client_id"],
                "client_secret": config["secret"],
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config["callback"],
                "code_verifier": state_row["code_verifier"],
                "scope": "openid profile email",
            },
            timeout=15,
        )
        token_response.raise_for_status()
        id_token = str(token_response.json().get("id_token") or "")
        if not id_token:
            raise ValueError("Microsoft did not return an OpenID Connect ID token.")
        unverified_claims = jwt.decode(
            id_token,
            options={"verify_signature": False, "verify_aud": False, "verify_exp": False},
            algorithms=["RS256"],
        )
        token_tenant = str(unverified_claims.get("tid") or "").strip()
        try:
            normalized_tenant = str(uuid.UUID(token_tenant))
        except (ValueError, AttributeError, TypeError):
            raise ValueError("Microsoft returned an invalid tenant identifier.")
        configured_tenant = str(config["tenant"]).strip().casefold()
        consumer_tenant = "9188040d-6c67-4c5b-b112-36a304b66dad"
        if configured_tenant not in {"common", "organizations", "consumers"} and normalized_tenant.casefold() != configured_tenant:
            raise ValueError("The Microsoft account belongs to a tenant not allowed by this app registration.")
        if configured_tenant == "organizations" and normalized_tenant.casefold() == consumer_tenant:
            raise ValueError("This RevelaCode Microsoft app accepts organizational accounts only.")
        if configured_tenant == "consumers" and normalized_tenant.casefold() != consumer_tenant:
            raise ValueError("This RevelaCode Microsoft app accepts personal Microsoft accounts only.")

        expected_issuer = str(metadata.get("issuer") or "").replace("{tenantid}", normalized_tenant)
        token_header = jwt.get_unverified_header(id_token)
        jwks_response = requests.get(metadata["jwks_uri"], timeout=12)
        jwks_response.raise_for_status()
        jwks = jwks_response.json().get("keys") or []
        signing_jwk = next(
            (item for item in jwks if item.get("kid") == token_header.get("kid")),
            None,
        )
        if not signing_jwk:
            raise ValueError("Microsoft's signing key could not be resolved.")
        key_issuer = str(signing_jwk.get("issuer") or "").replace("{tenantid}", normalized_tenant)
        if not key_issuer or key_issuer != expected_issuer:
            raise ValueError("Microsoft's signing key issuer did not match the account tenant.")
        signing_key = jwt.PyJWK.from_dict(signing_jwk).key
        claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256"],
            audience=config["client_id"],
            issuer=expected_issuer,
            options={"require": ["sub", "iss", "aud", "exp", "iat", "nonce", "tid"]},
        )
        if str(claims.get("tid") or "").casefold() != normalized_tenant.casefold():
            raise ValueError("Microsoft's tenant identity claim did not match the validated tenant.")
        if not secrets.compare_digest(str(claims.get("nonce") or ""), str(state_row.get("nonce") or "")):
            raise ValueError("Microsoft sign-in nonce did not match.")
        subject = normalized_tenant + ":" + str(claims["sub"])
        email = str(claims.get("email") or "").strip().lower()
        name = str(claims.get("name") or email.split("@")[0] or "RevelaCode member")
        user = _provider_identity("microsoft", subject, email, name, state_row)
        if not user:
            raise ValueError("Could not resolve the RevelaCode account.")
        return _issue_identity_ticket(user, "microsoft", state_row.get("return_uri"))
    except ValueError as exc:
        return _identity_callback_error(state_row, "microsoft", str(exc))
    except Exception:
        return _identity_callback_error(state_row, "microsoft", "sign_in_failed")


def _github_callback():
    state = str(request.args.get("state") or "").strip()
    code = str(request.args.get("code") or "").strip()
    if not state:
        return redirect(_frontend_base() + "/oauth/callback?oauth=error&provider=github&reason=invalid_state")
    _ensure_oauth_indexes()
    state_row = _db()["identity_oauth_states"].find_one_and_delete({
        "state_hash": _hash(state),
        "provider": "github",
        "expires_at": {"$gt": _now()},
    })
    if not state_row:
        return redirect(_frontend_base() + "/oauth/callback?oauth=error&provider=github&reason=invalid_or_expired_state")
    if not code:
        reason = str(request.args.get("error") or "authorization_cancelled")[:160]
        return _identity_callback_error(state_row, "github", reason)

    try:
        config = _provider_config("github")
        token_response = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": config["client_id"],
                "client_secret": config["secret"],
                "code": code,
                "redirect_uri": config["callback"],
            },
            timeout=15,
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
        access_token = str(token_payload.get("access_token") or "")
        if not access_token:
            raise ValueError("GitHub did not issue an access token. Confirm the OAuth App callback and credentials.")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RevelaCode-Identity",
        }
        profile_response = requests.get("https://api.github.com/user", headers=headers, timeout=12)
        profile_response.raise_for_status()
        profile = profile_response.json()
        github_id = str(profile.get("id") or "").strip()
        if not github_id:
            raise ValueError("GitHub did not return a stable account identifier.")
        emails_response = requests.get("https://api.github.com/user/emails", headers=headers, timeout=12)
        emails_response.raise_for_status()
        verified_emails = [
            item for item in emails_response.json()
            if isinstance(item, dict) and item.get("verified") is True and item.get("primary") is True
        ]
        email = str(verified_emails[0].get("email") or "").strip().lower() if verified_emails else ""
        name = str(profile.get("name") or profile.get("login") or email.split("@")[0])
        user = _provider_identity("github", github_id, email, name, state_row)
        if not user:
            raise ValueError("Could not resolve the RevelaCode account.")
        # The GitHub OAuth token is intentionally not persisted; this flow is
        # authentication only, not repository access.
        return _issue_identity_ticket(user, "github", state_row.get("return_uri"))
    except ValueError as exc:
        return _identity_callback_error(state_row, "github", str(exc))
    except Exception:
        return _identity_callback_error(state_row, "github", "sign_in_failed")


@identity_bp.get("/api/oauth/microsoft/start")
def microsoft_start():
    try:
        return _start_provider("microsoft")
    except RuntimeError as exc:
        return jsonify(success=False, code="microsoft_not_configured", message=str(exc)), 503
    except Exception:
        return jsonify(success=False, message="Microsoft sign-in could not be started."), 503


@identity_bp.get("/api/oauth/microsoft/callback")
def microsoft_callback():
    return _microsoft_callback()


@identity_bp.get("/api/oauth/github/start")
def github_start():
    try:
        return _start_provider("github")
    except RuntimeError as exc:
        return jsonify(success=False, code="github_not_configured", message=str(exc)), 503
    except Exception:
        return jsonify(success=False, message="GitHub sign-in could not be started."), 503


@identity_bp.get("/api/oauth/github/callback")
def github_callback():
    return _github_callback()


@identity_bp.post("/api/oauth/exchange")
def oauth_exchange():
    ticket = str((request.get_json(silent=True) or {}).get("ticket") or "").strip()
    if len(ticket) < 32:
        return jsonify(success=False, message="A valid one-time sign-in ticket is required."), 400
    _ensure_oauth_indexes()
    row = _db()["identity_login_tickets"].find_one_and_update(
        {"ticket_hash": _hash(ticket), "used": False, "expires_at": {"$gt": _now()}},
        {"$set": {"used": True, "used_at": _now()}},
        return_document=ReturnDocument.BEFORE,
    )
    if not row:
        # Preserve already-issued Google tickets and existing frontend clients.
        row = _db()["oauth_login_tickets"].find_one_and_update(
            {"ticket_hash": _hash(ticket), "used": False, "expires_at": {"$gt": _now()}},
            {"$set": {"used": True, "used_at": _now()}},
            return_document=ReturnDocument.BEFORE,
        )
    if not row:
        return jsonify(success=False, code="invalid_or_expired_ticket", message="This sign-in ticket has expired or was already used."), 401
    user = _load_user_by_id(row.get("user_id"))
    return _login_result(user)


def _phone_provider_config():
    username = os.getenv("AFRICASTALKING_USERNAME", "").strip()
    api_key = os.getenv("AFRICASTALKING_API_KEY", "").strip()
    sender = os.getenv("AFRICASTALKING_SENDER_ID", "").strip()
    environment = os.getenv("AFRICASTALKING_ENV", "production").strip().casefold()
    if not username or not api_key:
        raise RuntimeError("Phone sign-in SMS is not configured. Set AFRICASTALKING_USERNAME and AFRICASTALKING_API_KEY.")
    if environment not in {"production", "sandbox"}:
        raise RuntimeError("AFRICASTALKING_ENV must be production or sandbox.")
    endpoint = (
        "https://api.sandbox.africastalking.com/version1/messaging"
        if environment == "sandbox"
        else "https://api.africastalking.com/version1/messaging"
    )
    return username, api_key, sender, endpoint


def _normalise_phone(value: str) -> str:
    raw = re.sub(r"[\s().-]", "", str(value or ""))
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    if raw.startswith("0") and len(raw) == 10 and raw[1] in {"1", "7"}:
        raw = "+254" + raw[1:]
    if raw.startswith("254") and not raw.startswith("+"):
        raw = "+" + raw
    if not re.fullmatch(r"\+[1-9]\d{7,14}", raw):
        raise ValueError("Enter a valid phone number in international format, for example +2547XXXXXXXX.")
    return raw


def _phone_hash(phone: str) -> str:
    return hmac.new(
        os.getenv("JWT_SECRET", "").encode("utf-8"),
        ("revelacode-phone:" + phone).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _otp_hash(challenge_id: str, phone: str, code: str) -> str:
    material = f"{challenge_id}:{phone}:{code}".encode("utf-8")
    return hmac.new(os.getenv("JWT_SECRET", "").encode("utf-8"), material, hashlib.sha256).hexdigest()


def _send_sms(phone: str, code: str):
    username, api_key, sender, endpoint = _phone_provider_config()
    message = f"Your RevelaCode verification code is {code}. It expires in 5 minutes. Do not share this code."
    data = {"username": username, "to": phone, "message": message}
    if sender:
        data["from"] = sender
    response = requests.post(
        endpoint,
        headers={"apiKey": api_key, "Accept": "application/json"},
        data=data,
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    recipients = (payload.get("SMSMessageData") or {}).get("Recipients") or []
    if not recipients or str(recipients[0].get("status") or "").casefold() not in {"success", "sent", "accepted"}:
        raise RuntimeError("The SMS provider did not accept the verification message.")
    return payload


def _ensure_phone_indexes():
    db = _db()
    db["identity_phone_challenges"].create_index("challenge_id_hash", unique=True)
    db["identity_phone_challenges"].create_index("expires_at", expireAfterSeconds=0)
    claims = db["identity_phone_claims"]
    claims.create_index("phone_hash", unique=True)
    claims.create_index("user_id", unique=True)


def _create_phone_challenge(phone: str, user: dict | None, purpose: str):
    _ensure_phone_indexes()
    collection = _db()["identity_phone_challenges"]
    phone_hash = _phone_hash(phone)
    forwarded_ip = str(request.environ.get("revelacode.client_ip") or request.remote_addr or "unknown").strip()
    ip_hash = _hash(forwarded_ip)
    now_dt = _now()
    latest = collection.find_one({
        "phone_hash": phone_hash,
        "created_at": {"$gt": now_dt - timedelta(seconds=OTP_RESEND_SECONDS)},
    })
    if latest:
        raise ValueError("Please wait at least 60 seconds before requesting another code.")
    recent_count = collection.count_documents({
        "phone_hash": phone_hash,
        "created_at": {"$gt": now_dt - timedelta(hours=1)},
    })
    if recent_count >= OTP_HOURLY_LIMIT:
        raise ValueError("Too many verification requests. Try again in one hour.")
    ip_count = collection.count_documents({
        "ip_hash": ip_hash,
        "created_at": {"$gt": now_dt - timedelta(hours=1)},
    })
    if ip_count >= OTP_HOURLY_LIMIT * 3:
        raise ValueError("Too many verification requests from this network. Try again later.")
    challenge_id = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1_000_000):06d}"
    document = {
        "challenge_id_hash": _hash(challenge_id),
        "phone_hash": phone_hash,
        "ip_hash": ip_hash,
        "code_hash": _otp_hash(challenge_id, phone, code),
        "phone": phone,
        "user_id": _user_id(user) if user else None,
        "purpose": purpose,
        "attempts": 0,
        "created_at": now_dt,
        "expires_at": now_dt + timedelta(seconds=OTP_SECONDS),
        "consumed": False,
    }
    collection.insert_one(document)
    try:
        if user is not None:
            _send_sms(phone, code)
        # For unknown phone numbers, intentionally do not send an OTP. The
        # public response remains identical to avoid account enumeration.
    except Exception:
        collection.delete_one({"challenge_id_hash": _hash(challenge_id)})
        raise
    return challenge_id


def _consume_phone_challenge(challenge_id: str, phone: str, code: str, purpose: str):
    collection = _db()["identity_phone_challenges"]
    query = {
        "challenge_id_hash": _hash(challenge_id),
        "phone_hash": _phone_hash(phone),
        "purpose": purpose,
        "consumed": False,
        "expires_at": {"$gt": _now()},
    }
    challenge = collection.find_one(query)
    if not challenge:
        raise ValueError("This verification request has expired or is invalid. Request a new code.")
    if int(challenge.get("attempts") or 0) >= MAX_OTP_ATTEMPTS:
        collection.update_one(query, {"$set": {"consumed": True}})
        raise ValueError("Too many incorrect codes. Request a new code.")
    supplied_hash = _otp_hash(challenge_id, phone, code)
    if not hmac.compare_digest(str(challenge.get("code_hash") or ""), supplied_hash):
        collection.update_one(query, {"$inc": {"attempts": 1}})
        raise ValueError("The verification code is incorrect.")
    consumed = collection.find_one_and_update(
        {**query, "code_hash": supplied_hash},
        {"$set": {"consumed": True, "consumed_at": _now()}},
        return_document=ReturnDocument.BEFORE,
    )
    if not consumed:
        raise ValueError("This verification code has already been used.")
    return consumed


@identity_bp.get("/api/identity/providers")
def identity_provider_status():
    google_ready = bool(
        os.getenv("GOOGLE_WEB_CLIENT_ID", "").strip()
        and os.getenv("GOOGLE_WEB_CLIENT_SECRET", "").strip()
        and os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip().startswith("https://")
    )
    microsoft_ready = bool(
        os.getenv("MICROSOFT_CLIENT_ID", "").strip()
        and os.getenv("MICROSOFT_CLIENT_SECRET", "").strip()
        and os.getenv("MICROSOFT_OAUTH_REDIRECT_URI", "https://revelacode-backend.onrender.com/api/oauth/microsoft/callback").strip().startswith("https://")
    )
    github_ready = bool(
        os.getenv("GITHUB_CLIENT_ID", "").strip()
        and os.getenv("GITHUB_CLIENT_SECRET", "").strip()
        and os.getenv("GITHUB_OAUTH_REDIRECT_URI", "https://revelacode-backend.onrender.com/api/oauth/github/callback").strip().startswith("https://")
    )
    phone_ready = bool(os.getenv("AFRICASTALKING_USERNAME", "").strip() and os.getenv("AFRICASTALKING_API_KEY", "").strip())
    return jsonify(success=True, providers={
        "google": {"enabled": google_ready},
        "microsoft": {"enabled": microsoft_ready},
        "github": {"enabled": github_ready},
        "phone": {"enabled": phone_ready},
        "passkeys": {"enabled": True},
    }), 200


@identity_bp.get("/api/identity/account")
def identity_account():
    user, error = _actor_user()
    if error:
        return error
    providers = user.get("oauth_providers") if isinstance(user.get("oauth_providers"), dict) else {}
    connected = {
        name: bool(providers.get(name))
        for name in ("google", "microsoft", "github")
    }
    passkeys = list(_db()["identity_passkeys"].find(
        {"user_id": _user_id(user)},
        {"_id": 0, "credential_id": 1, "name": 1, "created_at": 1, "last_used_at": 1, "device_type": 1},
    ))
    for item in passkeys:
        item["credential_id"] = str(item.get("credential_id") or "")
        item["created_at"] = item["created_at"].isoformat() if hasattr(item.get("created_at"), "isoformat") else item.get("created_at")
        item["last_used_at"] = item["last_used_at"].isoformat() if hasattr(item.get("last_used_at"), "isoformat") else item.get("last_used_at")
    methods = list(user.get("login_methods") or [])
    if user.get("password"):
        methods.append("password")
    if user.get("phone_verified") is True:
        methods.append("phone")
    if passkeys:
        methods.append("passkey")
    return jsonify(
        success=True,
        providers=connected,
        phone={"number": user.get("phone") or "", "verified": user.get("phone_verified") is True, "sms_enabled": bool(os.getenv("AFRICASTALKING_USERNAME", "").strip() and os.getenv("AFRICASTALKING_API_KEY", "").strip())},
        passkeys=passkeys,
        login_methods=sorted(set(methods)),
    ), 200


@identity_bp.post("/api/identity/phone/link/request")
def phone_link_request():
    user, error = _actor_user()
    if error:
        return error
    try:
        phone = _normalise_phone((request.get_json(silent=True) or {}).get("phone"))
        claims = _db()["identity_phone_claims"]
        existing = claims.find_one({"phone_hash": _phone_hash(phone)})
        if existing and str(existing.get("user_id") or "") != _user_id(user):
            return jsonify(success=False, code="phone_already_linked", message="That phone number is already linked to another RevelaCode account."), 409
        legacy_owner = _users().find_one({"phone": phone, "phone_verified": True}, {"_id": 1, "id": 1, "user_id": 1})
        if legacy_owner and _user_id(legacy_owner) != _user_id(user):
            return jsonify(success=False, code="phone_already_linked", message="That phone number is already linked to another RevelaCode account."), 409
        challenge_id = _create_phone_challenge(phone, user, "phone_link")
        return jsonify(success=True, challenge_id=challenge_id, expires_in=OTP_SECONDS, message="A verification code was sent to your phone."), 200
    except RuntimeError as exc:
        return jsonify(success=False, code="sms_not_configured", message=str(exc)), 503
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 422
    except Exception:
        return jsonify(success=False, code="sms_delivery_failed", message="We could not send the phone verification code. Check the SMS provider configuration and try again."), 502


@identity_bp.post("/api/identity/phone/link/verify")
def phone_link_verify():
    user, error = _actor_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        phone = _normalise_phone(data.get("phone"))
        challenge_id = str(data.get("challenge_id") or "").strip()
        code = str(data.get("code") or "").strip()
        if not challenge_id or not re.fullmatch(r"\d{6}", code):
            raise ValueError("Enter the six-digit SMS code.")
        _consume_phone_challenge(challenge_id, phone, code, "phone_link")
        query = {"_id": user["_id"]} if user.get("_id") is not None else {"contact": user.get("contact")}
        uid = _user_id(user)
        claims = _db()["identity_phone_claims"]
        from pymongo.errors import DuplicateKeyError
        try:
            claims.replace_one(
                {"user_id": uid},
                {"user_id": uid, "phone_hash": _phone_hash(phone), "phone": phone, "verified_at": _now()},
                upsert=True,
            )
        except DuplicateKeyError:
            return jsonify(success=False, code="phone_already_linked", message="That phone number is already linked to another RevelaCode account."), 409
        result = _users().update_one(
            query,
            {"$set": {"phone": phone, "phone_verified": True, "phone_verified_at": _now()}, "$addToSet": {"login_methods": "phone"}},
        )
        if result.matched_count != 1:
            return jsonify(success=False, code="account_update_failed", message="Could not update this account. Sign in again and retry."), 503
        return jsonify(success=True, phone=phone, verified=True, message="Phone number verified and linked to your RevelaCode account."), 200
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 422
    except Exception:
        return jsonify(success=False, code="phone_link_failed", message="Phone verification could not be completed."), 503


@identity_bp.post("/api/identity/phone/login/request")
def phone_login_request():
    data = request.get_json(silent=True) or {}
    try:
        phone = _normalise_phone(data.get("phone"))
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 422
    try:
        _phone_provider_config()
        claim = _db()["identity_phone_claims"].find_one({"phone_hash": _phone_hash(phone)})
        user = _load_user_by_id(str(claim.get("user_id") or "")) if claim else None
        if user and (user.get("phone") != phone or user.get("phone_verified") is not True):
            user = None
        challenge_id = _create_phone_challenge(phone, user, "phone_login")
        return jsonify(
            success=True,
            challenge_id=challenge_id,
            expires_in=OTP_SECONDS,
            message="If the number is linked to a verified RevelaCode account, a sign-in code has been sent.",
        ), 200
    except RuntimeError as exc:
        return jsonify(success=False, code="sms_not_configured", message=str(exc)), 503
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 429
    except Exception:
        return jsonify(success=False, code="sms_delivery_failed", message="Phone sign-in is temporarily unavailable. Please try again."), 503


@identity_bp.post("/api/identity/phone/login/verify")
def phone_login_verify():
    data = request.get_json(silent=True) or {}
    try:
        phone = _normalise_phone(data.get("phone"))
        challenge_id = str(data.get("challenge_id") or "").strip()
        code = str(data.get("code") or "").strip()
        if not challenge_id or not re.fullmatch(r"\d{6}", code):
            raise ValueError("Enter the six-digit SMS code.")
        challenge = _consume_phone_challenge(challenge_id, phone, code, "phone_login")
        user = _load_user_by_id(str(challenge.get("user_id") or ""))
        claim = _db()["identity_phone_claims"].find_one({
            "phone_hash": _phone_hash(phone),
            "user_id": _user_id(user) if user else "",
        })
        if not user or not claim or user.get("phone") != phone or user.get("phone_verified") is not True:
            return jsonify(success=False, code="invalid_phone_login", message="This phone number is not linked to an active RevelaCode account."), 401
        return _login_result(user)
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 401
    except Exception:
        return jsonify(success=False, code="phone_login_failed", message="Phone sign-in could not be completed."), 503


def _webauthn_config():
    rp_id = os.getenv("REVELACODE_WEBAUTHN_RP_ID", "revelacode.co.ke").strip().lower()
    if not re.fullmatch(r"[a-z0-9.-]+", rp_id):
        raise RuntimeError("REVELACODE_WEBAUTHN_RP_ID is invalid.")
    raw_origins = os.getenv("REVELACODE_WEBAUTHN_ORIGINS", "")
    if raw_origins.strip():
        origins = {item.strip().rstrip("/") for item in raw_origins.split(",") if item.strip()}
    else:
        origins = {
            "https://revelacode.co.ke",
            "https://www.revelacode.co.ke",
            "https://biashara.revelacode.co.ke",
            "https://elimu.revelacode.co.ke",
            "https://shamba.revelacode.co.ke",
            "https://community.revelacode.co.ke",
        }
        if os.getenv("REVELACODE_ENV", os.getenv("ENVIRONMENT", "production")).casefold() != "production":
            origins.update({"http://localhost:5173", "http://localhost:4173"})
    return rp_id, origins


def _webauthn_origin():
    origin = str(request.headers.get("Origin") or "").strip().rstrip("/")
    _rp_id, origins = _webauthn_config()
    if origin not in origins:
        raise ValueError("This website origin is not approved for RevelaCode passkeys. Configure REVELACODE_WEBAUTHN_ORIGINS.")
    return origin


def _ensure_passkey_indexes():
    db = _db()
    db["identity_passkey_challenges"].create_index("challenge_id_hash", unique=True)
    db["identity_passkey_challenges"].create_index("expires_at", expireAfterSeconds=0)
    db["identity_passkeys"].create_index("credential_id", unique=True)
    db["identity_passkeys"].create_index("user_id")


def _new_passkey_challenge(challenge: str, purpose: str, user_id: str | None):
    challenge_id = secrets.token_urlsafe(32)
    _db()["identity_passkey_challenges"].insert_one({
        "challenge_id_hash": _hash(challenge_id),
        "challenge": challenge,
        "purpose": purpose,
        "user_id": user_id,
        "created_at": _now(),
        "expires_at": _now() + timedelta(minutes=5),
    })
    return challenge_id


def _get_passkey_challenge(challenge_id: str, purpose: str, user_id: str | None = None):
    return _db()["identity_passkey_challenges"].find_one_and_delete({
        "challenge_id_hash": _hash(challenge_id),
        "purpose": purpose,
        "user_id": user_id,
        "expires_at": {"$gt": _now()},
    })


@identity_bp.post("/api/identity/passkeys/registration/options")
def passkey_registration_options():
    user, error = _actor_user()
    if error:
        return error
    try:
        from webauthn import generate_registration_options, options_to_json
        from webauthn.helpers.structs import (
            AuthenticatorSelectionCriteria,
            ResidentKeyRequirement,
            UserVerificationRequirement,
        )
        _ensure_passkey_indexes()
        _webauthn_origin()
        rp_id, _origins = _webauthn_config()
        uid = _user_id(user)
        user_handle = user.get("webauthn_user_handle")
        if not isinstance(user_handle, bytes) or len(user_handle) < 32:
            user_handle = secrets.token_bytes(64)
            _users().update_one(
                {"_id": user["_id"]},
                {"$set": {"webauthn_user_handle": user_handle}},
            )
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="RevelaCode",
            user_id=user_handle,
            user_name=str(user.get("username") or user.get("email") or user.get("contact") or uid),
            user_display_name=str(user.get("full_name") or user.get("name") or user.get("username") or "RevelaCode member"),
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        payload = json.loads(options_to_json(options))
        challenge_id = _new_passkey_challenge(payload["challenge"], "registration", uid)
        return jsonify(success=True, challenge_id=challenge_id, publicKey=payload), 200
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    except Exception:
        return jsonify(success=False, code="passkey_setup_failed", message="Passkey registration could not be started."), 503


@identity_bp.post("/api/identity/passkeys/registration/verify")
def passkey_registration_verify():
    user, error = _actor_user()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    try:
        from webauthn import base64url_to_bytes, verify_registration_response
        _ensure_passkey_indexes()
        origin = _webauthn_origin()
        challenge_id = str(data.get("challenge_id") or "").strip()
        credential = data.get("credential")
        if not challenge_id or not isinstance(credential, dict):
            return jsonify(success=False, message="A passkey registration response is required."), 400
        challenge = _get_passkey_challenge(challenge_id, "registration", _user_id(user))
        if not challenge:
            return jsonify(success=False, code="passkey_challenge_expired", message="This passkey setup has expired. Start again."), 410
        rp_id, _origins = _webauthn_config()
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge["challenge"]),
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
        credential_id = _b64url(verification.credential_id)
        if _db()["identity_passkeys"].find_one({"credential_id": credential_id}, {"_id": 1}):
            return jsonify(success=False, code="passkey_already_registered", message="This passkey is already registered."), 409
        user_handle = user.get("webauthn_user_handle")
        if not isinstance(user_handle, bytes) or len(user_handle) < 32:
            return jsonify(success=False, code="passkey_user_handle_missing", message="Could not verify the private account handle for this passkey. Restart registration."), 409
        _db()["identity_passkeys"].insert_one({
            "credential_id": credential_id,
            "credential_public_key": verification.credential_public_key,
            "sign_count": int(verification.sign_count),
            "user_id": _user_id(user),
            "user_handle": user_handle,
            "name": str(data.get("name") or "Passkey")[:80],
            "device_type": str(verification.credential_device_type),
            "backed_up": bool(verification.credential_backed_up),
            "transports": list((credential.get("response") or {}).get("transports") or []),
            "created_at": _now(),
            "last_used_at": None,
        })
        _users().update_one(
            {"_id": user["_id"]},
            {"$addToSet": {"login_methods": "passkey"}},
        )
        return jsonify(success=True, credential_id=credential_id, message="Passkey added to your RevelaCode account."), 201
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    except Exception:
        return jsonify(success=False, code="passkey_registration_failed", message="The passkey could not be registered. Check that your device supports passkeys and try again."), 400


@identity_bp.post("/api/identity/passkeys/authentication/options")
def passkey_authentication_options():
    try:
        from webauthn import generate_authentication_options, options_to_json
        from webauthn.helpers.structs import UserVerificationRequirement
        _ensure_passkey_indexes()
        _webauthn_origin()
        rp_id, _origins = _webauthn_config()
        options = generate_authentication_options(
            rp_id=rp_id,
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        payload = json.loads(options_to_json(options))
        challenge_id = _new_passkey_challenge(payload["challenge"], "authentication", None)
        return jsonify(success=True, challenge_id=challenge_id, publicKey=payload), 200
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    except Exception:
        return jsonify(success=False, code="passkey_signin_unavailable", message="Passkey sign-in is temporarily unavailable."), 503


@identity_bp.post("/api/identity/passkeys/authentication/verify")
def passkey_authentication_verify():
    data = request.get_json(silent=True) or {}
    try:
        from webauthn import base64url_to_bytes, verify_authentication_response
        _ensure_passkey_indexes()
        origin = _webauthn_origin()
        challenge_id = str(data.get("challenge_id") or "").strip()
        credential = data.get("credential")
        if not challenge_id or not isinstance(credential, dict):
            return jsonify(success=False, message="A passkey authentication response is required."), 400
        challenge = _get_passkey_challenge(challenge_id, "authentication", None)
        if not challenge:
            return jsonify(success=False, code="passkey_challenge_expired", message="This passkey request has expired. Try again."), 410
        credential_id = str(credential.get("id") or credential.get("rawId") or "").strip()
        if not credential_id:
            return jsonify(success=False, message="The passkey response has no credential identifier."), 400
        stored = _db()["identity_passkeys"].find_one({"credential_id": credential_id})
        if not stored:
            return jsonify(success=False, code="passkey_not_found", message="This passkey is not registered with RevelaCode."), 401
        rp_id, _origins = _webauthn_config()
        supplied_user_handle = (credential.get("response") or {}).get("userHandle")
        if not supplied_user_handle:
            return jsonify(success=False, code="passkey_user_handle_missing", message="This passkey did not provide its discoverable account handle. Use another sign-in method."), 401
        if not stored.get("user_handle") or not hmac.compare_digest(
            bytes(stored["user_handle"]),
            base64url_to_bytes(supplied_user_handle),
        ):
            return jsonify(success=False, code="passkey_user_handle_mismatch", message="The passkey account handle did not match the registered RevelaCode account."), 401
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge["challenge"]),
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=stored["credential_public_key"],
            credential_current_sign_count=int(stored.get("sign_count") or 0),
            require_user_verification=True,
        )
        updated = _db()["identity_passkeys"].update_one(
            {"_id": stored["_id"], "sign_count": int(stored.get("sign_count") or 0)},
            {"$set": {"sign_count": int(verification.new_sign_count), "last_used_at": _now()}},
        )
        if updated.matched_count != 1:
            return jsonify(success=False, code="passkey_counter_conflict", message="This passkey was used in another sign-in request. Try again."), 409
        user = _load_user_by_id(str(stored.get("user_id") or ""))
        return _login_result(user)
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    except Exception:
        return jsonify(success=False, code="passkey_authentication_failed", message="Passkey sign-in could not be verified. Try again or use another sign-in method."), 401


@identity_bp.delete("/api/identity/passkeys/<credential_id>")
def passkey_delete(credential_id: str):
    user, error = _actor_user()
    if error:
        return error
    try:
        _ensure_passkey_indexes()
        stored = _db()["identity_passkeys"].find_one({
            "credential_id": credential_id,
            "user_id": _user_id(user),
        })
        if not stored:
            return jsonify(success=False, code="passkey_not_found", message="Passkey not found."), 404
        provider_data = user.get("oauth_providers") if isinstance(user.get("oauth_providers"), dict) else {}
        other_methods = bool(user.get("password") or user.get("phone_verified") is True or any(provider_data.get(key) for key in provider_data if key != "passkey"))
        other_passkeys = _db()["identity_passkeys"].count_documents({
            "user_id": _user_id(user),
            "credential_id": {"$ne": credential_id},
        })
        if not other_methods and not other_passkeys:
            return jsonify(success=False, code="last_login_method", message="Add another sign-in method before removing your only passkey."), 409
        _db()["identity_passkeys"].delete_one({"_id": stored["_id"]})
        if not other_passkeys:
            _users().update_one({"_id": user["_id"]}, {"$pull": {"login_methods": "passkey"}})
        return jsonify(success=True, message="Passkey removed."), 200
    except Exception:
        return jsonify(success=False, code="passkey_remove_failed", message="Could not remove this passkey."), 503


@identity_bp.delete("/api/identity/providers/<provider>")
def identity_provider_disconnect(provider: str):
    user, error = _actor_user()
    if error:
        return error
    provider = str(provider or "").strip().casefold()
    if provider not in {"google", "microsoft", "github"}:
        return jsonify(success=False, message="Unsupported identity provider."), 400
    providers = user.get("oauth_providers") if isinstance(user.get("oauth_providers"), dict) else {}
    passkey_count = _db()["identity_passkeys"].count_documents({"user_id": _user_id(user)})
    other_provider = any(value for key, value in providers.items() if key != provider)
    other_methods = bool(user.get("password") or user.get("phone_verified") is True or passkey_count or other_provider)
    if not other_methods:
        return jsonify(success=False, code="last_login_method", message="Add another sign-in method before disconnecting your only provider."), 409
    _users().update_one(
        {"_id": user["_id"]},
        {"$unset": {f"oauth_providers.{provider}": ""}, "$pull": {"login_methods": provider}},
    )
    return jsonify(success=True, message=f"{provider.title()} sign-in disconnected."), 200
