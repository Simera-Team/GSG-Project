"""Strict output schema for LLM field extraction.

Requirements covered:
- FR-021 strict schema sent to the LLM
- FR-025 only allowed field names (no protected traits exist in the schema)
- FR-026 null when the source does not contain a value
- FR-027 a confidence score on every value
- FR-060 values grouped by entity (one object per job, degree, ...)
- FR-065 evidence (exact snippet + page) with every value

Every value is an "extracted field": value + confidence + evidence + page.
Dates are kept exactly as written; they are converted to one format later
in code (FR-028), never by the LLM.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProficiencyLevel = Literal["native", "fluent", "intermediate", "basic"]
LinkType = Literal["linkedin", "github", "portfolio", "website", "other"]


class _Strict(BaseModel):
    # Unknown keys are an error, so only allowed field names get through.
    model_config = ConfigDict(extra="forbid")


class _EvidenceMixin(_Strict):
    confidence: float = Field(ge=0, le=1, description="How sure the extraction is, 0 to 1")
    evidence: str | None = Field(
        description="Exact quote copied from the CV text that contains this value; "
                    "null only when value is null"
    )
    page: int | None = Field(
        ge=1,
        description="Page number from the [Page N] marker above the evidence; "
                    "null when the text has no page markers",
    )


class TextField(_EvidenceMixin):
    value: str | None = Field(description="null when the CV does not contain it")


class FlagField(_EvidenceMixin):
    value: bool


class ProficiencyField(_EvidenceMixin):
    value: ProficiencyLevel | None


class PersonalInfo(_Strict):
    first_name: TextField
    last_name: TextField
    email: TextField
    phone: TextField
    city: TextField
    country: TextField
    title: TextField = Field(description="Professional headline or target role")
    summary: TextField


class WorkExperience(_Strict):
    company: TextField
    title: TextField
    location: TextField
    start_date: TextField = Field(description="As written in the CV")
    end_date: TextField = Field(description="As written; null if ongoing or missing")
    is_current: FlagField = Field(description="true only if the CV says the role is ongoing")
    description: TextField


class Education(_Strict):
    institution: TextField
    degree: TextField
    field: TextField
    start_date: TextField
    end_date: TextField


class Skill(_Strict):
    name: TextField


class Certification(_Strict):
    name: TextField
    issuer: TextField
    issue_date: TextField
    url: TextField


class Project(_Strict):
    name: TextField
    description: TextField
    url: TextField
    tech_stack: list[TextField]


class Language(_Strict):
    name: TextField
    proficiency: ProficiencyField


class Link(_Strict):
    type: LinkType
    url: TextField


class CVExtraction(_Strict):
    personal_info: PersonalInfo
    work_experience: list[WorkExperience]
    education: list[Education]
    skills: list[Skill]
    certifications: list[Certification]
    projects: list[Project]
    languages: list[Language]
    links: list[Link]
