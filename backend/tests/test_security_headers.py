"""Tests for the platform's baseline HTTP security headers."""
from backend.security.headers import apply_security_headers


class FakeResponse:
    def __init__(self):
        self.headers = {}


def test_security_headers_are_added_without_overwriting_route_policy():
    response = FakeResponse()
    response.headers["X-Frame-Options"] = "DENY"

    result = apply_security_headers(response, is_secure=False)

    assert result.headers["X-Content-Type-Options"] == "nosniff"
    assert result.headers["X-Frame-Options"] == "DENY"
    assert result.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert result.headers["Permissions-Policy"] == (
        "camera=(self), microphone=(self), geolocation=(self)"
    )
    assert "Strict-Transport-Security" not in result.headers


def test_hsts_is_added_only_for_secure_requests():
    response = apply_security_headers(FakeResponse(), is_secure=True)
    assert response.headers["Strict-Transport-Security"] == "max-age=15552000"
