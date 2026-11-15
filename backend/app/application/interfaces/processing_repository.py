from abc import ABC, abstractmethod

from app.application.dto.extracted_document import ExtractedDocument
from app.application.dto.profile_document import ProfileDocument
from app.domain.entities.field_record import FieldRecord, ReviewItem
from app.domain.entities.processing_attempt import ProcessingAttempt
from app.domain.entities.source_file import SourceFile
from app.domain.services.countries import CountryCatalog
from app.domain.services.skills import SkillCatalog


class ICatalogRepository(ABC):
    """Country and skill lists maintained by the administrator."""

    @abstractmethod
    def country_catalog(self) -> CountryCatalog: ...

    @abstractmethod
    def skill_catalog(self) -> SkillCatalog: ...


class IDocumentReader(ABC):
    """Reads a stored source file and returns its text (OCR included)."""

    @abstractmethod
    def read(self, source_file: SourceFile) -> ExtractedDocument: ...


class IProcessingRepository(ABC):
    """Stores processing results. Calls are not committed here; the use case
    commits once so a failure never leaves a partial profile (NFR-026)."""

    @abstractmethod
    def get_source_file(self, file_id: int) -> SourceFile | None: ...

    @abstractmethod
    def set_file_status(self, file_id: int, status: str, *, error: str | None = None,
                        extraction_method: str | None = None,
                        ocr_confidence: float | None = None,
                        llm_response: dict | None = None,
                        retries: int | None = None, finished: bool = False) -> None: ...

    @abstractmethod
    def next_attempt_number(self, file_id: int) -> int: ...

    @abstractmethod
    def save_attempts(self, file_id: int, attempts: tuple[ProcessingAttempt, ...],
                      first_number: int, confidence_threshold: float | None) -> list[int]:
        """Insert attempts (never update); returns their ids in order."""

    @abstractmethod
    def save_field_records(self, file_id: int, attempt_id: int,
                           records: list[FieldRecord]) -> dict[int, int]:
        """Insert field records; returns {local field_id: stored field_id}."""

    @abstractmethod
    def replace_open_reviews(self, profile_id: int, file_id: int, items: list[ReviewItem],
                             field_id_map: dict[int, int], conflicts_only: bool = False) -> None:
        """Replace the file's unresolved review items (resolved ones are kept)."""

    @abstractmethod
    def load_profile_field_records(self, profile_id: int) -> list[FieldRecord]:
        """Field records of the latest valid attempt of every file of the profile."""

    @abstractmethod
    def set_change_context(self, user_id: int | None, reason: str, file_id: int | None) -> None:
        """Tell the profile trigger who is changing the profile, why, and which file
        caused it, for the history (FR-037). Lasts until the transaction ends."""

    @abstractmethod
    def replace_profile(self, profile_id: int, profile: ProfileDocument,
                        records: list[FieldRecord]) -> None:
        """Write profile columns, final_json and all child records."""
