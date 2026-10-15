import pytest

from jumuiya.biashara.website import (
    build_biashara_seo_metadata,
    normalize_biashara_website_settings,
)
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

def test_published_storefront_seo_uses_trusted_canonical_origin():
    business = {
        "name": "Coastal Electronics",
        "slug": "coastal-electronics",
        "description": "Phones and accessories in Mombasa.",
        "location": "Kongowea",
        "county": "Mombasa",
        "phone": "+254700111222",
        "email": "sales@example.test",
        "logo_url": "https://cdn.example.test/logo.png",
    }
    website = {
        "headline": "Coastal Electronics",
        "seo_title": "Coastal Electronics | Mombasa",
        "seo_description": "Shop phones and accessories in Mombasa.",
        "hero_image_url": "https://cdn.example.test/hero.jpg",
        "contact_enabled": True,
    }

    metadata = build_biashara_seo_metadata(
        business,
        website,
        "coastal-electronics",
        public_base_url="https://shop.example.test",
    )

    assert metadata["canonical_path"] == "/b/coastal-electronics"
    assert metadata["canonical_url"] == "https://shop.example.test/b/coastal-electronics"
    assert metadata["canonical_origin_configured"] is True
    assert metadata["robots"] == "index,follow"
    assert metadata["open_graph"]["title"] == "Coastal Electronics | Mombasa"
    assert metadata["open_graph"]["image"] == "https://cdn.example.test/hero.jpg"
    assert metadata["twitter"]["card"] == "summary_large_image"
    assert metadata["structured_data"]["@type"] == "Store"
    assert metadata["structured_data"]["address"]["addressCountry"] == "KE"
    assert metadata["structured_data"]["telephone"] == "+254700111222"
    assert metadata["domain_verification_status"] == "not_implemented"


def test_seo_does_not_infer_canonical_origin_from_untrusted_or_invalid_url():
    business = {"name": "Local Store", "phone": "+254700111222"}
    website = {
        "seo_title": "Local Store",
        "seo_description": "A small local store.",
        "contact_enabled": False,
    }

    for invalid_origin in (
        "http://shop.example.test",
        "https://user:password@shop.example.test",
        "https://localhost",
        "https://127.0.0.1",
        "https://shop.example.test:bad",
        "https://shop.example.test/path",
    ):
        metadata = build_biashara_seo_metadata(
            business,
            website,
            "local-store",
            public_base_url=invalid_origin,
        )
        assert metadata["canonical_url"] is None
        assert metadata["canonical_path"] == "/b/local-store"
        assert metadata["canonical_origin_configured"] is False
        assert "telephone" not in metadata["structured_data"]

    metadata = build_biashara_seo_metadata(business, website, "local-store", public_base_url="")
    assert metadata["canonical_url"] is None
    assert metadata["open_graph"]["url"] is None

