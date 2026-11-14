"""The confidence score: a product of four factors we can verify.

Confidence is computed here, never taken from the LLM, so a confident-sounding
answer with weak evidence scores low. A field below the threshold is marked
``low_confidence`` and goes to review after one retry (R-06).
"""

from dataclasses import dataclass

from app.application.ai.schemas.field_record import ConfidenceParts, ExtractionStatus
from app.application.ai.settings import AISettings


@dataclass(frozen=True, slots=True)
class ConfidenceAssessment:
    """A score, its parts, and what the score means for the field."""

    confidence: float
    parts: ConfidenceParts
    status: ExtractionStatus

    @property
    def below_threshold(self) -> bool:
        return self.status is ExtractionStatus.LOW_CONFIDENCE


@dataclass(frozen=True, slots=True)
class RetryPlan:
    """Which factor pulled a score down, and the one retry that targets it.

    The retry runs once per field at most; if the new score is still below the
    threshold the field goes to review.
    """

    rerun_ocr: bool
    reask_llm: bool

    @property
    def is_worth_retrying(self) -> bool:
        return self.rerun_ocr or self.reask_llm


class ConfidenceScorer:
    """Combines the four factors and says what the result means."""

    def __init__(self, settings: AISettings) -> None:
        self._settings = settings

    def score(
        self,
        *,
        base: float,
        evidence: float,
        validation: float,
        mapping: float,
    ) -> ConfidenceAssessment:
        """Return the confidence of one field record."""
        parts = ConfidenceParts(
            base=base,
            evidence=evidence,
            validation=validation,
            mapping=mapping,
        )
        confidence = parts.product
        status = (
            ExtractionStatus.OK
            if confidence >= self._settings.confidence_threshold
            else ExtractionStatus.LOW_CONFIDENCE
        )
        return ConfidenceAssessment(confidence=confidence, parts=parts, status=status)

    def plan_retry(self, parts: ConfidenceParts, *, page_is_ocr: bool) -> RetryPlan:
        """Decide what the single R-06 retry should do.

        The retry targets the factor that pulled the score down: a weak OCR base
        means re-reading the page, while weak evidence or validation on a text
        page means re-asking the model for that one field with only its block.
        When both are weak, both run in the same retry round.
        """
        weakest = min(parts.base, parts.evidence, parts.validation, parts.mapping)

        rerun_ocr = page_is_ocr and parts.base <= weakest
        reask_llm = min(parts.evidence, parts.validation) <= weakest

        return RetryPlan(rerun_ocr=rerun_ocr, reask_llm=reask_llm)

    def apply_agreement_boost(
        self,
        confidences: list[float],
        *,
        agreeing_sources: int,
    ) -> float:
        """Raise the confidence of a value that independent sources confirm (M-04).

        The boost is the highest confidence among the agreeing sources plus the
        configured step, capped at 1.00, and is added once however many sources
        agree. Two blurry scans of the same CV still count, because a second
        file confirming a value is evidence in itself; the same value appearing
        twice inside one source is not.
        """
        if not confidences:
            return 0.0

        highest = max(confidences)
        if agreeing_sources < 2:
            return highest

        return round(min(1.0, highest + self._settings.agreement_boost), 2)
