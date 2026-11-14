"""Skill canonicalization (N-SKILL-01 to N-SKILL-05).

One raw entry can produce more than one skill, because "React/Redux" names two,
so this is the one normalizer that returns a list.
"""

import re

from app.application.ai.rules import RuleId
from app.application.ai.schemas.normalization import NormalizationOutcome
from app.application.ai.skills.alias_table import SkillAliasTable

#: Separators that join two skills in one entry (N-SKILL-02). A comma is not
#: one of them: the model is asked for one entry per skill, and splitting on
#: commas would break names such as "Oracle Database, 12c".
_COMBINED_ENTRY = re.compile(r"\s*[/&]\s*|\s+and\s+", re.IGNORECASE)

#: Names that contain a separator but are single skills, so they are never split.
_NEVER_SPLIT = frozenset({"ci/cd", "and", "r&d"})


class SkillCanonicalizer:
    """Turns raw skill text into canonical skill names."""

    def __init__(
        self,
        alias_table: SkillAliasTable | None = None,
        *,
        fuzzy_mapping_factor: float = 0.85,
    ) -> None:
        self._table = alias_table or SkillAliasTable()
        self._fuzzy_mapping_factor = fuzzy_mapping_factor

    def canonicalize(self, raw_value: str) -> list[NormalizationOutcome]:
        """Return one outcome per skill found in ``raw_value``.

        An entry naming two skills gives two outcomes; a soft skill gives one
        rejected outcome, so the drop still reaches the audit trail.
        """
        text = raw_value.strip()
        if not text:
            return [NormalizationOutcome.rejected(RuleId.R_02, "Empty skill")]

        parts = self._split(text)
        split_applied = len(parts) > 1

        return [self._canonicalize_one(part, split_applied) for part in parts]

    def _split(self, text: str) -> list[str]:
        """Split a combined entry, unless the whole entry is a known name."""
        if text.casefold() in _NEVER_SPLIT or self._table.resolve(text):
            return [text]

        parts = [part.strip() for part in _COMBINED_ENTRY.split(text) if part.strip()]
        return parts or [text]

    def _canonicalize_one(self, text: str, split_applied: bool) -> NormalizationOutcome:
        if self._table.is_soft_skill(text):
            # N-SKILL-04: dropped and logged, never reviewed.
            return NormalizationOutcome.rejected(
                RuleId.R_07, f"Soft skill dropped: {text!r}"
            )

        if canonical := self._table.resolve(text):
            rule = RuleId.N_SKILL_02 if split_applied else RuleId.N_SKILL_01
            if self._table.is_ambiguous(canonical):
                # N-SKILL-05 / R-08: the model's reading of the context is
                # trusted, and only the evidence check (R-03) guards it.
                return NormalizationOutcome.ok(canonical, RuleId.N_SKILL_05)
            return NormalizationOutcome.ok(canonical, rule)

        if canonical := self._table.resolve_fuzzy(text):
            if self._table.is_ambiguous(canonical):
                # Never reach an ambiguous short name by fuzzy matching: "god"
                # must not become "Go".
                return self._unknown(text)
            return NormalizationOutcome.mapped(
                canonical, RuleId.N_SKILL_03, self._fuzzy_mapping_factor
            )

        return self._unknown(text)

    @staticmethod
    def _unknown(text: str) -> NormalizationOutcome:
        """A skill matching nothing in the table becomes a system decision (R-09)."""
        return NormalizationOutcome(
            value=None,
            rule=RuleId.N_SKILL_01,
            rejected_by=RuleId.R_09,
            detail=f"No skill matches {text!r}",
            needs_system_decision=True,
        )
