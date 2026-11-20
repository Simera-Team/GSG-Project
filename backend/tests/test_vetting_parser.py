"""Vetting results parsed without an LLM (FR-056, FR-057).

The vetting table existed but nothing filled it, so no vetted field record was
ever created and the rule that prefers a vetted value (FR-032, C-01) could
never fire. These tests cover the parser that closes that loop.
"""

import json

import pytest

from app.application.services.vetting_parser import (
    VettingParser,
    VettingPayloadError,
)
from app.domain.entities.field_record import ReviewReason
from app.infrastructure.reference_data import seed_skill_catalog


@pytest.fixture
def parser():
    return VettingParser(seed_skill_catalog())


def payload(**parts) -> str:
    return json.dumps(parts)


# ---- skills ----

def test_vetted_skill_becomes_a_record_and_a_vetting_row(parser):
    result = parser.parse(payload(skills=[{"name": "React", "level": 4}]), "vet.json")
    assert [s.skill_name for s in result.skills] == ["React"]
    assert [s.level for s in result.skills] == [4]
    assert not result.errors


def test_vetted_records_are_marked_as_coming_from_vetting(parser):
    """The kind is what the conflict rules read for C-01."""
    result = parser.parse(payload(skills=[{"name": "Python", "level": 5}]), "vet.json")
    assert all(r.source_kind == "vetting" for r in result.records)


def test_vetted_values_are_certain(parser):
    """The platform produced the value itself: there is nothing to doubt."""
    result = parser.parse(payload(skills=[{"name": "Docker", "level": 3}]), "vet.json")
    assert all(r.confidence == 1.0 for r in result.records)


def test_skill_alias_is_mapped_to_the_standard_name(parser):
    result = parser.parse(payload(skills=[{"name": "postgres", "level": 3}]), "vet.json")
    assert [s.skill_name for s in result.skills] == ["PostgreSQL"]


@pytest.mark.parametrize("level", [0, 6, -1, None, "four", 1.5])
def test_level_outside_one_to_five_is_rejected(parser, level):
    """FR-056: a level outside 1 to 5 is rejected."""
    result = parser.parse(payload(skills=[{"name": "React", "level": level}]), "vet.json")
    assert result.skills == []
    assert result.errors
    assert any(ReviewReason.INVALID_FORMAT in r.review_reasons for r in result.records)


def test_the_skill_survives_an_unusable_level(parser):
    """The candidate does have the skill; only its level is unusable."""
    result = parser.parse(payload(skills=[{"name": "React", "level": 9}]), "vet.json")
    assert any(r.value == "React" for r in result.records)


def test_unknown_skill_is_queued_not_stored(parser):
    """FR-056 / FR-062: no skill is lost and none is silently accepted."""
    result = parser.parse(
        payload(skills=[{"name": "Nonexistent Framework", "level": 4}]), "vet.json")
    assert result.skills == []
    assert any(ReviewReason.UNKNOWN_SKILL in r.review_reasons for r in result.records)


def test_a_skill_entry_without_a_name_is_an_error(parser):
    result = parser.parse(payload(skills=[{"level": 4}]), "vet.json")
    assert result.errors and result.records == []


# ---- languages ----

def test_language_proficiency_word_is_kept(parser):
    result = parser.parse(
        payload(languages=[{"name": "English", "proficiency": "fluent"}]), "vet.json")
    values = {r.field_name: r.value for r in result.records}
    assert values["name"] == "English" and values["proficiency"] == "fluent"


def test_language_level_is_mapped_onto_the_proficiency_vocabulary(parser):
    result = parser.parse(payload(languages=[{"name": "Arabic", "level": 5}]), "vet.json")
    assert {r.field_name: r.value for r in result.records}["proficiency"] == "native"


def test_unusable_language_proficiency_is_flagged(parser):
    result = parser.parse(
        payload(languages=[{"name": "French", "proficiency": "quite good"}]), "vet.json")
    assert any(ReviewReason.INVALID_FORMAT in r.review_reasons for r in result.records)


# ---- payload shape ----

@pytest.mark.parametrize("raw", ["not json", "[]", '"a string"', '{"skills": 5}'])
def test_a_payload_that_is_not_a_vetting_result_is_rejected(parser, raw):
    with pytest.raises(VettingPayloadError):
        parser.parse(raw, "vet.json")


def test_an_empty_payload_is_valid_and_produces_nothing(parser):
    result = parser.parse("{}", "vet.json")
    assert result.records == [] and result.skills == [] and result.errors == []


def test_unknown_keys_are_ignored_not_guessed_at(parser):
    result = parser.parse(
        payload(skills=[{"name": "React", "level": 4}], gender="female", age=30),
        "vet.json")
    # FR-025: a protected trait has no field to land in and is simply ignored.
    assert {r.field_name for r in result.records} == {"name"}


def test_parsing_is_deterministic(parser):
    raw = payload(skills=[{"name": "React", "level": 4}, {"name": "Go", "level": 2}])
    first = [(s.skill_name, s.level) for s in parser.parse(raw, "v").skills]
    for _ in range(10):
        again = VettingParser(seed_skill_catalog()).parse(raw, "v")
        assert [(s.skill_name, s.level) for s in again.skills] == first
