
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums.user_role import UserRole


@dataclass
class User:
    user_id: int | None
    name: str
    email: str
    password_hash: str
    role: UserRole = UserRole.CANDIDATE
    created_at: datetime | None = None
