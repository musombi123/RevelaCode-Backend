from __future__ import annotations

from flask import Flask, g

from backend.jumuiya.core.errors import APIError, register_error_handlers
from backend.jumuiya.core.permissions import (
    is_platform_super_admin,
    require_authenticated,
    require_not_super_admin,
    require_roles,
)
from backend.jumuiya.integration import auth_bridge


def test_configured_owner_is_elevated_in_jumuiya_identity(monkeypatch):
    monkeypatch.setattr(
        auth_bridge,
        "is_configured_super_admin",
        lambda user_id, user: (
            str(user_id) == "owner-123"
            and str(user.get("email", "")).casefold() == "owner@example.com"
        ),
    )

    identity = auth_bridge.normalize_jumuiya_identity({
        "_id": "owner-123",
        "email": "owner@example.com",
        "role": "user",
        "roles": ["user"],
        "verified": True,
    })

    assert identity["role"] == "super_admin"
    assert "super_admin" in identity["roles"]
    assert identity["is_platform_super_admin"] is True


def test_unmatched_account_is_not_elevated(monkeypatch):
    monkeypatch.setattr(
        auth_bridge,
        "is_configured_super_admin",
        lambda user_id, user: False,
    )

    identity = auth_bridge.normalize_jumuiya_identity({
        "_id": "ordinary-123",
        "email": "member@example.com",
        "role": "user",
        "roles": ["user"],
        "verified": True,
    })

    assert identity["role"] == "user"
    assert identity["roles"] == ["user"]
    assert "is_platform_super_admin" not in identity


def test_super_admin_role_normalization_and_plan_exclusion():
    app = Flask(__name__)
    register_error_handlers(app)

    @app.before_request
    def attach_identity():
        g.jumuiya_user = {
            "id": "owner-123",
            "role": "SUPER_ADMIN",
            "roles": ["user"],
        }

    @app.get("/admin")
    @require_authenticated
    @require_roles("platform_admin", "super_admin")
    def admin_area():
        assert is_platform_super_admin()
        return {"success": True}, 200

    @app.get("/plans")
    @require_authenticated
    @require_not_super_admin
    @require_roles("platform_admin", "super_admin")
    def plans_area():
        return {"success": True}, 200

    client = app.test_client()
    assert client.get("/admin").status_code == 200
    denied = client.get("/plans")
    assert denied.status_code == 403
    assert denied.get_json()["code"] == "super_admin_plan_access_excluded"


def test_elimu_super_admin_gets_owner_equivalent_permissions(monkeypatch):
    from backend.jumuiya.elimu import permissions as elimu_permissions

    app = Flask(__name__)
    with app.test_request_context("/api/jumuiya/elimu/schools/school-123/students"):
        g.jumuiya_user = {
            "id": "owner-123",
            "role": "super_admin",
            "roles": ["super_admin"],
        }
        permission = next(iter(elimu_permissions.PERMISSIONS))
        member = elimu_permissions.authorize(
            "owner-123",
            permission,
            "school-123",
        )

    assert member["role"] == elimu_permissions.ROLE_OWNER
    assert member["school_id"] == "school-123"
    assert member["is_platform_admin"] is True
    assert set(member["permissions"]) == set(elimu_permissions.PERMISSIONS)
