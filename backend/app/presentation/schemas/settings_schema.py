"""Shapes for the administrator's settings endpoints (FR-046, FR-067)."""

from datetime import datetime

from pydantic import BaseModel, Field


class ConfidenceThresholdIn(BaseModel):
    value: float = Field(
        ge=0, le=1,
        description="Fields the extraction is less sure of than this go to review",
        examples=[0.65],
    )


class SettingOut(BaseModel):
    key: str
    value: str
    description: str | None = None
    updated_by: int | None = Field(
        default=None, description="Administrator who last changed it; null if never")
    updated_at: datetime | None = None


class SettingsListOut(BaseModel):
    settings: list[SettingOut]
