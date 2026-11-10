import os
from datetime import datetime, timezone

# Settings are read at import time; give tests their own values so they
# never depend on a developer's .env or touch a real database.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-chars")

import pytest  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.domain.entities.user import User  # noqa: E402
from app.domain.enums.user_role import UserRole  # noqa: E402
from app.domain.interfaces.user_repository import IUserRepository  # noqa: E402


class FakeUserRepository(IUserRepository):
    """In-memory replacement for the SQLAlchemy repository."""

    def __init__(self) -> None:
        self.users: dict[int, User] = {}

    def create(self, user: User) -> User:
        user.user_id = len(self.users) + 1
        user.created_at = user.created_at or datetime.now(timezone.utc)
        self.users[user.user_id] = user
        return user

    def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.users.values() if u.email == email), None)

    def get_by_id(self, user_id: int) -> User | None:
        return self.users.get(user_id)


@pytest.fixture
def user_repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def make_user(user_repo: FakeUserRepository):
    def _make(role: UserRole, email: str | None = None) -> User:
        return user_repo.create(User(
            user_id=None,
            name=role.value.title(),
            email=email or f"{role.value}-{len(user_repo.users)}@example.com",
            password_hash="not-used",
            role=role,
        ))
    return _make


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.user_id)}"}
