from datetime import datetime, timezone

from sqlalchemy import any_, func, literal, select
from sqlalchemy.orm import Session, aliased

from app.application.dto.review_views import ReviewItemView, ReviewOptionView, StoredField
from app.application.interfaces.review_repository import IReviewRepository
from app.domain.entities.field_record import DECISION_RULE
from app.infrastructure.persistence.models import (
    ExtractedFieldModel,
    ProcessingAttemptModel,
    ProfileChangeLogModel,
    ProfileModel,
    ReviewItemModel,
    ReviewOptionModel,
    SkillAliasModel,
    SkillModel,
    SourceFileModel,
    UserModel,
)

STATUSES = {"open", "waiting_candidate", "resolved", "all"}


class SqlReviewRepository(IReviewRepository):

    def __init__(self, db: Session):
        self.db = db

    # ---- reading the queue ----

    def list_items(self, status, reason, profile_id, limit, offset):
        query = self._base_query()
        if status == "open":
            query = query.where(ReviewItemModel.resolved.is_not(True))
        elif status == "waiting_candidate":
            query = query.where(ReviewItemModel.resolved.is_not(True),
                                ReviewItemModel.assigned_to_candidate.is_(True))
        elif status == "resolved":
            query = query.where(ReviewItemModel.resolved.is_(True))
        if reason:
            query = query.where(literal(reason) == any_(ReviewItemModel.reasons))
        if profile_id is not None:
            query = query.where(ReviewItemModel.profile_id == profile_id)

        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.db.execute(query.order_by(ReviewItemModel.created_at, ReviewItemModel.review_id)
                               .limit(limit).offset(offset)).all()
        return total, self._with_options(rows)

    def get_item(self, review_id, lock=False):
        if lock:
            # Row lock: a second reviewer waits, then sees the item as resolved.
            self.db.execute(select(ReviewItemModel.review_id)
                            .where(ReviewItemModel.review_id == review_id).with_for_update())
        rows = self.db.execute(self._base_query()
                               .where(ReviewItemModel.review_id == review_id)).all()
        items = self._with_options(rows)
        return items[0] if items else None

    def _base_query(self):
        candidate = aliased(UserModel)
        reviewer = aliased(UserModel)
        return (
            select(ReviewItemModel, candidate.name, candidate.email,
                   SourceFileModel.original_name, SourceFileModel.file_type, reviewer.name)
            .join(ProfileModel, ProfileModel.profile_id == ReviewItemModel.profile_id)
            .join(candidate, candidate.user_id == ProfileModel.user_id)
            .join(SourceFileModel, SourceFileModel.file_id == ReviewItemModel.file_id)
            .outerjoin(reviewer, reviewer.user_id == ReviewItemModel.resolved_by)
        )

    def _with_options(self, rows) -> list[ReviewItemView]:
        ids = [row[0].review_id for row in rows]
        options: dict[int, list[ReviewOptionView]] = {i: [] for i in ids}
        if ids:
            for o, name, ftype in self.db.execute(
                    select(ReviewOptionModel, SourceFileModel.original_name,
                           SourceFileModel.file_type)
                    .join(SourceFileModel, SourceFileModel.file_id == ReviewOptionModel.file_id)
                    .where(ReviewOptionModel.review_id.in_(ids))
                    .order_by(ReviewOptionModel.option_id)).all():
                options[o.review_id].append(ReviewOptionView(
                    option_id=o.option_id, file_id=o.file_id, file_name=name, file_type=ftype,
                    field_id=o.field_id, value=o.value, confidence=o.confidence,
                    evidence=o.evidence, page=o.page))

        return [
            ReviewItemView(
                review_id=r.review_id, profile_id=r.profile_id, candidate_name=c_name,
                candidate_email=c_email, file_id=r.file_id, file_name=f_name, file_type=f_type,
                entity=r.entity, field_name=r.field_name, reasons=list(r.reasons or []),
                message=r.message, created_at=r.created_at,
                assigned_to_candidate=bool(r.assigned_to_candidate),
                sent_to_candidate_at=r.sent_to_candidate_at, resolved=bool(r.resolved),
                resolution=r.resolution, resolved_value=r.resolved_value,
                resolved_option_id=r.resolved_option_id, resolved_by=r.resolved_by,
                resolved_by_name=reviewer_name, resolved_at=r.resolved_at,
                options=options[r.review_id])
            for r, c_name, c_email, f_name, f_type, reviewer_name in rows
        ]

    def get_field(self, field_id):
        m = self.db.get(ExtractedFieldModel, field_id) if field_id else None
        if m is None:
            return None
        return StoredField(m.field_id, m.file_id, m.attempt_id, m.entity, m.entity_type,
                           m.field_name, m.raw_value, m.value)

    def latest_valid_attempt_id(self, file_id):
        return self.db.scalar(select(func.max(ProcessingAttemptModel.attempt_id))
                              .where(ProcessingAttemptModel.file_id == file_id,
                                     ProcessingAttemptModel.outcome == "valid"))

    # ---- writing decisions ----

    def add_decision_field(self, file_id, attempt_id, entity, entity_type, field_name,
                           raw_value, value, evidence, page):
        model = ExtractedFieldModel(
            file_id=file_id, attempt_id=attempt_id, entity=entity, entity_type=entity_type,
            field_name=field_name, raw_value=raw_value, value=value, confidence=1.0,
            evidence=evidence, page=page, evidence_status="reviewer", rule=DECISION_RULE,
            review_status="accepted", review_reasons=[], is_winner=True)
        self.db.add(model)
        self.db.flush()
        return model.field_id

    def mark_resolved(self, review_id, resolution, option_id, value_text, field_id, user_id):
        item = self.db.get(ReviewItemModel, review_id)
        item.resolved = True
        item.resolution = resolution
        item.resolved_option_id = option_id
        item.resolved_value = value_text
        item.resolved_field_id = field_id
        item.resolved_by = user_id
        item.resolved_at = _now()
        self.db.flush()

    def mark_sent_to_candidate(self, review_id):
        item = self.db.get(ReviewItemModel, review_id)
        item.assigned_to_candidate = True
        item.sent_to_candidate_at = _now()
        self.db.flush()

    # ---- skills (FR-062: approved mappings are saved and reused) ----

    def ensure_skill(self, name):
        existing = self.db.scalar(select(SkillModel.canonical_name)
                                  .where(func.lower(SkillModel.canonical_name) == name.lower()))
        if existing:
            return existing
        self.db.add(SkillModel(canonical_name=name))
        self.db.flush()
        return name

    def add_skill_alias(self, alias, canonical_name):
        if self.db.scalar(select(SkillAliasModel.alias_id)
                          .where(SkillAliasModel.alias_name == alias)):
            return
        skill_id = self.db.scalar(select(SkillModel.skill_id)
                                  .where(SkillModel.canonical_name == canonical_name))
        self.db.add(SkillAliasModel(skill_id=skill_id, alias_name=alias))
        self.db.flush()

    # ---- change history (FR-037) ----

    def log_change(self, profile_id, file_id, field_name, old_value, new_value, user_id, reason):
        self.db.add(ProfileChangeLogModel(
            profile_id=profile_id, file_id=file_id, field_name=field_name[:100],
            old_value=old_value, new_value=new_value, changed_by=user_id, reason=reason))
        self.db.flush()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
