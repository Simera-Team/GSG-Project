from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Profile:
    profile_id: int | None
    user_id: int
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    city: str | None = None
    country_id: int | None = None
    title: str | None = None
    summary: str | None = None
    final_json: dict[str, Any] | None = None
    updated_at: datetime | None = None
