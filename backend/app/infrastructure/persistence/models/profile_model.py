
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.db.base import Base


class ProfileModel(Base):
    __tablename__ = "profile"

    profile_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("app_user.user_id"),
        unique=True,
        nullable=False
    )

    first_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    last_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    phone: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    country_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("country.country_id"),
        nullable=True
    )

    title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    final_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True
    )

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
        onupdate=func.now()
    )

    country: Mapped["CountryModel | None"] = relationship(
        "CountryModel",
        back_populates="profiles"
    )

    user: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="profile"
    )
    source_files: Mapped[list["SourceFileModel"]] = relationship(
    "SourceFileModel",
    back_populates="profile"
)
