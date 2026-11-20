from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.application.interfaces.read_repository import (
    AttemptView,
    ChangeView,
    FileView,
    IReadRepository,
    ProfileView,
)
from app.infrastructure.persistence.models import (
    ExtractedFieldModel,
    ProcessingAttemptModel,
    ProfileChangeLogModel,
    ProfileModel,
    ReviewItemModel,
    SourceFileModel,
    UserModel,
)


class SqlReadRepository(IReadRepository):

    def __init__(self, db: Session):
        self.db = db

    # ---- files ----

    def _file_query(self):
        attempts = (select(func.count()).where(ProcessingAttemptModel.file_id == SourceFileModel.file_id)
                    .correlate(SourceFileModel).scalar_subquery())
        reviews = (select(func.count()).where(ReviewItemModel.file_id == SourceFileModel.file_id,
                                              ReviewItemModel.resolved.is_not(True))
                   .correlate(SourceFileModel).scalar_subquery())
        return (select(SourceFileModel, ProfileModel.user_id, UserModel.name, attempts, reviews)
                .join(ProfileModel, ProfileModel.profile_id == SourceFileModel.profile_id)
                .join(UserModel, UserModel.user_id == ProfileModel.user_id))

    @staticmethod
    def _file_view(row) -> FileView:
        f, user_id, name, attempts, reviews = row
        return FileView(
            file_id=f.file_id, profile_id=f.profile_id, user_id=user_id, candidate_name=name,
            original_name=f.original_name, file_type=f.file_type, status=f.status,
            extraction_method=f.extraction_method, ocr_confidence=f.ocr_confidence,
            error_message=f.error_message, uploaded_at=f.uploaded_at, finished_at=f.finished_at,
            attempts=attempts or 0, open_reviews=reviews or 0)

    def list_files(self, profile_id, status, limit, offset):
        query = self._file_query()
        if profile_id is not None:
            query = query.where(SourceFileModel.profile_id == profile_id)
        if status:
            query = query.where(SourceFileModel.status == status)
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.db.execute(query.order_by(SourceFileModel.uploaded_at.desc(),
                                              SourceFileModel.file_id.desc())
                               .limit(limit).offset(offset)).all()
        return total, [self._file_view(r) for r in rows]

    def get_file(self, file_id):
        row = self.db.execute(self._file_query().where(SourceFileModel.file_id == file_id)).first()
        return self._file_view(row) if row else None

    def file_attempts(self, file_id):
        rows = self.db.scalars(select(ProcessingAttemptModel)
                               .where(ProcessingAttemptModel.file_id == file_id)
                               .order_by(ProcessingAttemptModel.attempt_number)).all()
        return [AttemptView(a.attempt_number, a.trigger, a.outcome, a.provider, a.model_version,
                            a.error_message, a.started_at, a.finished_at) for a in rows]

    # ---- profiles ----

    def profile_id_for_user(self, user_id):
        return self.db.scalar(select(ProfileModel.profile_id).where(ProfileModel.user_id == user_id))

    def get_profile(self, profile_id):
        row = self.db.execute(
            select(ProfileModel, UserModel.name, UserModel.email)
            .join(UserModel, UserModel.user_id == ProfileModel.user_id)
            .where(ProfileModel.profile_id == profile_id)).first()
        if row is None:
            return None
        p, name, email = row
        open_reviews = self.db.scalar(select(func.count()).where(
            ReviewItemModel.profile_id == profile_id, ReviewItemModel.resolved.is_not(True)))
        _, files = self.list_files(profile_id, None, 100, 0)
        return ProfileView(p.profile_id, p.user_id, name, email, p.updated_at, p.final_json,
                           open_reviews or 0, files)

    def change_history(self, profile_id, limit, offset):
        who = aliased(UserModel)
        query = (select(ProfileChangeLogModel, who.name)
                 .outerjoin(who, who.user_id == ProfileChangeLogModel.changed_by)
                 .where(ProfileChangeLogModel.profile_id == profile_id))
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.db.execute(query.order_by(ProfileChangeLogModel.change_id.desc())
                               .limit(limit).offset(offset)).all()
        return total, [ChangeView(c.change_id, c.field_name, c.old_value, c.new_value,
                                  name or "system", c.reason, c.file_id, c.changed_at)
                       for c, name in rows]

    # ---- dashboard (FR-047, FR-048, FR-052) ----

    def dashboard(self):
        by_status = dict(self.db.execute(
            select(SourceFileModel.status, func.count()).group_by(SourceFileModel.status)).all())
        attempts = self.db.execute(select(
            func.count(),
            func.count().filter(ProcessingAttemptModel.outcome == "valid"),
            func.count().filter(ProcessingAttemptModel.outcome != "valid"),
        )).one()
        first_tries = self.db.execute(select(
            func.count(),
            func.count().filter(ProcessingAttemptModel.outcome == "valid"),
        ).where(ProcessingAttemptModel.trigger == "first_run")).one()
        reached_limit = self.db.scalar(select(func.count()).select_from(
            select(ProcessingAttemptModel.file_id)
            .where(ProcessingAttemptModel.trigger != "admin_rerun")
            .group_by(ProcessingAttemptModel.file_id)
            .having(func.count() >= 3).subquery()))
        fields = self.db.execute(select(
            func.count(),
            func.avg(ExtractedFieldModel.confidence),
            func.count().filter(ExtractedFieldModel.review_status == "needs_review"),
        ).where(ExtractedFieldModel.rule != "review_decision")).one()
        reviews = self.db.execute(select(
            func.count().filter(ReviewItemModel.resolved.is_not(True)),
            func.count().filter(ReviewItemModel.resolved.is_(True)),
            func.count().filter(ReviewItemModel.resolution == "custom"),
        )).one()
        candidates = self.db.scalar(select(func.count()).where(UserModel.role == "candidate"))
        return {
            "candidates": candidates or 0,
            "files_total": sum(by_status.values()),
            "files_by_status": {s: by_status.get(s, 0) for s in
                                ("uploaded", "processing", "done", "needs_review", "failed")},
            "llm_attempts": attempts[0],
            "llm_failed_attempts": attempts[2],
            "valid_on_first_try_rate": round(first_tries[1] / first_tries[0], 3) if first_tries[0] else None,
            "files_that_hit_3_attempts": reached_limit or 0,
            "field_records": fields[0],
            "average_confidence": round(float(fields[1]), 3) if fields[1] is not None else None,
            "share_of_fields_sent_to_review": round(fields[2] / fields[0], 3) if fields[0] else None,
            "open_reviews": reviews[0],
            "resolved_reviews": reviews[1],
            "reviews_with_typed_correction": reviews[2],
        }
