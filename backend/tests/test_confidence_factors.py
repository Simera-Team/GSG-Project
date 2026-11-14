"""Confidence factors applied while building field records.

Two rules reach a value that is right but less certain than an exact read: a
corrected spelling (N-SKILL-03) and a date whose day/month order was
ambiguous (N-DATE-03). Neither sends the field to a person — the lost
certainty shows up as a lower confidence instead, which is also what decides
whether the review limit catches it.
"""

import pytest

from app.application.dto.cv_extraction import CVExtraction
from app.application.dto.extracted_document import ExtractedDocument
from app.application.services.field_record_builder import (
    AMBIGUOUS_DATE_VALIDATION_FACTOR,
    FieldRecordBuilder,
    FieldRecordSettings,
)
from app.domain.entities.field_record import ReviewReason
from app.domain.services.countries import CountryCatalog
from app.domain.services.skills import FUZZY_MAPPING_FACTOR, SkillRule
from app.infrastructure.reference_data import SEED_COUNTRIES, seed_skill_catalog

from tests.helpers import answer, f


def build(text: str, threshold: float = 0.65, **overrides):
    """Field records for one document, built with the real catalogs."""
    builder = FieldRecordBuilder(
        CountryCatalog(SEED_COUNTRIES), seed_skill_catalog(),
        FieldRecordSettings(confidence_threshold=threshold),
    )
    document = ExtractedDocument(source_name="cv.pdf", text=text)
    return builder.build(CVExtraction.model_validate(answer(**overrides)), document)


def one(records, entity_type, field_name, value=None):
    """The single record for a field, optionally the one holding ``value``."""
    found = [r for r in records
             if r.entity_type == entity_type and r.field_name == field_name
             and (value is None or r.raw_value == value)]
    assert len(found) == 1, f"expected one {entity_type}.{field_name}, got {len(found)}"
    return found[0]


# ---- N-SKILL-03: a corrected spelling is mapped, with its mapping factor ----

SKILL_TEXT = "SKILLS\nPostgress, PostgreSQL, Nagra\n"


def misspelt(confidence=1.0):
    return {"skills": [
        {"name": f("Postgress", "Postgress", confidence=confidence)},
        {"name": f("PostgreSQL", "PostgreSQL", confidence=confidence)},
        {"name": f("Nagra", "Nagra", confidence=confidence)},
    ]}


def test_misspelt_skill_is_mapped_and_not_sent_to_review():
    records = build(SKILL_TEXT, **misspelt())
    skill = one(records, "skills", "name", "Postgress")
    assert skill.value == "PostgreSQL"
    assert skill.rule == SkillRule.FUZZY
    assert ReviewReason.UNKNOWN_SKILL not in skill.review_reasons


def test_a_corrected_spelling_carries_the_mapping_factor():
    records = build(SKILL_TEXT, **misspelt())
    skill = one(records, "skills", "name", "Postgress")
    assert skill.confidence == pytest.approx(FUZZY_MAPPING_FACTOR)


def test_an_exact_skill_keeps_its_full_confidence():
    records = build(SKILL_TEXT, **misspelt())
    skill = one(records, "skills", "name", "PostgreSQL")
    assert skill.value == "PostgreSQL"
    assert skill.confidence == pytest.approx(1.0)


def test_a_skill_matching_nothing_still_goes_to_review():
    """R-09: fuzzy matching narrows what reaches a person; it does not empty
    the queue."""
    records = build(SKILL_TEXT, **misspelt())
    skill = one(records, "skills", "name", "Nagra")
    assert skill.rule == SkillRule.UNKNOWN
    assert ReviewReason.UNKNOWN_SKILL in skill.review_reasons


def test_the_mapping_factor_can_push_a_weak_value_under_the_limit():
    """A spelling correction on an already-uncertain read is what the limit is
    there to catch: 0.70 * 0.85 = 0.595, below 0.65."""
    records = build(SKILL_TEXT, threshold=0.65, **misspelt(confidence=0.70))
    skill = one(records, "skills", "name", "Postgress")
    assert skill.value == "PostgreSQL"
    assert ReviewReason.LOW_CONFIDENCE in skill.review_reasons


# ---- N-DATE-03: an ambiguous date keeps the year, with its factor ----

DATE_TEXT = "EXPERIENCE\nSales Intern, Zain Jordan\n04/05/2022 - 03/2024\n"


def dated(start, end):
    return {"work_experience": [{
        "company": f("Zain Jordan"), "title": f("Sales Intern"), "location": f(),
        "start_date": f(start, f"{start} - {end}"),
        "end_date": f(end, f"{start} - {end}"),
        "is_current": f(False), "description": f(),
    }]}


def test_ambiguous_date_keeps_the_year_without_a_review_item():
    records = build(DATE_TEXT, **dated("04/05/2022", "03/2024"))
    start = one(records, "work_experience", "start_date")
    assert start.value == {"value": "2022", "precision": "year"}
    assert start.review_reasons == []


def test_an_ambiguous_date_carries_the_validation_factor():
    records = build(DATE_TEXT, **dated("04/05/2022", "03/2024"))
    start = one(records, "work_experience", "start_date")
    assert start.confidence == pytest.approx(
        0.95 * AMBIGUOUS_DATE_VALIDATION_FACTOR)


def test_an_unambiguous_date_keeps_its_full_confidence():
    records = build("EXPERIENCE\n03/2022 - 03/2024\n", **dated("03/2022", "03/2024"))
    start = one(records, "work_experience", "start_date")
    assert start.value == {"value": "2022-03", "precision": "month"}
    assert start.confidence == pytest.approx(0.95)


def test_an_unreadable_date_still_goes_to_review():
    """Dropping a guessable month is not the same as dropping a date nobody
    can read."""
    records = build("EXPERIENCE\nsoon - 03/2024\n", **dated("soon", "03/2024"))
    start = one(records, "work_experience", "start_date")
    assert ReviewReason.UNPARSEABLE_DATE in start.review_reasons
