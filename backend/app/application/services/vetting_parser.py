"""Parse a vetting result into field records, with no LLM (FR-056, FR-057).

A vetting result is structured data the platform produced itself, so there is
nothing to extract and nothing to doubt: every value has confidence 1.0, its
evidence is the payload entry it came from, and no model is asked anything.
That is also why the kind matters downstream — a vetted value beats anything
a candidate claims about themselves (FR-032, rule C-01), and without this
parser no vetted record ever exists for that rule to find.

Expected payload::

    {"skills":    [{"name": "React", "level": 4}, ...],
     "languages": [{"name": "English", "proficiency": "fluent"}, ...]}

A skill that is not on the standard list, or a level outside 1 to 5, is
rejected and queued for a person rather than stored (FR-056). Anything else
in the payload is ignored rather than guessed at.
"""

import itertools
import json
from dataclasses import dataclass, field
from typing import Any

from app.domain.entities.field_record import FieldRecord, ReviewReason
from app.domain.services.skills import SkillCatalog

#: FR-056: a vetting level outside this range is not a level.
MIN_LEVEL = 1
MAX_LEVEL = 5

VETTING_RULE = "vetting_record"

PROFICIENCY_LEVELS = {"native", "fluent", "intermediate", "basic"}

#: A vetting level mapped onto the profile's language proficiency vocabulary,
#: used only when a language entry gives a level instead of a word.
LEVEL_TO_PROFICIENCY = {5: "native", 4: "fluent", 3: "intermediate",
                        2: "basic", 1: "basic"}


@dataclass
class VettedSkill:
    """One vetted skill level, ready for the vetting_record table (FR-056)."""

    skill_name: str          # standard name
    level: int


@dataclass
class VettingParseResult:
    records: list[FieldRecord] = field(default_factory=list)
    skills: list[VettedSkill] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class VettingPayloadError(ValueError):
    """The payload is not a vetting result at all."""


class VettingParser:
    """Turns a vetting payload into the same field records extraction produces.

    Both paths produce :class:`FieldRecord`, so nothing downstream needs to
    know which kind of source a value came from — only its ``source_kind``,
    which is what the conflict rules read.
    """

    def __init__(self, skills: SkillCatalog,
                 id_counter: itertools.count | None = None):
        self.skills = skills
        self._ids = id_counter or itertools.count(1)

    def parse(self, raw: bytes | str, source_name: str) -> VettingParseResult:
        payload = self._load(raw)
        result = VettingParseResult()

        for index, entry in enumerate(payload.get("skills") or [], start=1):
            self._add_skill(entry, index, source_name, result)

        for index, entry in enumerate(payload.get("languages") or [], start=1):
            self._add_language(entry, index, source_name, result)

        return result

    # ---- skills ----

    def _add_skill(self, entry: Any, index: int, source_name: str,
                   result: VettingParseResult) -> None:
        name = _text(entry, "name")
        level = _int(entry, "level")

        if name is None:
            result.errors.append(f"skills[{index}]: no skill name")
            return

        record = self._record(source_name, f"skills[{index}]", "skills",
                              "name", name)

        standard = self.skills.lookup(name)
        if standard is None:
            # FR-056 / FR-062: an unknown skill is kept and queued, never
            # silently stored and never silently dropped.
            record.review_reasons.append(ReviewReason.UNKNOWN_SKILL)
            hint = self.skills.suggest(name)
            record.note = (f"Vetted skill is not on the standard list. Closest: {hint}."
                           if hint else
                           "Vetted skill is not on the standard list.")
            result.records.append(record)
            result.errors.append(f"skills[{index}]: unknown skill {name!r}")
            return

        record.value = standard
        record.rule = VETTING_RULE

        if level is None or not MIN_LEVEL <= level <= MAX_LEVEL:
            # FR-056: a level outside 1 to 5 is rejected. The skill itself is
            # still recorded, because the candidate does have the skill.
            record.review_reasons.append(ReviewReason.INVALID_FORMAT)
            record.note = f"Vetting level {level!r} is outside {MIN_LEVEL} to {MAX_LEVEL}"
            result.records.append(record)
            result.errors.append(
                f"skills[{index}]: level {level!r} outside {MIN_LEVEL}-{MAX_LEVEL}")
            return

        result.records.append(record)
        # FR-057: stored so anyone can see the level is verified, not claimed.
        result.skills.append(VettedSkill(standard, level))

    # ---- languages ----

    def _add_language(self, entry: Any, index: int, source_name: str,
                      result: VettingParseResult) -> None:
        name = _text(entry, "name")
        if name is None:
            result.errors.append(f"languages[{index}]: no language name")
            return

        entity = f"languages[{index}]"
        result.records.append(
            self._record(source_name, entity, "languages", "name", name, value=name))

        proficiency = _text(entry, "proficiency")
        resolved = None
        if proficiency and proficiency.casefold() in PROFICIENCY_LEVELS:
            resolved = proficiency.casefold()
        else:
            level = _int(entry, "level")
            if level is not None and MIN_LEVEL <= level <= MAX_LEVEL:
                resolved = LEVEL_TO_PROFICIENCY[level]

        record = self._record(source_name, entity, "languages", "proficiency",
                              proficiency or _int(entry, "level"))
        if resolved is None:
            record.review_reasons.append(ReviewReason.INVALID_FORMAT)
            record.note = "Vetting gave no usable language proficiency"
            result.errors.append(f"languages[{index}]: unusable proficiency")
        else:
            record.value = resolved
            record.rule = VETTING_RULE
        result.records.append(record)

    # ---- record shape ----

    def _record(self, source_name: str, entity: str, entity_type: str,
                field_name: str, raw_value: Any, value: Any = None) -> FieldRecord:
        """A field record for a value the platform produced itself.

        Confidence is 1.0 and the evidence is the payload entry: there is no
        document to quote and nothing was inferred, so the audit trail points
        at the vetting result instead of a snippet (FR-065).
        """
        return FieldRecord(
            field_id=next(self._ids),
            source=source_name,
            entity=entity,
            entity_type=entity_type,
            field_name=field_name,
            raw_value=raw_value,
            value=value,
            confidence=1.0,
            evidence=json.dumps({field_name: raw_value}, ensure_ascii=False),
            page=None,
            evidence_status="not_required",
            rule=VETTING_RULE,
            source_kind="vetting",
        )

    @staticmethod
    def _load(raw: bytes | str) -> dict[str, Any]:
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise VettingPayloadError("Vetting payload is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise VettingPayloadError("Vetting payload must be a JSON object")
        if not isinstance(payload.get("skills", []), list) or \
                not isinstance(payload.get("languages", []), list):
            raise VettingPayloadError(
                "Vetting payload 'skills' and 'languages' must be lists")
        return payload


def _text(item: Any, key: str) -> str | None:
    if not isinstance(item, dict):
        return None
    value = item.get(key)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _int(item: Any, key: str) -> int | None:
    if not isinstance(item, dict):
        return None
    value = item.get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None
