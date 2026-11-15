"""Schema validation (FR-022, FR-025) and evidence checks (FR-065, NFR-028)."""

from app.application.services.evidence_checker import EvidenceChecker
from app.application.services.llm_output_validator import validate_llm_output
from tests.helpers import answer, as_json, f


def test_valid_answer_passes():
    result = validate_llm_output(as_json(answer()))
    assert result.is_valid, result.errors
    assert result.dropped_fields == []


def test_not_json_is_invalid():
    result = validate_llm_output("Sure! Here is the profile: {")
    assert not result.is_valid
    assert "not valid JSON" in result.errors[0]


def test_disallowed_fields_are_dropped_and_reported():
    data = answer()
    data["gender"] = f("female")                       # protected trait
    data["personal_info"]["date_of_birth"] = f("1999")
    data["skills"][0]["level"] = 5
    result = validate_llm_output(as_json(data))
    assert result.is_valid
    assert set(result.dropped_fields) == {
        "gender", "personal_info.date_of_birth", "skills[0].level"}


def test_missing_required_field_is_invalid():
    data = answer()
    del data["personal_info"]["emails"]
    result = validate_llm_output(as_json(data))
    assert not result.is_valid
    assert any("personal_info.emails" in e for e in result.errors)


def test_wrong_type_and_out_of_range_confidence_are_invalid():
    data = answer()
    data["personal_info"]["first_name"]["confidence"] = 1.7
    data["languages"] = [{"name": f("English"), "proficiency": f("expert")}]
    result = validate_llm_output(as_json(data))
    assert not result.is_valid
    assert len(result.errors) >= 2


def test_null_value_loses_evidence():
    data = answer()
    data["personal_info"]["phones"] = [{"value": None, "confidence": 1,
                                        "evidence": "invented", "page": 1}]
    result = validate_llm_output(as_json(data))
    assert result.extraction.personal_info.phones[0].evidence is None


TEXT = "SARA YOUSEF\nsara.yousef@example.com ● Ramallah, Palestine\nWaiter  06/2012 - 03/2017"


def test_evidence_found_ignoring_case_spacing_and_bullets():
    checker = EvidenceChecker(TEXT)
    assert checker.check("Sara", "Sara Yousef", None).ok
    assert checker.check("Ramallah", "sara.yousef@example.com • Ramallah", None).ok


def test_evidence_not_in_text_is_rejected():
    check = EvidenceChecker(TEXT).check("Dubai", "Dubai, UAE", None)
    assert check.status == "not_found" and not check.ok


def test_value_must_be_supported_by_its_evidence():
    check = EvidenceChecker(TEXT).check("Amman", "Ramallah, Palestine", None)
    assert check.status == "verified" and not check.value_supported


def test_missing_evidence():
    assert EvidenceChecker(TEXT).check("Sara", None, None).status == "missing"


def test_a_near_quote_is_graded_on_every_page_not_only_a_scan():
    """A model drops a comma or straightens a dash on any page, and rejecting
    those values lost correct data. The difference is priced instead: the grade
    becomes the `evidence` confidence factor."""
    ocr_text = "Boeing 737 FNPT Il simulator (40 hours)"
    snippet = "Boeing 737 FNPT II simulator (40 hours)"
    check = EvidenceChecker(ocr_text).check(None, snippet, None)
    assert check.status == "verified_fuzzy"
    assert check.similarity >= 0.90 and check.factor == 0.85


def test_a_worn_quote_is_kept_at_a_lower_grade():
    long_text = "Rana Odeh | Amman, Jordan 11942 | rana.odeh@example.com"
    check = EvidenceChecker(long_text).check("Amman", "Amman, Jordan 11942 PO Box", None)
    assert check.status == "verified_weak"
    assert 0.75 <= check.similarity < 0.90 and check.factor == 0.60


def test_a_snippet_mostly_absent_from_the_text_is_rejected():
    """Under 0.75 the snippet is not really in the document, which no score can
    express, so the value is dropped under R-03 instead (NFR-028)."""
    check = EvidenceChecker(TEXT).check("Dubai", "Dubai, United Arab Emirates", None)
    assert check.status == "not_found"
    assert check.similarity < 0.75 and not check.ok


def test_page_is_corrected_to_where_snippet_is():
    pages = ["intro A", "Waiter at Bella Napoli"]
    checker = EvidenceChecker("\n\n".join(pages), page_texts=pages)
    assert checker.check("Bella Napoli", "Waiter at Bella Napoli", page=1).page == 2
