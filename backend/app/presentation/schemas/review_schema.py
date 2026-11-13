from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    option_id: int
    file_id: int
    file_name: str
    file_type: str
    field_id: int | None
    value: str | None
    confidence: float | None
    evidence: str | None = Field(description="Snippet from the source text (FR-043)")
    page: int | None


class ReviewItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: int
    profile_id: int
    candidate_name: str
    candidate_email: str
    file_id: int
    file_name: str
    file_type: str
    entity: str | None = Field(description="e.g. work_experience[2]; null for a failed job")
    field_name: str | None = Field(description="null for a failed job (FR-042)")
    reasons: list[str] = Field(description="e.g. low_confidence, unknown_skill, source_conflict")
    message: str | None
    is_failed_job: bool
    created_at: datetime | None
    assigned_to_candidate: bool
    sent_to_candidate_at: datetime | None
    resolved: bool
    resolution: Literal["option", "custom", "rejected", "dismissed"] | None
    resolved_value: str | None
    resolved_option_id: int | None
    resolved_by: int | None
    resolved_by_name: str | None
    resolved_at: datetime | None
    options: list[ReviewOptionOut]


class ReviewListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ReviewItemOut]


class ResolveRequest(BaseModel):
    action: Literal["option", "custom", "reject", "dismiss"] = Field(
        description="option: pick one of the item's values; custom: type a corrected value; "
                    "reject: no value is correct, leave the field empty; "
                    "dismiss: close a failed-job item")
    option_id: int | None = Field(default=None, description="Required for 'option'")
    value: str | None = Field(default=None, max_length=5000,
                              description="Required for 'custom'")
    map_to_skill: str | None = Field(
        default=None, max_length=100,
        description="Skill items only: map the value to this existing standard skill and save "
                    "it as an alias (FR-062). Leave empty to approve the value as a new skill.")

    model_config = ConfigDict(json_schema_extra={"examples": [
        {"action": "option", "option_id": 12},
        {"action": "custom", "value": "March 2021"},
        {"action": "option", "option_id": 7, "map_to_skill": "PostgreSQL"},
        {"action": "reject"},
    ]})


class CandidateRequestOut(BaseModel):
    item: ReviewItemOut
    candidate_email: str
    suggested_message: str = Field(description="Text the reviewer can send to the candidate")
