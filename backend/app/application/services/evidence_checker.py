"""Hallucination control (FR-065, NFR-028).

Every non-null value must come with an evidence snippet, and that snippet
must actually be in the extracted text. The value itself must also be
supported by the snippet. Values that fail are flagged for review and kept
out of the live profile.

Comparison ignores case, spacing, quote/dash style and bullets. For OCR
text, a near match (small recognition differences) is accepted as
"verified_fuzzy".
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

FUZZY_MIN_RATIO = 0.85
LONG_VALUE_CHARS = 120      # summaries/descriptions are joined text, so only the snippet is checked


@dataclass(frozen=True)
class EvidenceCheck:
    status: str                 # verified | verified_fuzzy | missing | not_found
    page: int | None            # page where the snippet was actually found
    value_supported: bool

    @property
    def ok(self) -> bool:
        return self.status in ("verified", "verified_fuzzy") and self.value_supported


class EvidenceChecker:

    def __init__(self, text: str, page_texts: list[str] | None = None,
                 hyperlinks: list[str] | None = None, allow_fuzzy: bool = False):
        self._pages = [_norm(p) for p in (page_texts or [])]
        corpus = [text] + list(hyperlinks or [])
        self._text = _norm("\n".join(corpus))
        self._allow_fuzzy = allow_fuzzy

    def check(self, value, evidence: str | None, page: int | None,
              check_value: bool = True) -> EvidenceCheck:
        if not evidence or not evidence.strip():
            return EvidenceCheck("missing", None, False)

        snippet = _norm(evidence)
        found_page = self._find_page(snippet, page)

        if snippet in self._text:
            status = "verified"
        elif self._allow_fuzzy and self._fuzzy_contains(snippet):
            status = "verified_fuzzy"
        else:
            return EvidenceCheck("not_found", None, False)

        supported = not check_value or self._value_supported(value, snippet, status)
        return EvidenceCheck(status, found_page if found_page else page, supported)

    def _find_page(self, snippet: str, claimed: int | None) -> int | None:
        if not self._pages:
            return None
        if claimed and 1 <= claimed <= len(self._pages) and snippet in self._pages[claimed - 1]:
            return claimed
        for number, page_text in enumerate(self._pages, start=1):
            if snippet in page_text:
                return number
        return None

    def _fuzzy_contains(self, snippet: str) -> bool:
        if len(snippet) < 4:
            return False
        matcher = SequenceMatcher(None, self._text, snippet, autojunk=False)
        block = matcher.find_longest_match(0, len(self._text), 0, len(snippet))
        start = max(0, block.a - block.b)
        window = self._text[start:start + len(snippet)]
        return SequenceMatcher(None, window, snippet, autojunk=False).ratio() >= FUZZY_MIN_RATIO

    @staticmethod
    def _value_supported(value, snippet: str, status: str) -> bool:
        if value is None or isinstance(value, bool):
            return True
        text = _norm(str(value))
        if not text or len(text) > LONG_VALUE_CHARS:
            return True
        if text in snippet:
            return True
        # e.g. value "Sara" from "SARA YOUSEF", or "Amman" from "Amman, Jordan 11942"
        tokens = [t for t in re.findall(r"\w+", text) if len(t) > 1]
        if not tokens:
            return text in snippet
        found = sum(t in snippet for t in tokens)
        needed = 0.8 if status == "verified_fuzzy" else 1.0
        return found / len(tokens) >= needed


def _norm(text: str) -> str:
    text = text.casefold()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[‐-―−]", "-", text)          # all dash styles -> "-"
    text = re.sub(r"[•●▪◦‣·|]", " ", text)        # bullets and separators
    return re.sub(r"\s+", " ", text).strip()
