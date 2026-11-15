"""Build the candidate profile from field records (FR-036, FR-063, FR-038).

- Only accepted field records are used; flagged ones stay out of the live
  profile until a reviewer decides (FR-040) and become review items (FR-041).
- Every profile record lists the field records that produced it (FR-063).
- Records from several sources are merged: skills are unioned without
  repeats (FR-030); identical entities are merged; a personal-info field
  with different values from different sources is a conflict and goes to
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

from pydantic import ValidationError

from app.application.dto.profile_document import ProfileDocument
from app.domain.entities.field_record import (
    DECISION_RULE,
    FieldRecord,
    ReviewItem,
    ReviewOption,
    ReviewReason,
)

PERSONAL_FIELDS = ["first_name", "last_name", "email", "phone", "city",
                   "country", "title", "summary"]


@dataclass
class ProfileBuildResult:
    profile: ProfileDocument | None
    review_items: list[ReviewItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ProfileBuilder:

    def __init__(self, review_ids: itertools.count | None = None):
        self._review_ids = review_ids or itertools.count(1)

    def build(self, records: list[FieldRecord],
              include_field_reviews: bool = True) -> ProfileBuildResult:
        """include_field_reviews=False returns only cross-source conflicts; used
        when rebuilding a stored profile, where each file's flagged fields
        already have review items."""
        review_items: list[ReviewItem] = []

        personal = self._personal_info(records, review_items)
        # Conflicts above may have flagged more records, so collect reviews after.
        if include_field_reviews:
            review_items[:0] = [self._review_for(r) for r in records if r.needs_review
                                and ReviewReason.SOURCE_CONFLICT not in r.review_reasons]

        accepted = [r for r in records if not r.needs_review and r.value is not None]
        entities = _group_entities(accepted)

        data = {
            "personal_info": personal,
            "experience": _dedupe(
                [self._experience(e) for e in entities["work_experience"]],
                ("company", "title", "start_date")),
            "education": _dedupe(
                [self._education(e) for e in entities["education"]],
                ("institution", "degree", "field")),
            "skills": self._skills(entities["skills"]),
            "certifications": _dedupe(
                [self._simple(e, ["name", "issuer", "issue_date", "url"], "name")
                 for e in entities["certifications"]], ("name",)),
            "projects": _dedupe([self._project(e) for e in entities["projects"]], ("name",)),
            "languages": _dedupe(
                [self._simple(e, ["name", "proficiency"], "name") for e in entities["languages"]],
                ("name",)),
            "links": _dedupe([self._link(e) for e in entities["links"]], ("url",)),
        }

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
            distinct = {_key(r.value) for r in candidates}
            if len(distinct) == 1:
                info[name] = candidates[0].value
                info["field_ids"][name] = candidates[0].field_id
            elif len(distinct) > 1:
                # FR-033: sources disagree and no rule decides -> review, keep all values.
                for r in candidates:
                    r.review_reasons.append(ReviewReason.SOURCE_CONFLICT)
                review_items.append(ReviewItem(
                    review_id=next(self._review_ids),
                    source=", ".join(sorted({r.source for r in candidates})),
                    entity="personal_info",
                    field_name=name,
                    reasons=[ReviewReason.SOURCE_CONFLICT],
                    options=[_option(r) for r in candidates],
                ))
        return info

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


def _group_entities(records: list[FieldRecord]) -> dict[str, list[dict[str, FieldRecord]]]:
    groups: dict[tuple[str, str], dict[str, FieldRecord]] = {}
    for r in records:
        if r.entity_type != "personal_info":
            groups.setdefault((r.source, r.entity), {})[r.field_name] = r
    by_type: dict[str, list] = defaultdict(list)
    for (_, entity), fields in groups.items():
        by_type[entity.split("[")[0]].append(fields)
    return by_type


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
