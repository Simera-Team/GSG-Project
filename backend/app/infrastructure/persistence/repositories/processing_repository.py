"""Stores CV processing results in PostgreSQL.

Field records use the source file id (as text) as their `source`, so every
value, review option and profile skill can be traced to its file.
Nothing here commits; the use case commits once per job (NFR-026).
"""

import json
from datetime import datetime, timezone

from sqlalchemy import any_, delete, func, literal, or_, select, text
from sqlalchemy.orm import Session

from app.application.dto.profile_document import ProfileDocument
from app.application.interfaces.processing_repository import IProcessingRepository
from app.domain.entities.field_record import (
    CROSS_SOURCE_REASONS,
    FieldRecord,
    ReviewItem,
)
from app.domain.services.confidence import ConfidenceParts
from app.domain.entities.processing_attempt import ProcessingAttempt
from app.domain.entities.source_file import SourceFile
from app.infrastructure.persistence.models import (
    CertificationModel,
    CountryModel,
    EducationModel,
    ExtractedFieldModel,
    LanguageModel,
    ProcessingAttemptModel,
    ProfileContactModel,
    ProfileLinkModel,
    ProfileModel,
    ProfileSkillModel,
    ProjectModel,
    ReviewItemModel,
    ReviewOptionModel,
    SkillModel,
    SourceFileModel,
    WorkExperienceModel,
)
from app.infrastructure.persistence.repositories.file_repository import SourceFileRepository

CHILD_TABLES = (ProfileSkillModel, WorkExperienceModel, EducationModel, CertificationModel,
                ProjectModel, LanguageModel, ProfileContactModel, ProfileLinkModel)


class SqlProcessingRepository(IProcessingRepository):

    def __init__(self, db: Session):
        self.db = db

    # ---- source file ----

    def get_source_file(self, file_id: int) -> SourceFile | None:
        return SourceFileRepository(self.db).get_by_id(file_id)

    def set_file_status(self, file_id, status, *, error=None, extraction_method=None,
                        ocr_confidence=None, llm_response=None, retries=None,
                        finished=False, rule=None) -> None:
        model = self.db.get(SourceFileModel, file_id)
        model.status = status
        model.error_message = error
        if rule is not None and hasattr(model, "rule"):
            model.rule = rule
        if extraction_method is not None:
            model.extraction_method = extraction_method
        if ocr_confidence is not None:
            model.ocr_confidence = ocr_confidence
        if llm_response is not None:
            model.llm_response = llm_response
        if retries is not None:
            model.num_of_retries = retries
        model.finished_at = datetime.now(timezone.utc).replace(tzinfo=None) if finished else None
        self.db.flush()

    # ---- attempts (insert-only) ----

    def next_attempt_number(self, file_id: int) -> int:
        current = self.db.scalar(select(func.max(ProcessingAttemptModel.attempt_number))
                                 .where(ProcessingAttemptModel.file_id == file_id))
        return (current or 0) + 1

    def save_attempts(self, file_id, attempts, first_number, confidence_threshold) -> list[int]:
        models = [
            ProcessingAttemptModel(
                file_id=file_id,
                attempt_number=first_number + i,
                trigger=a.trigger.value,
                outcome=a.outcome.value,
                provider=a.provider,
                model_version=a.model_version,
                llm_response=a.llm_response,
                validation_result=a.validation_result,
                error_message=a.error,
                confidence_threshold=confidence_threshold,
                started_at=a.started_at,
                finished_at=a.finished_at,
            )
            for i, a in enumerate(attempts)
        ]
        self.db.add_all(models)
        self.db.flush()
        return [m.attempt_id for m in models]

    # ---- field records (insert-only) ----

    def save_field_records(self, file_id, attempt_id, records) -> dict[int, int]:
        pairs = []
        for r in records:
            model = ExtractedFieldModel(
                file_id=file_id,
                attempt_id=attempt_id,
                entity=r.entity,
                entity_type=r.entity_type,
                field_name=r.field_name,
                raw_value=r.raw_value,
                value=r.value,
                confidence=r.confidence,
                confidence_parts=r.confidence_parts.to_dict() if r.confidence_parts else None,
                model_confidence=r.model_confidence,
                evidence=r.evidence,
                page=r.page,
                evidence_status=r.evidence_status,
                rule=r.rule,
                review_status=r.review_status,
                review_reasons=list(r.review_reasons),
            )
            self.db.add(model)
            pairs.append((r.field_id, model))
        self.db.flush()
        return {local: model.field_id for local, model in pairs}

    def load_profile_field_records(self, profile_id: int) -> list[FieldRecord]:
        latest_valid = (
            select(func.max(ProcessingAttemptModel.attempt_id))
            .join(SourceFileModel, SourceFileModel.file_id == ProcessingAttemptModel.file_id)
            .where(SourceFileModel.profile_id == profile_id,
                   ProcessingAttemptModel.outcome == "valid")
            .group_by(ProcessingAttemptModel.file_id)
        )
        # The source's kind and arrival time come along, because the conflict
        # rules decide on them: a vetted value wins (FR-032) and otherwise the
        # newer source wins (FR-031).
        rows = self.db.execute(
            select(ExtractedFieldModel,
                   SourceFileModel.source_kind,
                   SourceFileModel.uploaded_at)
            .join(SourceFileModel, SourceFileModel.file_id == ExtractedFieldModel.file_id)
            .where(ExtractedFieldModel.attempt_id.in_(latest_valid))
            .order_by(ExtractedFieldModel.file_id, ExtractedFieldModel.field_id)
        ).all()
        return [
            FieldRecord(
                field_id=m.field_id, source=str(m.file_id), entity=m.entity,
                entity_type=m.entity_type, field_name=m.field_name,
                raw_value=m.raw_value, value=m.value, confidence=m.confidence,
                evidence=m.evidence, page=m.page, evidence_status=m.evidence_status,
                rule=m.rule or "", review_reasons=list(m.review_reasons or []),
                source_kind=source_kind, source_uploaded_at=uploaded_at,
                # Read back so a rebuild can keep explaining the score, and so
                # the agreement boost (M-04) can add to parts that exist.
                confidence_parts=_parts(m.confidence_parts),
                model_confidence=m.model_confidence,
            )
            for m, source_kind, uploaded_at in rows
        ]

    def _save_contacts(self, profile_id: int, info) -> None:
        """Write every email and phone of the profile, with its own ids (M-03)."""
        for kind, contacts in (("email", info.emails), ("phone", info.phones)):
            for contact in contacts:
                self.db.add(ProfileContactModel(
                    profile_id=profile_id, kind=kind, value=contact.value,
                    is_primary=contact.is_primary, field_ids=list(contact.field_ids),
                ))

    def save_rejected_values(self, attempt_id, rejected) -> None:
        """Store the values an R- rule dropped, with the attempt that read them.

        They belong to the attempt and not to the profile: a rejected value was
        never part of the candidate's data, only of what one model answer
        claimed (R-03, NFR-028).
        """
        attempt = self.db.get(ProcessingAttemptModel, attempt_id)
        if attempt is not None:
            attempt.rejected = [r.to_dict() for r in rejected]
            self.db.flush()

    # ---- review queue ----

    def replace_open_reviews(self, profile_id, file_id, items, field_id_map,
                             conflicts_only=False) -> None:
        is_conflict = _is_cross_source()
        query = delete(ReviewItemModel).where(ReviewItemModel.resolved.is_not(True))
        if conflicts_only:
            # Conflicts span files, so they are recomputed for the whole profile.
            # An open conflict that is still the same keeps its item (and id),
            # so a reviewer looking at it is not interrupted.
            existing = self._open_conflict_keys(profile_id)
            wanted = {_conflict_key(i.entity, i.field_name,
                                    [field_id_map.get(o.field_id, o.field_id) for o in i.options])
                      for i in items}
            stale = [rid for key, rid in existing.items() if key not in wanted]
            if stale:
                self.db.execute(delete(ReviewItemModel).where(ReviewItemModel.review_id.in_(stale)))
            items = [i for i in items if _conflict_key(
                i.entity, i.field_name,
                [field_id_map.get(o.field_id, o.field_id) for o in i.options]) not in existing]
        else:
            self.db.execute(query.where(ReviewItemModel.file_id == file_id, ~is_conflict))

        for item in items:
            model = ReviewItemModel(
                profile_id=profile_id, file_id=file_id, entity=item.entity,
                field_name=item.field_name, reasons=list(item.reasons), message=item.message,
            )
            self.db.add(model)
            self.db.flush()
            for option in item.options:
                self.db.add(ReviewOptionModel(
                    review_id=model.review_id,
                    file_id=_file_id(option.source, file_id),
                    field_id=field_id_map.get(option.field_id, option.field_id),
                    value=_as_text(option.value),
                    confidence=option.confidence,
                    evidence=option.evidence,
                    page=option.page,
                ))
        self.db.flush()

    def _open_conflict_keys(self, profile_id: int) -> dict[tuple, int]:
        is_conflict = _is_cross_source()
        rows = self.db.execute(
            select(ReviewItemModel.review_id, ReviewItemModel.entity,
                   ReviewItemModel.field_name, ReviewOptionModel.field_id)
            .outerjoin(ReviewOptionModel, ReviewOptionModel.review_id == ReviewItemModel.review_id)
            .where(ReviewItemModel.profile_id == profile_id,
                   ReviewItemModel.resolved.is_not(True), is_conflict)
        ).all()
        grouped: dict[int, tuple] = {}
        for review_id, entity, field_name, field_id in rows:
            e, f, ids = grouped.get(review_id, (entity, field_name, []))
            ids.append(field_id)
            grouped[review_id] = (e, f, ids)
        return {_conflict_key(e, f, ids): rid for rid, (e, f, ids) in grouped.items()}

    # ---- live profile (generated, never edited directly: FR-063) ----

    def set_change_context(self, user_id, reason, file_id) -> None:
        # Transaction-local settings read by the trg_profile_log trigger.
        self.db.execute(text("SELECT set_config('app.current_user_id', :u, true), "
                             "set_config('app.change_reason', :r, true), "
                             "set_config('app.change_file_id', :f, true)"),
                        {"u": str(user_id or ""), "r": reason, "f": str(file_id or "")})

    def replace_profile(self, profile_id: int, profile: ProfileDocument,
                        records: list[FieldRecord]) -> None:
        for table in CHILD_TABLES:
            self.db.execute(delete(table).where(table.profile_id == profile_id))

        info = profile.personal_info
        model = self.db.get(ProfileModel, profile_id)
        model.first_name, model.last_name = info.first_name, info.last_name
        # The primary is denormalised onto the profile so the common read needs
        # no join; every address and number lives in profile_contact below.
        model.email, model.phone = info.primary_email, info.primary_phone
        model.city = info.city
        model.title, model.summary = info.title, info.summary
        model.country_id = (
            self.db.scalar(select(CountryModel.country_id)
                           .where(CountryModel.country_code == info.country.code))
            if info.country else None
        )
        model.final_json = profile.model_dump(mode="json")

        # M-03: one row per address and number, so a candidate can be found by
        # any of them and each traces back to its field records (FR-063).
        self._save_contacts(profile_id, info)

        confidence = {r.field_id: r.confidence for r in records}
        skill_ids = dict(self.db.execute(select(SkillModel.canonical_name, SkillModel.skill_id)).all())

        for s in profile.skills:
            scores = [confidence[i] for i in s.field_ids if confidence.get(i) is not None]
            self.db.add(ProfileSkillModel(
                profile_id=profile_id, skill_id=skill_ids[s.name], level=s.level,
                verified=s.verified, confidence=max(scores) if scores else None,
                source_file_ids=sorted({int(x) for x in s.sources}), field_ids=s.field_ids,
            ))
        for e in profile.experience:
            self.db.add(WorkExperienceModel(
                profile_id=profile_id, company=e.company, title=e.title, location=e.location,
                start_date=_date(e.start_date), end_date=_date(e.end_date),
                employment_status=e.employment_status, description=e.description,
                field_ids=e.field_ids))
        for e in profile.education:
            self.db.add(EducationModel(
                profile_id=profile_id, institution=e.institution, degree=e.degree, field=e.field,
                start_date=_date(e.start_date), end_date=_date(e.end_date), field_ids=e.field_ids))
        for c in profile.certifications:
            self.db.add(CertificationModel(
                profile_id=profile_id, name=c.name, issuer=c.issuer,
                issue_date=_date(c.issue_date), url=c.url, field_ids=c.field_ids))
        for p in profile.projects:
            self.db.add(ProjectModel(
                profile_id=profile_id, name=p.name, description=p.description, url=p.url,
                tech_stack=p.tech_stack, field_ids=p.field_ids))
        for lang in profile.languages:
            self.db.add(LanguageModel(
                profile_id=profile_id, name=lang.name, proficiency=lang.proficiency,
                field_ids=lang.field_ids))
        for link in profile.links:
            self.db.add(ProfileLinkModel(
                profile_id=profile_id, type=link.type, url=link.url, field_ids=link.field_ids))
        self.db.flush()


def _parts(stored) -> ConfidenceParts | None:
    """Read stored confidence parts back, ignoring keys a later version added.

    A record written before the confidence model existed has none, and its
    score cannot be decomposed after the fact, so it stays None rather than
    being given invented parts.
    """
    if not isinstance(stored, dict):
        return None
    known = {name: stored[name] for name in
             ("base", "evidence", "validation", "mapping", "agreement")
             if isinstance(stored.get(name), (int, float))}
    return ConfidenceParts(**known) if known else None


def _is_cross_source():
    """SQL for "this review item came from comparing sources, not reading one".

    Such an item belongs to the whole profile rather than to the file that
    triggered the rebuild, so it is recomputed as a set instead of being
    replaced per file (FR-033, FR-036).
    """
    return or_(*[literal(reason) == any_(ReviewItemModel.reasons)
                 for reason in CROSS_SOURCE_REASONS])


def _conflict_key(entity, field_name, field_ids) -> tuple:
    return (entity, field_name, tuple(sorted(i for i in field_ids if i is not None)))


def _date(value) -> str | None:
    return value.value if value else None


def _file_id(source: str, default: int) -> int:
    return int(source) if source.isdigit() else default


def _as_text(value) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)
