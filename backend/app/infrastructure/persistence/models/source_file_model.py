
from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    Enum,
    JSON,
    CHAR,
    func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.db.base import Base


class SourceFileModel(Base):
    __tablename__ = "source_file"

    file_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("profile.profile_id"),
        nullable=False,
        index=True
    )

    file_type: Mapped[str] = mapped_column(
        Enum(
            "pdf",
            "docx",
            "md",
            "json",
            name="file_type"
        ),
        nullable=False
    )

    original_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    file_hash: Mapped[str] = mapped_column(
        CHAR(64),
        nullable=False
    )

    storage_path: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        Enum(
            "uploaded",
            "processing",
            "done",
            "failed",
            "needs_review",
            name="file_status"
        ),
        nullable=False,
        server_default="uploaded"
    )

    extraction_method: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    ocr_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    llm_response: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True
    )

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    num_of_retries: Mapped[int] = mapped_column(
        "Num_Of_Retries",
        Integer,
        nullable=False,
        server_default="0"
    )

    profile: Mapped["ProfileModel"] = relationship(
        "ProfileModel",
        back_populates="source_files"
    )
