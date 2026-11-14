"""Turn a validated LLM answer into field records (FR-035, FR-060).

For every value: check its evidence against the source text (NFR-028),
normalise it with fixed code rules (dates FR-028, countries FR-070, skills
FR-029), compute its confidence from the four factors in
:mod:`app.domain.services.confidence`, and compare that with the review limit
(FR-041, NFR-027).

There are three outcomes, and the difference between them matters:

* **accepted** — the value is in the document and scored at or above the limit.
* **flagged** — the value is in the document but something about it needs a
  person: an unreadable date, an unknown skill, a score under the limit. It is
  kept as a field record, so nothing is lost, but stays out of the live
  profile until someone decides (FR-040, FR-041).
* **rejected** — the value is *not* in the document. There is nothing to
  decide, so it becomes no field record and no review item; it goes on the
  attempt's rejected list with rule ``R-03`` so the drop can still be audited.

The confidence a value ends up with is computed here, never taken from the
model: ``field.confidence`` is stored untouched as ``model_confidence`` for
comparison and is read by nothing.
"""

import itertools
import re
from dataclasses import dataclass, field, replace

from pydantic import BaseModel

from app.application.dto.cv_extraction import CVExtraction, FlagField, Link
from app.application.dto.extracted_document import ExtractedDocument
from app.application.services.evidence_checker import EvidenceChecker
from app.domain.entities.field_record import (
    FieldRecord,
    RejectedValue,
    ReviewReason,
)
from app.domain.services.confidence import (
    DEFAULT_REVIEW_CONFIDENCE,
    ConfidenceParts,
    ConfidenceRule,
    EvidenceGrade,
    mapping_factor,
    page_base_factor,
    validation_factor,
)
from app.domain.services.contacts import (
    ContactRule,
    normalize_email,
    normalize_person_name,
    normalize_phone,
)
from app.domain.services.countries import (
    CountryCatalog,
    GeoRule,
    infer_country_code_from_city,
)
from app.domain.services.dates import (
    DateRule,
    PartialDate,
    parse_date,
    repair_date_order,
)
from app.domain.services.skills import (
    SkillCatalog,
    SkillRule,
)

DATE_FIELDS = {"start_date", "end_date", "issue_date"}
URL_FIELDS = {"url"}
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
URL_RE = re.compile(r"^(https?://)?([\w-]+\.)+[a-z]{2,}(/\S*)?$", re.IGNORECASE)

# Values the LLM classifies rather than copies: the snippet must exist,
# but the value itself is not expected to appear in it.
INTERPRETED_FIELDS = {"proficiency", "is_current", "type"}

ENTITY_LISTS = ["work_experience", "education", "skills", "certifications",
                "projects", "languages", "links"]


@dataclass
class FieldRecordSettings:
    confidence_threshold: float = DEFAULT_REVIEW_CONFIDENCE   # FR-046 review limit


@dataclass
class _Repairs:
    """What one value's normalisation had to do to it.

    The two confidence factors the rules can lower are decided by what
    happened, not by the rule id alone: a phone number cites N-PHONE-01
    whether or not a country had to be borrowed for it, and only the borrowed
    case is a repair.
    """

    repaired: bool = False     # a listed repair ran (N-DATE-03/05, N-PHONE-01)
    fuzzy: bool = False        # matched a reference table only fuzzily

    def parts(self, base: float, evidence: float) -> ConfidenceParts:
        return ConfidenceParts(
            base=base,
            evidence=evidence,
            validation=validation_factor(self.repaired),
            mapping=mapping_factor(self.fuzzy),
        )


@dataclass
class ExtractionOutcome:
    """What one source produced: records to keep, and values that were dropped."""

    records: list[FieldRecord] = field(default_factory=list)
    rejected: list[RejectedValue] = field(default_factory=list)


class FieldRecordBuilder:

    def __init__(self, countries: CountryCatalog, skills: SkillCatalog,
                 settings: FieldRecordSettings | None = None,
                 id_counter: itertools.count | None = None):
        self.countries = countries
        self.skills = skills
        self.settings = settings or FieldRecordSettings()
        self._ids = id_counter or itertools.count(1)
        self._profile_country: str | None = None

    def build(self, extraction: CVExtraction,
              document: ExtractedDocument) -> ExtractionOutcome:
        checker = EvidenceChecker(document.text, document.page_texts,
                                  document.hyperlinks)
        outcome = ExtractionOutcome()

        # The phone rule needs a country before it can turn a local number into
        # E.164, and the personal fields are processed in schema order, where
        # phone comes before country. So the country is resolved up front.
        self._profile_country = self._resolve_profile_country(extraction.personal_info)

        self._add_entity(outcome, extraction.personal_info, "personal_info",
                         "personal_info", document, checker)
        self._add_inferred_country(outcome, extraction.personal_info, document,
                                   checker)

        for entity_type in ENTITY_LISTS:
            entities = getattr(extraction, entity_type)
            if entity_type == "skills":
                entities = self._expand_combined_skills(entities)
            for index, entity in enumerate(entities, start=1):
                self._add_entity(outcome, entity, f"{entity_type}[{index}]",
                                 entity_type, document, checker)

        self._check_current_jobs(outcome.records)
        self._repair_reversed_dates(outcome.records)
        return outcome

    def _resolve_profile_country(self, personal_info) -> str | None:
        """The candidate's country code, from what the CV states or from its city.

        A stated country is always preferred, even over a city that disagrees
        with it: the candidate said it, so it is not ours to overrule.
        """
        stated = self.countries.match(personal_info.country.value)
        if stated:
            return stated.code
        return infer_country_code_from_city(personal_info.city.value)

    def _add_inferred_country(self, outcome, personal_info, document,
                              checker) -> None:
        """Record a country inferred from the city when none was stated (N-GEO-02).

        Most CVs give a city and no country, so without this the profile has no
        country at all and the candidate is invisible to anyone filtering by
        one. The record cites the city's own evidence, because the city is the
        text the country was read from, and carries the N-GEO-02 rule so it is
        never mistaken for a country the source stated (FR-035, FR-051).

        Nothing is inferred when the CV states a country, even an unlisted one:
        that value belongs in review (FR-070), not overruled by a guess.
        """
        if personal_info.country.value is not None:
            return
        city_field = personal_info.city
        if city_field.value is None:
            return
        code = infer_country_code_from_city(city_field.value)
        if code is None:
            return
        country = self.countries.by_code(code)
        if country is None:
            return

        # The country is read from the city's own text, so it exists only if the
        # city did: a city whose snippet was not in the document has already
        # been rejected, and inferring from it would reject the same snippet a
        # second time for a value the model never offered.
        if not any(r.field_name == "city" and r.entity_type == "personal_info"
                   and r.value is not None for r in outcome.records):
            return

        record = self._record(city_field, "personal_info", "personal_info",
                              "country", document, checker, outcome)
        if record is None:
            return
        record.value = country.to_dict()
        record.rule = GeoRule.INFERRED_FROM_CITY
        record.note = f"Country inferred from the city {city_field.value!r}"
        # The city was present and checked; an unknown-country reason from the
        # null original does not apply to the inferred value.
        record.review_reasons = [r for r in record.review_reasons
                                 if r != ReviewReason.UNKNOWN_COUNTRY]
        # N-GEO-02 is a fuzzy table match: the city identifies the country, but
        # the source never stated it, so it is not worth an exact read.
        self._rescore(record, mapping=mapping_factor(True))
        outcome.records.append(record)

    def _expand_combined_skills(self, skills: list) -> list:
        """One entry naming two skills becomes two entities (N-SKILL-02, FR-060).

        Each copy keeps the original entry's confidence, evidence and page: the
        snippet that proves "React/Redux" proves both halves of it.
        """
        expanded = []
        for skill in skills:
            parts = self.skills.split_entry(skill.name.value)
            if len(parts) < 2:
                expanded.append(skill)
                continue
            for part in parts:
                copy = skill.model_copy(deep=True)
                copy.name.value = part
                expanded.append(copy)
        return expanded

    def _repair_reversed_dates(self, records: list[FieldRecord]) -> None:
        """Swap a start and end date that are the wrong way round (N-DATE-05).

        Both records keep their evidence and cite the repair rule, so the
        change stays visible in the field history (FR-035). Only normalised
        month/year pairs are compared; an ongoing role has no end date to
        compare against.
        """
        by_entity: dict[str, dict[str, FieldRecord]] = {}
        for r in records:
            if r.entity_type in ("work_experience", "education") and \
                    r.field_name in ("start_date", "end_date"):
                by_entity.setdefault(r.entity, {})[r.field_name] = r

        for fields in by_entity.values():
            start, end = fields.get("start_date"), fields.get("end_date")
            if not start or not end or start.needs_review or end.needs_review:
                continue
            new_start, new_end, swapped = repair_date_order(
                _as_partial_date(start.value), _as_partial_date(end.value))
            if not swapped:
                continue
            start.value, end.value = new_start.to_dict(), new_end.to_dict()
            start.rule = end.rule = DateRule.SWAPPED
            # N-DATE-05 is a repair: the pair is right only if the swap was the
            # correct reading of a source that contradicted itself.
            for record in (start, end):
                self._rescore(record, validation=validation_factor(True))

    @staticmethod
    def _check_current_jobs(records: list[FieldRecord]) -> None:
        """A job marked ongoing that also has an end date is contradictory (FR-028)."""
        jobs: dict[str, dict[str, FieldRecord]] = {}
        for r in records:
            if r.entity_type == "work_experience":
                jobs.setdefault(r.entity, {})[r.field_name] = r
        for fields in jobs.values():
            current, end = fields.get("is_current"), fields.get("end_date")
            if current and current.value is True and end and isinstance(end.value, dict):
                end.review_reasons.append(ReviewReason.CURRENT_JOB_CONFLICT)

    def _add_entity(self, outcome, entity: BaseModel, entity_label, entity_type,
                    document, checker):
        for name in type(entity).model_fields:
            value = getattr(entity, name)
            if isinstance(entity, Link) and name == "type":
                continue  # stored together with the url record below
            if isinstance(value, list):     # e.g. project tech_stack
                for i, item in enumerate(value, start=1):
                    record = self._record(item, entity_label, entity_type,
                                          f"{name}[{i}]", document, checker, outcome)
                    if record is not None:
                        outcome.records.append(record)
                continue
            record = self._record(value, entity_label, entity_type, name,
                                  document, checker, outcome)
            if record is None:
                continue
            if isinstance(entity, Link):
                record.value = {"type": entity.type, "url": record.value}
            outcome.records.append(record)

    def _record(self, field, entity_label, entity_type, field_name,
                document, checker, outcome) -> FieldRecord | None:
        """One field record, or ``None`` when the value was rejected (R-03).

        A rejection is appended to ``outcome.rejected`` rather than returned,
        because the caller has nothing to do with a value that is not in the
        document.
        """
        raw = field.value
        record = FieldRecord(
            field_id=next(self._ids),
            source=document.source_name,
            entity=entity_label,
            entity_type=entity_type,
            field_name=field_name,
            raw_value=raw,
            value=raw,
            confidence=1.0,
            evidence=field.evidence,
            page=field.page,
            evidence_status=EvidenceGrade.NOT_REQUIRED,
            rule="llm_extraction",
            confidence_parts=ConfidenceParts(),
            # Stored for comparison only; it is not in the formula (FR-048).
            model_confidence=field.confidence,
        )

        # FR-026: a missing value is saved as null and needs no evidence.
        # is_current=false is the "nothing stated" default for the same reason.
        # Nothing was read, so there is nothing to be less than certain about.
        if raw is None or (isinstance(field, FlagField) and raw is False):
            return record

        # NFR-028: the snippet must exist in the source text and support the
        # value. A value that fails is not in the document, so it is dropped
        # under R-03 instead of being stored at a low score (FR-065).
        check = checker.check(raw, field.evidence, field.page,
                              check_value=field_name not in INTERPRETED_FIELDS)
        if not check.ok:
            outcome.rejected.append(RejectedValue(
                entity=entity_label, entity_type=entity_type, field_name=field_name,
                raw_value=raw, reason=ConfidenceRule.EVIDENCE_REJECTED,
                detail=check.detail, evidence=field.evidence, page=field.page,
            ))
            return None

        record.evidence_status = check.status
        record.page = check.page

        # Normalisation decides the validation and mapping factors, so it runs
        # before the score: otherwise a value knocked below the limit by a
        # repair would still count as accepted.
        repairs = _Repairs()
        self._normalise(record, entity_type, field_name, repairs)

        base = page_base_factor(document.page_confidence(record.page, field.evidence))
        record.confidence_parts = repairs.parts(base, check.factor)
        record.confidence = record.confidence_parts.confidence

        # FR-041 / NFR-027: below the limit a person looks at it. A page read
        # by OCR carries its own quality in `base`, so a poor scan reaches this
        # line already scored down (FR-018) — no separate flag is needed, and
        # the stored parts say which factor was responsible.
        if record.confidence < self.settings.confidence_threshold:
            record.review_reasons.append(ReviewReason.LOW_CONFIDENCE)

        return record

    def _rescore(self, record: FieldRecord, **factors) -> None:
        """Recompute a record's confidence after one factor changed.

        Used by the rules that only learn what they did after the record
        exists: a country read from a city, and a reversed date pair that can
        only be spotted once both dates are built.
        """
        parts = replace(record.confidence_parts or ConfidenceParts(), **factors)
        record.confidence_parts = parts
        record.confidence = parts.confidence

        was_low = ReviewReason.LOW_CONFIDENCE in record.review_reasons
        now_low = record.confidence < self.settings.confidence_threshold
        if now_low and not was_low:
            record.review_reasons.append(ReviewReason.LOW_CONFIDENCE)
        elif was_low and not now_low:
            record.review_reasons.remove(ReviewReason.LOW_CONFIDENCE)

    def _normalise(self, record: FieldRecord, entity_type: str, field_name: str,
                   repairs: "_Repairs") -> None:
        raw = record.raw_value

        if field_name in DATE_FIELDS:
            result = parse_date(raw)
            if result.kind == "date":
                record.value = result.date.to_dict()
                record.rule = result.rule or DateRule.MONTH
                if result.ambiguous:
                    # N-DATE-03: either part could be the month, but the year is
                    # certain, so the year is kept at year precision. Nobody is
                    # asked: the rule is deterministic and nothing is guessed;
                    # only the lost month shows up in the confidence.
                    repairs.repaired = True
            elif result.kind == "current" and field_name == "end_date":
                record.value = "current"
                record.rule = DateRule.CURRENT_MARKER
            else:
                record.review_reasons.append(ReviewReason.UNPARSEABLE_DATE)

        elif entity_type == "personal_info" and field_name == "country":
            country = self.countries.match(raw)
            if country:
                record.value = country.to_dict()
                record.rule = GeoRule.COUNTRY_LIST
            else:
                record.review_reasons.append(ReviewReason.UNKNOWN_COUNTRY)

        elif entity_type == "skills" and field_name == "name":
            standard = self.skills.lookup(raw)
            if standard:
                record.value = standard
                record.rule = "alias_table" if standard.casefold() != raw.strip().casefold() \
                    else "standard_name"
                return

            # N-SKILL-03: a misspelt known skill is not an unknown skill, so a
            # name within the allowed edit distance is mapped rather than
            # queued. The mapping factor keeps a corrected spelling from being
            # as certain as an exact match.
            fuzzy = self.skills.resolve_fuzzy(raw)
            if fuzzy:
                record.value = fuzzy
                record.rule = SkillRule.FUZZY
                repairs.fuzzy = True
                record.note = f"Read as {fuzzy!r}; the source wrote {raw.strip()!r}"
                return

            # R-09: matched nothing in the tables, so a person decides.
            record.rule = SkillRule.UNKNOWN
            record.review_reasons.append(ReviewReason.UNKNOWN_SKILL)
            hint = self.skills.suggest(raw)
            record.note = (f"Not a standard skill. Closest standard skill: {hint} "
                           f"(map it with map_to_skill), or approve it as new."
                           if hint else
                           "Not a standard skill: approve it as new, map it to an "
                           "existing skill with map_to_skill, or reject it.")

        elif field_name == "email":
            # N-EMAIL-01: lowercase, so one address is not two values of a field.
            email = normalize_email(raw)
            if email:
                record.value = email
                record.rule = ContactRule.EMAIL
            else:
                record.review_reasons.append(ReviewReason.INVALID_FORMAT)

        elif entity_type == "personal_info" and field_name == "phone":
            # N-PHONE-01: E.164, borrowing the profile country for a local number.
            phone = normalize_phone(raw, self._profile_country)
            if phone.ok:
                record.value = phone.e164
                record.rule = ContactRule.PHONE
                if phone.borrowed_country:
                    # N-PHONE-01 as a repair: the source gave a local number and
                    # the dial code came from elsewhere on the page, so the
                    # number is right only if that country is.
                    repairs.repaired = True
                    record.note = ("Country code taken from the profile country "
                                   f"{phone.borrowed_country}")
            else:
                record.review_reasons.append(ReviewReason.INVALID_FORMAT)

        elif entity_type == "personal_info" and field_name in ("first_name", "last_name"):
            # N-NAME-01: collapse spacing and title-case, keeping acronyms.
            name = normalize_person_name(raw)
            if name:
                record.value = name
                if name != raw:
                    record.rule = ContactRule.NAME

        elif field_name in URL_FIELDS and not URL_RE.match(raw.strip()):
            record.review_reasons.append(ReviewReason.INVALID_FORMAT)


def _as_partial_date(value) -> PartialDate | None:
    """Read back a normalised date record value, or None for anything else."""
    if not isinstance(value, dict) or "value" not in value:
        return None
    parts = str(value["value"]).split("-")
    try:
        year = int(parts[0])
    except (ValueError, IndexError):
        return None
    month = int(parts[1]) if len(parts) > 1 else None
    return PartialDate(year, month)
