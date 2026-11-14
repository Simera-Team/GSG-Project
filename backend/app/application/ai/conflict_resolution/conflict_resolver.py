"""Resolves disagreement between sources with explicit rules, never an LLM.

The rules run in the order the field's policy gives, and the first one that
decides ends the chain, so the same inputs always give the same profile
(FR-034, NFR-023). A field no rule decides is not guessed: it is handed on as
an :class:`UnresolvedConflict` with every candidate value and its source
intact, which is what the review queue shows (FR-041).
"""

import logging
from collections import OrderedDict
from datetime import date

from pydantic import BaseModel

from app.application.ai.confidence.scorer import ConfidenceScorer
from app.application.ai.conflict_resolution.field_policy import (
    FieldPolicy,
    policy_for,
)
from app.application.ai.rules import RuleId
from app.application.ai.schemas.document_text import SourceKind
from app.application.ai.schemas.field_record import (
    ExtractionStatus,
    FieldName,
    FieldRecord,
)
from app.application.ai.schemas.merge import (
    ConflictFallback,
    FieldKind,
    MatchedEntity,
    ResolvedField,
    UnresolvedConflict,
    ValueCandidate,
)
from app.application.ai.schemas.normalized_value import NormalizedValue, PartialDate
from app.application.ai.settings import AISettings
from app.application.ai.text_matching import canonical_text

logger = logging.getLogger(__name__)

#: A group of candidates that all gave the same value after normalization.
_ValueGroup = list[ValueCandidate]


class ConflictResolver:
    """Picks one value per field, or preserves the conflict for a person."""

    def __init__(
        self,
        settings: AISettings | None = None,
        scorer: ConfidenceScorer | None = None,
    ) -> None:
        self._settings = settings or AISettings()
        self._scorer = scorer or ConfidenceScorer(self._settings)

    def resolve(
        self, entity: MatchedEntity
    ) -> tuple[list[ResolvedField], list[UnresolvedConflict]]:
        """Resolve every field of one matched entity."""
        resolved: list[ResolvedField] = []
        conflicts: list[UnresolvedConflict] = []

        for field in self._fields_of(entity):
            policy = policy_for(entity.entity, field)
            candidates = self._candidates_for(entity, field)
            if not candidates:
                continue

            if policy.kind is FieldKind.LIST:
                resolved.append(self._resolve_list(entity, field, policy, candidates))
                continue

            outcome = self._resolve_single(entity, field, policy, candidates)
            if isinstance(outcome, UnresolvedConflict):
                conflicts.append(outcome)
            else:
                resolved.append(outcome)

        return resolved, conflicts

    # --- list fields -----------------------------------------------------

    def _resolve_list(
        self,
        entity: MatchedEntity,
        field: FieldName,
        policy: FieldPolicy,
        candidates: list[ValueCandidate],
    ) -> ResolvedField:
        """Merge a list field as a union without duplicates (M-02, M-03).

        A list field cannot conflict: every distinct value is kept. Values are
        ordered newest source first, so the primary email, phone or link of each
        type is the newest source's (M-03).
        """
        groups = self._group_by_value(candidates)
        kept = [self._boosted(group) for group in groups.values()]
        kept.sort(key=lambda candidate: candidate.source.uploaded_at, reverse=True)

        return ResolvedField(
            entity=entity.entity,
            entity_id=entity.entity_id,
            field=field,
            kind=FieldKind.LIST,
            values=kept,
            decided_by=policy.rules[0] if policy.rules else RuleId.M_02,
            confidence=min(candidate.record.confidence for candidate in kept),
            agreeing_sources=sorted(
                {candidate.source.source_id for candidate in candidates}
            ),
        )

    # --- single fields ---------------------------------------------------

    def _resolve_single(
        self,
        entity: MatchedEntity,
        field: FieldName,
        policy: FieldPolicy,
        candidates: list[ValueCandidate],
    ) -> ResolvedField | UnresolvedConflict:
        """Apply the field's rules in order until one decides."""
        groups = self._group_by_value(candidates)

        if len(groups) == 1:
            group = next(iter(groups.values()))
            winner = self._boosted(group)
            decided_by = (
                RuleId.M_04 if self._distinct_sources(group) > 1 else None
            )
            return self._finish(entity, field, policy, winner, candidates, decided_by)

        for rule in policy.rules:
            winner = self._apply(rule, groups, policy)
            if winner is None:
                continue
            return self._finish(entity, field, policy, winner, candidates, rule)

        if policy.fallback is ConflictFallback.NONE:
            # The policy asserts this field never conflicts, so a tie here is
            # broken deterministically rather than silently dropped: the most
            # confident value, then the newest source, then the lowest source
            # id so the result never depends on input order.
            winner = self._deterministic_tiebreak(candidates)
            decided_by = policy.rules[-1] if policy.rules else None
            return self._finish(entity, field, policy, winner, candidates, decided_by)

        return self._conflict(entity, field, policy, candidates)

    def _apply(
        self,
        rule: RuleId,
        groups: "OrderedDict[str, _ValueGroup]",
        policy: FieldPolicy,
    ) -> ValueCandidate | None:
        """Run one conflict rule and return its winner, or ``None`` if it abstains."""
        if rule is RuleId.C_01:
            return self._vetted_wins(groups)
        if rule is RuleId.C_02:
            return self._newer_source_wins(groups)
        if rule is RuleId.C_03:
            return self._source_priority_wins(groups, policy)
        if rule is RuleId.C_04:
            return self._more_precise_wins(groups)
        if rule is RuleId.M_01:
            # Variants of the same identifying name are one entity, so the
            # newest source's spelling is used and the field never conflicts.
            return self._newest(
                [candidate for group in groups.values() for candidate in group]
            )
        return None

    def _vetted_wins(
        self, groups: "OrderedDict[str, _ValueGroup]"
    ) -> ValueCandidate | None:
        """C-01: a vetted value wins over anything the candidate claimed."""
        vetted = [
            candidate
            for group in groups.values()
            for candidate in group
            if candidate.source.kind is SourceKind.VETTING
        ]
        return self._newest(vetted)

    def _newer_source_wins(
        self, groups: "OrderedDict[str, _ValueGroup]"
    ) -> ValueCandidate | None:
        """C-02: the later upload wins; two uploads on the same day are a tie.

        Comparing calendar days rather than timestamps is what makes "same-day"
        a real tie that passes to the next rule, instead of being decided by
        which file finished uploading first.
        """
        best_day: date | None = None
        winners: list[ValueCandidate] = []

        for group in groups.values():
            candidate = self._newest(group)
            if candidate is None:
                continue
            day = candidate.source.uploaded_at.date()
            if best_day is None or day > best_day:
                best_day, winners = day, [candidate]
            elif day == best_day:
                winners.append(candidate)

        return winners[0] if len(winners) == 1 else None

    def _source_priority_wins(
        self,
        groups: "OrderedDict[str, _ValueGroup]",
        policy: FieldPolicy,
    ) -> ValueCandidate | None:
        """C-03: the higher-priority source wins when recency ties."""
        for kind in policy.source_priority:
            matches = [
                candidate
                for group in groups.values()
                for candidate in group
                if candidate.source.kind is kind
            ]
            if not matches:
                continue
            values = {self._value_key(candidate.record.value) for candidate in matches}
            if len(values) == 1:
                return self._newest(matches)
            # Two sources of the same priority disagree, so priority cannot
            # decide; the next rule, or the fallback, handles it.
            return None
        return None

    def _more_precise_wins(
        self, groups: "OrderedDict[str, _ValueGroup]"
    ) -> ValueCandidate | None:
        """C-04: the same date at different precision is not a conflict.

        ``2022`` and ``2022-03`` describe one date, so the more precise value is
        kept and no boost is applied: the sources did not independently confirm
        the same thing.
        """
        candidates = [
            self._newest(group) for group in groups.values()
        ]
        dated = [
            candidate
            for candidate in candidates
            if candidate is not None and isinstance(candidate.record.value, PartialDate)
        ]
        if len(dated) != len(candidates) or len(dated) < 2:
            return None

        most_precise = max(
            dated,
            key=lambda candidate: (
                candidate.record.value.precision_rank,  # type: ignore[union-attr]
                candidate.source.uploaded_at,
            ),
        )
        precise_value: PartialDate = most_precise.record.value  # type: ignore[assignment]

        for candidate in dated:
            value: PartialDate = candidate.record.value  # type: ignore[assignment]
            if value is precise_value:
                continue
            if not value.coarser_than(precise_value):
                # Genuinely different dates, not one stated less precisely.
                return None

        return most_precise

    # --- assembly --------------------------------------------------------

    def _finish(
        self,
        entity: MatchedEntity,
        field: FieldName,
        policy: FieldPolicy,
        winner: ValueCandidate | None,
        candidates: list[ValueCandidate],
        decided_by: RuleId | None,
    ) -> ResolvedField | UnresolvedConflict:
        """Wrap a chosen value, unless it is still below the threshold (R-06).

        The threshold is checked after any agreement boost, so a value two weak
        scans confirm can pass where one on its own would not.
        """
        if winner is None:
            return self._conflict(entity, field, policy, candidates)

        if winner.record.confidence < self._settings.confidence_threshold:
            return UnresolvedConflict(
                entity=entity.entity,
                entity_id=entity.entity_id,
                field=field,
                candidates=candidates,
                fallback=ConflictFallback.REVIEWER,
                reason=RuleId.R_06,
            )

        agreeing = [
            candidate
            for candidate in candidates
            if self._value_key(candidate.record.value)
            == self._value_key(winner.record.value)
        ]

        return ResolvedField(
            entity=entity.entity,
            entity_id=entity.entity_id,
            field=field,
            kind=policy.kind,
            values=[winner],
            decided_by=decided_by,
            confidence=winner.record.confidence,
            agreeing_sources=sorted(
                {candidate.source.source_id for candidate in agreeing}
            ),
            discarded=[
                candidate for candidate in candidates if candidate not in agreeing
            ],
        )

    def _conflict(
        self,
        entity: MatchedEntity,
        field: FieldName,
        policy: FieldPolicy,
        candidates: list[ValueCandidate],
    ) -> UnresolvedConflict:
        """Hand the field to a person, keeping every candidate value."""
        reason = (
            RuleId.C_05
            if policy.fallback is ConflictFallback.CANDIDATE
            else RuleId.C_06
        )
        logger.debug(
            "Field %s.%s of %s goes to %s",
            entity.entity.value,
            field.value,
            entity.entity_id,
            policy.fallback.value,
        )
        return UnresolvedConflict(
            entity=entity.entity,
            entity_id=entity.entity_id,
            field=field,
            candidates=candidates,
            fallback=policy.fallback,
            reason=reason,
        )

    def _boosted(self, group: _ValueGroup) -> ValueCandidate:
        """Return the group's best candidate, with the agreement boost applied (M-04).

        The boost is added once however many sources agree, and the same value
        appearing twice inside one source is not agreement.
        """
        best = max(group, key=lambda candidate: candidate.record.confidence)
        sources = self._distinct_sources(group)
        if sources < 2:
            return best

        boosted = self._scorer.apply_agreement_boost(
            [candidate.record.confidence for candidate in group],
            agreeing_sources=sources,
        )
        if boosted <= best.record.confidence:
            return best

        status = (
            ExtractionStatus.OK
            if boosted >= self._settings.confidence_threshold
            else best.record.extraction_status
        )
        record: FieldRecord = best.record.model_copy(
            update={"confidence": boosted, "extraction_status": status}
        )
        return ValueCandidate(source=best.source, record=record)

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _fields_of(entity: MatchedEntity) -> list[FieldName]:
        """Every field any member stated, in the order they first appear."""
        fields: list[FieldName] = []
        for member in entity.members:
            for field in member.field_names:
                if field not in fields:
                    fields.append(field)
        return fields

    @staticmethod
    def _candidates_for(
        entity: MatchedEntity, field: FieldName
    ) -> list[ValueCandidate]:
        return [
            ValueCandidate(source=member.source, record=record)
            for member in entity.members
            for record in member.records_for(field)
        ]

    def _group_by_value(
        self, candidates: list[ValueCandidate]
    ) -> "OrderedDict[str, _ValueGroup]":
        """Group candidates that gave the same value after normalization."""
        groups: OrderedDict[str, _ValueGroup] = OrderedDict()
        for candidate in candidates:
            groups.setdefault(self._value_key(candidate.record.value), []).append(
                candidate
            )
        return groups

    @staticmethod
    def _value_key(value: NormalizedValue) -> str:
        """A comparable key for a normalized value.

        Text is folded for comparison so that two sources spelling a company
        with different capitalisation count as agreeing; the stored value keeps
        the winner's own spelling.
        """
        if isinstance(value, BaseModel):
            return value.model_dump_json()
        if isinstance(value, str):
            return canonical_text(value)
        return repr(value)

    @staticmethod
    def _distinct_sources(group: _ValueGroup) -> int:
        return len({candidate.source.source_id for candidate in group})

    @staticmethod
    def _newest(candidates: list[ValueCandidate]) -> ValueCandidate | None:
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate.source.uploaded_at)

    @staticmethod
    def _deterministic_tiebreak(candidates: list[ValueCandidate]) -> ValueCandidate:
        return max(
            candidates,
            key=lambda candidate: (
                candidate.record.confidence,
                candidate.source.uploaded_at,
                candidate.source.source_id,
            ),
        )
