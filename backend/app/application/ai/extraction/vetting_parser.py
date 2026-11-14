"""Parses a vetting result into field records, without an LLM.

A vetting result is structured data the platform produced itself, so there is
nothing to extract and nothing to doubt: every factor is 1.00 and the evidence
is the vetting payload rather than a span of document text. Vetted values win
over anything a candidate claims about themselves (C-01).
"""

import json
from typing import Any

from app.application.ai.rules import RuleId
from app.application.ai.schemas.document_text import SourceMeta
from app.application.ai.schemas.field_record import (
    ConfidenceParts,
    EntityType,
    EvidenceMatch,
    ExtractionResult,
    ExtractionStatus,
    FieldEvidence,
    FieldName,
    FieldRecord,
    RejectedValue,
    build_entity_key,
)
from app.application.ai.schemas.normalization import NormalizationOutcome
from app.application.ai.skills.canonicalizer import SkillCanonicalizer
from app.application.ai.normalization.vocabularies import normalize_language_proficiency

#: Confidence parts for a value the platform produced itself.
_CERTAIN = ConfidenceParts(base=1.0, evidence=1.0, validation=1.0, mapping=1.0)

#: The block id used for evidence that comes from the payload, not a document.
_VETTING_BLOCK = "vetting"


class VettingParser:
    """Turns a vetting payload into the same field records extraction produces.

    Both paths produce :class:`ExtractionResult`, so the merge stage never needs
    to know which kind of source a value came from — only its ``kind``, which
    is what C-01 looks at.
    """

    def __init__(self, skill_canonicalizer: SkillCanonicalizer | None = None) -> None:
        self._skills = skill_canonicalizer or SkillCanonicalizer()

    def parse(self, raw_json: bytes, meta: SourceMeta) -> ExtractionResult:
        """Parse ``raw_json`` into field records with confidence 1.0.

        The payload is expected to hold a ``skills`` list of ``{name, level}``
        and an optional ``languages`` list of ``{name, proficiency}``. Anything
        else is ignored rather than guessed at.
        """
        payload = self._load(raw_json)

        records: list[FieldRecord] = []
        rejected: list[RejectedValue] = []

        for index, skill in enumerate(payload.get("skills") or [], start=1):
            self._add_skill(skill, index, records, rejected)

        for index, language in enumerate(payload.get("languages") or [], start=1):
            self._add_language(language, index, records, rejected)

        return ExtractionResult(
            source_id=meta.source_id, fields=records, rejected=rejected
        )

    def _add_skill(
        self,
        skill: Any,
        index: int,
        records: list[FieldRecord],
        rejected: list[RejectedValue],
    ) -> None:
        name = self._text(skill, "name")
        if not name:
            return

        for outcome in self._skills.canonicalize(name):
            if not outcome.accepted:
                rejected.append(
                    self._rejection(EntityType.SKILL, FieldName.NAME, name, outcome)
                )
                continue

            records.append(
                self._record(
                    entity=EntityType.SKILL,
                    index=index,
                    field=FieldName.NAME,
                    raw_value=name,
                    value=outcome.value,
                    rule=outcome.rule,
                )
            )

    def _add_language(
        self,
        language: Any,
        index: int,
        records: list[FieldRecord],
        rejected: list[RejectedValue],
    ) -> None:
        proficiency = self._text(language, "proficiency")
        if not proficiency:
            return

        outcome = normalize_language_proficiency(proficiency)
        if not outcome.accepted:
            rejected.append(
                self._rejection(
                    EntityType.LANGUAGE, FieldName.PROFICIENCY, proficiency, outcome
                )
            )
            return

        records.append(
            self._record(
                entity=EntityType.LANGUAGE,
                index=index,
                field=FieldName.PROFICIENCY,
                raw_value=proficiency,
                value=outcome.value,
                rule=outcome.rule,
            )
        )

    @staticmethod
    def _record(
        *,
        entity: EntityType,
        index: int,
        field: FieldName,
        raw_value: str,
        value: Any,
        rule: RuleId | None,
    ) -> FieldRecord:
        return FieldRecord(
            entity=entity,
            entity_key=build_entity_key(entity, index),
            field=field,
            raw_value=raw_value,
            value=value,
            confidence=1.0,
            confidence_parts=_CERTAIN,
            evidence=FieldEvidence(
                block_id=_VETTING_BLOCK,
                page=1,
                snippet=raw_value,
                match=EvidenceMatch.EXACT,
            ),
            normalization=rule,
            extraction_status=ExtractionStatus.OK,
        )

    @staticmethod
    def _rejection(
        entity: EntityType,
        field: FieldName,
        raw_value: str,
        outcome: NormalizationOutcome,
    ) -> RejectedValue:
        return RejectedValue(
            entity=entity,
            field=field,
            raw_value=raw_value,
            reason=outcome.rejected_by or RuleId.R_02,
            detail=outcome.detail,
        )

    @staticmethod
    def _load(raw_json: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(raw_json)
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError("Vetting payload is not valid JSON") from error

        if not isinstance(payload, dict):
            raise ValueError("Vetting payload must be a JSON object")
        return payload

    @staticmethod
    def _text(item: Any, key: str) -> str | None:
        if not isinstance(item, dict):
            return None
        value = item.get(key)
        if not isinstance(value, str):
            return None
        return value.strip() or None
