from __future__ import annotations

from backend.jumuiya.elimu.permissions import effective_permissions
from backend.jumuiya.elimu.staff.models import normalize_permissions


STAFF_MANAGEMENT_PERMISSIONS = {
    "staff.view",
    "staff.invite",
    "staff.update",
    "staff.remove",
    "staff.roles",
}


def test_legacy_staff_manage_grant_expands_to_canonical_owner_permissions():
    assert effective_permissions("owner", ["staff.manage"]) == STAFF_MANAGEMENT_PERMISSIONS


def test_legacy_staff_manage_grant_is_preserved_by_membership_permission_normalizer():
    assert set(normalize_permissions(["staff.manage"])) == STAFF_MANAGEMENT_PERMISSIONS


def test_legacy_staff_manage_alias_cannot_expand_teacher_permissions():
    assert effective_permissions("teacher", ["staff.manage"]) == {"staff.view"}


def test_legacy_staff_manage_alias_cannot_expand_finance_only_bursar_permissions():
    assert effective_permissions("bursar", ["staff.manage"]) == set()
