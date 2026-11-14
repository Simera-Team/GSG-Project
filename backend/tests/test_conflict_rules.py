"""Conflict resolution when sources disagree (FR-031 to FR-034).

Before this, any disagreement between two sources went straight to a human.
These tests pin the order the requirements ask for: a vetted value wins, then
the newer source, then source priority, and only what is left reaches a
person.
"""

from datetime import datetime, timezone

import pytest

from app.domain.entities.field_record import FieldRecord
from app.domain.services.conflict_rules import (
    ConflictRule,
    Fallback,
    policy_for,
    resolve_field,
)

OLDER = datetime(2024, 1, 1, tzinfo=timezone.utc)
NEWER = datetime(2026, 1, 1, tzinfo=timezone.utc)


def record(value, *, kind="cv", at=OLDER, entity_type="personal_info",
           field_name="city", field_id=1, source="1"):
    return FieldRecord(
        field_id=field_id, source=source, entity=entity_type,
        entity_type=entity_type, field_name=field_name, raw_value=value,
        value=value, confidence=0.9, evidence="snippet", page=1,
        evidence_status="verified", rule="llm_extraction",
        source_kind=kind, source_uploaded_at=at,
    )


# ---- no conflict at all ----

def test_a_single_value_needs_no_rule():
    outcome = resolve_field([record("Amman")])
    assert outcome.decided and outcome.winner.value == "Amman"
    assert outcome.rule == ConflictRule.AGREED


def test_sources_that_agree_are_not_a_conflict():
    """Case and spacing differences are not disagreements."""
    outcome = resolve_field([record("Amman"), record("  amman ", field_id=2)])
    assert outcome.decided and outcome.rule == ConflictRule.AGREED


def test_empty_values_are_ignored():
    assert resolve_field([record(None), record(None, field_id=2)]).winner is None


# ---- C-01: a vetted value wins (FR-032) ----

def test_vetted_value_beats_a_self_reported_one():
    """FR-032: vetted Node level 4/5 is used, whatever the CV claims."""
    outcome = resolve_field([
        record("intermediate", kind="cv", at=NEWER,
               entity_type="languages", field_name="proficiency"),
        record("fluent", kind="vetting", at=OLDER, field_id=2,
               entity_type="languages", field_name="proficiency"),
    ])
    assert outcome.decided
    assert outcome.rule == ConflictRule.VETTED_WINS
    assert outcome.winner.value == "fluent"


def test_vetting_beats_recency_even_when_older():
    """Recency must never override a vetted value."""
    outcome = resolve_field([
        record("Dubai", kind="cv", at=NEWER),
        record("Amman", kind="vetting", at=OLDER, field_id=2),
    ])
    assert outcome.winner.value == "Amman"
    assert outcome.rule == ConflictRule.VETTED_WINS


def test_two_vetting_results_that_disagree_go_to_a_person():
    """No rule should pick between two vetted values."""
    outcome = resolve_field([
        record("Amman", kind="vetting", at=OLDER),
        record("Dubai", kind="vetting", at=OLDER, field_id=2),
    ])
    assert not outcome.decided and outcome.ask is not None


# ---- C-02: the newer source wins, where the policy allows it (FR-031) ----

def test_newer_source_wins_for_a_recency_field():
    """FR-031: end date 2022 vs 2024 gives 2024."""
    outcome = resolve_field([
        record({"value": "2022", "precision": "year"}, at=OLDER,
               entity_type="work_experience", field_name="end_date"),
        record({"value": "2024", "precision": "year"}, at=NEWER, field_id=2,
               entity_type="work_experience", field_name="end_date"),
    ])
    assert outcome.decided
    assert outcome.rule == ConflictRule.NEWER_WINS
    assert outcome.winner.value["value"] == "2024"


def test_recency_never_decides_a_field_whose_policy_forbids_it():
    """FR-031: "recency never decides a skill level". A degree is the same
    kind of claim: a newer file does not make it truer."""
    outcome = resolve_field([
        record("BSc", at=OLDER, entity_type="education", field_name="degree"),
        record("MSc", at=NEWER, field_id=2,
               entity_type="education", field_name="degree"),
    ])
    assert not outcome.decided
    assert outcome.rule == ConflictRule.ASK_REVIEWER


def test_source_priority_never_decides_a_field_whose_policy_forbids_it():
    """A degree level: one of the two claims is simply wrong, and preferring
    the kind of file it arrived in does not tell anyone which. Both rungs are
    off for this field, so it reaches a reviewer with both values (FR-033)."""
    outcome = resolve_field([
        record("BSc", kind="cv", at=OLDER,
               entity_type="education", field_name="degree"),
        record("MSc", kind="linkedin", at=NEWER, field_id=2,
               entity_type="education", field_name="degree"),
    ])
    assert not outcome.decided
    assert outcome.rule == ConflictRule.ASK_REVIEWER
    assert {r.value for r in outcome.others} == {"BSc", "MSc"}


def test_a_vetted_value_still_wins_where_source_priority_is_off():
    """C-01 runs above C-03, so switching priority off must not reach it."""
    outcome = resolve_field([
        record("BSc", kind="cv", at=NEWER,
               entity_type="education", field_name="degree"),
        record("MSc", kind="vetting", at=OLDER, field_id=2,
               entity_type="education", field_name="degree"),
    ])
    assert outcome.decided
    assert outcome.rule == ConflictRule.VETTED_WINS
    assert outcome.winner.value == "MSc"


def test_same_upload_time_does_not_let_recency_decide():
    outcome = resolve_field([
        record("Amman", kind="cv", at=OLDER),
        record("Dubai", kind="cv", at=OLDER, field_id=2),
    ])
    assert not outcome.decided


# ---- C-04: a precision difference is not a conflict ----

def test_the_more_precise_date_is_kept_without_asking_anyone():
    """"2022-03" and "2022" are one date known to two accuracies (FR-028)."""
    outcome = resolve_field([
        record({"value": "2022", "precision": "year"}, at=NEWER,
               entity_type="work_experience", field_name="start_date"),
        record({"value": "2022-03", "precision": "month"}, at=OLDER, field_id=2,
               entity_type="work_experience", field_name="start_date"),
    ])
    assert outcome.decided
    assert outcome.rule == ConflictRule.MORE_PRECISE
    assert outcome.winner.value["value"] == "2022-03"


def test_genuinely_different_dates_are_still_a_conflict():
    outcome = resolve_field([
        record({"value": "2019", "precision": "year"}, at=OLDER,
               entity_type="education", field_name="end_date"),
        record({"value": "2022-03", "precision": "month"}, at=OLDER, field_id=2,
               entity_type="education", field_name="end_date"),
    ])
    assert outcome.rule != ConflictRule.MORE_PRECISE


# ---- C-03: source priority breaks a remaining tie ----

def test_source_priority_breaks_a_tie_when_recency_cannot():
    """A name comes from the CV first; a stale LinkedIn headline does not
    overrule what the candidate wrote deliberately."""
    outcome = resolve_field([
        record("Nada", kind="cv", at=OLDER, field_name="first_name"),
        record("N.", kind="linkedin", at=NEWER, field_id=2,
               field_name="first_name"),
    ])
    assert outcome.decided
    assert outcome.rule == ConflictRule.SOURCE_PRIORITY
    assert outcome.winner.value == "Nada"


# ---- C-05 / C-06: who gets asked (FR-033) ----

def test_an_undecided_personal_detail_is_asked_of_the_candidate():
    """FR-033: city "Amman" vs "Dubai" keeps both values and their sources."""
    outcome = resolve_field([
        record("Amman", kind="cv", at=OLDER),
        record("Dubai", kind="cv", at=OLDER, field_id=2, source="2"),
    ])
    assert outcome.rule == ConflictRule.ASK_CANDIDATE
    assert outcome.ask == Fallback.CANDIDATE
    assert {r.value for r in outcome.others} == {"Amman", "Dubai"}


def test_an_undecided_claim_is_asked_of_a_reviewer():
    outcome = resolve_field([
        record("BSc Physics", at=OLDER, entity_type="education", field_name="field"),
        record("BSc Maths", at=OLDER, field_id=2,
               entity_type="education", field_name="field"),
    ])
    assert outcome.rule == ConflictRule.ASK_REVIEWER


def test_no_value_is_ever_auto_picked_when_no_rule_decides():
    """FR-033: never auto-pick an unsupported value."""
    outcome = resolve_field([
        record("Amman", at=OLDER), record("Dubai", at=OLDER, field_id=2),
    ])
    assert outcome.winner is None


# ---- the policy table is the FR-031 "list kept in code configuration" ----

@pytest.mark.parametrize("entity_type, field_name, recency", [
    ("work_experience", "end_date", True),
    ("personal_info", "title", True),
    ("education", "degree", False),
    ("personal_info", "first_name", False),
    ("languages", "proficiency", False),
])
def test_recency_is_allowed_only_where_the_table_says_so(entity_type, field_name, recency):
    assert policy_for(entity_type, field_name).recency is recency


@pytest.mark.parametrize("entity_type, field_name, priority", [
    ("education", "degree", False),
    ("education", "field", True),
    ("personal_info", "first_name", True),
    ("work_experience", "company", True),
])
def test_source_priority_is_allowed_only_where_the_table_says_so(
        entity_type, field_name, priority):
    assert policy_for(entity_type, field_name).priority is priority


def test_an_unlisted_field_falls_back_to_the_safe_default():
    """A field nobody thought about must not silently auto-pick a value."""
    policy = policy_for("projects", "something_new")
    assert policy.fallback == Fallback.REVIEWER
    assert policy.recency is True and policy.priority is True


# ---- determinism (FR-034, NFR-023) ----

def test_the_same_records_always_give_the_same_answer():
    records = [
        record("Amman", kind="cv", at=OLDER),
        record("Dubai", kind="linkedin", at=NEWER, field_id=2),
    ]
    first = resolve_field(records)
    for _ in range(20):
        again = resolve_field(records)
        assert again.rule == first.rule
        assert (again.winner.value if again.winner else None) == \
               (first.winner.value if first.winner else None)
