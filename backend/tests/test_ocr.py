"""OCR fixes for poor images (FR-017): orientation, deskew, text inside images.

Pages are generated, so no sample files are needed. Each test runs the real
OCR models (a few seconds each).
"""

import cv2
import numpy as np
import pymupdf
import pytest

from app.infrastructure.file_processing.ocr_engine import ocr_image_detailed
from app.infrastructure.file_processing.pdf_extractor import PdfExtractor

LINES = ["SAMIRA KHALIL", "PROFESSIONAL EXPERIENCE", "Senior Accountant at Arab Bank",
         "January 2019 to Present", "EDUCATION", "Bachelor of Accounting",
         "University of Jordan 2014 to 2018", "SKILLS", "Financial Reporting and Auditing"]


def page(lines=LINES) -> np.ndarray:
    img = np.full((1600, 1200, 3), 255, np.uint8)
    for i, line in enumerate(lines):
        cv2.putText(img, line, (70, 120 + i * 150), cv2.FONT_HERSHEY_DUPLEX, 1.5,
                    (20, 20, 20), 2, cv2.LINE_AA)
    return img


def in_order(text: str) -> bool:
    """All lines found, top to bottom in the original order."""
    low = text.casefold()
    positions = [low.find(line.casefold()) for line in LINES]
    return all(p >= 0 for p in positions) and positions == sorted(positions)


def test_upright_page_needs_no_fix():
    outcome = ocr_image_detailed(page())
    assert in_order(outcome.text)
    assert outcome.fixes == []
    assert outcome.confidence > 0.9


@pytest.mark.parametrize("rotation, fix", [
    (cv2.ROTATE_90_CLOCKWISE, "rotated 270 degrees"),
    (cv2.ROTATE_90_COUNTERCLOCKWISE, "rotated 90 degrees"),
    (cv2.ROTATE_180, "rotated 180 degrees"),
])
def test_sideways_or_upside_down_page_is_turned(rotation, fix):
    outcome = ocr_image_detailed(cv2.rotate(page(), rotation))
    assert fix in outcome.fixes
    assert in_order(outcome.text), outcome.text


def test_tilted_page_is_straightened():
    img = page()
    h, w = img.shape[:2]
    tilted = cv2.warpAffine(img, cv2.getRotationMatrix2D((w / 2, h / 2), 7, 1.0), (w, h),
                            borderValue=(255, 255, 255))
    outcome = ocr_image_detailed(tilted)
    assert any(f.startswith("deskewed") for f in outcome.fixes)
    assert in_order(outcome.text), outcome.text


def test_text_inside_an_image_on_a_text_page_is_read():
    banner = np.full((200, 1600, 3), (40, 70, 120), np.uint8)
    cv2.putText(banner, "samira.khalil@example.com  +962 79 555 0101", (40, 120),
                cv2.FONT_HERSHEY_DUPLEX, 1.4, (255, 255, 255), 2, cv2.LINE_AA)
    ok, png = cv2.imencode(".png", banner)
    doc = pymupdf.open()
    p = doc.new_page(width=595, height=842)
    p.insert_image(pymupdf.Rect(40, 30, 555, 94), stream=png.tobytes())
    p.insert_textbox(pymupdf.Rect(40, 120, 555, 800),
                     "EXPERIENCE\nSenior Accountant, Arab Bank, 2019 - Present\n"
                     "SKILLS\nFinancial reporting, auditing, Excel", fontsize=11)

    result = PdfExtractor().extract(doc.tobytes())

    assert result.method == "mixed"
    assert "read text inside images" in result.pages[0].ocr_fixes
    assert "samira.khalil@example.com" in result.text
    assert "Arab Bank" in result.text                    # text layer kept
    assert result.text.count("Arab Bank") == 1           # not duplicated by OCR
