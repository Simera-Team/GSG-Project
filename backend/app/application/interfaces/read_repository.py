"""Read-only queries behind the profile, file-status and admin endpoints."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FileView:
    file_id: int
    profile_id: int
    user_id: int
    candidate_name: str
    original_name: str
    file_type: str
    status: str                       # uploaded | processing | done | needs_review | failed
    extraction_method: str | None
    ocr_confidence: float | None
    error_message: str | None
    uploaded_at: datetime | None
    finished_at: datetime | None
    attempts: int
    open_reviews: int


@dataclass
class AttemptView:
    attempt_number: int
    trigger: str
    outcome: str
    provider: str
    model_version: str
    error_message: str | None
    started_at: datetime
    finished_at: datetime


@dataclass
class ProfileView:
    profile_id: int
    user_id: int
    candidate_name: str
    candidate_email: str
    updated_at: datetime | None
    profile: dict[str, Any] | None    # the generated profile (final_json), Simera format
    open_reviews: int
    files: list[FileView] = field(default_factory=list)


@dataclass
class ChangeView:
    change_id: int
    field_name: str
    old_value: str | None
    new_value: str | None
    changed_by: str                   # user name, or "system"
    reason: str | None
    file_id: int | None
    changed_at: datetime | None


class IReadRepository(ABC):

    @abstractmethod
    def list_files(self, profile_id: int | None, status: str | None,
                   limit: int, offset: int) -> tuple[int, list[FileView]]: ...

    @abstractmethod
    def get_file(self, file_id: int) -> FileView | None: ...

    @abstractmethod
    def file_attempts(self, file_id: int) -> list[AttemptView]: ...

    @abstractmethod
    def profile_id_for_user(self, user_id: int) -> int | None: ...

    @abstractmethod
    def get_profile(self, profile_id: int) -> ProfileView | None: ...

    @abstractmethod
    def change_history(self, profile_id: int, limit: int, offset: int
                       ) -> tuple[int, list[ChangeView]]: ...

    @abstractmethod
    def dashboard(self) -> dict[str, Any]: ...
