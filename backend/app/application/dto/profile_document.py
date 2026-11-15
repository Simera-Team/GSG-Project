"""Simera profile format (FR-004, FR-038, FR-063).

The requirements do not define "Simera's profile format" beyond the field
list in FR-004, so this model is that definition. A built profile must pass
it before it may be saved; lengths match the database columns.

Every record carries `field_ids`: the field records that produced it
(FR-063), so each profile value can be traced back to its source.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.application.dto.cv_extraction import LinkType, ProficiencyLevel

RULE_VERSION = "1.0"  # bump when normalisation / merge rules change (NFR-023)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PartialDateValue(_Strict):
    """A date with the precision the source gave - never an invented day (FR-028)."""
    value: str = Field(pattern=r"^\d{4}(-(0[1-9]|1[0-2]))?$", description="YYYY or YYYY-MM")
    precision: Literal["year", "month"]


class CountryValue(_Strict):
    name: str = Field(max_length=100)
    code: str = Field(pattern=r"^[A-Z]{2}$")


class PersonalInfoRecord(_Strict):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    city: str | None = Field(default=None, max_length=100)
    country: CountryValue | None = None
    title: str | None = Field(default=None, max_length=255)
    summary: str | None = None
    field_ids: dict[str, int] = Field(default_factory=dict, description="field name -> field record id")


class ExperienceRecord(_Strict):
    company: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    location: str | None = None
    start_date: PartialDateValue | None = None
    end_date: PartialDateValue | None = None
    # current = ongoing job; unknown = end date missing in the source (FR-028)
    employment_status: Literal["current", "ended", "unknown"]
    description: str | None = None
    field_ids: list[int]


class EducationRecord(_Strict):
    institution: str | None = Field(default=None, max_length=255)
    degree: str | None = Field(default=None, max_length=255)
    field: str | None = Field(default=None, max_length=255)
    start_date: PartialDateValue | None = None
    end_date: PartialDateValue | None = None
    field_ids: list[int]


class SkillRecord(_Strict):
    name: str = Field(max_length=100, description="Standard skill name from the skill table")
    level: int | None = Field(default=None, ge=1, le=5)
    verified: bool = False            # True only for vetted skills (FR-057)
    sources: list[str]
    field_ids: list[int]


class CertificationRecord(_Strict):
    name: str = Field(max_length=255)
    issuer: str | None = Field(default=None, max_length=255)
    issue_date: PartialDateValue | None = None
    url: str | None = None
    field_ids: list[int]


class ProjectRecord(_Strict):
    name: str = Field(max_length=255)
    description: str | None = None
    url: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    field_ids: list[int]


class LanguageRecord(_Strict):
    name: str = Field(max_length=50)
    proficiency: ProficiencyLevel | None = None
    field_ids: list[int]


class LinkRecord(_Strict):
    type: LinkType
    url: str = Field(min_length=4)
    field_ids: list[int]


class ProfileDocument(_Strict):
    rule_version: str = RULE_VERSION
    personal_info: PersonalInfoRecord
    experience: list[ExperienceRecord]
    education: list[EducationRecord]
    skills: list[SkillRecord]
    certifications: list[CertificationRecord]
    projects: list[ProjectRecord]
    languages: list[LanguageRecord]
    links: list[LinkRecord]
