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
    ocr_confidence: float | None = None
