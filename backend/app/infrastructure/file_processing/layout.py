"""Turn positioned text pieces into reading-order text.

Used by both the PDF text layer and OCR output. Handles two-column CVs
(sidebar + main column) by finding a vertical gap that splits the page,
then reading each column top-to-bottom instead of mixing them row by row.
"""

from dataclasses import dataclass


@dataclass
class TextBox:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


def boxes_to_text(boxes: list[TextBox], page_width: float) -> str:
    boxes = [b for b in boxes if b.text.strip()]
    if not boxes:
        return ""

    parts = []
    for group in _split_columns(boxes, page_width):
        parts.append("\n".join(_group_rows(group)))
    return "\n\n".join(p for p in parts if p)


def _split_columns(boxes: list[TextBox], width: float) -> list[list[TextBox]]:
    """Return [above, left, right, below] when the page has two columns,
    otherwise [boxes]."""
    best_x, best_cross = None, None

    # Try candidate gutter positions across the middle of the page.
    steps = 60
    for i in range(steps + 1):
        x = width * (0.2 + 0.6 * i / steps)
        crossing = [b for b in boxes if b.x0 < x < b.x1]
        left = sum(1 for b in boxes if b.x1 <= x)
        right = sum(1 for b in boxes if b.x0 >= x)
        if left < 4 or right < 4:
            continue
        if best_cross is None or len(crossing) < best_cross:
            best_x, best_cross = x, len(crossing)

    if best_x is None:
        return [boxes]

    left = [b for b in boxes if b.x1 <= best_x]
    right = [b for b in boxes if b.x0 >= best_x]
    spanning = [b for b in boxes if b.x0 < best_x < b.x1]

    # Columns must actually sit side by side (overlap vertically),
    # otherwise it is just a single column with a short line here and there.
    col_top = max(min(b.y0 for b in left), min(b.y0 for b in right))
    col_bottom = min(max(b.y1 for b in left), max(b.y1 for b in right))
    if col_bottom - col_top <= 0:
        return [boxes]

    # Full-width lines may only appear above or below the columns
    # (e.g. a name banner or footer); allow a few that sit inside.
    inside = [b for b in spanning if b.y1 > col_top and b.y0 < col_bottom]
    if len(inside) > max(2, 0.05 * len(boxes)):
        return [boxes]

    above = [b for b in spanning if b.y1 <= col_top or b in inside and b.y0 < col_top]
    below = [b for b in spanning if b not in above]
    return [above, left, right, below]


def _group_rows(boxes: list[TextBox]) -> list[str]:
    """Join boxes on the same row, top-to-bottom, left-to-right."""
    rows: list[list[TextBox]] = []
    for box in sorted(boxes, key=lambda b: (b.y0, b.x0)):
        if rows:
            last = rows[-1]
            top = min(b.y0 for b in last)
            bottom = max(b.y1 for b in last)
            overlap = min(box.y1, bottom) - max(box.y0, top)
            if overlap > 0.5 * min(box.y1 - box.y0, bottom - top):
                last.append(box)
                continue
        rows.append([box])

    return [
        "  ".join(b.text.strip() for b in sorted(row, key=lambda b: b.x0))
        for row in rows
    ]
