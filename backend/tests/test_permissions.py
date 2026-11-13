"""The permission matrix itself (requirements.md §2.10, FR-003)."""

import pytest

from app.domain.enums.user_role import UserRole
from app.domain.permissions import ROLE_PERMISSIONS, Permission, has_permission


def test_every_role_has_an_entry():
    assert set(ROLE_PERMISSIONS) == set(UserRole)


def test_administrator_has_all_reviewer_abilities():
    assert ROLE_PERMISSIONS[UserRole.REVIEWER] <= ROLE_PERMISSIONS[UserRole.ADMINISTRATOR]


@pytest.mark.parametrize("permission", [
    Permission.VETTING_UPLOAD,
    Permission.JOB_RERUN,
    Permission.DASHBOARD_VIEW,
    Permission.USER_MANAGE,
    Permission.SKILL_MANAGE,
    Permission.SETTINGS_MANAGE,
    Permission.CANDIDATE_DATA_ACCESS_ANY,
])
def test_admin_only_permissions(permission):
    assert has_permission(UserRole.ADMINISTRATOR, permission)
    assert not has_permission(UserRole.REVIEWER, permission)
    assert not has_permission(UserRole.CANDIDATE, permission)


@pytest.mark.parametrize("permission", [Permission.REVIEW_QUEUE, Permission.REVIEW_RESOLVE])
def test_candidate_cannot_use_review_queue(permission):
    assert not has_permission(UserRole.CANDIDATE, permission)


def test_reviewer_cannot_access_other_candidates_data():
    assert not has_permission(UserRole.REVIEWER, Permission.CANDIDATE_DATA_ACCESS_ANY)
