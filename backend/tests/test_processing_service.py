"""Attempts and retries (FR-023, FR-058), review flags (FR-041, FR-062, FR-070),
profile built from field records (FR-036, FR-063, FR-038)."""

from app.application.dto.extracted_document import ExtractedDocument
from app.application.interfaces.ai_client import IAIClient, LLMResponse
from app.application.services.cv_processing_service import CVProcessingService, JobStatus
from app.core.exceptions import LLMProviderError
from app.domain.entities.field_record import ReviewReason
from app.domain.entities.processing_attempt import AttemptOutcome, AttemptTrigger
from app.domain.services.confidence import DEFAULT_REVIEW_CONFIDENCE
from app.infrastructure.reference_data import seed_country_catalog, seed_skill_catalog
from tests.helpers import CV_TEXT, answer, as_json, f


class FakeAI(IAIClient):
    """Returns the scripted replies in order; an Exception is raised instead."""
    provider = "fake"
    model = "fake-model-1"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0
        self.user_prompts = []

    def generate_structured(self, system_prompt, user_prompt, json_schema):
        self.calls += 1
        self.user_prompts.append(user_prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(text=reply, provider="fake", model_version="fake-model-1-0612",
                           status="completed")


def make_service(ai, waits=None):
    return CVProcessingService(ai, seed_country_catalog(), seed_skill_catalog(),
                               confidence_threshold=DEFAULT_REVIEW_CONFIDENCE,
                               sleep=(waits.append if waits is not None else lambda s: None))


DOC = ExtractedDocument(source_name="rana.docx", text=CV_TEXT)

#: The same CV as a scan the OCR engine was unsure of, which is what the
#: confidence model reads as uncertainty now (FR-018, FR-048).
SCAN = ExtractedDocument(
    source_name="rana.pdf", text=CV_TEXT, page_texts=[CV_TEXT],
    extraction_method="ocr", ocr_confidence=0.5,
    page_ocr_confidence=[0.5], page_text_layers=[""],
)


def test_valid_first_try_builds_profile_from_field_records():
    result = make_service(FakeAI(as_json(answer()))).process(DOC)

    assert len(result.attempts) == 1
    attempt = result.attempts[0]
    assert attempt.outcome == AttemptOutcome.VALID
    assert attempt.trigger == AttemptTrigger.FIRST_RUN
    assert attempt.model_version == "fake-model-1-0612"
    assert attempt.llm_response and attempt.validation_result["is_valid"]

    profile = result.profile
    assert profile.personal_info.first_name == "Rana"
    assert profile.personal_info.country.code == "JO"
    job = profile.experience[0]
    assert job.employment_status == "current"
    assert job.start_date.value == "2023-06" and job.start_date.precision == "month"

    # FR-063: every profile record points at existing field records
    ids = {r.field_id for r in result.field_records}
    assert set(job.field_ids) <= ids
    personal_ids = {
        fid
        for v in profile.personal_info.field_ids.values()
        for fid in (v if isinstance(v, list) else [v])
    }
    assert personal_ids <= ids


def test_unknown_skill_goes_to_review_and_stays_out_of_profile():
    result = make_service(FakeAI(as_json(answer()))).process(DOC)
    assert [s.name for s in result.profile.skills] == ["React"]   # reactjs -> React
    flagged = [r for r in result.review_items if r.field_name == "name"]
    assert flagged[0].reasons == [ReviewReason.UNKNOWN_SKILL]
    assert flagged[0].options[0].value == "Nagra"
    assert result.status == JobStatus.NEEDS_REVIEW


def test_unknown_country_left_empty_and_queued():
    data = answer()
    data["personal_info"]["country"] = f("Ireland", "Dublin, Ireland")
    text = CV_TEXT + "\nDublin, Ireland"
    result = make_service(FakeAI(as_json(data))).process(
        ExtractedDocument(source_name="x.pdf", text=text))
    assert result.profile.personal_info.country is None
    assert any(ReviewReason.UNKNOWN_COUNTRY in r.reasons for r in result.review_items)


def test_value_without_evidence_in_text_is_rejected():
    """R-03: a value that is not in the document is dropped, not queued. There
    is nothing for a person to decide, so it becomes no field record and no
    review item - only an entry on the attempt's rejected list (NFR-028)."""
    data = answer()
    data["personal_info"]["city"] = f("Dubai", "Dubai, UAE")       # not in the CV
    result = make_service(FakeAI(as_json(data))).process(DOC)

    assert result.profile.personal_info.city is None
    assert not [r for r in result.field_records if r.field_name == "city"]
    assert not [i for i in result.review_items if i.field_name == "city"]
    assert [r.raw_value for r in result.rejected if r.field_name == "city"] == ["Dubai"]
    assert all(r.reason == "R-03" for r in result.rejected)


def test_low_confidence_is_flagged():
    """What makes a value uncertain is the page it was read from, not what the
    model said about itself: the same answer off a 0.50 scan is held back."""
    data = answer()
    data["personal_info"]["last_name"] = f("Odeh", "Rana Odeh", confidence=0.99)
    result = make_service(FakeAI(as_json(data))).process(SCAN)

    assert result.profile.personal_info.last_name is None
    assert any(ReviewReason.LOW_CONFIDENCE in r.reasons for r in result.review_items)
    held = next(r for r in result.field_records if r.field_name == "last_name")
    assert (held.confidence, held.model_confidence) == (0.5, 0.99)


def test_invalid_then_valid_retries_immediately_with_errors_in_prompt():
    """Test 6: Invalid, then valid: 2 attempts, no sleep called, the second prompt contains the errors."""
    waits = []
    ai = FakeAI("not json", as_json(answer()))
    result = make_service(ai, waits).process(DOC)

    assert ai.calls == 2
    assert len(result.attempts) == 2
    assert waits == []  # Retry immediately, no wait
    assert [a.outcome for a in result.attempts] == [
        AttemptOutcome.INVALID, AttemptOutcome.VALID]
    assert [a.trigger for a in result.attempts] == [
        AttemptTrigger.FIRST_RUN, AttemptTrigger.AUTO_RETRY]
    assert result.attempts[0].carried_feedback is False
    assert result.attempts[1].carried_feedback is True
    assert "Your previous answer did not match the schema:" in ai.user_prompts[1]
    assert result.profile is not None


def test_invalid_twice_stops_after_two_attempts_and_goes_to_review():
    """Test 7: Invalid twice: stops after 2 attempts and goes to review with the reason."""
    waits = []
    ai = FakeAI("not json", '{"personal_info": {}}')
    result = make_service(ai, waits).process(DOC)

    assert ai.calls == 2
    assert len(result.attempts) == 2
    assert waits == []  # No wait for invalid retries
    assert result.status == JobStatus.FAILED
    assert result.profile is None
    assert result.review_items[0].reasons == [ReviewReason.LLM_FAILED]
    assert "invalid answer" in result.review_items[0].message


def test_timeout_timeout_valid_three_attempts_with_backoff():
    """Test 8: Timeout, timeout, valid: 3 attempts with backoff."""
    waits = []
    ai = FakeAI(
        LLMProviderError("timeout", retryable=True),
        LLMProviderError("timeout", retryable=True),
        as_json(answer()),
    )
    result = make_service(ai, waits).process(DOC)

    assert ai.calls == 3
    assert len(result.attempts) == 3
    assert waits == [2.0, 4.0]
    assert [a.outcome for a in result.attempts] == [
        AttemptOutcome.ERROR, AttemptOutcome.ERROR, AttemptOutcome.VALID]
    assert result.profile is not None


def test_timeout_then_invalid_twice_stops_at_three_attempts_total():
    """Test 9: Timeout, then invalid twice: stops at 3 attempts in total."""
    waits = []
    ai = FakeAI(
        LLMProviderError("timeout", retryable=True),
        "not json",
        '{"personal_info": {}}',
    )
    result = make_service(ai, waits).process(DOC)

    assert ai.calls == 3
    assert len(result.attempts) == 3
    assert waits == [2.0]  # Only provider timeout waited; invalid was immediate
    assert [a.outcome for a in result.attempts] == [
        AttemptOutcome.ERROR, AttemptOutcome.INVALID, AttemptOutcome.INVALID]
    assert result.status == JobStatus.FAILED
    assert result.profile is None


def test_non_retryable_error_stops_immediately():
    """Test 10: Non-retryable provider error (e.g. 401): 1 attempt, fails at once."""
    waits = []
    ai = FakeAI(LLMProviderError("401: Unauthorized", retryable=False))
    result = make_service(ai, waits).process(DOC)
    assert ai.calls == 1
    assert len(result.attempts) == 1
    assert waits == []
    assert result.status == JobStatus.FAILED


def test_no_text_skips_llm():
    ai = FakeAI()
    result = make_service(ai).process(ExtractedDocument(source_name="scan.pdf", text="  "))
    assert ai.calls == 0
    assert result.review_items[0].reasons == [ReviewReason.NO_TEXT]


def test_admin_rerun_trigger_recorded():
    result = make_service(FakeAI(as_json(answer()))).process(
        DOC, trigger=AttemptTrigger.ADMIN_RERUN)
    assert result.attempts[0].trigger == AttemptTrigger.ADMIN_RERUN


def test_current_job_with_end_date_is_flagged():
    data = answer()
    data["work_experience"][0]["end_date"] = f("June 2023", "June 2023 - Present")
    result = make_service(FakeAI(as_json(data))).process(DOC)
    assert any(ReviewReason.CURRENT_JOB_CONFLICT in r.reasons for r in result.review_items)


def test_attempt_records_cannot_be_changed():
    import dataclasses
    import pytest
    result = make_service(FakeAI(as_json(answer()))).process(DOC)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.attempts[0].error = "edited"
