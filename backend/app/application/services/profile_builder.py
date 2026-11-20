"""Build the candidate profile from field records (FR-036, FR-063, FR-038).

- Only accepted field records are used; flagged ones stay out of the live
  profile until a reviewer decides (FR-040) and become review items (FR-041).
- Every profile record lists the field records that produced it (FR-063).
- Records from several sources are merged: skills are unioned without
  repeats (FR-030); entities that describe the same thing are matched across
  sources by :mod:`app.domain.services.entity_matching` (M-01) and then every
  field of a matched entity goes through the same conflict ladder as a
  personal detail; a field that no rule settles is a conflict and goes to
  review with every value and its source (FR-033).
- The result must pass the Simera profile format; otherwise no profile is
  produced and the job goes to review (FR-038).

Same field records in, same profile out (FR-034, NFR-023): no LLM, no
clock, no randomness.
"""

import itertools
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import ValidationError

from app.application.dto.profile_document import ProfileDocument
from app.domain.services.conflict_rules import (
    ConflictRule,
    Fallback,
    resolve_field,
)
from app.domain.entities.field_record import (
    DECISION_RULE,
    FieldRecord,
    ReviewItem,
    ReviewOption,
    ReviewReason,
)
from app.domain.services.confidence import (
    DEFAULT_REVIEW_CONFIDENCE,
    apply_agreement_boost,
)
from app.domain.services.entity_matching import (
    EntityGroup,
    MatchRule,
    match_entities,
)

PERSONAL_FIELDS = ["first_name", "last_name", "city",
                   "country", "title", "summary"]

#: Contact fields merged as a union (M-03): no conflict, no review item.
CONTACT_LIST_FIELDS = ["email", "phone"]


@dataclass
class ProfileBuildResult:
    profile: ProfileDocument | None
    review_items: list[ReviewItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ProfileBuilder:

    def __init__(self, review_ids: itertools.count | None = None,
                 confidence_threshold: float = DEFAULT_REVIEW_CONFIDENCE):
        self._review_ids = review_ids or itertools.count(1)
        # The limit in force for this job (FR-046, FR-067). Needed here and not
        # only while records are built, because the agreement boost can lift a
        # record back over it.
        self._confidence_threshold = confidence_threshold

    def build(self, records: list[FieldRecord],
              include_field_reviews: bool = True) -> ProfileBuildResult:
        """include_field_reviews=False returns only cross-source conflicts; used
        when rebuilding a stored profile, where each file's flagged fields
        already have review items."""
        review_items: list[ReviewItem] = []

        # M-04, before anything else looks at which records are usable: two
        # sources stating the same value confirm each other, which can lift a
        # record that was held back only for a low score back to accepted.
        apply_agreement_boost(records, self._confidence_threshold)

        personal = self._personal_info(records, review_items)
        accepted = [r for r in records if not r.needs_review and r.value is not None]

        # M-01: the same job or degree from two sources becomes one entity, so
        # the conflict rules compare like with like inside it.
        matched = match_entities(accepted)
        entity_reviews: list[ReviewItem] = []

        data = {
            "personal_info": personal,
            "experience": self._entities(matched.of_type("work_experience"),
                                         self._experience, entity_reviews),
            "education": self._entities(matched.of_type("education"),
                                        self._education, entity_reviews),
            "skills": self._skills([g.first_fields for g in matched.of_type("skills")]),
            "certifications": self._entities(
                matched.of_type("certifications"),
                lambda e: self._simple(e, ["name", "issuer", "issue_date", "url"], "name"),
                entity_reviews),
            "projects": self._entities(matched.of_type("projects"),
                                       self._project, entity_reviews),
            # A language or a link is one value, merged as a union without a
            # ladder (M-02 / FR-030), so these keep their exact-value dedupe.
            "languages": _dedupe(
                [self._simple(g.first_fields, ["name", "proficiency"], "name")
                 for g in matched.of_type("languages")], ("name",)),
            "links": _dedupe([self._link(g.first_fields)
                              for g in matched.of_type("links")], ("url",)),
        }

        # Conflicts above may have flagged more records, so collect reviews after.
        if include_field_reviews:
            review_items[:0] = [self._review_for(r) for r in records if r.needs_review
                                and ReviewReason.SOURCE_CONFLICT not in r.review_reasons]
        review_items += entity_reviews

        try:
            profile = ProfileDocument.model_validate(data)
        except ValidationError as exc:
            errors = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
            review_items.append(ReviewItem(
                review_id=next(self._review_ids),
                source=", ".join(sorted({r.source for r in records})),
                reasons=[ReviewReason.PROFILE_INVALID],
                message="Built profile does not match the Simera profile format: "
                        + "; ".join(errors[:5]),
            ))
            return ProfileBuildResult(None, review_items, errors)

        return ProfileBuildResult(profile, review_items)

    # ---- personal info (one value per person) ----

    def _personal_info(self, records, review_items) -> dict:
        info: dict = {"field_ids": {}}
        by_field: dict[str, list[FieldRecord]] = defaultdict(list)
        decisions: dict[str, list[FieldRecord]] = defaultdict(list)
        for r in records:
            if r.entity_type != "personal_info" or r.needs_review:
                continue
            if r.rule == DECISION_RULE:
                decisions[r.field_name].append(r)
            elif r.value is not None:
                by_field[r.field_name].append(r)

        # M-03: contact list fields — union all accepted values, de-duplicate
        # on normalised value, primary from newest source.  Never a review item
        # or a candidate question.
        for name in CONTACT_LIST_FIELDS:
            candidates = by_field.get(name, [])
            if not candidates:
                continue

            # Group by normalised value to collect all field_ids (FR-063)
            groups: dict[str, list[FieldRecord]] = defaultdict(list)
            for r in candidates:
                groups[_key(r.value)].append(r)

            # One entry per distinct value, each keeping every record that
            # stated it, whichever source that was (FR-063).
            unique_entries = [
                (max(recs, key=_contact_recency_key), sorted(r.field_id for r in recs))
                for recs in groups.values()
            ]
            # Order: newest source (uploaded_at, then source id); within one
            # source, the first one listed. The first entry is the primary, so
            # the primary is a position rather than a second copy of a value.
            unique_entries.sort(key=lambda item: _contact_recency_key(item[0]), reverse=True)

            info[name + "s"] = [
                {"value": best.value, "is_primary": index == 0, "field_ids": field_ids}
                for index, (best, field_ids) in enumerate(unique_entries)
            ]

        for name in PERSONAL_FIELDS:
            # A reviewer's decision settles the field across all sources (FR-043);
            # the latest decision wins, and a rejection (null) leaves it empty.
            if decisions.get(name):
                latest = max(decisions[name], key=lambda r: r.field_id)
                if latest.value is not None:
                    info[name] = latest.value
                    info["field_ids"][name] = latest.field_id
                continue

            candidates = by_field.get(name, [])
            if not candidates:
                continue

            # The rules settle what they can on their own (FR-031, FR-032) and
            # a person is asked only for what is left (FR-033).
            outcome = resolve_field(candidates)

            if outcome.decided:
                info[name] = outcome.winner.value
                info["field_ids"][name] = outcome.winner.field_id
                # The rule that chose the value is recorded on the record, so
                # the profile can explain the choice later (FR-035, FR-051).
                if outcome.rule != ConflictRule.AGREED:
                    outcome.winner.rule = outcome.rule
                continue

            for r in outcome.others:
                r.review_reasons.append(ReviewReason.SOURCE_CONFLICT)
            review_items.append(ReviewItem(
                review_id=next(self._review_ids),
                source=", ".join(sorted({r.source for r in outcome.others})),
                entity="personal_info",
                field_name=name,
                reasons=[ReviewReason.SOURCE_CONFLICT],
                message=_conflict_message(outcome),
                options=[_option(r) for r in outcome.others],
            ))
        return info

    # ---- entities matched across sources (M-01) ----

    def _entities(self, groups: list[EntityGroup], make, review_items) -> list[dict]:
        """Turn matched entities into profile records.

        Each group is one entity of the profile however many sources describe
        it. Its fields go through the same ladder as a personal detail, so a
        job that two sources date differently is settled by a rule (C-02/C-04)
        instead of appearing twice; what no rule settles becomes a review item
        and is left out of the profile rather than guessed (FR-033).
        """
        built: list[dict] = []
        for group in groups:
            if group.ambiguous_with:
                review_items.append(self._ambiguous_item(group))

            item = make(self._resolve_group(group, review_items))
            if item is None:
                continue
            # FR-063: every field record that fed the entity, from every source.
            item["field_ids"] = group.field_ids
            item["entity_id"] = group.entity_id
            if group.merged:
                item["rule"] = MatchRule.SAME_ENTITY
            built.append(item)
        return built

    def _resolve_group(self, group: EntityGroup,
                       review_items: list[ReviewItem]) -> dict[str, FieldRecord]:
        """The value of each field of one entity, settled across its sources."""
        winners: dict[str, FieldRecord] = {}

        for name in group.field_names:
            outcome = resolve_field(group.records_for(name))

            if outcome.decided:
                winners[name] = outcome.winner
                # The rule that chose the value is recorded on the record, so
                # the profile can explain the choice later (FR-035, FR-051).
                if outcome.rule != ConflictRule.AGREED:
                    outcome.winner.rule = outcome.rule
                continue

            if not outcome.others:
                continue

            # FR-033: nothing unsupported is picked; every value is kept with
            # its source and a person chooses.
            for record in outcome.others:
                record.review_reasons.append(ReviewReason.SOURCE_CONFLICT)
            review_items.append(ReviewItem(
                review_id=next(self._review_ids),
                source=", ".join(sorted({r.source for r in outcome.others})),
                entity=group.entity_id,
                field_name=name,
                reasons=[ReviewReason.SOURCE_CONFLICT],
                message=_conflict_message(outcome),
                options=[_option(r) for r in outcome.others],
            ))
        return winners

    def _ambiguous_item(self, group: EntityGroup) -> ReviewItem:
        """Ask which of several candidates an entity is (R-10).

        Merging one of two equally good candidates would be a guess, so the
        entity is kept on its own and the candidates are offered to a reviewer.
        """
        entity = group.members[0]
        return ReviewItem(
            review_id=next(self._review_ids),
            source=entity.source,
            entity=group.entity_id,
            reasons=[ReviewReason.ENTITY_MATCH_AMBIGUOUS],
            message=(f"{entity.label()!r} from source {entity.source} matches "
                     f"{len(group.ambiguous_with)} entities of another source "
                     f"({', '.join(group.ambiguous_ids)}), so none of them was "
                     f"merged; a reviewer says which one it is (R-10)."),
            options=[_option(record) for record in
                     (candidate.identifying_record() for candidate in group.ambiguous_with)
                     if record is not None],
        )

    # ---- entities ----

    @staticmethod
    def _experience(e: dict[str, FieldRecord]) -> dict | None:
        if "company" not in e and "title" not in e:
            return None
        end = e.get("end_date")
        current = e.get("is_current")
        if (end and end.value == "current") or (current and current.value is True):
            status, end_value = "current", None
        elif end and isinstance(end.value, dict):
            status, end_value = "ended", end.value
        else:
            status, end_value = "unknown", None
        return {
            "company": _val(e, "company"), "title": _val(e, "title"),
            "location": _val(e, "location"), "start_date": _val(e, "start_date"),
            "end_date": end_value, "employment_status": status,
            "description": _val(e, "description"), "field_ids": _ids(e),
        }

    @staticmethod
    def _education(e) -> dict | None:
        if "institution" not in e and "degree" not in e:
            return None
        return {k: _val(e, k) for k in ["institution", "degree", "field", "start_date", "end_date"]} \
            | {"field_ids": _ids(e)}

    @staticmethod
    def _simple(e, names, required) -> dict | None:
        if required not in e:
            return None
        return {k: _val(e, k) for k in names} | {"field_ids": _ids(e)}

    @staticmethod
    def _project(e) -> dict | None:
        if "name" not in e:
            return None
        tech = [r.value for k, r in sorted(e.items()) if k.startswith("tech_stack[")]
        return {"name": _val(e, "name"), "description": _val(e, "description"),
                "url": _val(e, "url"), "tech_stack": tech, "field_ids": _ids(e)}

    @staticmethod
    def _link(e) -> dict | None:
        if "url" not in e:
            return None
        return {**e["url"].value, "field_ids": _ids(e)}

    @staticmethod
    def _skills(skill_entities: list[dict[str, FieldRecord]]) -> list[dict]:
        # FR-030: union across all sources, one entry per standard name.
        merged: dict[str, dict] = {}
        for e in skill_entities:
            record = e.get("name")
            if not record:
                continue
            entry = merged.setdefault(record.value.casefold(), {
                "name": record.value, "sources": [], "field_ids": [],
            })
            if record.source not in entry["sources"]:
                entry["sources"].append(record.source)
            entry["field_ids"].append(record.field_id)
        return list(merged.values())

    def _review_for(self, record: FieldRecord) -> ReviewItem:
        return ReviewItem(
            review_id=next(self._review_ids),
            source=record.source,
            entity=record.entity,
            field_name=record.field_name,
            reasons=list(record.review_reasons),
            message=record.note,
            options=[_option(record)],
        )


def _dedupe(items: list[dict | None], key_fields: tuple[str, ...]) -> list[dict]:
    """Merge the same entity found in several sources, keeping all field ids."""
    merged: dict[str, dict] = {}
    for item in items:
        if item is None:
            continue
        key = _key([item.get(k) for k in key_fields])
        if key in merged:
            merged[key]["field_ids"] += item["field_ids"]
        else:
            merged[key] = item
    return list(merged.values())


def _val(e: dict[str, FieldRecord], name: str):
    return e[name].value if name in e else None


def _ids(e: dict[str, FieldRecord]) -> list[int]:
    return sorted(r.field_id for r in e.values())


def _option(r: FieldRecord) -> ReviewOption:
    return ReviewOption(value=r.raw_value, source=r.source, confidence=r.confidence,
                        evidence=r.evidence, page=r.page, field_id=r.field_id)


def _key(value) -> str:
    return json.dumps(value, sort_keys=True, default=str).casefold()


def _conflict_message(outcome) -> str:
    """Say who is being asked and why, so the queue entry explains itself."""
    if outcome.ask == Fallback.CANDIDATE:
        return ("Sources disagree and no rule decides this personal detail; "
                "only the candidate can confirm it (C-05).")
    return ("Sources disagree and no rule decides; a reviewer picks from the "
            "values below or enters a corrected one (C-06).")


def _contact_recency_key(record: FieldRecord):
    """Recency key for M-03: newest source (uploaded_at, source_id); within one source, first listed."""
    uploaded = record.source_uploaded_at or datetime.min
    if uploaded.tzinfo is None:
        uploaded = uploaded.replace(tzinfo=timezone.utc)
    try:
        src_num = int(record.source)
    except (ValueError, TypeError):
        src_num = 0
    return (uploaded, src_num, str(record.source), -record.field_id)
