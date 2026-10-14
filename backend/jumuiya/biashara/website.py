"""Validation and defaults for public Biashara business websites."""

from __future__ import annotations

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
