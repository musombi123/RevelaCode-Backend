"""Static safety contract tests for the public verification harness."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_repo_file(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_load_scripts_require_exact_staging_host():
    guard = read_repo_file("tests/load/lib/staging-target.js")
    for production_host in (
        "revelacode.co.ke",
        "www.revelacode.co.ke",
        "revelacode-backend.onrender.com",
        "revelacode-api.onrender.com",
    ):
        assert production_host in guard
    assert "EXPECTED_STAGING_HOST" in guard
    assert "https://" in guard
    assert "actualHost !== expectedHost" in guard


def test_authenticated_profile_requires_synthetic_token_and_is_capped():
    profile = read_repo_file("tests/load/authenticated-read.js")
    assert 'if (!accessToken)' in profile
    assert "TARGET_VUS" in profile
    assert "targetVus > 1000" in profile
    assert 'http.get(baseUrl + apiPath' in profile


def test_health_profile_uses_shared_staging_host_guard():
    profile = read_repo_file("tests/load/health-smoke.js")
    assert 'requireStagingBaseUrl' in profile
    assert 'http.get(`${baseUrl}/health`' in profile


def test_programme_forbids_production_and_real_customer_data():
    staging = read_repo_file("docs/testing/STAGING_ENVIRONMENT.md")
    licence = read_repo_file("docs/testing/TESTER_LICENCE.md")
    capacity = read_repo_file("docs/testing/CAPACITY_TEST_PLAN.md")
    assert "revelacode_staging" in staging
    assert "no read/write access to production" in staging
    assert "real student" in staging
    assert "Target production" in licence
    assert "100,000 concurrent" in capacity
    assert "not a measured traffic profile or capacity result" in capacity
