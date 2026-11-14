"""Input contract: the text the backend extracted from one source file.

Text arrives split by page and by block so every extracted value can point back
to where it was read. OCR pages also carry per-word confidence, which is what
the confidence model's ``base`` factor is computed from.
"""

from datetime import datetime
from enum import Enum

from pydantic import Field

from app.application.ai.schemas.base import AIInputSchema


class ExtractionMethod(str, Enum):
    """How one page's text was read. Decided per page, not per file."""

    TEXT = "text"
    OCR = "ocr"


class BlockRegion(str, Enum):
    """Where a block sits on the page, set by fixed geometry rules in code.

    The model is given the region next to each block's text so it can tell a
    sidebar skills list from a job description. Region only helps it read;
    every value still needs its evidence and validation.
    """

    HEADER = "header"
    FOOTER = "footer"
    SIDEBAR = "sidebar"
    MAIN = "main"


class SourceKind(str, Enum):
    """Which kind of source a file is, used for conflict source priority."""

    CV = "cv"
    LINKEDIN = "linkedin"
    VETTING = "vetting"
    OTHER = "other"


class OcrWord(AIInputSchema):
    """One OCR word with the engine's confidence in it."""

    text: str
    conf: float = Field(ge=0, le=1)


class TextBlock(AIInputSchema):
    """One block of text with enough provenance to cite it as evidence."""

    block_id: str
    region: BlockRegion = BlockRegion.MAIN
    text: str

    bbox: tuple[float, float, float, float] | None = Field(
        default=None,
        description="[x0, y0, x1, y1] in PDF points, origin at the page's top-left.",
    )

    line_start: int | None = Field(
        default=None,
        description="Markdown sources carry line numbers instead of a bbox.",
    )
    line_end: int | None = None

    ocr_words: list[OcrWord] = Field(default_factory=list)


class DocumentPage(AIInputSchema):
    """One page of a source, read either from its text layer or by OCR."""

    page: int = Field(ge=1)
    method: ExtractionMethod
    blocks: list[TextBlock] = Field(default_factory=list)

    @property
    def is_ocr(self) -> bool:
        return self.method is ExtractionMethod.OCR


class DocumentText(AIInputSchema):
    """All of one source's text, as produced by the backend."""

    source_id: str
    pages: list[DocumentPage] = Field(default_factory=list)

    def iter_blocks(self) -> list[tuple[DocumentPage, TextBlock]]:
        """Return every block with the page it belongs to, in reading order."""
        return [(page, block) for page in self.pages for block in page.blocks]

    def find_page(self, page_number: int) -> DocumentPage | None:
        """Return the page with ``page_number``, or ``None``."""
        return next((page for page in self.pages if page.page == page_number), None)

    def find_block(self, block_id: str) -> tuple[DocumentPage, TextBlock] | None:
        """Return the block with ``block_id`` and its page, or ``None``."""
        return next(
            (
                (page, block)
                for page, block in self.iter_blocks()
                if block.block_id == block_id
            ),
            None,
        )

    def has_usable_text(self) -> bool:
        """Whether any block holds text. Empty sources are rejected without an LLM call."""
        return any(block.text.strip() for _, block in self.iter_blocks())


class SourceMeta(AIInputSchema):
    """What the module needs to know about the file a result came from.

    ``uploaded_at`` decides recency for the conflict rules, and ``kind`` decides
    source priority when recency ties.
    """

    source_id: str
    kind: SourceKind = SourceKind.CV
    uploaded_at: datetime
    file_hash: str | None = None
    original_name: str | None = None
