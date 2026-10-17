import pytest

from jumuiya.biashara.website import normalize_biashara_website_settings
from backend.jumuiya.core.errors import APIError


def test_website_settings_accept_safe_publish_configuration():
    result = normalize_biashara_website_settings({
        "headline": "Coastal Electronics",
        "published": True,
        "show_products": True,
        "contact_enabled": False,
        "primary_color": "#123ABC",
    })

    assert result["headline"] == "Coastal Electronics"
    assert result["published"] is True
    assert result["show_products"] is True
    assert result["contact_enabled"] is False
    assert result["primary_color"] == "#123abc"


def test_website_settings_reject_non_https_hero_images():
    with pytest.raises(APIError):
        normalize_biashara_website_settings({
            "hero_image_url": "http://example.com/banner.jpg",
        })


def test_website_settings_reject_invalid_theme_colour():
    with pytest.raises(APIError):
        normalize_biashara_website_settings({
            "primary_color": "red",
        })


def test_website_settings_reject_html_in_headline():
    with pytest.raises(APIError):
        normalize_biashara_website_settings({
            "headline": "<script>alert(1)</script>",
        })


def test_website_settings_reject_non_boolean_flags():
    with pytest.raises(APIError):
        normalize_biashara_website_settings({
            "published": "true",
        })


def test_website_settings_accepts_premium_media_socials_and_domain_request():
    result = normalize_biashara_website_settings({
        "logo_url": "https://cdn.example.com/logo.webp",
        "hero_video_url": "https://www.youtube.com/watch?v=abc123",
        "hero_slides": [
            {"image_url": "https://cdn.example.com/hero.webp", "title": "Welcome", "subtitle": "Made for you"},
            {"video_url": "https://vimeo.com/123456", "title": "Our story"},
        ],
        "gallery_items": [
            {"type": "image", "url": "https://cdn.example.com/product.webp", "caption": "Featured product"},
            {"type": "video", "url": "https://www.youtube.com/watch?v=abc123", "caption": "Product demo"},
        ],
        "social_links": {
            "facebook": "https://facebook.com/coastal",
            "instagram": "https://instagram.com/coastal",
            "tiktok": "https://tiktok.com/@coastal",
        },
        "custom_domain": "shop.example.com",
        "show_gallery": True,
        "show_social_links": True,
    })

    assert result["logo_url"] == "https://cdn.example.com/logo.webp"
    assert len(result["hero_slides"]) == 2
    assert len(result["gallery_items"]) == 2
    assert result["social_links"]["facebook"] == "https://facebook.com/coastal"
    assert result["custom_domain"] == "shop.example.com"
    assert result["domain_status"] == "pending_platform_setup"


def test_website_settings_accepts_compressed_uploaded_image_data_url():
    result = normalize_biashara_website_settings({
        "logo_url": "data:image/webp;base64," + ("A" * 64),
    })
    assert result["logo_url"].startswith("data:image/webp;base64,")


def test_website_settings_rejects_non_https_social_profile():
    with pytest.raises(APIError):
        normalize_biashara_website_settings({
            "social_links": {"facebook": "javascript:alert(1)"},
        })


def test_website_settings_rejects_invalid_custom_domain():
    with pytest.raises(APIError):
        normalize_biashara_website_settings({
            "custom_domain": "https://example.com/path",
        })


def test_website_settings_cannot_trust_client_domain_verification():
    result = normalize_biashara_website_settings({
        "custom_domain": "shop.example.com",
        "domain_status": "active",
    })
    assert result["domain_status"] == "pending_platform_setup"


def test_website_settings_rejects_oversized_uploaded_images():
    with pytest.raises(APIError):
        normalize_biashara_website_settings({
            "logo_url": "data:image/webp;base64," + ("A" * 450_001),
        })
