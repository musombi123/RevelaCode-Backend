"""Small, dependency-free HTTP security-header policy for the Flask API."""
from __future__ import annotations


def apply_security_headers(response, *, is_secure: bool):
    """Add safe baseline headers without imposing a restrictive CSP.

    HSTS is emitted only for HTTPS requests. It intentionally omits
    includeSubDomains until every RevelaCode subdomain is confirmed HTTPS-ready.
    """
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(self), microphone=(self), geolocation=(self)",
    )
    if is_secure:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=15552000",
        )
    return response
