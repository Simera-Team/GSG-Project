"""OCR for scanned or image-only pages, with automatic fixes for poor images.

Measured on degraded copies of a scanned CV, the recognition model reads
97-100% of the words even at 72 DPI, heavily blurred or on a dark, low-contrast
page. What breaks extraction is page geometry, which scrambles the reading
order the LLM depends on:
  - a page scanned sideways or upside down  (reading order ~23% correct)
  - a tilted page (9 degrees)               (reading order ~77% correct)
So every page goes through:
  1. first pass, per-line rotation classifier off (faster; and with it on,
     an upside-down page still scores high while its line order is reversed)
  2. orientation fix: if lines run vertically, or confidence is low, try the
     page rotated 90 / 180 / 270 degrees and keep the best
  3. deskew: measure the text-line angle and straighten the page if tilted
  4. enhancement, only when the result is still poor: upscale small images,
     even out lighting and contrast (CLAHE), remove noise; keep it only if it
     scores better
"""

import math
import os
from dataclasses import dataclass, field
from functools import lru_cache

import cv2
import numpy as np

from app.infrastructure.file_processing.layout import TextBox, boxes_to_text

GOOD_CONFIDENCE = 0.90       # at or above this, no further fixes are tried
LOW_CONFIDENCE = 0.80        # below this, also try other orientations
SIDEWAYS_SHARE = 0.6         # share of text boxes taller than wide => page is sideways
MIN_SKEW_DEGREES = 1.0       # smaller tilts do not disturb line grouping (measured)
MAX_SKEW_DEGREES = 20.0
MIN_SHORT_SIDE = 1500        # upscale smaller images before enhancing


@dataclass
class OcrOutcome:
    text: str
    confidence: float | None
    fixes: list[str] = field(default_factory=list)   # e.g. ["rotated 90", "deskewed 4.0"]


@dataclass
class _Pass:
    boxes: list
    texts: list[str]
    scores: list[float]
    width: int

    @property
    def confidence(self) -> float:
        return float(np.mean(self.scores)) if self.scores else 0.0

    @property
    def chars(self) -> int:
        return sum(len(t) for t in self.texts)

    def score(self) -> float:
        # confidence weighted by how much text was read, so an orientation
        # that reads three confident words doesn't beat the full page
        return self.confidence * math.log1p(self.chars)


@lru_cache(maxsize=1)
def _get_engine():
    # Imported lazily: loading the OCR models is slow and only needed for scans.
    from rapidocr import RapidOCR
    try:
        from app.core.config import settings
        threads = settings.OCR_THREADS
    except Exception:            # settings unavailable (e.g. a bare script): use the default
        threads = int(os.environ.get("OCR_THREADS", "4"))
    # Spreading work over every core is slower on laptops that mix fast and
    # slow cores; 4 threads measured ~40% faster than all cores.
    return RapidOCR(params={
        "EngineConfig.onnxruntime.intra_op_num_threads": threads,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    })


def ocr_image(image: np.ndarray) -> tuple[str, float | None]:
    """Run OCR on an RGB image. Returns (text, mean confidence 0..1)."""
    outcome = ocr_image_detailed(image)
    return outcome.text, outcome.confidence


def ocr_image_detailed(image: np.ndarray) -> OcrOutcome:
    fixes: list[str] = []
    best = _run(image)
    current = image

    # 2. orientation
    sideways = bool(best.texts) and _sideways_share(best) >= SIDEWAYS_SHARE
    if sideways or (best.texts and best.confidence < LOW_CONFIDENCE):
        # The recogniser turns each tall line upright by itself, so a sideways
        # page still scores high - but its lines come out in the wrong order.
        # A sideways page therefore always switches to the best orientation
        # whose lines run horizontally; otherwise switch only if clearly better.
        chosen = None
        for name, code in (("90", cv2.ROTATE_90_CLOCKWISE), ("180", cv2.ROTATE_180),
                           ("270", cv2.ROTATE_90_COUNTERCLOCKWISE)):
            rotated = cv2.rotate(image, code)
            attempt = _run(rotated)
            if sideways and _sideways_share(attempt) >= 1 - SIDEWAYS_SHARE:
                continue
            if chosen is None or attempt.score() > chosen[0].score():
                chosen = (attempt, rotated, name)
        if chosen and (sideways or chosen[0].score() > best.score() * 1.05):
            best, current = chosen[0], chosen[1]
            fixes.append(f"rotated {chosen[2]} degrees")

    # 3. deskew
    angle = _skew_angle(best)
    if MIN_SKEW_DEGREES <= abs(angle) <= MAX_SKEW_DEGREES:
        straight = _rotate_by(current, angle)
        attempt = _run(straight)
        if attempt.texts and attempt.confidence >= best.confidence - 0.02:
            best, current = attempt, straight
            fixes.append(f"deskewed {angle:.1f} degrees")

    # 4. enhancement, only when still poor
    if not best.texts or best.confidence < GOOD_CONFIDENCE:
        enhanced = _enhance(current)
        attempt = _run(enhanced)
        if attempt.score() > best.score():
            best = attempt
            fixes.append("enhanced (upscale, contrast, denoise)")

    if not best.texts:
        return OcrOutcome("", None, fixes)
    boxes = [TextBox(min(p[0] for p in b), min(p[1] for p in b),
                     max(p[0] for p in b), max(p[1] for p in b), t)
             for b, t in zip(best.boxes, best.texts)]
    return OcrOutcome(boxes_to_text(boxes, page_width=best.width),
                      round(best.confidence, 4), fixes)


def _run(image: np.ndarray) -> _Pass:
    result = _get_engine()(image, use_cls=False)
    if result is None or not result.txts:
        return _Pass([], [], [], image.shape[1])
    return _Pass([np.asarray(b) for b in result.boxes], list(result.txts),
                 [float(s) for s in result.scores], image.shape[1])


def _sideways_share(p: _Pass) -> float:
    tall = 0
    for b in p.boxes:
        width = np.linalg.norm(b[1] - b[0])
        height = np.linalg.norm(b[3] - b[0])
        tall += height > width * 1.5
    return tall / len(p.boxes) if p.boxes else 0.0


def _skew_angle(p: _Pass) -> float:
    """Median angle of the long text lines, in degrees (cv2 sign convention)."""
    angles, weights = [], []
    for b in p.boxes:
        dx, dy = b[1][0] - b[0][0], b[1][1] - b[0][1]
        length = math.hypot(dx, dy)
        if length < 80:                       # short boxes give noisy angles
            continue
        angles.append(math.degrees(math.atan2(dy, dx)))
        weights.append(length)
    if len(angles) < 3:
        return 0.0
    order = np.argsort(angles)
    cumulative = np.cumsum(np.asarray(weights)[order])
    median = np.asarray(angles)[order][np.searchsorted(cumulative, cumulative[-1] / 2)]
    return float(median)


def _rotate_by(image: np.ndarray, degrees: float) -> np.ndarray:
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w, new_h = int(h * sin + w * cos), int(h * cos + w * sin)
    matrix[0, 2] += new_w / 2 - w / 2
    matrix[1, 2] += new_h / 2 - h / 2
    return cv2.warpAffine(image, matrix, (new_w, new_h), flags=cv2.INTER_CUBIC,
                          borderValue=(255, 255, 255))


def _enhance(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    short = min(gray.shape[:2])
    if short < MIN_SHORT_SIDE:
        scale = MIN_SHORT_SIDE / short
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)   # lighting + contrast
    gray = cv2.fastNlMeansDenoising(gray, None, h=12, templateWindowSize=7, searchWindowSize=21)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
