"""Registry of every deterministic rule the system cites on a decision.

Each field record stores the identifier of the rule that produced its value
(FR-035). This module is what turns that identifier into a sentence a person
can read, which is what the dashboard needs to show why a value was chosen or
sent to review (FR-051), and what makes a decision taken months ago still
explainable after the rules have moved on (NFR-023).

The identifiers themselves live next to the logic that applies them —
:class:`~app.domain.services.dates.DateRule`,
:class:`~app.domain.services.countries.GeoRule`,
:class:`~app.domain.services.contacts.ContactRule`,
:class:`~app.domain.services.skills.SkillRule` and
:class:`~app.domain.services.conflict_rules.ConflictRule` — so a rule and its
description cannot drift apart unnoticed: :func:`describe` raises for an
identifier that is not listed here, and the test suite walks every class.

Prefixes:

* ``N-`` deterministic normalisation, run while building field records.
* ``C-`` conflict resolution, run when sources are merged.
* ``R-`` the value was not kept; a person decides.
"""

#: Bumped whenever a rule's behaviour changes, so each job can record the
#: version it ran under (NFR-023).
RULE_VERSION = "1.0.0"

RULE_DESCRIPTIONS: dict[str, str] = {
    # --- dates (FR-028) ------------------------------------------------
    "N-DATE-01": "Month-precision date recognised and stored as year-month.",
    "N-DATE-02": "Year-only date kept at year precision; no month was invented.",
    "N-DATE-03": "Day and month order was ambiguous; the year was kept and a "
                 "reviewer was asked for the month.",
    "N-DATE-04": "Ongoing-role marker ('present', 'current', 'now').",
    "N-DATE-05": "End date came before the start date; the two were swapped.",
    "N-DATE-06": "Date too far in the future to be real; treated as unreadable.",

    # --- skills (FR-029, FR-030, FR-062) --------------------------------
    "N-SKILL-01": "Skill name matched the standard list on its match key.",
    "N-SKILL-02": "One entry named two skills and was split into two records.",

    # --- places and contacts (FR-070) -----------------------------------
    "N-GEO-01": "Country matched the country list by name or two-letter code.",
    "N-GEO-02": "No country was stated; it was read from a city that "
                "identifies exactly one country.",
    "N-PHONE-01": "Phone number put into E.164 form.",
    "N-EMAIL-01": "Email address lowercased and validated.",
    "N-NAME-01": "Person name spacing collapsed and title-cased.",

    # --- conflict resolution (FR-031 to FR-034) -------------------------
    "C-00": "Every source agreed on this value.",
    "C-01": "A vetted value exists, so it was used over the self-reported one.",
    "C-02": "Sources disagreed; the value from the newer source was used.",
    "C-03": "Recency did not decide; the value from the more trusted kind of "
            "source was used.",
    "C-04": "The same value at two precisions; the more precise one was kept.",
    "C-05": "No rule decided this personal detail, so the candidate was asked.",
    "C-06": "No rule decided, so a reviewer was asked to choose.",

    # --- other provenance values already stored on records --------------
    "llm_extraction": "Value read from the source by the language model, with "
                      "no normalisation rule applying to it.",
    "vetting_record": "Value came from a vetting result the platform produced.",
    "review_decision": "Value set by a reviewer's decision.",
    "standard_name": "Skill was already written as its standard name.",
    "alias_table": "Skill name mapped to its standard name through the alias table.",
}


def describe(rule: str) -> str:
    """The human-readable description of ``rule``.

    Raises :class:`KeyError` for an unknown identifier, so a rule added to the
    code without a description fails a test rather than reaching a dashboard
    as a bare code.
    """
    return RULE_DESCRIPTIONS[rule]


def describe_or_none(rule: str | None) -> str | None:
    """Same as :func:`describe` but tolerant, for displaying stored records
    written by an older version of the rules."""
    if not rule:
        return None
    return RULE_DESCRIPTIONS.get(rule)
