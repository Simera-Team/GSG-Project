"""Decide which entities from different sources are the same thing (M-01).

A candidate's CV and their LinkedIn export describe the same job twice. Before
this module the profile builder de-duplicated entities on exact field tuples,
so "Google" and "Google LLC" stayed two separate jobs: their fields never met,
and the conflict ladder (``C-``) never ran inside work experience or education.
This module groups the entities first, so the ladder has something to compare.

What identifies an entity is deliberately narrow:

* A company or institution name, compared on a key that ignores case,
  punctuation, a leading "the" and legal suffixes, with a similarity threshold
  for the rest ("Google" / "Google, Inc." / "Google LLC" are one company).
* For a job and a degree, dates that overlap, or that are not stated. Two
  non-overlapping spells at one employer are two jobs, not one: a promotion is
  a second row in a CV and should stay one.
* Nothing else. A job title is **not** part of the match, and neither is a
  degree level: those are fields of a matched entity, and a disagreement about
  them is a conflict for ``C-02``/``C-03`` or a reviewer (``C-06``) to settle,
  not a reason to call two records different jobs.

Two rules hold for every kind of entity:

* Two entities from the **same** source are never merged. Two jobs at one
  company in one CV are two jobs, whatever they look like.
* A group therefore holds at most one entity per source.

Sources are processed in a fixed order — upload time, then source id — and the
result never depends on the order the records arrive in (FR-034, NFR-023).
Everything here is a pure function: no I/O, no clock, no randomness, no LLM.

Where an entity could be matched with more than one entity from another
source, nothing is merged: the entity is kept on its own and a person is asked
(``R-10``), because picking one of two equally good candidates would be a
guess, which is exactly what these rules exist to avoid.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

from app.domain.entities.field_record import FieldRecord


class MatchRule:
    """Identifier stored on a profile record for the rule that matched it."""

    SAME_ENTITY = "M-01"     # entities from two sources are the same thing
    AMBIGUOUS = "R-10"       # more than one candidate; a person decides


#: Two names count as the same when their keys are this similar. 0.90 keeps
#: "Google" and "Googel" together while leaving "Google" and "Apple" apart.
MIN_NAME_SIMILARITY = 0.90

#: Entity types whose cross-source duplicates this module matches. Skills,
#: languages and links are merged as unions of a single value elsewhere
#: (M-02 / FR-030), so they stay one entity per source here.
MATCHED_ENTITY_TYPES: tuple[str, ...] = (
    "work_experience", "education", "certifications", "projects",
)

#: Legal forms that say nothing about which company a name refers to. Compared
#: after punctuation is removed, so "L.L.C" arrives here as "llc".
COMPANY_SUFFIXES = frozenset({
    "llc", "inc", "incorporated", "ltd", "limited", "co", "corp",
    "corporation", "company", "gmbh", "plc", "llp", "sa", "pvt",
})

#: How institutions get shortened on a CV. Written out before two names are
#: compared, because "Univ. of Jordan" against "University of Jordan" is one
#: institution and scores only 0.82 as raw text — below the threshold, so
#: without this the two would stay separate entries. Keys are the forms left
#: after punctuation is removed, which is where "univ." arrives as "univ".
INSTITUTION_ABBREVIATIONS: Mapping[str, str] = {
    "univ": "university",
    "inst": "institute",
    "tech": "technology",
    "coll": "college",
    "dept": "department",
}

#: An ongoing role has no end, so it is compared against this sentinel rather
#: than against today's date, which no rule here may read (FR-034).
OPEN_END = (9999, 12)

#: Marker value a normalised ``end_date`` record carries for an ongoing role.
_CURRENT = "current"

_DROPPED_PUNCTUATION = re.compile(r"[.'’]")
_OTHER_PUNCTUATION = re.compile(r"[^0-9a-z\s]+")
_WHITESPACE = re.compile(r"\s+")
_ENTITY_INDEX = re.compile(r"\[(\d+)\]\s*$")

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# name keys
# ---------------------------------------------------------------------------

def normalized_name(value: object | None) -> str:
    """``value`` folded so that only a difference in content shows.

    Case, accents, dots, apostrophes and any other punctuation go, and runs of
    whitespace collapse to one space. A dot is removed rather than replaced by
    a space so that "L.L.C" and "S.A" arrive as single words.
    """
    if not isinstance(value, str):
        return ""
    folded = unicodedata.normalize("NFKC", value).casefold()
    folded = _DROPPED_PUNCTUATION.sub("", folded)
    folded = _OTHER_PUNCTUATION.sub(" ", folded)
    return _WHITESPACE.sub(" ", folded).strip()


def company_key(value: object | None) -> str:
    """The part of a company name that identifies the company.

    "Google LLC", "google, inc." and "Google" all give ``"google"``; "The Walt
    Disney Company" gives ``"walt disney"``. The last token is never removed if
    it is all that is left, so a company genuinely named after a legal form
    does not reduce to nothing.
    """
    tokens = _without_leading_the(normalized_name(value).split())
    while len(tokens) > 1 and tokens[-1] in COMPANY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def institution_key(value: object | None) -> str:
    """The part of an institution name that identifies the institution.

    Common abbreviations are written out first, so "Univ. of Jordan" and
    "University of Jordan" are one institution.

    Legal suffixes are *not* dropped here: "University", "College" and
    "Institute" are what such names are made of, and removing them would make
    two unrelated institutions in one city look alike.
    """
    tokens = _without_leading_the(normalized_name(value).split())
    return " ".join(INSTITUTION_ABBREVIATIONS.get(token, token) for token in tokens)


def _without_leading_the(tokens: list[str]) -> list[str]:
    return tokens[1:] if len(tokens) > 1 and tokens[0] == "the" else list(tokens)


def similarity(left: str, right: str) -> float:
    """How similar two keys are, from 0 to 1 (stdlib only, order-independent)."""
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def keys_match(left: str, right: str) -> bool:
    """Whether two name keys refer to the same thing.

    An empty key cannot confirm anything, so it never matches: a nameless
    entity stays on its own rather than being merged into the first candidate.
    """
    if not left or not right:
        return False
    return left == right or similarity(left, right) >= MIN_NAME_SIMILARITY


def _equal_or_missing(left: object | None, right: object | None) -> bool:
    """Whether two optional values agree, counting a missing value as agreement.

    Used for a field that narrows a match without being able to rule one out:
    a CV that does not name the field of study does not thereby describe a
    different degree.
    """
    left_key = normalized_name(left)
    right_key = normalized_name(right)
    if not left_key or not right_key:
        return True
    return left_key == right_key


# ---------------------------------------------------------------------------
# dates
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DateRange:
    """An entity's span, as far as its source states it.

    ``start`` and ``end`` are ``(year, month)`` keys. A year-only start counts
    as January and a year-only end as December, which is the widest reading the
    source supports and so the one that does not invent a gap. ``end`` is
    :data:`OPEN_END` for an ongoing role. ``None`` means the source did not say.
    """

    start: tuple[int, int] | None = None
    end: tuple[int, int] | None = None

    @property
    def stated(self) -> bool:
        """Whether both ends are known, so the range can rule a match out."""
        return self.start is not None and self.end is not None


def _partial_date(value: object | None) -> tuple[int, int | None] | None:
    """Read a normalised date record value back as ``(year, month | None)``."""
    if not isinstance(value, Mapping):
        return None
    parts = str(value.get("value", "")).split("-")
    if not parts or not parts[0].isdigit():
        return None
    month = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    return int(parts[0]), month if month and 1 <= month <= 12 else None


def date_range(start: object | None, end: object | None,
               is_current: object | None = None) -> DateRange:
    """The span an entity's date fields describe.

    ``end`` may be the ongoing-role marker a normalised record carries, or
    ``is_current`` may say the same thing on its own field; either one makes
    the range open-ended. Today's date is never consulted.
    """
    parsed_start = _partial_date(start)
    start_key = (parsed_start[0], parsed_start[1] or 1) if parsed_start else None

    if is_current is True or (isinstance(end, str) and end.strip().casefold() == _CURRENT):
        return DateRange(start_key, OPEN_END)

    parsed_end = _partial_date(end)
    end_key = (parsed_end[0], parsed_end[1] or 12) if parsed_end else None
    return DateRange(start_key, end_key)


def ranges_allow_match(left: DateRange, right: DateRange) -> bool:
    """Whether two spans can belong to the same entity.

    Overlapping spans can. So can a span that one source left open at either
    end: a CV that gives no dates for a job is far more likely to be the job
    LinkedIn dates than a second one. Two fully stated spans that do not
    overlap cannot — at one employer that is a promotion, which is two rows.
    """
    if not left.stated or not right.stated:
        return True
    return left.start <= right.end and right.start <= left.end


# ---------------------------------------------------------------------------
# entities
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceEntity:
    """One entity as a single source describes it: its records, keyed by field."""

    source: str
    entity: str                      # e.g. "work_experience[2]"
    entity_type: str                 # e.g. "work_experience"
    uploaded_at: datetime | None
    fields: Mapping[str, FieldRecord]

    @property
    def entity_id(self) -> str:
        """Identity of this entity within its source, stable across rebuilds."""
        return f"{self.source}:{self.entity}"

    @property
    def order_key(self) -> tuple:
        """Position in the fixed source order: upload time, source id, index."""
        return (_source_order(self.uploaded_at, self.source), _entity_order(self.entity))

    def value(self, field_name: str) -> object | None:
        record = self.fields.get(field_name)
        return record.value if record else None

    @property
    def date_range(self) -> DateRange:
        return date_range(self.value("start_date"), self.value("end_date"),
                          self.value("is_current"))

    def identifying_record(self) -> FieldRecord | None:
        """The record whose value names this entity, for a review item's option."""
        for name in ("company", "institution", "name"):
            record = self.fields.get(name)
            if record is not None and record.value is not None:
                return record
        return next(iter(self.fields.values()), None)

    def label(self) -> str:
        """A short human description, for a reviewer choosing between candidates."""
        for name in ("company", "institution", "name"):
            value = self.value(name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return self.entity


@dataclass(frozen=True)
class EntityGroup:
    """Entities from different sources that describe one thing.

    A group with one member is an entity only one source mentioned, which is
    the normal case; ``merged`` tells the two apart, because only a group that
    actually brought sources together cites M-01 on the profile record.
    """

    entity_type: str
    members: tuple[SourceEntity, ...]
    #: Entities this group could equally have joined. Non-empty means nothing
    #: was merged and a person is asked instead (R-10).
    ambiguous_with: tuple[SourceEntity, ...] = ()

    @property
    def ambiguous_ids(self) -> tuple[str, ...]:
        return tuple(entity.entity_id for entity in self.ambiguous_with)

    @property
    def entity_id(self) -> str:
        """The id of the earliest member, so it survives a newer source arriving."""
        return self.members[0].entity_id

    @property
    def merged(self) -> bool:
        return len(self.members) > 1

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(member.source for member in self.members)

    @property
    def field_names(self) -> tuple[str, ...]:
        """Every field any member states, in a fixed order."""
        return tuple(sorted({name for member in self.members for name in member.fields}))

    @property
    def field_ids(self) -> list[int]:
        """Every field record that fed this group (FR-063)."""
        return sorted({record.field_id
                       for member in self.members
                       for record in member.fields.values()})

    def records_for(self, field_name: str) -> list[FieldRecord]:
        """One member's record for ``field_name`` per member that states it."""
        return [member.fields[field_name] for member in self.members
                if field_name in member.fields]

    @property
    def first_fields(self) -> Mapping[str, FieldRecord]:
        """The earliest member's records, for entities that are never merged."""
        return self.members[0].fields


@dataclass(frozen=True)
class MatchResult:
    """Every entity of a candidate, grouped across their sources."""

    groups: tuple[EntityGroup, ...]

    def of_type(self, entity_type: str) -> list[EntityGroup]:
        return [group for group in self.groups if group.entity_type == entity_type]

    @property
    def ambiguous(self) -> list[EntityGroup]:
        return [group for group in self.groups if group.ambiguous_with]


# ---------------------------------------------------------------------------
# the match rules per entity type
# ---------------------------------------------------------------------------

def same_entity(left: SourceEntity, right: SourceEntity) -> bool:
    """Whether two entities from different sources are the same thing (M-01).

    Two entities from the same source are never the same thing, however alike
    they look: a CV listing one company twice is listing two jobs.
    """
    if left.entity_type != right.entity_type:
        return False
    if left.source == right.source:
        return False

    if left.entity_type == "work_experience":
        return _same_job(left, right)
    if left.entity_type == "education":
        return _same_study(left, right)
    if left.entity_type == "certifications":
        return _same_certification(left, right)
    if left.entity_type == "projects":
        return _same_project(left, right)
    return False


def _same_job(left: SourceEntity, right: SourceEntity) -> bool:
    """Same company and a span that can be the same spell of work.

    The title is not consulted: "Engineer" and "Senior Engineer" at one company
    over one span is one job described twice, and which title to keep is a
    field conflict (C-02 / C-03), not a matching question.
    """
    if not keys_match(company_key(left.value("company")),
                      company_key(right.value("company"))):
        return False
    return ranges_allow_match(left.date_range, right.date_range)


def _same_study(left: SourceEntity, right: SourceEntity) -> bool:
    """Same institution, the same field of study where both name one, same span.

    The degree level is not consulted, so a bachelor's in one source and a
    master's in the other at one institution becomes one entry with a field
    conflict for a reviewer (C-06) rather than two silently separate degrees.
    """
    if not keys_match(institution_key(left.value("institution")),
                      institution_key(right.value("institution"))):
        return False
    if not _equal_or_missing(left.value("field"), right.value("field")):
        return False
    return ranges_allow_match(left.date_range, right.date_range)


def _same_certification(left: SourceEntity, right: SourceEntity) -> bool:
    """Same name exactly, and the same issuer where both name one.

    A certification name is a proper title awarded by one body, so it is
    matched exactly rather than fuzzily: "AWS Developer" and "AWS Architect"
    are similar strings and different certificates.
    """
    left_name = normalized_name(left.value("name"))
    right_name = normalized_name(right.value("name"))
    if not left_name or left_name != right_name:
        return False
    return _equal_or_missing(left.value("issuer"), right.value("issuer"))


def _same_project(left: SourceEntity, right: SourceEntity) -> bool:
    """Same name exactly. A project has nothing else that identifies it."""
    left_name = normalized_name(left.value("name"))
    return bool(left_name) and left_name == normalized_name(right.value("name"))


# ---------------------------------------------------------------------------
# grouping
# ---------------------------------------------------------------------------

def match_entities(records: Iterable[FieldRecord]) -> MatchResult:
    """Group ``records`` into entities and match those across sources (M-01).

    ``records`` are the accepted field records of one candidate, from every
    source. Personal details are left out: a person exists once, and their
    fields are resolved without any matching.

    The same records always give the same groups, in the same order, whatever
    order they arrive in (FR-034, NFR-023).
    """
    entities = _collect(records)

    groups: list[EntityGroup] = []
    for entity_type in _entity_types(entities):
        of_type = [entity for entity in entities if entity.entity_type == entity_type]
        if entity_type in MATCHED_ENTITY_TYPES:
            groups.extend(_match_one_type(entity_type, of_type))
        else:
            # Never matched across sources; one group per entity keeps the
            # caller's handling of these types uniform.
            groups.extend(EntityGroup(entity_type, (entity,)) for entity in of_type)

    return MatchResult(tuple(groups))


def _collect(records: Iterable[FieldRecord]) -> list[SourceEntity]:
    """One :class:`SourceEntity` per (source, entity), in the fixed order."""
    grouped: dict[tuple[str, str], dict[str, FieldRecord]] = {}
    meta: dict[tuple[str, str], FieldRecord] = {}

    for record in records:
        if record.entity_type == "personal_info":
            continue
        key = (record.source, record.entity)
        grouped.setdefault(key, {})[record.field_name] = record
        meta.setdefault(key, record)

    entities = [
        SourceEntity(
            source=source,
            entity=entity,
            entity_type=meta[(source, entity)].entity_type,
            uploaded_at=meta[(source, entity)].source_uploaded_at,
            fields=fields,
        )
        for (source, entity), fields in grouped.items()
    ]
    return sorted(entities, key=lambda entity: entity.order_key)


def _entity_types(entities: Sequence[SourceEntity]) -> list[str]:
    """The entity types present, matched ones first and otherwise as they came."""
    present = {entity.entity_type for entity in entities}
    matched = [name for name in MATCHED_ENTITY_TYPES if name in present]
    rest: list[str] = []
    for entity in entities:
        if entity.entity_type not in MATCHED_ENTITY_TYPES and entity.entity_type not in rest:
            rest.append(entity.entity_type)
    return matched + rest


def _match_one_type(entity_type: str,
                    entities: Sequence[SourceEntity]) -> list[EntityGroup]:
    """Group one entity type's entities across sources.

    Candidates are worked out for every entity first and only then merged, so
    an entity that two others could claim is found however the entities are
    ordered. Only a pair that is each other's *only* candidate in the other's
    source is merged; anything less is ambiguous and merged with nothing.
    """
    candidates = _candidates(entities)
    ambiguous = {index: _candidate_entities(entities, found)
                 for index, found in candidates.items()
                 if any(len(matches) > 1 for matches in found.values())}

    parent = list(range(len(entities)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    members: dict[int, list[int]] = {index: [index] for index in range(len(entities))}

    for left in range(len(entities)):
        if left in ambiguous:
            continue
        for right in range(left + 1, len(entities)):
            if right in ambiguous:
                continue
            if candidates[left].get(entities[right].source) != [right]:
                continue
            if candidates[right].get(entities[left].source) != [left]:
                continue

            left_root, right_root = root(left), root(right)
            if left_root == right_root:
                continue
            # A group holds at most one entity per source; a chain of matches
            # that would break that is not a match this rule can make.
            if {entities[i].source for i in members[left_root]} & \
               {entities[i].source for i in members[right_root]}:
                continue
            parent[right_root] = left_root
            members[left_root] += members.pop(right_root)

    groups = [
        EntityGroup(
            entity_type=entity_type,
            members=tuple(entities[i] for i in sorted(found,
                                                      key=lambda i: entities[i].order_key)),
            ambiguous_with=ambiguous.get(found[0], ()) if len(found) == 1 else (),
        )
        for found in members.values()
    ]
    return sorted(groups, key=lambda group: group.members[0].order_key)


def _candidates(entities: Sequence[SourceEntity]) -> dict[int, dict[str, list[int]]]:
    """For each entity, the entities of every *other* source it could be."""
    found: dict[int, dict[str, list[int]]] = {index: {} for index in range(len(entities))}
    for left in range(len(entities)):
        for right in range(len(entities)):
            if left == right:
                continue
            if same_entity(entities[left], entities[right]):
                found[left].setdefault(entities[right].source, []).append(right)
    return found


def _candidate_entities(entities: Sequence[SourceEntity],
                        found: Mapping[str, list[int]]) -> tuple[SourceEntity, ...]:
    """Every candidate an entity could be, in the fixed order."""
    indexes = sorted({index for matches in found.values() for index in matches},
                     key=lambda index: entities[index].order_key)
    return tuple(entities[index] for index in indexes)


# ---------------------------------------------------------------------------
# the fixed order
# ---------------------------------------------------------------------------

def _source_order(uploaded_at: datetime | None, source: str) -> tuple:
    """Sources in the fixed order: upload time, then source id.

    A source with no upload time sorts first, and source ids are compared as
    numbers where they are numbers, so file 9 comes before file 10.
    """
    stamp = _as_utc(uploaded_at) if uploaded_at is not None else _EPOCH
    return (stamp, (0, int(source), "") if source.isdigit() else (1, 0, source))


def _entity_order(entity: str) -> tuple:
    """Entities within a source in the order the source listed them."""
    match = _ENTITY_INDEX.search(entity)
    if match:
        return (0, int(match.group(1)), entity)
    return (1, 0, entity)


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
