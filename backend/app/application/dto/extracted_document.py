import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtractedDocument:
    """Text read from one source file, handed from extraction to the LLM step.

    Kept independent of the extractor classes so the application layer does
    not depend on infrastructure code.
    """

    source_name: str                     # file name or file id, used to trace values
    text: str
    page_texts: list[str] = field(default_factory=list)   # empty for DOCX / Markdown
    hyperlinks: list[str] = field(default_factory=list)
    extraction_method: str = "text"      # text | ocr | mixed
    ocr_confidence: float | None = None  # mean over the pages that needed OCR

    # Per page, the mean OCR confidence of the text read from it, or None for a
    # page that had a text layer. The confidence model needs this per page and
    # not per file: one scanned page in a ten-page PDF should not make the
    # other nine look doubtful, and a 0.60 scan should not be hidden behind a
    # file-wide mean of 0.95.
    page_ocr_confidence: list[float | None] = field(default_factory=list)

    # Per page, the part of its text that came from a text layer; empty for a
    # page read entirely by OCR. A page can hold both, when a logo or sidebar
    # image on an otherwise readable page is also read (extraction_method
    # "mixed"), and a value quoted from the text layer of such a page was
    # never recognised by OCR, so it is not worth less than any other.
    page_text_layers: list[str] = field(default_factory=list)

    def page_confidence(self, page: int | None, snippet: str | None = None) -> float | None:
        """The OCR confidence that applies to ``snippet`` on ``page``.

        ``None`` means "not read by OCR", which the confidence model reads as a
        clean text layer. A page outside the list, or no page at all, falls
        back to the file's own mean: on a document that needed OCR anywhere, a
        value whose page could not be pinned down should not be credited with a
        text layer it may not have come from.
        """
        if page is None or not 1 <= page <= len(self.page_ocr_confidence):
            return self.ocr_confidence

        score = self.page_ocr_confidence[page - 1]
        if score is None:
            return None

        if snippet and page <= len(self.page_text_layers):
            layer = self.page_text_layers[page - 1]
            if layer and _folded(snippet) in _folded(layer):
                return None
        return score


def _folded(text: str) -> str:
    """Case and spacing folded, the same way the evidence check folds them."""
    return re.sub(r"\s+", " ", text.casefold()).strip()
