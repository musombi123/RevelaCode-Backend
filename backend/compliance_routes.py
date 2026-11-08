"""Shared, versioned feature notices and tenant website privacy/cookie controls.

This blueprint uses the existing RevelaCode Mongo database and JWT identity.
It does not create a second account store or treat cookie consent as consent
for unrelated processing purposes.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import jwt
from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, jsonify, request

from backend import auth_gate as auth
from backend.jumuiya.core.database import collection

compliance_bp = Blueprint("compliance_bp", __name__)

NOTICE_CATALOG = {
    "ai_chat": {
        "version": "1.0",
        "title": "AI Chat use notice",
        "body": "AI-generated responses can be incomplete, inaccurate, or out of date. Verify important facts, calculations, citations, legal, medical, financial, and safety-related information using authoritative sources. You remain responsible for decisions and content you submit or publish.",
    },
    "humanizer": {
        "version": "1.0",
        "title": "Humanizer use notice",
        "body": "Humanizer suggestions may change nuance or meaning. Review every edit and retain appropriate attribution and citations. Rewriting does not guarantee originality, academic acceptance, or any AI-detector outcome. Do not use this feature to misrepresent authorship or bypass academic or workplace rules.",
    },
    "ai_vision": {
        "version": "1.0",
        "title": "AI Vision analysis notice",
        "body": "Image and visual analysis may misidentify objects, text, conditions, or context. Treat results as assistance, not a verified inspection or professional diagnosis. Confirm consequential findings independently.",
    },
    "shamba_advisory": {
        "version": "1.0",
        "title": "Shamba advisory notice",
        "body": "Agricultural recommendations are informational estimates and may not reflect local soil, weather, pest, disease, or market conditions. Confirm high-impact decisions with qualified local agricultural officers or other reliable sources. No yield, price, or harvest outcome is guaranteed.",
    },
    "biashara_insights": {
        "version": "1.0",
        "title": "Biashara insights notice",
        "body": "Business, accounting, tax, cash-flow, inventory, and forecasting outputs are decision-support information, not audited accounts or professional financial, tax, or legal advice. Verify records, calculations, and statutory obligations before acting.",
    },
    "elimu_assistant": {
        "version": "1.0",
        "title": "Elimu learning and administration notice",
        "body": "AI-generated learning and school-administration content requires review by an appropriately qualified teacher or authorized school officer. It may contain errors and must not replace professional judgment, school safeguarding procedures, or required approvals. Handle student and child information only where authorized.",
    },
    "faith_content": {
        "version": "1.0",
        "title": "Faith and study content notice",
        "body": "Generated study notes, summaries, interpretations, and references may be incomplete or mistaken. Check quotations and references against the source text and apply your own careful judgment.",
    },
}

FEATURE_ALIASES = {
    "chat": "ai_chat",
    "ai-chat": "ai_chat",
    "humanizer": "humanizer",
    "vision": "ai_vision",
    "shamba": "shamba_advisory",
    "biashara": "biashara_insights",
    "elimu": "elimu_assistant",
    "faith": "faith_content",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _user_from_request():
    authorization = str(request.headers.get("Authorization") or "").strip()
    if not authorization.lower().startswith("bearer "):
        return None, (jsonify(success=False, code="authentication_required"), 401)
    try:
        claims = jwt.decode(
            authorization[7:].strip(),
            auth.JWT_SECRET,
            algorithms=[auth.JWT_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
    except jwt.InvalidTokenError:
        return None, (jsonify(success=False, code="invalid_token"), 401)
    if claims.get("purpose") is not None:
        return None, (jsonify(success=False, code="full_session_required"), 401)
    user_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
    if not user_id:
        return None, (jsonify(success=False, code="invalid_user_identity"), 401)
    try:
        user = None
        if auth.MONGO_AVAILABLE and auth.users_col is not None:
            if ObjectId.is_valid(user_id):
                user = auth.users_col.find_one({"_id": ObjectId(user_id)})
            if user is None:
                user = auth.users_col.find_one({"$or": [{"id": user_id}, {"user_id": user_id}]})
        else:
            for record in auth.load_users_file().values():
                if isinstance(record, dict) and str(record.get("_id") or record.get("id") or record.get("user_id") or "") == user_id:
                    user = record
                    break
    except Exception:
        return None, (jsonify(success=False, code="user_lookup_unavailable"), 503)
    if not user or str(user.get("_id") or user.get("id") or user.get("user_id") or "") != user_id:
        return None, (jsonify(success=False, code="user_not_found"), 401)
    if int(claims.get("token_version") or 0) != int(user.get("token_version") or 0):
        return None, (jsonify(success=False, code="session_revoked"), 401)
    status = str(user.get("status") or "active").casefold()
    if user.get("is_active") is False or status in {"inactive", "disabled", "suspended", "blocked", "banned", "deleted", "revoked"}:
        return None, (jsonify(success=False, code="account_inactive"), 403)
    if user.get("mfa_enabled") is True and claims.get("mfa_verified") is not True:
        return None, (jsonify(success=False, code="mfa_required"), 401)
    return user, None


def _tenant(tenant_type: str, tenant_id: str):
    tenant_type = str(tenant_type or "").strip().lower()
    if tenant_type == "school":
        name = "jumuiya_schools"
        query = {"status": "active", "verification_status": "verified", "public_profile_enabled": True, "is_demo": {"$ne": True}}
    elif tenant_type == "business":
        name = "jumuiya_businesses"
        query = {"status": "active", "verification_status": "verified"}
    else:
        return None
    try:
        oid = ObjectId(str(tenant_id))
    except (InvalidId, TypeError, ValueError):
        return None
    return collection(name).find_one({"_id": oid, **query})


def _policy_defaults(tenant_type: str, tenant: dict):
    tenant_name = str(tenant.get("name") or "This website").strip()
    contact = str(tenant.get("email") or tenant.get("contact_email") or "").strip()
    contact_line = f"Contact: {contact}" if contact else "Contact the website owner using the contact details published on this website."
    privacy = (
        f"# Privacy Policy — {tenant_name}\n\n"
        f"This policy explains how {tenant_name} handles personal information submitted through this website. "
        "The website owner is responsible for identifying the purposes and lawful basis for processing and for responding to privacy requests. "
        "RevelaCode provides website hosting and platform services and may process information on the owner's documented instructions. "
        "The parties' controller/processor roles depend on the actual processing arrangement.\n\n"
        "## Information and purposes\n\n"
        "Information may include details entered into enquiry, contact, application, or service forms; technical information needed to secure and operate the website; and preferences saved for this website. "
        "Information should be collected only where necessary, for a stated purpose, and retained only as long as justified.\n\n"
        + ("## Students and children\n\n"
           "Where this website relates to a school, student or child information must be handled with heightened care. The school should collect only information necessary for a defined educational or administrative purpose, restrict access to authorized personnel, apply age-appropriate safeguards, and obtain parent or guardian authorization where required by law. Student photographs, names, work, and identifiable records must not be published without the required authority and safeguards.\n\n"
           if tenant_type == "school" else "")
        + "## Sharing, security, retention and rights\n\n"
        "Information may be handled by hosting, communication, security, analytics, or other service providers only as appropriate for the disclosed purpose and applicable law. Reasonable technical and organizational safeguards should be used. Individuals may have rights to be informed, access, object, correct, or request deletion, subject to applicable law.\n\n"
        + contact_line
        + "\n\nThis template must be reviewed and completed by the website owner to reflect actual processing, recipients, retention periods, lawful bases, and contact channels."
    )
    cookies = (
        f"# Cookie Policy — {tenant_name}\n\n"
        "This website may use essential cookies or similar storage needed for security, session management, and core functionality. Optional analytics, personalization, and advertising technologies should remain off until the visitor makes a valid choice where consent is required. "
        "The visitor must be able to accept all optional categories, reject optional categories, or customize preferences, and later change or withdraw that choice.\n\n"
        "The exact cookies, providers, purposes, lifetimes, and data recipients must be listed here after the website owner audits the live site and its embedded services. Do not describe a technology as essential unless it is strictly necessary for a service the visitor requested.\n\n"
        + contact_line
        + "\n\nThis template is a starting point, not a substitute for auditing the actual cookies and third-party scripts deployed on this website."
    )
    return {"privacy_policy": privacy, "cookie_policy": cookies, "version": "1.0", "is_template": True}


@compliance_bp.get("/api/compliance/notices")
def list_feature_notices():
    feature = str(request.args.get("feature") or "").strip().lower()
    if feature:
        feature = FEATURE_ALIASES.get(feature, feature)
        notice = NOTICE_CATALOG.get(feature)
        if not notice:
            return jsonify(success=False, code="notice_not_found"), 404
        return jsonify(success=True, feature=feature, notice=notice), 200
    return jsonify(success=True, notices=NOTICE_CATALOG), 200


@compliance_bp.get("/api/compliance/acknowledgements")
def get_feature_acknowledgements():
    user, error = _user_from_request()
    if error:
        return error
    return jsonify(success=True, acknowledgements=user.get("compliance_acknowledgements") or {}), 200


@compliance_bp.post("/api/compliance/acknowledgements")
def acknowledge_feature_notice():
    user, error = _user_from_request()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    feature = FEATURE_ALIASES.get(str(payload.get("feature") or "").strip().lower(), str(payload.get("feature") or "").strip().lower())
    version = str(payload.get("version") or "").strip()
    notice = NOTICE_CATALOG.get(feature)
    if not notice or version != notice["version"] or payload.get("accepted") is not True:
        return jsonify(success=False, code="invalid_notice_acknowledgement"), 422
    acknowledgements = user.get("compliance_acknowledgements")
    if not isinstance(acknowledgements, dict):
        acknowledgements = {}
    acknowledgements[feature] = {
        "version": version,
        "accepted_at": _now(),
    }
    try:
        if auth.MONGO_AVAILABLE and auth.users_col is not None:
            query = {"_id": user["_id"]} if user.get("_id") is not None else {"id": str(user.get("id") or user.get("user_id"))}
            auth.users_col.update_one(query, {"$set": {"compliance_acknowledgements": acknowledgements}})
        else:
            user["compliance_acknowledgements"] = acknowledgements
            auth.save_user_to_file(user)
    except Exception:
        return jsonify(success=False, code="acknowledgement_save_failed"), 503
    return jsonify(success=True, feature=feature, acknowledgement=acknowledgements[feature]), 200


@compliance_bp.get("/api/compliance/websites/<tenant_type>/<tenant_id>/policies")
def get_website_policies(tenant_type: str, tenant_id: str):
    tenant = _tenant(tenant_type, tenant_id)
    if not tenant:
        return jsonify(success=False, code="public_website_not_found"), 404
    defaults = _policy_defaults(tenant_type, tenant)
    saved = collection("jumuiya_website_policies").find_one({
        "tenant_type": tenant_type,
        "tenant_id": str(tenant["_id"]),
    })
    if saved:
        defaults.update({
            "privacy_policy": saved.get("privacy_policy") or defaults["privacy_policy"],
            "cookie_policy": saved.get("cookie_policy") or defaults["cookie_policy"],
            "version": str(saved.get("version") or defaults["version"]),
            "is_template": False,
            "updated_at": saved.get("updated_at"),
        })
    return jsonify(success=True, tenant={"id": str(tenant["_id"]), "name": tenant.get("name", "")}, policies=defaults), 200


@compliance_bp.put("/api/compliance/websites/<tenant_type>/<tenant_id>/policies")
def update_website_policies(tenant_type: str, tenant_id: str):
    user, error = _user_from_request()
    if error:
        return error
    tenant = _tenant(tenant_type, tenant_id)
    if not tenant:
        return jsonify(success=False, code="verified_tenant_required"), 404
    owner_field = "owner_user_id"
    if str(tenant.get(owner_field) or "") != str(user.get("_id") or user.get("id") or user.get("user_id") or ""):
        return jsonify(success=False, code="tenant_owner_required"), 403
    payload = request.get_json(silent=True) or {}
    privacy = payload.get("privacy_policy")
    cookies = payload.get("cookie_policy")
    if not isinstance(privacy, str) or not isinstance(cookies, str) or not privacy.strip() or not cookies.strip():
        return jsonify(success=False, code="both_policies_required"), 422
    if len(privacy) > 30000 or len(cookies) > 20000:
        return jsonify(success=False, code="policy_too_long"), 422
    version = str(payload.get("version") or "1.0").strip()[:40]
    record = {
        "tenant_type": tenant_type,
        "tenant_id": str(tenant["_id"]),
        "privacy_policy": privacy.strip(),
        "cookie_policy": cookies.strip(),
        "version": version,
        "updated_at": _now(),
        "updated_by": str(user.get("_id") or user.get("id") or user.get("user_id") or ""),
    }
    collection("jumuiya_website_policies").update_one(
        {"tenant_type": tenant_type, "tenant_id": str(tenant["_id"])},
        {"$set": record},
        upsert=True,
    )
    return jsonify(success=True, policies={"version": version, "updated_at": record["updated_at"]}), 200


@compliance_bp.post("/api/compliance/websites/<tenant_type>/<tenant_id>/cookie-consent")
def record_website_cookie_consent(tenant_type: str, tenant_id: str):
    tenant = _tenant(tenant_type, tenant_id)
    if not tenant:
        return jsonify(success=False, code="public_website_not_found"), 404
    payload = request.get_json(silent=True) or {}
    preferences = payload.get("preferences")
    if not isinstance(preferences, dict):
        return jsonify(success=False, code="cookie_preferences_required"), 422
    analytics = preferences.get("analytics") is True
    advertising = preferences.get("advertising") is True
    personalization = preferences.get("personalization") is True
    consent_id = str(payload.get("consent_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", consent_id):
        return jsonify(success=False, code="valid_consent_id_required"), 422
    version = str(payload.get("policy_version") or "1.0").strip()[:40]
    collection("jumuiya_website_cookie_consents").update_one(
        {"tenant_type": tenant_type, "tenant_id": str(tenant["_id"]), "consent_id": consent_id},
        {"$set": {
            "tenant_type": tenant_type,
            "tenant_id": str(tenant["_id"]),
            "consent_id": consent_id,
            "policy_version": version,
            "preferences": {
                "essential": True,
                "analytics": analytics,
                "advertising": advertising,
                "personalization": personalization,
            },
            "updated_at": _now(),
            "source": "website_cookie_banner",
        }},
        upsert=True,
    )
    return jsonify(success=True, preferences={
        "essential": True,
        "analytics": analytics,
        "advertising": advertising,
        "personalization": personalization,
    }), 200
