from app.infrastructure.file_processing.base_extractor import (
    BaseExtractor,
    ExtractionResult,
)


class MarkdownExtractor(BaseExtractor):

    def extract(self, content: bytes) -> ExtractionResult:
        # Markdown is already plain text; headings (#) are kept because
        # they mark the sections.
        text = content.decode("utf-8-sig", errors="replace").strip()
        return ExtractionResult(text=text, method="text")
