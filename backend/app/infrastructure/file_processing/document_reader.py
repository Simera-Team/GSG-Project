from pathlib import Path

from app.application.dto.extracted_document import ExtractedDocument
from app.application.interfaces.file_storage import IFileStorage
from app.application.interfaces.processing_repository import IDocumentReader
from app.domain.entities.source_file import SourceFile
from app.infrastructure.file_processing.extractor_factory import get_extractor


class StoredDocumentReader(IDocumentReader):
    """Reads the stored original file (never modified, FR-009) and extracts its text.

    With a storage, files are read through it (which refuses paths outside the
    storage folder); without one (tests) the path is read directly.
    """

    def __init__(self, storage: IFileStorage | None = None):
        self.storage = storage

    def read(self, source_file: SourceFile) -> ExtractedDocument:
        path = Path(source_file.storage_path)
        content = (self.storage.read(source_file.storage_path) if self.storage
                   else path.read_bytes())
        result = get_extractor(path.suffix).extract(content)
        return ExtractedDocument(
            source_name=str(source_file.file_id),
            text=result.text,
            page_texts=[p.text for p in result.pages] if path.suffix.lower() == ".pdf" else [],
            hyperlinks=result.hyperlinks,
            extraction_method=result.method,
            ocr_confidence=result.ocr_confidence,
        )
