"""Schemas for the stage that puts several sources together.

Matching groups the records that describe the same real thing across sources;
conflict resolution then picks one value per field, or hands the field on with
every candidate value intact when no rule decides.
"""

from enum import Enum

from pydantic import Field

from app.application.ai.rules import RuleId
from app.application.ai.schemas.base import AIBaseSchema
from app.application.ai.schemas.document_text import SourceMeta
from app.application.ai.schemas.field_record import (
    EntityType,
    ExtractionResult,
    FieldName,
    FieldRecord,
)
from app.application.ai.schemas.normalized_value import NormalizedValue


class FieldKind(str, Enum):
    """Whether a field can conflict at all.

    List fields merge by union and never conflict; single fields can.
    """

    SINGLE = "single"
    LIST = "list"


class ConflictFallback(str, Enum):
    """Who decides when no rule in a field's policy does.

    Only fields with a reviewer or candidate fallback can ever reach a person;
    every other path ends in accept or reject.
    """

    NONE = "none"
    REVIEWER = "reviewer"
    CANDIDATE = "candidate"


class SourceExtraction(AIBaseSchema):
    """One source's result together with the metadata the rules need."""

    meta: SourceMeta
    result: ExtractionResult


class SourceEntity(AIBaseSchema):
    """One entity as a single source described it.

    Records are kept as a list rather than keyed by field name, because a list
    field such as a profile link or a project's tech stack is stated more than
    once within the same entity.
    """

    source: SourceMeta
    entity: EntityType
    entity_key: str
    records: list[FieldRecord] = Field(default_factory=list)

    def records_for(self, field: FieldName) -> list[FieldRecord]:
        """Return every record this source gave for ``field``."""
        return [record for record in self.records if record.field is field]

    def record_for(self, field: FieldName) -> FieldRecord | None:
        """Return the first record for ``field``, for single-valued fields."""
        return next((record for record in self.records if record.field is field), None)

    def value_of(self, field: FieldName) -> NormalizedValue | None:
        record = self.record_for(field)
        return record.value if record else None

    @property
    def field_names(self) -> list[FieldName]:
        """The fields this source stated, in the order it stated them."""
        seen: list[FieldName] = []
        for record in self.records:
            if record.field not in seen:
                seen.append(record.field)
        return seen


class MatchedEntity(AIBaseSchema):
    """The same entity as seen across every source that mentions it.

    ``entity_id`` is stable within one merge run; the backend maps it onto the
    profile entity's own persistent id.
    """

    entity: EntityType
    entity_id: str
    members: list[SourceEntity] = Field(default_factory=list)
    matched_by: RuleId | None = Field(
        default=None,
        description="The rule that joined the members, or null for a single-source entity.",
    )

    @property
    def source_count(self) -> int:
        return len({member.source.source_id for member in self.members})


class ValueCandidate(AIBaseSchema):
    """One source's answer for a field, kept whether or not it won."""

    source: SourceMeta
    record: FieldRecord


class ResolvedField(AIBaseSchema):
    """A field a rule decided, with the losing candidates kept for history."""

    entity: EntityType
    entity_id: str
    field: FieldName
    kind: FieldKind

    values: list[ValueCandidate] = Field(
        description="The chosen value, or every member of a merged list, newest source first.",
    )
    decided_by: RuleId | None = Field(
        default=None,
        description="The rule that chose the value, or null when only one source stated it.",
    )
    confidence: float = Field(
        ge=0,
        le=1,
        description="The chosen value's confidence, or the weakest value's for a list.",
    )
    agreeing_sources: list[str] = Field(
        default_factory=list,
        description="Sources that gave the same value after normalization (M-04).",
    )
    discarded: list[ValueCandidate] = Field(
        default_factory=list,
        description="Values not chosen, kept so the decision can be explained (FR-035).",
    )


class UnresolvedConflict(AIBaseSchema):
    """A field no rule decided, passed on with every candidate value intact."""

    entity: EntityType
    entity_id: str
    field: FieldName
    candidates: list[ValueCandidate]
    fallback: ConflictFallback
    reason: RuleId = Field(
        description="The rule that sends the field to a person (C-05, C-06 or R-06).",
    )


class MergeResult(AIBaseSchema):
    """Everything the merge stage produced for one candidate."""

    resolved: list[ResolvedField] = Field(default_factory=list)
    conflicts: list[UnresolvedConflict] = Field(default_factory=list)
    rule_version: str | None = None
    policy_version: str | None = None
