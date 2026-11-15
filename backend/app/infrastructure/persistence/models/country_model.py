
from sqlalchemy import Integer, String, CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.db.base import Base


class CountryModel(Base):
    __tablename__ = "country"

    country_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    country_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True
    )

    country_code: Mapped[str] = mapped_column(
        CHAR(2),
        nullable=False,
        unique=True
    )

    profiles: Mapped[list["ProfileModel"]] = relationship(
        "ProfileModel",
        back_populates="country"
    )
