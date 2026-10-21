"""Authenticated account-profile exports and verifiable RevelaCode account certificates.

These are account identity/participation documents, not academic qualifications,
professional licences, or external accreditation. Source data comes from the
RevelaCode users collection and explicitly recorded hub-affiliation fields.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Any

import jwt
from bson import ObjectId
from flask import Blueprint, jsonify, request, send_file
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from backend.db import db

account_documents_bp = Blueprint("account_documents_bp", __name__)
users_col = db.get_collection("users")
certificates_col = db.get_collection("revelacode_account_certificates")
JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
JWT_ALGORITHM = "HS256"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items() if not str(k).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _authenticated_user():
    if not JWT_SECRET:
        return None, (jsonify(success=False, error={"code": "auth_not_configured", "message": "Authentication is not configured."}), 503)
    authorization = (request.headers.get("Authorization") or "").strip()
    if not authorization.lower().startswith("bearer "):
        return None, (jsonify(success=False, error={"code": "authentication_required", "message": "Sign in to access account documents."}), 401)
    token = authorization[7:].strip()
    if not token:
        return None, (jsonify(success=False, error={"code": "authentication_required", "message": "A Bearer token is required."}), 401)
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "iat", "exp"]})
    except jwt.ExpiredSignatureError:
        return None, (jsonify(success=False, error={"code": "token_expired", "message": "Your session has expired. Sign in again."}), 401)
    except jwt.InvalidTokenError:
        return None, (jsonify(success=False, error={"code": "invalid_token", "message": "The authentication token is invalid."}), 401)
    user_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
    if not user_id or len(user_id) > 128:
        return None, (jsonify(success=False, error={"code": "invalid_user_identity", "message": "The token does not identify an account."}), 401)
    query = {"$or": [{"id": user_id}, {"user_id": user_id}]}
    if ObjectId.is_valid(user_id):
        query = {"$or": [{"_id": ObjectId(user_id)}, {"id": user_id}, {"user_id": user_id}]}
    try:
        user = users_col.find_one(query)
    except Exception:
        return None, (jsonify(success=False, error={"code": "account_lookup_unavailable", "message": "Account data is temporarily unavailable."}), 503)
    if not user:
        return None, (jsonify(success=False, error={"code": "user_not_found", "message": "The account for this session no longer exists."}), 404)
    # Tokens may identify the same account by Mongo ObjectId, legacy "id",
    # or "user_id". Validate against every trusted identifier on the matched
    # record instead of assuming that Mongo's _id is always the JWT subject.
    account_ids = {
        str(value).strip()
        for value in (user.get("_id"), user.get("id"), user.get("user_id"))
        if value is not None and str(value).strip()
    }
    if user_id not in account_ids:
        return None, (jsonify(success=False, error={"code": "user_identity_mismatch", "message": "The session identity does not match the account record."}), 403)
    return user, None


def _roles(user: dict) -> list[str]:
    raw = user.get("roles")
    values = list(raw) if isinstance(raw, list) else ([raw] if isinstance(raw, str) and raw.strip() else [])
    if user.get("role"):
        values.append(user["role"])
    normalized = []
    seen = set()
    for item in values:
        role = str(item or "").strip()
        if role and role.casefold() not in seen:
            seen.add(role.casefold())
            normalized.append(role)
    return normalized or ["user"]


def _hubs(user: dict) -> list[dict]:
    """Report explicit hub data and authoritative active Elimu school memberships."""
    raw = user.get("hub_usage")
    if not isinstance(raw, list):
        raw = user.get("current_hubs")
    if not isinstance(raw, list):
        raw = user.get("hubs")
    if not isinstance(raw, list):
        raw = []
    result = []
    seen = set()
    for item in raw:
        if isinstance(item, str):
            entry = {"name": item.strip(), "status": "recorded"}
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("hub_name") or item.get("title") or "").strip()
            if not name:
                continue
            entry = {
                "id": str(item.get("id") or item.get("hub_id") or ""),
                "name": name,
                "status": str(item.get("status") or item.get("membership_status") or "recorded"),
                "role": str(item.get("role") or item.get("hub_role") or ""),
                "last_accessed": _iso(item.get("last_accessed") or item.get("lastAccessed")),
            }
            for key in ("progress_percent", "completed_lessons", "total_lessons", "time_spent_label"):
                if item.get(key) is not None:
                    entry[key] = item[key]
        else:
            continue
        key = entry["name"].casefold()
        if key and key not in seen:
            seen.add(key)
            result.append(entry)

    # Elimu school membership is stored separately from the core user record.
    # Include only active/accepted memberships belonging to this authenticated ID.
    user_id = str(user.get("_id") or user.get("id") or user.get("user_id") or "")
    if user_id:
        try:
            members = db.get_collection("jumuiya_elimu_school_members")
            for membership in members.find({
                "user_id": user_id,
                "status": {"$in": ["active", "accepted"]},
            }):
                school_id = str(membership.get("school_id") or membership.get("school_oid") or "")
                school = None
                if school_id:
                    school_query = {"$or": [{"_id": school_id}, {"id": school_id}, {"school_id": school_id}]}
                    if ObjectId.is_valid(school_id):
                        school_query["$or"].insert(0, {"_id": ObjectId(school_id)})
                    school = db.get_collection("jumuiya_schools").find_one(school_query, {"name": 1, "school_name": 1, "display_name": 1})
                school_name = str((school or {}).get("name") or (school or {}).get("school_name") or (school or {}).get("display_name") or membership.get("school_name") or "School affiliation").strip()
                key = f"elimu:{school_id}:{school_name}".casefold()
                if key in seen:
                    continue
                seen.add(key)
                result.append({
                    "id": school_id,
                    "name": "Elimu",
                    "status": str(membership.get("status") or "active"),
                    "role": str(membership.get("role") or membership.get("school_role") or ""),
                    "institution": school_name,
                    "joined_at": _iso(membership.get("created_at") or membership.get("joined_at")),
                })
        except Exception:
            # Core profile export remains available if an optional hub registry
            # is temporarily unavailable; it does not fabricate missing records.
            pass
    return result


def _profile(user: dict) -> dict:
    roles = _roles(user)
    hubs = _hubs(user)
    contact = str(user.get("contact") or user.get("email") or "")
    verified = bool(user.get("verified", user.get("is_verified", False)))
    public_profile = {
        "id": str(user.get("_id") or user.get("id") or user.get("user_id") or ""),
        "full_name": str(user.get("full_name") or user.get("fullName") or user.get("name") or user.get("username") or ""),
        "username": str(user.get("username") or ""),
        "contact": contact,
        "email": str(user.get("email") or (contact if "@" in contact else "")),
        "phone": str(user.get("phone") or (contact if "@" not in contact else "")),
        "verified": verified,
        "account_status": str(user.get("status") or ("active" if verified else "unverified")),
        "created_at": _iso(user.get("created_at") or user.get("joined_at")),
        "roles": roles,
        "role": roles[0] if roles else "user",
        "hubs": hubs,
        "hubs_count": len(hubs),
        "certificates_count": certificates_col.count_documents({"user_id": str(user.get("_id") or user.get("id") or user.get("user_id") or "")}),
        "document_issued_at": _now().isoformat(),
        "issuer": "RevelaCode",
        "document_scope": "Account identity and recorded platform participation",
    }
    # Never serialize credential or operational secrets into an export.
    return public_profile


def _canonical_signature(claims: dict) -> str:
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured")
    # Domain-separate certificate signatures from login JWT signatures.
    configured_key = os.getenv("REVELACODE_CERTIFICATE_SIGNING_KEY", "").strip()
    signing_key = (
        configured_key.encode("utf-8")
        if configured_key
        else hmac.new(
            JWT_SECRET.encode("utf-8"),
            b"revelacode-account-certificate-v1",
            hashlib.sha256,
        ).digest()
    )
    payload = json.dumps(claims, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hmac.new(signing_key, payload, hashlib.sha256).hexdigest()


def _pdf(title: str, subtitle: str, rows: list[tuple[str, str]], footer: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=22*mm, bottomMargin=20*mm, title=title, author="RevelaCode")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="RCBrand", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=colors.HexColor("#0A74DA"), spaceAfter=5))
    styles.add(ParagraphStyle(name="RCSubtitle", parent=styles["Heading2"], fontSize=13, leading=18, textColor=colors.HexColor("#2E8B57"), spaceAfter=15))
    styles.add(ParagraphStyle(name="RCBody", parent=styles["BodyText"], fontSize=9, leading=13, textColor=colors.HexColor("#263238")))
    story = [Paragraph("RevelaCode", styles["RCBrand"]), Paragraph(title, styles["RCSubtitle"]), Paragraph(subtitle, styles["BodyText"]), Spacer(1, 7*mm)]
    table_data = []
    for label, value in rows:
        safe_label = str(label).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_value = str(value or "Not recorded").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
        table_data.append([Paragraph(f"<b>{safe_label}</b>", styles["RCBody"]), Paragraph(safe_value, styles["RCBody"])])
    table = Table(table_data, colWidths=[47*mm, 115*mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#EEF5FC")),
        ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#D6E0E8")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    story.extend([table, Spacer(1, 8*mm), Paragraph(footer.replace("&", "&amp;"), styles["Italic"])])
    doc.build(story)
    return buffer.getvalue()


def _profile_pdf(profile: dict) -> bytes:
    hub_text = "\n".join(
        f"{hub['name']} — {hub.get('status', 'recorded')}" + (f" — institution: {hub['institution']}" if hub.get("institution") else "") + (f" — role: {hub['role']}" if hub.get("role") else "") + (f" — progress: {hub['progress_percent']}%" if hub.get("progress_percent") is not None else "")
        for hub in profile.get("hubs", [])
    ) or "No hub usage/affiliation data is recorded on this account."
    rows = [
        ("Full name", profile.get("full_name")),
        ("Account ID", profile.get("id")),
        ("Username", profile.get("username")),
        ("Email", profile.get("email")),
        ("Phone", profile.get("phone")),
        ("Account verified", "Yes" if profile.get("verified") else "No"),
        ("Account status", profile.get("account_status")),
        ("Account created", profile.get("created_at")),
        ("Roles", ", ".join(profile.get("roles", []))),
        ("Recorded hubs", hub_text),
        ("Hub count", profile.get("hubs_count")),
        ("Document reference", f"RC-PROFILE-{profile.get('id')}"),
        ("Issued at (UTC)", profile.get("document_issued_at")),
    ]
    return _pdf("Account Profile", "Authenticated account record", rows, "This document summarizes account data available from RevelaCode at the issue time. It is not proof of academic qualification or external accreditation.")


def _certificate_pdf(record: dict) -> bytes:
    claims = record["claims"]
    hubs = claims.get("hubs") or []
    hub_text = "\n".join(
        f"{hub.get('name', 'Hub')} — {hub.get('status', 'recorded')}" + (f" — institution: {hub['institution']}" if hub.get("institution") else "") + (f" — role: {hub['role']}" if hub.get("role") else "") + (f" — progress: {hub['progress_percent']}%" if hub.get("progress_percent") is not None else "")
        for hub in hubs
    ) or "No hub usage/affiliation data was recorded at issuance."
    rows = [
        ("Certificate number", record["certificate_id"]),
        ("Issued to", claims.get("full_name")),
        ("Account ID", claims.get("user_id")),
        ("Verified account", "Yes" if claims.get("verified") else "No"),
        ("Roles recorded", ", ".join(claims.get("roles") or [])),
        ("Hub affiliations recorded", hub_text),
        ("Issue date (UTC)", claims.get("issued_at")),
        ("Verification URL", claims.get("verification_url")),
        ("Issuer", "RevelaCode"),
        ("Certificate scope", "Account identity and recorded platform participation only"),
    ]
    return _pdf("RevelaCode Account Certificate", "Certificate of account identity and recorded platform participation", rows, "This is an account identity/participation certificate, not an academic qualification, professional licence, competency award, or government accreditation. Public verification checks the issued record and its server-side signature.")


@account_documents_bp.route("/api/accounts/profile/download", methods=["GET"])
def download_account_profile():
    user, error = _authenticated_user()
    if error:
        return error
    profile = _profile(user)
    output_format = (request.args.get("format") or "pdf").strip().lower()
    if output_format == "json":
        response = jsonify(success=True, profile=profile)
        response.headers["Cache-Control"] = "no-store"
        return response
    if output_format != "pdf":
        return jsonify(success=False, error={"code": "unsupported_format", "message": "Supported formats are pdf and json."}), 400
    raw = _profile_pdf(profile)
    response = send_file(io.BytesIO(raw), mimetype="application/pdf", as_attachment=True, download_name=f"revelacode-profile-{re.sub(r'[^A-Za-z0-9_-]+', '-', profile['id'])}.pdf", max_age=0)
    response.headers["Cache-Control"] = "no-store"
    return response


@account_documents_bp.route("/api/accounts/certificates", methods=["POST"])
def issue_account_certificate():
    user, error = _authenticated_user()
    if error:
        return error
    profile = _profile(user)
    user_id = profile["id"]
    if not profile["verified"]:
        return jsonify(success=False, error={"code": "account_not_verified", "message": "Verify your RevelaCode account before requesting an account certificate."}), 409
    # Issue one active account certificate per user; repeated calls are idempotent.
    existing = certificates_col.find_one({"user_id": user_id, "status": "active"})
    if existing:
        return jsonify(success=True, certificate_id=existing["certificate_id"], already_issued=True, verification_url=existing["claims"]["verification_url"], download_url=f"/api/accounts/certificates/{existing['certificate_id']}/download")
    issued_at = _now().isoformat()
    certificate_id = "RC-AC-" + secrets.token_hex(8).upper()
    # Include account-level roles plus role responsibilities recorded by
    # authoritative hub affiliations. Preserve the source role text and qualify
    # hub roles so they cannot be mistaken for global platform privileges.
    certificate_roles = list(profile["roles"])
    seen_roles = {role.casefold() for role in certificate_roles}
    for hub in profile["hubs"]:
        hub_role = str(hub.get("role") or "").strip()
        if not hub_role:
            continue
        context = str(hub.get("institution") or hub.get("name") or "Platform hub").strip()
        qualified_role = f"{hub_role} ({context})"
        if qualified_role.casefold() not in seen_roles:
            seen_roles.add(qualified_role.casefold())
            certificate_roles.append(qualified_role)

    claims = {
        "certificate_id": certificate_id,
        "user_id": user_id,
        "full_name": profile["full_name"],
        "verified": profile["verified"],
        "roles": certificate_roles,
        "hubs": profile["hubs"],
        "issued_at": issued_at,
        "issuer": "RevelaCode",
        "scope": "account_identity_and_recorded_platform_participation",
    }
    public_root = os.getenv("REVELACODE_PUBLIC_URL", "https://revelacode.co.ke").strip().rstrip("/")
    if not public_root.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        public_root = "https://revelacode.co.ke"
    claims["verification_url"] = f"{public_root}/verify/certificate/{certificate_id}"
    signature = _canonical_signature(claims)
    record = {
        "certificate_id": certificate_id,
        "user_id": user_id,
        "status": "active",
        "claims": claims,
        "signature": signature,
        "signature_algorithm": "HMAC-SHA256",
        "created_at": _now(),
    }
    certificates_col.insert_one(record)
    return jsonify(success=True, certificate_id=certificate_id, already_issued=False, verification_url=claims["verification_url"], download_url=f"/api/accounts/certificates/{certificate_id}/download"), 201


@account_documents_bp.route("/api/accounts/certificates/<certificate_id>/download", methods=["GET"])
def download_account_certificate(certificate_id: str):
    user, error = _authenticated_user()
    if error:
        return error
    certificate_id = str(certificate_id or "").strip()
    record = certificates_col.find_one({"certificate_id": certificate_id, "user_id": str(user.get("_id") or user.get("id") or user.get("user_id") or ""), "status": "active"})
    if not record:
        return jsonify(success=False, error={"code": "certificate_not_found", "message": "No active certificate was found for this account."}), 404
    if not hmac.compare_digest(str(record.get("signature") or ""), _canonical_signature(record.get("claims") or {})):
        return jsonify(success=False, error={"code": "certificate_signature_invalid", "message": "The certificate record failed integrity verification."}), 409
    raw = _certificate_pdf(record)
    response = send_file(io.BytesIO(raw), mimetype="application/pdf", as_attachment=True, download_name=f"{certificate_id}.pdf", max_age=0)
    response.headers["Cache-Control"] = "no-store"
    return response


@account_documents_bp.route("/api/accounts/certificates/<certificate_id>/revoke", methods=["POST"])
def revoke_account_certificate(certificate_id: str):
    user, error = _authenticated_user()
    if error:
        return error
    admin_roles = {"admin", "platform_admin", "super_admin", "revelacode_admin"}
    if not admin_roles.intersection({role.casefold() for role in _roles(user)}):
        return jsonify(success=False, error={"code": "admin_required", "message": "A RevelaCode platform administrator is required to revoke a certificate."}), 403
    reason_payload = request.get_json(silent=True) or {}
    reason = str(reason_payload.get("reason") or "Revoked by platform administrator").strip()[:500]
    result = certificates_col.update_one(
        {"certificate_id": str(certificate_id or "").strip(), "status": "active"},
        {"$set": {"status": "revoked", "revoked_at": _now(), "revoked_by": str(user.get("_id") or user.get("id") or user.get("user_id") or ""), "revocation_reason": reason}},
    )
    if result.matched_count == 0:
        return jsonify(success=False, error={"code": "active_certificate_not_found", "message": "No active certificate was found for revocation."}), 404
    return jsonify(success=True, certificate_id=certificate_id, status="revoked"), 200


@account_documents_bp.route("/api/verify/certificate/<certificate_id>", methods=["GET"])
def verify_account_certificate(certificate_id: str):
    certificate_id = str(certificate_id or "").strip()
    if not re.fullmatch(r"RC-AC-[A-F0-9]{16}", certificate_id):
        return jsonify(valid=False, certificate_id=certificate_id, reason="certificate_not_found"), 404
    record = certificates_col.find_one({"certificate_id": certificate_id})
    if not record:
        return jsonify(valid=False, certificate_id=certificate_id, reason="certificate_not_found"), 404
    if record.get("status") != "active":
        return jsonify(valid=False, certificate_id=certificate_id, reason="certificate_revoked"), 200
    claims = record.get("claims") or {}
    expected = _canonical_signature(claims)
    if not hmac.compare_digest(str(record.get("signature") or ""), expected):
        return jsonify(valid=False, certificate_id=certificate_id, reason="signature_invalid"), 200
    # Public verification exposes only fields needed to validate the account
    # certificate. Internal school IDs, access timestamps, and other metadata
    # remain private even when stored in the signed claims.
    public_hubs = []
    for item in claims.get("hubs") or []:
        if isinstance(item, str):
            name = item.strip()
            if name:
                public_hubs.append({"name": name, "status": "recorded"})
            continue
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("hub_name") or item.get("title") or "").strip()
        if not name:
            continue
        hub = {
            "name": name,
            "status": str(item.get("status") or item.get("membership_status") or "recorded"),
        }
        role = str(item.get("role") or item.get("hub_role") or "").strip()
        institution = str(item.get("institution") or "").strip()
        if role:
            hub["role"] = role
        if institution:
            hub["institution"] = institution
        public_hubs.append(hub)

    return jsonify(
        valid=True,
        certified_by="RevelaCode",
        certificate_id=certificate_id,
        user={"name": claims.get("full_name"), "roles": claims.get("roles") or []},
        hub={"name": "Recorded platform affiliations", "hubs": public_hubs},
        hubs=public_hubs,
        roles=claims.get("roles") or [],
        issued_at=claims.get("issued_at"),
        verification_url=claims.get("verification_url"),
        signature_algorithm="HMAC-SHA256",
        certificate_scope="Account identity and recorded platform participation; not an academic or professional qualification.",
    )
