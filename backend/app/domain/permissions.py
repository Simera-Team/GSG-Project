"""Permission matrix: which role may do what (requirements.md §2.10, FR-003).

This is the single source of truth for authorization. Endpoints ask for a
Permission, never for a role, so changing who can do what only touches
this file.
"""

from enum import Enum

from app.domain.enums.user_role import UserRole


class Permission(str, Enum):
    # Candidate: own data only (ownership is checked separately)
    PROFILE_VIEW_OWN = "profile:view_own"
    SOURCE_UPLOAD = "source:upload"
    SOURCE_VIEW_OWN = "source:view_own"
    JOB_VIEW_OWN = "job:view_own"

    # Reviewer
    REVIEW_QUEUE = "review:queue"
    REVIEW_RESOLVE = "review:resolve"

    # Administrator only
    VETTING_UPLOAD = "vetting:upload"
    JOB_RERUN = "job:rerun"
    DASHBOARD_VIEW = "dashboard:view"
    USER_MANAGE = "user:manage"
    SKILL_MANAGE = "skill:manage"
    SETTINGS_MANAGE = "settings:manage"
    # Lets a user open any candidate's sources, jobs and profile
    CANDIDATE_DATA_ACCESS_ANY = "candidate_data:access_any"


_CANDIDATE: frozenset[Permission] = frozenset({
    Permission.PROFILE_VIEW_OWN,
    Permission.SOURCE_UPLOAD,
    Permission.SOURCE_VIEW_OWN,
    Permission.JOB_VIEW_OWN,
})

_REVIEWER: frozenset[Permission] = frozenset({
    Permission.REVIEW_QUEUE,
    Permission.REVIEW_RESOLVE,
})

# §2.10: "Administrator: all reviewer abilities, plus ..."
_ADMINISTRATOR: frozenset[Permission] = _REVIEWER | frozenset({
    Permission.VETTING_UPLOAD,
    Permission.JOB_RERUN,
    Permission.DASHBOARD_VIEW,
    Permission.USER_MANAGE,
    Permission.SKILL_MANAGE,
    Permission.SETTINGS_MANAGE,
    Permission.CANDIDATE_DATA_ACCESS_ANY,
})

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.CANDIDATE: _CANDIDATE,
    UserRole.REVIEWER: _REVIEWER,
    UserRole.ADMINISTRATOR: _ADMINISTRATOR,
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
