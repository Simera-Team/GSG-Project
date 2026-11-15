from abc import ABC, abstractmethod
from typing import Any

from app.application.dto.review_views import ReviewItemView, StoredField


class IReviewRepository(ABC):
    """Review queue storage. Nothing here commits; the service commits once."""

    @abstractmethod
    def list_items(self, status: str, reason: str | None, profile_id: int | None,
                   limit: int, offset: int) -> tuple[int, list[ReviewItemView]]: ...

    @abstractmethod
    def get_item(self, review_id: int, lock: bool = False) -> ReviewItemView | None:
        """lock=True blocks a second reviewer resolving the same item at once."""

    @abstractmethod
    def get_field(self, field_id: int) -> StoredField | None: ...

    @abstractmethod
    def latest_valid_attempt_id(self, file_id: int) -> int | None: ...

    @abstractmethod
    def add_decision_field(self, file_id: int, attempt_id: int, entity: str, entity_type: str,
                           field_name: str, raw_value: Any, value: Any,
                           evidence: str | None, page: int | None) -> int:
        """Insert the field record that carries a reviewer's decision; returns its id."""

    @abstractmethod
    def mark_resolved(self, review_id: int, resolution: str, option_id: int | None,
                      value_text: str | None, field_id: int | None, user_id: int) -> None: ...

    @abstractmethod
    def mark_sent_to_candidate(self, review_id: int) -> None: ...

    @abstractmethod
    def ensure_skill(self, name: str) -> str:
        """Return the standard name, creating the skill if it is new (FR-062)."""

    @abstractmethod
    def add_skill_alias(self, alias: str, canonical_name: str) -> None: ...

    @abstractmethod
    def log_change(self, profile_id: int, file_id: int | None, field_name: str,
                   old_value: str | None, new_value: str | None, user_id: int,
                   reason: str) -> None: ...
