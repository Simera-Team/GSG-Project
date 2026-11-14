"""Deterministic string comparison used by evidence checks, skills and matching.

Everything here is stdlib only and order-independent, so the same inputs always
give the same score (NFR-023). The contract names ``rapidfuzz`` as an example
of a fuzzy ratio; :func:`partial_similarity` keeps the same semantics without
adding a dependency, and can be swapped for it behind this module.
"""

import re
import unicodedata
from difflib import SequenceMatcher

_WHITESPACE = re.compile(r"\s+")

#: Dash and quote characters a model commonly swaps for their ASCII form.
_PUNCTUATION_FOLDING = str.maketrans(
    {
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        " ": " ",
    }
)


def canonical_text(value: str) -> str:
    """Return ``value`` folded for comparison.

    Case, surrounding whitespace, repeated spaces and the punctuation variants a
    model tends to rewrite are all removed, so a difference in any of them does
    not look like a difference in content.
    """
    folded = unicodedata.normalize("NFKC", value).translate(_PUNCTUATION_FOLDING)
    return _WHITESPACE.sub(" ", folded).strip().casefold()


def similarity(left: str, right: str) -> float:
    """Return how similar two whole strings are, from 0 to 1."""
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def partial_similarity(needle: str, haystack: str) -> float:
    """Return how much of ``needle`` appears in ``haystack``, from 0 to 1.

    A whole-string ratio would punish a short snippet quoted from a long block,
    so the snippet is compared against the best-aligned window of the block
    instead. Both sides are folded by :func:`canonical_text` first.
    """
    needle_text = canonical_text(needle)
    haystack_text = canonical_text(haystack)

    if not needle_text or not haystack_text:
        return 0.0
    if needle_text in haystack_text:
        return 1.0
    if len(needle_text) >= len(haystack_text):
        return similarity(needle_text, haystack_text)

    best = 0.0
    width = len(needle_text)
    matcher = SequenceMatcher(None, needle_text, haystack_text)

    for _, start, size in matcher.get_matching_blocks():
        if size == 0:
            continue
        # Centre a snippet-sized window on each anchor the matcher found, so
        # the comparison sees the same amount of text on both sides.
        centre = start + size // 2
        left = max(0, min(centre - width // 2, len(haystack_text) - width))
        window = haystack_text[left : left + width]
        best = max(best, similarity(needle_text, window))
        if best == 1.0:
            break

    return best


def bounded_edit_distance(left: str, right: str, max_distance: int) -> int | None:
    """Return the edit distance, or ``None`` once it exceeds ``max_distance``.

    Swapping two adjacent characters counts as one edit, not two, because that
    is how typing errors actually happen: "Pyhton" is one slip away from
    "Python", and the skill rules' own allowance of a single edit for a short
    name only works if it is counted that way.

    Giving up early keeps alias lookups cheap, since the rules never ask about
    distances beyond two.
    """
    if abs(len(left) - len(right)) > max_distance:
        return None
    if left == right:
        return 0

    before_previous: list[int] = []
    previous = list(range(len(right) + 1))

    for i, left_char in enumerate(left, start=1):
        current = [i] + [0] * len(right)
        for j, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current[j] = min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + cost,
            )
            transposed = (
                i > 1
                and j > 1
                and left_char == right[j - 2]
                and left[i - 2] == right_char
            )
            if transposed:
                current[j] = min(current[j], before_previous[j - 2] + 1)

        if min(current) > max_distance:
            return None
        before_previous, previous = previous, current

    distance = previous[-1]
    return distance if distance <= max_distance else None
