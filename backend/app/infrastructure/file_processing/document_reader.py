from pathlib import Path

from app.application.dto.extracted_document import ExtractedDocument
from app.application.interfaces.processing_repository import IDocumentReader
from app.domain.entities.source_file import SourceFile
from app.infrastructure.file_processing.extractor_factory import get_extractor


class StoredDocumentReader(IDocumentReader):
    """Reads the stored original file (never modified, FR-009) and extracts its text."""

    def read(self, source_file: SourceFile) -> ExtractedDocument:
        path = Path(source_file.storage_path)
        result = get_extractor(path.suffix).extract(path.read_bytes())
        return ExtractedDocument(
            source_name=str(source_file.file_id),
            text=result.text,
            page_texts=[p.text for p in result.pages] if path.suffix.lower() == ".pdf" else [],
            hyperlinks=result.hyperlinks,
            extraction_method=result.method,
            ocr_confidence=result.ocr_confidence,
        )
