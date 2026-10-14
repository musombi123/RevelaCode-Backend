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
