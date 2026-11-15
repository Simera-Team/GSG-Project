"""Object-level authorization (NFR-016, FR-055).

Role checks answer "may this kind of user call this endpoint?".
Ownership checks answer "may this user see *this* record?". Every endpoint
that loads a source, job or profile by id must call ensure_can_access on
the loaded record before returning it.
"""

from app.core.exceptions import PermissionDeniedError
from app.domain.entities.user import User
from app.domain.permissions import Permission, has_permission


def can_access(user: User, owner_user_id: int) -> bool:
    """True if the user owns the record or may access any candidate's data."""
    if user.user_id is not None and user.user_id == owner_user_id:
        return True

    return has_permission(user.role, Permission.CANDIDATE_DATA_ACCESS_ANY)


def ensure_can_access(user: User, owner_user_id: int) -> None:
    """Raise PermissionDeniedError unless the user may access the record.

    Usage, once a record is loaded:
        profile = profile_repo.get_by_id(profile_id)
        ensure_can_access(current_user, profile.user_id)
    """
    if not can_access(user, owner_user_id):
        raise PermissionDeniedError()
