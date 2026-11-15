"""Turn a validated LLM answer into field records (FR-035, FR-060).

For every value: check evidence (NFR-028), check confidence against the
review limit (FR-041, NFR-027), normalise it with fixed code rules
(dates FR-028, countries FR-070, skills FR-029), and mark it for review
when any check fails. A flagged value is kept as a field record (nothing
is lost) but is not used in the live profile (FR-040).
"""

import itertools
import re
from dataclasses import dataclass

from pydantic import BaseModel

from app.application.dto.cv_extraction import CVExtraction, FlagField, Link
from app.application.dto.extracted_document import ExtractedDocument
from app.application.services.evidence_checker import EvidenceChecker
from app.domain.entities.field_record import FieldRecord, ReviewReason
from app.domain.services.countries import CountryCatalog
from app.domain.services.dates import parse_date
from app.domain.services.skills import SkillCatalog

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
    confidence_threshold: float = 0.6     # FR-046 default review limit


class FieldRecordBuilder:

    def __init__(self, countries: CountryCatalog, skills: SkillCatalog,
                 settings: FieldRecordSettings | None = None,
                 id_counter: itertools.count | None = None):
        self.countries = countries
        self.skills = skills
        self.settings = settings or FieldRecordSettings()
        self._ids = id_counter or itertools.count(1)

    def build(self, extraction: CVExtraction, document: ExtractedDocument) -> list[FieldRecord]:
        checker = EvidenceChecker(
            document.text, document.page_texts, document.hyperlinks,
            allow_fuzzy=document.extraction_method in ("ocr", "mixed"),
        )
        low_ocr = (document.ocr_confidence is not None
                   and document.ocr_confidence < self.settings.confidence_threshold)

        records: list[FieldRecord] = []
        self._add_entity(records, extraction.personal_info, "personal_info",
                         "personal_info", document, checker, low_ocr)

        for entity_type in ENTITY_LISTS:
            for index, entity in enumerate(getattr(extraction, entity_type), start=1):
                self._add_entity(records, entity, f"{entity_type}[{index}]",
                                 entity_type, document, checker, low_ocr)

        self._check_current_jobs(records)
        return records

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

    def _add_entity(self, records, entity: BaseModel, entity_label, entity_type,
                    document, checker, low_ocr):
        for name in type(entity).model_fields:
            value = getattr(entity, name)
            if isinstance(entity, Link) and name == "type":
                continue  # stored together with the url record below
            if isinstance(value, list):     # e.g. project tech_stack
                for i, item in enumerate(value, start=1):
                    records.append(self._record(item, entity_label, entity_type,
                                                f"{name}[{i}]", document, checker, low_ocr))
                continue
            record = self._record(value, entity_label, entity_type, name,
                                  document, checker, low_ocr)
            if isinstance(entity, Link):
                record.value = {"type": entity.type, "url": record.value}
            records.append(record)

    def _record(self, field, entity_label, entity_type, field_name,
                document, checker, low_ocr) -> FieldRecord:
        raw = field.value
        record = FieldRecord(
            field_id=next(self._ids),
            source=document.source_name,
            entity=entity_label,
            entity_type=entity_type,
            field_name=field_name,
            raw_value=raw,
            value=raw,
            confidence=field.confidence,
            evidence=field.evidence,
            page=field.page,
            evidence_status="not_required",
            rule="llm_extraction",
        )

        # FR-026: a missing value is saved as null and needs no evidence.
        # is_current=false is the "nothing stated" default for the same reason.
        if raw is None or (isinstance(field, FlagField) and raw is False):
            return record

        reasons = record.review_reasons

        # NFR-028: evidence must exist in the source text.
        check = checker.check(raw, field.evidence, field.page,
                              check_value=field_name not in INTERPRETED_FIELDS)
        record.evidence_status = check.status
        record.page = check.page
        if check.status == "missing":
            reasons.append(ReviewReason.EVIDENCE_MISSING)
        elif check.status == "not_found":
            reasons.append(ReviewReason.EVIDENCE_NOT_FOUND)
        elif not check.value_supported:
            reasons.append(ReviewReason.VALUE_NOT_IN_EVIDENCE)

        # FR-041 / NFR-027 / FR-018
        if field.confidence < self.settings.confidence_threshold:
            reasons.append(ReviewReason.LOW_CONFIDENCE)
        if low_ocr:
            reasons.append(ReviewReason.LOW_OCR_CONFIDENCE)

        self._normalise(record, entity_type, field_name)
        return record

    def _normalise(self, record: FieldRecord, entity_type: str, field_name: str) -> None:
        raw = record.raw_value

        if field_name in DATE_FIELDS:
            result = parse_date(raw)
            if result.kind == "date":
                record.value = result.date.to_dict()
                record.rule = "date_normalized"
            elif result.kind == "current" and field_name == "end_date":
                record.value = "current"
                record.rule = "date_current_marker"
            else:
                record.review_reasons.append(ReviewReason.UNPARSEABLE_DATE)

        elif entity_type == "personal_info" and field_name == "country":
            country = self.countries.match(raw)
            if country:
                record.value = country.to_dict()
                record.rule = "country_list"
            else:
                record.review_reasons.append(ReviewReason.UNKNOWN_COUNTRY)

        elif entity_type == "skills" and field_name == "name":
            standard = self.skills.lookup(raw)
            if standard:
                record.value = standard
                record.rule = "alias_table" if standard.casefold() != raw.strip().casefold() \
                    else "standard_name"
            else:
                record.review_reasons.append(ReviewReason.UNKNOWN_SKILL)
                hint = self.skills.suggest(raw)
                record.note = (f"Not a standard skill. Closest standard skill: {hint} "
                               f"(map it with map_to_skill), or approve it as new."
                               if hint else
                               "Not a standard skill: approve it as new, map it to an "
                               "existing skill with map_to_skill, or reject it.")

        elif field_name == "email" and not EMAIL_RE.match(raw.strip()):
            record.review_reasons.append(ReviewReason.INVALID_FORMAT)

        elif field_name in URL_FIELDS and not URL_RE.match(raw.strip()):
            record.review_reasons.append(ReviewReason.INVALID_FORMAT)
