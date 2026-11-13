import re

import numpy as np
import pymupdf

from app.infrastructure.file_processing.base_extractor import (
    BaseExtractor,
    ExtractionResult,
    PageResult,
)
from app.infrastructure.file_processing.layout import TextBox, boxes_to_text
from app.infrastructure.file_processing.ocr_engine import ocr_image_detailed


class PdfExtractor(BaseExtractor):

    # A page with fewer real characters than this is treated as scanned.
    MIN_TEXT_CHARS = 50
    OCR_DPI = 300
    # On a page that has a text layer, images at least this big (share of the
    # page) are read with OCR too: a header or sidebar saved as a picture can
    # hold contact details or skills that the text layer doesn't have.
    MIN_IMAGE_SHARE = 0.03
    MIN_IMAGE_SIDE_PT = 40
    MAX_IMAGES_PER_PAGE = 5

    def extract(self, content: bytes) -> ExtractionResult:
        pages: list[PageResult] = []
        hyperlinks: list[str] = []

        with pymupdf.open(stream=content, filetype="pdf") as doc:
            for index, page in enumerate(doc, start=1):
                for link in page.get_links():
                    uri = link.get("uri")
                    if uri and uri not in hyperlinks:
                        hyperlinks.append(uri)

                text = self._read_text_layer(page)

                if self._has_enough_text(text):
                    pages.append(self._text_page(index, page, text))
                else:
                    outcome = ocr_image_detailed(self._render(page))
                    pages.append(PageResult(index, "ocr", outcome.text, outcome.confidence,
                                            ocr_fixes=outcome.fixes))

        result = self._combine(pages)
        result.hyperlinks = hyperlinks
        return result

    def _text_page(self, index: int, page, text: str) -> PageResult:
        """Text-layer page, plus any text found only inside its images."""
        extra, scores, fixes = [], [], []
        known = _norm(text)
        for rect in self._text_image_areas(page):
            outcome = ocr_image_detailed(self._render(page, clip=rect))
            new = [line for line in outcome.text.splitlines()
                   if len(_norm(line)) >= 3 and _norm(line) not in known]
            if new:
                extra.extend(new)
                known += " " + _norm(" ".join(new))
                scores.append(outcome.confidence)
                fixes.extend(outcome.fixes)

        if not extra:
            return PageResult(index, "text", text)
        return PageResult(index, "mixed", text + "\n\n" + "\n".join(extra),
                          round(float(np.mean(scores)), 4),
                          ocr_fixes=["read text inside images"] + fixes)

    def _text_image_areas(self, page) -> list:
        page_area = page.rect.width * page.rect.height
        areas = []
        for info in page.get_image_info():
            rect = pymupdf.Rect(info["bbox"]) & page.rect
            if (rect.is_empty or rect.width < self.MIN_IMAGE_SIDE_PT
                    or rect.height < self.MIN_IMAGE_SIDE_PT
                    or rect.width * rect.height / page_area < self.MIN_IMAGE_SHARE):
                continue
            areas.append(rect)
        areas.sort(key=lambda r: r.width * r.height, reverse=True)
        return areas[:self.MAX_IMAGES_PER_PAGE]

    def _read_text_layer(self, page) -> str:
        boxes = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line["spans"])
                text = " ".join(text.split())
                if text:
                    boxes.append(TextBox(*line["bbox"], text))
        return boxes_to_text(boxes, page_width=page.rect.width)

    def _has_enough_text(self, text: str) -> bool:
        return sum(ch.isalnum() for ch in text) >= self.MIN_TEXT_CHARS

    def _render(self, page, clip=None) -> np.ndarray:
        pix = page.get_pixmap(dpi=self.OCR_DPI, colorspace=pymupdf.csRGB, alpha=False,
                              clip=clip)
        return np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, 3
        )

    def _combine(self, pages: list[PageResult]) -> ExtractionResult:
        methods = {p.method for p in pages}
        method = methods.pop() if len(methods) == 1 else "mixed"

        scores = [p.ocr_confidence for p in pages if p.ocr_confidence is not None]
        confidence = round(sum(scores) / len(scores), 4) if scores else None

        return ExtractionResult(
            text="\n\n".join(p.text for p in pages if p.text),
            method=method,
            ocr_confidence=confidence,
            page_count=len(pages),
            pages=pages,
        )


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w@.+]", " ", text.casefold())).strip()
