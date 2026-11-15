"""Audit trail of processing: attempts and field records."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    REAL,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.db.base import Base

ATTEMPT_TRIGGER = Enum("first_run", "auto_retry", "admin_rerun", name="attempt_trigger")
ATTEMPT_OUTCOME = Enum("valid", "invalid", "error", name="attempt_outcome")


class ProcessingAttemptModel(Base):
    """One processing try of a source file (FR-058). Insert-only (NFR-024)."""
    __tablename__ = "processing_attempt"
    __table_args__ = (
        UniqueConstraint("file_id", "attempt_number", name="uq_attempt_file_number"),
        CheckConstraint("confidence_threshold BETWEEN 0 AND 1", name="ck_attempt_threshold"),
    )

    attempt_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_file.file_id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger: Mapped[str] = mapped_column(ATTEMPT_TRIGGER, nullable=False)
    outcome: Mapped[str] = mapped_column(ATTEMPT_OUTCOME, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    llm_response: Mapped[str | None] = mapped_column(Text)
    validation_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    confidence_threshold: Mapped[float | None] = mapped_column(REAL)   # FR-067
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExtractedFieldModel(Base):
    """One extracted value with entity, evidence and the rule that chose it
    (FR-035, FR-060, FR-065). Insert-only: a re-run adds new rows."""
    __tablename__ = "extracted_field"
    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_field_confidence"),
        CheckConstraint("page IS NULL OR page >= 1", name="ck_field_page"),
        CheckConstraint("review_status IN ('accepted', 'needs_review')", name="ck_field_review_status"),
        Index("ix_extracted_field_file_field", "file_id", "field_name"),
    )

    field_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_file.file_id", ondelete="CASCADE"), nullable=False)
    attempt_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("processing_attempt.attempt_id", ondelete="CASCADE"), index=True)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)        # work_experience[2]
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)    # work_experience
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)    # end_date
    raw_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)   # as the LLM returned it
    value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)       # after normalisation
    confidence: Mapped[float | None] = mapped_column(REAL)
    evidence: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    evidence_status: Mapped[str] = mapped_column(String(20), nullable=False)
    rule: Mapped[str | None] = mapped_column(String(100))
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="accepted")
    review_reasons: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), nullable=False, server_default="{}")
    is_winner: Mapped[bool | None] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
