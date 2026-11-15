from enum import Enum


class UserRole(str, Enum):
    """User roles as defined in requirements.md §2.10."""

    CANDIDATE = "candidate"
    REVIEWER = "reviewer"
    ADMINISTRATOR = "administrator"
