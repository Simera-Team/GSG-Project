
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateSourceFileHashError

from app.domain.entities.source_file import SourceFile
from app.domain.interfaces.source_file_repository import ISourceFileRepository
from app.infrastructure.persistence.models.source_file_model import SourceFileModel


class SourceFileRepository(ISourceFileRepository):

    def __init__(self, db: Session):
        self.db = db

    def create(self, source_file: SourceFile) -> SourceFile:

        model = SourceFileModel(
            profile_id=source_file.profile_id,
            file_type=source_file.file_type,
            original_name=source_file.original_name,
            file_hash=source_file.file_hash,
            storage_path=source_file.storage_path,
            status=source_file.status,
            extraction_method=source_file.extraction_method,
            ocr_confidence=source_file.ocr_confidence,
            error_message=source_file.error_message,
            llm_response=source_file.llm_response,
            finished_at=source_file.finished_at,
            num_of_retries=source_file.num_of_retries
        )

        self.db.add(model)

        try:
            self.db.flush()
        except IntegrityError as exc:
            if "uq_source_file_profile_hash" in str(exc.orig):
                raise DuplicateSourceFileHashError(
                    "Source file hash already exists for this profile"
                ) from exc
            raise

        return self._to_entity(model)

    def get_by_id(self, file_id: int) -> SourceFile | None:

        model = self.db.get(SourceFileModel, file_id)

        if model is None:
            return None

        return self._to_entity(model)

    def get_by_profile_and_hash(
        self,
        profile_id: int,
        file_hash: str
    ) -> SourceFile | None:

        stmt = select(SourceFileModel).where(
            SourceFileModel.profile_id == profile_id,
            SourceFileModel.file_hash == file_hash
        )

        model = self.db.scalar(stmt)

        if model is None:
            return None

        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: SourceFileModel) -> SourceFile:

        return SourceFile(
            file_id=model.file_id,
            profile_id=model.profile_id,
            file_type=model.file_type,
            original_name=model.original_name,
            file_hash=model.file_hash,
            storage_path=model.storage_path,
            status=model.status,
            extraction_method=model.extraction_method,
            ocr_confidence=model.ocr_confidence,
            error_message=model.error_message,
            llm_response=model.llm_response,
            uploaded_at=model.uploaded_at,
            finished_at=model.finished_at,
            num_of_retries=model.num_of_retries
        )
