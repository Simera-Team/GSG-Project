"""Entity matching across sources (M-01) and the conflict ladder inside entities.

Before this, the profile builder de-duplicated entities on exact field tuples,
so "Google" in a CV and "Google LLC" on LinkedIn stayed two separate jobs and
their fields never met: the ``C-`` ladder only ever ran on personal details.
These tests pin what counts as the same entity, what deliberately does not,
and that the answer never depends on the order the records arrive in.
"""

import random
from datetime import datetime, timezone

import pytest

from app.application.services.profile_builder import ProfileBuilder
from app.domain.entities.field_record import FieldRecord, ReviewReason
from app.domain.services.conflict_rules import ConflictRule
from app.domain.services.entity_matching import (
    MatchRule,
    company_key,
    institution_key,
    match_entities,
)

CV = ("1", "cv", datetime(2024, 1, 1, tzinfo=timezone.utc))
LINKEDIN = ("2", "linkedin", datetime(2026, 1, 1, tzinfo=timezone.utc))
NEWEST = ("3", "cv", datetime(2026, 6, 1, tzinfo=timezone.utc))

_ids = iter(range(1, 10_000))


def date(value: str | None):
    """A normalised date record value: "2022" or "2022-03"; None for nothing."""
    if value is None:
        return None
    return {"value": value, "precision": "month" if "-" in value else "year"}


def entity(source, entity_type, index, **fields) -> list[FieldRecord]:
    """The field records of one entity as one source describes it."""
    source_id, kind, uploaded_at = source
    return [
        FieldRecord(
            field_id=next(_ids), source=source_id,
            entity=f"{entity_type}[{index}]", entity_type=entity_type,
            field_name=name, raw_value=value, value=value, confidence=0.95,
            evidence="snippet", page=1, evidence_status="verified",
            rule="llm_extraction", source_kind=kind, source_uploaded_at=uploaded_at,
        )
        for name, value in fields.items() if value is not None
    ]


def job(source, index, company, title=None, start=None, end=None, **extra):
    return entity(source, "work_experience", index, company=company, title=title,
                  start_date=date(start), end_date=end if end == "current" else date(end),
                  **extra)


def study(source, index, institution, degree=None, field=None, start=None, end=None):
    return entity(source, "education", index, institution=institution, degree=degree,
                  field=field, start_date=date(start), end_date=date(end))


def groups_of(records, entity_type):
    return match_entities(records).of_type(entity_type)


def build(records):
    """The profile the builder makes of these records, plus its review items."""
    return ProfileBuilder().build(records, include_field_reviews=False)


# ---- the company key (FR-034: a fixed rule, not a guess) ----

def test_a_company_key_ignores_case_punctuation_and_legal_form():
    assert company_key("Google LLC") == "google"
    assert company_key("google, inc.") == "google"
    assert company_key("Google") == "google"
    assert company_key("Google L.L.C") == "google"
    assert company_key("The Walt Disney Company") == "walt disney"
    assert company_key("Infosys Pvt Ltd") == "infosys"


def test_a_company_whose_whole_name_is_a_legal_form_keeps_it():
    """Stripping must never leave nothing to compare."""
    assert company_key("Ltd") == "ltd"


def test_different_companies_keep_different_keys():
    assert company_key("Google") != company_key("Apple")


# ---- 1. the same company spelt two ways is one job ----

def test_google_and_google_llc_with_overlapping_dates_are_one_job():
    records = (
        job(CV, 1, "Google", "Engineer", start="2020-01", end="2023-01")
        + job(LINKEDIN, 1, "Google LLC", "Senior Engineer", start="2020-01", end="2023-01")
    )
    matched = groups_of(records, "work_experience")

    assert len(matched) == 1
    assert matched[0].merged
    assert matched[0].sources == ("1", "2")

    built = build(records)
    assert len(built.profile.experience) == 1
    row = built.profile.experience[0]
    # FR-063: every field record that fed the entity is kept, from both sources.
    assert row.field_ids == sorted(r.field_id for r in records)
    assert row.rule == MatchRule.SAME_ENTITY
    # The title was never part of the match; C-02 settles it from the newer source.
    assert row.title == "Senior Engineer"


# ---- 2. a promotion is two jobs ----

def test_the_same_company_over_two_separate_spells_stays_two_jobs():
    """Non-overlapping dates at one employer are a promotion, not a duplicate."""
    records = (
        job(CV, 1, "Google", "Engineer", start="2018-01", end="2019-12")
        + job(LINKEDIN, 1, "Google LLC", "Director", start="2022-01", end="2024-01")
    )
    matched = groups_of(records, "work_experience")

    assert len(matched) == 2
    assert all(not group.merged for group in matched)
    assert len(build(records).profile.experience) == 2


# ---- 3. one source listing a company twice lists two jobs ----

def test_two_jobs_at_one_company_in_one_source_are_never_merged():
    records = (
        job(CV, 1, "Google", "Engineer", start="2020-01", end="2022-01")
        + job(CV, 2, "Google LLC", "Engineer", start="2020-01", end="2022-01")
    )
    matched = groups_of(records, "work_experience")

    assert len(matched) == 2
    assert [len(group.members) for group in matched] == [1, 1]
    assert len(build(records).profile.experience) == 2


# ---- 4. dates that are not stated cannot rule a match out ----

def test_a_source_with_no_dates_matches_on_the_company_alone():
    records = (
        job(CV, 1, "Google")
        + job(LINKEDIN, 1, "Google LLC", "Engineer", start="2020-01", end="2023-01")
    )
    matched = groups_of(records, "work_experience")

    assert len(matched) == 1 and matched[0].merged


def test_an_open_ended_span_still_has_to_overlap():
    """A role running from 2023 is not the role that ended in 2019."""
    records = (
        job(CV, 1, "Google", start="2016-01", end="2019-01")
        + job(LINKEDIN, 1, "Google", start="2023-01", end="current")
    )
    assert len(groups_of(records, "work_experience")) == 2


# ---- 5. two equally good candidates are not a match ----

def test_an_entity_matching_two_others_is_kept_separate_and_reviewed():
    """Picking one of two candidates would be a guess (R-10)."""
    records = (
        job(CV, 1, "Google", "Engineer", start="2018-01", end="2019-12")
        + job(CV, 2, "Google", "Director", start="2022-01", end="2024-01")
        # Spans both CV jobs, so it could be either one.
        + job(LINKEDIN, 1, "Google LLC", "Engineer", start="2018-01", end="2024-01")
    )
    matched = groups_of(records, "work_experience")

    assert len(matched) == 3
    assert all(not group.merged for group in matched)

    ambiguous = [group for group in matched if group.ambiguous_with]
    assert len(ambiguous) == 1
    assert ambiguous[0].entity_id == "2:work_experience[1]"
    assert ambiguous[0].ambiguous_ids == ("1:work_experience[1]", "1:work_experience[2]")

    built = build(records)
    items = [i for i in built.review_items
             if ReviewReason.ENTITY_MATCH_AMBIGUOUS in i.reasons]
    assert len(items) == 1
    assert len(items[0].options) == 2
    assert len(built.profile.experience) == 3


# ---- 6. "present" against a stated end date ----

def test_an_end_date_against_present_is_one_job_settled_by_recency():
    records = (
        job(CV, 1, "Google", "Engineer", start="2020-01", end="2022-01")
        + job(LINKEDIN, 1, "Google", "Engineer", start="2020-01", end="current")
    )
    matched = groups_of(records, "work_experience")
    assert len(matched) == 1 and matched[0].merged

    built = build(records)
    assert len(built.profile.experience) == 1
    row = built.profile.experience[0]
    # C-02: the newer source says the role is ongoing, so it is.
    assert row.employment_status == "current"
    assert row.end_date is None
    winner = next(r for r in records
                  if r.field_name == "end_date" and r.source == "2")
    assert winner.rule == ConflictRule.NEWER_WINS


# ---- 7. a precision difference is not a conflict ----

def test_a_year_and_a_year_month_start_keep_the_more_precise_one():
    records = (
        job(CV, 1, "Google", "Engineer", start="2022", end="2024-01")
        + job(LINKEDIN, 1, "Google", "Engineer", start="2022-03", end="2024-01")
    )
    assert len(groups_of(records, "work_experience")) == 1

    built = build(records)
    row = built.profile.experience[0]
    # C-04 keeps the month even though the year came from the newer source.
    assert (row.start_date.value, row.start_date.precision) == ("2022-03", "month")
    winner = next(r for r in records
                  if r.field_name == "start_date" and r.source == "2")
    assert winner.rule == ConflictRule.MORE_PRECISE


# ---- 8. education: the degree level is a field, not an identity ----

def test_a_bachelor_and_a_master_of_one_study_are_one_entry_with_a_conflict():
    """The degree level is not part of the match, so a disagreement about it is
    a field conflict inside one entry rather than two separate degrees.

    Neither rung of the ladder may settle it: a newer file does not make a
    degree truer and neither does the kind of file it came in, because one of
    the two claims is simply wrong and only a person can say which. So the
    bachelor's and the master's reach C-06 with both values, which before
    M-01 could not happen at all — the two rows never met.
    """
    records = (
        study(CV, 1, "University of Jordan", degree="BSc",
              field="Computer Science", start="2016", end="2020")
        + study(LINKEDIN, 1, "The University of Jordan", degree="MSc",
                field="Computer Science", start="2016", end="2020")
    )
    matched = groups_of(records, "education")
    assert len(matched) == 1 and matched[0].merged

    built = build(records)
    assert len(built.profile.education) == 1
    row = built.profile.education[0]
    assert row.institution is not None
    assert row.field == "Computer Science"
    assert row.rule == MatchRule.SAME_ENTITY
    # FR-033: no value is auto-picked, so the field is left out of the profile.
    assert row.degree is None

    items = [i for i in built.review_items if i.field_name == "degree"]
    assert len(items) == 1
    assert items[0].reasons == [ReviewReason.SOURCE_CONFLICT]
    assert "C-06" in items[0].message
    assert {o.value for o in items[0].options} == {"BSc", "MSc"}
    assert items[0].entity == "1:education[1]"


def test_a_vetted_degree_level_still_wins():
    """Switching C-03 off must not keep a vetted value from winning at C-01."""
    vetted = ("2", "vetting", datetime(2026, 1, 1, tzinfo=timezone.utc))
    records = (
        study(CV, 1, "University of Jordan", degree="BSc",
              field="Computer Science", start="2016", end="2020")
        + study(vetted, 1, "University of Jordan", degree="MSc",
                field="Computer Science", start="2016", end="2020")
    )
    built = build(records)
    assert built.profile.education[0].degree == "MSc"
    winner = next(r for r in records if r.field_name == "degree" and r.source == "2")
    assert winner.rule == ConflictRule.VETTED_WINS


def test_an_abbreviated_institution_matches_the_name_written_out():
    """"Univ. of Jordan" scores only 0.82 against "University of Jordan" as raw
    text, so without expanding the abbreviation the two would stay separate."""
    assert institution_key("Univ. of Jordan") == institution_key("University of Jordan")
    records = (
        study(CV, 1, "Univ. of Jordan", field="Computer Science",
              start="2016", end="2020")
        + study(LINKEDIN, 1, "University of Jordan", field="Computer Science",
                start="2016", end="2020")
    )
    matched = groups_of(records, "education")
    assert len(matched) == 1 and matched[0].merged
    assert len(build(records).profile.education) == 1


@pytest.mark.parametrize("abbreviated, written_out", [
    ("Univ of Jordan", "University of Jordan"),
    ("Massachusetts Inst. of Tech.", "Massachusetts Institute of Technology"),
    ("Georgia Inst. of Tech.", "Georgia Institute of Technology"),
    ("Imperial Coll. London", "Imperial College London"),
    ("Dept. of Computing, Imperial", "Department of Computing Imperial"),
])
def test_the_institution_abbreviations_are_written_out(abbreviated, written_out):
    assert institution_key(abbreviated) == institution_key(written_out)


def test_expanding_an_abbreviation_does_not_merge_two_institutions():
    """Writing names out must not make different institutions look alike."""
    assert institution_key("Univ. of Jordan") != institution_key("Univ. of Amman")


def test_a_different_field_of_study_at_one_institution_is_a_different_entry():
    records = (
        study(CV, 1, "University of Jordan", field="Computer Science",
              start="2016", end="2020")
        + study(LINKEDIN, 1, "University of Jordan", field="Law",
                start="2016", end="2020")
    )
    assert len(groups_of(records, "education")) == 2


# ---- 9. certifications ----

def test_a_certification_matches_when_the_issuer_is_missing_on_one_side():
    records = (
        entity(CV, "certifications", 1, name="AWS Solutions Architect")
        + entity(LINKEDIN, "certifications", 1, name="aws solutions architect",
                 issuer="Amazon Web Services")
    )
    matched = groups_of(records, "certifications")
    assert len(matched) == 1 and matched[0].merged

    built = build(records)
    assert len(built.profile.certifications) == 1
    assert built.profile.certifications[0].issuer == "Amazon Web Services"


def test_a_certification_with_a_different_issuer_is_a_different_certificate():
    records = (
        entity(CV, "certifications", 1, name="Scrum Master", issuer="Scrum Alliance")
        + entity(LINKEDIN, "certifications", 1, name="Scrum Master", issuer="Scrum.org")
    )
    assert len(groups_of(records, "certifications")) == 2


def test_a_project_matches_on_its_name_only():
    records = (
        entity(CV, "projects", 1, name="Resume Parser", description="a CV parser")
        + entity(LINKEDIN, "projects", 1, name="resume parser")
    )
    matched = groups_of(records, "projects")
    assert len(matched) == 1 and matched[0].merged
    assert len(build(records).profile.projects) == 1


# ---- 10. the result never depends on the input order (FR-034, NFR-023) ----

def _shape(result):
    return [(group.entity_type, group.entity_id, group.sources,
             tuple(group.field_ids), group.ambiguous_ids)
            for group in result.groups]


def test_shuffled_records_give_an_identical_result():
    records = (
        job(CV, 1, "Google", "Engineer", start="2018-01", end="2019-12")
        + job(CV, 2, "Zain Jordan", "Intern", start="2017-01", end="2017-12")
        + job(LINKEDIN, 1, "Google LLC", "Senior Engineer", start="2018-01", end="2019-12")
        + job(LINKEDIN, 2, "Zain Jordan, Inc.", "Sales Intern", start="2017-01", end="2017-12")
        + study(CV, 1, "University of Jordan", degree="BSc", start="2013", end="2017")
        + study(LINKEDIN, 1, "The University of Jordan", degree="BSc",
                start="2013", end="2017")
        + entity(CV, "skills", 1, name="Python")
        + entity(LINKEDIN, "skills", 1, name="Python")
    )
    expected = _shape(match_entities(records))
    assert [group[2] for group in expected].count(("1", "2")) == 3

    shuffler = random.Random(20261114)
    for _ in range(25):
        shuffled = list(records)
        shuffler.shuffle(shuffled)
        assert _shape(match_entities(shuffled)) == expected


# ---- 11. ids survive a newer source arriving ----

def test_adding_a_newer_source_keeps_the_ids_of_existing_entities():
    """An entity id is taken from its earliest source, so the profile does not
    renumber itself every time a file is uploaded."""
    existing = (
        job(CV, 1, "Google", "Engineer", start="2020-01", end="2023-01")
        + job(LINKEDIN, 1, "Google LLC", "Senior Engineer", start="2020-01", end="2023-01")
        + study(CV, 1, "University of Jordan", degree="BSc", start="2013", end="2017")
    )
    before = {group.entity_type: group.entity_id
              for group in match_entities(existing).groups}
    assert before == {"work_experience": "1:work_experience[1]",
                      "education": "1:education[1]"}

    with_newer = existing + (
        job(NEWEST, 1, "Google, Inc.", "Staff Engineer", start="2020-01", end="2023-01")
        + job(NEWEST, 2, "Careem", "Staff Engineer", start="2023-02", end="current")
        + study(NEWEST, 1, "University of Jordan", degree="MSc", start="2018", end="2020")
    )
    after = match_entities(with_newer)

    assert [group.entity_id for group in after.of_type("work_experience")] == [
        "1:work_experience[1]",     # the merged Google job keeps the CV's id
        "3:work_experience[2]",     # the new job gets its own
    ]
    assert after.of_type("work_experience")[0].sources == ("1", "2", "3")
    # The master's does not overlap the bachelor's, so it is a second entry.
    assert [group.entity_id for group in after.of_type("education")] == [
        "1:education[1]", "3:education[1]",
    ]


def test_a_group_never_holds_two_entities_from_one_source():
    records = (
        job(CV, 1, "Google", start="2020-01", end="2023-01")
        + job(LINKEDIN, 1, "Google LLC", start="2020-01", end="2023-01")
        + job(NEWEST, 1, "Google Inc", start="2020-01", end="2023-01")
        + job(NEWEST, 2, "Alphabet", start="2020-01", end="2023-01")
    )
    for group in match_entities(records).groups:
        assert len(set(group.sources)) == len(group.sources)


# ---- the ladder now runs inside an entity, which was the point ----

def test_a_single_source_profile_is_unchanged_and_cites_no_merge_rule():
    records = job(CV, 1, "Zain Jordan", "Intern", start="2023-06", end="current")
    built = build(records)

    assert len(built.profile.experience) == 1
    row = built.profile.experience[0]
    assert row.rule is None
    assert row.entity_id == "1:work_experience[1]"
    assert built.review_items == []
