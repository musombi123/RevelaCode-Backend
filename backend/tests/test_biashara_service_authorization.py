import sys
import types

import pytest

_missing_module = object()
_original_db_module = sys.modules.get("backend.db", _missing_module)
_test_db_module = types.ModuleType("backend.db")
_test_db_module.get_db = lambda: None
sys.modules["backend.db"] = _test_db_module
try:
    from backend.jumuiya.biashara.analytics import service as analytics
    from backend.jumuiya.biashara.intelligence import service as intelligence
    from backend.jumuiya.biashara import services as biashara
finally:
    if _original_db_module is _missing_module:
        sys.modules.pop("backend.db", None)
    else:
        sys.modules["backend.db"] = _original_db_module

from backend.jumuiya.core.errors import APIError


def test_analytics_service_checks_permission_after_resolving_selected_business(monkeypatch):
    calls = []
    monkeypatch.setattr(analytics, "_require_business", lambda user_id: {
        "id": "business-analytics-1",
        "membership_role": "accountant",
    })
    monkeypatch.setattr(
        analytics,
        "require_permission",
        lambda user_id, permission, business_id=None: calls.append(
            (user_id, permission, business_id)
        ),
    )

    business = analytics._analytics_business("accountant-1")

    assert business["id"] == "business-analytics-1"
    assert calls == [("accountant-1", "analytics.view", "business-analytics-1")]


def test_analytics_service_propagates_denied_role(monkeypatch):
    monkeypatch.setattr(analytics, "_require_business", lambda user_id: {
        "id": "business-analytics-2",
    })

    def deny(user_id, permission, business_id=None):
        raise APIError("Denied", 403, "business_permission_denied")

    monkeypatch.setattr(analytics, "require_permission", deny)
    with pytest.raises(APIError) as raised:
        analytics._analytics_business("cashier-1")
    assert raised.value.code == "business_permission_denied"


def test_intelligence_business_context_checks_role_before_returning_tenant_data(monkeypatch):
    calls = []
    monkeypatch.setattr(biashara, "_require_business", lambda user_id: {
        "id": "business-intelligence-1",
        "name": "Test merchant",
    })
    monkeypatch.setattr(
        intelligence,
        "require_permission",
        lambda user_id, permission, business_id=None: calls.append(
            (user_id, permission, business_id)
        ),
    )

    context = intelligence.get_business_context("advisor-1")

    assert context["id"] == "business-intelligence-1"
    assert calls == [("advisor-1", "intelligence.view", "business-intelligence-1")]


def test_intelligence_discovery_can_return_empty_context_without_a_business(monkeypatch):
    def no_business(user_id):
        raise APIError("Create your business profile first.", 409, "business_required")

    monkeypatch.setattr(biashara, "_require_business", no_business)
    monkeypatch.setattr(
        intelligence,
        "require_permission",
        lambda *args, **kwargs: pytest.fail("No-business discovery should not request a tenant permission."),
    )

    assert intelligence.get_business_context("new-user") == {}
