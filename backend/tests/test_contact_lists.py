"""Tests for Part 1: Emails and phones are lists (M-03)."""

from datetime import datetime, timezone

from app.application.dto.cv_extraction import CVExtraction
from app.application.dto.extracted_document import ExtractedDocument
from app.application.services.field_record_builder import FieldRecordBuilder, FieldRecordSettings
from app.application.services.profile_builder import ProfileBuilder
from app.domain.entities.field_record import FieldRecord, ReviewReason
from app.domain.services.confidence import ConfidenceParts
from app.domain.services.conflict_rules import ConflictRule, Fallback, resolve_field
from app.domain.services.countries import CountryCatalog
from app.infrastructure.reference_data import SEED_COUNTRIES, seed_skill_catalog
from tests.helpers import answer, f

OLDER = datetime(2024, 1, 1, tzinfo=timezone.utc)
NEWER = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_cv_with_two_emails_two_records_both_in_profile_no_review():
    """1. CV with two emails: two records, both in the profile, no review item."""
    data = answer()
    data["personal_info"]["emails"] = [
        f("rana.work@example.com", "rana.work@example.com"),
        f("rana.personal@example.com", "rana.personal@example.com"),
    ]
    text = (
        "Rana Odeh\n"
        "rana.work@example.com | rana.personal@example.com\n"
        "Amman, Jordan 11942\n"
    )
    doc = ExtractedDocument(source_name="cv.pdf", text=text)
    builder = FieldRecordBuilder(
        CountryCatalog(SEED_COUNTRIES), seed_skill_catalog(),
        FieldRecordSettings(confidence_threshold=0.6),
    )
    outcome = builder.build(CVExtraction.model_validate(data), doc)

    email_records = [r for r in outcome.records if r.field_name == "email"]
    assert len(email_records) == 2
    assert {r.value for r in email_records} == {"rana.work@example.com", "rana.personal@example.com"}

    result = ProfileBuilder(confidence_threshold=0.6).build(outcome.records)
    profile = result.profile
    assert profile is not None
    assert len(profile.personal_info.emails) == 2
    assert profile.personal_info.emails == ["rana.work@example.com", "rana.personal@example.com"]
    assert profile.personal_info.email == "rana.work@example.com"
    assert profile.personal_info.primary_email == "rana.work@example.com"
    email_reviews = [i for i in result.review_items if i.field_name in ("email", "emails")]
    assert email_reviews == []


def test_cv_email_a_linkedin_email_b_both_kept_primary_is_b():
    """2. CV email A, LinkedIn (newer) email B: both kept, primary is B, no candidate question."""
    r_cv = FieldRecord(
        field_id=1, source="1", entity="personal_info", entity_type="personal_info",
        field_name="email", raw_value="email.a@example.com", value="email.a@example.com",
        confidence=0.9, evidence="email.a@example.com", page=1, evidence_status="verified",
        rule="llm_extraction", source_kind="cv", source_uploaded_at=OLDER,
    )
    r_li = FieldRecord(
        field_id=2, source="2", entity="personal_info", entity_type="personal_info",
        field_name="email", raw_value="email.b@example.com", value="email.b@example.com",
        confidence=0.9, evidence="email.b@example.com", page=1, evidence_status="verified",
        rule="llm_extraction", source_kind="linkedin", source_uploaded_at=NEWER,
    )
    result = ProfileBuilder(confidence_threshold=0.6).build([r_cv, r_li])
    profile = result.profile
    assert profile is not None
    assert set(profile.personal_info.emails) == {"email.a@example.com", "email.b@example.com"}
    assert profile.personal_info.email == "email.b@example.com"
    assert profile.personal_info.primary_email == "email.b@example.com"
    assert not any(i.field_name in ("email", "emails") for i in result.review_items)


def test_email_case_variants_merge_to_one_with_m04_boost():
    """3. "Ahmad.K@Example.com" in the CV and "ahmad.k@example.com" in LinkedIn: one email, M-04 boost."""
    r_cv = FieldRecord(
        field_id=1, source="1", entity="personal_info", entity_type="personal_info",
        field_name="email", raw_value="Ahmad.K@Example.com", value="ahmad.k@example.com",
        confidence=0.62, evidence="Ahmad.K@Example.com", page=1, evidence_status="verified",
        rule="N-EMAIL-01", source_kind="cv", source_uploaded_at=OLDER,
        confidence_parts=ConfidenceParts(base=0.62),
    )
    r_li = FieldRecord(
        field_id=2, source="2", entity="personal_info", entity_type="personal_info",
        field_name="email", raw_value="ahmad.k@example.com", value="ahmad.k@example.com",
        confidence=0.62, evidence="ahmad.k@example.com", page=1, evidence_status="verified",
        rule="N-EMAIL-01", source_kind="linkedin", source_uploaded_at=NEWER,
        confidence_parts=ConfidenceParts(base=0.62),
    )
    result = ProfileBuilder(confidence_threshold=0.65).build([r_cv, r_li])
    profile = result.profile
    assert profile is not None
    assert profile.personal_info.emails == ["ahmad.k@example.com"]
    assert profile.personal_info.email == "ahmad.k@example.com"
    assert profile.personal_info.primary_email == "ahmad.k@example.com"
    assert r_cv.confidence == 0.67
    assert r_li.confidence == 0.67
    assert r_cv.confidence_parts.agreement == 0.05
    assert r_li.confidence_parts.agreement == 0.05
    assert set(profile.personal_info.field_ids["emails"]) == {1, 2}
    assert not any(i.field_name in ("email", "emails") for i in result.review_items)


def test_phone_local_and_international_merge_to_one_phone():
    """4. "0790001234" and "+962 7 9000 1234": one phone."""
    r_cv = FieldRecord(
        field_id=1, source="1", entity="personal_info", entity_type="personal_info",
        field_name="phone", raw_value="0790001234", value="+962790001234",
        confidence=0.9, evidence="0790001234", page=1, evidence_status="verified",
        rule="N-PHONE-01", source_kind="cv", source_uploaded_at=OLDER,
    )
    r_li = FieldRecord(
        field_id=2, source="2", entity="personal_info", entity_type="personal_info",
        field_name="phone", raw_value="+962 7 9000 1234", value="+962790001234",
        confidence=0.9, evidence="+962 7 9000 1234", page=1, evidence_status="verified",
        rule="N-PHONE-01", source_kind="linkedin", source_uploaded_at=NEWER,
    )
    result = ProfileBuilder(confidence_threshold=0.6).build([r_cv, r_li])
    profile = result.profile
    assert profile is not None
    assert profile.personal_info.phones == ["+962790001234"]
    assert profile.personal_info.phone == "+962790001234"
    assert profile.personal_info.primary_phone == "+962790001234"
    assert set(profile.personal_info.field_ids["phones"]) == {1, 2}
    assert not any(i.field_name in ("phone", "phones") for i in result.review_items)


def test_city_still_conflicts_and_reaches_candidate_c05():
    """5. City still conflicts and reaches the candidate (C-05) when nothing decides it."""
    r_cv = FieldRecord(
        field_id=1, source="1", entity="personal_info", entity_type="personal_info",
        field_name="city", raw_value="Amman", value="Amman",
        confidence=0.9, evidence="Amman", page=1, evidence_status="verified",
        rule="llm_extraction", source_kind="cv", source_uploaded_at=OLDER,
    )
    r_li = FieldRecord(
        field_id=2, source="2", entity="personal_info", entity_type="personal_info",
        field_name="city", raw_value="Dubai", value="Dubai",
        confidence=0.9, evidence="Dubai", page=1, evidence_status="verified",
        rule="llm_extraction", source_kind="cv", source_uploaded_at=OLDER,
    )
    outcome = resolve_field([r_cv, r_li])
    assert not outcome.decided
    assert outcome.rule == ConflictRule.ASK_CANDIDATE
    assert outcome.ask == Fallback.CANDIDATE

    result = ProfileBuilder(confidence_threshold=0.6).build([r_cv, r_li])
    city_reviews = [i for i in result.review_items if i.field_name == "city"]
    assert len(city_reviews) == 1
    assert city_reviews[0].reasons == [ReviewReason.SOURCE_CONFLICT]
    assert "C-05" in city_reviews[0].message
    assert result.profile.personal_info.city is None

