"""Evidence check: every value must be traceable to the source text.

This is the hallucination control (NFR-028). A value whose snippet is not in the
document is rejected outright (R-03), however confident the model sounded, and
the quality of the text the value was read from becomes the ``base`` factor.
"""

from dataclasses import dataclass

from app.application.ai.schemas.document_text import DocumentPage, DocumentText, TextBlock
from app.application.ai.schemas.field_record import EvidenceMatch, FieldEvidence
from app.application.ai.settings import AISettings
from app.application.ai.text_matching import canonical_text, partial_similarity

#: Punctuation that clings to a word without being part of it. Stripping it the
#: same way on both sides is what lets an OCR word line up with the snippet it
#: appears in: "Soft," in the word list is the "Soft" of "Orbit Soft, Junior".
_WORD_PUNCTUATION = ".,;:()[]{}!?\"'·"


def _word_key(token: str) -> str:
    """Fold one word for comparison between a snippet and the OCR word list."""
    return canonical_text(token).strip(_WORD_PUNCTUATION)


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    """The outcome of checking one value's evidence against the source."""

    evidence: FieldEvidence | None
    base: float
    evidence_factor: float

    @property
    def found(self) -> bool:
        return self.evidence is not None


class EvidenceVerifier:
    """Finds a value's snippet in the source text and scores the match."""

    def __init__(self, settings: AISettings) -> None:
        self._settings = settings

    def verify(
        self,
        document: DocumentText,
        *,
        snippet: str | None,
        raw_value: str,
        block_id: str | None = None,
    ) -> EvidenceAssessment:
        """Locate ``snippet`` in ``document`` and score how well it matched.

        The model is asked for the shortest span of source text containing the
        value; when it returns none, the raw value itself is searched for, so a
        missing snippet costs the field nothing on its own.
        """
        needle = (snippet or raw_value).strip()
        if not needle:
            return EvidenceAssessment(None, base=0.0, evidence_factor=0.0)

        best = self._best_match(document, needle, block_id)
        if best is None:
            return EvidenceAssessment(None, base=0.0, evidence_factor=0.0)

        page, block, score = best
        match = self._classify(score)
        if match is None:
            # Below the low cut-off most of the snippet is not in the text, so
            # the value was likely rewritten or invented: reject under R-03.
            return EvidenceAssessment(None, base=0.0, evidence_factor=0.0)

        return EvidenceAssessment(
            evidence=FieldEvidence(
                block_id=block.block_id,
                page=page.page,
                snippet=needle,
                match=match,
                similarity=round(score, 4),
            ),
            base=self.base_factor(page, block, needle),
            evidence_factor=self._factor(match),
        )

    def base_factor(self, page: DocumentPage, block: TextBlock, snippet: str) -> float:
        """Quality of the text a value was read from.

        A text layer is taken at face value; an OCR page is only as good as the
        engine's confidence in the words that make up the snippet.
        """
        if not page.is_ocr or not block.ocr_words:
            return 1.0

        snippet_words = {_word_key(token) for token in canonical_text(snippet).split()}
        snippet_words.discard("")
        if not snippet_words:
            return 1.0

        confidences = [
            word.conf
            for word in block.ocr_words
            if _word_key(word.text) in snippet_words
        ]
        if not confidences:
            # The snippet spans the block but matches no single word; fall back
            # to the block's own mean rather than assuming a clean read.
            confidences = [word.conf for word in block.ocr_words]

        return round(sum(confidences) / len(confidences), 4)

    def _best_match(
        self,
        document: DocumentText,
        needle: str,
        block_id: str | None,
    ) -> tuple[DocumentPage, TextBlock, float] | None:
        """Return the block the snippet matches best, with its similarity.

        A block the model cited is checked first and kept when it matches
        exactly; otherwise every block is searched, since a cited block can be
        wrong while the text is genuinely in the document.
        """
        candidates: list[tuple[DocumentPage, TextBlock]] = []

        if block_id and (cited := document.find_block(block_id)):
            score = partial_similarity(needle, cited[1].text)
            if score >= 1.0:
                return cited[0], cited[1], score
            candidates.append(cited)

        best: tuple[DocumentPage, TextBlock, float] | None = None

        for page, block in document.iter_blocks():
            if not block.text.strip():
                continue
            score = partial_similarity(needle, block.text)
            if best is None or score > best[2]:
                best = (page, block, score)
            if score >= 1.0:
                break

        return best

    def _classify(self, score: float) -> EvidenceMatch | None:
        """Turn a similarity into a match class, or ``None`` to reject."""
        if score >= 1.0:
            return EvidenceMatch.EXACT
        if score >= self._settings.evidence_fuzzy_high_similarity:
            return EvidenceMatch.FUZZY_HIGH
        if score >= self._settings.evidence_fuzzy_low_similarity:
            return EvidenceMatch.FUZZY_LOW
        return None

    def _factor(self, match: EvidenceMatch) -> float:
        return {
            EvidenceMatch.EXACT: 1.0,
            EvidenceMatch.FUZZY_HIGH: self._settings.evidence_fuzzy_high_factor,
            EvidenceMatch.FUZZY_LOW: self._settings.evidence_fuzzy_low_factor,
        }[match]
