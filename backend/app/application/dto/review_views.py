from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ReviewOptionView:
    option_id: int
    file_id: int
    file_name: str
    file_type: str
    field_id: int | None
    value: str | None
    confidence: float | None
    evidence: str | None          # FR-043: the reviewer sees each value next to its evidence
    page: int | None


@dataclass
class ReviewItemView:
    review_id: int
    profile_id: int
    candidate_name: str
    candidate_email: str
    file_id: int
    file_name: str
    file_type: str
    entity: str | None            # None for a failed job (FR-042)
    field_name: str | None
    reasons: list[str]
    message: str | None
    created_at: datetime | None
    assigned_to_candidate: bool
    sent_to_candidate_at: datetime | None
    resolved: bool
    resolution: str | None
    resolved_value: str | None
    resolved_option_id: int | None
    resolved_by: int | None
    resolved_by_name: str | None
    resolved_at: datetime | None
    options: list[ReviewOptionView] = field(default_factory=list)

    @property
    def is_failed_job(self) -> bool:
        return self.field_name is None


@dataclass
class StoredField:
    field_id: int
    file_id: int
    attempt_id: int | None
    entity: str
    entity_type: str
    field_name: str
    raw_value: Any
    value: Any
