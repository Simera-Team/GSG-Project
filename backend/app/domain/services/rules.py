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
:class:`~app.domain.services.skills.SkillRule`,
:class:`~app.domain.services.entity_matching.MatchRule` and
:class:`~app.domain.services.conflict_rules.ConflictRule` — so a rule and its
description cannot drift apart unnoticed: :func:`describe` raises for an
identifier that is not listed here, and the test suite walks every class.

Prefixes:

* ``N-`` deterministic normalisation, run while building field records.
* ``M-`` entity matching and cross-source agreement, run when sources merge.
* ``C-`` conflict resolution, run when sources are merged.
* ``R-`` the value was not kept. Usually a person decides; ``R-03`` is the
  exception, where the value is not in the document and so there is nothing
  to decide.
"""

#: Bumped whenever a rule's behaviour changes, so each job can record the
#: version it ran under (NFR-023).
#: 1.1.0 — entity matching across sources added (M-01, R-10), and C-03 no
#: longer decides a degree level.
RULE_VERSION = "1.1.0"

RULE_DESCRIPTIONS: dict[str, str] = {
    # --- dates (FR-028) ------------------------------------------------
    "N-DATE-01": "Month-precision date recognised and stored as year-month.",
    "N-DATE-02": "Year-only date kept at year precision; no month was invented.",
    "N-DATE-03": "Day and month order was ambiguous; the year was kept at "
                 "year precision and the month was dropped, never guessed.",
    "N-DATE-04": "Ongoing-role marker ('present', 'current', 'now').",
    "N-DATE-05": "End date came before the start date; the two were swapped.",
    "N-DATE-06": "Date too far in the future to be real; treated as unreadable.",

    # --- skills (FR-029, FR-030, FR-062) --------------------------------
    "N-SKILL-01": "Skill name matched the standard list on its match key.",
    "N-SKILL-02": "One entry named two skills and was split into two records.",
    "N-SKILL-03": "Skill name matched a standard name or alias within the "
                  "allowed edit distance; the spelling was corrected.",
    "R-09": "Skill matched nothing in the standard list or the aliases, so a "
            "person decides whether it is new, a mapping, or rejected.",

    # --- places and contacts (FR-070) -----------------------------------
    "N-GEO-01": "Country matched the country list by name or two-letter code.",
    "N-GEO-02": "No country was stated; it was read from a city that "
                "identifies exactly one country.",
    "N-PHONE-01": "Phone number put into E.164 form.",
    "N-EMAIL-01": "Email address lowercased and validated.",
    "N-NAME-01": "Person name spacing collapsed and title-cased.",

    # --- rejection: the value never becomes a field record --------------
    "R-03": "The evidence snippet was not in the source text, or did not "
            "support the value, so the value was dropped rather than stored. "
            "Nothing is sent to a person: a value that is not in the document "
            "is not a judgement call.",

    # --- entity matching across sources (FR-031, FR-063) ----------------
    "M-01": "Entities from different sources describe the same thing and were "
            "merged: the same company or institution, and dates that overlap "
            "or were not stated. The job title and the degree level are not "
            "part of the match, so a difference in them is a field conflict.",
    "R-10": "An entity could equally be either of several entities from "
            "another source, so nothing was merged and a person decides which "
            "of them it is.",
    "M-03": "Contact list (email, phone) merged as a union across all sources, "
            "de-duplicated on the normalised value; primary from the newest "
            "source. Never creates a review item or a candidate question.",
    "M-04": "Two or more different sources state the same value, so the "
            "agreement itself raised its confidence: the highest of their "
            "scores plus 0.05, capped at 1.00, added once however many "
            "sources agree. Two mentions inside one source are not "
            "agreement.",

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
