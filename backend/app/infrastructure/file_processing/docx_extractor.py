from io import BytesIO

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.infrastructure.file_processing.base_extractor import (
    BaseExtractor,
    ExtractionResult,
)


class DocxExtractor(BaseExtractor):

    def extract(self, content: bytes) -> ExtractionResult:
        document = Document(BytesIO(content))
        lines: list[str] = []

        # Contact details are often placed in the page header.
        for section in document.sections:
            for paragraph in section.header.paragraphs:
                self._add(lines, paragraph.text)

        # Walk the body in order so tables stay where they appear.
        for block in document.element.body.iterchildren():
            tag = block.tag.rsplit("}", 1)[-1]
            if tag == "p":
                self._add(lines, Paragraph(block, document).text)
            elif tag == "tbl":
                self._read_table(Table(block, document), lines)

        return ExtractionResult(
            text="\n".join(lines),
            method="text",
            hyperlinks=self._hyperlinks(document),
        )

    @staticmethod
    def _hyperlinks(document) -> list[str]:
        urls: list[str] = []
        parts = [document.part] + [
            s.header.part for s in document.sections if s.header.is_linked_to_previous is False
        ]
        for part in parts:
            for rel in part.rels.values():
                if rel.is_external and "hyperlink" in rel.reltype:
                    url = rel.target_ref
                    if url not in urls:
                        urls.append(url)
        return urls

    def _read_table(self, table: Table, lines: list[str]) -> None:
        for row in table.rows:
            cells: list[str] = []
            for cell in row.cells:
                text = cell.text.strip()
                # Merged cells repeat the same text; keep it once.
                if text and text not in cells:
                    cells.append(text)
            self._add(lines, " | ".join(cells))

    @staticmethod
    def _add(lines: list[str], text: str) -> None:
        text = text.strip()
        if text:
            lines.append(text)
