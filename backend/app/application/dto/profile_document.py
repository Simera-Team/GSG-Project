"""Simera profile format (FR-004, FR-038, FR-063).

The requirements do not define "Simera's profile format" beyond the field
list in FR-004, so this model is that definition. A built profile must pass
it before it may be saved; lengths match the database columns.

Every record carries `field_ids`: the field records that produced it
(FR-063), so each profile value can be traced back to its source.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, model_validator

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


class _Matched(_Strict):
    """Fields every entity merged across sources carries (M-01, FR-063).

    ``entity_id`` identifies the entity itself rather than its position in the
    list: it is taken from the earliest source that mentions it, so a newer
    source arriving never renumbers what is already there. ``rule`` is set only
    where sources were actually brought together, so a profile can explain why
    two rows became one (FR-035, FR-051).
    """

    entity_id: str | None = Field(default=None, max_length=120,
                                  description="stable id of the matched entity")
    rule: str | None = Field(default=None, max_length=20,
                             description="M-01 when sources were merged into this record")


class _Contact(_Strict):
    """One way to reach the candidate: an address or a number (M-03).

    Each one carries its own ``field_ids``, like every other repeated record in
    this document, so a contact traces back to the source text it was read
    from rather than sharing a pile of ids with the others (FR-063).

    The list is ordered: the first entry is the one the merge took from the
    newest source, and it is the one flagged ``is_primary``. There is no
    separate "primary" value stored anywhere, so the two can never disagree.
    """

    is_primary: bool = False
    field_ids: list[int] = Field(default_factory=list)


class EmailRecord(_Contact):
    value: EmailStr


class PhoneRecord(_Contact):
    value: str = Field(max_length=50)


#: Keys PersonalInfoRecord writes but never reads as input: the derived
#: primaries, and the pre-M-03 single-value names.
_DERIVED_CONTACT_KEYS = ("primary_email", "primary_phone", "email", "phone")
#: A pre-M-03 single value, and the list it now lives in.
_LEGACY_CONTACT_LISTS = {"email": "emails", "phone": "phones"}


class PersonalInfoRecord(_Strict):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    # A person has more than one of each, so a contact is a list, never a
    # single value two sources can disagree about (M-03). Every address and
    # number the sources state is here, de-duplicated on the normalised value
    # and ordered with the newest source's first.
    emails: list[EmailRecord] = Field(default_factory=list)
    phones: list[PhoneRecord] = Field(default_factory=list)
    city: str | None = Field(default=None, max_length=100)
    country: CountryValue | None = None
    title: str | None = Field(default=None, max_length=255)
    summary: str | None = None
    field_ids: dict[str, int] = Field(default_factory=dict,
                                      description="field name -> field record id")

    @model_validator(mode="before")
    @classmethod
    def _accept_stored_shape(cls, data: Any) -> Any:
        """Read back what this model writes, and what it used to write.

        ``final_json`` is a dump of this model, so it carries the derived
        values below. They are output only: drop them on the way in, or
        ``extra="forbid"`` rejects every stored profile.

        Profiles saved before M-03 hold one ``email`` / ``phone`` string and no
        lists; that string was the primary, so it becomes the one-entry list.
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for derived in _DERIVED_CONTACT_KEYS:
            value = data.pop(derived, None)
            list_key = _LEGACY_CONTACT_LISTS.get(derived)
            if list_key and value and not data.get(list_key):
                data[list_key] = [{"value": value, "is_primary": True}]
        return data

    @computed_field  # type: ignore[prop-decorator]
    @property
    def primary_email(self) -> str | None:
        """The address the merge chose, derived rather than stored."""
        return self.emails[0].value if self.emails else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def primary_phone(self) -> str | None:
        return self.phones[0].value if self.phones else None

    # The single-value names the profile had before M-03. API clients (the
    # web app among them) read ``personal_info.email`` / ``.phone``; keeping
    # them as the primary means the list change does not break any reader.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def email(self) -> str | None:
        """Same as ``primary_email``; kept for clients of the pre-M-03 format."""
        return self.primary_email

    @computed_field  # type: ignore[prop-decorator]
    @property
    def phone(self) -> str | None:
        """Same as ``primary_phone``; kept for clients of the pre-M-03 format."""
        return self.primary_phone


class ExperienceRecord(_Matched):
    company: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    location: str | None = None
    start_date: PartialDateValue | None = None
    end_date: PartialDateValue | None = None
    # current = ongoing job; unknown = end date missing in the source (FR-028)
    employment_status: Literal["current", "ended", "unknown"]
    description: str | None = None
    field_ids: list[int]


class EducationRecord(_Matched):
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


class CertificationRecord(_Matched):
    name: str = Field(max_length=255)
    issuer: str | None = Field(default=None, max_length=255)
    issue_date: PartialDateValue | None = None
    url: str | None = None
    field_ids: list[int]


class ProjectRecord(_Matched):
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
