from pathlib import Path


def test_ordinary_biashara_invitations_exclude_admin_and_director_roles():
    source = (Path(__file__).resolve().parents[1] / "backend/jumuiya/biashara/contracts.py").read_text(encoding="utf-8")
    assert 'INVITABLE_ROLES = ROLES - {"admin", "director"}' in source
    assert "if role not in INVITABLE_ROLES:" in source
    assert '@contracts_bp.post("/team/invitations")' in source
    assert '@contracts_bp.post("/team/invitations/accept")' in source
