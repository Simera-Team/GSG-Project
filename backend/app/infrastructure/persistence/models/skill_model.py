from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.db.base import Base


class SkillModel(Base):
    """Standard skill names (FR-029); managed by the administrator."""
    __tablename__ = "skill"

    skill_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)


class SkillAliasModel(Base):
    """Other spellings of a standard skill, stored lowercase (e.g. 'reactjs')."""
    __tablename__ = "skill_alias"

    alias_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("skill.skill_id", ondelete="CASCADE"), nullable=False)
    alias_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
