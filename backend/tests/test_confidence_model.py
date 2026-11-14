"""The four-factor confidence model (FR-048, NFR-027, NFR-028).

    confidence = base x evidence x validation x mapping

A field's confidence used to be the number the language model reported about
its own answer. These tests pin the replacement: every score is computed from
checks that can be re-run, the model's number changes nothing, and a value
whose snippet is not in the document is dropped rather than scored low.

Each test names the arithmetic it expects, because the point of storing the
four parts is that a number can be argued with instead of trusted.
"""

from datetime import datetime, timezone

import pytest

from app.application.dto.cv_extraction import CVExtraction
from app.application.dto.extracted_document import ExtractedDocument
from app.application.services.field_record_builder import (
    FieldRecordBuilder,
    FieldRecordSettings,
)
from app.application.services.profile_builder import ProfileBuilder
from app.application.services.vetting_parser import VettingParser
from app.domain.entities.field_record import FieldRecord, ReviewReason
from app.domain.services.confidence import (
    AGREEMENT_BOOST,
    DEFAULT_REVIEW_CONFIDENCE,
    ConfidenceParts,
    ConfidenceRule,
    EvidenceGrade,
    apply_agreement_boost,
)
from app.domain.services.countries import CountryCatalog
from app.domain.services.dates import DateRule
from app.domain.services.skills import SkillRule
from app.infrastructure.reference_data import SEED_COUNTRIES, seed_skill_catalog

from tests.helpers import answer, f

# The limit the whole suite reads against, so a test never disagrees with the
# shipped default by accident (FR-046).
LIMIT = DEFAULT_REVIEW_CONFIDENCE


def build(document: ExtractedDocument, threshold: float = LIMIT, **overrides):
    """The extraction outcome for one document, with the real catalogs."""
    builder = FieldRecordBuilder(
        CountryCatalog(SEED_COUNTRIES), seed_skill_catalog(),
        FieldRecordSettings(confidence_threshold=threshold),
    )
    return builder.build(CVExtraction.model_validate(answer(**overrides)), document)


def text_document(text: str) -> ExtractedDocument:
    """A file with a text layer: nothing was recognised, so nothing is doubted."""
    return ExtractedDocument(source_name="cv.docx", text=text)


def scanned_document(text: str, confidence: float) -> ExtractedDocument:
    """A one-page scan the OCR engine scored ``confidence``."""
    return ExtractedDocument(
        source_name="scan.pdf", text=text, page_texts=[text],
        extraction_method="ocr", ocr_confidence=confidence,
        page_ocr_confidence=[confidence], page_text_layers=[""],
    )


def one(outcome, entity_type, field_name, value=None) -> FieldRecord:
    found = [r for r in outcome.records
             if r.entity_type == entity_type and r.field_name == field_name
             and (value is None or r.raw_value == value)]
    assert len(found) == 1, f"expected one {entity_type}.{field_name}, got {len(found)}"
    return found[0]


def personal(first_name=None, email=None, city=None, phone=None, **rest):
    """An answer holding only the personal fields a test cares about.

    The other entity lists are emptied: a test about one field should not also
    be asserting on the sample CV's default job and skills, whose snippets are
    not in the short text the test wrote.
    """
    return {"personal_info": {
        "first_name": first_name or f(), "last_name": f(), "email": email or f(),
        "phone": phone or f(), "city": city or f(), "country": f(),
        "title": f(), "summary": f(),
    }, "work_experience": [], "education": [], "skills": [], "certifications": [],
        "projects": [], "languages": [], "links": [], **rest}


def job(start, end, company="Zain Jordan", evidence=None):
    """An answer holding one job and nothing else."""
    return {"skills": [], "work_experience": [{
        "company": f(company), "title": f(), "location": f(),
        "start_date": f(start, evidence or f"{start} - {end}"),
        "end_date": f(end, evidence or f"{start} - {end}"),
        "is_current": f(False), "description": f(),
    }]}


# ---- 1. nothing to doubt ----

def test_a_text_page_quoted_exactly_scores_one():
    """Every factor neutral: 1.00 x 1.00 x 1.00 x 1.00."""
    outcome = build(text_document("Rana Odeh\nrana@example.com\n"),
                    **personal(first_name=f("Rana", "Rana Odeh")))
    record = one(outcome, "personal_info", "first_name")

    assert record.evidence_status == EvidenceGrade.VERIFIED
    assert record.confidence_parts == ConfidenceParts(1.0, 1.0, 1.0, 1.0)
    assert record.confidence == 1.0
    assert record.review_reasons == []


# ---- 2. a near quote ----

def test_a_snippet_with_a_stray_space_is_priced_not_rejected():
    """0.90 or better is a near quote: 1.00 x 0.85 = 0.85, still accepted."""
    text = "Rana Odeh\nrana.odeh@example.com | Amman\n"
    outcome = build(text_document(text),
                    **personal(email=f("rana.odeh@example.com",
                                       "rana.odeh @example.com")))
    record = one(outcome, "personal_info", "email")

    assert record.evidence_status == EvidenceGrade.VERIFIED_FUZZY
    assert record.confidence_parts.evidence == 0.85
    assert record.confidence == 0.85
    assert record.review_reasons == []


# ---- 3. a fuzzy table match ----

def test_a_corrected_skill_spelling_costs_the_mapping_factor():
    """N-SKILL-03: 1.00 x 1.00 x 1.00 x 0.85 = 0.85."""
    outcome = build(text_document("SKILLS\nPyhton, React\n"),
                    work_experience=[],
                    skills=[{"name": f("Pyhton")}, {"name": f("React")}])
    record = one(outcome, "skills", "name", "Pyhton")

    assert record.value == "Python"
    assert record.rule == SkillRule.FUZZY
    assert record.confidence_parts.mapping == 0.85
    assert record.confidence == 0.85
    assert record.review_reasons == []

    # The skill spelt correctly next to it pays nothing.
    assert one(outcome, "skills", "name", "React").confidence == 1.0


# ---- 4. a repair ----

def test_a_repaired_date_pair_costs_the_validation_factor():
    """N-DATE-05: the pair was the wrong way round, so 1.00 x 1.00 x 0.80 x 1.00."""
    text = "EXPERIENCE\nZain Jordan\n03/2024 - 03/2022\n"
    outcome = build(text_document(text), **job("03/2024", "03/2022"))

    start = one(outcome, "work_experience", "start_date")
    end = one(outcome, "work_experience", "end_date")

    assert start.rule == end.rule == DateRule.SWAPPED
    assert start.value == {"value": "2022-03", "precision": "month"}
    for record in (start, end):
        assert record.confidence_parts.validation == 0.80
        assert record.confidence == 0.80
        assert record.review_reasons == []


def test_an_ambiguous_date_costs_the_same_factor():
    """N-DATE-03: either part could be the month, so the month was dropped."""
    text = "EXPERIENCE\nZain Jordan\n04/05/2022 - 03/2024\n"
    outcome = build(text_document(text), **job("04/05/2022", "03/2024"))
    start = one(outcome, "work_experience", "start_date")

    assert start.rule == DateRule.AMBIGUOUS_ORDER
    assert start.value == {"value": "2022", "precision": "year"}
    assert start.confidence == 0.80


# ---- 5, 6, 9, 14. base: how readable the page was ----

def test_a_poor_scan_drags_an_exact_quote_down_to_its_own_score():
    """0.62 x 1.00 x 1.00 x 1.00 = 0.62, under the 0.65 limit."""
    outcome = build(scanned_document("Rana Odeh\nAmman\n", 0.62),
                    **personal(first_name=f("Rana", "Rana Odeh")))
    record = one(outcome, "personal_info", "first_name")

    assert record.confidence_parts.base == 0.62
    assert record.confidence == 0.62
    assert ReviewReason.LOW_CONFIDENCE in record.review_reasons


def test_a_good_scan_with_a_near_quote_stays_accepted():
    """0.80 x 0.85 = 0.68, which clears 0.65 — the case the limit is tuned for."""
    text = "Rana Odeh\nrana.odeh@example.com | Amman\n"
    outcome = build(scanned_document(text, 0.80),
                    **personal(email=f("rana.odeh@example.com",
                                       "rana.odeh @example.com", page=1)))
    record = one(outcome, "personal_info", "email")

    assert (record.confidence_parts.base, record.confidence_parts.evidence) == (0.80, 0.85)
    assert record.confidence == 0.68
    assert record.review_reasons == []


def test_the_models_own_confidence_changes_nothing():
    """A model reports the same certainty for a copied value and an invented
    one, so 0.99 from the model on a 0.50 scan is still 0.50."""
    outcome = build(scanned_document("Rana Odeh\nAmman\n", 0.50),
                    **personal(first_name=f("Rana", "Rana Odeh", confidence=0.99)))
    record = one(outcome, "personal_info", "first_name")

    assert record.model_confidence == 0.99       # kept for comparison only
    assert record.confidence == 0.50
    assert ReviewReason.LOW_CONFIDENCE in record.review_reasons


def test_a_value_on_a_text_page_is_not_punished_for_a_scan_elsewhere():
    """Per page, not per file: one scanned page must not make the readable
    pages look doubtful."""
    pages = ["Rana Odeh\nrana@example.com\n", "SKILLS\nReact\n"]
    document = ExtractedDocument(
        source_name="two-page.pdf", text="\n\n".join(pages), page_texts=pages,
        extraction_method="mixed", ocr_confidence=0.70,
        page_ocr_confidence=[None, 0.70],          # page 1 had a text layer
        page_text_layers=[pages[0], ""],
    )
    outcome = build(document, **personal(
        first_name=f("Rana", "Rana Odeh", page=1),
        skills=[{"name": f("React", "React", page=2)}]))

    record = one(outcome, "personal_info", "first_name")
    assert record.page == 1
    assert record.confidence_parts.base == 1.0
    assert record.confidence == 1.0

    # ... while a value on the scanned page is worth what that page scored.
    skill = one(outcome, "skills", "name", "React")
    assert skill.page == 2 and skill.confidence_parts.base == 0.70


def test_a_value_quoted_from_the_text_layer_of_a_mixed_page_keeps_full_base():
    """A page can hold both a text layer and a logo read by OCR. A value quoted
    from the text layer was never recognised, so it is not worth less."""
    layer = "Rana Odeh\nrana@example.com\n"
    document = ExtractedDocument(
        source_name="mixed.pdf", text=layer + "\nZAIN JORDAN\n",
        page_texts=[layer + "\nZAIN JORDAN\n"], extraction_method="mixed",
        ocr_confidence=0.55, page_ocr_confidence=[0.55], page_text_layers=[layer],
    )
    outcome = build(document, **personal(
        first_name=f("Rana", "Rana Odeh", page=1),
        work_experience=[{"company": f("Zain Jordan", "ZAIN JORDAN", page=1),
                          "title": f(), "location": f(), "start_date": f(),
                          "end_date": f(), "is_current": f(False), "description": f()}]))

    assert one(outcome, "personal_info", "first_name").confidence_parts.base == 1.0
    # The logo text was not in the layer, so it is scored as what it is.
    assert one(outcome, "work_experience", "company").confidence_parts.base == 0.55


# ---- 7. a weak quote ----

def test_a_weak_quote_on_a_text_page_scores_low_and_goes_to_review():
    """0.75 to 0.90 is recognisably the same span, worn: 1.00 x 0.60 = 0.60."""
    text = "Rana Odeh\nAmman, Jordan 11942\nrana.odeh@example.com\n"
    outcome = build(text_document(text),
                    **personal(city=f("Amman", "Amman, Jordan 11942 PO Box")))
    record = one(outcome, "personal_info", "city")

    assert record.evidence_status == EvidenceGrade.VERIFIED_WEAK
    assert record.confidence_parts.evidence == 0.60
    assert record.confidence == 0.60
    assert ReviewReason.LOW_CONFIDENCE in record.review_reasons


# ---- 8. not in the document at all ----

def test_a_snippet_that_is_not_in_the_text_is_rejected_not_queued():
    """R-03: a value that is not in the document is not a judgement call, so
    there is no field record and nobody is asked (NFR-028)."""
    outcome = build(text_document("Rana Odeh\nAmman, Jordan\n"),
                    **personal(city=f("Dubai", "Dubai, United Arab Emirates")))

    assert not [r for r in outcome.records if r.field_name == "city"]

    dropped = [r for r in outcome.rejected if r.field_name == "city"]
    assert len(dropped) == 1
    assert dropped[0].reason == ConfidenceRule.EVIDENCE_REJECTED
    assert dropped[0].raw_value == "Dubai"
    assert dropped[0].evidence == "Dubai, United Arab Emirates"
    assert "not in the source text" in dropped[0].detail

    built = ProfileBuilder().build(outcome.records)
    assert built.profile.personal_info.city is None
    assert not [i for i in built.review_items if i.field_name == "city"]


def test_a_value_its_own_snippet_does_not_support_is_rejected():
    """The snippet is in the text but says something else, which is the other
    way a value can fail to be in the document."""
    outcome = build(text_document("Rana Odeh\nAmman, Jordan 11942\n"),
                    **personal(city=f("Dubai", "Amman, Jordan 11942")))

    assert not [r for r in outcome.records if r.field_name == "city"]
    assert [r.reason for r in outcome.rejected if r.field_name == "city"] == \
        [ConfidenceRule.EVIDENCE_REJECTED]


def test_a_value_with_no_snippet_at_all_is_rejected():
    outcome = build(text_document("Rana Odeh\nAmman\n"),
                    **personal(city={"value": "Amman", "confidence": 0.9,
                                     "evidence": None, "page": None}))
    assert not [r for r in outcome.records if r.field_name == "city"]
    assert [r.field_name for r in outcome.rejected] == ["city"]


def test_a_value_the_source_does_not_state_is_still_a_record():
    """FR-026: a null is not a rejection. There was nothing to read, so there
    is nothing to doubt and nothing to quote."""
    outcome = build(text_document("Rana Odeh\n"), **personal())
    record = one(outcome, "personal_info", "city")

    assert record.value is None
    assert record.evidence_status == EvidenceGrade.NOT_REQUIRED
    assert record.confidence == 1.0
    assert outcome.rejected == []


# ---- 10, 11, 12. M-04: agreement between sources ----

OLDER = datetime(2024, 1, 1, tzinfo=timezone.utc)
NEWER = datetime(2026, 1, 1, tzinfo=timezone.utc)

_ids = iter(range(1, 10_000))


def record(value, *, source="1", confidence=0.62, field_name="company",
           entity_type="work_experience", entity=None, at=OLDER,
           reasons=None, parts=None) -> FieldRecord:
    return FieldRecord(
        field_id=next(_ids), source=source, entity=entity or f"{entity_type}[1]",
        entity_type=entity_type, field_name=field_name, raw_value=value, value=value,
        confidence=confidence, evidence="snippet", page=1,
        evidence_status=EvidenceGrade.VERIFIED, rule="llm_extraction",
        review_reasons=list(reasons if reasons is not None else [ReviewReason.LOW_CONFIDENCE]),
        source_kind="cv", source_uploaded_at=at,
        confidence_parts=parts or ConfidenceParts(base=confidence),
    )


def test_two_sources_agreeing_lift_a_value_over_the_limit():
    """Two scans of the same employer at 0.62 are worth more than either: the
    second file is evidence the first one did not have. 0.62 + 0.05 = 0.67."""
    records = [record("Zain Jordan", source="1"), record("Zain Jordan", source="2")]
    apply_agreement_boost(records, LIMIT)

    assert [r.confidence for r in records] == [0.67, 0.67]
    assert all(r.review_reasons == [] for r in records)
    # The stored parts still add up to the stored confidence.
    for r in records:
        assert r.confidence_parts.product + r.confidence_parts.agreement == r.confidence


def test_the_same_value_twice_in_one_source_is_not_agreement():
    """A CV repeating itself confirms nothing."""
    records = [record("Zain Jordan", source="1", entity="work_experience[1]"),
               record("Zain Jordan", source="1", entity="work_experience[2]")]
    apply_agreement_boost(records, LIMIT)

    assert [r.confidence for r in records] == [0.62, 0.62]
    assert all(r.review_reasons == [ReviewReason.LOW_CONFIDENCE] for r in records)


def test_three_sources_agreeing_add_the_boost_once():
    """The boost is for being confirmed, not for being popular."""
    records = [record("Zain Jordan", source=str(n)) for n in (1, 2, 3)]
    apply_agreement_boost(records, LIMIT)

    assert [r.confidence for r in records] == [0.67] * 3
    assert all(r.confidence_parts.agreement == AGREEMENT_BOOST for r in records)


def test_the_boost_is_built_on_the_best_reading_of_the_value():
    """Whichever record the conflict rules later pick, the profile value is the
    one two sources confirmed, so all of them carry that score."""
    records = [record("Zain Jordan", source="1", confidence=0.62),
               record("Zain Jordan", source="2", confidence=0.90, reasons=[])]
    apply_agreement_boost(records, LIMIT)

    assert [r.confidence for r in records] == [0.95, 0.95]


def test_the_boost_never_passes_one():
    records = [record("Zain Jordan", source=s, confidence=0.98, reasons=[])
               for s in ("1", "2")]
    apply_agreement_boost(records, LIMIT)
    assert [r.confidence for r in records] == [1.0, 1.0]


def test_agreement_does_not_clear_any_other_reason():
    """Two sources agreeing on what the page says is not agreement that the
    value is usable: an unknown skill is still unknown."""
    records = [record("Nagra", source=s, entity_type="skills", field_name="name",
                      reasons=[ReviewReason.UNKNOWN_SKILL]) for s in ("1", "2")]
    apply_agreement_boost(records, LIMIT)

    assert [r.confidence for r in records] == [0.67, 0.67]
    assert all(r.review_reasons == [ReviewReason.UNKNOWN_SKILL] for r in records)


def test_values_that_differ_are_not_agreement():
    records = [record("Zain Jordan", source="1"), record("Orange Jordan", source="2")]
    apply_agreement_boost(records, LIMIT)
    assert [r.confidence for r in records] == [0.62, 0.62]


def test_the_profile_keeps_a_value_two_sources_rescued():
    """End to end: the boost runs before the builder decides what is usable,
    which is the whole reason it is there."""
    records = [
        record("Zain Jordan", source="1", at=OLDER),
        record("Zain Jordan", source="2", at=NEWER),
        record("Sales Intern", source="1", field_name="title", at=OLDER),
        record("Sales Intern", source="2", field_name="title", at=NEWER),
    ]
    built = ProfileBuilder(confidence_threshold=LIMIT).build(
        records, include_field_reviews=False)

    assert len(built.profile.experience) == 1
    assert built.profile.experience[0].company == "Zain Jordan"
    assert built.review_items == []


# ---- 13. the platform's own data ----

def test_a_vetted_value_scores_one_on_every_factor():
    """There is no text layer to doubt, no snippet to match, no repair and no
    table lookup: the platform produced the value itself (FR-056)."""
    parsed = VettingParser(seed_skill_catalog()).parse(
        '{"skills": [{"name": "React", "level": 4}]}', "vetting.json")

    assert parsed.records
    for r in parsed.records:
        assert r.confidence == 1.0
        assert r.confidence_parts == ConfidenceParts(1.0, 1.0, 1.0, 1.0)
        assert r.model_confidence is None        # no model was asked


# ---- the limit itself (FR-046) ----

def test_the_shipped_review_limit_is_the_documented_one():
    """FR-046 names 0.65. Every default in the system reads from one place, so
    they cannot drift apart."""
    from app.core.config import settings
    from app.infrastructure.persistence.repositories.settings_repository import (
        DEFAULT_CONFIDENCE_THRESHOLD,
    )

    assert DEFAULT_REVIEW_CONFIDENCE == 0.65
    assert DEFAULT_CONFIDENCE_THRESHOLD == DEFAULT_REVIEW_CONFIDENCE
    assert FieldRecordSettings().confidence_threshold == DEFAULT_REVIEW_CONFIDENCE
    assert settings.REVIEW_CONFIDENCE_THRESHOLD == DEFAULT_REVIEW_CONFIDENCE


# ---- the parts are the explanation (FR-035, FR-048) ----

@pytest.mark.parametrize("parts, expected", [
    (ConfidenceParts(), 1.0),
    (ConfidenceParts(base=0.62), 0.62),
    (ConfidenceParts(base=0.80, evidence=0.85), 0.68),
    (ConfidenceParts(evidence=0.60), 0.60),
    (ConfidenceParts(validation=0.80), 0.80),
    (ConfidenceParts(mapping=0.85), 0.85),
    (ConfidenceParts(base=0.90, evidence=0.85, validation=0.80, mapping=0.85), 0.52),
])
def test_the_product_is_rounded_to_two_decimals(parts, expected):
    assert parts.product == expected
    assert parts.confidence == expected


def test_the_stored_parts_name_only_what_applied():
    """Four keys normally; the fifth appears only when sources agreed, so a
    reader can always add up what is written down."""
    assert set(ConfidenceParts(base=0.8).to_dict()) == {
        "base", "evidence", "validation", "mapping"}
    assert ConfidenceParts(base=0.62, agreement=0.05).to_dict()["agreement"] == 0.05


def test_every_built_record_can_explain_its_own_confidence():
    """The promise the parts exist to keep, over a whole document."""
    outcome = build(scanned_document(
        "Rana Odeh\nrana.odeh@example.com | Amman, Jordan 11942\n"
        "EXPERIENCE\nSales Intern, Zain Jordan\nJune 2023 - Present\n"
        "SKILLS\nreactjs, Nagra\n", 0.88))

    assert outcome.records
    for r in outcome.records:
        assert r.confidence_parts is not None, r.field_name
        assert r.confidence == r.confidence_parts.confidence, r.field_name
