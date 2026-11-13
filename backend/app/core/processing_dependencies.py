from sqlalchemy.orm import Session

from app.application.use_cases.process_cv import ProcessCVUseCase


def build_process_cv_use_case(db: Session, settings) -> ProcessCVUseCase:
    """Wire the use case with its database, file reader and LLM client.
    Used by the CV worker and scripts; tests build it with fakes instead."""
    from app.infrastructure.ai.ai_client_factory import create_ai_client
    from app.infrastructure.file_processing.document_reader import StoredDocumentReader
    from app.infrastructure.storage.local_file_storage import LocalFileStorage
    from app.infrastructure.persistence.repositories.catalog_repository import SqlCatalogRepository
    from app.infrastructure.persistence.repositories.processing_repository import (
        SqlProcessingRepository,
    )
    from app.infrastructure.persistence.repositories.unit_of_work import SqlAlchemyUnitOfWork

    return ProcessCVUseCase(
        repository=SqlProcessingRepository(db),
        catalogs=SqlCatalogRepository(db),
        reader=StoredDocumentReader(LocalFileStorage()),
        ai_client=create_ai_client(settings),
        unit_of_work=SqlAlchemyUnitOfWork(db),
        confidence_threshold=settings.REVIEW_CONFIDENCE_THRESHOLD,
        max_attempts=settings.LLM_MAX_ATTEMPTS,
        retry_base_seconds=settings.LLM_RETRY_BASE_SECONDS,
    )
