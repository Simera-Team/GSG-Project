"""Language detection for incoming sources (R-11).

Only English sources are accepted. Sources in other languages are rejected
before calling the language model, saving provider calls on files that will
not be processed.

Detection is deterministic with no external dependencies:
1. At least 80% of alphabetic characters must be Latin letters (A-Z, a-z).
2. The text must contain at least 3 distinct English markers from a fixed list
   of common function words and standard CV section headings.
"""

import re
from typing import Final

# Thresholds placed in one location for easy tuning
MIN_LETTERS_FOR_CHECK: Final[int] = 200
MIN_LATIN_RATIO: Final[float] = 0.80
MIN_ENGLISH_MARKERS: Final[int] = 3

ENGLISH_FUNCTION_WORDS: Final[frozenset[str]] = frozenset({
    "the", "and", "of", "in", "to", "with", "for", "at", "on", "from"
})

ENGLISH_SECTION_HEADINGS: Final[frozenset[str]] = frozenset({
    "experience", "education", "skills", "summary", "projects",
    "certifications", "languages"
})

ENGLISH_MARKERS: Final[frozenset[str]] = frozenset(
    ENGLISH_FUNCTION_WORDS | ENGLISH_SECTION_HEADINGS
)


class LanguageRule:
    """Rule identifier for source language checks."""
    UNSUPPORTED_LANGUAGE = "R-11"


def is_english(text: str) -> bool:
    """Check if the extracted source text is in English.

    Returns True if the text qualifies as English, or if it has fewer than
    200 alphabetic characters (in which case the language check is skipped,
    leaving the file to the no-usable-text path FR-020).
    """
    letters = [c for c in text if c.isalpha()]
    if len(letters) < MIN_LETTERS_FOR_CHECK:
        return True

    latin_count = sum(1 for c in letters if "a" <= c <= "z" or "A" <= c <= "Z")
    if (latin_count / len(letters)) < MIN_LATIN_RATIO:
        return False

    words = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
    if len(words & ENGLISH_MARKERS) < MIN_ENGLISH_MARKERS:
        return False

    return True

