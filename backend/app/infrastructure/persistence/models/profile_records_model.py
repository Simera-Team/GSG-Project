"""Profile child records (FR-004). Generated from field records, never edited
directly; `field_ids` lists the field records that produced each row (FR-063).

Dates are stored as text "YYYY" or "YYYY-MM" so no day is ever invented
(FR-028); the length shows the precision.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    REAL,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.db.base import Base

PARTIAL_DATE_REGEX = r"^\d{4}(-(0[1-9]|1[0-2]))?$"
LINK_TYPE = Enum("linkedin", "github", "portfolio", "website", "other", name="link_type")


def _date_column():
    return mapped_column(String(7))


def _date_check(table: str, column: str) -> CheckConstraint:
    return CheckConstraint(f"{column} ~ '{PARTIAL_DATE_REGEX}'", name=f"ck_{table}_{column}")


def _profile_fk():
    return mapped_column(Integer, ForeignKey("profile.profile_id", ondelete="CASCADE"),
                         nullable=False, index=True)


def _field_ids():
    return mapped_column(ARRAY(Integer), nullable=False, server_default="{}")


class ProfileSkillModel(Base):
    __tablename__ = "profile_skill"
    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 5", name="ck_profile_skill_level"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_profile_skill_confidence"),
    )

    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("profile.profile_id", ondelete="CASCADE"), primary_key=True)
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("skill.skill_id"), primary_key=True)
    level: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(REAL)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")  # FR-057
    source_file_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False,
                                                      server_default="{}")              # FR-057
    field_ids: Mapped[list[int]] = _field_ids()


class WorkExperienceModel(Base):
    __tablename__ = "work_experience"
    __table_args__ = (
        _date_check("work_experience", "start_date"),
        _date_check("work_experience", "end_date"),
        CheckConstraint("employment_status IN ('current', 'ended', 'unknown')",
                        name="ck_work_experience_status"),
    )

    exp_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = _profile_fk()
    company: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[str | None] = _date_column()
    end_date: Mapped[str | None] = _date_column()
    # current = ongoing job; unknown = end date missing in the source (FR-028)
    employment_status: Mapped[str] = mapped_column(String(10), nullable=False,
                                                   server_default="unknown")
    description: Mapped[str | None] = mapped_column(Text)
    field_ids: Mapped[list[int]] = _field_ids()


class EducationModel(Base):
    __tablename__ = "education"
    __table_args__ = (_date_check("education", "start_date"), _date_check("education", "end_date"))

    edu_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = _profile_fk()
    institution: Mapped[str | None] = mapped_column(String(255))
    degree: Mapped[str | None] = mapped_column(String(255))
    field: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[str | None] = _date_column()
    end_date: Mapped[str | None] = _date_column()
    field_ids: Mapped[list[int]] = _field_ids()


class CertificationModel(Base):
    __tablename__ = "certification"
    __table_args__ = (_date_check("certification", "issue_date"),)

    cert_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = _profile_fk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(255))
    issue_date: Mapped[str | None] = _date_column()
    url: Mapped[str | None] = mapped_column(Text)
    field_ids: Mapped[list[int]] = _field_ids()


class ProjectModel(Base):
    __tablename__ = "project"

    project_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = _profile_fk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    tech_stack: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    field_ids: Mapped[list[int]] = _field_ids()


class LanguageModel(Base):
    __tablename__ = "language"
    __table_args__ = (
        UniqueConstraint("profile_id", "name", name="uq_language_profile_name"),
        CheckConstraint("proficiency IN ('native', 'fluent', 'intermediate', 'basic')",
                        name="ck_language_proficiency"),
    )

    language_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = _profile_fk()
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    proficiency: Mapped[str | None] = mapped_column(String(30))
    field_ids: Mapped[list[int]] = _field_ids()


class ProfileLinkModel(Base):
    __tablename__ = "profile_link"
    __table_args__ = (UniqueConstraint("profile_id", "url", name="uq_profile_link_url"),)

    link_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = _profile_fk()
    type: Mapped[str] = mapped_column(LINK_TYPE, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    field_ids: Mapped[list[int]] = _field_ids()
