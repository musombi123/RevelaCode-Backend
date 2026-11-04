"""Google OpenID Connect Authorization Code + PKCE login for RevelaCode.

Google identity is verified server-side. Social sign-in never assigns a staff
role; support roles are granted only by a valid, matching invitation.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
import requests
from flask import Blueprint, jsonify, redirect, request
from pymongo import ReturnDocument

from backend.db import get_db
from backend.auth_gate import create_access_token
from backend.utils.current_role_auth import resolve_current_actor

oauth_bp = Blueprint("oauth", __name__)
UTC = timezone.utc
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs"


def _now():
    return datetime.now(UTC)


def _ensure_indexes():
    db = get_db()
    db["oauth_states"].create_index([("state_hash", 1)], unique=True)
    db["oauth_states"].create_index([("expires_at", 1)], expireAfterSeconds=0)
    db["oauth_login_tickets"].create_index([("ticket_hash", 1)], unique=True)
    db["oauth_login_tickets"].create_index([("expires_at", 1)], expireAfterSeconds=0)


def _client_config():
    # Normalize whitespace and accidental wrapping quotes from Render values.
    client_id = str(os.getenv("GOOGLE_WEB_CLIENT_ID") or "").strip().strip("\"'").strip()
    client_secret = str(os.getenv("GOOGLE_WEB_CLIENT_SECRET") or "").strip().strip("\"'").strip()
    redirect_uri = str(os.getenv("GOOGLE_OAUTH_REDIRECT_URI") or "").strip().strip("\"'").strip()
    if not (client_id and client_secret and redirect_uri.startswith("https://")):
        raise RuntimeError("Google OAuth server configuration is incomplete. Set the Web application Client ID, matching Client Secret and HTTPS callback URI in Render.")
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise RuntimeError("GOOGLE_WEB_CLIENT_ID must be copied from a Google Cloud OAuth client of type Web application.")
    return client_id, client_secret, redirect_uri


@oauth_bp.get("/api/oauth/google/config-status")
def google_config_status():
    """Expose safe Google OAuth configuration diagnostics without secrets."""
    client_id = str(os.getenv("GOOGLE_WEB_CLIENT_ID") or "").strip().strip("\"'").strip()
    client_secret = str(os.getenv("GOOGLE_WEB_CLIENT_SECRET") or "").strip().strip("\"'").strip()
    redirect_uri = str(os.getenv("GOOGLE_OAUTH_REDIRECT_URI") or "").strip().strip("\"'").strip()
    client_id_shape_ok = bool(client_id.endswith(".apps.googleusercontent.com"))
    ready = bool(client_id and client_id_shape_ok and client_secret and redirect_uri.startswith("https://"))
    return jsonify(
        success=True,
        google={
            "configured": ready,
            "client_id_present": bool(client_id),
            "client_id_format_valid": client_id_shape_ok,
            "client_id_hint": (client_id[:8] + "…" + client_id[-28:]) if len(client_id) > 40 else None,
            "client_secret_present": bool(client_secret),
            "redirect_uri_present": bool(redirect_uri),
            "redirect_uri": redirect_uri or None,
            "required_redirect_uri": "https://revelacode-backend.onrender.com/api/oauth/google/callback",
            "note": "A valid-looking Client ID may still be deleted, disabled or belong to another Google Cloud project. Confirm the client exists in Google Cloud Console.",
        },
    ), 200


def _frontend_base():
    return str(os.getenv("FRONTEND_URL") or os.getenv("REVELACODE_FRONTEND_URL") or "https://revelacode.co.ke").strip().rstrip("/")


def _return_uri(client):
    if client == "android":
        value = str(os.getenv("GOOGLE_ANDROID_RETURN_URI") or "").strip()
        if not value.startswith("com.revelacode.app://"):
            raise RuntimeError("GOOGLE_ANDROID_RETURN_URI must be the registered RevelaCode Android deep link.")
        return value
    return _frontend_base() + "/oauth/callback"


def _b64url(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _token_hash(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _redirect_result(return_uri, **params):
    separator = "&" if "?" in return_uri else "?"
    return redirect(return_uri + separator + urlencode(params), code=302)


def _load_user_by_id(user_id):
    from bson import ObjectId
    query = {"_id": ObjectId(user_id)} if ObjectId.is_valid(str(user_id)) else {"$or": [{"id": str(user_id)}, {"user_id": str(user_id)}]}
    return get_db()["users"].find_one(query)


def _issue_login_ticket(user, return_uri):
    ticket = secrets.token_urlsafe(36)
    get_db()["oauth_login_tickets"].insert_one({
        "ticket_hash": _token_hash(ticket),
        "user_id": str(user.get("_id") or user.get("id") or user.get("user_id") or ""),
        "provider": "google",
        "created_at": _now(),
        "expires_at": _now() + timedelta(minutes=2),
        "used": False,
    })
    return _redirect_result(return_uri, oauth="success", ticket=ticket)


def _google_claims(id_token, expected_client_id, expected_nonce):
    signing_key = jwt.PyJWKClient(GOOGLE_JWKS).get_signing_key_from_jwt(id_token).key
    claims = jwt.decode(
        id_token,
        signing_key,
        algorithms=["RS256"],
        audience=expected_client_id,
        issuer=["https://accounts.google.com", "accounts.google.com"],
        options={"require": ["sub", "iss", "aud", "exp", "iat", "email", "email_verified"]},
    )
    if claims.get("email_verified") is not True:
        raise ValueError("Google has not verified this email address.")
    if not secrets.compare_digest(str(claims.get("nonce") or ""), expected_nonce):
        raise ValueError("Google sign-in nonce did not match.")
    return claims


@oauth_bp.get("/api/oauth/providers")
def oauth_providers():
    return jsonify(success=True, providers=[
        {"id": "google", "label": "Google", "enabled": bool(os.getenv("GOOGLE_WEB_CLIENT_ID") and os.getenv("GOOGLE_WEB_CLIENT_SECRET"))},
        {"id": "apple", "label": "Apple", "enabled": False},
        {"id": "microsoft", "label": "Microsoft", "enabled": False},
        {"id": "facebook", "label": "Facebook", "enabled": False},
        {"id": "github", "label": "GitHub", "enabled": False},
    ]), 200


@oauth_bp.get("/api/oauth/google/start")
def google_start():
    try:
        _ensure_indexes()
        client_id, _secret, redirect_uri = _client_config()
        mode = str(request.args.get("mode") or "login").strip().lower()
        client = str(request.args.get("client") or "web").strip().lower()
        if mode not in {"login", "link", "invite"} or client not in {"web", "android"}:
            return jsonify(success=False, message="Unsupported Google sign-in mode."), 400
        return_uri = _return_uri(client)
        actor_id = None
        invite_hash = None
        invite_email = None
        if mode == "link":
            actor, error, status = resolve_current_actor(request)
            if error:
                return jsonify(error), status
            actor_id = str(actor.get("id") or "")
            if not actor_id:
                return jsonify(success=False, message="Sign in before connecting Google."), 401
        elif mode == "invite":
            return jsonify(success=False, message="Use the secure invitation POST flow for Google acceptance."), 400

        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = _b64url(secrets.token_bytes(48))
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        get_db()["oauth_states"].insert_one({
            "state_hash": _token_hash(state),
            "nonce": nonce,
            "code_verifier": verifier,
            "mode": mode,
            "client": client,
            "return_uri": return_uri,
            "actor_id": actor_id,
            "invite_token_hash": invite_hash,
            "invite_email": invite_email,
            "created_at": _now(),
            "expires_at": _now() + timedelta(minutes=10),
        })
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        return redirect(GOOGLE_AUTH + "?" + urlencode(params), code=302)
    except RuntimeError as exc:
        return jsonify(success=False, code="google_oauth_not_configured", message=str(exc)), 503
    except Exception:
        return jsonify(success=False, message="Google sign-in could not be started."), 503


@oauth_bp.post("/api/oauth/google/invite/start")
def google_invite_start():
    data = request.get_json(silent=True) or {}
    raw_invite = str(data.get("invite_token") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    client = str(data.get("client") or "web").strip().lower()
    if len(raw_invite) < 32 or "@" not in email or client not in {"web", "android"}:
        return jsonify(success=False, message="The support invitation is incomplete."), 400
    _ensure_indexes()
    invite_hash = _token_hash(raw_invite)
    invitation = get_db()["admin_invitations"].find_one({"token_hash": invite_hash, "contact": email, "status": "pending", "expires_at": {"$gt": _now()}})
    if not invitation:
        return jsonify(success=False, message="The invitation is invalid, expired or does not match this email."), 404
    if invitation.get("invitation_type") == "role_change":
        return jsonify(success=False, code="existing_account_role_change", message="This email belongs to an existing RevelaCode account. Open the request to explicitly accept or decline the role change; no new account or password is required."), 409
    try:
        client_id, _secret, redirect_uri = _client_config()
        return_uri = _return_uri(client)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = _b64url(secrets.token_bytes(48))
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        get_db()["oauth_states"].insert_one({
            "state_hash": _token_hash(state), "nonce": nonce, "code_verifier": verifier,
            "mode": "invite", "client": client, "return_uri": return_uri,
            "invite_token_hash": invite_hash, "invite_email": email,
            "created_at": _now(), "expires_at": _now() + timedelta(minutes=10),
        })
        params = {
            "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": "openid email profile", "state": state, "nonce": nonce,
            "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account",
        }
        return jsonify(success=True, authorization_url=GOOGLE_AUTH + "?" + urlencode(params)), 200
    except RuntimeError as exc:
        return jsonify(success=False, code="google_oauth_not_configured", message=str(exc)), 503


@oauth_bp.get("/api/oauth/google/callback")
def google_callback():
    state = str(request.args.get("state") or "").strip()
    code = str(request.args.get("code") or "").strip()
    if not state:
        return _redirect_result(_frontend_base() + "/oauth/callback", oauth="error", reason="google_authorization_failed")
    _ensure_indexes()
    db = get_db()
    state_row = db["oauth_states"].find_one_and_delete({"state_hash": _token_hash(state), "expires_at": {"$gt": _now()}})
    if not state_row:
        return _redirect_result(_frontend_base() + "/oauth/callback", oauth="error", reason="invalid_or_expired_state")
    if not code:
        # Google redirects here with an error parameter when a user cancels or
        # denies consent. Preserve the original client's return destination so
        # Android returns to its callback route instead of being stranded on web.
        reason = str(request.args.get("error") or "google_authorization_failed")[:120]
        return _redirect_result(state_row["return_uri"], oauth="error", reason=reason)
    try:
        client_id, client_secret, redirect_uri = _client_config()
        response = requests.post(GOOGLE_TOKEN, data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": state_row["code_verifier"],
        }, timeout=15)
        response.raise_for_status()
        token_payload = response.json()
        id_token = str(token_payload.get("id_token") or "")
        if not id_token:
            raise ValueError("Google did not return an ID token.")
        claims = _google_claims(id_token, client_id, state_row["nonce"])
        google_sub = str(claims["sub"])
        email = str(claims["email"]).strip().lower()
        full_name = str(claims.get("name") or claims.get("given_name") or email.split("@")[0])[:120]
        return_uri = state_row["return_uri"]

        # An existing provider subject is authoritative, but the verified
        # email must still match the account's stored verified email.
        user = db["users"].find_one({"oauth_providers.google.sub": google_sub})
        if user:
            stored_email = str(user.get("email") or user.get("contact") or "").strip().lower()
            if stored_email != email or user.get("verified") is not True:
                raise ValueError("The Google identity is not linked to a verified RevelaCode account.")
        elif state_row.get("mode") == "link":
            user = _load_user_by_id(state_row.get("actor_id"))
            if not user or user.get("verified") is not True:
                raise ValueError("The RevelaCode account must have a verified email before linking Google.")
            stored_email = str(user.get("email") or user.get("contact") or "").strip().lower()
            if stored_email != email:
                raise ValueError("The Google email must match the signed-in RevelaCode account.")
            db["users"].update_one({"_id": user["_id"]}, {"$set": {
                "oauth_providers.google": {"sub": google_sub, "email": email, "linked_at": _now()},
            }, "$addToSet": {"login_methods": "google"}})
            user = db["users"].find_one({"_id": user["_id"]})
        elif state_row.get("mode") == "invite":
            invitation = db["admin_invitations"].find_one({
                "token_hash": state_row.get("invite_token_hash"),
                "contact": email,
                "status": "pending",
                "expires_at": {"$gt": _now()},
            })
            if not invitation or email != str(state_row.get("invite_email") or "").lower():
                raise ValueError("The Google email does not match this active support invitation.")
            role = str(invitation.get("role") or "").strip().lower()
            if role not in {"support_admin", "support_agent", "support"}:
                raise ValueError("This invitation does not grant a supported staff role.")
            user_data = {
                "full_name": invitation.get("full_name") or full_name,
                "fullName": invitation.get("full_name") or full_name,
                "name": invitation.get("full_name") or full_name,
                "email": email,
                "contact": email,
                "role": role,
                "roles": [role],
                "verified": True,
                "is_verified": True,
                "is_active": True,
                "status": "active",
                "token_version": 0,
                "oauth_providers": {"google": {"sub": google_sub, "email": email, "linked_at": _now()}},
                "login_methods": ["google"],
                "created_at": _now(),
                "invited_by": invitation.get("invited_by"),
            }
            created = db["users"].insert_one(user_data)
            user = db["users"].find_one({"_id": created.inserted_id})
            db["admin_invitations"].update_one({"_id": invitation["_id"], "status": "pending"}, {"$set": {"status": "accepted", "accepted_at": _now(), "accepted_user_id": str(created.inserted_id)}})
            if role == "support_admin":
                db["support_admin_seats"].update_one({"invitation_id": str(invitation["_id"]), "status": "reserved"}, {"$set": {"status": "active", "member_id": str(created.inserted_id), "activated_at": _now()}})
        else:
            email_match = {"$regex": "^" + __import__("re").escape(email) + "$", "$options": "i"}
            user = db["users"].find_one({"$or": [{"email": email_match}, {"contact": email_match}]})
            if user:
                if user.get("verified") is not True:
                    raise ValueError("This RevelaCode account has not verified its email. Verify it with the existing login method before linking Google.")
                raise ValueError("An account already exists with this email. Sign in using its existing method, then connect Google from Account Center.")
            user_data = {
                "full_name": full_name, "fullName": full_name, "name": full_name,
                "email": email, "contact": email, "role": "user", "roles": ["user"],
                "verified": True, "is_verified": True, "is_active": True, "status": "active",
                "token_version": 0, "oauth_providers": {"google": {"sub": google_sub, "email": email, "linked_at": _now()}},
                "login_methods": ["google"], "created_at": _now(),
            }
            created = db["users"].insert_one(user_data)
            user = db["users"].find_one({"_id": created.inserted_id})

        if not user:
            raise ValueError("The RevelaCode account could not be resolved.")
        return _issue_login_ticket(user, return_uri)
    except ValueError as exc:
        return _redirect_result(state_row.get("return_uri") or (_frontend_base() + "/oauth/callback"), oauth="error", reason=str(exc)[:180])
    except Exception:
        return _redirect_result(state_row.get("return_uri") or (_frontend_base() + "/oauth/callback"), oauth="error", reason="google_sign_in_failed")


@oauth_bp.post("/api/oauth/google/exchange")
def google_exchange():
    ticket = str((request.get_json(silent=True) or {}).get("ticket") or "").strip()
    if len(ticket) < 32:
        return jsonify(success=False, message="A valid one-time login ticket is required."), 400
    db = get_db()
    row = db["oauth_login_tickets"].find_one_and_update(
        {"ticket_hash": _token_hash(ticket), "used": False, "expires_at": {"$gt": _now()}},
        {"$set": {"used": True, "used_at": _now()}},
        return_document=ReturnDocument.BEFORE,
    )
    if not row:
        return jsonify(success=False, message="This Google sign-in ticket has expired or was already used."), 401
    user = _load_user_by_id(row.get("user_id"))
    if not user or user.get("verified") is not True or user.get("is_active") is False or str(user.get("status") or "active") != "active":
        return jsonify(success=False, message="This RevelaCode account is not active."), 403
    return jsonify(success=True, user={
        "id": str(user.get("_id") or user.get("id") or user.get("user_id") or ""),
        "full_name": user.get("full_name") or user.get("name") or "",
        "contact": user.get("contact") or user.get("email") or "",
        "email": user.get("email") or "",
        "role": user.get("role") or "user",
        "roles": user.get("roles") or [user.get("role") or "user"],
        "verified": True,
    }, access_token=create_access_token(user), token_type="Bearer"), 200


@oauth_bp.get("/api/oauth/account")
def oauth_account():
    actor, error, status = resolve_current_actor(request)
    if error:
        return jsonify(error), status
    user = _load_user_by_id(actor.get("id"))
    providers = user.get("oauth_providers") if isinstance(user.get("oauth_providers"), dict) else {}
    return jsonify(success=True, providers=[{"id": key, "connected": bool(value)} for key, value in providers.items()], login_methods=user.get("login_methods") or (["password"] if user.get("password") else [])), 200


@oauth_bp.delete("/api/oauth/google/disconnect")
def google_disconnect():
    actor, error, status = resolve_current_actor(request)
    if error:
        return jsonify(error), status
    user = _load_user_by_id(actor.get("id"))
    if not user:
        return jsonify(success=False, message="Account not found."), 404
    providers = user.get("oauth_providers") if isinstance(user.get("oauth_providers"), dict) else {}
    methods = list(user.get("login_methods") or [])
    has_password = bool(user.get("password"))
    other_providers = [key for key in providers if key != "google" and providers.get(key)]
    if not has_password and not other_providers:
        return jsonify(success=False, code="last_login_method", message="Connect another login method or set a password before disconnecting Google."), 409
    get_db()["users"].update_one({"_id": user["_id"]}, {"$unset": {"oauth_providers.google": ""}, "$pull": {"login_methods": "google"}})
    return jsonify(success=True, message="Google sign-in disconnected."), 200
