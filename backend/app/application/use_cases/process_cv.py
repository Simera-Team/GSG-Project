"""Process one stored source file and save the results (FR-039).

1. mark the file "processing" (committed, so the candidate sees it - FR-014)
2. read the stored original and extract its text
3. run the pipeline (LLM attempts, validation, field records, review items)
4. in ONE transaction (NFR-026):
   - insert every attempt (FR-058) and the field records of the valid one
   - replace this file's open review items
   - rebuild the live profile from the field records of ALL the candidate's
     files (FR-036), replacing its child records; recompute cross-source
     conflicts (FR-033)
   - set the file status: done / needs_review / failed
If saving fails, nothing from step 4 is kept and the file is marked failed.
A failed job saves its attempts and review item but no profile data (FR-023).
"""

import json
import time
from collections.abc import Callable

from app.application.interfaces.ai_client import IAIClient
from app.application.interfaces.processing_repository import (
    ICatalogRepository,
    IDocumentReader,
    IProcessingRepository,
)
from app.application.interfaces.unit_of_work import IUnitOfWork
from app.application.services.cv_processing_service import (
    CVProcessingService,
    JobStatus,
    ProcessingResult,
)
from app.application.services.profile_rebuild_service import ProfileRebuildService
from app.domain.entities.field_record import ReviewItem, ReviewReason
from app.domain.entities.processing_attempt import AttemptOutcome, AttemptTrigger


class SourceFileNotFoundError(Exception):
    pass


class ProcessCVUseCase:

    def __init__(self, repository: IProcessingRepository, catalogs: ICatalogRepository,
                 reader: IDocumentReader, ai_client: IAIClient, unit_of_work: IUnitOfWork,
                 confidence_threshold: float = 0.6, max_attempts: int = 3,
                 retry_base_seconds: float = 2.0,
                 sleep: Callable[[float], None] = time.sleep):
        self.repo = repository
        self.catalogs = catalogs
        self.reader = reader
        self.ai_client = ai_client
        self.uow = unit_of_work
        self.confidence_threshold = confidence_threshold
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds
        self.sleep = sleep

    def execute(self, file_id: int,
                trigger: AttemptTrigger = AttemptTrigger.FIRST_RUN) -> ProcessingResult:
        source = self.repo.get_source_file(file_id)
        if source is None:
            raise SourceFileNotFoundError(f"Source file {file_id} does not exist")

        self.repo.set_file_status(file_id, "processing")
        self.uow.commit()

        try:
            document = self.reader.read(source)
        except Exception as exc:   # broken or unreadable file: FR-020
            result = ProcessingResult(
                JobStatus.FAILED, f"Text extraction failed: {exc}", (),
                review_items=[ReviewItem(1, str(file_id), [ReviewReason.NO_TEXT],
                                         message=f"Text extraction failed: {exc}")],
                confidence_threshold=self.confidence_threshold)
            self._save(source.profile_id, file_id, None, result)
            return result

        service = CVProcessingService(
            self.ai_client, self.catalogs.country_catalog(), self.catalogs.skill_catalog(),
            confidence_threshold=self.confidence_threshold, max_attempts=self.max_attempts,
            retry_base_seconds=self.retry_base_seconds, sleep=self.sleep)
        result = service.process(document, trigger)
        self._save(source.profile_id, file_id, document, result)
        return result

    def _save(self, profile_id, file_id, document, result: ProcessingResult) -> None:
        try:
            status = self._write(profile_id, file_id, document, result)
            self.uow.commit()
            result.status = status
        except Exception as exc:
            self.uow.rollback()
            self.repo.set_file_status(file_id, JobStatus.FAILED, finished=True,
                                      error=f"Saving results failed: {exc}")
            self.uow.commit()
            raise

    def _write(self, profile_id, file_id, document, result) -> str:
        first_number = self.repo.next_attempt_number(file_id)
        attempt_ids = self.repo.save_attempts(file_id, result.attempts, first_number,
                                              result.confidence_threshold)

        valid = next((i for i, a in enumerate(result.attempts)
                      if a.outcome == AttemptOutcome.VALID), None)
        id_map: dict[int, int] = {}
        if valid is not None and result.field_records:
            id_map = self.repo.save_field_records(file_id, attempt_ids[valid], result.field_records)

        file_items = [i for i in result.review_items
                      if ReviewReason.SOURCE_CONFLICT not in i.reasons]
        self.repo.replace_open_reviews(profile_id, file_id, file_items, id_map)

        status = result.status
        if valid is not None:
            # FR-036: the live profile always comes from the stored field records
            # of every source of this candidate, not just this file.
            self.repo.set_change_context(None, "auto_merge", file_id)   # FR-037
            built = ProfileRebuildService(self.repo).rebuild(profile_id, file_id)
            if built.profile is None:
                status = JobStatus.FAILED
            elif status == JobStatus.DONE and built.review_items:
                status = JobStatus.NEEDS_REVIEW

        answer = result.attempts[valid].llm_response if valid is not None else None
        self.repo.set_file_status(
            file_id, status,
            error=result.reason if status == JobStatus.FAILED else None,
            extraction_method=document.extraction_method if document else None,
            ocr_confidence=document.ocr_confidence if document else None,
            llm_response=json.loads(answer) if answer else None,
            retries=max(0, first_number + len(result.attempts) - 2),
            finished=True,
        )
        return status
