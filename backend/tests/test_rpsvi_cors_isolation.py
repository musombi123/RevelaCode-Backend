"""RPSVI staging CORS isolation tests."""
from backend.security.cors_origins import resolve_frontend_origins


DEFAULTS = {
    "https://revelacode.co.ke",
    "https://www.revelacode.co.ke",
    "http://localhost:5173",
}


def test_staging_uses_only_explicit_staging_origins():
    assert resolve_frontend_origins(
        DEFAULTS,
        "https://revelacode-rpsvi-frontend.onrender.com",
        "staging",
    ) == {"https://revelacode-rpsvi-frontend.onrender.com"}


def test_empty_staging_configuration_does_not_inherit_production_or_local_origins():
    assert resolve_frontend_origins(DEFAULTS, "", "staging") == set()


def test_staging_rejects_wildcard_and_non_http_origins():
    assert resolve_frontend_origins(
        DEFAULTS,
        "*,javascript:alert(1),https://revelacode-rpsvi-frontend.onrender.com/",
        "staging",
    ) == {"https://revelacode-rpsvi-frontend.onrender.com"}


def test_production_keeps_defaults_and_adds_configured_origins():
    assert resolve_frontend_origins(
        DEFAULTS,
        "https://extra-trusted.example.test,https://revelacode.co.ke",
        "production",
    ) == DEFAULTS | {"https://extra-trusted.example.test"}


def test_non_staging_environment_keeps_existing_default_behaviour():
    assert resolve_frontend_origins(
        DEFAULTS,
        "http://localhost:4173",
        "development",
    ) == DEFAULTS | {"http://localhost:4173"}
