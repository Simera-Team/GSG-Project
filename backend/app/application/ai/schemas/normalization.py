"""What a normalizer returns, and the context it needs to do its work."""

from dataclasses import dataclass

from app.application.ai.rules import RuleId
from app.application.ai.schemas.normalized_value import NormalizedValue


@dataclass(frozen=True, slots=True)
class NormalizationContext:
    """Facts from outside one value that a normalizer may need.

    ``profile_country`` supplies the country code a local phone number is
    missing (N-PHONE-01).
    """

    profile_country: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizationOutcome:
    """The result of normalizing one raw value.

    Either it produced a catalogue value, or an R-rule rejected it. A value no
    rule can normalize is rejected, never guessed.
    """

    value: NormalizedValue | None = None
    rule: RuleId | None = None
    validation: float = 1.0
    mapping: float = 1.0
    rejected_by: RuleId | None = None
    detail: str | None = None
    #: Set when the value is valid but its mapping needs a human decision whose
    #: answer changes a shared table rather than one profile (R-09).
    needs_system_decision: bool = False

    @property
    def accepted(self) -> bool:
        return self.rejected_by is None and self.value is not None

    @classmethod
    def ok(
        cls,
        value: NormalizedValue,
        rule: RuleId | None = None,
    ) -> "NormalizationOutcome":
        """A value that passed every format check as it stood."""
        return cls(value=value, rule=rule)

    @classmethod
    def repaired(
        cls,
        value: NormalizedValue,
        rule: RuleId,
        validation: float,
        detail: str | None = None,
    ) -> "NormalizationOutcome":
        """A value that passed only after a listed deterministic repair."""
        return cls(value=value, rule=rule, validation=validation, detail=detail)

    @classmethod
    def mapped(
        cls,
        value: NormalizedValue,
        rule: RuleId,
        mapping: float,
        needs_system_decision: bool = False,
    ) -> "NormalizationOutcome":
        """A value matched against a shared table, exactly or fuzzily."""
        return cls(
            value=value,
            rule=rule,
            mapping=mapping,
            needs_system_decision=needs_system_decision,
        )

    @classmethod
    def rejected(
        cls,
        reason: RuleId,
        detail: str | None = None,
    ) -> "NormalizationOutcome":
        """A value no rule could normalize, or that failed a format check."""
        return cls(rejected_by=reason, detail=detail)
