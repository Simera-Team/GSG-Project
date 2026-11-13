from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PageResult:
    page_number: int
    method: str                      # "text", "ocr", or "mixed" (text + images read by OCR)
    text: str
    ocr_confidence: float | None = None
    ocr_fixes: list[str] = field(default_factory=list)   # e.g. ["rotated 90", "deskewed 4.2 degrees"]


@dataclass
class ExtractionResult:
    text: str
    method: str                      # "text", "ocr" or "mixed"
    ocr_confidence: float | None = None
    page_count: int = 1
    pages: list[PageResult] = field(default_factory=list)
    # URLs behind clickable text (e.g. "LinkedIn" linking to the profile),
    # which do not appear in the visible text.
    hyperlinks: list[str] = field(default_factory=list)


class BaseExtractor(ABC):

    @abstractmethod
    def extract(self, content: bytes) -> ExtractionResult:
        pass
