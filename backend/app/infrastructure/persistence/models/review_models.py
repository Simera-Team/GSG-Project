"""Human review queue (FR-041, FR-042, FR-043).

A field-level item has entity + field_name. A failed job has neither and
links to its source file only (FR-042), so field_name is nullable.
"""

from datetime import datetime

from sqlalchemy import REAL, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.db.base import Base


class ReviewItemModel(Base):
    __tablename__ = "review_item"
    __table_args__ = (
        CheckConstraint("resolution IN ('option', 'custom', 'rejected', 'dismissed')",
                        name="ck_review_item_resolution"),
    )

    review_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profile.profile_id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_file.file_id", ondelete="CASCADE"), nullable=False, index=True)
    entity: Mapped[str | None] = mapped_column(String(100))
    field_name: Mapped[str | None] = mapped_column(String(100))
    reasons: Mapped[list[str]] = mapped_column(ARRAY(String(50)), nullable=False, server_default="{}")
    message: Mapped[str | None] = mapped_column(Text)
    assigned_to_candidate: Mapped[bool | None] = mapped_column(Boolean, server_default="false")
    sent_to_candidate_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved: Mapped[bool | None] = mapped_column(Boolean, server_default="false", index=True)
    resolved_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("app_user.user_id"))
    resolved_value: Mapped[str | None] = mapped_column(Text)
    # FR-066: option = picked an option, custom = typed a value,
    # rejected = no value is correct, dismissed = failed job closed
    resolution: Mapped[str | None] = mapped_column(String(20))
    resolved_option_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("review_option.option_id", ondelete="SET NULL",
                            use_alter=True, name="review_item_resolved_option_id_fkey"))
    resolved_field_id: Mapped[int | None] = mapped_column(        # field record the decision created
        Integer, ForeignKey("extracted_field.field_id", ondelete="SET NULL"))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)


class ProfileChangeLogModel(Base):
    """History of every profile change (FR-037). Profile columns are logged by
    the trg_profile_log trigger; other changes are written by the backend."""
    __tablename__ = "profile_change_log"
    __table_args__ = (Index("ix_profile_change_log_profile", "profile_id", "changed_at"),)

    change_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profile.profile_id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("source_file.file_id", ondelete="SET NULL"))
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("app_user.user_id"))
    reason: Mapped[str | None] = mapped_column(String(100))
    changed_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())


class ReviewOptionModel(Base):
    """One candidate value of a review item, with its source and evidence."""
    __tablename__ = "review_option"
    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_option_confidence"),
    )

    option_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("review_item.review_id", ondelete="CASCADE"), nullable=False, index=True)
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_file.file_id", ondelete="CASCADE"), nullable=False, index=True)
    field_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("extracted_field.field_id", ondelete="SET NULL"))
    value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(REAL)
    evidence: Mapped[str | None] = mapped_column(Text)          # FR-043: shown next to the value
    page: Mapped[int | None] = mapped_column(Integer)
