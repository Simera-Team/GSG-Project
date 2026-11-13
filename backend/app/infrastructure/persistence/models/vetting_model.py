from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.db.base import Base


class VettingRecordModel(Base):
    """One vetted skill level for a candidate (FR-056).

    The table follows FR-056 (candidate, skill, level 1-5, uploader, time).
    The parser that fills it waits for the vetting JSON structure (flag 7).
    """
    __tablename__ = "vetting_record"
    __table_args__ = (CheckConstraint("level BETWEEN 1 AND 5", name="ck_vetting_level"),)

    vetting_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profile.profile_id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill.skill_id"), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_file.file_id", ondelete="CASCADE"), nullable=False)
    uploaded_by: Mapped[int] = mapped_column(Integer, ForeignKey("app_user.user_id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now())
