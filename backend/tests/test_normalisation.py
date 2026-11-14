"""Dates (FR-028), countries (FR-070), skills (FR-029, FR-030)."""

from datetime import date

import pytest

from app.domain.services.contacts import (
    normalize_email,
    normalize_person_name,
    normalize_phone,
)
from app.domain.services.countries import CountryCatalog, infer_country_code_from_city
from app.domain.services.dates import (
    PartialDate,
    parse_date,
    repair_date_order,
    resolve_employment_end,
)
from app.domain.services.skills import SkillCatalog, clean_skill_name, union_skills
from app.infrastructure.reference_data import SEED_COUNTRIES, seed_skill_catalog


@pytest.mark.parametrize("text, expected, precision", [
    ("03/2022", "2022-03", "month"),
    ("3/2022", "2022-03", "month"),
    ("March 2022", "2022-03", "month"),
    ("Mar 2022", "2022-03", "month"),
    ("Sept. 2014", "2014-09", "month"),
    ("15 March 2022", "2022-03", "month"),     # day dropped, never stored
    ("2022-03-15", "2022-03", "month"),
    ("25/03/2022", "2022-03", "month"),
    ("2022", "2022", "year"),
    ("Summer 2020", "2020", "year"),
])
def test_dates_share_one_format_and_keep_precision(text, expected, precision):
    result = parse_date(text)
    assert result.kind == "date"
    assert result.date.iso == expected
    assert result.date.precision == precision


@pytest.mark.parametrize("text", ["Present", "current", "Now"])
def test_current_markers(text):
    assert parse_date(text).kind == "current"


@pytest.mark.parametrize("text", ["13/2022", "soon", "22", "99/99/2022"])
def test_bad_dates_are_invalid(text):
    assert parse_date(text).kind == "invalid"


@pytest.mark.parametrize("text", ["04/05/2022", "1/2/2020"])
def test_ambiguous_day_month_order_keeps_the_year_only(text):
    """N-DATE-03: either part could be the month, but the year is certain.

    The year is kept at year precision and the month is dropped, never
    guessed. Nobody is asked: the rule is deterministic, so the only trace is
    a lower validation factor on the value (see the builder test for that).
    """
    result = parse_date(text)
    assert result.kind == "date"
    assert result.date.precision == "year"
    assert result.date.iso == text[-4:]
    assert result.ambiguous is True


@pytest.mark.parametrize("text", ["2099", "2140-03"])
def test_dates_too_far_ahead_are_invalid(text):
    """N-DATE-06: a year beyond next year is an OCR misreading, not a date."""
    assert parse_date(text, today=date(2026, 11, 14)).kind == "invalid"


def test_reversed_start_and_end_dates_are_swapped():
    """N-DATE-05: one sensible repair, so it is repaired, not sent to a person."""
    start, end, swapped = repair_date_order(PartialDate(2024, 3), PartialDate(2020, 1))
    assert swapped and start.iso == "2020-01" and end.iso == "2024-03"


def test_dates_in_order_are_left_alone():
    start, end, swapped = repair_date_order(PartialDate(2020, 1), PartialDate(2024, 3))
    assert not swapped and start.iso == "2020-01"


def test_precision_difference_is_not_a_reversal():
    """"2020" against "2020-03" differ in precision, not in order."""
    _, _, swapped = repair_date_order(PartialDate(2020), PartialDate(2020, 3))
    assert not swapped


def test_current_job_differs_from_missing_end_date():
    assert resolve_employment_end("Present", False).status == "current"
    assert resolve_employment_end(None, True).status == "current"
    assert resolve_employment_end(None, False).status == "unknown"
    ended = resolve_employment_end("11/2020", False)
    assert ended.status == "ended" and ended.date.iso == "2020-11"
    assert resolve_employment_end("11/2020", True).conflict


@pytest.mark.parametrize("text, code", [
    ("Jordan", "JO"), ("jordan", "JO"), ("JO", "JO"), ("gb", "GB"),
    ("UK", "GB"), ("United Kingdom.", "GB"), ("Palestinian Authority", "PS"),
])
def test_country_matched_by_name_or_code(text, code):
    assert CountryCatalog(SEED_COUNTRIES).match(text).code == code


@pytest.mark.parametrize("text", ["Ireland", "Portugal", "XX", ""])
def test_unknown_country_is_none(text):
    assert CountryCatalog(SEED_COUNTRIES).match(text) is None


@pytest.mark.parametrize("text, standard", [
    # case and alias table (FR-029)
    ("reactjs", "React"), ("React", "React"), ("REACT.JS", "React"),
    ("  node ", "Node.js"), ("postgres", "PostgreSQL"), ("MS Excel", "Microsoft Excel"),
    ("Microsoft Office Suite", "Microsoft Office"), ("SPSS Statistics", "SPSS"),
    # spelling variants through the match key, no alias needed
    ("Node JS", "Node.js"), ("NodeJS", "Node.js"), ("node-js", "Node.js"),
    ("Problem-Solving", "Problem Solving"), ("problem solving", "Problem Solving"),
    ("MAC OS", "macOS"), ("Vue", "Vue.js"), ("next js", "Next.js"),
    # qualifiers, endorsement counts, levels and versions are ignored
    ("Pandas (Software)", "Pandas"), ("Microsoft Access (Basic)", "Microsoft Access"),
    ("Artificial Intelligence (AI)", "Artificial Intelligence"),
    ("Critical Thinking · 1 endorsements", "Critical Thinking"),
    ("Communication · 12 endorsements", "Communication"),
    ("Python - Advanced", "Python"), ("Python 3", "Python"), ("Angular 15", "Angular"),
    ("Microsoft Office 365", "Microsoft Office"), ("Postgre SQL", "PostgreSQL"),
    ("Teamwork & Leadership", None),
])
def test_skill_lookup(text, standard):
    assert seed_skill_catalog().lookup(text) == standard


@pytest.mark.parametrize("a, b", [("C", "C#"), ("C", "C++"), ("C#", "C++"),
                                  ("Java", "JavaScript"), ("R", "Ruby")])
def test_similar_languages_stay_different(a, b):
    catalog = seed_skill_catalog()
    assert catalog.lookup(a) != catalog.lookup(b)


@pytest.mark.parametrize("text", ["Nagra", "Short Films", "Full UK Driving Licence", "", "  "])
def test_unknown_skill_is_none(text):
    assert seed_skill_catalog().lookup(text) is None


@pytest.mark.parametrize("text, standard", [
    ("Postgress", "PostgreSQL"),     # one substitution plus one insertion
    ("Pyhton", "Python"),            # two characters transposed
    ("Dockerr", "Docker"),           # one character too many
    ("Javascrpt", "JavaScript"),
])
def test_misspelt_known_skill_is_mapped_automatically(text, standard):
    """N-SKILL-03: a misspelt known skill is not an unknown skill (FR-062).

    One edit is allowed for a match key of 5 to 8 characters and two from 9
    upwards. The rule is fixed, so this stays deterministic (FR-034).
    """
    assert seed_skill_catalog().resolve_fuzzy(text) == standard


@pytest.mark.parametrize("text", ["God", "Jva", "Rst", "Pyt"])
def test_short_names_are_never_fuzzy_matched(text):
    """Under five characters almost everything is one edit from something
    else, so "God" must not become "Go"."""
    assert seed_skill_catalog().resolve_fuzzy(text) is None


@pytest.mark.parametrize("text", [
    "Adobe Effects",                 # five edits away: a missing word, not a typo
    "Strong verbal communication",   # a phrase, not a misspelling
    "Creative problem solving",
    "Nagra", "Short Films",
])
def test_a_name_too_far_from_any_standard_skill_is_not_mapped(text):
    catalog = seed_skill_catalog()
    assert catalog.lookup(text) is None
    assert catalog.resolve_fuzzy(text) is None


@pytest.mark.parametrize("text, hint", [
    ("Adobe Effects", "Adobe After Effects"),
    ("Strong verbal communication", "Communication"),  # standard skill inside the phrase
    ("Creative problem solving", "Problem Solving"),
    ("Nagra", None), ("Short Films", None),
])
def test_suggestion_for_reviewer(text, hint):
    """R-09: what matches nothing still reaches a person, with a hint that is
    offered and never applied on its own."""
    catalog = seed_skill_catalog()
    assert catalog.lookup(text) is None
    assert catalog.resolve_fuzzy(text) is None
    assert catalog.suggest(text) == hint


def test_skill_union_without_repeats():
    assert union_skills([["React", "Node.js"], ["react", "Node JS", "Docker"]]) ==         ["React", "Node.js", "Docker"]


def test_alias_to_unknown_skill_is_rejected():
    with pytest.raises(ValueError):
        SkillCatalog(["React"], {"vue": "Vue"})


def test_two_standard_skills_with_the_same_key_are_rejected():
    with pytest.raises(ValueError, match="same match key"):
        SkillCatalog(["Node.js", "NodeJS"], {})


@pytest.mark.parametrize("text, clean", [
    ("Nagra (Basic)", "Nagra"), ("Critical Thinking · 1 endorsements", "Critical Thinking"),
    ("  Final   Cut  ", "Final Cut"), ("Sound Design - Advanced", "Sound Design"),
])
def test_new_skill_names_are_cleaned(text, clean):
    assert clean_skill_name(text) == clean


@pytest.mark.parametrize("text, standard", [
    # phrasings of existing soft skills
    ("Excellent communication skills", "Communication"), ("Communication skills", "Communication"),
    ("Teamwork & collaboration", "Teamwork"), ("Collaborative", "Teamwork"),
    ("Leadership abilities", "Leadership"), ("Problem solving skills", "Problem Solving"),
    ("Extremely organised", "Organization"), ("Highly organized", "Organization"),
    ("Organisational skills", "Organization"), ("Conflict management", "Conflict Resolution"),
    # new soft skills
    ("Attention to detail", "Attention to Detail"), ("Detail-oriented", "Attention to Detail"),
    ("Flexible", "Adaptability"), ("Strong work ethic", "Work Ethic"),
    ("Hard-working", "Work Ethic"), ("Self-motivated", "Self-Motivation"),
    ("Self starter", "Self-Motivation"), ("Works well under pressure", "Working Under Pressure"),
    ("People skills", "Interpersonal Skills"), ("Interpersonal skills", "Interpersonal Skills"),
    ("Public speaking", "Presentation Skills"), ("Multi-tasking", "Multitasking"),
    ("Analytical skills", "Analytical Thinking"), ("Emotional Intelligence (EQ)", "Emotional Intelligence"),
    ("Coaching", "Mentoring"), ("Proactive", "Initiative"),
])
def test_soft_skill_phrasings(text, standard):
    assert seed_skill_catalog().lookup(text) == standard


@pytest.mark.parametrize("text, hint", [
    # an extra word that changes the meaning goes to review, with a hint
    ("Strong verbal communication", "Communication"),
    ("Creative problem solving", "Problem Solving"),
])
def test_qualified_soft_skills_still_go_to_review(text, hint):
    catalog = seed_skill_catalog()
    assert catalog.lookup(text) is None
    assert catalog.suggest(text) == hint


# ---- contacts: phone, email, name (N-PHONE-01, N-EMAIL-01, N-NAME-01) ----

@pytest.mark.parametrize("raw", ["+962 7 9000 1234", "00962790001234", "+962-790-001-234"])
def test_one_number_written_three_ways_becomes_one_value(raw):
    """Three spellings of one number would be three false conflicts (FR-033)."""
    assert normalize_phone(raw).e164 == "+962790001234"


def test_local_number_borrows_the_profile_country():
    result = normalize_phone("0790001234", "JO")
    assert result.e164 == "+962790001234"
    assert result.borrowed_country == "JO"


def test_local_number_without_a_country_is_rejected_not_guessed():
    """A wrong dial code looks correct, so it is worse than a flagged field."""
    assert normalize_phone("0790001234", None).e164 is None


@pytest.mark.parametrize("raw", ["not a phone", "", "12", "+0123456789"])
def test_unusable_phone_numbers_are_rejected(raw):
    assert normalize_phone(raw).e164 is None


def test_email_is_lowercased():
    assert normalize_email("Ahmad.Y@Example.COM") == "ahmad.y@example.com"


@pytest.mark.parametrize("raw", ["no-at-sign", "a@b", "", "a b@c.com"])
def test_invalid_emails_are_rejected(raw):
    assert normalize_email(raw) is None


@pytest.mark.parametrize("raw, expected", [
    ("ahmad   AL-masri", "Ahmad Al-Masri"),
    ("NADA KHAIRALDIN", "Nada Khairaldin"),   # CV headers often shout the name
    ("J.R.R. tolkien", "J.R.R. Tolkien"),     # initials keep their shape
    ("o'brien", "O'Brien"),
    ("ali bin hassan", "Ali bin Hassan"),  # particle stays lowercase
])
def test_person_names_are_normalised(raw, expected):
    assert normalize_person_name(raw) == expected


# ---- country inference from city (N-GEO-02) ----

@pytest.mark.parametrize("city, code", [
    ("Ramallah", "PS"), ("Amman", "JO"), ("  CAIRO  ", "EG"), ("Dubai", "AE"),
])
def test_country_inferred_from_an_unambiguous_city(city, code):
    """Most CVs give a city and no country; without this the profile has none."""
    assert infer_country_code_from_city(city) == code


@pytest.mark.parametrize("city", ["Springfield", "Nowhere", "", None])
def test_no_country_is_inferred_from_an_unknown_or_ambiguous_city(city):
    assert infer_country_code_from_city(city) is None


# ---- the rule registry explains every rule the code can cite (FR-051) ----

def test_every_rule_identifier_has_a_description():
    """A rule added without a description would reach the dashboard as a bare
    code, so this fails instead."""
    from app.domain.services.conflict_rules import ConflictRule
    from app.domain.services.contacts import ContactRule
    from app.domain.services.countries import GeoRule
    from app.domain.services.dates import DateRule
    from app.domain.services.entity_matching import MatchRule
    from app.domain.services.rules import describe
    from app.domain.services.skills import SkillRule

    for holder in (DateRule, GeoRule, ContactRule, SkillRule, ConflictRule,
                   MatchRule):
        for name, value in vars(holder).items():
            if name.startswith("_") or not isinstance(value, str):
                continue
            assert describe(value), f"{holder.__name__}.{name} ({value}) has no description"
