from dataclasses import dataclass, field
from typing import Any

# rule of a field record created by a reviewer's decision (FR-043)
DECISION_RULE = "review_decision"


# Why a field needs a human (stored on the field record and the review item).
class ReviewReason:
    LOW_CONFIDENCE = "low_confidence"                 # FR-041, NFR-027
    LOW_OCR_CONFIDENCE = "low_ocr_confidence"         # FR-018
    EVIDENCE_MISSING = "evidence_missing"             # NFR-028
    EVIDENCE_NOT_FOUND = "evidence_not_found"         # NFR-028
    VALUE_NOT_IN_EVIDENCE = "value_not_in_evidence"   # NFR-028
    UNPARSEABLE_DATE = "unparseable_date"             # FR-028
    CURRENT_JOB_CONFLICT = "current_job_has_end_date" # FR-028
    UNKNOWN_COUNTRY = "unknown_country"               # FR-070
    UNKNOWN_SKILL = "unknown_skill"                   # FR-062
    INVALID_FORMAT = "invalid_format"                 # e-mail / URL shape
    SOURCE_CONFLICT = "source_conflict"               # FR-033
    LLM_FAILED = "llm_failed"                         # FR-023
    NO_TEXT = "no_text"                               # FR-020
    PROFILE_INVALID = "profile_invalid"               # FR-038


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
