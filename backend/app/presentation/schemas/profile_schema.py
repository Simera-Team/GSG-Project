from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.application.dto.profile_document import ProfileDocument
from app.presentation.schemas.file_schema import FileOut


class ProfileOut(BaseModel):
    """The candidate's unified profile (FR-004), built from all their sources."""
    model_config = ConfigDict(from_attributes=True)

    profile_id: int
    candidate_name: str
    candidate_email: str
    updated_at: datetime | None
    open_reviews: int = Field(description="values still waiting for a reviewer; they are not "
                                          "in the profile until decided (FR-040)")
    profile: ProfileDocument | None = Field(
        description="null until the first file has been processed")
    files: list[FileOut] = Field(description="the sources this profile is built from")


class ChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    change_id: int
    field_name: str
    old_value: str | None
    new_value: str | None
    changed_by: str = Field(description="reviewer name, or 'system' for automatic merges")
    reason: str | None = Field(description="auto_merge, review_decision or manual_edit")
    file_id: int | None
    changed_at: datetime | None


class ChangeListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ChangeOut]


class StaffUserIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["reviewer", "administrator"]


class StaffUserOut(BaseModel):
    user_id: int
    name: str
    email: str
    role: str
