from app.infrastructure.file_processing.base_extractor import BaseExtractor
from app.infrastructure.file_processing.docx_extractor import DocxExtractor
from app.infrastructure.file_processing.markdown_extractor import MarkdownExtractor
from app.infrastructure.file_processing.pdf_extractor import PdfExtractor


_EXTRACTORS: dict[str, type[BaseExtractor]] = {
    ".pdf": PdfExtractor,
    ".docx": DocxExtractor,
    ".md": MarkdownExtractor,
}


def get_extractor(extension: str) -> BaseExtractor:
    extractor_class = _EXTRACTORS.get(extension.lower())
    if extractor_class is None:
        raise ValueError(f"No text extractor for '{extension}' files")
    return extractor_class()
