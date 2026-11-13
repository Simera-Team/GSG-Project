"""Attempts and retries (FR-023, FR-058), review flags (FR-041, FR-062, FR-070),
profile built from field records (FR-036, FR-063, FR-038)."""

from app.application.dto.extracted_document import ExtractedDocument
from app.application.interfaces.ai_client import IAIClient, LLMResponse
from app.application.services.cv_processing_service import CVProcessingService, JobStatus
from app.core.exceptions import LLMProviderError
from app.domain.entities.field_record import ReviewReason
from app.domain.entities.processing_attempt import AttemptOutcome, AttemptTrigger
from app.infrastructure.reference_data import seed_country_catalog, seed_skill_catalog
from tests.helpers import CV_TEXT, answer, as_json, f


class FakeAI(IAIClient):
    """Returns the scripted replies in order; an Exception is raised instead."""
    provider = "fake"
    model = "fake-model-1"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def generate_structured(self, system_prompt, user_prompt, json_schema):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(text=reply, provider="fake", model_version="fake-model-1-0612",
                           status="completed")


def make_service(ai, waits=None):
    return CVProcessingService(ai, seed_country_catalog(), seed_skill_catalog(),
                               confidence_threshold=0.6,
                               sleep=(waits.append if waits is not None else lambda s: None))


DOC = ExtractedDocument(source_name="rana.docx", text=CV_TEXT)


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
    assert set(profile.personal_info.field_ids.values()) <= ids


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


def test_value_without_evidence_in_text_is_flagged():
    data = answer()
    data["personal_info"]["city"] = f("Dubai", "Dubai, UAE")       # not in the CV
    result = make_service(FakeAI(as_json(data))).process(DOC)
    assert result.profile.personal_info.city is None
    assert any(ReviewReason.EVIDENCE_NOT_FOUND in r.reasons for r in result.review_items)


def test_low_confidence_is_flagged():
    data = answer()
    data["personal_info"]["last_name"] = f("Odeh", "Rana Odeh", confidence=0.4)
    result = make_service(FakeAI(as_json(data))).process(DOC)
    assert result.profile.personal_info.last_name is None
    assert any(ReviewReason.LOW_CONFIDENCE in r.reasons for r in result.review_items)


def test_invalid_then_valid_retries_with_increasing_wait():
    waits = []
    ai = FakeAI("not json", '{"personal_info": {}}', as_json(answer()))
    result = make_service(ai, waits).process(DOC)

    assert [a.outcome for a in result.attempts] == [
        AttemptOutcome.INVALID, AttemptOutcome.INVALID, AttemptOutcome.VALID]
    assert [a.trigger for a in result.attempts] == [
        AttemptTrigger.FIRST_RUN, AttemptTrigger.AUTO_RETRY, AttemptTrigger.AUTO_RETRY]
    assert waits == [2.0, 4.0]
    assert result.profile is not None


def test_three_failures_send_job_to_review_without_profile():
    ai = FakeAI(LLMProviderError("server error 503", retryable=True),
                "not json",
                LLMProviderError("network error", retryable=True))
    result = make_service(ai).process(DOC)

    assert ai.calls == 3
    assert result.status == JobStatus.FAILED
    assert result.profile is None and result.field_records == []
    item = result.review_items[0]
    assert item.reasons == [ReviewReason.LLM_FAILED]
    assert item.field_name is None and item.source == "rana.docx"   # FR-042
    assert "network error" in item.message


def test_non_retryable_error_stops_immediately():
    ai = FakeAI(LLMProviderError("400: API key not valid", retryable=False))
    result = make_service(ai).process(DOC)
    assert ai.calls == 1
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
