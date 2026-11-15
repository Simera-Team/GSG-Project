"""Dates (FR-028), countries (FR-070), skills (FR-029, FR-030)."""

import pytest

from app.domain.services.countries import CountryCatalog
from app.domain.services.dates import parse_date, resolve_employment_end
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


@pytest.mark.parametrize("text", ["04/05/2022", "13/2022", "soon", "22"])
def test_ambiguous_or_bad_dates_are_invalid(text):
    assert parse_date(text).kind == "invalid"


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


@pytest.mark.parametrize("text, hint", [
    ("Adobe Effects", "Adobe After Effects"),          # close spelling
    ("Postgress", "PostgreSQL"),                      # misspelt
    ("Strong verbal communication", "Communication"),  # standard skill inside the phrase
    ("Creative problem solving", "Problem Solving"),
    ("Nagra", None), ("Short Films", None),
])
def test_suggestion_for_reviewer(text, hint):
    catalog = seed_skill_catalog()
    assert catalog.lookup(text) is None        # never applied automatically (FR-062)
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
