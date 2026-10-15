"""DNS TXT ownership verification for Biashara custom-domain claims.

A successful TXT check proves control of the DNS zone only. It does not
configure hosting, TLS, reverse-proxy routing, or make the custom domain live.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import secrets
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from backend.jumuiya.core.audit import log_action
from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.biashara.tenancy.service import require_permission


logger = logging.getLogger("jumuiya.biashara.domains")
DOMAINS_COLLECTION = "jumuiya_business_domains"
TXT_PREFIX = "revelacode-domain-verification="
MAX_DOMAIN_LENGTH = 253
LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def now_utc():
    return datetime.now(timezone.utc)


def _clean_id(value):
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return value


def normalize_hostname(value):
    """Normalize a hostname and reject URLs, ports, local names and IP literals."""
    if not isinstance(value, str):
        raise APIError("Domain hostname must be text.", 422, "invalid_domain_hostname")
    raw = value.strip()
    if not raw or len(raw) > 500 or any(ord(char) < 33 for char in raw):
        raise APIError("Domain hostname is empty or invalid.", 422, "invalid_domain_hostname")
    if any(char in raw for char in (":", "/", "@", "?", "#", "\\")):
        raise APIError(
            "Enter only a hostname, for example shop.example.co.ke. Do not include a scheme, port or path.",
            422,
            "invalid_domain_hostname",
        )
    if raw.endswith(".."):
        raise APIError("Domain hostname is invalid.", 422, "invalid_domain_hostname")
    raw = raw[:-1] if raw.endswith(".") else raw
    try:
        hostname = raw.encode("idna").decode("ascii").lower()
    except (UnicodeError, UnicodeDecodeError):
        raise APIError("Domain hostname is not a valid internationalized domain name.", 422, "invalid_domain_hostname")

    if len(hostname) > MAX_DOMAIN_LENGTH or "." not in hostname:
        raise APIError("Enter a fully qualified public domain name.", 422, "invalid_domain_hostname")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith((".localhost", ".local", ".internal")):
        raise APIError("Local-only domains cannot be claimed.", 422, "invalid_domain_hostname")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise APIError("An IP address cannot be claimed as a custom domain.", 422, "invalid_domain_hostname")

    labels = hostname.split(".")
    if any(not LABEL_RE.fullmatch(label) for label in labels):
        raise APIError("Domain hostname contains an invalid label.", 422, "invalid_domain_hostname")
    if len(labels[-1]) < 2:
        raise APIError("Domain hostname must use a valid public suffix.", 422, "invalid_domain_hostname")
    return hostname


def _context(user_id, permission):
    context = require_permission(user_id, permission)
    business_id = str(context.get("id") or "")
    if not business_id:
        raise APIError("Selected business is unavailable.", 409, "business_id_missing")
    return context, business_id


def _public_claim(document, include_challenge=True, verification_result=None):
    hostname = str(document.get("hostname") or "")
    result = {
        "id": str(document.get("_id") or ""),
        "hostname": hostname,
        "business_id": str(document.get("business_id") or ""),
        "status": str(document.get("status") or "pending_dns"),
        "verified": document.get("status") == "verified",
        "record_name": "_revelacode-verification." + hostname,
        "created_at": _json_datetime(document.get("created_at")),
        "updated_at": _json_datetime(document.get("updated_at")),
        "last_checked_at": _json_datetime(document.get("last_checked_at")),
        "verified_at": _json_datetime(document.get("verified_at")),
        "last_check_result": document.get("last_check_result"),
        "domain_serving_status": "not_configured",
        "domain_serving_note": "DNS ownership verification does not configure hosting or TLS.",
    }
    if include_challenge:
        result["record_type"] = "TXT"
        result["record_value"] = TXT_PREFIX + str(document.get("verification_token") or "")
    if verification_result:
        result["verification_result"] = verification_result
    return result


def _json_datetime(value):
    if not isinstance(value, datetime):
        return value
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def list_domain_claims(user_id):
    _context_value, business_id = _context(user_id, "website.view")
    rows = (
        collection(DOMAINS_COLLECTION)
        .find({"business_id": business_id})
        .sort("created_at", -1)
        .limit(20)
    )
    return [_public_claim(row) for row in rows]


def create_domain_claim(user_id, hostname):
    _context_value, business_id = _context(user_id, "website.manage")
    normalized = normalize_hostname(hostname)
    domains = collection(DOMAINS_COLLECTION)
    existing = domains.find_one({"hostname": normalized})
    if existing:
        if str(existing.get("business_id") or "") == business_id:
            return _public_claim(existing)
        raise APIError("This domain is already claimed by another business.", 409, "domain_already_claimed")

    now = now_utc()
    token = secrets.token_urlsafe(32)
    document = {
        "_id": ObjectId(),
        "business_id": business_id,
        "hostname": normalized,
        "status": "pending_dns",
        "verification_token": token,
        "created_by_user_id": str(user_id),
        "created_at": now,
        "updated_at": now,
        "last_checked_at": None,
        "last_check_result": None,
        "verified_at": None,
        "verified_by_user_id": None,
        "verification_method": "dns_txt",
        "domain_serving_status": "not_configured",
    }
    try:
        domains.insert_one(document)
    except DuplicateKeyError:
        existing = domains.find_one({"hostname": normalized})
        if existing and str(existing.get("business_id") or "") == business_id:
            return _public_claim(existing)
        raise APIError("This domain is already claimed by another business.", 409, "domain_already_claimed")

    log_action(user_id, "biashara.domain_claim_created", "business_domain", document["_id"], {
        "hostname": normalized,
        "verification_method": "dns_txt",
    })
    return _public_claim(document)


def _lookup_txt_records(record_name):
    """Resolve TXT values; kept separate so automated tests can fake DNS answers."""
    import dns.resolver

    answer = dns.resolver.resolve(record_name, "TXT", lifetime=4.0)
    values = []
    for record in answer:
        chunks = getattr(record, "strings", None)
        if chunks is not None:
            values.append(b"".join(chunks).decode("utf-8", errors="replace"))
        else:
            values.append(record.to_text().strip('"'))
    return values


def verify_domain_claim(user_id, domain_id):
    _context_value, business_id = _context(user_id, "website.manage")
    domains = collection(DOMAINS_COLLECTION)
    current = domains.find_one({
        "_id": _clean_id(domain_id),
        "business_id": business_id,
    })
    if not current:
        raise APIError("Domain claim not found.", 404, "domain_claim_not_found")
    if current.get("status") == "verified":
        return _public_claim(current, include_challenge=False, verification_result="already_verified")

    hostname = str(current.get("hostname") or "")
    record_name = "_revelacode-verification." + hostname
    expected = TXT_PREFIX + str(current.get("verification_token") or "")
    checked_at = now_utc()
    try:
        records = _lookup_txt_records(record_name)
    except Exception as error:
        # DNS resolvers may raise different exceptions for NXDOMAIN, no answer,
        # or timeout. Do not leak resolver internals into the API response.
        logger.info(
            "Biashara domain verification lookup deferred (domain_hash=%s, error=%s)",
            __import__("hashlib").sha256(hostname.encode("utf-8")).hexdigest()[:12],
            type(error).__name__,
        )
        records = None

    if records is not None and any(
        isinstance(record, str) and secrets.compare_digest(record.strip(), expected)
        for record in records
    ):
        next_status = "verified"
        result = "verified"
        verified_at = checked_at
    else:
        next_status = "pending_dns"
        result = "dns_lookup_failed" if records is None else "verification_txt_record_not_found"
        verified_at = None

    updated = domains.find_one_and_update(
        {
            "_id": current["_id"],
            "business_id": business_id,
            "status": "pending_dns",
        },
        {"$set": {
            "status": next_status,
            "last_checked_at": checked_at,
            "last_check_result": result,
            "verified_at": verified_at,
            "verified_by_user_id": str(user_id) if verified_at else None,
            "updated_at": checked_at,
        }},
    )
    if not updated:
        # Some test adapters or concurrent requests may return no post-update
        # document; read the authoritative current record.
        updated = domains.find_one({"_id": current["_id"], "business_id": business_id})
    if not updated:
        raise APIError("Domain claim changed during verification.", 409, "domain_claim_conflict")

    if verified_at:
        log_action(user_id, "biashara.domain_ownership_verified", "business_domain", current["_id"], {
            "hostname": hostname,
            "method": "dns_txt",
            "domain_serving_status": "not_configured",
        })
    return _public_claim(updated, include_challenge=True, verification_result=result)


def delete_domain_claim(user_id, domain_id):
    _context_value, business_id = _context(user_id, "website.manage")
    domains = collection(DOMAINS_COLLECTION)
    current = domains.find_one({
        "_id": _clean_id(domain_id),
        "business_id": business_id,
    })
    if not current:
        raise APIError("Domain claim not found.", 404, "domain_claim_not_found")
    result = domains.delete_one({
        "_id": current["_id"],
        "business_id": business_id,
    })
    if not getattr(result, "deleted_count", 0):
        raise APIError("Domain claim changed while deleting.", 409, "domain_claim_conflict")
    log_action(user_id, "biashara.domain_claim_deleted", "business_domain", current["_id"], {
        "hostname": current.get("hostname"),
        "was_verified": current.get("status") == "verified",
    })
    return {
        "id": str(current["_id"]),
        "hostname": current.get("hostname"),
        "status": "deleted",
        "domain_serving_status": "not_configured",
    }
