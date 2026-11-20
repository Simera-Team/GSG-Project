"""Process one extracted document into field records, review items and a profile.

Flow:
  extracted text -> LLM (up to 3 attempts) -> schema validation
  -> field records (evidence, confidence, normalisation) -> review items
  -> profile built from accepted field records -> Simera format check

Requirements covered here:
- FR-020 no readable text: no LLM call, job goes to review with the reason
- FR-023 retry failed/invalid LLM calls up to 3 times with increasing wait,
         then send the job to review with the reason and produce no profile
- FR-058 one immutable attempt record per try (number, trigger, LLM response,
         validation result, error, start/end, model version)
- FR-059 admin re-runs are recorded but do not count toward the 3-try limit
"""

import itertools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.application.dto.cv_extraction import CVExtraction
from app.application.dto.extracted_document import ExtractedDocument
from app.application.dto.profile_document import ProfileDocument
from app.application.interfaces.ai_client import IAIClient
from app.application.prompts.cv_extraction_prompt import SYSTEM_PROMPT, build_user_prompt
from app.application.services.field_record_builder import (
    FieldRecordBuilder,
    FieldRecordSettings,
)
from app.application.services.llm_output_validator import ValidationResult, validate_llm_output
from app.application.services.profile_builder import ProfileBuilder
from app.core.exceptions import LLMProviderError
from app.domain.services.confidence import DEFAULT_REVIEW_CONFIDENCE
from app.domain.services.language import LanguageRule, is_english
from app.domain.entities.field_record import (
    FieldRecord,
    RejectedValue,
    ReviewItem,
    ReviewReason,
)
from app.domain.entities.processing_attempt import (
    AttemptLog,
    AttemptOutcome,
    AttemptTrigger,
    ProcessingAttempt,
)
from app.domain.services.countries import CountryCatalog
from app.domain.services.skills import SkillCatalog


logger = logging.getLogger(__name__)


class JobStatus:
    DONE = "done"                   # profile built, nothing needs a person
    NEEDS_REVIEW = "needs_review"   # profile built, some fields wait for a reviewer
    FAILED = "failed"               # no profile; whole job is in the review queue
    REJECTED = "rejected"           # file rejected (e.g. unsupported language)


@dataclass
class ProcessingResult:
    status: str
    reason: str | None
    attempts: tuple[ProcessingAttempt, ...]
    field_records: list[FieldRecord] = field(default_factory=list)
    review_items: list[ReviewItem] = field(default_factory=list)
    profile: ProfileDocument | None = None
    confidence_threshold: float | None = None   # the limit this job used (FR-067)
    # Values dropped by an R- rule: not field records and not review items,
    # but kept so a drop can be audited (R-03, NFR-028).
    rejected: list[RejectedValue] = field(default_factory=list)
    rule: str | None = None
    message: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "rule": self.rule,
            "message": self.message,
            "confidence_threshold": self.confidence_threshold,
            "attempts": [a.to_dict() for a in self.attempts],
            "review_items": [r.to_dict() for r in self.review_items],
            "field_records": [r.to_dict() for r in self.field_records],
            "rejected": [r.to_dict() for r in self.rejected],
            "profile": self.profile.model_dump(mode="json") if self.profile else None,
        }


class CVProcessingService:

    def __init__(self, ai_client: IAIClient, countries: CountryCatalog,
                 skills: SkillCatalog, confidence_threshold: float = DEFAULT_REVIEW_CONFIDENCE,
                 max_attempts: int = 3, retry_base_seconds: float = 2.0,
                 sleep: Callable[[float], None] = time.sleep):
        self.ai_client = ai_client
        self.countries = countries
        self.skills = skills
        self.confidence_threshold = confidence_threshold
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds
        self.sleep = sleep
        self.schema = CVExtraction.model_json_schema()

    def process(self, document: ExtractedDocument,
                trigger: AttemptTrigger = AttemptTrigger.FIRST_RUN) -> ProcessingResult:
        review_ids = itertools.count(1)
        log = AttemptLog()

        # FR-020: nothing to send to the LLM.
        if not document.text.strip():
            return self._failed(document, log, review_ids, ReviewReason.NO_TEXT,
                                "No text could be read from the file")

        # R-11: Only English sources are accepted. Check language before any LLM call.
        if not is_english(document.text):
            logger.info("File %s rejected: unsupported_language (rule: %s)",
                        document.source_name, LanguageRule.UNSUPPORTED_LANGUAGE)
            return ProcessingResult(
                status=JobStatus.REJECTED,
                reason="unsupported_language",
                attempts=(),
                field_records=[],
                review_items=[],
                profile=None,
                confidence_threshold=self.confidence_threshold,
                rule=LanguageRule.UNSUPPORTED_LANGUAGE,
                message="Only CVs written in English are accepted. Please upload an English version.",
            )

        validation, last_error = self._run_attempts(document, trigger, log)
        if validation is None:
            # FR-023: after the last failed attempt, a person gets the job; no profile data.
            return self._failed(document, log, review_ids, ReviewReason.LLM_FAILED,
                                f"LLM extraction failed after {len(log.attempts)} "
                                f"attempt(s): {last_error}")

        builder = FieldRecordBuilder(
            self.countries, self.skills,
            FieldRecordSettings(confidence_threshold=self.confidence_threshold),
        )
        extracted = builder.build(validation.extraction, document)
        records = extracted.records
        built = ProfileBuilder(review_ids, self.confidence_threshold).build(records)

        if built.profile is None:
            status, reason = JobStatus.FAILED, "Built profile failed the Simera profile format"
        elif built.review_items:
            status, reason = JobStatus.NEEDS_REVIEW, f"{len(built.review_items)} field(s) need review"
        else:
            status, reason = JobStatus.DONE, None

        return ProcessingResult(status, reason, log.attempts, records,
                                built.review_items, built.profile,
                                self.confidence_threshold, extracted.rejected)

    def _run_attempts(self, document, first_trigger, log: AttemptLog):
        base_prompt = build_user_prompt(document.text, document.hyperlinks,
                                         document.ocr_confidence, document.page_texts)
        prompt = base_prompt
        last_error = "unknown error"
        invalid_count = 0
        carried_feedback = False
        provider_attempt = 0

        for number in range(1, self.max_attempts + 1):
            trigger = first_trigger if number == 1 else AttemptTrigger.AUTO_RETRY
            started = _now()

            try:
                response = self.ai_client.generate_structured(SYSTEM_PROMPT, prompt, self.schema)
            except LLMProviderError as exc:
                provider_attempt += 1
                last_error = str(exc)
                log.append(self._attempt(number, trigger, started, AttemptOutcome.ERROR,
                                         self.ai_client.model, None, None, last_error,
                                         carried_feedback=carried_feedback))
                if not exc.retryable:
                    break                      # e.g. invalid key: another try cannot help

                if number >= self.max_attempts:
                    break

                wait = self.retry_base_seconds * (2 ** (provider_attempt - 1))
                wait = max(wait, exc.retry_after or 0)
                self.sleep(wait)
            else:
                validation = self._validate(response)
                outcome = AttemptOutcome.VALID if validation.is_valid else AttemptOutcome.INVALID
                error = None if validation.is_valid else "; ".join(validation.errors[:5])
                log.append(self._attempt(number, trigger, started, outcome,
                                         response.model_version, response.text,
                                         validation.to_dict(), error,
                                         carried_feedback=carried_feedback))
                if validation.is_valid:
                    return validation, None

                invalid_count += 1
                last_error = f"invalid answer ({error})"

                # At most 2 attempts in total for invalid output
                if invalid_count >= 2 or number >= self.max_attempts:
                    break

                # Retry IMMEDIATELY, with no wait, appending validation errors as feedback
                feedback = self._format_validation_feedback(validation.errors)
                prompt = (
                    f"{base_prompt}\n\n"
                    f"Your previous answer did not match the schema: {feedback}. "
                    "Return the complete JSON again, fixing these errors."
                )
                carried_feedback = True

        return None, last_error

    @staticmethod
    def _format_validation_feedback(errors: list[str]) -> str:
        """Format up to 10 validation errors (field paths and messages only, <= 1000 chars)."""
        selected = errors[:10]
        formatted = "; ".join(selected)
        if len(formatted) > 1000:
            formatted = formatted[:1000].rstrip()
        return formatted

    @staticmethod
    def _validate(response) -> ValidationResult:
        if response.status != "completed":
            return ValidationResult(False, [f"LLM did not finish (status: {response.status})"])
        return validate_llm_output(response.text)

    def _attempt(self, number, trigger, started, outcome, model_version,
                 llm_response, validation, error,
                 carried_feedback: bool = False) -> ProcessingAttempt:
        return ProcessingAttempt(
            attempt_number=number,
            trigger=trigger,
            provider=self.ai_client.provider,
            model_version=model_version,
            started_at=started,
            finished_at=_now(),
            outcome=outcome,
            llm_response=llm_response,
            validation_result=validation,
            error=error,
            carried_feedback=carried_feedback,
        )

    def _failed(self, document, log, review_ids, reason, message) -> ProcessingResult:
        # FR-042: a failed job has no field name; the item links to the source only.
        item = ReviewItem(review_id=next(review_ids), source=document.source_name,
                          reasons=[reason], message=message)
        return ProcessingResult(JobStatus.FAILED, message, log.attempts,
                                review_items=[item],
                                confidence_threshold=self.confidence_threshold)


def _now() -> datetime:
    return datetime.now(timezone.utc)
