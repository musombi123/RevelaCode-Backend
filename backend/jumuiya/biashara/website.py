"""Validation and defaults for premium public Biashara websites."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from backend.jumuiya.core.errors import APIError


DEFAULT_BIASHARA_WEBSITE_SETTINGS = {
    "headline": "",
    "tagline": "",
    "about": "",
    "logo_url": "",
    "cover_image_url": "",
    "hero_image_url": "",
    "hero_video_url": "",
    "hero_slides": [],
    "service_items": [],
    "gallery_items": [],
    "social_links": {},
    "custom_domain": "",
    "domain_status": "not_configured",
    "domain_setup_requested_at": None,
    "announcement": "",
    "footer_message": "",
    "show_products": True,
    "show_services": True,
    "show_gallery": True,
    "show_social_links": True,
    "contact_enabled": True,
    "primary_color": "#1d4ed8",
    "accent_color": "#0f766e",
    "seo_title": "",
    "seo_description": "",
    "whatsapp_number": "",
    "published": False,
    "published_at": None,
    "updated_at": None,
}

WEBSITE_TEXT_LIMITS = {
    "headline": 120,
    "tagline": 240,
    "about": 1600,
    "announcement": 180,
    "footer_message": 240,
    "seo_title": 70,
    "seo_description": 180,
    "whatsapp_number": 32,
}

SOCIAL_FIELDS = (
    "facebook",
    "instagram",
    "messenger",
    "tiktok",
    "youtube",
    "x",
    "linkedin",
    "telegram",
    "pinterest",
    "snapchat",
    "threads",
    "whatsapp_channel",
    "reddit",
    "discord",
    "twitch",
    "bluesky",
    "mastodon",
    "github",
    "medium",
    "wechat",
    "vk",
    "rumble",
    "line",
    "signal",
    "website",
    "other",
)

MAX_EMBEDDED_IMAGE_LENGTH = 450_000
MAX_URL_LENGTH = 1200


def _clean_text(field, value, limit):
    if not isinstance(value, str):
        raise APIError(field.replace("_", " ").capitalize() + " must be text.", 422, "validation_error")
    value = value.strip()
    if len(value) > limit:
        raise APIError(field.replace("_", " ").capitalize() + " must be " + str(limit) + " characters or fewer.", 422, "validation_error")
    if "<" in value or ">" in value:
        raise APIError("HTML is not allowed in website text fields.", 422, "invalid_website_text")
    return value


def _safe_https_url(field, value, allow_embedded_image=False):
    if not isinstance(value, str):
        raise APIError(field.replace("_", " ").capitalize() + " must be text.", 422, "validation_error")
    value = value.strip()
    if not value:
        return ""
    if len(value) > MAX_URL_LENGTH and not (allow_embedded_image and value.startswith("data:image/")):
        raise APIError(field.replace("_", " ").capitalize() + " is too long.", 422, "invalid_website_url")

    if allow_embedded_image and value.startswith("data:image/"):
        pattern = r"data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}"
        if len(value) > MAX_EMBEDDED_IMAGE_LENGTH or not re.fullmatch(pattern, value):
            raise APIError("Uploaded images must be valid PNG, JPEG, or WebP files under the image-size limit.", 422, "invalid_website_image")
        return value

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        # Accessing .port also detects malformed port values.
        _ = parsed.port
    except ValueError as exc:
        raise APIError(field.replace("_", " ").capitalize() + " is invalid.", 422, "invalid_website_url") from exc
    if parsed.scheme.lower() != "https" or not hostname or parsed.username or parsed.password:
        raise APIError(field.replace("_", " ").capitalize() + " must be a valid HTTPS URL.", 422, "invalid_website_url")
    return value


def _normalise_media_items(value, field, limit, allow_video=True):
    if not isinstance(value, list) or len(value) > limit:
        raise APIError(field.replace("_", " ").capitalize() + " must be a list of no more than " + str(limit) + " items.", 422, "invalid_website_media")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise APIError(field.replace("_", " ").capitalize() + " items must be objects.", 422, "invalid_website_media")

        media = {}
        if field == "hero_slides":
            media["image_url"] = _safe_https_url(field + " image", item.get("image_url", ""), allow_embedded_image=True)
            media["video_url"] = _safe_https_url(field + " video", item.get("video_url", "")) if allow_video else ""
            media["title"] = _clean_text("slide title", item.get("title", ""), 120)
            media["subtitle"] = _clean_text("slide subtitle", item.get("subtitle", ""), 240)
            media["alt"] = _clean_text("slide alt text", item.get("alt", ""), 140)
            if not media["image_url"] and not media["video_url"]:
                raise APIError("Each hero slide needs an image or video URL.", 422, "invalid_website_media")
        else:
            media_type = item.get("type", "image")
            if media_type not in ("image", "video"):
                raise APIError("Gallery media type must be image or video.", 422, "invalid_website_media")
            media["type"] = media_type
            media["url"] = _safe_https_url("gallery media URL", item.get("url", ""), allow_embedded_image=(media_type == "image"))
            media["caption"] = _clean_text("gallery caption", item.get("caption", ""), 180)
            media["alt"] = _clean_text("gallery alt text", item.get("alt", ""), 140)
            if not media["url"]:
                raise APIError("Each gallery item needs a media URL.", 422, "invalid_website_media")
        result.append(media)
    return result


def normalize_biashara_website_settings(payload, current=None):
    """Validate website settings without accepting arbitrary HTML, scripts, or client-trusted domain state."""
    if not isinstance(payload, dict):
        raise APIError("Website settings must be a JSON object.", 400, "invalid_website_settings")

    current = current if isinstance(current, dict) else {}
    result = dict(DEFAULT_BIASHARA_WEBSITE_SETTINGS)
    result.update(current)
    result["hero_slides"] = list(current.get("hero_slides", [])) if isinstance(current.get("hero_slides"), list) else []
    result["service_items"] = list(current.get("service_items", [])) if isinstance(current.get("service_items"), list) else []
    result["gallery_items"] = list(current.get("gallery_items", [])) if isinstance(current.get("gallery_items"), list) else []
    result["social_links"] = dict(current.get("social_links", {})) if isinstance(current.get("social_links"), dict) else {}

    for field, limit in WEBSITE_TEXT_LIMITS.items():
        if field in payload:
            result[field] = _clean_text(field, payload[field], limit)

    for field in ("logo_url", "cover_image_url", "hero_image_url"):
        if field in payload:
            result[field] = _safe_https_url(field, payload[field], allow_embedded_image=True)

    if "hero_video_url" in payload:
        result["hero_video_url"] = _safe_https_url("hero video URL", payload["hero_video_url"])

    if "hero_slides" in payload:
        result["hero_slides"] = _normalise_media_items(payload["hero_slides"], "hero_slides", 8)
    if "service_items" in payload:
        raw_services = payload["service_items"]
        if not isinstance(raw_services, list) or len(raw_services) > 12:
            raise APIError("Service items must be a list of no more than 12 items.", 422, "invalid_website_services")
        services = []
        for item in raw_services:
            if not isinstance(item, dict):
                raise APIError("Each service item must be an object.", 422, "invalid_website_services")
            title = _clean_text("service title", item.get("title", ""), 100)
            description = _clean_text("service description", item.get("description", ""), 600)
            price_label = _clean_text("service price", item.get("price_label", ""), 80)
            image_url = _safe_https_url("service image", item.get("image_url", ""), allow_embedded_image=True)
            if not title:
                raise APIError("Each service item requires a title.", 422, "invalid_website_services")
            services.append({
                "title": title,
                "description": description,
                "price_label": price_label,
                "image_url": image_url,
            })
        result["service_items"] = services

    if "gallery_items" in payload:
        result["gallery_items"] = _normalise_media_items(payload["gallery_items"], "gallery_items", 12)

    if "social_links" in payload:
        raw_socials = payload["social_links"]
        if not isinstance(raw_socials, dict):
            raise APIError("Social links must be an object of profile URLs.", 422, "invalid_social_links")
        socials = {}
        for field in SOCIAL_FIELDS:
            raw_value = raw_socials.get(field, "")
            if raw_value is None:
                raw_value = ""
            if not isinstance(raw_value, str):
                raise APIError("Social profile URLs must be text.", 422, "invalid_social_links")
            raw_value = raw_value.strip()
            if raw_value:
                socials[field] = _safe_https_url(field + " profile URL", raw_value)
            else:
                socials[field] = ""
        result["social_links"] = socials

    if "custom_domain" in payload:
        value = payload["custom_domain"]
        if not isinstance(value, str):
            raise APIError("Custom domain must be text.", 422, "invalid_custom_domain")
        value = value.strip().lower().rstrip(".")
        if value and (
            len(value) > 253
            or not re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", value)
        ):
            raise APIError("Enter a domain name only, such as shop.example.com. Do not include https:// or a path.", 422, "invalid_custom_domain")
        result["custom_domain"] = value

    for field in ("primary_color", "accent_color"):
        if field in payload:
            value = payload[field]
            if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value.strip()):
                raise APIError(field.replace("_", " ").capitalize() + " must be a six-digit hex colour.", 422, "invalid_website_color")
            result[field] = value.strip().lower()

    for field in ("show_products", "show_services", "show_gallery", "show_social_links", "contact_enabled", "published"):
        if field in payload:
            if not isinstance(payload[field], bool):
                raise APIError(field.replace("_", " ").capitalize() + " must be true or false.", 422, "validation_error")
            result[field] = payload[field]

    if "whatsapp_number" in payload:
        value = result["whatsapp_number"]
        if value and not re.fullmatch(r"[+0-9() .-]{7,32}", value):
            raise APIError("WhatsApp number contains unsupported characters.", 422, "invalid_phone")
        result["whatsapp_number"] = value

    # These fields are server-managed. Ignore any client attempt to mark a domain verified.
    if not result.get("custom_domain"):
        result["domain_status"] = "not_configured"
        result["domain_setup_requested_at"] = None
    elif result.get("domain_status") not in ("pending_platform_setup", "active"):
        result["domain_status"] = "pending_platform_setup"
        result["domain_setup_requested_at"] = None

    return result
