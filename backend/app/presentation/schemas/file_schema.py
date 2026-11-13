from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FileStatus = Literal["uploaded", "processing", "done", "needs_review", "failed"]


class UploadCVResponse(BaseModel):
    file_id: int
    filename: str
    size: int
    status: str = Field(description="uploaded (queued for processing) or duplicate")
    duplicate: bool = Field(default=False,
                            description="True when you already uploaded this exact file: "
                                        "nothing new is created or processed (FR-012)")
    message: str


class FileOut(BaseModel):
    """One upload and its processing state (FR-014)."""
    model_config = ConfigDict(from_attributes=True)

    file_id: int
    original_name: str
    file_type: str
    status: FileStatus = Field(description="uploaded -> processing -> done / needs_review / failed")
    extraction_method: str | None = Field(description="text, ocr or mixed")
    ocr_confidence: float | None
    error_message: str | None
    uploaded_at: datetime | None
    finished_at: datetime | None
    attempts: int = Field(description="LLM attempts so far")
    open_reviews: int = Field(description="fields of this file waiting for a reviewer")


class FileListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[FileOut]


class AttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt_number: int
    trigger: Literal["first_run", "auto_retry", "admin_rerun"]
    outcome: Literal["valid", "invalid", "error"]
    provider: str
    model_version: str
    error_message: str | None
    started_at: datetime
    finished_at: datetime


class AdminFileOut(FileOut):
    profile_id: int
    user_id: int
    candidate_name: str


class AdminFileListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdminFileOut]


class AdminFileDetailOut(AdminFileOut):
    attempts_detail: list[AttemptOut] = Field(description="every processing try (FR-058)")


class RerunOut(BaseModel):
    file_id: int
    status: FileStatus
    message: str
