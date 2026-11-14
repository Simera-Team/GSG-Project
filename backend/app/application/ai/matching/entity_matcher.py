"""Decides which records from different sources describe the same thing (M-01).

Field records number their entities per source, so the same job can be #1 in a
CV and #2 in LinkedIn. This module groups a source's records back into entities
and then matches those entities across sources, which is what lets the conflict
rules compare like with like.
"""

from collections.abc import Sequence

from app.application.ai.rules import RuleId
from app.application.ai.schemas.field_record import (
    EntityType,
    FieldName,
    FieldRecord,
)
from app.application.ai.schemas.merge import (
    MatchedEntity,
    SourceEntity,
    SourceExtraction,
)
from app.application.ai.schemas.normalized_value import PartialDate, PresentDate
from app.application.ai.settings import AISettings
from app.application.ai.text_matching import canonical_text, similarity

#: The field whose value identifies each kind of entity.
_IDENTITY_FIELDS: dict[EntityType, tuple[FieldName, ...]] = {
    EntityType.WORK_EXPERIENCE: (FieldName.COMPANY,),
    EntityType.EDUCATION: (FieldName.INSTITUTION,),
    EntityType.CERTIFICATION: (FieldName.NAME, FieldName.ISSUER),
    EntityType.PROJECT: (FieldName.NAME,),
    EntityType.SKILL: (FieldName.NAME,),
    EntityType.LANGUAGE: (FieldName.NAME,),
}

#: Entities whose identity also depends on their dates overlapping.
_DATE_SENSITIVE = frozenset({EntityType.WORK_EXPERIENCE, EntityType.EDUCATION})


class EntityMatcher:
    """Groups records into entities and matches them across sources."""

    def __init__(self, settings: AISettings | None = None) -> None:
        self._settings = settings or AISettings()

    def match(self, extractions: Sequence[SourceExtraction]) -> list[MatchedEntity]:
        """Return every entity across ``extractions``, newest source first.

        Sources are ordered by upload time so that "the newest source" is a
        property of a matched entity's member list, not something each rule has
        to work out again.
        """
        ordered = sorted(extractions, key=lambda item: item.meta.uploaded_at, reverse=True)

        matched: list[MatchedEntity] = []
        for extraction in ordered:
            for entity in self._group_into_entities(extraction):
                target = self._find_match(matched, entity)
                if target is None:
                    matched.append(
                        MatchedEntity(
                            entity=entity.entity,
                            entity_id=self._next_entity_id(matched, entity.entity),
                            members=[entity],
                        )
                    )
                else:
                    target.members.append(entity)
                    target.matched_by = self._match_rule(entity.entity)

        return matched

    def _group_into_entities(
        self, extraction: SourceExtraction
    ) -> list[SourceEntity]:
        """Collect one source's records into entities by their entity key."""
        grouped: dict[str, list[FieldRecord]] = {}
        kinds: dict[str, EntityType] = {}

        for record in extraction.result.fields:
            grouped.setdefault(record.entity_key, []).append(record)
            kinds[record.entity_key] = record.entity

        return [
            SourceEntity(
                source=extraction.meta,
                entity=kinds[entity_key],
                entity_key=entity_key,
                records=records,
            )
            for entity_key, records in grouped.items()
        ]

    def _find_match(
        self, matched: list[MatchedEntity], entity: SourceEntity
    ) -> MatchedEntity | None:
        """Return the entity ``entity`` belongs to, or ``None`` for a new one."""
        for existing in matched:
            if existing.entity is not entity.entity:
                continue
            if any(self._is_same(member, entity) for member in existing.members):
                return existing
        return None

    def _is_same(self, left: SourceEntity, right: SourceEntity) -> bool:
        """Whether two entities from different sources are the same thing (M-01)."""
        if left.entity is not right.entity:
            return False

        # A person's own details exist once, so the profile entity is always
        # one entity however many sources describe it.
        if left.entity is EntityType.PROFILE:
            return True

        if not self._identities_match(left, right):
            return False

        if left.entity in _DATE_SENSITIVE:
            return self._dates_allow_match(left, right)

        return True

    def _identities_match(self, left: SourceEntity, right: SourceEntity) -> bool:
        """Compare the fields that identify this kind of entity.

        A name has to match exactly after normalization or be similar enough to
        be a spelling variant; two genuinely different company names stay
        separate entities, which is why variants of a company never conflict.
        """
        fields = _IDENTITY_FIELDS.get(left.entity, (FieldName.NAME,))

        for field in fields:
            left_value = left.value_of(field)
            right_value = right.value_of(field)

            if left_value is None or right_value is None:
                # A missing identity field cannot confirm a match.
                return False

            left_text = canonical_text(str(left_value))
            right_text = canonical_text(str(right_value))

            if left_text == right_text:
                continue
            if similarity(left_text, right_text) < self._settings.entity_name_similarity:
                return False

        return True

    def _dates_allow_match(self, left: SourceEntity, right: SourceEntity) -> bool:
        """Whether two same-named entities overlap in time, or say nothing about it.

        Missing dates are treated as compatible: the same employer with no dates
        in one source is far more likely to be the same job than a second one.
        """
        left_range = _date_range(left)
        right_range = _date_range(right)

        if left_range is None or right_range is None:
            return True

        left_start, left_end = left_range
        right_start, right_end = right_range

        return left_start <= right_end and right_start <= left_end

    @staticmethod
    def _match_rule(entity: EntityType) -> RuleId | None:
        """The rule that joined two entities of this kind.

        The profile entity is not joined by any rule: a person's own details
        exist once per person, so every source describes the same one.
        """
        if entity is EntityType.PROFILE:
            return None
        if entity in {EntityType.SKILL, EntityType.LANGUAGE}:
            return RuleId.M_02
        return RuleId.M_01

    @staticmethod
    def _next_entity_id(matched: list[MatchedEntity], entity: EntityType) -> str:
        if entity is EntityType.PROFILE:
            return "profile#1"
        existing = sum(1 for item in matched if item.entity is entity)
        return f"{entity.value}#{existing + 1}"


#: An ongoing role has no end, so it is compared against this sentinel.
_OPEN_ENDED = (9999, 12, 31)


def _date_range(
    entity: SourceEntity,
) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
    """Return an entity's start and end as comparable keys, or ``None``.

    ``None`` means the entity states no usable dates at all, which the caller
    reads as "no objection to a match".
    """
    start = entity.value_of(FieldName.START_DATE)
    end = entity.value_of(FieldName.END_DATE)

    start_key = start.as_sort_key() if isinstance(start, PartialDate) else None
    if isinstance(end, PresentDate):
        end_key: tuple[int, int, int] | None = _OPEN_ENDED
    elif isinstance(end, PartialDate):
        end_key = end.as_sort_key()
    else:
        end_key = None

    if start_key is None and end_key is None:
        return None

    return (start_key or (0, 1, 1), end_key or _OPEN_ENDED)
