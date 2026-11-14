"""Output contract: one record per extracted value, plus the result wrapper.

A record is deliberately single-valued. A CV fragment of one job with four
stated fields and two skills becomes six records, each with its own evidence and
confidence, so every value can be checked, accepted or rejected on its own.
``entity_key`` is what ties the fields of one entity back together.
"""

from enum import Enum

from pydantic import Field, computed_field

from app.application.ai.rules import RuleId
from app.application.ai.schemas.base import AIBaseSchema
from app.application.ai.schemas.normalized_value import NormalizedValue


class EntityType(str, Enum):
    """Which kind of thing a field belongs to."""

    PROFILE = "profile"
    WORK_EXPERIENCE = "work_experience"
    EDUCATION = "education"
    SKILL = "skill"
    CERTIFICATION = "certification"
    PROJECT = "project"
    LANGUAGE = "language"


class FieldName(str, Enum):
    """The field catalogue. Nothing outside this list is ever extracted.

    Names follow the extraction schema and the stored profile, which splits a
    person's name into ``first_name`` / ``last_name`` and calls the headline
    ``title``.
    """

    # profile
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    EMAIL = "email"
    PHONE = "phone"
    CITY = "city"
    COUNTRY = "country"
    SUMMARY = "summary"
    LINK = "link"

    # shared between entities
    TITLE = "title"
    NAME = "name"
    DESCRIPTION = "description"
    URL = "url"
    START_DATE = "start_date"
    END_DATE = "end_date"

    # work_experience
    COMPANY = "company"

    # education
    INSTITUTION = "institution"
    DEGREE = "degree"
    FIELD = "field"

    # certification
    ISSUER = "issuer"
    ISSUE_DATE = "issue_date"

    # project
    TECH_STACK = "tech_stack"

    # language
    PROFICIENCY = "proficiency"

    def __str__(self) -> str:
        return self.value


class EvidenceMatch(str, Enum):
    """How the model's snippet was found in the block text."""

    EXACT = "exact"
    FUZZY_HIGH = "fuzzy_high"
    FUZZY_LOW = "fuzzy_low"


class ExtractionStatus(str, Enum):
    """Result of the AI checks, before the merge stage decides the outcome."""

    OK = "ok"
    LOW_CONFIDENCE = "low_confidence"


#: Stable key of the single profile entity. A person's own details exist once
#: per person, unlike jobs or skills, which repeat.
PROFILE_ENTITY_KEY = "profile#1"


def build_entity_key(entity: EntityType, index: int) -> str:
    """Return the entity key for the ``index``-th ``entity`` in one source.

    Entities are numbered in order of appearance and the number is local to the
    source: the same job can be #1 in a CV and #2 in LinkedIn. Matching them
    across sources is the merge stage's job (M-01).
    """
    if entity is EntityType.PROFILE:
        return PROFILE_ENTITY_KEY
    return f"{entity.value}#{index}"


class FieldEvidence(AIBaseSchema):
    """Where a value was read, and how well the snippet matched the source."""

    block_id: str
    page: int = Field(ge=1, description="Markdown sources are always page 1.")
    snippet: str = Field(description="Shortest span of source text containing the value.")
    match: EvidenceMatch
    similarity: float = Field(
        default=1.0,
        ge=0,
        le=1,
        description="Similarity that produced the match class, kept for tuning.",
    )


class ConfidenceParts(AIBaseSchema):
    """The four verifiable factors whose product is the confidence score.

    The score is computed in code from checks we can verify; it is never taken
    from the LLM.
    """

    base: float = Field(ge=0, le=1, description="Quality of the text the value was read from.")
    evidence: float = Field(ge=0, le=1, description="How well the snippet matched the source.")
    validation: float = Field(
        ge=0, le=1, description="Passed format checks as is, or after a repair."
    )
    mapping: float = Field(
        ge=0, le=1, description="Matched a skill or country table exactly or fuzzily."
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def product(self) -> float:
        """base x evidence x validation x mapping, rounded to two decimals."""
        return round(self.base * self.evidence * self.validation * self.mapping, 2)


class FieldRecord(AIBaseSchema):
    """One extracted value that passed every AI check."""

    entity: EntityType
    entity_key: str
    field: FieldName

    raw_value: str = Field(description="Text exactly as the LLM returned it, before normalization.")
    value: NormalizedValue = Field(description="The normalized value in catalogue format.")

    confidence: float = Field(ge=0, le=1)
    confidence_parts: ConfidenceParts
    evidence: FieldEvidence

    normalization: RuleId | None = Field(
        default=None,
        description="The normalization rule applied, or null when the value needed none.",
    )
    extraction_status: ExtractionStatus = ExtractionStatus.OK


class RejectedValue(AIBaseSchema):
    """A value an R-rule dropped, kept for the audit trail.

    This list is stored with the processing attempt so an admin can see what was
    dropped and why. It is never written to application log files, which must
    not hold personal data.
    """

    entity: EntityType
    field: FieldName
    raw_value: str
    reason: RuleId
    detail: str | None = None


class ExtractionResult(AIBaseSchema):
    """Everything the AI module returns for one source."""

    source_id: str
    fields: list[FieldRecord] = Field(default_factory=list)
    rejected: list[RejectedValue] = Field(default_factory=list)

    def fields_for(self, entity_key: str) -> list[FieldRecord]:
        """Return the records that describe one entity."""
        return [record for record in self.fields if record.entity_key == entity_key]


class CandidateValue(AIBaseSchema):
    """A value read off the LLM answer, before normalization and scoring.

    This is the pipeline's internal hand-off between flattening the extraction
    schema and running the deterministic checks over each value.
    """

    entity: EntityType
    entity_key: str
    field: FieldName
    raw_value: str
    evidence_snippet: str | None = None
    block_id: str | None = Field(
        default=None,
        description="Block the model cited, when it cited one; otherwise the verifier searches.",
    )
    raw_type: str | None = Field(
        default=None,
        description=(
            "The kind the model assigned, for the one field whose catalogue form "
            "is typed rather than scalar: a profile link's {type, url}."
        ),
    )
