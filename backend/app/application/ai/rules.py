"""Registry of the rule identifiers the AI module cites on every decision.

Every value the module keeps, repairs or drops cites exactly one rule ID, which
is stored on the field record so the profile history can explain the decision
later (see the CVerge AI module contract, "Rule registry").

Prefixes:

* ``N-`` deterministic normalization rules, run in this module.
* ``R-`` rejection / review rules, run in this module.
* ``M-`` matching rules, run in the merge stage.
* ``C-`` conflict rules, run in the merge stage.

Member names mirror the IDs so code can be grepped against the contract.
"""

from enum import Enum
from typing import Final


class RuleId(str, Enum):
    """Identifier of a single deterministic rule."""

    # --- Normalization: dates -------------------------------------------
    N_DATE_01 = "N-DATE-01"
    N_DATE_02 = "N-DATE-02"
    N_DATE_03 = "N-DATE-03"
    N_DATE_04 = "N-DATE-04"
    N_DATE_05 = "N-DATE-05"
    N_DATE_06 = "N-DATE-06"

    # --- Normalization: skills ------------------------------------------
    N_SKILL_01 = "N-SKILL-01"
    N_SKILL_02 = "N-SKILL-02"
    N_SKILL_03 = "N-SKILL-03"
    N_SKILL_04 = "N-SKILL-04"
    N_SKILL_05 = "N-SKILL-05"

    # --- Normalization: places and contacts -----------------------------
    N_GEO_01 = "N-GEO-01"
    N_GEO_02 = "N-GEO-02"
    N_GEO_03 = "N-GEO-03"
    N_PHONE_01 = "N-PHONE-01"
    N_EMAIL_01 = "N-EMAIL-01"
    N_NAME_01 = "N-NAME-01"

    # --- Normalization: closed vocabularies -----------------------------
    # Module-local extension, not yet part of the contract's registry. It
    # covers every field whose normalized format is a fixed catalogue list:
    # education.degree, language.proficiency, language.name (ISO 639-1) and
    # profile link types. Needs sign-off before the contract is reissued.
    N_ENUM_01 = "N-ENUM-01"

    # --- Rejection and review (AI stage) --------------------------------
    R_01 = "R-01"
    R_02 = "R-02"
    R_03 = "R-03"
    R_04 = "R-04"
    R_05 = "R-05"
    R_06 = "R-06"
    R_07 = "R-07"
    R_08 = "R-08"
    R_09 = "R-09"

    # --- Matching (merge stage) -----------------------------------------
    M_01 = "M-01"
    M_02 = "M-02"
    M_03 = "M-03"
    M_04 = "M-04"

    # --- Conflict resolution (merge stage) ------------------------------
    C_01 = "C-01"
    C_02 = "C-02"
    C_03 = "C-03"
    C_04 = "C-04"
    C_05 = "C-05"
    C_06 = "C-06"

    def __str__(self) -> str:
        return self.value


RULE_DESCRIPTIONS: Final[dict[RuleId, str]] = {
    RuleId.N_DATE_01: "Month-precision date recognised and stored as year-month.",
    RuleId.N_DATE_02: "Year-only date kept at year precision; no month or day is invented.",
    RuleId.N_DATE_03: "Ambiguous day/month order fell back to year precision.",
    RuleId.N_DATE_04: "Ongoing role marker ('present', 'current', 'now', 'to date').",
    RuleId.N_DATE_05: "End date before start date in one snippet; the two were swapped.",
    RuleId.N_DATE_06: "Date outside the plausible range (before 1950, or too far ahead).",
    RuleId.N_SKILL_01: "Skill lowercased and trimmed, then looked up in the alias table.",
    RuleId.N_SKILL_02: "Combined skill entry split on '/' or '&'.",
    RuleId.N_SKILL_03: "Skill matched an alias within the allowed edit distance.",
    RuleId.N_SKILL_04: "Skill is on the soft-skill stop list and was dropped.",
    RuleId.N_SKILL_05: "Ambiguous short skill name kept as the model read it in context.",
    RuleId.N_GEO_01: "Country name or alias mapped to its ISO 3166-1 alpha-2 code.",
    RuleId.N_GEO_02: "Country inferred from a city with exactly one match.",
    RuleId.N_GEO_03: "Country unknown; queued as a system decision.",
    RuleId.N_PHONE_01: "Phone number put into E.164 form.",
    RuleId.N_EMAIL_01: "Email lowercased and validated.",
    RuleId.N_NAME_01: "Person name spacing collapsed and title-cased, acronyms kept.",
    RuleId.N_ENUM_01: "Value mapped onto a closed catalogue vocabulary.",
    RuleId.R_01: "LLM answer failed schema validation.",
    RuleId.R_02: "Value failed a format check or could not be normalized.",
    RuleId.R_03: "Evidence snippet was not found in the source text.",
    RuleId.R_04: "Protected trait; never extracted and never stored.",
    RuleId.R_05: "Source does not mention the field, so it is absent.",
    RuleId.R_06: "Confidence below the threshold; retried once, then review.",
    RuleId.R_07: "Skill on the soft-skill stop list.",
    RuleId.R_08: "Ambiguous short skill name accepted on its evidence alone.",
    RuleId.R_09: "Skill or country matched nothing in the tables; system decision.",
    RuleId.M_01: "Entities with the same name and overlapping dates are one entity.",
    RuleId.M_02: "List field from several sources merged as a union without duplicates.",
    RuleId.M_03: "Contact list merged as a union; primary value from the newest source.",
    RuleId.M_04: "Sources agree after normalization; confidence boosted once.",
    RuleId.C_01: "A vetted value exists and wins.",
    RuleId.C_02: "Values differ and the newer source wins.",
    RuleId.C_03: "Still tied; the higher-priority source wins.",
    RuleId.C_04: "Same value at different precision; the more precise one is kept.",
    RuleId.C_05: "Personal field still tied; asked of the candidate.",
    RuleId.C_06: "Claim field still tied; sent to the review queue.",
}

#: Bumped whenever a rule's behaviour changes, so each job can record the
#: version it ran under (NFR-023).
RULE_VERSION: Final[str] = "0.1.0"


def describe(rule: RuleId) -> str:
    """Return the human-readable description of ``rule``."""
    return RULE_DESCRIPTIONS[rule]
