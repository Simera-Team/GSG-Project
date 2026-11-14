"""The structured answer the LLM is asked for, for one source file.

This is the only schema the model ever sees. ``extra="forbid"`` on
:class:`~app.application.ai.schemas.base.AIBaseSchema` makes the field
catalogue binding: an answer carrying any other key fails validation as a
whole (R-01), which is how protected traits stay out (R-04).

Dates and URLs are typed as ``str`` on purpose. The contract requires
``raw_value`` to hold the text exactly as the model returned it, and requires
partial dates (``2022``), ongoing-role markers (``present``) and malformed URLs
to be handled per field: rejected under R-02 or normalized under an N-rule. A
``date`` or ``HttpUrl`` annotation would instead fail the whole answer under
R-01 and lose every other field in the file. Parsing happens in
``app.application.ai.normalization``, which stores the catalogue form in
``value`` and keeps the original in ``raw_value``.

The ``confidence`` the model reports is advisory only and is never used for
scoring: the confidence a field record carries is computed in code from checks
that can be verified.
"""

from typing import Generic, TypeVar

from pydantic import Field

from app.application.ai.schemas.base import AIBaseSchema


T = TypeVar("T")


class ExtractedValue(AIBaseSchema, Generic[T]):
    """A single extracted value with its confidence and supporting evidence."""

    value: T | None = None

    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description=(
            "The model's own confidence. Advisory only; the stored score is "
            "computed in code from the four verifiable factors."
        ),
    )

    evidence: str | None = Field(
        default=None,
        description="Original text supporting the extracted value.",
    )

    block_id: str | None = Field(
        default=None,
        description=(
            "The block the evidence was read from. Optional: when the model "
            "omits it, the evidence check searches every block instead."
        ),
    )


class PersonalInformation(AIBaseSchema):
    first_name: ExtractedValue[str] | None = None
    last_name: ExtractedValue[str] | None = None
    email: ExtractedValue[str] | None = None
    phone: ExtractedValue[str] | None = None
    city: ExtractedValue[str] | None = None
    country: ExtractedValue[str] | None = None
    title: ExtractedValue[str] | None = None
    summary: ExtractedValue[str] | None = None


class ExtractedSkill(AIBaseSchema):
    name: ExtractedValue[str]


class ExtractedWorkExperience(AIBaseSchema):
    company: ExtractedValue[str] | None = None
    title: ExtractedValue[str] | None = None
    start_date: ExtractedValue[str] | None = None
    end_date: ExtractedValue[str] | None = None
    description: ExtractedValue[str] | None = None


class ExtractedEducation(AIBaseSchema):
    institution: ExtractedValue[str] | None = None
    degree: ExtractedValue[str] | None = None
    field: ExtractedValue[str] | None = None
    start_date: ExtractedValue[str] | None = None
    end_date: ExtractedValue[str] | None = None


class ExtractedProject(AIBaseSchema):
    name: ExtractedValue[str] | None = None
    description: ExtractedValue[str] | None = None
    url: ExtractedValue[str] | None = None
    tech_stack: list[ExtractedValue[str]] = Field(default_factory=list)


class ExtractedCertification(AIBaseSchema):
    name: ExtractedValue[str] | None = None
    issuer: ExtractedValue[str] | None = None
    issue_date: ExtractedValue[str] | None = None
    url: ExtractedValue[str] | None = None


class ExtractedLanguage(AIBaseSchema):
    name: ExtractedValue[str]
    proficiency: ExtractedValue[str] | None = None


class ExtractedProfileLink(AIBaseSchema):
    type: ExtractedValue[str]
    url: ExtractedValue[str]


class ExtractedProfile(AIBaseSchema):
    """Structured information extracted from one source file."""

    personal_information: PersonalInformation | None = None

    skills: list[ExtractedSkill] = Field(default_factory=list)

    work_experience: list[ExtractedWorkExperience] = Field(
        default_factory=list
    )

    education: list[ExtractedEducation] = Field(default_factory=list)

    projects: list[ExtractedProject] = Field(default_factory=list)

    certifications: list[ExtractedCertification] = Field(
        default_factory=list
    )

    languages: list[ExtractedLanguage] = Field(default_factory=list)

    links: list[ExtractedProfileLink] = Field(default_factory=list)
