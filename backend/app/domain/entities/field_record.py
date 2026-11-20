from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:                      # avoids a cycle: confidence imports this module
    from app.domain.services.confidence import ConfidenceParts

# rule of a field record created by a reviewer's decision (FR-043)
DECISION_RULE = "review_decision"


# Why a field needs a human (stored on the field record and the review item).
class ReviewReason:
    LOW_CONFIDENCE = "low_confidence"                 # FR-041, NFR-027
    # The three evidence failures below are no longer raised: a value whose
    # snippet is not in the document is rejected under R-03 instead of being
    # queued, because there is nothing for a person to decide (NFR-028). They
    # stay listed so records stored before that change still read back with a
    # reason a dashboard can name.
    EVIDENCE_MISSING = "evidence_missing"             # NFR-028, legacy
    EVIDENCE_NOT_FOUND = "evidence_not_found"         # NFR-028, legacy
    VALUE_NOT_IN_EVIDENCE = "value_not_in_evidence"   # NFR-028, legacy
    # Raised while OCR quality was a flag of its own; it is now the `base`
    # factor of the confidence model, so a poor scan scores low instead.
    LOW_OCR_CONFIDENCE_LEGACY = "low_ocr_confidence"  # FR-018, legacy
    UNPARSEABLE_DATE = "unparseable_date"             # FR-028
    CURRENT_JOB_CONFLICT = "current_job_has_end_date" # FR-028
    UNKNOWN_COUNTRY = "unknown_country"               # FR-070
    UNKNOWN_SKILL = "unknown_skill"                   # FR-062
    INVALID_FORMAT = "invalid_format"                 # e-mail / URL shape
    SOURCE_CONFLICT = "source_conflict"               # FR-033
    ENTITY_MATCH_AMBIGUOUS = "entity_match_ambiguous" # M-01 / R-10
    LLM_FAILED = "llm_failed"                         # FR-023
    NO_TEXT = "no_text"                               # FR-020
    PROFILE_INVALID = "profile_invalid"               # FR-038


#: Reasons that are not a property of one file but of how a candidate's
#: sources fit together, so they are recomputed for the whole profile on every
#: rebuild instead of being replaced per file (FR-033, FR-036).
CROSS_SOURCE_REASONS: tuple[str, ...] = (
    ReviewReason.SOURCE_CONFLICT,
    ReviewReason.ENTITY_MATCH_AMBIGUOUS,
)


def is_cross_source(reasons) -> bool:
    """Whether a review item came from comparing sources rather than reading one."""
    return any(reason in CROSS_SOURCE_REASONS for reason in reasons)


@dataclass
class FieldRecord:
    """One extracted value with its entity, source, confidence, evidence
    and the rule that produced it (FR-035, FR-060, FR-065)."""

    field_id: int
    source: str                      # source file the value came from
    entity: str                      # e.g. "personal_info", "work_experience[2]"
    entity_type: str                 # e.g. "work_experience"
    field_name: str                  # e.g. "end_date"
    raw_value: Any                   # value exactly as the LLM returned it
    value: Any                       # value after normalisation
    confidence: float
    evidence: str | None
    page: int | None
    evidence_status: str             # verified | verified_fuzzy | missing | not_found | not_required
    rule: str                        # e.g. llm_extraction, date_normalized, alias_table
    review_reasons: list[str] = field(default_factory=list)
    note: str | None = None          # hint for the reviewer, e.g. closest skill

    # Why the confidence is what it is: base x evidence x validation x mapping,
    # plus any agreement between sources (M-04). Stored so a number can always
    # be explained rather than trusted (FR-035, FR-048).
    confidence_parts: "ConfidenceParts | None" = None

    # What the language model said about its own answer. Kept for comparison
    # only: it is not part of the formula and decides nothing, because a model
    # reports the same certainty for a copied value and an invented one.
    model_confidence: float | None = None

    # Where the value came from, needed by the conflict rules (FR-031, FR-032).
    # Set when records are loaded for a merge; left at the defaults while a
    # single file is being processed, where there is nothing to compare against.
    source_kind: str = "cv"                      # cv | linkedin | vetting
    source_uploaded_at: datetime | None = None   # recency for FR-031

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons)

    @property
    def review_status(self) -> str:
        return "needs_review" if self.needs_review else "accepted"

    def to_dict(self) -> dict:
        return {
            "field_id": self.field_id,
            "source": self.source,
            "entity": self.entity,
            "field_name": self.field_name,
            "raw_value": self.raw_value,
            "value": self.value,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "page": self.page,
            "evidence_status": self.evidence_status,
            "rule": self.rule,
            "review_status": self.review_status,
            "review_reasons": self.review_reasons,
            "note": self.note,
            "source_kind": self.source_kind,
            "confidence_parts": self.confidence_parts.to_dict() if self.confidence_parts else None,
            "model_confidence": self.model_confidence,
        }


@dataclass
class RejectedValue:
    """A value an ``R-`` rule dropped, kept so the drop can be audited.

    A rejected value is not a field record and not a review item: there is
    nothing for a person to decide, because the value is not in the source
    document (NFR-028). It is still written down, because "the model claimed
    this and we threw it away" is exactly what someone investigating a bad
    profile needs to see. The list is stored with the processing attempt that
    produced it, never in an application log, which must hold no personal data.
    """

    entity: str                      # e.g. "work_experience[2]"
    entity_type: str
    field_name: str
    raw_value: Any                   # value exactly as the LLM returned it
    reason: str                      # the rule that dropped it, e.g. "R-03"
    detail: str | None = None        # why, in a sentence
    evidence: str | None = None      # the snippet the model offered
    page: int | None = None

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "entity_type": self.entity_type,
            "field_name": self.field_name,
            "raw_value": self.raw_value,
            "reason": self.reason,
            "detail": self.detail,
            "evidence": self.evidence,
            "page": self.page,
        }


@dataclass
class ReviewOption:
    value: Any
    source: str
    confidence: float | None = None
    evidence: str | None = None
    page: int | None = None
    field_id: int | None = None


@dataclass
class ReviewItem:
    """An entry in the needs-review queue (FR-041, FR-042).

    A failed job has no entity or field name; it links to the source only.
    """

    review_id: int
    source: str
    reasons: list[str]
    entity: str | None = None
    field_name: str | None = None
    message: str | None = None
    options: list[ReviewOption] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "review_id": self.review_id,
            "source": self.source,
            "entity": self.entity,
            "field_name": self.field_name,
            "reasons": self.reasons,
            "message": self.message,
            "options": [vars(o) for o in self.options],
        }
