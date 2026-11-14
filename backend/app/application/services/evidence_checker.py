"""Hallucination control (FR-065, NFR-028).

Every non-null value must come with an evidence snippet, and that snippet must
actually be in the extracted text. The value itself must also be supported by
the snippet. A value that fails is **rejected** under ``R-03``: it does not
become a field record and nobody is asked about it, because a value that is
not in the document is not a judgement call.

Comparison ignores case, spacing, quote/dash style and bullets, and then asks
how much of the snippet is really there. The answer is a similarity, graded by
:func:`app.domain.services.confidence.grade_evidence`:

* the snippet is in the text                       -> ``verified``
* 0.90 or better                                   -> ``verified_fuzzy``
* 0.75 to 0.90                                     -> ``verified_weak``
* under 0.75                                       -> rejected

The near-match grades used to apply only to pages read by OCR, on the grounds
that a text layer should quote itself exactly. In practice a model drops a
comma or normalises a dash on any page, and rejecting those values lost
correct data; the grade now prices the difference instead, on every page.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.domain.services.confidence import (
    EvidenceGrade,
    evidence_factor,
    grade_evidence,
)

LONG_VALUE_CHARS = 120      # summaries/descriptions are joined text, so only the snippet is checked

#: Shortest snippet worth comparing loosely. Under four characters almost any
#: fragment is similar to something in a CV.
MIN_FUZZY_CHARS = 4

#: Share of a value's words that must appear in its snippet. A snippet that is
#: itself only a near match is allowed to have lost one word in the noise.
VALUE_SUPPORT_EXACT = 1.0
VALUE_SUPPORT_FUZZY = 0.8


@dataclass(frozen=True)
class EvidenceCheck:
    status: str                 # verified | verified_fuzzy | verified_weak | missing | not_found
    page: int | None            # page where the snippet was actually found
    value_supported: bool
    #: How much of the snippet was found in the source text, 0 to 1.
    similarity: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status in (EvidenceGrade.VERIFIED, EvidenceGrade.VERIFIED_FUZZY,
                               EvidenceGrade.VERIFIED_WEAK) and self.value_supported

    @property
    def factor(self) -> float:
        """What this match is worth as the ``evidence`` confidence factor."""
        return evidence_factor(self.status)

    @property
    def detail(self) -> str:
        """Why the value was rejected, in a sentence a person can act on."""
        if self.status == EvidenceGrade.MISSING:
            return "No evidence snippet was given for the value (R-03)."
        if self.status == EvidenceGrade.NOT_FOUND:
            return (f"The evidence snippet is not in the source text; the closest "
                    f"span matched {self.similarity:.2f} of it (R-03).")
        return ("The evidence snippet is in the source text but does not contain "
                "the value (R-03).")


class EvidenceChecker:

    def __init__(self, text: str, page_texts: list[str] | None = None,
                 hyperlinks: list[str] | None = None):
        self._pages = [_norm(p) for p in (page_texts or [])]
        corpus = [text] + list(hyperlinks or [])
        self._text = _norm("\n".join(corpus))

    def check(self, value, evidence: str | None, page: int | None,
              check_value: bool = True) -> EvidenceCheck:
        if not evidence or not evidence.strip():
            return EvidenceCheck(EvidenceGrade.MISSING, None, False)

        snippet = _norm(evidence)
        found_page = self._find_page(snippet, page)

        similarity = 1.0 if snippet in self._text else self._best_ratio(snippet)
        status = grade_evidence(similarity)
        if status is None:
            return EvidenceCheck(EvidenceGrade.NOT_FOUND, None, False, similarity)

        supported = not check_value or self._value_supported(value, snippet, status)
        return EvidenceCheck(status, found_page if found_page else page,
                             supported, similarity)

    def _find_page(self, snippet: str, claimed: int | None) -> int | None:
        if not self._pages:
            return None
        if claimed and 1 <= claimed <= len(self._pages) and snippet in self._pages[claimed - 1]:
            return claimed
        for number, page_text in enumerate(self._pages, start=1):
            if snippet in page_text:
                return number
        return None

    def _best_ratio(self, snippet: str) -> float:
        """How much of ``snippet`` is in the source text, 0 to 1.

        A whole-document ratio would punish a short snippet quoted from a long
        CV, so the snippet is compared against the best-aligned span of the
        text instead: every place the matcher found something in common anchors
        one snippet-sized window, and the best of those windows is the answer.

        A window starts at ``text_position - snippet_position``, which lines
        the two copies of the common run up with each other. Centring the
        window on the run instead would slide a snippet whose match sits at one
        end half out of the window and score a near-exact quote as a weak one.
        """
        if len(snippet) < MIN_FUZZY_CHARS or not self._text:
            return 0.0

        matcher = SequenceMatcher(None, self._text, snippet, autojunk=False)
        width = len(snippet)
        best = 0.0

        for text_at, snippet_at, size in matcher.get_matching_blocks():
            if size == 0:
                continue
            left = max(0, min(text_at - snippet_at, len(self._text) - width))
            window = self._text[left:left + width]
            best = max(best, SequenceMatcher(None, window, snippet,
                                             autojunk=False).ratio())
            if best >= 1.0:
                break

        return best

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
        needed = (VALUE_SUPPORT_EXACT if status == EvidenceGrade.VERIFIED
                  else VALUE_SUPPORT_FUZZY)
        return found / len(tokens) >= needed


def _norm(text: str) -> str:
    text = text.casefold()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[‐-―−]", "-", text)          # all dash styles -> "-"
    text = re.sub(r"[•●▪◦‣·|]", " ", text)        # bullets and separators
    return re.sub(r"\s+", " ", text).strip()
