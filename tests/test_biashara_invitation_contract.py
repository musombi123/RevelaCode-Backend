from pathlib import Path


def test_ordinary_biashara_invitations_exclude_admin_and_director_roles():
    source = (Path(__file__).resolve().parents[1] / "backend/jumuiya/biashara/contracts.py").read_text(encoding="utf-8")
    assert 'INVITABLE_ROLES = ROLES - {"admin", "director"}' in source
    assert "if role not in INVITABLE_ROLES:" in source
    assert '@contracts_bp.post("/team/invitations")' in source
    assert '@contracts_bp.post("/team/invitations/accept")' in source


def test_elimu_platform_admin_school_invitation_is_tenant_scoped_and_protects_owner_roles():
    root = Path(__file__).resolve().parents[1]
    service = (root / "backend/jumuiya/elimu/staff/services.py").read_text(encoding="utf-8")
    routes = (root / "backend/jumuiya/platform_admin_routes.py").read_text(encoding="utf-8")
    assert "def invite_staff_for_platform_admin" in service
    assert "target_school_id" in service
    assert "ROLE_OWNER, ROLE_PRINCIPAL" in service
    assert 'inviter_name="RevelaCode Platform Administration"' in service
    assert '@platform_admin_bp.post("/schools/<school_id>/staff-invitations")' in routes
    assert "invite_staff_for_platform_admin(" in routes
