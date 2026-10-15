"""Validation and defaults for public Biashara business websites."""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

from backend.jumuiya.core.errors import APIError


DEFAULT_BIASHARA_WEBSITE_SETTINGS = {
    "headline": "",
    "tagline": "",
    "about": "",
    "hero_image_url": "",
    "primary_color": "#1d4ed8",
    "accent_color": "#0f766e",
    "seo_title": "",
    "seo_description": "",
    "whatsapp_number": "",
    "show_products": True,
    "contact_enabled": True,
    "published": False,
    "published_at": None,
    "updated_at": None,
}

WEBSITE_TEXT_LIMITS = {
    "headline": 120,
    "tagline": 240,
    "about": 1600,
    "seo_title": 70,
    "seo_description": 180,
    "whatsapp_number": 32,
}


def normalize_biashara_website_settings(payload, current=None):
    """Validate website settings without accepting arbitrary HTML or scripts."""
    if not isinstance(payload, dict):
        raise APIError("Website settings must be a JSON object.", 400, "invalid_website_settings")

    current = current if isinstance(current, dict) else {}
    result = dict(DEFAULT_BIASHARA_WEBSITE_SETTINGS)
    result.update(current)

    for field, limit in WEBSITE_TEXT_LIMITS.items():
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, str):
            raise APIError(field.replace("_", " ").capitalize() + " must be text.", 422, "validation_error")
        value = value.strip()
        if len(value) > limit:
            raise APIError(field.replace("_", " ").capitalize() + " must be " + str(limit) + " characters or fewer.", 422, "validation_error")
        if "<" in value or ">" in value:
            raise APIError("HTML is not allowed in website text fields.", 422, "invalid_website_text")
        result[field] = value

    for field in ("hero_image_url",):
        if field in payload:
            value = payload[field]
            if not isinstance(value, str):
                raise APIError("Hero image URL must be text.", 422, "validation_error")
            value = value.strip()
            if value:
                try:
                    parsed = urlsplit(value)
                except ValueError as exc:
                    raise APIError("Hero image URL is invalid.", 422, "invalid_website_url") from exc
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    raise APIError("Hero image URL must be a valid HTTPS URL.", 422, "invalid_website_url")
            result[field] = value

    for field in ("primary_color", "accent_color"):
        if field in payload:
            value = payload[field]
            if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value.strip()):
                raise APIError(field.replace("_", " ").capitalize() + " must be a six-digit hex colour.", 422, "invalid_website_color")
            result[field] = value.strip().lower()

    for field in ("show_products", "contact_enabled", "published"):
        if field in payload:
            if not isinstance(payload[field], bool):
                raise APIError(field.replace("_", " ").capitalize() + " must be true or false.", 422, "validation_error")
            result[field] = payload[field]

    if "whatsapp_number" in payload:
        value = result["whatsapp_number"]
        if value and not re.fullmatch(r"[+0-9() .-]{7,32}", value):
            raise APIError("WhatsApp number contains unsupported characters.", 422, "invalid_phone")
        result["whatsapp_number"] = value

    return result

def _trusted_public_base_url(value=None):
    """Return only a configured HTTPS origin; never trust a request Host header."""
    raw = value if value is not None else os.getenv("BIASHARA_PUBLIC_BASE_URL", "")
    raw = str(raw or "").strip().rstrip("/")
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            return None
    except ValueError:
        return None
    host = parsed.hostname.lower().rstrip(".")
    if not host or host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local")):
        return None
    try:
        from ipaddress import ip_address
        parsed_ip = ip_address(host)
        if not parsed_ip.is_global:
            return None
    except ValueError:
        # DNS resolution/domain verification is separate; this validates only
        # that the configured canonical origin is a plausible public hostname.
        if "." not in host or host.startswith(".") or host.endswith("."):
            return None
    try:
        port = parsed.port
    except ValueError:
        return None
    authority_host = "[" + host + "]" if ":" in host else host
    authority = authority_host if port in (None, 443) else f"{authority_host}:{port}"
    return "https://" + authority


def build_biashara_seo_metadata(business, website, slug, public_base_url=None):
    """Build redacted SEO metadata for a published storefront response.

    The caller must enforce publication and business status first. Absolute
    canonical URLs are returned only from a trusted configured public origin.
    """
    business = business if isinstance(business, dict) else {}
    website = website if isinstance(website, dict) else {}
    clean_slug = str(slug or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", clean_slug):
        raise APIError("Business website not found.", 404, "website_not_found")

    path = "/b/" + clean_slug
    origin = _trusted_public_base_url(public_base_url)
    canonical_url = origin + path if origin else None
    title = str(
        website.get("seo_title")
        or website.get("headline")
        or business.get("name")
        or "Business website"
    ).strip()[:70]
    description = str(
        website.get("seo_description")
        or website.get("about")
        or business.get("description")
        or ""
    ).strip()[:180]
    image = str(website.get("hero_image_url") or "").strip()
    if image:
        try:
            parsed_image = urlsplit(image)
            if (
                parsed_image.scheme.lower() != "https"
                or not parsed_image.hostname
                or parsed_image.username
                or parsed_image.password
            ):
                image = ""
        except ValueError:
            image = ""

    open_graph = {
        "type": "website",
        "title": title,
        "description": description,
        "site_name": str(business.get("name") or title)[:160],
        "image": image or None,
        "url": canonical_url,
    }
    twitter_card = {
        "card": "summary_large_image" if image else "summary",
        "title": title,
        "description": description,
        "image": image or None,
        "url": canonical_url,
    }

    structured_data = {
        "@context": "https://schema.org",
        "@type": "Store",
        "name": str(business.get("name") or title)[:160],
        "description": description,
        "address": {
            "@type": "PostalAddress",
            "addressLocality": str(business.get("location") or "")[:120],
            "addressRegion": str(business.get("county") or "")[:120],
            "addressCountry": "KE",
        },
    }
    if canonical_url:
        structured_data["url"] = canonical_url
    logo = str(business.get("logo_url") or "").strip()
    if logo:
        try:
            parsed_logo = urlsplit(logo)
            if (
                parsed_logo.scheme.lower() == "https"
                and parsed_logo.hostname
                and not parsed_logo.username
                and not parsed_logo.password
            ):
                structured_data["image"] = logo
        except ValueError:
            pass
    if image:
        structured_data["photo"] = image
    if website.get("contact_enabled", True) is True:
        phone = str(business.get("phone") or "").strip()
        if phone:
            structured_data["telephone"] = phone

    return {
        "title": title,
        "description": description,
        "canonical_path": path,
        "canonical_url": canonical_url,
        "canonical_origin_configured": bool(origin),
        "indexable": True,
        "robots": "index,follow",
        "open_graph": open_graph,
        "twitter": twitter_card,
        "structured_data": structured_data,
        "domain_verification_status": "not_implemented",
    }

